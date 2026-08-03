import importlib.util
import pathlib
import random
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "versions" / "aether.0.20.0.py"
sys.path.insert(0, str(SRC))

from aether.shape_generator import ShapeAwareGenerator as NewShapeAwareGenerator


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_0_20_0", ARCHIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShapeAwareGeneratorRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = load_archive()

    def test_generate_shape_matches_archive_with_identical_random_seeds(self):
        cases = [
            (0.0, 0.0, 0.0, 0.0),
            (0.2, 0.5, 0.6, 0.1),
            (0.5, 0.2, 0.8, 0.2),
            (0.8, 1.0, 0.4, 0.0),
            (0.99, 0.7, 0.95, 0.6),
        ]
        for seed, args in enumerate(cases, 42):
            with self.subTest(seed=seed, args=args):
                random.seed(seed)
                old = self.archive.ShapeAwareGenerator.generate_shape(*args)
                random.seed(seed)
                new = NewShapeAwareGenerator.generate_shape(*args)
                self.assertEqual(old, new)

    def test_draw_helpers_match_archive(self):
        for method_name, args in [
            ("draw_circle", (8, 5, 3)),
            ("draw_square", (8, 5, 6)),
            ("draw_triangle", (8, 7, 5)),
        ]:
            with self.subTest(method_name=method_name):
                old_grid = [[" " for _ in range(18)] for _ in range(12)]
                new_grid = [[" " for _ in range(18)] for _ in range(12)]
                getattr(self.archive.ShapeAwareGenerator, method_name)(old_grid, *args)
                getattr(NewShapeAwareGenerator, method_name)(new_grid, *args)
                self.assertEqual(old_grid, new_grid)


if __name__ == "__main__":
    unittest.main()
