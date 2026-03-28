import subprocess
import sys
import unittest
from pathlib import Path


class DocsConsistencyTests(unittest.TestCase):
    def test_generated_architecture_facts_are_current(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "scripts/render_architecture_facts.py", "--check"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self.fail((result.stderr or result.stdout).strip())


if __name__ == "__main__":
    unittest.main()
