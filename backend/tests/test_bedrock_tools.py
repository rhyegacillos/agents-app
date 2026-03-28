import unittest

from services.bedrock_tools import run_bedrock_with_tools


class _FakeSession:
    async def call_tool(self, tool_name, arguments=None):
        return {"status": "ok", "email_id": "em_123", "message": "Email sent successfully. ID: em_123"}


class _FakeStack:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncExitStack:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def enter_async_context(self, ctx):
        return await ctx.__aenter__()


class _FakeBedrockClient:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "usage": {"totalTokens": 5},
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "send_resend_email",
                                    "toolUseId": "tool-1",
                                    "input": {"to": "a@example.com", "subject": "s", "body": "b"},
                                }
                            }
                        ]
                    }
                },
            }
        return {
            "usage": {"totalTokens": 3},
            "output": {"message": {"content": [{"text": "done"}]}},
        }


class _FakeBedrockClientTwoStep:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "usage": {"totalTokens": 5},
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "generate_pdf_from_text",
                                    "toolUseId": "tool-1",
                                    "input": {"content": "# Report"},
                                }
                            }
                        ]
                    }
                },
            }
        if len(self.calls) == 2:
            return {
                "usage": {"totalTokens": 4},
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "send_resend_email",
                                    "toolUseId": "tool-2",
                                    "input": {"to": "a@example.com", "subject": "s", "body": "b"},
                                }
                            }
                        ]
                    }
                },
            }
        return {
            "usage": {"totalTokens": 3},
            "output": {"message": {"content": [{"text": "done"}]}},
        }


class BedrockToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_tool_choice_is_only_for_first_round(self) -> None:
        client = _FakeBedrockClient()

        from unittest.mock import patch

        with (
            patch("services.bedrock_tools.AsyncExitStack", _FakeAsyncExitStack),
            patch(
                "services.bedrock_tools._open_mcp_sessions",
                return_value=(
                    [{"toolSpec": {"name": "send_resend_email", "description": "", "inputSchema": {"json": {}}}}],
                    {"send_resend_email": _FakeSession()},
                ),
            ),
        ):
            output, tokens, tool_events = await run_bedrock_with_tools(
                bedrock_client=client,
                model_id="model",
                system_text="system",
                user_text="user",
                mcp_specs=[],
                required_tool_names=["send_resend_email"],
                max_tool_rounds=3,
            )

        self.assertEqual(output, "done")
        self.assertEqual(tokens, 8)
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(
            client.calls[0]["toolConfig"].get("toolChoice"),
            {"tool": {"name": "send_resend_email"}},
        )
        self.assertNotIn("toolChoice", client.calls[1]["toolConfig"])

    async def test_required_tool_sequence_forces_next_missing_tool(self) -> None:
        client = _FakeBedrockClientTwoStep()

        from unittest.mock import patch

        tool_specs = [
            {"toolSpec": {"name": "generate_pdf_from_text", "description": "", "inputSchema": {"json": {}}}},
            {"toolSpec": {"name": "send_resend_email", "description": "", "inputSchema": {"json": {}}}},
        ]
        tool_sessions = {
            "generate_pdf_from_text": _FakeSession(),
            "send_resend_email": _FakeSession(),
        }

        with (
            patch("services.bedrock_tools.AsyncExitStack", _FakeAsyncExitStack),
            patch("services.bedrock_tools._open_mcp_sessions", return_value=(tool_specs, tool_sessions)),
        ):
            output, tokens, tool_events = await run_bedrock_with_tools(
                bedrock_client=client,
                model_id="model",
                system_text="system",
                user_text="user",
                mcp_specs=[],
                required_tool_names=["generate_pdf_from_text", "send_resend_email"],
                max_tool_rounds=4,
            )

        self.assertEqual(output, "done")
        self.assertEqual(tokens, 12)
        self.assertEqual(
            [event["tool_name"] for event in tool_events],
            ["generate_pdf_from_text", "send_resend_email"],
        )
        self.assertEqual(
            client.calls[0]["toolConfig"].get("toolChoice"),
            {"tool": {"name": "generate_pdf_from_text"}},
        )
        self.assertEqual(
            client.calls[1]["toolConfig"].get("toolChoice"),
            {"tool": {"name": "send_resend_email"}},
        )
        self.assertNotIn("toolChoice", client.calls[2]["toolConfig"])


if __name__ == "__main__":
    unittest.main()
