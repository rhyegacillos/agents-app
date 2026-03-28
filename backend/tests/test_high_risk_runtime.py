import unittest
from unittest.mock import AsyncMock, Mock, patch

from services.chat_runtime.bedrock_runner import run_bedrock_chat
from services.chat_runtime.high_risk_flow import finalize_high_risk_response
from services.chat_runtime.result_types import HighRiskChatResult


class BedrockRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_bedrock_chat_returns_provider_neutral_result(self) -> None:
        tool_events = [{"tool_name": "brave_web_search", "output": {"results": []}}]
        with patch(
            "services.chat_runtime.bedrock_runner.run_bedrock_with_tools",
            AsyncMock(return_value=("answer", 13, tool_events)),
        ) as run_with_tools:
            result = await run_bedrock_chat(
                bedrock_client=object(),
                bedrock_model_id="apac.amazon.nova-lite-v1:0",
                default_aws_region="ap-southeast-1",
                system_text="system",
                user_text="user",
                mcp_specs=[],
            )

        self.assertEqual(result.output, "answer")
        self.assertEqual(result.llm_tokens, 13)
        self.assertEqual(result.tool_events, tool_events)
        run_with_tools.assert_awaited_once()

    async def test_run_bedrock_chat_passes_required_tool_names(self) -> None:
        with patch(
            "services.chat_runtime.bedrock_runner.run_bedrock_with_tools",
            AsyncMock(return_value=("answer", 13, [])),
        ) as run_with_tools:
            await run_bedrock_chat(
                bedrock_client=object(),
                bedrock_model_id="apac.amazon.nova-lite-v1:0",
                default_aws_region="ap-southeast-1",
                system_text="system",
                user_text="user",
                mcp_specs=[],
                required_tool_names=["generate_pdf_from_text", "send_resend_email"],
            )

        self.assertEqual(
            run_with_tools.await_args.kwargs["required_tool_names"],
            ["generate_pdf_from_text", "send_resend_email"],
        )


class HighRiskFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_high_risk_response_uses_injected_validator(self) -> None:
        validator = Mock(
            return_value={
                "compliant": True,
                "reason": "",
                "fix_instructions": "",
            }
        )
        initial = HighRiskChatResult(output="answer", tool_events=[], llm_tokens=2)

        with (
            patch("services.chat_runtime.high_risk_flow.load_approved_memory", Mock(return_value=[{"text": "A"}])),
            patch("services.chat_runtime.high_risk_flow.render_high_risk_output", Mock(return_value="answer")),
            patch(
                "services.chat_runtime.high_risk_flow.apply_truth_gate",
                Mock(return_value={"status": "pass", "output": "answer"}),
            ),
            patch("services.chat_runtime.high_risk_flow.persist_truth_context", Mock()),
            patch("services.chat_runtime.high_risk_flow.persist_truth_gate_verdict", Mock()),
        ):
            out = await finalize_high_risk_response(
                user_id="user_12345678",
                user_message="hello",
                session_id="sess-1",
                require_sources=False,
                initial_result=initial,
                rerun_with_fix=AsyncMock(),
                memory_validator=validator,
            )

        self.assertEqual(out, ("answer", 2))
        validator.assert_called_once_with([{"text": "A"}], "hello", "answer")

    async def test_finalize_high_risk_response_accumulates_rerun_tokens_and_events(self) -> None:
        initial = HighRiskChatResult(
            output="first draft",
            tool_events=[{"tool_name": "brave_web_search", "output": {"results": []}}],
            llm_tokens=2,
        )
        rerun_result = HighRiskChatResult(
            output="fixed draft",
            tool_events=[{"tool_name": "generate_pdf_from_text", "output": {"status": "ok", "filename": "x.pdf"}}],
            llm_tokens=5,
        )
        rerun_with_fix = AsyncMock(return_value=rerun_result)

        with (
            patch("services.chat_runtime.high_risk_flow.load_approved_memory", Mock(return_value=[])),
            patch(
                "services.chat_runtime.high_risk_flow.render_high_risk_output",
                Mock(side_effect=["rendered-1", "rendered-2"]),
            ),
            patch(
                "services.chat_runtime.high_risk_flow.apply_truth_gate",
                Mock(
                    side_effect=[
                        {"status": "block", "issues": [{"code": "SOURCE_LINK_MISSING"}]},
                        {"status": "pass", "output": "final output"},
                    ]
                ),
            ),
            patch("services.chat_runtime.high_risk_flow.persist_truth_context", Mock()),
            patch("services.chat_runtime.high_risk_flow.persist_truth_gate_verdict", Mock()),
            patch("services.chat_runtime.high_risk_flow.should_attempt_auto_fix", Mock(return_value=True)),
            patch(
                "services.chat_runtime.high_risk_flow.build_auto_fix_instructions",
                Mock(return_value="retry with canonical sources"),
            ),
        ):
            out = await finalize_high_risk_response(
                user_id="user_12345678",
                user_message="search the web",
                session_id="sess-1",
                require_sources=True,
                initial_result=initial,
                rerun_with_fix=rerun_with_fix,
                memory_validator=Mock(return_value={"compliant": True}),
            )

        self.assertEqual(out, ("final output", 7))
        rerun_with_fix.assert_awaited_once_with("retry with canonical sources")

    async def test_finalize_high_risk_response_logs_email_tool_failures(self) -> None:
        initial = HighRiskChatResult(
            output="send failed",
            tool_events=[
                {
                    "tool_name": "send_resend_email",
                    "output": "Email failed: ApiError: domain not verified",
                }
            ],
            llm_tokens=2,
        )

        with (
            patch("services.chat_runtime.high_risk_flow.load_approved_memory", Mock(return_value=[])),
            patch(
                "services.chat_runtime.high_risk_flow.render_high_risk_output",
                Mock(return_value="Email send failed: ApiError: domain not verified"),
            ),
            patch(
                "services.chat_runtime.high_risk_flow.apply_truth_gate",
                Mock(return_value={"status": "pass", "output": "Email send failed: ApiError: domain not verified"}),
            ),
            patch("services.chat_runtime.high_risk_flow.persist_truth_context", Mock()),
            patch("services.chat_runtime.high_risk_flow.persist_truth_gate_verdict", Mock()),
            patch("services.chat_runtime.high_risk_flow.log_event", Mock()) as log_event_mock,
        ):
            out = await finalize_high_risk_response(
                user_id="user_12345678",
                user_message="please resend the pdf to my email",
                session_id="sess-1",
                require_sources=False,
                initial_result=initial,
                rerun_with_fix=AsyncMock(),
                memory_validator=Mock(return_value={"compliant": True}),
            )

        self.assertEqual(out, ("Email send failed: ApiError: domain not verified", 2))
        self.assertTrue(
            any(
                call.args and call.args[0] == "execute.tool_failure"
                for call in log_event_mock.call_args_list
            )
        )

    async def test_finalize_high_risk_response_logs_missing_required_tools(self) -> None:
        initial = HighRiskChatResult(output="no tool used", tool_events=[], llm_tokens=2)

        with (
            patch("services.chat_runtime.high_risk_flow.load_approved_memory", Mock(return_value=[])),
            patch("services.chat_runtime.high_risk_flow.log_event", Mock()) as log_event_mock,
        ):
            out = await finalize_high_risk_response(
                user_id="user_12345678",
                user_message="send this pdf to my email",
                session_id="sess-1",
                require_sources=False,
                initial_result=initial,
                rerun_with_fix=AsyncMock(),
                memory_validator=Mock(return_value={"compliant": True}),
                required_tool_names=["generate_pdf_from_text", "send_resend_email"],
            )

        self.assertEqual(
            out,
            (
                "I couldn't complete that action because one or more required execution tools did not run. "
                "Please retry the action.",
                2,
            ),
        )
        self.assertTrue(
            any(
                call.args and call.args[0] == "execute.required_tools_missing"
                for call in log_event_mock.call_args_list
            )
        )

    async def test_finalize_high_risk_response_rejects_out_of_order_required_tools(self) -> None:
        initial = HighRiskChatResult(
            output="wrong order",
            tool_events=[
                {"tool_name": "send_resend_email", "output": {"status": "ok", "email_id": "em_1"}},
                {"tool_name": "generate_pdf_from_text", "output": {"status": "ok", "filename": "x.pdf"}},
            ],
            llm_tokens=2,
        )

        with (
            patch("services.chat_runtime.high_risk_flow.load_approved_memory", Mock(return_value=[])),
            patch("services.chat_runtime.high_risk_flow.log_event", Mock()) as log_event_mock,
        ):
            out = await finalize_high_risk_response(
                user_id="user_12345678",
                user_message="send this pdf to my email",
                session_id="sess-1",
                require_sources=False,
                initial_result=initial,
                rerun_with_fix=AsyncMock(),
                memory_validator=Mock(return_value={"compliant": True}),
                required_tool_names=["generate_pdf_from_text", "send_resend_email"],
            )

        self.assertEqual(
            out,
            (
                "I couldn't complete that action because the required tool execution order was not satisfied. "
                "Please retry the action.",
                2,
            ),
        )
        self.assertTrue(
            any(
                call.args and call.args[0] == "execute.required_tools_out_of_order"
                for call in log_event_mock.call_args_list
            )
        )


if __name__ == "__main__":
    unittest.main()
