import os
from fastapi import FastAPI
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
            result = execute_instruction(instr)
            return {"trace_id": trace_id, "result": result.model_dump()}
    # Fallback when OTel is not available/disabled
    instr = Instruction.model_validate(payload.instruction)
    result = execute_instruction(instr)
    return {"trace_id": None, "result": result.model_dump()}

# Config router
try:
    from .api_config import router as config_router  # type: ignore

    app.include_router(config_router, prefix="/config", tags=["config"])
except Exception:
    # Keep API importable even if config store is misconfigured
    pass
