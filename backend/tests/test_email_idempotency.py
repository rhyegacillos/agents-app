import unittest
from unittest.mock import Mock, patch

from mcp_tools.core_mcp_server import send_resend_email


class EmailIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_resend_email_dedupes_identical_calls(self) -> None:
        fake_response = {"id": "em_123"}

        with (
            patch("mcp_tools.core_mcp_server.RESEND_API_KEY", "key"),
            patch("mcp_tools.core_mcp_server.resend.Emails.send", Mock(return_value=fake_response)) as send_mock,
            patch("mcp_tools.core_mcp_server.read_result", Mock(side_effect=[None, {
                "status": "ok",
                "email_id": "em_123",
                "message": "Email sent successfully. ID: em_123",
                "stored_at": "2026-03-19T00:00:00+00:00",
            }])),
            patch("mcp_tools.core_mcp_server.write_result", Mock(side_effect=lambda key, result: dict(result))) as write_mock,
        ):
            first = await send_resend_email("a@example.com", "Subject", "Body")
            second = await send_resend_email("a@example.com", "Subject", "Body")

        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["email_id"], "em_123")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["email_id"], "em_123")
        self.assertTrue(second["deduped"])
        send_mock.assert_called_once()
        write_mock.assert_called_once()

    async def test_send_resend_email_dedupes_same_recipient_and_subject_even_if_body_changes(self) -> None:
        fake_response = {"id": "em_123"}

        with (
            patch("mcp_tools.core_mcp_server.RESEND_API_KEY", "key"),
            patch("mcp_tools.core_mcp_server.resend.Emails.send", Mock(return_value=fake_response)) as send_mock,
            patch(
                "mcp_tools.core_mcp_server.read_result",
                Mock(
                    side_effect=[
                        None,
                        {
                            "status": "ok",
                            "email_id": "em_123",
                            "message": "Email sent successfully. ID: em_123",
                            "stored_at": "2026-03-19T00:00:00+00:00",
                        },
                    ]
                ),
            ),
            patch("mcp_tools.core_mcp_server.write_result", Mock(side_effect=lambda key, result: dict(result))) as write_mock,
        ):
            first = await send_resend_email("a@example.com", "Subject", "Body 1")
            second = await send_resend_email("a@example.com", "Subject", "Body 2")

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertTrue(second["deduped"])
        send_mock.assert_called_once()
        write_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
