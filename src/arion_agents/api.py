import os
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
import logging
from logging.handlers import RotatingFileHandler
from arion_agents.prompts.context_builder import (
    build_constraints,
    build_context,
    build_prompt,
    build_tool_definitions,
    build_route_definitions,
)

from arion_agents.runtime_models import CompiledGraph
from arion_agents.system_params import merge_with_defaults

# Basic logging config; level via LOG_LEVEL (default INFO)
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
try:
    logging.basicConfig(
        level=getattr(logging, _LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
except Exception:
    pass


def _project_root() -> Path:
    # src/arion_agents/api.py -> repo_root/arion_agents
    return Path(__file__).resolve().parents[2]


@dataclass
class GraphBundle:
    graph: dict
    network_id: int
    network_version_id: int
    graph_version_key: str


def _setup_file_logging() -> None:
    try:
        root = logging.getLogger()
        logs_dir = _project_root() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = (logs_dir / "server.log").resolve()
        # Avoid duplicate handlers on reload
        existing = [getattr(h, "baseFilename", None) for h in root.handlers]
        if str(log_path) not in (str(p) for p in existing if p):
            handler = RotatingFileHandler(
                log_path, maxBytes=5 * 1024 * 1024, backupCount=3
            )
            handler.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            root.addHandler(handler)
    except Exception:
        # Never crash the app because of logging setup
        pass


_setup_file_logging()

app = FastAPI(title="arion_agents API")

_allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    _setup_file_logging()
    try:
        from arion_agents.db import init_db

        init_db()
    except Exception:
        logging.getLogger(__name__).exception("Failed to initialize database tables")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class InvokeRequest(BaseModel):
    instruction: dict
    network: str  # network name (slug)
    agent_key: str
    version: int | None = None
    allow_respond: bool = True
    system_params: dict = Field(default_factory=dict)


class LLMCompleteRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.post("/llm/complete")
async def llm_complete(payload: LLMCompleteRequest) -> dict:
    """Test endpoint to verify Gemini connectivity and return a completion.

    Requires env var GEMINI_API_KEY. Optional GEMINI_MODEL or request.model.
    """
    try:
        from arion_agents.llm import gemini_complete

        text = gemini_complete(payload.prompt, payload.model)
        return {
            "model": payload.model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            "text": text,
        }
    except Exception as e:  # Catch config and runtime errors
        msg = str(e)
        raise HTTPException(status_code=400, detail=msg)


class DraftInstructionRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.post("/llm/draft-instruction")
async def draft_instruction(payload: DraftInstructionRequest) -> dict:
    """Generate a structured Instruction using Pydantic AI with Gemini.

    Uses disabled thinking via google_thinking_config with budget 0.
    """
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.google import GoogleModel, GoogleProvider
        from pydantic_ai.models import ModelSettings
        from arion_agents.orchestrator import Instruction
        from arion_agents.llm import _require_gemini_config

        api_key, default_model = _require_gemini_config()
        model_name = payload.model or default_model
        settings = ModelSettings(google_thinking_config={"thinking_budget": 0})
        provider = GoogleProvider(api_key=api_key)
        model = GoogleModel(model_name, provider=provider, settings=settings)
        agent = Agent(model=model, output_type=Instruction)
        # Provide minimal instruction; output_type drives schema (async)
        res = await agent.run(payload.prompt)
        out = res.output
        return {"model": model_name, "instruction": out.model_dump()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _build_constraints_text(cfg) -> str:
    lines = []
    lines.append(
        "You MUST respond as JSON with fields: action (USE_TOOL|ROUTE_TO_AGENT|RESPOND), action_reasoning (string), action_details (object)."
    )
    if cfg.equipped_tools:
        lines.append("Allowed tools and agent-provided params:")
        for k in cfg.equipped_tools:
            ts = cfg.tools_map.get(k)
            if not ts:
                continue
            # ts may be a dict or a ToolRuntimeSpec
            params_schema = getattr(ts, "params_schema", None)
            if params_schema is None and isinstance(ts, dict):
                params_schema = ts.get("params_schema")
            ps = [
                name
                for name, spec in (params_schema or {}).items()
                if (spec or {}).get("source", "agent") == "agent"
            ]
            lines.append(f"- {k}: params={ps}")
    if cfg.allowed_routes:
        lines.append("Allowed routes (agent keys):")
        for r in cfg.allowed_routes:
            lines.append(f"- {r}")
    lines.append(
        "When using USE_TOOL, action_details must be an object with 'tool_name' (string) and 'tool_params' (object)."
    )
    lines.append(
        "When using ROUTE_TO_AGENT, action_details must be an object with 'target_agent_name' (string) and 'context' (object)."
    )
    lines.append(
        "When using RESPOND, action_details must be an object with 'payload' (object)."
    )
    return "\n".join(lines)


class RunOnceRequest(BaseModel):
    network: str | None = None
    agent_key: str | None = None
    user_message: str
    version: int | None = None
    system_params: dict = Field(default_factory=dict)
    model: str | None = None
    debug: bool = False
    snapshot: CompiledGraph | None = None

    @model_validator(mode="after")
    def _require_target(cls, data: "RunOnceRequest"):
        if (data.network is None) == (data.snapshot is None):
            raise ValueError("Provide exactly one of 'network' or 'snapshot'")
        return data


@app.post("/run")
async def run_once(payload: RunOnceRequest) -> dict:
    """One-step run: LLM decision → translate → execute → return result.

    Uses compiled prompt + constraints; enforces structured JSON via google-genai JSON mode.
    """
    # Per-run log record
    run_started = time.time()
    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_id = uuid.uuid4().hex
    merged_system_params = merge_with_defaults(payload.system_params)

    request_payload = payload.model_dump()
    request_payload["system_params"] = merged_system_params
    request_payload["trace_id"] = run_id

    run_record = {
        "request": request_payload,
        "started_at_utc": run_ts,
        "run_id": run_id,
    }
    out: dict | None = None
    try:
        from arion_agents.engine.loop import run_loop

        if payload.snapshot is not None:
            graph = payload.snapshot.as_dict()
            network_id = None
            network_version_id = payload.snapshot.version_id
            graph_version_key = (
                str(payload.snapshot.version_id)
                if payload.snapshot.version_id is not None
                else None
            )
        else:
            assert payload.network is not None  # validated upstream
            bundle = _load_graph_from_db(payload.network, payload.version)
            graph = bundle.graph
            network_id = bundle.network_id
            network_version_id = bundle.network_version_id
            graph_version_key = bundle.graph_version_key

        default_agent = payload.agent_key or graph.get("default_agent_key")
        if not default_agent:
            raise HTTPException(
                status_code=400,
                detail="No default agent in snapshot and no agent_key provided",
            )

        def _get_cfg(agent_key: str):
            return _build_run_config_from_graph(
                graph, agent_key, True, merged_system_params
            )

        out = run_loop(
            _get_cfg,
            default_agent,
            payload.user_message,
            max_steps=10,
            model=payload.model,
            debug=payload.debug,
        )
        if out is None:
            out = {}
        out.setdefault("trace_id", run_id)
        if graph_version_key is not None:
            out.setdefault("graph_version_id", graph_version_key)
        out.setdefault("network_id", network_id)
        out.setdefault("system_params", merged_system_params)

        step_events = out.get("step_events")
        if isinstance(step_events, list):
            for idx, env in enumerate(step_events):
                if not isinstance(env, dict):
                    continue
                env.setdefault("traceId", run_id)
                env.setdefault("seq", idx)
                if "t" not in env or env["t"] is None:
                    env["t"] = int(time.time() * 1000)

        try:
            from arion_agents.run_models import RunRecord
            from arion_agents.db import get_session

            status = (
                (out.get("final") or {}).get("status")
                if isinstance(out.get("final"), dict)
                else None
            )
            with get_session() as db:
                db.add(
                    RunRecord(
                        run_id=run_id,
                        network_id=network_id,
                        network_version_id=network_version_id,
                        graph_version_key=graph_version_key,
                        user_message=payload.user_message,
                        status=status or "unknown",
                        request_payload=request_payload,
                        response_payload=out,
                    )
                )
        except Exception:
            # Persistence failure should not block the response; errors are logged later.
            pass

        return out
    except HTTPException:
        raise
    except Exception as e:
        import logging

        logging.exception("Error in run_once")
        run_record["error"] = str(e)
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            runs_dir = _project_root() / "logs" / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            run_record["response"] = out
            run_record["duration_ms"] = int((time.time() - run_started) * 1000)
            # Use milliseconds to avoid collisions
            ms = int(run_started * 1000)
            fname = f"run_{run_ts}_{ms}.json"
            with open(runs_dir / fname, "w", encoding="utf-8") as f:
                json.dump(run_record, f, indent=2)
        except Exception:
            pass


def _load_graph_from_db(network: str, version: int | None) -> GraphBundle:
    if not network:
        raise HTTPException(status_code=400, detail="Network name is required")

    from sqlalchemy import select, func
    from arion_agents.db import get_session
    from arion_agents.config_models import Network, NetworkVersion, CompiledSnapshot

    with get_session() as db:
        net = db.scalar(
            select(Network).where(func.lower(Network.name) == network.strip().lower())
        )
        if not net:
            raise HTTPException(
                status_code=404, detail=f"Network '{network}' not found"
            )
        if version is not None:
            ver = db.scalar(
                select(NetworkVersion).where(
                    (NetworkVersion.network_id == net.id)
                    & (NetworkVersion.version == version)
                )
            )
            if not ver:
                raise HTTPException(
                    status_code=404,
                    detail=f"Version {version} not found for network '{network}'",
                )
            ver_id = ver.id
        else:
            ver_id = net.current_version_id
            if ver_id:
                ver = db.get(NetworkVersion, ver_id)
            else:
                ver = None
        if not ver_id or not ver:
            raise HTTPException(
                status_code=400, detail="No published version for network"
            )
        snap = db.scalar(
            select(CompiledSnapshot).where(
                CompiledSnapshot.network_version_id == ver_id
            )
        )
        if not snap:
            raise HTTPException(
                status_code=500, detail="Compiled snapshot missing for version"
            )
        graph = snap.compiled_graph or {}
        graph_version_key = f"{net.id}:{ver.version}"
        return GraphBundle(
            graph=graph,
            network_id=net.id,
            network_version_id=ver_id,
            graph_version_key=graph_version_key,
        )


def _build_run_config_from_graph(
    graph: dict, agent_key: str, allow_respond: bool, system_params: dict
):
    from arion_agents.orchestrator import RunConfig

    agents = {a["key"].lower(): a for a in graph.get("agents", [])}
    tools = {t["key"].lower(): t for t in graph.get("tools", [])}
    lookup = agent_key.strip().lower()
    agent = agents.get(lookup)
    if not agent:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_key}' not in snapshot"
        )

    equipped = list(agent.get("equipped_tools", []))
    routes = list(agent.get("allowed_routes", []))
    allow = bool(agent.get("allow_respond", False)) and allow_respond
    prompt = agent.get("prompt")

    tools_map = {}
    for tk in equipped:
        item = tools.get(str(tk).strip().lower())
        if not item:
            continue
        tools_map[item["key"]] = {
            "key": item["key"],
            "provider_type": item.get("provider_type") or "",
            "params_schema": item.get("params_schema") or {},
            "secret_ref": item.get("secret_ref"),
            "metadata": item.get("metadata") or {},
            "description": item.get("description") or None,
        }

    return RunConfig(
        current_agent=agent["key"],
        equipped_tools=equipped,
        tools_map=tools_map,
        allowed_routes=routes,
        allow_respond=allow,
        system_params=system_params or {},
        prompt=prompt,
    )


def _load_run_record(run_id: str):
    from sqlalchemy import select
    from arion_agents.run_models import RunRecord
    from arion_agents.db import get_session

    with get_session() as db:
        stmt = select(RunRecord).where(RunRecord.run_id == run_id)
        run = db.exec(stmt).scalars().first()
        if run is None:
            return None
        db.expunge(run)
        return run


def _run_record_to_snapshot(record, include_steps: bool = True) -> dict:
    response_payload = record.response_payload or {}
    step_events = response_payload.get("step_events") if include_steps else []
    envelopes: list[dict] = []
    if include_steps and isinstance(step_events, list):
        for idx, env in enumerate(step_events):
            if not isinstance(env, dict):
                continue
            seq = env.get("seq", idx)
            t_val = env.get("t")
            try:
                t_int = int(t_val) if t_val is not None else None
            except Exception:
                t_int = None
            step_payload = env.get("step")
            if not isinstance(step_payload, dict):
                continue
            envelopes.append(
                {
                    "traceId": record.run_id,
                    "seq": seq,
                    "t": t_int or 0,
                    "step": step_payload,
                }
            )

    response_system_params = None
    if isinstance(record.response_payload, dict):
        response_system_params = record.response_payload.get("system_params")

    metadata = {
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "status": record.status,
        "network_id": record.network_id,
        "network_version_id": record.network_version_id,
        "graph_version_key": record.graph_version_key,
        "user_message": record.user_message,
        "system_params": response_system_params,
    }
    final_payload = (
        response_payload.get("final") if isinstance(response_payload, dict) else None
    )
    if final_payload is not None:
        metadata["final"] = final_payload

    return {
        "traceId": record.run_id,
        "graphVersionId": record.graph_version_key,
        "steps": envelopes,
        "metadata": metadata,
    }


@app.post("/invoke")
async def invoke(payload: InvokeRequest) -> dict:
    from arion_agents.orchestrator import Instruction, execute_instruction

    bundle = _load_graph_from_db(payload.network, payload.version)
    instr = Instruction.model_validate(payload.instruction)
    cfg = _build_run_config_from_graph(
        bundle.graph,
        payload.agent_key,
        payload.allow_respond,
        merge_with_defaults(payload.system_params),
    )
    result = execute_instruction(instr, cfg)
    return {"trace_id": None, "result": result.model_dump()}


@app.get("/runs")
async def list_runs(limit: int = 20) -> list[dict]:
    from sqlalchemy import select
    from arion_agents.run_models import RunRecord
    from arion_agents.db import get_session

    if limit <= 0:
        limit = 20

    with get_session() as db:
        stmt = select(RunRecord).order_by(RunRecord.created_at.desc()).limit(limit)
        records = list(db.exec(stmt).scalars())
        for rec in records:
            db.expunge(rec)
    return [_run_record_to_snapshot(rec, include_steps=False) for rec in records]


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    record = _load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_record_to_snapshot(record, include_steps=True)


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, from_seq: int | None = None) -> StreamingResponse:
    record = _load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="run not found")

    snapshot = _run_record_to_snapshot(record, include_steps=True)
    envelopes = snapshot.get("steps") or []
    if from_seq is not None:
        envelopes = [env for env in envelopes if env.get("seq", 0) >= from_seq]

    def _event_stream():
        for env in envelopes:
            payload = json.dumps(env)
            yield f"event: run.step\ndata: {payload}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


# Config router
try:
    from .api_config import router as config_router  # type: ignore

    app.include_router(config_router, prefix="/config", tags=["config"])
except Exception:
    # Keep API importable even if config store is misconfigured
    pass


class ResolvePromptRequest(BaseModel):
    network: str
    agent_key: str | None = None
    user_message: str
    version: int | None = None


@app.post("/prompts/resolve")
async def resolve_prompt(payload: ResolvePromptRequest) -> dict:
    """Return the fully-resolved prompt string that would be sent to the LLM for the given agent.

    Uses current compiled base prompt + empty tool history + constraints.
    """
    try:
        bundle = _load_graph_from_db(payload.network, payload.version)
        graph = bundle.graph

        agent_key = payload.agent_key or graph.get("default_agent_key")
        if not agent_key:
            raise HTTPException(
                status_code=400,
                detail="No default agent in snapshot and no agent_key provided",
            )

        cfg = _build_run_config_from_graph(graph, agent_key, True, {})
        constraints = build_constraints(cfg)
        context = build_context(payload.user_message, exec_log=[], full_tool_outputs=[])
        tool_defs = build_tool_definitions(cfg)
        route_defs = build_route_definitions(cfg)
        prompt = build_prompt(
            cfg, cfg.prompt, context, constraints, tool_defs, route_defs
        )
        return {"agent_key": agent_key, "prompt": prompt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
