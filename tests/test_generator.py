import unittest
import sys
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import runpy
from aether.generator import Generator
from aether.config import HardConfig


class GeneratorRegressionTest(unittest.TestCase):
    """Test Generator behavior matches archive implementation."""
    
    def setUp(self):
        self.archive = runpy.run_path(str(ROOT / "archive" / "versions" / "aether.0.20.0.py"))
    
    def test_initialization_creates_valid_params(self):
        """Test Generator initializes with valid parameter ranges."""
        random.seed(42)
        old = self.archive['Generator']()
        
        random.seed(42)
        new = Generator()
        
        # Check all required params exist
        required_keys = {'pattern', 'symmetry', 'density', 'complexity', 'noise', 'shape_param'}
        self.assertEqual(set(old.params.keys()), required_keys)
        self.assertEqual(set(new.params.keys()), required_keys)
        
        # Check pattern is valid
        self.assertIn(old.params['pattern'], HardConfig.PATTERNS)
        self.assertIn(new.params['pattern'], HardConfig.PATTERNS)
        
        # With same seed, should get same params
        self.assertEqual(old.params, new.params)
    
    def test_blocked_pattern_raises_error(self):
        """Test that blocked patterns raise ValueError."""
        random.seed(42)
        old = self.archive['Generator']()
        
        random.seed(42)
        new = Generator()
        
        blocked = [old.params['pattern']]
        
        with self.assertRaises(ValueError) as old_ctx:
            old.generate(blocked)
        
        with self.assertRaises(ValueError) as new_ctx:
            new.generate(blocked)
        
        self.assertIn(old.params['pattern'], str(old_ctx.exception))
        self.assertIn(new.params['pattern'], str(new_ctx.exception))
    
    def test_generate_returns_tuple(self):
        """Test generate() returns (art_string, pattern_name) tuple."""
        random.seed(123)
        old = self.archive['Generator']()
        
        random.seed(123)
        new = Generator()
        
        old_result = old.generate([])
        new_result = new.generate([])
        
        self.assertIsInstance(old_result, tuple)
        self.assertIsInstance(new_result, tuple)
        self.assertEqual(len(old_result), 2)
        self.assertEqual(len(new_result), 2)
        
        old_art, old_pattern = old_result
        new_art, new_pattern = new_result
        
        self.assertIsInstance(old_art, str)
        self.assertIsInstance(new_art, str)
        self.assertIsInstance(old_pattern, str)
        self.assertIsInstance(new_pattern, str)
        
        # Pattern names should match
        self.assertEqual(old_pattern, new_pattern)
    
    def test_generate_wave_pattern(self):
        """Test wave pattern generation."""
        random.seed(100)
        old = self.archive['Generator']()
        old.set_params({'pattern': 'wave'})
        
        random.seed(100)
        new = Generator()
        new.set_params({'pattern': 'wave'})
        
        random.seed(200)
        old_art, old_pat = old.generate([])
        
        random.seed(200)
        new_art, new_pat = new.generate([])
        
        self.assertEqual(old_pat, 'wave')
        self.assertEqual(new_pat, 'wave')
        
        # Check grid dimensions
        old_lines = old_art.split('\n')
        new_lines = new_art.split('\n')
        
        self.assertEqual(len(old_lines), 18)
        self.assertEqual(len(new_lines), 18)
        
        # With same seed, output should be identical
        self.assertEqual(old_art, new_art)
    
    def test_generate_fractal_pattern(self):
        """Test fractal pattern generation."""
        random.seed(101)
        old = self.archive['Generator']()
        old.set_params({'pattern': 'fractal'})
        
        random.seed(101)
        new = Generator()
        new.set_params({'pattern': 'fractal'})
        
        random.seed(201)
        old_art, old_pat = old.generate([])
        
        random.seed(201)
        new_art, new_pat = new.generate([])
        
        self.assertEqual(old_pat, 'fractal')
        self.assertEqual(new_pat, 'fractal')
        self.assertEqual(old_art, new_art)
    
    def test_generate_cellular_pattern(self):
        """Test cellular automata pattern generation."""
        random.seed(102)
        old = self.archive['Generator']()
        old.set_params({'pattern': 'cellular'})
        
        random.seed(102)
        new = Generator()
        new.set_params({'pattern': 'cellular'})
        
        random.seed(202)
        old_art, old_pat = old.generate([])
        
        random.seed(202)
        new_art, new_pat = new.generate([])
        
        self.assertEqual(old_pat, 'cellular')
        self.assertEqual(new_pat, 'cellular')
        self.assertEqual(old_art, new_art)
    
    def test_generate_lsystem_pattern(self):
        """Test L-system pattern generation."""
        random.seed(103)
        old = self.archive['Generator']()
        old.set_params({'pattern': 'lsystem'})
        
        random.seed(103)
        new = Generator()
        new.set_params({'pattern': 'lsystem'})
        
        random.seed(203)
        old_art, old_pat = old.generate([])
        
        random.seed(203)
        new_art, new_pat = new.generate([])
        
        self.assertEqual(old_pat, 'lsystem')
        self.assertEqual(new_pat, 'lsystem')
        self.assertEqual(old_art, new_art)
    
    def test_generate_shape_pattern_delegates(self):
        """Test shape pattern delegates to ShapeAwareGenerator."""
        random.seed(104)
        old = self.archive['Generator']()
        old.set_params({'pattern': 'shape'})
        
        random.seed(104)
        new = Generator()
        new.set_params({'pattern': 'shape'})
        
        random.seed(204)
        old_art, old_pat = old.generate([])
        
        random.seed(204)
        new_art, new_pat = new.generate([])
        
        self.assertEqual(old_pat, 'shape')
        self.assertEqual(new_pat, 'shape')
        
        # Shape generation should match
        self.assertEqual(old_art, new_art)
    
    def test_set_params_updates_parameters(self):
        """Test set_params() updates generator parameters."""
        old = self.archive['Generator']()
        new = Generator()
        
        params = {'symmetry': 0.9, 'density': 0.8}
        old.set_params(params)
        new.set_params(params)
        
        self.assertEqual(old.params['symmetry'], 0.9)
        self.assertEqual(new.params['symmetry'], 0.9)
        self.assertEqual(old.params['density'], 0.8)
        self.assertEqual(new.params['density'], 0.8)
    
    def test_mutate_respects_bounds(self):
        """Test mutate() keeps parameters within valid bounds."""
        random.seed(300)
        old = self.archive['Generator']()
        old.mutate(intensity=1.0)  # Max intensity for testing
        
        random.seed(300)
        new = Generator()
        new.mutate(intensity=1.0)
        
        # Check bounds
        for key in ['symmetry', 'density', 'complexity', 'noise']:
            self.assertGreaterEqual(old.params[key], 0.05)
            self.assertLessEqual(old.params[key], 0.95)
            self.assertGreaterEqual(new.params[key], 0.05)
            self.assertLessEqual(new.params[key], 0.95)
        
        self.assertGreaterEqual(old.params['shape_param'], 0.0)
        self.assertLessEqual(old.params['shape_param'], 1.0)
        self.assertGreaterEqual(new.params['shape_param'], 0.0)
        self.assertLessEqual(new.params['shape_param'], 1.0)
        
        self.assertIn(old.params['pattern'], HardConfig.PATTERNS)
        self.assertIn(new.params['pattern'], HardConfig.PATTERNS)
        
        # With same seed, mutations should match
        self.assertEqual(old.params, new.params)
    
    def test_crossover_with_memory(self):
        """Test crossover_with_memory() averages numeric parameters."""
        random.seed(400)
        old = self.archive['Generator']()
        old.set_params({'symmetry': 0.8, 'density': 0.6, 'pattern': 'wave'})
        
        random.seed(400)
        new = Generator()
        new.set_params({'symmetry': 0.8, 'density': 0.6, 'pattern': 'wave'})
        
        memory = {'symmetry': 0.4, 'density': 0.8, 'pattern': 'fractal'}
        
        random.seed(500)
        old.crossover_with_memory(memory)
        
        random.seed(500)
        new.crossover_with_memory(memory)
        
        # Numeric values should be averaged
        self.assertEqual(old.params['symmetry'], (0.8 + 0.4) / 2.0)
        self.assertEqual(new.params['symmetry'], (0.8 + 0.4) / 2.0)
        self.assertEqual(old.params['density'], (0.6 + 0.8) / 2.0)
        self.assertEqual(new.params['density'], (0.6 + 0.8) / 2.0)
        
        # Pattern crossover is random, with same seed should match
        self.assertEqual(old.params['pattern'], new.params['pattern'])
    
    def test_grid_dimensions_consistent(self):
        """Test all generated art has consistent grid dimensions."""
        patterns_to_test = ['wave', 'fractal', 'cellular', 'lsystem']
        
        for i, pattern in enumerate(patterns_to_test):
            with self.subTest(pattern=pattern):
                random.seed(600 + i)
                old = self.archive['Generator']()
                old.set_params({'pattern': pattern})
                
                random.seed(600 + i)
                new = Generator()
                new.set_params({'pattern': pattern})
                
                random.seed(700 + i)
                old_art, _ = old.generate([])
                
                random.seed(700 + i)
                new_art, _ = new.generate([])
                
                old_lines = old_art.split('\n')
                new_lines = new_art.split('\n')
                
                # Should be 18 lines
                self.assertEqual(len(old_lines), 18)
                self.assertEqual(len(new_lines), 18)
                
                # Each line should be <= 52 chars (may be shorter due to rstrip)
                for line in old_lines:
                    self.assertLessEqual(len(line), 52)
                for line in new_lines:
                    self.assertLessEqual(len(line), 52)


if __name__ == '__main__':
    unittest.main()
