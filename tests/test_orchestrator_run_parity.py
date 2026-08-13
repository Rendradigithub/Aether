import contextlib
import importlib.util
import io
import random
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

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


def assert_cores_equal(test_case, archive_core, modular_core, label):
    """Reusable assertion helper for comparing core state."""
    # Core state
    test_case.assertEqual(archive_core.cycle, modular_core.cycle,
                          f"{label}: cycle mismatch")

    # Budget
    test_case.assertEqual(archive_core.budget.energy, modular_core.budget.energy,
                          f"{label}: energy mismatch")
    test_case.assertEqual(archive_core.budget.attention, modular_core.budget.attention,
                          f"{label}: attention mismatch")
    test_case.assertEqual(archive_core.budget.fatigue, modular_core.budget.fatigue,
                          f"{label}: fatigue mismatch")
    test_case.assertEqual(archive_core.budget.failure_burden, modular_core.budget.failure_burden,
                          f"{label}: failure_burden mismatch")
    test_case.assertEqual(archive_core.budget.consecutive_same_pattern,
                          modular_core.budget.consecutive_same_pattern,
                          f"{label}: consecutive_same_pattern mismatch")

    # Generator params
    test_case.assertEqual(archive_core.generator.params, modular_core.generator.params,
                          f"{label}: generator params mismatch")

    # Pattern counts
    test_case.assertEqual(dict(archive_core.pattern_counts), dict(modular_core.pattern_counts),
                          f"{label}: pattern_counts mismatch")

    # Reward history
    test_case.assertEqual(list(archive_core.budget.reward_history),
                          list(modular_core.budget.reward_history),
                          f"{label}: reward_history mismatch")

    # Current state
    np.testing.assert_allclose(archive_core.current_state,
                               modular_core.current_state,
                               atol=1e-6,
                               err_msg=f"{label}: current_state mismatch")

    # Memory
    test_case.assertEqual(list(archive_core.memory.working),
                          list(modular_core.memory.working),
                          f"{label}: working memory mismatch")
    test_case.assertEqual(list(archive_core.memory.episodic),
                          list(modular_core.memory.episodic),
                          f"{label}: episodic memory mismatch")
    test_case.assertEqual(archive_core.memory.semantic,
                          modular_core.memory.semantic,
                          f"{label}: semantic memory mismatch")
    for v1, v2 in zip(archive_core.memory.vectors, modular_core.memory.vectors):
        np.testing.assert_allclose(v1, v2, atol=1e-6,
                                   err_msg=f"{label}: memory vector mismatch")
    test_case.assertEqual(len(archive_core.memory.vectors),
                          len(modular_core.memory.vectors),
                          f"{label}: memory vector count mismatch")

    # World model
    test_case.assertAlmostEqual(archive_core.world_model.prediction_error,
                                modular_core.world_model.prediction_error,
                                places=6,
                                msg=f"{label}: prediction_error mismatch")
    test_case.assertAlmostEqual(archive_core.world_model.confidence,
                                modular_core.world_model.confidence,
                                places=6,
                                msg=f"{label}: confidence mismatch")
    np.testing.assert_allclose(archive_core.world_model.W1,
                               modular_core.world_model.W1,
                               atol=1e-6,
                               err_msg=f"{label}: world W1 mismatch")
    np.testing.assert_allclose(archive_core.world_model.W2,
                               modular_core.world_model.W2,
                               atol=1e-6,
                               err_msg=f"{label}: world W2 mismatch")
    np.testing.assert_allclose(archive_core.world_model.b1,
                               modular_core.world_model.b1,
                               atol=1e-6,
                               err_msg=f"{label}: world b1 mismatch")
    np.testing.assert_allclose(archive_core.world_model.b2,
                               modular_core.world_model.b2,
                               atol=1e-6,
                               err_msg=f"{label}: world b2 mismatch")

    # Decoder
    test_case.assertEqual(archive_core.decoder.is_trained,
                          modular_core.decoder.is_trained,
                          f"{label}: decoder trained flag mismatch")
    test_case.assertEqual(len(archive_core.decoder.training_buffer),
                          len(modular_core.decoder.training_buffer),
                          f"{label}: decoder buffer length mismatch")
    test_case.assertEqual(archive_core.decoder.loss_history,
                          modular_core.decoder.loss_history,
                          f"{label}: decoder loss_history mismatch")
    test_case.assertEqual(archive_core.decoder.best_loss,
                          modular_core.decoder.best_loss,
                          f"{label}: decoder best_loss mismatch")
    test_case.assertEqual(archive_core.decoder.current_threshold,
                          modular_core.decoder.current_threshold,
                          f"{label}: decoder threshold mismatch")
    for key in ['W1', 'b1', 'W2', 'b2', 'W3', 'b3', 'W4', 'b4']:
        w_arch = getattr(archive_core.decoder, key)
        w_mod = getattr(modular_core.decoder, key)
        np.testing.assert_allclose(w_arch, w_mod, atol=1e-6,
                                   err_msg=f"{label}: decoder {key} mismatch")


class OrchestratorRunParityTest(unittest.TestCase):
    def test_run_parity(self):
        # Suppress harmless RuntimeWarnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)

        # Load archive and import orchestrator
        archive_mod = load_archive()
        ArchiveCore = archive_mod.AetherCognitiveCore
        from src.aether.orchestrator import AetherCognitiveCore as ModularCore

        # Create temporary stimulus
        stimulus_path = create_stimulus_file()

        # Use a small deterministic cycle count
        RUN_CYCLES = 10
        CONSTRUCTOR_SEED = 42
        RUN_SEED = 12345

        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            workspace1 = Path(tmp1)
            workspace2 = Path(tmp2)

            # ------------------------------------------------------------------
            # 1) Instantiate both cores with identical RNG state
            # ------------------------------------------------------------------
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
            # 2) Run archive core (capture stdout, patch sleep)
            # ------------------------------------------------------------------
            random.seed(RUN_SEED)
            np.random.seed(RUN_SEED)
            archive_stdout_capture = io.StringIO()
            with patch('time.sleep', return_value=None):
                with contextlib.redirect_stdout(archive_stdout_capture):
                    archive_core.run(cycles=RUN_CYCLES)
            archive_stdout = archive_stdout_capture.getvalue()

            # ------------------------------------------------------------------
            # 3) Run modular core (capture stdout, patch sleep)
            # ------------------------------------------------------------------
            random.seed(RUN_SEED)
            np.random.seed(RUN_SEED)
            modular_stdout_capture = io.StringIO()
            with patch('time.sleep', return_value=None):
                with contextlib.redirect_stdout(modular_stdout_capture):
                    modular_core.run(cycles=RUN_CYCLES)
            modular_stdout = modular_stdout_capture.getvalue()

            # ------------------------------------------------------------------
            # 4) Verify cycle count (implicitly checked by state comparison,
            #    but we assert explicitly from the summary)
            # ------------------------------------------------------------------
            self.assertIn(f"Total cycles: {RUN_CYCLES}", archive_stdout,
                          "Archive stdout missing expected cycle count")
            self.assertIn(f"Total cycles: {RUN_CYCLES}", modular_stdout,
                          "Modular stdout missing expected cycle count")

            # ------------------------------------------------------------------
            # 5) Verify standard output is identical
            # ------------------------------------------------------------------
            self.assertEqual(archive_stdout, modular_stdout,
                             "run() stdout differs between archive and modular orchestrator")

            # ------------------------------------------------------------------
            # 6) Verify final core state is identical
            # ------------------------------------------------------------------
            assert_cores_equal(self, archive_core, modular_core, "After run()")

            # ------------------------------------------------------------------
            # 7) Verify decoder weights persistence (context-managed to close files)
            # ------------------------------------------------------------------
            archive_weights_path = workspace1 / "decoder_weights.npz"
            modular_weights_path = workspace2 / "decoder_weights.npz"

            self.assertTrue(archive_weights_path.exists(),
                            "Archive did not save decoder_weights.npz")
            self.assertTrue(modular_weights_path.exists(),
                            "Modular did not save decoder_weights.npz")

            # Use context manager to ensure files are closed before directory cleanup
            with np.load(archive_weights_path) as archive_weights, \
                 np.load(modular_weights_path) as modular_weights:

                self.assertEqual(set(archive_weights.keys()), set(modular_weights.keys()),
                                 "Saved weight keys differ")
                for key in archive_weights.keys():
                    np.testing.assert_allclose(archive_weights[key],
                                               modular_weights[key],
                                               atol=1e-6,
                                               err_msg=f"Saved weight {key} differs")

                # Optional: ensure saved weights match the final decoder state
                for key in ['W1', 'b1', 'W2', 'b2', 'W3', 'b3', 'W4', 'b4']:
                    w_arch_core = getattr(archive_core.decoder, key)
                    w_mod_core = getattr(modular_core.decoder, key)
                    np.testing.assert_allclose(w_arch_core, archive_weights[key],
                                               atol=1e-6,
                                               err_msg=f"Archive saved {key} does not match core state")
                    np.testing.assert_allclose(w_mod_core, modular_weights[key],
                                               atol=1e-6,
                                               err_msg=f"Modular saved {key} does not match core state")

        # Clean up stimulus file
        stimulus_path.unlink()


if __name__ == '__main__':
    unittest.main()