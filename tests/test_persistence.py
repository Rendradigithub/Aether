import unittest
import tempfile
import pickle
import os
from pathlib import Path
from src.aether.orchestrator import AetherCognitiveCore

class TestPersistence(unittest.TestCase):
    def test_restart_persistence(self):
        """Test persistence restart: run, save, load, and continue."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # We must use a valid stimulus so that it actually steps and populates memory.
            # Create a mock 36-D stimulus file.
            stim_file = Path(temp_dir) / "stim.txt"
            with open(stim_file, "w") as f:
                f.write(" ".join(["0.1"] * 36))
                
            core1 = AetherCognitiveCore(stimulus_source=str(stim_file), quiet=True)
            core1.workspace = Path(temp_dir) / "workspace"
            core1.workspace.mkdir(parents=True, exist_ok=True)
            
            # Need to initialize decoder to save weights
            core1._init_decoder()
            core1.decoder.is_trained = True
            
            for _ in range(3):
                core1.step()
                
            core1.decoder.save_weights(core1.workspace / "decoder_weights.npz")
            
            mem_path = core1.workspace / "memory.pkl"
            with open(mem_path, 'wb') as f:
                pickle.dump(core1.memory, f)
            
            core2 = AetherCognitiveCore(stimulus_source=str(stim_file), quiet=True)
            core2.workspace = core1.workspace
            core2._init_decoder()
            
            weights_path = core2.workspace / "decoder_weights.npz"
            
            core2.decoder.load_weights(weights_path)
            with open(mem_path, 'rb') as f:
                core2.memory = pickle.load(f)
            
            self.assertTrue(core2.decoder.is_trained)
            self.assertIsNotNone(core2.decoder.best_weights)
            self.assertEqual(len(core2.memory.working), len(core1.memory.working))
            
            core2.step()
            self.assertEqual(len(core2.memory.working), len(core1.memory.working) + 1)

if __name__ == '__main__':
    unittest.main()
