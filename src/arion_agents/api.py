import asyncio
import csv
import io
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache
import sqlalchemy as sa
from sqlmodel import Session
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
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
from arion_agents.db import get_session
from arion_agents.run_models import (
    ExperimentQueueRecord,
    ExperimentQueueStatus,
    ExperimentRecord,
    RunRecord,
    enqueue_queue_items,
    lease_next_queue_item,
    mark_queue_item_completed,
)

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


def _combine_description_prompt(
    description: Optional[str], prompt: Optional[str]
) -> Optional[str]:
    parts: list[str] = []
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    if isinstance(prompt, str) and prompt.strip():
        parts.append(prompt.strip())
    if not parts:
        return None
    return "\n\n".join(parts)


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


_queue_worker_lock = asyncio.Lock()
_queue_worker_task: asyncio.Task[Any] | None = None
_FORCE_DEBUG_LOGGING = os.getenv("DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
    "debug",
}


@app.on_event("startup")
async def _startup() -> None:
    _setup_file_logging()
    try:
        from arion_agents.db import init_db

        init_db()
    except Exception:
        logging.getLogger(__name__).exception("Failed to initialize database tables")

    await _ensure_queue_worker()


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
    experiment_id: str | None = None
    experiment_desc: str | None = None
    experiment_item_index: int | None = None
    experiment_iteration: int | None = None
    experiment_item_payload: dict | None = None
    max_steps: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _require_target(cls, data: "RunOnceRequest"):
        if (data.network is None) == (data.snapshot is None):
            raise ValueError("Provide exactly one of 'network' or 'snapshot'")
        return data


class ExperimentItem(BaseModel):
    user_message: str
    correct_answer: str | None = None
    iterations: int = Field(default=1, ge=1)
    system_params: dict = Field(default_factory=dict)
    metadata: dict | None = None
    label: str | None = None


class RunBatchRequest(BaseModel):
    experiment_id: str
    experiment_desc: str | None = None
    network: str
    agent_key: str | None = None
    version: int | None = None
    model: str | None = None
    debug: bool = False
    shared_system_params: dict = Field(default_factory=dict)
    items: List[ExperimentItem]
    max_steps: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_items(cls, data: "RunBatchRequest"):
        if not data.items:
            raise ValueError("items must contain at least one entry")
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
    merged_system_params.setdefault("dialogflow_session_id", uuid.uuid4().hex)

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

        max_steps = payload.max_steps or 10
        debug_enabled = payload.debug or _FORCE_DEBUG_LOGGING
        out = await asyncio.to_thread(
            run_loop,
            _get_cfg,
            default_agent,
            payload.user_message,
            max_steps=max_steps,
            model=payload.model,
            debug=debug_enabled,
        )
        if out is None:
            out = {}
        out.setdefault("trace_id", run_id)
        if graph_version_key is not None:
            out.setdefault("graph_version_id", graph_version_key)
        out.setdefault("network_id", network_id)
        out.setdefault("system_params", merged_system_params)
        model_name = payload.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        out.setdefault("model", model_name)

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
                        experiment_id=payload.experiment_id,
                        experiment_desc=payload.experiment_desc,
                        experiment_item_index=payload.experiment_item_index,
                        experiment_iteration=payload.experiment_iteration,
                        experiment_item_payload=payload.experiment_item_payload,
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


_STALE_QUEUE_TIMEOUT = timedelta(minutes=5)


async def _ensure_queue_worker() -> None:
    global _queue_worker_task
    async with _queue_worker_lock:
        if _queue_worker_task and not _queue_worker_task.done():
            return
        _reset_stale_queue_items()
        loop = asyncio.get_running_loop()
        _queue_worker_task = loop.create_task(_drain_experiment_queue())


def _reset_stale_queue_items() -> None:
    logger = logging.getLogger(__name__)
    now = datetime.utcnow()
    cutoff = now - _STALE_QUEUE_TIMEOUT

    with get_session() as db:
        stmt = sa.select(ExperimentQueueRecord).where(
            ExperimentQueueRecord.status == ExperimentQueueStatus.IN_PROGRESS.value
        )

        if _STALE_QUEUE_TIMEOUT.total_seconds() > 0:
            stmt = stmt.where(
                sa.or_(
                    ExperimentQueueRecord.started_at.is_(None),
                    ExperimentQueueRecord.started_at < cutoff,
                )
            )

        stale_items = db.exec(stmt).scalars().all()
        if not stale_items:
            return

        for item in stale_items:
            logger.warning(
                "Resetting stale experiment queue item %s (started_at=%s)",
                item.id,
                item.started_at,
            )
            item.status = ExperimentQueueStatus.PENDING
            item.started_at = None
            item.completed_at = None
            item.error = None
            item.result = None
            db.add(item)


async def _drain_experiment_queue() -> None:
    logger = logging.getLogger(__name__)
    try:
        while True:
            record_id: int | None = None
            leased = False
            with get_session() as db:
                record = lease_next_queue_item(db)
                if record is not None:
                    leased = True
                    record_id = record.id
                    if record_id is None:
                        logger.warning("Lease returned queue item without id")
                        record_id = None
            if not leased:
                break
            if record_id is None:
                continue
            await _process_queue_record(record_id)
            await asyncio.sleep(0)
    except Exception:
        logger.exception("Experiment queue worker crashed")
    finally:
        _queue_worker_task = None


async def _process_queue_record(record_id: int) -> None:
    logger = logging.getLogger(__name__)
    with get_session() as db:
        record = db.get(ExperimentQueueRecord, record_id)
        if record is None:
            logger.warning("Queue item %s missing before processing", record_id)
            return
        payload = dict(record.payload or {})
        if _FORCE_DEBUG_LOGGING and not payload.get("debug"):
            payload["debug"] = True
        result_summary: dict[str, Any] = {
            "item_index": record.item_index,
            "iteration": record.iteration,
        }

    success = False
    error_text: str | None = None

    try:
        request = RunOnceRequest(**payload)
        result = await run_once(request)
        final_section = result.get("final") if isinstance(result, dict) else None
        final_status = (
            final_section.get("status") if isinstance(final_section, dict) else None
        )
        trace_id = result.get("trace_id") if isinstance(result, dict) else None
        result_summary.update({"trace_id": trace_id, "status": final_status})
        success = final_status in {None, "ok"}
        if not success:
            error_text = f"final status {final_status!r}"
    except HTTPException as exc:
        success = False
        error_text = f"HTTP {exc.status_code}: {exc.detail}"
        result_summary.setdefault("status", "error")
        result_summary["trace_id"] = None
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Experiment queue item %s failed", record_id)
        success = False
        error_text = str(exc)
        result_summary.setdefault("status", "error")
        result_summary["trace_id"] = None
    finally:
        try:
            if error_text:
                result_summary["error"] = error_text
            with get_session() as db:
                mark_queue_item_completed(
                    db,
                    record_id,
                    succeeded=success,
                    error=error_text,
                    result=result_summary,
                )
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to update queue item %s", record_id)


_CSV_REQUIRED_COLUMNS = ["iterations"]
_CSV_OPTIONAL_COLUMNS = [
    "user_message",
    "issue_description",
    "true_solution_description",
    "stopping_conditions",
    "correct_answer",
    "label",
]
_SYSTEM_PARAMS_PREFIX = "system_params"


def _decode_upload_bytes(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def _load_rows_from_csv(text: str) -> list[dict[str, Any]]:
    buffer = io.StringIO(text)
    try:
        reader = csv.DictReader(buffer)
    except csv.Error as exc:  # pragma: no cover - csv module raises on malformed header
        raise ValueError(f"Invalid CSV: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        if not raw_row:
            continue
        cleaned: dict[str, Any] = {}
        for key, value in raw_row.items():
            if key is None:
                continue
            clean_key = key.strip()
            if not clean_key:
                continue
            if isinstance(value, str):
                value = value.strip()
            cleaned[clean_key] = value
        if any(v not in (None, "") for v in cleaned.values()):
            rows.append(cleaned)
    return rows


def _load_rows_from_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {lineno}: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Line {lineno} must be a JSON object")
        shaped = {}
        for key, value in parsed.items():
            clean_key = str(key).strip()
            if clean_key:
                shaped[clean_key] = value
        if any(v not in (None, "") for v in shaped.values()):
            rows.append(shaped)
    return rows


def _coerce_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed == "":
            return ""
        lowered = trimmed.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if lowered == "null":
            return None
        if trimmed[0] in "[{" and trimmed[-1] in "]}":
            try:
                return json.loads(trimmed)
            except json.JSONDecodeError:
                return trimmed
        return trimmed
    return value


def _coerce_iterations(value: Any) -> tuple[int, str | None]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1, "iterations is missing or invalid; defaulting to 1"
    if parsed < 1:
        return 1, "iterations must be >= 1; defaulting to 1"
    return parsed, None


def _assign_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    if not path:
        return
    current = target
    for key in path[:-1]:
        existing = current.get(key)
        if not isinstance(existing, dict):
            existing = {}
            current[key] = existing
        current = existing
    current[path[-1]] = value


def _parse_system_param_path(raw_key: str) -> list[str]:
    if not raw_key.lower().startswith(_SYSTEM_PARAMS_PREFIX):
        return []
    suffix = raw_key[len(_SYSTEM_PARAMS_PREFIX) :]
    suffix = suffix.lstrip("._")
    if not suffix:
        return []
    normalized = suffix.replace("__", ".")
    parts = [part for part in normalized.split(".") if part]
    return parts


def _row_to_experiment_item(
    row: dict[str, Any]
) -> tuple[ExperimentItem | None, list[str], str | None]:
    metadata: dict[str, Any] = {}
    system_params: dict[str, Any] = {}
    warnings: list[str] = []
    iterations = 1
    user_message: str | None = None
    correct_answer: str | None = None
    label: str | None = None

    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip()
        if not key:
            continue
        lowered = key.lower()
        value = _coerce_jsonish(raw_value)

        if lowered == "iterations":
            iterations, warn = _coerce_iterations(value)
            if warn:
                warnings.append(warn)
        elif lowered == "user_message":
            user_message = str(value) if value is not None else None
        elif lowered == "correct_answer":
            correct_answer = (
                str(value) if value not in (None, "") else None
            )
        elif lowered == "label":
            label = str(value) if value not in (None, "") else None
        elif lowered in {
            "issue_description",
            "true_solution_description",
            "stopping_conditions",
        }:
            if value not in (None, ""):
                metadata[lowered] = value
        elif lowered.startswith(_SYSTEM_PARAMS_PREFIX):
            path = _parse_system_param_path(key)
            if not path:
                if isinstance(value, dict):
                    system_params.update(value)
                elif value not in (None, ""):
                    warnings.append(
                        "system_params column expects an object; value ignored"
                    )
            else:
                _assign_nested(system_params, path, value)
        else:
            if value not in (None, ""):
                metadata[key] = value

    if user_message is None or not str(user_message).strip():
        user_message = "start conversation"
        warnings.append(
            "user_message missing; defaulted to 'start conversation'"
        )

    try:
        item = ExperimentItem(
            user_message=str(user_message),
            correct_answer=correct_answer,
            iterations=iterations,
            system_params=system_params,
            metadata=metadata or None,
            label=label,
        )
        return item, warnings, None
    except ValidationError as exc:
        return None, warnings, exc.errors()[0].get("msg", str(exc))


def _collect_queue_stats(
    session: Session, experiment_ids: list[str] | None = None
) -> dict[str, dict[str, Any]]:
    total = sa.func.count(ExperimentQueueRecord.id).label("total")
    pending = sa.func.sum(
        sa.case(
            (ExperimentQueueRecord.status == ExperimentQueueStatus.PENDING.value, 1),
            else_=0,
        )
    ).label("pending")
    in_progress = sa.func.sum(
        sa.case(
            (ExperimentQueueRecord.status == ExperimentQueueStatus.IN_PROGRESS.value, 1),
            else_=0,
        )
    ).label("in_progress")
    completed = sa.func.sum(
        sa.case(
            (ExperimentQueueRecord.status == ExperimentQueueStatus.COMPLETED.value, 1),
            else_=0,
        )
    ).label("completed")
    failed = sa.func.sum(
        sa.case(
            (ExperimentQueueRecord.status == ExperimentQueueStatus.FAILED.value, 1),
            else_=0,
        )
    ).label("failed")

    stmt = (
        sa.select(
            ExperimentQueueRecord.experiment_id,
            total,
            pending,
            in_progress,
            completed,
            failed,
            sa.func.min(ExperimentQueueRecord.started_at).label("first_started_at"),
            sa.func.max(ExperimentQueueRecord.completed_at).label("last_completed_at"),
        )
        .group_by(ExperimentQueueRecord.experiment_id)
    )
    if experiment_ids:
        stmt = stmt.where(ExperimentQueueRecord.experiment_id.in_(experiment_ids))

    stats: dict[str, dict[str, Any]] = {}
    for row in session.exec(stmt):
        stats[row.experiment_id] = {
            "total": row.total or 0,
            "pending": row.pending or 0,
            "in_progress": row.in_progress or 0,
            "completed": row.completed or 0,
            "failed": row.failed or 0,
            "first_started_at": row.first_started_at,
            "last_completed_at": row.last_completed_at,
        }
    return stats


@app.post("/run-batch/upload")
async def upload_experiment_items(file: UploadFile = File(...)) -> dict:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    decoded = _decode_upload_bytes(payload)
    filename = (file.filename or "").lower()
    fmt = "jsonl" if filename.endswith(".jsonl") else "csv"

    try:
        raw_rows = (
            _load_rows_from_jsonl(decoded) if fmt == "jsonl" else _load_rows_from_csv(decoded)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items: list[ExperimentItem] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for idx, row in enumerate(raw_rows, start=1):
        item, row_warnings, error = _row_to_experiment_item(row)
        if row_warnings:
            warnings.extend({"row": idx, "message": w} for w in row_warnings)
        if error:
            errors.append({"row": idx, "error": error})
            continue
        if item is None:
            continue
        items.append(item)

    preview = [item.model_dump() for item in items[:5]]
    return {
        "format": fmt,
        "count": len(items),
        "items": [item.model_dump() for item in items],
        "preview": preview,
        "errors": errors,
        "warnings": warnings,
        "schema_hint": {
            "required": _CSV_REQUIRED_COLUMNS,
            "optional": _CSV_OPTIONAL_COLUMNS,
            "system_params_prefix": f"{_SYSTEM_PARAMS_PREFIX}.*",
        },
        "columns": list(raw_rows[0].keys()) if raw_rows else [],
    }


@app.post("/run-batch")
async def run_batch(payload: RunBatchRequest) -> dict:
    """Queue experiment runs for asynchronous execution."""

    experiment_payload = {
        "network": payload.network,
        "agent_key": payload.agent_key,
        "version": payload.version,
        "model": payload.model,
        "max_steps": payload.max_steps,
        "shared_system_params": payload.shared_system_params,
        "items": [item.model_dump() for item in payload.items],
    }

    queue_records: List[ExperimentQueueRecord] = []
    for item_index, item in enumerate(payload.items):
        total_iterations = max(int(item.iterations or 0), 0)
        if total_iterations == 0:
            continue
        for iteration in range(1, total_iterations + 1):
            combined_system_params = dict(payload.shared_system_params or {})
            combined_system_params.update(item.system_params or {})

            request = RunOnceRequest(
                network=payload.network,
                agent_key=payload.agent_key,
                user_message=item.user_message,
                version=payload.version,
                system_params=combined_system_params,
                model=payload.model,
                debug=payload.debug,
                experiment_id=payload.experiment_id,
                experiment_desc=payload.experiment_desc,
                experiment_item_index=item_index,
                experiment_iteration=iteration,
                experiment_item_payload={
                    "correct_answer": item.correct_answer,
                    "metadata": item.metadata,
                    "label": item.label,
                    "iterations": item.iterations,
                    "user_message": item.user_message,
                },
                max_steps=payload.max_steps,
            )

            queue_records.append(
                ExperimentQueueRecord(
                    experiment_id=payload.experiment_id,
                    item_index=item_index,
                    iteration=iteration,
                    payload=request.model_dump(),
                )
            )

    total_runs = len(queue_records)
    if total_runs == 0:
        raise HTTPException(status_code=400, detail="No iterations to queue")

    try:
        with get_session() as db:
            stmt = sa.select(ExperimentRecord).where(
                ExperimentRecord.experiment_id == payload.experiment_id
            )
            existing = db.exec(stmt).scalars().first()
            if existing:
                existing.description = payload.experiment_desc
                existing.payload = experiment_payload
            else:
                db.add(
                    ExperimentRecord(
                        experiment_id=payload.experiment_id,
                        description=payload.experiment_desc,
                        payload=experiment_payload,
                    )
                )
            enqueue_queue_items(db, queue_records)
    except Exception:
        logging.getLogger(__name__).exception("Failed to store experiment metadata")
        raise HTTPException(status_code=500, detail="Failed to queue experiment runs")

    await _ensure_queue_worker()

    return {
        "experiment_id": payload.experiment_id,
        "experiment_desc": payload.experiment_desc,
        "queued": True,
        "total_runs": total_runs,
    }


@app.get("/experiments")
async def list_experiments() -> list[dict]:
    with get_session() as db:
        experiments = (
            db.exec(
                sa.select(ExperimentRecord).order_by(ExperimentRecord.created_at.desc())
            )
            .scalars()
            .all()
        )
        experiment_ids = [exp.experiment_id for exp in experiments]
        stats_map = _collect_queue_stats(db, experiment_ids)

        results: list[dict[str, Any]] = []
        for exp in experiments:
            stats = stats_map.get(exp.experiment_id, {})
            results.append(
                {
                    "experiment_id": exp.experiment_id,
                    "description": exp.description,
                    "created_at": exp.created_at,
                    "updated_at": exp.updated_at,
                    "total_runs": stats.get("total", 0),
                    "queued": stats.get("pending", 0),
                    "in_progress": stats.get("in_progress", 0),
                    "completed": stats.get("completed", 0),
                    "failed": stats.get("failed", 0),
                    "started_at": stats.get("first_started_at"),
                    "completed_at": stats.get("last_completed_at"),
                }
            )

    return results


@app.get("/experiments/{experiment_id}")
async def get_experiment_detail(experiment_id: str) -> dict:
    with get_session() as db:
        stmt = sa.select(ExperimentRecord).where(
            ExperimentRecord.experiment_id == experiment_id
        )
        experiment = db.exec(stmt).scalars().first()
        if experiment is None:
            raise HTTPException(status_code=404, detail="Experiment not found")

        stats = _collect_queue_stats(db, [experiment_id]).get(experiment_id, {})
        queue_stmt = (
            sa.select(ExperimentQueueRecord)
            .where(ExperimentQueueRecord.experiment_id == experiment_id)
            .order_by(ExperimentQueueRecord.item_index, ExperimentQueueRecord.iteration)
        )
        queue_items = db.exec(queue_stmt).scalars().all()

        items_payload = []
        for item in queue_items:
            status_value = (
                item.status.value
                if isinstance(item.status, ExperimentQueueStatus)
                else str(item.status)
            )
            items_payload.append(
                {
                    "id": item.id,
                    "item_index": item.item_index,
                    "iteration": item.iteration,
                    "status": status_value,
                    "enqueued_at": item.enqueued_at,
                    "started_at": item.started_at,
                    "completed_at": item.completed_at,
                    "error": item.error,
                    "result": item.result,
                }
            )

        response = {
            "experiment": {
                "experiment_id": experiment.experiment_id,
                "description": experiment.description,
                "payload": experiment.payload,
                "created_at": experiment.created_at,
                "updated_at": experiment.updated_at,
            },
            "queue": {
                "total_runs": stats.get("total", 0),
                "queued": stats.get("pending", 0),
                "in_progress": stats.get("in_progress", 0),
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0),
                "started_at": stats.get("first_started_at"),
                "completed_at": stats.get("last_completed_at"),
                "items": items_payload,
            },
        }

    return response


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

    display_name = agent.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = agent.get("key")

    equipped = list(agent.get("equipped_tools", []))
    routes = list(agent.get("allowed_routes", []))
    metadata = agent.get("metadata") or {}
    allow = bool(agent.get("allow_respond", False)) and allow_respond
    raw_allow_task_group = agent.get("allow_task_group")
    if raw_allow_task_group is None:
        raw_allow_task_group = metadata.get("allow_task_group")
    allow_task_group = bool(raw_allow_task_group)
    raw_allow_task_respond = agent.get("allow_task_respond")
    if raw_allow_task_respond is None:
        raw_allow_task_respond = metadata.get("allow_task_respond")
    allow_task_respond = bool(raw_allow_task_respond)
    description = agent.get("description")
    prompt = agent.get("prompt")
    prompt = _combine_description_prompt(description, prompt)

    route_descriptions: Dict[str, str] = {}
    if routes:
        agents_entries = graph.get("agents", [])
        if isinstance(agents_entries, list):
            for entry in agents_entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("key")
                if key in routes:
                    desc = entry.get("description")
                    if isinstance(desc, str) and desc.strip():
                        route_descriptions[key] = desc.strip()

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

    respond_cfg = graph.get("respond") if isinstance(graph, dict) else None
    respond_payload_schema = None
    respond_payload_guidance = None
    respond_payload_example = None
    if isinstance(respond_cfg, dict):
        respond_payload_schema = respond_cfg.get("payload_schema")
        respond_payload_guidance = respond_cfg.get("payload_guidance")
        respond_payload_example = respond_cfg.get("payload_example")

    return RunConfig(
        current_agent=agent["key"],
        equipped_tools=equipped,
        tools_map=tools_map,
        allowed_routes=routes,
        route_descriptions=route_descriptions,
        allow_respond=allow,
        allow_task_group=allow_task_group,
        allow_task_respond=allow_task_respond,
        system_params=system_params or {},
        prompt=prompt,
        respond_payload_schema=respond_payload_schema,
        respond_payload_guidance=respond_payload_guidance,
        respond_payload_example=respond_payload_example,
        display_name=display_name,
    )


def _load_run_record(run_id: str):
    with get_session() as db:
        stmt = sa.select(RunRecord).where(RunRecord.run_id == run_id)
        run = db.exec(stmt).scalars().first()
        if run is None:
            return None
        db.expunge(run)
        return run


@lru_cache(maxsize=256)
def _lookup_network_name(network_id: int) -> Optional[str]:
    from arion_agents.config_models import Network  # local import avoids circular deps

    with get_session() as db:
        net = db.get(Network, network_id)
        if not net:
            return None
        name = net.name
        db.expunge(net)
        return name


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
    response_model = None
    response_totals = None
    response_run_duration = None
    if isinstance(record.response_payload, dict):
        response_system_params = record.response_payload.get("system_params")
        response_model = record.response_payload.get("model")
        response_totals = record.response_payload.get("llm_usage_totals")
        response_run_duration = record.response_payload.get("run_duration_ms")

    metadata = {
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "status": record.status,
        "network_id": record.network_id,
        "network_version_id": record.network_version_id,
        "graph_version_key": record.graph_version_key,
        "user_message": record.user_message,
        "system_params": response_system_params,
    }
    network_name: Optional[str] = None
    if record.network_id:
        try:
            network_name = _lookup_network_name(record.network_id)
        except Exception:
            network_name = None
    request_payload = record.request_payload if isinstance(record.request_payload, dict) else {}
    if not network_name:
        candidate = request_payload.get("network_name")
        if isinstance(candidate, str) and candidate.strip():
            network_name = candidate.strip()
    if not network_name:
        candidate = request_payload.get("network")
        if isinstance(candidate, str) and candidate.strip():
            network_name = candidate.strip()
    if network_name is not None:
        metadata["network_name"] = network_name
    if response_model is not None:
        metadata["model"] = response_model
    if response_totals is not None:
        metadata["llm_usage_totals"] = response_totals
    if response_run_duration is not None:
        metadata["run_duration_ms"] = response_run_duration
    final_payload = (
        response_payload.get("final") if isinstance(response_payload, dict) else None
    )
    if final_payload is not None:
        metadata["final"] = final_payload

    snapshot = {
        "traceId": record.run_id,
        "graphVersionId": record.graph_version_key,
        "steps": envelopes,
        "metadata": metadata,
    }
    if response_totals is not None:
        snapshot["llm_usage_totals"] = response_totals
    if response_run_duration is not None:
        snapshot["run_duration_ms"] = response_run_duration
    return snapshot


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
async def list_runs(limit: int = 20, experiment_id: str | None = None) -> list[dict]:
    if limit <= 0:
        limit = 20

    with get_session() as db:
        stmt = sa.select(RunRecord).order_by(RunRecord.created_at.desc())
        if experiment_id:
            stmt = stmt.where(RunRecord.experiment_id == experiment_id)
        stmt = stmt.limit(limit)
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
    from .api_config import (
        router as config_router,
        list_snapshots as _list_snapshots,
        SnapshotOut,
    )  # type: ignore

    app.include_router(config_router, prefix="/config", tags=["config"])
    app.add_api_route(
        "/snapshots",
        _list_snapshots,
        methods=["GET"],
        response_model=list[SnapshotOut],
        tags=["config"],
    )
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
        tool_defs = build_tool_definitions(cfg)
        route_defs = build_route_definitions(cfg)
        constraints = build_constraints(cfg, tool_defs, route_defs)
        context = build_context(payload.user_message, exec_log=[], full_tool_outputs=[])
        prompt = build_prompt(cfg, cfg.prompt, context, constraints)
        return {"agent_key": agent_key, "prompt": prompt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
