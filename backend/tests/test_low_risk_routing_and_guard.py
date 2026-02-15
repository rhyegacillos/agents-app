import unittest

from services.prose_guard import apply_low_risk_prose_guard
from services.risk_router import classify_risk


class LowRiskRoutingAndGuardTests(unittest.TestCase):
    def test_research_query_routes_high(self) -> None:
        out = classify_risk("share latest research papers on rag failures")
        self.assertEqual(out.get("tier"), "high")

    def test_low_risk_guard_keeps_regular_source_links(self) -> None:
        text = "See source: https://arxiv.org/abs/2507.18910"
        guarded, issues = apply_low_risk_prose_guard(text)
        self.assertIn("https://arxiv.org/abs/2507.18910", guarded)
        self.assertIn("raw_url_present", issues)

    def test_low_risk_guard_masks_sensitive_download_links(self) -> None:
        text = "Download: /downloads/report.pdf"
        guarded, issues = apply_low_risk_prose_guard(text)
        self.assertIn("[link withheld in low-risk mode]", guarded)
        self.assertIn("sensitive_url_removed", issues)

    def test_email_address_routes_high(self) -> None:
        out = classify_risk("gacillos.rhye@icloud.com")
        self.assertEqual(out.get("tier"), "high")
        self.assertEqual(out.get("reason"), "email_address")


if __name__ == "__main__":
    unittest.main()
