import os
from mangum import Mangum
from opentelemetry.trace import SpanKind
from server import app
from otel_observability import flush_otel, get_tracer

# v3: no Kaleido/Chrome. Keep Lambda writable dirs safe defaults.
os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

# (Optional) If Graphviz needs a writable temp dir explicitly:
os.environ.setdefault("TMPDIR", "/tmp")

_asgi_handler = Mangum(app)


def handler(event, context):
    try:
        tracer = get_tracer("digital_assistant.api")
        with tracer.start_as_current_span("lambda.api", kind=SpanKind.SERVER) as span:
            if span is not None:
                request_id = getattr(context, "aws_request_id", None)
                function_name = getattr(context, "function_name", None)
                path = (event or {}).get("path") or (event or {}).get("rawPath")
                if request_id:
                    span.set_attribute("aws.request_id", request_id)
                if function_name:
                    span.set_attribute("faas.name", function_name)
                if path:
                    span.set_attribute("http.target", path)
            return _asgi_handler(event, context)
    finally:
        flush_otel()
