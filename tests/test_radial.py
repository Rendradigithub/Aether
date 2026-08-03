import importlib.util
import pathlib
import sys
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "versions" / "aether.0.20.0.py"
sys.path.insert(0, str(SRC))

from aether.radial import AreaCoherence as NewAreaCoherence
from aether.radial import RadialSignature as NewRadialSignature


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_0_20_0", ARCHIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RadialRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = load_archive()

    def test_from_ascii_art_matches_archive(self):
        arts = [
            "",
            "  █  \n ███ \n  █  ",
            "█ █\n █ \n█ █",
            "░▒▓\n █ \n  @",
        ]
        for art in arts:
            for contour_only in (True, False):
                with self.subTest(art=art, contour_only=contour_only):
                    old = self.archive.RadialSignature.from_ascii_art(art, num_rays=36, contour_only=contour_only)
                    new = NewRadialSignature.from_ascii_art(art, num_rays=36, contour_only=contour_only)
                    np.testing.assert_array_equal(old, new)

    def test_signature_math_matches_archive(self):
        sig1 = np.array([0.1, 0.3, 0.8, 0.2], dtype=np.float32)
        sig2 = np.array([0.2, 0.4, 0.7, 0.1], dtype=np.float32)
        self.assertEqual(
            self.archive.RadialSignature.cross_correlation(sig1, sig2),
            NewRadialSignature.cross_correlation(sig1, sig2),
        )
        self.assertEqual(
            self.archive.RadialSignature.cross_correlation(np.zeros(4), sig2),
            NewRadialSignature.cross_correlation(np.zeros(4), sig2),
        )

    def test_ideal_contour_and_consistency_match_archive(self):
        cases = [
            (0.2, 0.5, 0.6, 0.1),
            (0.5, 0.2, 0.8, 0.2),
            (0.8, 1.0, 0.4, 0.0),
        ]
        for args in cases:
            with self.subTest(args=args):
                old = self.archive.RadialSignature.ideal_contour_from_params(*args)
                new = NewRadialSignature.ideal_contour_from_params(*args)
                np.testing.assert_array_equal(old, new)
                self.assertEqual(
                    self.archive.RadialSignature.contour_consistency(old, new),
                    NewRadialSignature.contour_consistency(old, new),
                )

    def test_area_coherence_matches_archive(self):
        arts = [
            "",
            "  █  \n ███ \n  █  ",
            "█ █\n █ \n█ █",
            "█  █\n    \n█  █",
        ]
        for art in arts:
            with self.subTest(art=art):
                self.assertEqual(
                    self.archive.AreaCoherence.largest_connected_component_ratio(art),
                    NewAreaCoherence.largest_connected_component_ratio(art),
                )


if __name__ == "__main__":
    unittest.main()
