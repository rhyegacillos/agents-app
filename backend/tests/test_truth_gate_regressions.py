import unittest
from unittest.mock import patch

from services.canonical_renderer import NO_CANONICAL_SOURCES_MESSAGE
from services.output_truth_gate import apply_truth_gate, normalize_truth_context


class TruthGateRegressionTests(unittest.TestCase):
    def test_blocks_placeholder_link(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            "Download here: {{PDF_URL}}",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "block")
        self.assertIn("LINK_PLACEHOLDER", {i["code"] for i in verdict["issues"]})

    def test_blocks_unverified_email_claim(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            "Email sent successfully to your inbox.",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "block")
        self.assertIn("CLAIM_UNVERIFIED_EMAIL_SENT", {i["code"] for i in verdict["issues"]})

    def test_blocks_noncanonical_source_url(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "A", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "B", "url": "https://example.org/paper"},
            ],
        }
        output = (
            "Recent analysis (Acme Lab, 2026) [source](https://not-canonical.example/x)\n\n"
            "Sources:\n"
            "- [A](https://arxiv.org/abs/2507.18910)\n"
            "- [B](https://example.org/paper)\n"
        )
        verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SOURCE_URL_INVALID", {i["code"] for i in verdict["issues"]})

    def test_passes_with_canonical_sources(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "A", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "B", "url": "https://example.org/paper"},
            ],
        }
        output = (
            "Findings from [A](https://arxiv.org/abs/2507.18910) and "
            "[B](https://example.org/paper).\n\n"
            "Sources:\n"
            "- [A](https://arxiv.org/abs/2507.18910)\n"
            "- [B](https://example.org/paper)\n"
        )
        verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_passes_research_output_without_inline_links_when_sources_present(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "A", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "B", "url": "https://example.org/paper"},
            ],
        }
        output = (
            "Stats: Even advanced RAG hallucinates 10-30% (Ozaki et al., 2025).\n\n"
            "Sources:\n"
            "- [A](https://arxiv.org/abs/2507.18910)\n"
            "- [B](https://example.org/paper)\n"
        )
        with patch.dict("os.environ", {"TRUTH_GATE_REQUIRE_INLINE_CITATIONS": "false"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_blocks_research_output_without_inline_links_when_inline_required(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "A", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "B", "url": "https://example.org/paper"},
            ],
        }
        output = (
            "Stats: Even advanced RAG hallucinates 10-30% (Ozaki et al., 2025).\n\n"
            "Sources:\n"
            "- [A](https://arxiv.org/abs/2507.18910)\n"
            "- [B](https://example.org/paper)\n"
        )
        with patch.dict("os.environ", {"TRUTH_GATE_REQUIRE_INLINE_CITATIONS": "true"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SOURCE_LINK_INLINE_MISSING", {i["code"] for i in verdict["issues"]})

    def test_passes_research_output_with_inline_canonical_link_when_inline_required(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [
                {"title": "A", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "B", "url": "https://example.org/paper"},
            ],
        }
        output = (
            "Stats: Even advanced RAG hallucinates 10-30% (Ozaki et al., 2025) "
            "[Ozaki et al., 2025](https://arxiv.org/abs/2507.18910).\n\n"
            "Sources:\n"
            "- [A](https://arxiv.org/abs/2507.18910)\n"
            "- [B](https://example.org/paper)\n"
        )
        with patch.dict("os.environ", {"TRUTH_GATE_REQUIRE_INLINE_CITATIONS": "true"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_passes_source_link_when_only_trailing_slash_differs(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = (
            "Summary from [A](https://example.org/paper/).\n\n"
            "Sources:\n"
            "- [A](https://example.org/paper/)\n"
        )
        verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_downloads_relative_url_is_normalized_safely(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/a.pdf"}],
            "outcomes": [],
            "search_results": [],
        }
        verdict = apply_truth_gate(
            "Your PDF is ready: [Download PDF](/downloads/a.pdf?token=abc123)",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_allows_downloads_filename_path_when_tool_emits_filename(self) -> None:
        context = {
            "artifacts": [
                {
                    "kind": "pdf",
                    "download_url": "https://files.example.com/reports/a.pdf?sig=abc123",
                    "filename": "a.pdf",
                }
            ],
            "outcomes": [],
            "search_results": [],
        }
        verdict = apply_truth_gate(
            "Your PDF is ready: [Download PDF](/downloads/a.pdf)",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_blocks_unverified_page_count_claim(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/a.pdf", "page_count": 4}],
            "outcomes": [],
            "search_results": [],
        }
        verdict = apply_truth_gate(
            "Your PDF is ready: [Download PDF](/downloads/a.pdf). It has 28 pages.",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "block")
        self.assertIn("CLAIM_UNVERIFIED_PAGE_COUNT", {i["code"] for i in verdict["issues"]})

    def test_does_not_enforce_source_links_when_require_sources_false(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            "Recent report (Acme Labs, 2026): this trend increased.",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_passes_citation_like_line_with_link_when_require_sources_false(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.com/report"}],
        }
        verdict = apply_truth_gate(
            "Recent report (Acme Labs, 2026): [details](https://example.com/report).",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_blocks_noncanonical_http_link_when_require_sources_false(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            "Reference: https://not-canonical.example/abc",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SOURCE_URL_INVALID", {i["code"] for i in verdict["issues"]})

    def test_allows_pdf_url_when_it_is_canonical_search_url_even_with_artifacts_present(self) -> None:
        context = {
            "artifacts": [{"kind": "pdf", "download_url": "/downloads/local-report.pdf"}],
            "outcomes": [],
            "search_results": [{"title": "P1", "url": "https://arxiv.org/pdf/2401.05856.pdf"}],
        }
        verdict = apply_truth_gate(
            "Paper: https://arxiv.org/pdf/2401.05856.pdf",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_blocks_when_require_sources_true_and_context_empty_for_regular_output(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            "Recent report (Acme Labs, 2026): trend increased.",
            context,
            risk_tier="high",
            require_sources=True,
        )
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SEARCH_CONTEXT_EMPTY", {i["code"] for i in verdict["issues"]})

    def test_passes_deterministic_no_sources_message_when_context_empty(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        verdict = apply_truth_gate(
            NO_CANONICAL_SOURCES_MESSAGE,
            context,
            risk_tier="high",
            require_sources=True,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_passes_no_sources_message_with_formatting_variation(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        output = (
            "I couldn't include canonical web sources because no valid source URLs were returned by the search tool.\n"
            "Please retry the search request."
        )
        verdict = apply_truth_gate(
            output,
            context,
            risk_tier="high",
            require_sources=True,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_passes_no_sources_message_when_used_as_prefix(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        output = (
            f"{NO_CANONICAL_SOURCES_MESSAGE}\n"
            "Note: try again in a few seconds."
        )
        verdict = apply_truth_gate(
            output,
            context,
            risk_tier="high",
            require_sources=True,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_passes_no_sources_message_with_marker(self) -> None:
        context = {"artifacts": [], "outcomes": [], "search_results": []}
        output = "TRUTH_GATE_NO_SOURCES\nRetry with a broader query."
        verdict = apply_truth_gate(
            output,
            context,
            risk_tier="high",
            require_sources=True,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_normalize_truth_context_dedupes_search_urls_by_normalized_value(self) -> None:
        tool_events = [
            {
                "tool_name": "brave_web_search",
                "output": {
                    "results": [
                        {"title": "A", "url": "https://example.org/paper?utm_source=x"},
                        {"title": "A2", "url": "https://example.org/paper/"},
                        {"title": "B", "url": "https://example.org/other#frag"},
                    ]
                },
            }
        ]
        context = normalize_truth_context(tool_events)
        urls = [r["url"] for r in context.get("search_results", [])]
        self.assertEqual(len(urls), 2)
        self.assertIn("https://example.org/paper", urls)
        self.assertIn("https://example.org/other", urls)

    def test_normalize_truth_context_extracts_pdf_artifact_from_wrapped_content_json(self) -> None:
        tool_events = [
            {
                "tool_name": "mcp__core_tools__generate_pdf_from_text",
                "output": {
                    "content": [
                        {
                            "type": "text",
                            "text": '{"status":"ok","filename":"RAG_Failures_Research.pdf"}',
                        }
                    ]
                },
            }
        ]
        context = normalize_truth_context(tool_events)
        artifacts = context.get("artifacts", [])
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].get("download_url"), "/downloads/RAG_Failures_Research.pdf")

    def test_normalize_truth_context_extracts_email_success_for_prefixed_tool_name(self) -> None:
        tool_events = [
            {
                "tool_name": "mcp__core_tools__send_resend_email",
                "output": "Email sent successfully. ID: abc123",
            }
        ]
        context = normalize_truth_context(tool_events)
        outcomes = context.get("outcomes", [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].get("tool"), "send_resend_email")
        self.assertEqual(outcomes[0].get("status"), "ok")
        self.assertEqual(outcomes[0].get("email_id"), "abc123")

    def test_normalize_truth_context_extracts_email_success_from_wrapped_content_text(self) -> None:
        tool_events = [
            {
                "tool_name": "mcp__core_tools__send_resend_email",
                "output": {
                    "content": [
                        {"type": "text", "text": "Email sent successfully. ID: abc123"}
                    ]
                },
            }
        ]
        context = normalize_truth_context(tool_events)
        outcomes = context.get("outcomes", [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].get("status"), "ok")
        self.assertEqual(outcomes[0].get("email_id"), "abc123")

    def test_unverified_email_claim_passes_when_context_has_normalized_email_success(self) -> None:
        tool_events = [
            {
                "tool_name": "mcp__core_tools__send_resend_email",
                "output": "Email sent successfully. ID: abc123",
            }
        ]
        context = normalize_truth_context(tool_events)
        verdict = apply_truth_gate(
            "Email sent successfully to your inbox.",
            context,
            risk_tier="high",
            require_sources=False,
        )
        self.assertEqual(verdict["status"], "pass")

    def test_require_sources_can_enforce_sources_section_scope(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = "Mentioned above: https://example.org/paper\n\nNo sources section."
        with patch.dict("os.environ", {"TRUTH_GATE_SOURCE_URL_SCOPE": "sources_section"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SOURCE_LINK_MISSING", {i["code"] for i in verdict["issues"]})

    def test_require_sources_sources_section_scope_passes_when_section_has_links(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = "Summary text.\n\nSources:\n- [A](https://example.org/paper)"
        with patch.dict("os.environ", {"TRUTH_GATE_SOURCE_URL_SCOPE": "sources_section"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_require_sources_sources_section_scope_accepts_sources_header_without_colon(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = "Summary text.\n\nSources\n- [A](https://example.org/paper)"
        with patch.dict("os.environ", {"TRUTH_GATE_SOURCE_URL_SCOPE": "sources_section"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_require_sources_sources_section_scope_accepts_parenthetical_sources_header(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = (
            "Summary text.\n\n"
            "Sources (all claims above map to these canonical references):\n"
            "- [A](https://example.org/paper)"
        )
        with patch.dict("os.environ", {"TRUTH_GATE_SOURCE_URL_SCOPE": "sources_section"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_require_sources_sources_section_scope_accepts_markdown_heading_sources(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = "Summary text.\n\n### Sources\n- [A](https://example.org/paper)"
        with patch.dict("os.environ", {"TRUTH_GATE_SOURCE_URL_SCOPE": "sources_section"}, clear=False):
            verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "pass")

    def test_blocks_duplicate_sources_sections(self) -> None:
        context = {
            "artifacts": [],
            "outcomes": [],
            "search_results": [{"title": "A", "url": "https://example.org/paper"}],
        }
        output = (
            "Summary text.\n\n"
            "Sources:\n"
            "- [A](https://example.org/paper)\n\n"
            "Sources:\n"
            "- [A](https://example.org/paper)\n"
        )
        verdict = apply_truth_gate(output, context, risk_tier="high", require_sources=True)
        self.assertEqual(verdict["status"], "block")
        self.assertIn("SOURCE_SECTION_DUPLICATE", {i["code"] for i in verdict["issues"]})


if __name__ == "__main__":
    unittest.main()
