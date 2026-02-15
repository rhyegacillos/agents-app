import unittest

from services.truth_fix_loop import build_auto_fix_instructions, should_attempt_auto_fix


class TruthFixLoopPolicyTests(unittest.TestCase):
    def test_allows_auto_fix_for_source_issues(self) -> None:
        self.assertTrue(
            should_attempt_auto_fix(["SOURCE_LINK_MISSING", "SOURCE_URL_INVALID"])
        )

    def test_blocks_auto_fix_for_hard_block_codes(self) -> None:
        self.assertFalse(
            should_attempt_auto_fix(["CLAIM_UNVERIFIED_EMAIL_SENT", "SOURCE_LINK_MISSING"])
        )

    def test_allows_auto_fix_without_source_mode_flag(self) -> None:
        self.assertTrue(should_attempt_auto_fix(["SOURCE_LINK_MISSING"]))

    def test_allows_auto_fix_for_inline_source_issues(self) -> None:
        self.assertTrue(
            should_attempt_auto_fix(["SOURCE_LINK_INLINE_MISSING", "SOURCE_LINK_INLINE_NONCANONICAL"])
        )

    def test_allows_auto_fix_for_duplicate_sources_section(self) -> None:
        self.assertTrue(should_attempt_auto_fix(["SOURCE_SECTION_DUPLICATE"]))

    def test_allows_auto_fix_for_noncanonical_artifact_link_issue(self) -> None:
        self.assertTrue(should_attempt_auto_fix(["LINK_NOT_CANONICAL"]))

    def test_build_instructions_embeds_canonical_sources(self) -> None:
        context = {
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
                {"title": "S2", "url": "https://example.org/paper"},
            ]
        }
        text = build_auto_fix_instructions(
            issue_codes=["SOURCE_LINK_MISSING"],
            issue_details=[
                {
                    "code": "SOURCE_LINK_MISSING",
                    "path": "output.line:12",
                    "detail": "Citation-like text must include a clickable source URL.",
                }
            ],
            truth_context=context,
            attempt=1,
            max_attempts=2,
        )
        self.assertIn("SOURCE_LINK_MISSING", text)
        self.assertIn("https://arxiv.org/abs/2507.18910", text)
        self.assertIn("https://example.org/paper", text)
        self.assertIn("attempt 1 of 2", text)
        self.assertIn("output.line:12", text)
        self.assertIn("Do not fabricate claim-to-source mapping.", text)
        self.assertIn("Do not append generic per-sentence links like `[source](url)`.", text)

    def test_build_instructions_include_required_source_target(self) -> None:
        context = {
            "search_results": [
                {"title": "S1", "url": "https://arxiv.org/abs/2507.18910"},
            ]
        }
        text = build_auto_fix_instructions(
            issue_codes=["SOURCE_LINK_MISSING"],
            issue_details=[
                {
                    "code": "SOURCE_LINK_MISSING",
                    "required": 1,
                }
            ],
            truth_context=context,
            attempt=2,
            max_attempts=2,
        )
        self.assertIn("Ensure at least 1 canonical source URL(s)", text)


if __name__ == "__main__":
    unittest.main()
