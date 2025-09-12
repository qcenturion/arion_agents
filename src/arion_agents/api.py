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
