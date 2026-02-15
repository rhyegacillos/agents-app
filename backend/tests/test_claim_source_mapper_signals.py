import unittest

from services.claim_source_mapper import (
    _line_needs_source_mapping,
    build_claim_source_map,
    inject_claim_source_refs,
)


class ClaimSourceMapperSignalTests(unittest.TestCase):
    def test_plain_title_case_year_is_not_forced_as_citation(self) -> None:
        line = "Recent update from Acme Lab, 2026 improved ranking latency."
        self.assertFalse(_line_needs_source_mapping(line))

    def test_according_to_phrase_triggers_source_need(self) -> None:
        line = "According to Google Research, retrieval quality improves with reranking."
        self.assertTrue(_line_needs_source_mapping(line))

    def test_et_al_parenthetical_triggers_source_need(self) -> None:
        line = "This trend persists (Smith et al., 2024) in production systems."
        self.assertTrue(_line_needs_source_mapping(line))

    def test_numeric_bracket_citation_triggers_source_need(self) -> None:
        line = "Recent findings confirm this behavior [1, 2]."
        self.assertTrue(_line_needs_source_mapping(line))

    def test_existing_link_skips_mapping(self) -> None:
        line = "According to [paper](https://arxiv.org/abs/2401.05856), failures persist."
        self.assertFalse(_line_needs_source_mapping(line))

    def test_claim_source_map_is_hard_disabled(self) -> None:
        text = "According to Smith et al., 2024, failures persist."
        sources = [{"source_id": "S1", "title": "Paper", "url": "https://example.org/paper"}]
        self.assertEqual(build_claim_source_map(text, sources), {})

    def test_inject_claim_source_refs_is_hard_disabled(self) -> None:
        text = "Claim line."
        mappings = {0: {"source_id": "S1", "url": "https://example.org/paper"}}
        self.assertEqual(inject_claim_source_refs(text, mappings), text)


if __name__ == "__main__":
    unittest.main()
