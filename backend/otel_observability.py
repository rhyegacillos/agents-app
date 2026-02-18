import logging
import os
from typing import Any, Dict, Optional

from opentelemetry import _logs, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_INITIALIZED = False
_LOGS_INITIALIZED = False


def _truthy(raw: str) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(raw: str, default: float) -> float:
    try:
        return float(raw.strip())
    except Exception:
        return default


def _parse_headers(raw: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in (raw or "").split(","):
        part = item.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = k.strip()
        value = v.strip()
        if key and value:
            out[key] = value
    return out


def _derive_logs_endpoint(trace_endpoint: str) -> str:
    endpoint = (trace_endpoint or "").strip()
    if not endpoint:
        return ""
    if endpoint.endswith("/v1/traces"):
        return f"{endpoint[:-len('/v1/traces')]}/v1/logs"
    if endpoint.endswith("/"):
        return f"{endpoint}v1/logs"
    return f"{endpoint}/v1/logs"


def _init_otel_logs(resource: Resource, default_headers: Dict[str, str], trace_endpoint: str) -> bool:
    global _LOGS_INITIALIZED
    if _LOGS_INITIALIZED:
        return True

    if not _truthy(os.getenv("OTEL_LOGS_ENABLED", "false")):
        logging.info("[otel] logs disabled (OTEL_LOGS_ENABLED=false)")
        return False

    logs_endpoint = (
        os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "").strip()
        or _derive_logs_endpoint(trace_endpoint)
    )
    if not logs_endpoint:
        logging.warning("[otel] logs disabled (OTEL_EXPORTER_OTLP_LOGS_ENDPOINT missing)")
        return False

    logs_headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_LOGS_HEADERS", "")) or default_headers

    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=logs_endpoint, headers=logs_headers)
    processor = BatchLogRecordProcessor(
        exporter,
        schedule_delay_millis=5000,
        max_queue_size=2048,
        max_export_batch_size=512,
    )
    provider.add_log_record_processor(processor)
    _logs.set_logger_provider(provider)

    min_level_name = (os.getenv("OTEL_LOGS_MIN_LEVEL", "INFO") or "INFO").upper()
    min_level = getattr(logging, min_level_name, logging.INFO)
    otel_handler = LoggingHandler(level=min_level, logger_provider=provider)
    root_logger = logging.getLogger()
    if root_logger.level > min_level:
        root_logger.setLevel(min_level)
    root_logger.addHandler(otel_handler)

    _LOGS_INITIALIZED = True
    logging.info(
        "[otel] logs initialized endpoint=%s min_level=%s",
        logs_endpoint,
        min_level_name,
    )
    return True


def init_otel() -> bool:
    global _INITIALIZED
    if _INITIALIZED:
        return True

    if not _truthy(os.getenv("OTEL_ENABLED", "false")):
        logging.info("[otel] disabled (OTEL_ENABLED=false)")
        return False

    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        logging.warning("[otel] disabled (OTEL_EXPORTER_OTLP_ENDPOINT missing)")
        return False

    service_name = (os.getenv("OTEL_SERVICE_NAME") or "").strip() or "digital-assistant-backend"
    environment = (
        (os.getenv("OTEL_ENVIRONMENT") or "").strip()
        or (os.getenv("ENVIRONMENT") or "").strip()
        or "dev"
    )
    sample_rate = max(0.0, min(1.0, _parse_float(os.getenv("OTEL_TRACES_SAMPLE_RATE", "0.1"), 0.1)))

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": environment,
            "deployment.environment.name": environment,
            "environment": environment,
        }
    )

    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(sample_rate)),
    )
    headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    processor = BatchSpanProcessor(
        exporter,
        schedule_delay_millis=5000,
        max_queue_size=2048,
        max_export_batch_size=512,
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _init_otel_logs(resource, headers, endpoint)
    _INITIALIZED = True
    logging.info(
        "[otel] initialized service=%s env=%s endpoint=%s sample=%.3f",
        service_name,
        environment,
        endpoint,
        sample_rate,
    )
    return True


def flush_otel(timeout_millis: int = 3000) -> None:
    if not _INITIALIZED:
        return
    try:
        trace_provider = trace.get_tracer_provider()
        if hasattr(trace_provider, "force_flush"):
            trace_provider.force_flush(timeout_millis=timeout_millis)
    except Exception:
        logging.exception("[otel] failed to flush traces")
    try:
        logger_provider = _logs.get_logger_provider()
        if hasattr(logger_provider, "force_flush"):
            logger_provider.force_flush(timeout_millis=timeout_millis)
    except Exception:
        logging.exception("[otel] failed to flush logs")


def instrument_fastapi_app(app: Any) -> None:
    if not _INITIALIZED:
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        logging.exception("[otel] failed to instrument FastAPI app")


def get_tracer(name: str):
    return trace.get_tracer(name)


def set_current_span_attributes(attributes: Optional[Dict[str, Any]]) -> None:
    if not _INITIALIZED or not attributes:
        return
    span = trace.get_current_span()
    if span is None:
        return
    for key, value in attributes.items():
        if value is None:
            continue
        span.set_attribute(str(key), value)


def record_current_span_exception(exc: Exception) -> None:
    if not _INITIALIZED:
        return
    span = trace.get_current_span()
    if span is None:
        return
    span.record_exception(exc)
