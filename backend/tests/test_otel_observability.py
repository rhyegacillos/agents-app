import unittest
from unittest.mock import patch

from otel_observability import get_fastapi_excluded_urls, should_trace_http_path


class OtelObservabilityTests(unittest.TestCase):
    def test_default_excluded_urls_include_polling_endpoints(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            pattern = get_fastapi_excluded_urls()

        self.assertIn("^/quota$", pattern)
        self.assertIn("^/jobs(?:/.*)?$", pattern)
        self.assertIn("^/memory(?:/.*)?$", pattern)

    def test_should_trace_http_path_skips_polling_endpoints(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            self.assertFalse(should_trace_http_path("/quota"))
            self.assertFalse(should_trace_http_path("/jobs/abc"))
            self.assertFalse(should_trace_http_path("/memory"))
            self.assertFalse(should_trace_http_path("/memory/candidates"))
            self.assertTrue(should_trace_http_path("/chat"))


if __name__ == "__main__":
    unittest.main()
