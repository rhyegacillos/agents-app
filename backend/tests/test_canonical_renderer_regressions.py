import unittest

from services.canonical_renderer import (
    EMAIL_DELIVERY_UNVERIFIED_MESSAGE,
    EMAIL_DELIVERY_UNVERIFIED_WITH_PDF_MESSAGE,
    NO_CANONICAL_SOURCES_MESSAGE,
    render_high_risk_output,
)


class CanonicalRendererRegressionTests(unittest.TestCase):
    def test_pdf_response_uses_canonical_link(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/report.pdf", "page_count": 4}],
            "outcomes": [],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please generate a pdf",
            llm_output="random draft text",
            context=context,
            require_sources=False,
        )
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)
        self.assertIn("Verified page count: 4.", rendered)

    def test_pdf_response_prefers_downloads_path_from_filename(self) -> None:
        context = {
            "artifacts": [
                {
                    "kind": "pdf",
                    "download_url": "http://localhost:8000/downloads/report.pdf?sig=abc",
                    "filename": "report.pdf",
                    "page_count": 4,
                }
            ],
            "outcomes": [],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please generate a pdf",
            llm_output="random draft text",
            context=context,
            require_sources=False,
        )
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)
        self.assertNotIn("http://localhost:8000/downloads/report.pdf?sig=abc", rendered)

    def test_pdf_response_preserves_s3_presigned_url(self) -> None:
        s3_url = (
            "https://bucket.s3.ap-southeast-1.amazonaws.com/downloads/abc/report.pdf"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=deadbeef"
        )
        context = {
            "artifacts": [
                {"kind": "pdf", "download_url": s3_url, "filename": "report.pdf", "page_count": 4}
            ],
            "outcomes": [],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please generate a pdf",
            llm_output="random draft text",
            context=context,
            require_sources=False,
        )
        self.assertIn(f"[Download PDF]({s3_url})", rendered)

    def test_email_success_response_is_canonical(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/report.pdf"}],
            "outcomes": [{"tool": "send_resend_email", "status": "ok", "email_id": "abc123"}],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="send it to my email",
            llm_output="done",
            context=context,
            require_sources=False,
        )
        self.assertIn("Email sent successfully.", rendered)
        self.assertIn("`abc123`", rendered)
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)

    def test_email_success_prefers_downloads_path_from_filename(self) -> None:
        context = {
            "artifacts": [
                {
                    "kind": "pdf",
                    "download_url": "http://localhost:8000/downloads/report.pdf?sig=abc",
                    "filename": "report.pdf",
                }
            ],
            "outcomes": [{"tool": "send_resend_email", "status": "ok", "email_id": "abc123"}],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="send it to my email",
            llm_output="done",
            context=context,
            require_sources=False,
        )
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)
        self.assertNotIn("http://localhost:8000/downloads/report.pdf?sig=abc", rendered)

    def test_email_success_preserves_s3_presigned_url(self) -> None:
        s3_url = (
            "https://bucket.s3.ap-southeast-1.amazonaws.com/downloads/abc/report.pdf"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=deadbeef"
        )
        context = {
            "artifacts": [{"kind": "pdf", "download_url": s3_url, "filename": "report.pdf"}],
            "outcomes": [{"tool": "send_resend_email", "status": "ok", "email_id": "abc123"}],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="send it to my email",
            llm_output="done",
            context=context,
            require_sources=False,
        )
        self.assertIn(f"[Download PDF]({s3_url})", rendered)

    def test_email_intent_without_verified_outcome_returns_deterministic_unverified_message(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        rendered = render_high_risk_output(
            user_message="please resend the pdf to my email",
            llm_output=(
                "I'm resending the PDF to your email address now. "
                "Please check your inbox and spam folder."
            ),
            context=context,
            require_sources=False,
        )
        self.assertEqual(rendered, EMAIL_DELIVERY_UNVERIFIED_MESSAGE)

    def test_email_intent_without_verified_outcome_uses_pdf_artifact_and_hides_model_claims(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/report.pdf"}],
            "outcomes": [],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please resend the pdf to my email",
            llm_output=(
                "I apologize for the inconvenience.\n\n"
                "<thinking>I will send it again.</thinking>\n\n"
                "I'm resending the PDF to your email address now."
            ),
            context=context,
            require_sources=False,
        )
        self.assertIn(EMAIL_DELIVERY_UNVERIFIED_WITH_PDF_MESSAGE, rendered)
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)
        self.assertNotIn("I'm resending the PDF", rendered)
        self.assertNotIn("<thinking>", rendered)

    def test_email_failure_response_keeps_failure_and_canonical_pdf_link(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/report.pdf"}],
            "outcomes": [
                {
                    "tool": "send_resend_email",
                    "status": "error",
                    "message": "Email failed: RESEND_API_KEY not configured",
                }
            ],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please resend the pdf to my email",
            llm_output="done",
            context=context,
            require_sources=False,
        )
        self.assertIn("Email send failed: Email failed: RESEND_API_KEY not configured", rendered)
        self.assertIn("[Download PDF](/downloads/report.pdf)", rendered)

    def test_sources_section_replaced_with_canonical(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ],
        }
        rendered = render_high_risk_output(
            user_message="latest research",
            llm_output="Answer body\n\nSources:\n- [Old](https://old.example)",
            context=context,
            require_sources=True,
        )
        self.assertIn("Sources:", rendered)
        self.assertIn("https://arxiv.org/abs/2507.18910", rendered)
        self.assertIn("https://example.org/paper", rendered)
        self.assertNotIn("https://old.example", rendered)

    def test_replaces_trailing_sources_block_without_colon(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ],
        }
        rendered = render_high_risk_output(
            user_message="latest research",
            llm_output=(
                "Answer body\n\n"
                "Sources\n"
                "1. Old Source A\n"
                "2. Old Source B\n"
            ),
            context=context,
            require_sources=True,
        )
        self.assertIn("Sources:", rendered)
        self.assertIn("https://arxiv.org/abs/2507.18910", rendered)
        self.assertIn("https://example.org/paper", rendered)
        self.assertNotIn("Old Source A", rendered)

    def test_replaces_trailing_sources_block_with_parenthetical_heading(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ],
        }
        rendered = render_high_risk_output(
            user_message="latest research",
            llm_output=(
                "Answer body\n\n"
                "Sources (all claims above map to these canonical references):\n"
                "- Old Source A\n"
            ),
            context=context,
            require_sources=True,
        )
        self.assertIn("Sources:", rendered)
        self.assertIn("https://arxiv.org/abs/2507.18910", rendered)
        self.assertNotIn("Old Source A", rendered)

    def test_strips_multiple_existing_sources_blocks_before_appending_canonical(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ],
        }
        rendered = render_high_risk_output(
            user_message="latest research",
            llm_output=(
                "Body text.\n\n"
                "### Sources\n"
                "- Old A\n"
                "- Old B\n\n"
                "If you'd like more details, ask.\n\n"
                "Sources:\n"
                "- Old C\n"
            ),
            context=context,
            require_sources=True,
        )
        self.assertEqual(rendered.count("Sources:"), 1)
        self.assertNotIn("Old A", rendered)
        self.assertNotIn("Old C", rendered)

    def test_does_not_force_inline_source_for_citation_like_line(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ],
        }
        rendered = render_high_risk_output(
            user_message="latest research on rag failures",
            llm_output="Key update (Acme Lab, 2026): retrieval drift increased.",
            context=context,
            require_sources=True,
        )
        self.assertNotIn("[source](", rendered)
        self.assertIn("Sources:", rendered)
        self.assertIn("https://arxiv.org/abs/2507.18910", rendered)

    def test_returns_deterministic_message_when_require_sources_but_no_sources(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        rendered = render_high_risk_output(
            user_message="latest rag failures",
            llm_output="Here is a detailed report (Acme Lab, 2026).",
            context=context,
            require_sources=True,
        )
        self.assertEqual(rendered, NO_CANONICAL_SOURCES_MESSAGE)

    def test_non_source_mode_strips_noncanonical_links_when_canonical_exists(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "S1", "url": "https://example.org/a"}],
        }
        rendered = render_high_risk_output(
            user_message="summarize this",
            llm_output=(
                "Useful: [good](https://example.org/a) and "
                "[bad](https://bad.example/x). Raw bad: https://evil.example/z"
            ),
            context=context,
            require_sources=False,
        )
        self.assertIn("[good](https://example.org/a)", rendered)
        self.assertIn("bad (link removed)", rendered)
        self.assertIn("[unverified link removed]", rendered)

    def test_email_success_omits_non_allowlisted_download_url(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "ftp://evil.example/file.pdf"}],
            "outcomes": [{"tool": "send_resend_email", "status": "ok", "email_id": "abc123"}],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="send it to my email",
            llm_output="done",
            context=context,
            require_sources=False,
        )
        self.assertIn("Email sent successfully.", rendered)
        self.assertNotIn("[Download PDF](", rendered)

    def test_pdf_response_omits_non_allowlisted_download_url(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "ftp://evil.example/file.pdf", "page_count": 4}],
            "outcomes": [],
            "search_results": [],
        }
        rendered = render_high_risk_output(
            user_message="please generate a pdf",
            llm_output="draft",
            context=context,
            require_sources=False,
        )
        self.assertIn("Your PDF is ready.", rendered)
        self.assertNotIn("[Download PDF](", rendered)


if __name__ == "__main__":
    unittest.main()
