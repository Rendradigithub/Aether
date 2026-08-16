"""
Focused tests for perception encoder abstraction.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.aether.perception import PerceptionEncoder, RadialEncoder
from src.aether.orchestrator import AetherCognitiveCore


class FakeEncoder(PerceptionEncoder):
    """
    Test encoder that returns a fixed 36-D representation.
    Used to verify that AetherCognitiveCore uses the injected encoder
    rather than constructing RadialEncoder internally.
    """

    def __init__(self, representation=None):
        """
        Initialize with optional custom representation.
        If not provided, returns a deterministic vector.
        """
        if representation is None:
            self.representation = np.linspace(0.1, 0.9, 36, dtype=np.float32)
        else:
            self.representation = representation

    def encode(self, source: str):
        """Return the fixed representation, ignoring source."""
        return self.representation.copy()


class RadialEncoderTest(unittest.TestCase):
    """Tests for RadialEncoder behavior."""

    def test_radial_encoder_text_stimulus_36_values(self):
        """RadialEncoder correctly loads 36-value text stimulus."""
        encoder = RadialEncoder()
        
        # Create temp file with 36 values
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            values = np.linspace(0, 1, 36)
            f.write(' '.join(f"{v:.6f}" for v in values))
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)
            self.assertIsNotNone(result)
            self.assertEqual(len(result), 36)
            self.assertEqual(result.dtype, np.float64)  # Preserve original dtype
            
            # Verify normalization
            expected = values / (np.linalg.norm(values) + 1e-8)
            np.testing.assert_allclose(result, expected, rtol=1e-6)
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
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(' '.join(str(i) for i in range(20)))  # 20 values, not 36
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)
            self.assertIsNone(result)
        finally:
            Path(temp_path).unlink()

    def test_radial_encoder_output_dimension(self):
        """RadialEncoder produces 36-D output."""
        encoder = RadialEncoder()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(' '.join(str(i / 36.0) for i in range(36)))
            temp_path = f.name

        try:
            result = encoder.encode(temp_path)
            self.assertEqual(result.shape, (36,))
        finally:
            Path(temp_path).unlink()


class PerceptionInjectionTest(unittest.TestCase):
    """Tests for perception encoder dependency injection."""

    def test_default_encoder_is_radial(self):
        """AetherCognitiveCore uses RadialEncoder by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stimulus_file = Path(tmpdir) / "stimulus.txt"
            stimulus_file.write_text(' '.join(str(i / 36.0) for i in range(36)))
            
            core = AetherCognitiveCore(
                stimulus_source=str(stimulus_file),
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True
            )
            
            # Should have loaded stimulus via default RadialEncoder
            self.assertIsNotNone(core.stimulus_radial)
            self.assertEqual(len(core.stimulus_radial), 36)

    def test_custom_encoder_is_used(self):
        """AetherCognitiveCore uses the injected encoder, not RadialEncoder."""
        fake_representation = np.array([0.123] * 36, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_representation)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="dummy_path.txt",  # This path is ignored by FakeEncoder
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder
            )
            
            # Verify that the core received the fake encoder's representation
            self.assertIsNotNone(core.stimulus_radial)
            np.testing.assert_array_equal(core.stimulus_radial, fake_representation)

    def test_encoder_injection_proves_usage(self):
        """
        Prove AetherCognitiveCore uses the injected encoder.
        
        If the core were constructing RadialEncoder internally,
        this test would fail because FakeEncoder returns a different vector
        than RadialEncoder would for the same (ignored) source.
        """
        fake_vec = np.full(36, 0.42, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_vec)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a nonexistent path
            core = AetherCognitiveCore(
                stimulus_source="/does/not/exist.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder
            )
            
            # If core used RadialEncoder internally, stimulus_radial would be None
            # (because the path doesn't exist).
            # But with injected FakeEncoder, it should have the fake representation.
            self.assertIsNotNone(core.stimulus_radial)
            np.testing.assert_array_equal(core.stimulus_radial, fake_vec)
            
            # This proves the injected encoder was actually called.

    def test_backward_compatibility_no_encoder_argument(self):
        """Existing code without perception_encoder argument still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stimulus_file = Path(tmpdir) / "stimulus.txt"
            stimulus_file.write_text(' '.join(str(i / 36.0) for i in range(36)))
            
            # Call without perception_encoder argument
            core = AetherCognitiveCore(
                stimulus_source=str(stimulus_file),
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True
                # no perception_encoder specified
            )
            
            self.assertIsNotNone(core.stimulus_radial)
            self.assertEqual(len(core.stimulus_radial), 36)

    def test_current_state_initialized_from_stimulus(self):
        """current_state is initialized from stimulus_radial regardless of encoder."""
        fake_rep = np.array([0.5] * 36, dtype=np.float32)
        fake_encoder = FakeEncoder(representation=fake_rep)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            core = AetherCognitiveCore(
                stimulus_source="any_path.txt",
                workspace=str(Path(tmpdir) / "workspace"),
                quiet=True,
                perception_encoder=fake_encoder
            )
            
            # current_state should be a copy of stimulus_radial
            np.testing.assert_array_equal(core.current_state, fake_rep)
            # Verify it's a copy, not the same object
            self.assertIsNot(core.current_state, core.stimulus_radial)


if __name__ == '__main__':
    unittest.main()
