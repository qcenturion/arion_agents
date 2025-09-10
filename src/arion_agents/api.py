import os
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def _format_trace_id(trace_id: int) -> str:
    return f"{trace_id:032x}"


def setup_tracing() -> None:
    service_name = os.getenv("OTEL_SERVICE_NAME", "arion_agents_api")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Use insecure=True for local dev endpoints over http
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


setup_tracing()
app = FastAPI(title="arion_agents API")
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/invoke")
async def invoke(payload: dict) -> dict:
    tracer = trace.get_tracer("arion_agents.orchestrator")
    with tracer.start_as_current_span("invoke") as span:
        span.set_attribute("request.payload_size", len(str(payload)))
        # Placeholder orchestrator behavior; will be implemented per workstream
        trace_id = _format_trace_id(span.get_span_context().trace_id)
        return {"trace_id": trace_id, "status": "not_implemented"}

