import unittest

from mcp_tools.core_mcp_server import _markdown_to_html


class PdfMarkdownNormalizationTests(unittest.TestCase):
    def test_normalizes_inline_bullet_table_to_html_table(self) -> None:
        text = (
            "- Benchmarks/Evals: | Benchmark | Focus | Key Finding |\n"
            "|---|---|---|\n"
            "| arXiv:2503.21157 | Hallucination detection | 70-80% |\n"
        )
        html = _markdown_to_html(text)
        self.assertIn("<table>", html)
        self.assertIn("Benchmark", html)
        self.assertIn("arXiv:2503.21157", html)

    def test_wraps_code_like_block_in_fence(self) -> None:
        text = (
            "Quick Eval Harness Suggestion:\n"
            "# Minimal RAG eval\n"
            "import ragas\n"
            "from datasets import Dataset\n"
            "def eval_rag(queries: list):\n"
            "    return ragas.evaluate(queries)\n"
        )
        html = _markdown_to_html(text)
        self.assertIn("<pre", html)
        self.assertIn("import ragas", html)
        self.assertIn("def eval_rag", html)

    def test_linkifies_plain_urls_inside_table_cells(self) -> None:
        text = (
            "| Paper | Source Link |\n"
            "| --- | --- |\n"
            "| Seven Failure Points | https://arxiv.org/abs/2401.05856 |\n"
        )
        html = _markdown_to_html(text)
        self.assertIn('href="https://arxiv.org/abs/2401.05856"', html)


if __name__ == "__main__":
    unittest.main()
