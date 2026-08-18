"""
Focused tests for perception encoder abstraction.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.aether.perception import PerceptionEncoder, RadialEncoder
from src.aether.representation import Representation
from src.aether.orchestrator import AetherCognitiveCore


class FakeEncoder(PerceptionEncoder):
    """
    Test encoder that returns a fixed Representation.

    Used to verify that AetherCognitiveCore uses the injected encoder
    rather than constructing RadialEncoder internally.
    """

    def __init__(self, representation=None):
        if representation is None:
            representation = np.linspace(0.1, 0.9, 36, dtype=np.float32)
        self.representation = np.asarray(representation, dtype=np.float32)

    def encode(self, source: str):
        """Return a provider-independent Representation, ignoring source."""
        return Representation(
            vector=self.representation.copy(),
            encoder_id="fake",
        )


class RadialEncoderTest(unittest.TestCase):
    """Tests for RadialEncoder behavior."""

    def test_radial_encoder_text_stimulus_36_values(self):
        """RadialEncoder correctly loads 36-value text stimulus."""
        encoder = RadialEncoder()

        values = np.linspace(0, 1, 36)
        rounded_strings = [f"{v:.6f}" for v in values]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write(" ".join(rounded_strings))
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)

            self.assertIsInstance(result, Representation)
            self.assertEqual(result.dimension, 36)
            self.assertEqual(result.encoder_id, "radial")
            self.assertEqual(result.vector.dtype, np.float64)

            rounded_values = np.array(
                [float(s) for s in rounded_strings], dtype=np.float64
            )
            expected = rounded_values / (np.linalg.norm(rounded_values) + 1e-8)

            np.testing.assert_allclose(
                result.vector,
                expected.astype(np.float32),
                rtol=0,
                atol=1e-7,
            )
        finally:
            Path(temp_path).unlink()

    def test_radial_encoder_invalid_stimulus(self):
        """RadialEncoder returns None for missing file."""
        encoder = RadialEncoder()
        result = encoder.encode("/nonexistent/path/to/file.txt")
        self.assertIsNone(result)

    def test_radial_encoder_wrong_vector_length(self):
        """RadialEncoder returns None for non-36 vector."""
        encoder = RadialEncoder()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write(" ".join(str(i) for i in range(20)))
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)
            self.assertIsNone(result)
        finally:
            Path(temp_path).unlink()

    def test_radial_encoder_output_dimension(self):
        """RadialEncoder produces a 36-D Representation."""
        encoder = RadialEncoder()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write(" ".join(str(i / 36.0) for i in range(36)))
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)

            self.assertIsInstance(result, Representation)
            self.assertEqual(result.vector.shape, (36,))
            self.assertEqual(result.dimension, 36)
            self.assertEqual(result.encoder_id, "radial")
        finally:
            Path(temp_path).unlink()


class PerceptionInjectionTest(unittest.TestCase):
    """Tests for perception encoder dependency injection."""

    def test_default_encoder_is_radial(self):
        """AetherCognitiveCore uses RadialEncoder by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stimulus_file = Path(tmpdir) / "stimulus.txt"
            stimulus_file.write_text(
                " ".join(str(i / 36.0) for i in range(36))
            )

            core = AetherCognitiveCore(
                stimulus_source=str(stimulus_file),
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
            )

            self.assertIsInstance(core.perception_encoder, RadialEncoder)
            self.assertIsInstance(core.stimulus_representation, Representation)
            self.assertEqual(core.stimulus_representation.encoder_id, "radial")
            self.assertEqual(core.representation_dim, 36)

            # Legacy runtime view remains available.
            self.assertIsNotNone(core.stimulus_radial)
            self.assertEqual(core.stimulus_radial.shape, (36,))

    def test_custom_encoder_is_used(self):
        """AetherCognitiveCore uses the injected encoder, not RadialEncoder."""
        fake_vector = np.array([0.123] * 36, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_vector)

        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="dummy_path.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder,
            )

            self.assertIs(core.perception_encoder, fake_encoder)
            self.assertIsInstance(core.stimulus_representation, Representation)
            self.assertEqual(core.stimulus_representation.encoder_id, "fake")
            np.testing.assert_array_equal(
                core.stimulus_representation.vector,
                fake_vector,
            )

            # Compatibility vector must work for non-radial encoders too.
            np.testing.assert_array_equal(
                core.stimulus_radial,
                fake_vector,
            )

    def test_custom_encoder_non_36_dimension(self):
        """Cognitive components follow the injected representation dimension."""
        fake_vector = np.linspace(0.1, 0.9, 64, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_vector)

        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="dummy_path.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder,
            )

            self.assertEqual(core.representation_dim, 64)
            self.assertEqual(core.world_model.W1.shape[1], 65)
            self.assertEqual(core.world_model.W2.shape[0], 64)
            self.assertEqual(core.decoder.input_dim, 64)
            self.assertEqual(core.current_state.shape, (64,))

            np.testing.assert_array_equal(
                core.stimulus_representation.vector,
                fake_vector,
            )
            np.testing.assert_array_equal(
                core.stimulus_radial,
                fake_vector,
            )

    def test_encoder_injection_proves_usage(self):
        """
        Prove AetherCognitiveCore uses the injected encoder.

        If the core constructed RadialEncoder internally, the nonexistent
        source path would fail. The injected encoder ignores that path and
        supplies the expected representation.
        """
        fake_vector = np.full(36, 0.42, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_vector)

        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="/does/not/exist.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder,
            )

            self.assertIs(core.perception_encoder, fake_encoder)
            np.testing.assert_array_equal(
                core.stimulus_representation.vector,
                fake_vector,
            )
            np.testing.assert_array_equal(
                core.stimulus_radial,
                fake_vector,
            )

    def test_backward_compatibility_no_encoder_argument(self):
        """Existing code without perception_encoder argument still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stimulus_file = Path(tmpdir) / "stimulus.txt"
            stimulus_file.write_text(
                " ".join(str(i / 36.0) for i in range(36))
            )

            core = AetherCognitiveCore(
                stimulus_source=str(stimulus_file),
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
            )

            self.assertIsInstance(core.stimulus_representation, Representation)
            self.assertEqual(core.stimulus_representation.encoder_id, "radial")
            self.assertEqual(core.representation_dim, 36)
            self.assertEqual(core.stimulus_radial.shape, (36,))

    def test_current_state_initialized_from_stimulus(self):
        """current_state is initialized from the canonical representation."""
        fake_vector = np.array([0.5] * 36, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_vector)

        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="any_path.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder,
            )

            np.testing.assert_array_equal(core.current_state, fake_vector)
            self.assertIsNot(
                core.current_state,
                core.stimulus_representation.vector,
            )


if __name__ == "__main__":
    unittest.main()
