import json
import unittest
from unittest.mock import Mock, patch

from api.schemas import ChatRequest
import worker_handler
from mcp_tools import mcp_servers


class TracePropagationTests(unittest.TestCase):
    def test_build_mcp_server_specs_includes_trace_context_env(self) -> None:
        with (
            patch.object(mcp_servers, "resolve_mcp_python", Mock(return_value="/usr/bin/python3")),
            patch.object(mcp_servers, "build_trace_context_env", Mock(return_value={"TRACEPARENT": "00-abc"})),
        ):
            specs = mcp_servers.build_mcp_server_specs(enable_search=False, job_id="job-1")

        self.assertGreaterEqual(len(specs), 2)
        for spec in specs:
            self.assertEqual(spec["params"]["env"]["TRACEPARENT"], "00-abc")

    def test_worker_handler_extracts_parent_trace_context_from_event(self) -> None:
        parent_context = object()
        span_cm = Mock()
        span = Mock()
        span_cm.__enter__ = Mock(return_value=span)
        span_cm.__exit__ = Mock(return_value=False)
        tracer = Mock()
        tracer.start_as_current_span.return_value = span_cm

        with (
            patch.object(worker_handler, "extract_trace_context", Mock(return_value=parent_context)),
            patch.object(worker_handler, "get_otel_tracer", Mock(return_value=tracer)),
            patch.object(worker_handler, "_upstash_get", Mock(return_value={"status": "canceled"})),
            patch.object(worker_handler, "set_trace_id", Mock(return_value=(None, object()))),
            patch.object(worker_handler, "reset_trace_id", Mock()),
            patch.object(worker_handler, "flush_otel", Mock()),
            patch.object(worker_handler, "set_current_span_attributes", Mock()),
        ):
            result = worker_handler.handler(
                {
                    "job_id": "job-1",
                    "trace_id": "trace-1",
                    "trace_headers": {"traceparent": "00-abc"},
                    "user_id": "user_12345678",
                    "session_id": "sess-1",
                    "message": "hello",
                },
                context=Mock(),
            )

        self.assertEqual(result, {"status": "canceled", "job_id": "job-1"})
        tracer.start_as_current_span.assert_called_once()
        self.assertIs(tracer.start_as_current_span.call_args.kwargs["context"], parent_context)

class AsyncTracePropagationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_chat_payload_includes_trace_headers(self) -> None:
        import server

        lambda_client = Mock()
        with (
            patch.object(server, "ASYNC_CHAT_ENABLED", True),
            patch.object(server, "_upstash_enabled", Mock(return_value=True)),
            patch.object(server, "ASYNC_WORKER_FUNCTION_NAME", "worker-fn"),
            patch.object(server, "inject_current_trace_headers", Mock(return_value={"traceparent": "00-abc"})),
            patch.object(server, "_upstash_set", Mock()),
            patch("server.boto3.client", Mock(return_value=lambda_client)),
        ):
            response = await server.chat(
                ChatRequest(
                    user_id="user_12345678",
                    session_id="sess-1",
                    message="hello",
                    file_id=None,
                )
            )

        self.assertEqual(response.status_code, 202)
        lambda_client.invoke.assert_called_once()
        payload = json.loads(lambda_client.invoke.call_args.kwargs["Payload"].decode("utf-8"))
        self.assertEqual(payload["trace_headers"], {"traceparent": "00-abc"})


if __name__ == "__main__":
    unittest.main()
