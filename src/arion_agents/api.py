import os
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

# OpenTelemetry is optional at import time. We lazy-import and no-op if missing.
_OTEL_AVAILABLE = True
try:  # defer imports so IDEs/tests don’t break if OTel isn’t installed yet
    from opentelemetry import trace  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import (  # type: ignore
        FastAPIInstrumentor,
    )
except Exception:  # pragma: no cover
    _OTEL_AVAILABLE = False


def _format_trace_id(trace_id: int) -> str:
    return f"{trace_id:032x}"


def setup_tracing() -> None:
    if not _OTEL_AVAILABLE:
        return
    if os.getenv("OTEL_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "arion_agents_api")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Use insecure=True for local dev endpoints over http
    insecure = endpoint.startswith("http://")
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


setup_tracing()
app = FastAPI(title="arion_agents API")
if _OTEL_AVAILABLE and os.getenv("OTEL_ENABLED", "true").lower() in {"1", "true", "yes"}:
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        # Don’t fail app import if instrumentation errors out
        pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class InvokeRequest(BaseModel):
    instruction: dict
    network: str  # network name (slug)
    agent_key: str
    version: int | None = None
    allow_respond: bool = True
    system_params: dict = {}


class LLMCompleteRequest(BaseModel):
    prompt: str
    model: str | None = None


@app.post("/llm/complete")
async def llm_complete(payload: LLMCompleteRequest) -> dict:
    """Test endpoint to verify Gemini connectivity and return a completion.

    Requires env var GEMINI_API_KEY. Optional GEMINI_MODEL or request.model.
    """
    try:
        from arion_agents.llm import gemini_complete, LLMNotConfigured

        text = gemini_complete(payload.prompt, payload.model)
        return {"model": payload.model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash"), "text": text}
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
    lines.append("You MUST respond as JSON with fields: action (USE_TOOL|ROUTE_TO_AGENT|RESPOND), action_reasoning (string), action_details (object).")
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
            ps = [name for name, spec in (params_schema or {}).items() if (spec or {}).get("source", "agent") == "agent"]
            lines.append(f"- {k}: params={ps}")
    if cfg.allowed_routes:
        lines.append("Allowed routes (agent keys):")
        for r in cfg.allowed_routes:
            lines.append(f"- {r}")
    lines.append("When using USE_TOOL, action_details must include tool_name and tool_params.")
    lines.append("When routing, action_details must include target_agent_name.")
    lines.append("When responding, put your payload in action_details.payload.")
    return "\n".join(lines)


class RunOnceRequest(BaseModel):
    network: str
    agent_key: str | None = None
    user_message: str
    version: int | None = None
    system_params: dict = {}
    model: str | None = None
    debug: bool = False


@app.post("/run")
async def run_once(payload: RunOnceRequest) -> dict:
    """One-step run: LLM decision → translate → execute → return result.

    Uses compiled prompt + constraints; enforces structured JSON via google-genai JSON mode.
    """
    try:
        from arion_agents.engine.loop import run_loop

        # Resolve default agent from snapshot if not provided
        from sqlalchemy import select, func
        from arion_agents.db import get_session
        from arion_agents.config_models import Network, NetworkVersion, CompiledSnapshot

        with get_session() as db:
            net = db.scalar(select(Network).where(func.lower(Network.name) == payload.network.strip().lower()))
            if not net:
                raise HTTPException(status_code=404, detail=f"Network '{payload.network}' not found")
            if payload.version is not None:
                ver = db.scalar(
                    select(NetworkVersion).where(
                        (NetworkVersion.network_id == net.id) & (NetworkVersion.version == payload.version)
                    )
                )
                if not ver:
                    raise HTTPException(status_code=404, detail=f"Version {payload.version} not found for network '{payload.network}'")
                ver_id = ver.id
            else:
                ver_id = net.current_version_id
            if not ver_id:
                raise HTTPException(status_code=400, detail="No published version for network")
            snap = db.scalar(select(CompiledSnapshot).where(CompiledSnapshot.network_version_id == ver_id))
            if not snap:
                raise HTTPException(status_code=500, detail="Compiled snapshot missing for version")
            graph = snap.compiled_graph or {}

        default_agent = payload.agent_key or graph.get("default_agent_key")
        if not default_agent:
            raise HTTPException(status_code=400, detail="No default agent in snapshot and no agent_key provided")

        def _get_cfg(agent_key: str):
            return _build_run_config(payload.network, agent_key, payload.version, True, payload.system_params)

        out = run_loop(
            _get_cfg,
            default_agent,
            payload.user_message,
            max_steps=10,
            model=payload.model,
            debug=payload.debug,
        )
        return out
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _build_run_config(network: str, agent_key: str, version: int | None, allow_respond: bool, system_params: dict):
    from sqlalchemy import select, func
    from arion_agents.db import get_session
    from arion_agents.config_models import Network, NetworkVersion, CompiledSnapshot
    from arion_agents.orchestrator import RunConfig

    with get_session() as db:
        net = db.scalar(select(Network).where(func.lower(Network.name) == network.strip().lower()))
        if not net:
            raise HTTPException(status_code=404, detail=f"Network '{network}' not found")
        ver_id = None
        if version is not None:
            ver = db.scalar(
                select(NetworkVersion).where(
                    (NetworkVersion.network_id == net.id) & (NetworkVersion.version == version)
                )
            )
            if not ver:
                raise HTTPException(status_code=404, detail=f"Version {version} not found for network '{network}'")
            ver_id = ver.id
        else:
            ver_id = net.current_version_id
        if not ver_id:
            raise HTTPException(status_code=400, detail="No published version for network")
        snap = db.scalar(select(CompiledSnapshot).where(CompiledSnapshot.network_version_id == ver_id))
        if not snap:
            raise HTTPException(status_code=500, detail="Compiled snapshot missing for version")
        graph = snap.compiled_graph or {}
        # Build config for the requested agent
        agents = {a["key"].lower(): a for a in graph.get("agents", [])}
        tools = {t["key"].lower(): t for t in graph.get("tools", [])}
        a = agents.get(agent_key.strip().lower())
        if not a:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not in snapshot")
        equipped = list(a.get("equipped_tools", []))
        routes = list(a.get("allowed_routes", []))
        allow = bool(a.get("allow_respond", False)) and allow_respond
        prompt = a.get("prompt")
        # Build tools_map for current agent
        tools_map = {}
        for tk in equipped:
            item = tools.get(str(tk).strip().lower())
            if not item:
                # tool not present in snapshot; skip
                continue
            tools_map[item["key"]] = {
                "key": item["key"],
                "provider_type": item.get("provider_type") or "",
                "params_schema": item.get("params_schema") or {},
                "secret_ref": item.get("secret_ref"),
                "metadata": item.get("metadata") or {},
            }
        return RunConfig(
            current_agent=a["key"],
            equipped_tools=equipped,
            tools_map=tools_map,
            allowed_routes=routes,
            allow_respond=allow,
            system_params=system_params or {},
            prompt=prompt,
        )


@app.post("/invoke")
async def invoke(payload: InvokeRequest) -> dict:
    # Lazy import here to keep api.py light
    from arion_agents.orchestrator import Instruction, execute_instruction

    if _OTEL_AVAILABLE and os.getenv("OTEL_ENABLED", "true").lower() in {"1", "true", "yes"}:
        tracer = trace.get_tracer("arion_agents.orchestrator")
        with tracer.start_as_current_span("invoke") as span:
            span.set_attribute("request.payload_size", len(str(payload.model_dump())))
            trace_id = _format_trace_id(span.get_span_context().trace_id)
            instr = Instruction.model_validate(payload.instruction)
            cfg = _build_run_config(payload.network, payload.agent_key, payload.version, payload.allow_respond, payload.system_params)
            result = execute_instruction(instr, cfg)
            return {"trace_id": trace_id, "result": result.model_dump()}
    # Fallback when OTel is not available/disabled
    instr = Instruction.model_validate(payload.instruction)
    cfg = _build_run_config(payload.network, payload.agent_key, payload.version, payload.allow_respond, payload.system_params)
    result = execute_instruction(instr, cfg)
    return {"trace_id": None, "result": result.model_dump()}

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
        from arion_agents.prompts.context_builder import build_constraints, build_context, build_prompt
        # Identify default agent if not provided
        from sqlalchemy import select, func
        from arion_agents.db import get_session
        from arion_agents.config_models import Network, NetworkVersion, CompiledSnapshot

        with get_session() as db:
            net = db.scalar(select(Network).where(func.lower(Network.name) == payload.network.strip().lower()))
            if not net:
                raise HTTPException(status_code=404, detail=f"Network '{payload.network}' not found")
            if payload.version is not None:
                ver = db.scalar(
                    select(NetworkVersion).where(
                        (NetworkVersion.network_id == net.id) & (NetworkVersion.version == payload.version)
                    )
                )
                if not ver:
                    raise HTTPException(status_code=404, detail=f"Version {payload.version} not found for network '{payload.network}'")
                ver_id = ver.id
            else:
                ver_id = net.current_version_id
            if not ver_id:
                raise HTTPException(status_code=400, detail="No published version for network")
            snap = db.scalar(select(CompiledSnapshot).where(CompiledSnapshot.network_version_id == ver_id))
            if not snap:
                raise HTTPException(status_code=500, detail="Compiled snapshot missing for version")
            graph = snap.compiled_graph or {}

        agent_key = payload.agent_key or graph.get("default_agent_key")
        if not agent_key:
            raise HTTPException(status_code=400, detail="No default agent in snapshot and no agent_key provided")

        # Build a transient cfg and resolve prompt
        cfg = _build_run_config(payload.network, agent_key, payload.version, True, {})
        constraints = build_constraints(cfg)
        context = build_context(payload.user_message, exec_log=[], full_tool_outputs=[])
        prompt = build_prompt(cfg.prompt, context, constraints)
        return {"agent_key": agent_key, "prompt": prompt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
