import unittest
from unittest.mock import AsyncMock, Mock, patch

import server
from services.risk_router import required_tool_sequence, requires_email_tool_action
from services.chat_runtime import HighRiskChatResult


class ProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_requires_email_tool_action_detects_email_send_turn(self) -> None:
        self.assertTrue(requires_email_tool_action("send it to rhye@example.com"))
        self.assertTrue(
            requires_email_tool_action(
                "try again",
                conversation=[{"role": "assistant", "content": "I can email the PDF to you."}],
            )
        )

    def test_required_tool_sequence_detects_pdf_then_email_contract(self) -> None:
        self.assertEqual(
            required_tool_sequence("send it to rhye@example.com in pdf"),
            ["generate_pdf_from_text", "send_resend_email"],
        )

    async def test_high_risk_uses_bedrock_when_provider_is_bedrock(self) -> None:
        with (
            patch.object(server, "AI_PROVIDER", "bedrock"),
            patch.object(server, "call_bedrock", AsyncMock(return_value=("bedrock", 7))) as bedrock_call,
            patch.object(server, "call_grok_with_mcp", AsyncMock()) as grok_call,
        ):
            out = await server._generate_response_for_risk(
                user_id="user_12345678",
                conversation=[],
                agent_message="find latest papers",
                session_id="sess-1",
                tier="high",
                require_sources=True,
            )

        self.assertEqual(out, ("bedrock", 7))
        bedrock_call.assert_awaited_once()
        grok_call.assert_not_awaited()

    async def test_high_risk_uses_grok_when_provider_is_grok(self) -> None:
        with (
            patch.object(server, "AI_PROVIDER", "grok"),
            patch.object(server, "call_bedrock", AsyncMock()) as bedrock_call,
            patch.object(server, "call_grok_with_mcp", AsyncMock(return_value=("grok", 5))) as grok_call,
        ):
            out = await server._generate_response_for_risk(
                user_id="user_12345678",
                conversation=[],
                agent_message="find latest papers",
                session_id="sess-1",
                tier="high",
                require_sources=True,
            )

        self.assertEqual(out, ("grok", 5))
        grok_call.assert_awaited_once()
        bedrock_call.assert_not_awaited()

    async def test_low_risk_bedrock_path_avoids_tools_and_applies_guard(self) -> None:
        with (
            patch.object(server, "run_bedrock_prose", AsyncMock(return_value=("raw output", 11))) as prose_call,
            patch.object(
                server,
                "apply_low_risk_prose_guard",
                Mock(return_value=("guarded output", ["raw_url_present"])),
            ) as prose_guard,
            patch.object(server, "build_mcp_server_specs", Mock()) as build_mcp_specs,
        ):
            out = await server.call_bedrock_prose_guarded(
                "user_12345678",
                [],
                "hello there",
            )

        self.assertEqual(out, ("guarded output", 11))
        prose_call.assert_awaited_once()
        prose_guard.assert_called_once_with("raw output")
        build_mcp_specs.assert_not_called()

    async def test_missing_grok_key_does_not_break_bedrock_low_risk_path(self) -> None:
        with (
            patch.object(server, "GROK_API_KEY", ""),
            patch.object(server, "run_bedrock_prose", AsyncMock(return_value=("bedrock reply", 3))),
            patch.object(server, "apply_low_risk_prose_guard", Mock(return_value=("bedrock reply", []))),
        ):
            out = await server.call_bedrock_prose_guarded(
                "user_12345678",
                [],
                "hello there",
            )

        self.assertEqual(out, ("bedrock reply", 3))

    async def test_bedrock_high_risk_path_passes_bedrock_memory_validator(self) -> None:
        with (
            patch.object(server, "build_full_instructions", Mock(return_value="system prompt")),
            patch.object(server, "build_conversation_input", Mock(return_value="user prompt")),
            patch.object(server, "build_mcp_server_specs", Mock(return_value=[])),
            patch.object(
                server,
                "run_bedrock_chat",
                AsyncMock(return_value=HighRiskChatResult(output="ready", tool_events=[], llm_tokens=3)),
            ),
            patch.object(server, "finalize_high_risk_response", AsyncMock(return_value=("done", 3))) as finalize,
        ):
            out = await server.call_bedrock(
                "user_12345678",
                [],
                "search the web",
                session_id="sess-1",
                require_sources=True,
            )

        self.assertEqual(out, ("done", 3))
        finalize.assert_awaited_once()
        self.assertIs(
            finalize.await_args.kwargs["memory_validator"],
            server.validate_memory_compliance_bedrock,
        )

    async def test_bedrock_high_risk_path_propagates_required_tool_names(self) -> None:
        with (
            patch.object(server, "build_full_instructions", Mock(return_value="system prompt")),
            patch.object(server, "build_conversation_input", Mock(return_value="user prompt")),
            patch.object(server, "build_mcp_server_specs", Mock(return_value=[])),
            patch.object(
                server,
                "run_bedrock_chat",
                AsyncMock(return_value=HighRiskChatResult(output="ready", tool_events=[], llm_tokens=3)),
            ),
            patch.object(server, "finalize_high_risk_response", AsyncMock(return_value=("done", 3))) as finalize,
        ):
            await server.call_bedrock(
                "user_12345678",
                [],
                "send it to rhye@example.com",
                session_id="sess-1",
                require_sources=False,
                required_tool_names=["generate_pdf_from_text", "send_resend_email"],
            )

        self.assertEqual(
            finalize.await_args.kwargs["required_tool_names"],
            ["generate_pdf_from_text", "send_resend_email"],
        )


if __name__ == "__main__":
    unittest.main()
