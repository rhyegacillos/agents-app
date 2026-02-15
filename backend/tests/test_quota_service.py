import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import os
from botocore.exceptions import ClientError

from services.quota import (
    _s3_write_usage_atomic,
    count_quota_actions_from_truth_context,
    consume_daily_quota,
    get_daily_quota,
)


class QuotaServiceTests(unittest.TestCase):
    def test_count_quota_actions_from_truth_context(self) -> None:
        context = {
            "artifacts": [
                {
                    "kind": "pdf",
                    "source_tool": "generate_pdf_from_text",
                    "download_url": "/downloads/a.pdf",
                    "status": "ok",
                },
                {
                    "kind": "pdf",
                    "source_tool": "download_pdf",
                    "download_url": "/downloads/b.pdf",
                    "status": "ok",
                },
                {
                    "kind": "pdf",
                    "source_tool": "generate_pdf_from_text",
                    "download_url": "/downloads/a.pdf",
                    "status": "ok",
                },
            ],
            "outcomes": [
                {"tool": "send_resend_email", "status": "ok", "email_id": "em_1"},
                {"tool": "send_resend_email", "status": "ok", "email_id": "em_1"},
                {"tool": "send_resend_email", "status": "error", "email_id": "em_2"},
            ],
        }
        counts = count_quota_actions_from_truth_context(context)
        self.assertEqual(counts["pdf"], 1)
        self.assertEqual(counts["email"], 1)

    def test_get_daily_quota_disabled_when_upstash_unavailable(self) -> None:
        with patch("services.quota._upstash_enabled", return_value=False), patch(
            "services.quota._s3_quota_enabled", return_value=False
        ), patch.dict(os.environ, {"QUOTA_LOCAL_FALLBACK": "false"}, clear=False):
            snapshot = get_daily_quota("user_12345678")
        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["usage"]["tokens"], 0)

    def test_get_daily_quota_falls_back_to_hash(self) -> None:
        with patch("services.quota._upstash_enabled", return_value=True), patch(
            "services.quota._upstash_get", side_effect=RuntimeError("wrongtype")
        ), patch(
            "services.quota._upstash_hgetall",
            return_value={"tokens": "11", "pdf": "2", "email": "1"},
        ):
            snapshot = get_daily_quota("user_12345678")
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(snapshot["usage"]["tokens"], 11)

    def test_consume_daily_quota_caps_and_reports_exceeded(self) -> None:
        now = datetime(2026, 2, 15, 3, 0, tzinfo=timezone.utc)
        store = {
            "quota:user_12345678:20260215": {
                "usage": {"tokens": 9, "pdf": 1, "email": 0},
            }
        }

        def fake_get(key: str):
            return dict(store.get(key, {}))

        def fake_set(key: str, value, ttl):
            store[key] = dict(value)

        with patch("services.quota._utc_now", return_value=now), patch(
            "services.quota._upstash_enabled", return_value=True
        ), patch("services.quota._upstash_get", side_effect=fake_get), patch(
            "services.quota._upstash_set", side_effect=fake_set
        ), patch(
            "services.quota._limits",
            return_value={"tokens": 10, "pdf": 2, "email": 1},
        ):
            result = consume_daily_quota(
                "user_12345678",
                {"tokens": 5, "pdf": 2, "email": 2},
            )

        self.assertEqual(set(result["exceeded"]), {"tokens", "pdf", "email"})
        self.assertEqual(result["applied"], {"tokens": 1, "pdf": 1, "email": 1})
        self.assertEqual(result["snapshot"]["usage"], {"tokens": 10, "pdf": 2, "email": 1})

    def test_s3_atomic_update_retries_on_precondition_failed(self) -> None:
        now = datetime(2026, 2, 15, 3, 0, tzinfo=timezone.utc)
        read_states = [
            ({"usage": {"tokens": 10, "pdf": 1, "email": 0}}, '"etag-1"'),
            ({"usage": {"tokens": 12, "pdf": 1, "email": 0}}, '"etag-2"'),
        ]

        precondition_error = ClientError(
            error_response={"Error": {"Code": "PreconditionFailed", "Message": "etag mismatch"}},
            operation_name="PutObject",
        )

        with patch("services.quota._s3_read_payload_with_etag", side_effect=read_states), patch(
            "services.quota.s3_client"
        ) as mock_s3:
            mock_s3.put_object.side_effect = [precondition_error, {}]
            usage, applied, exceeded = _s3_write_usage_atomic(
                user_id="user_12345678",
                now=now,
                increments={"tokens": 5, "pdf": 1, "email": 0},
                limits={"tokens": 20, "pdf": 3, "email": 5},
            )

        # Second read state should be used after retry.
        self.assertEqual(usage["tokens"], 17)
        self.assertEqual(applied["tokens"], 5)
        self.assertEqual(applied["pdf"], 1)
        self.assertEqual(exceeded, [])


if __name__ == "__main__":
    unittest.main()
