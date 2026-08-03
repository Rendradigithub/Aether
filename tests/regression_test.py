import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CORE = SRC / "aether" / "core.py"


class CliRegressionTest(unittest.TestCase):
    def test_core_delegates_existing_cli_usage(self):
        result = subprocess.run(
            [sys.executable, str(CORE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage: python aether.0.20.0.py --image circle.png --auto 500", result.stdout)


if __name__ == "__main__":
    unittest.main()
