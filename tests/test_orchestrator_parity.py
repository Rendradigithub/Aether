import importlib.util
import random
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

# Determine paths
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = ROOT / "archive" / "versions" / "aether.0.20.0.py"


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_archive", ARCHIVE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_stimulus_file():
    """Create a temporary file with a deterministic 36‑dimensional vector."""
    vec = np.linspace(0, 1, 36)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    tmp.write(' '.join(f"{v:.6f}" for v in vec))
    tmp.close()
    return Path(tmp.name)


class OrchestratorParityTest(unittest.TestCase):
    def test_parity(self):
        # Suppress RuntimeWarnings (e.g., divide by zero) – these are not parity failures
        warnings.filterwarnings("ignore", category=RuntimeWarning)

        # Load archive and import orchestrator
        archive_mod = load_archive()
        ArchiveCore = archive_mod.AetherCognitiveCore
        from src.aether.orchestrator import AetherCognitiveCore as ModularCore

        # Create temporary stimulus
        stimulus_path = create_stimulus_file()

        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            workspace1 = Path(tmp1)
            workspace2 = Path(tmp2)

            # ------------------------------------------------------------------
            # 1) Instantiate both cores with the same random seed
            # ------------------------------------------------------------------
            CONSTRUCTOR_SEED = 42

            random.seed(CONSTRUCTOR_SEED)
            np.random.seed(CONSTRUCTOR_SEED)
            archive_core = ArchiveCore(stimulus_source=str(stimulus_path),
                                       workspace=str(workspace1),
                                       quiet=True)

            random.seed(CONSTRUCTOR_SEED)
            np.random.seed(CONSTRUCTOR_SEED)
            modular_core = ModularCore(stimulus_source=str(stimulus_path),
                                       workspace=str(workspace2),
                                       quiet=True)

            # ------------------------------------------------------------------
            # 2) Run cycles, resetting random seed before each corresponding step
            # ------------------------------------------------------------------
            num_cycles = 3

            for i in range(num_cycles):
                step_seed = 1000 + i  # unique per cycle

                # Archive step
                random.seed(step_seed)
                np.random.seed(step_seed)
                art_arch, reward_arch, rad_arch, pat_arch = archive_core.step()

                # Modular step (same seed)
                random.seed(step_seed)
                np.random.seed(step_seed)
                art_mod, reward_mod, rad_mod, pat_mod = modular_core.step()

                # ------------------------------------------------------------------
                # 3) Assertions – compare returned values and internal state
                # ------------------------------------------------------------------
                self.assertEqual(art_arch, art_mod,
                                 f"Art mismatch at cycle {i+1}")
                self.assertAlmostEqual(reward_arch, reward_mod, places=6,
                                       msg=f"Reward mismatch at cycle {i+1}")
                self.assertAlmostEqual(rad_arch, rad_mod, places=6,
                                       msg=f"Radial similarity mismatch at cycle {i+1}")
                self.assertEqual(pat_arch, pat_mod,
                                 f"Pattern mismatch at cycle {i+1}")

                # Cycle number
                self.assertEqual(archive_core.cycle, modular_core.cycle,
                                 f"Cycle number mismatch at cycle {i+1}")

                # Budget
                self.assertEqual(archive_core.budget.energy, modular_core.budget.energy,
                                 f"Energy mismatch at cycle {i+1}")
                self.assertEqual(archive_core.budget.attention, modular_core.budget.attention,
                                 f"Attention mismatch at cycle {i+1}")
                self.assertEqual(archive_core.budget.fatigue, modular_core.budget.fatigue,
                                 f"Fatigue mismatch at cycle {i+1}")
                self.assertEqual(archive_core.budget.failure_burden, modular_core.budget.failure_burden,
                                 f"Failure burden mismatch at cycle {i+1}")
                self.assertEqual(archive_core.budget.consecutive_same_pattern,
                                 modular_core.budget.consecutive_same_pattern,
                                 f"Consecutive same pattern mismatch at cycle {i+1}")

                # Generator params
                self.assertEqual(archive_core.generator.params, modular_core.generator.params,
                                 f"Generator params mismatch at cycle {i+1}")

                # Pattern counts
                self.assertEqual(dict(archive_core.pattern_counts), dict(modular_core.pattern_counts),
                                 f"Pattern counts mismatch at cycle {i+1}")

                # Reward history
                self.assertEqual(list(archive_core.budget.reward_history),
                                 list(modular_core.budget.reward_history),
                                 f"Reward history mismatch at cycle {i+1}")

                # Current state (floating)
                np.testing.assert_allclose(archive_core.current_state,
                                           modular_core.current_state,
                                           atol=1e-6,
                                           err_msg=f"Current state mismatch at cycle {i+1}")

                # Memory state
                self.assertEqual(list(archive_core.memory.working),
                                 list(modular_core.memory.working),
                                 f"Working memory mismatch at cycle {i+1}")
                self.assertEqual(list(archive_core.memory.episodic),
                                 list(modular_core.memory.episodic),
                                 f"Episodic memory mismatch at cycle {i+1}")
                self.assertEqual(archive_core.memory.semantic,
                                 modular_core.memory.semantic,
                                 f"Semantic memory mismatch at cycle {i+1}")
                for v1, v2 in zip(archive_core.memory.vectors, modular_core.memory.vectors):
                    np.testing.assert_allclose(v1, v2, atol=1e-6,
                                               err_msg=f"Memory vector mismatch at cycle {i+1}")
                self.assertEqual(len(archive_core.memory.vectors),
                                 len(modular_core.memory.vectors),
                                 f"Memory vector count mismatch at cycle {i+1}")

                # World model state
                self.assertAlmostEqual(archive_core.world_model.prediction_error,
                                       modular_core.world_model.prediction_error,
                                       places=6,
                                       msg=f"Prediction error mismatch at cycle {i+1}")
                self.assertAlmostEqual(archive_core.world_model.confidence,
                                       modular_core.world_model.confidence,
                                       places=6,
                                       msg=f"Confidence mismatch at cycle {i+1}")
                np.testing.assert_allclose(archive_core.world_model.W1,
                                           modular_core.world_model.W1,
                                           atol=1e-6,
                                           err_msg=f"World model W1 mismatch at cycle {i+1}")
                np.testing.assert_allclose(archive_core.world_model.W2,
                                           modular_core.world_model.W2,
                                           atol=1e-6,
                                           err_msg=f"World model W2 mismatch at cycle {i+1}")
                np.testing.assert_allclose(archive_core.world_model.b1,
                                           modular_core.world_model.b1,
                                           atol=1e-6,
                                           err_msg=f"World model b1 mismatch at cycle {i+1}")
                np.testing.assert_allclose(archive_core.world_model.b2,
                                           modular_core.world_model.b2,
                                           atol=1e-6,
                                           err_msg=f"World model b2 mismatch at cycle {i+1}")

                # Decoder state
                self.assertEqual(archive_core.decoder.is_trained,
                                 modular_core.decoder.is_trained,
                                 f"Decoder trained flag mismatch at cycle {i+1}")
                self.assertEqual(len(archive_core.decoder.training_buffer),
                                 len(modular_core.decoder.training_buffer),
                                 f"Decoder buffer length mismatch at cycle {i+1}")
                self.assertEqual(archive_core.decoder.loss_history,
                                 modular_core.decoder.loss_history,
                                 f"Decoder loss history mismatch at cycle {i+1}")
                self.assertEqual(archive_core.decoder.best_loss,
                                 modular_core.decoder.best_loss,
                                 f"Decoder best loss mismatch at cycle {i+1}")
                self.assertEqual(archive_core.decoder.current_threshold,
                                 modular_core.decoder.current_threshold,
                                 f"Decoder threshold mismatch at cycle {i+1}")
                for key in ['W1', 'b1', 'W2', 'b2', 'W3', 'b3', 'W4', 'b4']:
                    w_arch = getattr(archive_core.decoder, key)
                    w_mod = getattr(modular_core.decoder, key)
                    np.testing.assert_allclose(w_arch, w_mod, atol=1e-6,
                                               err_msg=f"Decoder {key} mismatch at cycle {i+1}")

        # Clean up stimulus file
        stimulus_path.unlink()


if __name__ == '__main__':
    unittest.main()