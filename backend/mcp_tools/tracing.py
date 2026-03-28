import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from otel_observability import (
    extract_trace_context,
    get_tracer as get_otel_tracer,
    inject_current_trace_headers,
    record_current_span_exception,
)


_TRACE_HEADER_ENV_MAP = {
    "traceparent": "TRACEPARENT",
    "tracestate": "TRACESTATE",
    "baggage": "BAGGAGE",
}


def build_trace_context_env() -> Dict[str, str]:
    headers = inject_current_trace_headers()
    return {
        env_key: headers[header_key]
        for header_key, env_key in _TRACE_HEADER_ENV_MAP.items()
        if headers.get(header_key)
    }


def extract_trace_context_from_env():
    carrier = {
        header_key: os.getenv(env_key, "").strip()
        for header_key, env_key in _TRACE_HEADER_ENV_MAP.items()
        if os.getenv(env_key, "").strip()
    }
    return extract_trace_context(carrier)


def _tool_status_from_result(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("status"):
            return str(result.get("status"))
        if result.get("error"):
            return "error"
    return "ok"


@contextmanager
def start_mcp_tool_span(tool_name: str, *, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
    tracer = get_otel_tracer("digital_assistant.mcp")
    parent_context = extract_trace_context_from_env()
    with tracer.start_as_current_span(f"mcp.tool.{tool_name}", context=parent_context) as span:
        if span is not None:
            span.set_attribute("tool.name", tool_name)
            service_name = os.getenv("OTEL_SERVICE_NAME", "").strip()
            if service_name:
                span.set_attribute("service.name", service_name)
            for key, value in (attributes or {}).items():
                if value is None:
                    continue
                span.set_attribute(str(key), value)
        try:
            yield span
        except Exception as exc:
            if span is not None:
                span.set_attribute("tool.status", "error")
            record_current_span_exception(exc)
            raise


def annotate_tool_result(span: Any, result: Any) -> None:
    if span is None:
        return
    span.set_attribute("tool.status", _tool_status_from_result(result))
    if isinstance(result, dict):
        if result.get("error"):
            span.set_attribute("tool.error", str(result.get("error")))
        if result.get("message"):
            span.set_attribute("tool.message", str(result.get("message")))
