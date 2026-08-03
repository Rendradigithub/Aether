import contextlib
import importlib.util
import io
import pathlib
import sys
import tempfile
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ARCHIVE = ROOT / "archive" / "versions" / "aether.0.20.0.py"
CHECKPOINT = ROOT / "experiments" / "aether_works_v020" / "decoder_weights.npz"
sys.path.insert(0, str(SRC))

from aether.decoder import NeuralDecoder as NewNeuralDecoder


def load_archive():
    spec = importlib.util.spec_from_file_location("aether_0_20_0", ARCHIVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WEIGHT_KEYS = ("W1", "b1", "W2", "b2", "W3", "b3", "W4", "b4")


def decoder_state(decoder):
    return {key: getattr(decoder, key) for key in WEIGHT_KEYS}


class NeuralDecoderRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = load_archive()

    def assert_decoder_weights_equal(self, old, new):
        for key in WEIGHT_KEYS:
            np.testing.assert_array_equal(getattr(old, key), getattr(new, key))

    def test_initialization_matches_archive_with_identical_random_seed(self):
        np.random.seed(123)
        old = self.archive.NeuralDecoder()
        np.random.seed(123)
        new = NewNeuralDecoder()
        self.assert_decoder_weights_equal(old, new)
        self.assertEqual(old.input_dim, new.input_dim)
        self.assertEqual(old.is_trained, new.is_trained)
        self.assertEqual(old.loss_history, new.loss_history)
        self.assertEqual(old.best_loss, new.best_loss)
        self.assertEqual(old.best_weights, new.best_weights)
        self.assertEqual(old.current_threshold, new.current_threshold)

    def test_forward_and_prediction_match_archive(self):
        np.random.seed(456)
        old = self.archive.NeuralDecoder()
        np.random.seed(456)
        new = NewNeuralDecoder()
        x = np.linspace(0.0, 1.0, 36, dtype=np.float64)
        np.testing.assert_array_equal(old.forward(x), new.forward(x))
        old_out, old_cache = old.forward(x, cache=True)
        new_out, new_cache = new.forward(x, cache=True)
        np.testing.assert_array_equal(old_out, new_out)
        for old_arr, new_arr in zip(old_cache, new_cache):
            np.testing.assert_array_equal(old_arr, new_arr)
        self.assertEqual(old.predict_params(x), new.predict_params(x))

    def test_collect_sample_matches_archive(self):
        np.random.seed(789)
        old = self.archive.NeuralDecoder()
        np.random.seed(789)
        new = NewNeuralDecoder()
        stimulus = np.arange(36, dtype=np.float32) / 36.0
        params = {
            "pattern": "shape",
            "symmetry": 0.25,
            "density": 0.75,
            "complexity": 0.5,
            "noise": 0.1,
            "shape_param": 0.8,
        }
        old.collect_sample(stimulus, params)
        new.collect_sample(stimulus, params)
        self.assertEqual(len(old.training_buffer), len(new.training_buffer))
        np.testing.assert_array_equal(old.training_buffer[0][0], new.training_buffer[0][0])
        np.testing.assert_array_equal(old.training_buffer[0][1], new.training_buffer[0][1])
        self.assertEqual(old.current_threshold, new.current_threshold)

    def test_training_updates_match_archive(self):
        np.random.seed(321)
        old = self.archive.NeuralDecoder()
        np.random.seed(321)
        new = NewNeuralDecoder()
        for i in range(40):
            stimulus = (np.arange(36, dtype=np.float64) + i) / 50.0
            params = {
                "pattern": "shape",
                "symmetry": (i % 10) / 10.0,
                "density": 0.2 + (i % 7) / 10.0,
                "complexity": 0.1 + (i % 8) / 10.0,
                "noise": (i % 6) / 20.0,
                "shape_param": (i % 11) / 11.0,
            }
            old.collect_sample(stimulus, params)
            new.collect_sample(stimulus, params)
        np.random.seed(654)
        with contextlib.redirect_stdout(io.StringIO()):
            old.train(epochs=2, batch_size=8, lr=0.003)
        np.random.seed(654)
        with contextlib.redirect_stdout(io.StringIO()):
            new.train(epochs=2, batch_size=8, lr=0.003)
        self.assert_decoder_weights_equal(old, new)
        self.assertEqual(old.loss_history, new.loss_history)
        self.assertEqual(old.best_loss, new.best_loss)
        self.assertEqual(old.is_trained, new.is_trained)
        for old_arr, new_arr in zip(old.best_weights, new.best_weights):
            np.testing.assert_array_equal(old_arr, new_arr)

    def test_saved_checkpoint_arrays_match_archive(self):
        np.random.seed(987)
        old = self.archive.NeuralDecoder()
        np.random.seed(987)
        new = NewNeuralDecoder()
        with tempfile.TemporaryDirectory() as tmp:
            old_path = pathlib.Path(tmp) / "old_decoder_weights.npz"
            new_path = pathlib.Path(tmp) / "new_decoder_weights.npz"
            old.save_weights(old_path)
            new.save_weights(new_path)
            with np.load(old_path) as old_data, np.load(new_path) as new_data:
                self.assertEqual(tuple(old_data.files), tuple(new_data.files))
                for key in WEIGHT_KEYS:
                    np.testing.assert_array_equal(old_data[key], new_data[key])

    def test_existing_checkpoint_load_matches_archive_and_inference(self):
        if not CHECKPOINT.exists():
            self.skipTest(f"missing checkpoint: {CHECKPOINT}")
        np.random.seed(135)
        old = self.archive.NeuralDecoder()
        np.random.seed(135)
        new = NewNeuralDecoder()
        with contextlib.redirect_stdout(io.StringIO()):
            old.load_weights(CHECKPOINT)
        with contextlib.redirect_stdout(io.StringIO()):
            new.load_weights(CHECKPOINT)
        self.assert_decoder_weights_equal(old, new)
        self.assertEqual(old.is_trained, new.is_trained)
        self.assertEqual(old.current_threshold, new.current_threshold)
        x = np.linspace(1.0, 0.0, 36, dtype=np.float64)
        np.testing.assert_array_equal(old.forward(x), new.forward(x))
        self.assertEqual(old.predict_params(x), new.predict_params(x))


if __name__ == "__main__":
    unittest.main()
