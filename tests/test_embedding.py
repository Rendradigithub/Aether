import importlib.util
import pathlib
import sys
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "versions" / "aether.0.20.0.py"
sys.path.insert(0, str(SRC))

from aether.embedding import ArtEmbedder as NewArtEmbedder


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_0_20_0", ARCHIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArtEmbedderRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = load_archive()

    def test_embed_matches_archive_for_identical_inputs(self):
        arts = [
            "",
            "   \n  \n",
            "  █  \n ███ \n  █  ",
            "█ █\n █ \n█ █",
            "░▒▓\n █ \n  @",
            ".:oO0@\n  ██  \n@0Oo:.",
            "single line art",
        ]
        for art in arts:
            with self.subTest(art=art):
                old = self.archive.ArtEmbedder.embed(art)
                new = NewArtEmbedder.embed(art)
                np.testing.assert_array_equal(old, new)


if __name__ == "__main__":
    unittest.main()
