import importlib.util
import pathlib
import pickle
import sys
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "versions" / "aether.0.20.0.py"
sys.path.insert(0, str(SRC))

from aether.memory import MenteMemory as NewMenteMemory


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_0_20_0", ARCHIVE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def memory_snapshot(memory):
    return {
        "working": list(memory.working),
        "working_maxlen": memory.working.maxlen,
        "episodic": list(memory.episodic),
        "episodic_maxlen": memory.episodic.maxlen,
        "semantic": dict(memory.semantic),
        "vectors": [v.copy() for v in memory.vectors],
    }


class MenteMemoryRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = load_archive()

    def assert_memory_equal(self, old, new):
        old_state = memory_snapshot(old)
        new_state = memory_snapshot(new)
        self.assertEqual(old_state["working"], new_state["working"])
        self.assertEqual(old_state["working_maxlen"], new_state["working_maxlen"])
        self.assertEqual(old_state["episodic"], new_state["episodic"])
        self.assertEqual(old_state["episodic_maxlen"], new_state["episodic_maxlen"])
        self.assertEqual(old_state["semantic"], new_state["semantic"])
        self.assertEqual(len(old_state["vectors"]), len(new_state["vectors"]))
        for old_vec, new_vec in zip(old_state["vectors"], new_state["vectors"]):
            np.testing.assert_array_equal(old_vec, new_vec)

    def test_initialization_matches_archive(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        self.assert_memory_equal(old, new)

        old_custom = self.archive.MenteMemory(working_capacity=2, episodic_capacity=3)
        new_custom = NewMenteMemory(working_capacity=2, episodic_capacity=3)
        self.assert_memory_equal(old_custom, new_custom)

    def test_add_experience_state_transitions_match_archive(self):
        old = self.archive.MenteMemory(working_capacity=3, episodic_capacity=2)
        new = NewMenteMemory(working_capacity=3, episodic_capacity=2)
        experiences = [
            {"pattern": "wave", "contour_reward": 0.2, "state": [0.0, 1.0, 2.0]},
            {"pattern": "shape", "contour_reward": 0.8, "state": np.array([3.0, 4.0, 5.0])},
            {"pattern": "shape", "contour_reward": 0.71, "params": {"density": 0.4}},
            {"pattern": "fractal", "reward": 0.5, "state": [6.0, 7.0, 8.0]},
        ]
        for experience in experiences:
            old.add_experience(experience)
            new.add_experience(experience)
            self.assert_memory_equal(old, new)

    def test_recall_similar_matches_archive(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        experiences = [
            {"id": "a", "pattern": "wave", "contour_reward": 0.2},
            {"id": "b", "pattern": "shape", "contour_reward": 0.9},
            {"id": "c", "pattern": "shape", "contour_reward": 0.6},
            {"id": "d", "pattern": "cellular", "contour_reward": 0.75},
        ]
        for experience in experiences:
            old.add_experience(experience)
            new.add_experience(experience)
        query = {"pattern": "shape", "contour_reward": 0.7}
        self.assertEqual(old.recall_similar(query, k=3), new.recall_similar(query, k=3))
        self.assertEqual(old.recall_similar({}, k=10), new.recall_similar({}, k=10))

    def test_semantic_updates_match_archive(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        old.update_semantic("pattern.bias", {"shape": 0.8})
        new.update_semantic("pattern.bias", {"shape": 0.8})
        self.assert_memory_equal(old, new)

    def test_vector_capacity_and_novelty_match_archive(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        for i in range(205):
            experience = {
                "pattern": "shape" if i % 2 else "wave",
                "contour_reward": 0.9 if i % 3 == 0 else 0.1,
                "state": np.linspace(i, i + 1, 36),
            }
            old.add_experience(experience)
            new.add_experience(experience)
        self.assert_memory_equal(old, new)
        self.assertEqual(len(old.vectors), 200)
        self.assertEqual(len(new.vectors), 200)

        query = np.linspace(0.5, 1.5, 36)
        self.assertEqual(old.novelty(query), new.novelty(query))

    def test_novelty_for_empty_memory_matches_archive(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        query = np.ones(36)
        self.assertEqual(old.novelty(query), new.novelty(query))

    def test_pickle_roundtrip_preserves_extracted_state_shape(self):
        old = self.archive.MenteMemory()
        new = NewMenteMemory()
        experience = {"pattern": "shape", "contour_reward": 0.95, "state": [1, 2, 3]}
        old.add_experience(experience)
        new.add_experience(experience)
        old.update_semantic("x", 1)
        new.update_semantic("x", 1)

        old_roundtrip = pickle.loads(pickle.dumps(old))
        new_roundtrip = pickle.loads(pickle.dumps(new))
        self.assert_memory_equal(old_roundtrip, new_roundtrip)


if __name__ == "__main__":
    unittest.main()
