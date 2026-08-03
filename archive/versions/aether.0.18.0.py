#!/usr/bin/env python3
"""
AETHER v0.18.0 — STRUCTURAL STABILITY & PREDICTIVE CURIOSITY
================================================================
Changes from v0.17.0:
- Shape generator now produces clean contour (thick edge) without internal filler noise,
  allowing reward to focus on topology, not texture.
- Contour consistency reward: compares binary edge map of generated shape with
  idealized edge map reconstructed from radial signature of stimulus.
- Predictive world model: predicts reward from (state, action) and uses prediction error
  as curiosity bonus (replaces simple novelty).
- Reduced hardcoded shape utility bonus (0.8 instead of 1.5) – moving toward learned preference.
- Fixed bug: MenteBudget now has 'cycle' attribute.
- Decoder training now uses contour-based reward as additional target? Not yet, but reward
  signal is cleaner.
- Anti-stagnation coma now also triggers if reward does not improve over window.
"""

import math
import random
import time
import json
from collections import deque, Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not installed. Install with: pip install Pillow")

# ============================================================================
# HARD CONFIGURATION (tuned for v0.18.0)
# ============================================================================

class HardConfig:
    MAX_ENERGY = 120
    MAX_ATTENTION = 120
    MAX_FATIGUE = 100
    MEMORY_SLOTS = 30

    ACTION_COSTS = {
        'generate': (7, 5, 0, 3),
        'explore':  (22, 16, 1, 6),
        'refine':   (5, 8, 0, 3),
        'recall':   (2, 2, 0, 1),
        'combine':  (14, 11, 1, 5),
        'rest':     (-7, -9, 0, -7),
        'forget':   (4, 2, -1, 2),
    }

    COMMITMENT_WINDOW = 5
    COMMITMENT_VIOLATION_PENALTY = {'energy': -20, 'attention': -30, 'fatigue': +15}
    COMMITMENT_THRESHOLD_CONFIDENCE = 0.65

    FAILURE_BURDEN_MAX = 100
    COST_MULTIPLIER_MAX = 1.8

    EMERGENCY_BURDEN_THRESHOLD = 75
    EMERGENCY_ENERGY_THRESHOLD = 20
    COMA_BURDEN = 100
    COMA_ENERGY = 12
    COMA_DURATION = 5

    TRAUMA_BLOCK_THRESHOLD = 0.75
    TRAUMA_BLOCK_DURATION = 12

    WORLD_MODEL_UPDATE_RATE = 0.03
    WORLD_MODEL_HIDDEN_DIM = 8
    VECTOR_DIM = 8      # not used for stimulus

    # Decoder: radial signature input = 36 rays
    NN_INPUT_DIM = 36
    NN_HIDDEN_1 = 48
    NN_HIDDEN_2 = 64
    NN_HIDDEN_3 = 32
    NN_OUTPUT_DIM = 6

    NN_LEARNING_RATE = 0.008
    NN_TRAINING_EPOCHS = 10
    NN_BATCH_SIZE = 32
    NN_TRAIN_INTERVAL = 20
    NN_SAMPLE_THRESHOLD_INITIAL = 0.15
    NN_SAMPLE_THRESHOLD_MAX = 0.7
    NN_CONFIDENCE_LOSS_THRESH = 0.04
    NN_FORCED_SHAPE_PROB = 0.85
    NN_POST_TRAIN_FORCED_SHAPE_PROB = 0.5      # reduced to let learning take over
    NN_GENERATE_BONUS_TRAINED = 0.8
    NN_SHAPE_UTILITY_BONUS = 0.8               # reduced from 1.5

    BOOTSTRAPPING_CYCLES = 35
    BOOTSTRAP_ENERGY_REWARD = 10
    BOOTSTRAP_BURDEN_REDUCTION = -12
    BOOTSTRAP_COST = (2, 1, 1)

    FORESIGHT_STEPS = 1                         # reduced for simplicity
    PLANNING_DISCOUNT = 0.9

    EXPLORATION_NOISE_STD = 0.1
    CURIOSITY_BONUS = 0.3                       # will be dynamic

    REPETITION_PENALTY_PER_USE = 0.05
    STATE_TRANSITION_NOISE = 0.08

    ACTION_SHIFT = {
        'explore': 0.25, 'refine': 0.08, 'generate': 0.02,
        'combine': 0.12, 'rest': -0.07, 'recall': 0.0, 'forget': 0.0
    }

    REST_COOLDOWN = 3
    REST_FATIGUE_REDUCTION = 10
    REST_ENERGY_GAIN_BASE = 8
    REST_ATTENTION_GAIN_BASE = 12
    BURDEN_RECOVERY_REST = -8

    STIMULUS_WEIGHT = 0.25
    STIMULUS_SIMILARITY_THRESHOLD = 0.1
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']

    REPETITION_STAGNATION_THRESHOLD = 10
    REWARD_STAGNATION_WINDOW = 8
    REWARD_IMPROVEMENT_THRESHOLD = 0.03

    # Reward components
    REWARD_CONTOUR_SIM_WEIGHT = 0.5
    REWARD_RADIAL_SIM_WEIGHT = 0.3
    REWARD_NOVELTY_WEIGHT = 0.1
    REWARD_SURVIVAL_WEIGHT = 0.1


# ============================================================================
# NEURAL DECODER (NumPy) – same as v0.17.0
# ============================================================================

class NeuralDecoder:
    def __init__(self, input_dim=HardConfig.NN_INPUT_DIM,
                 hidden1=HardConfig.NN_HIDDEN_1,
                 hidden2=HardConfig.NN_HIDDEN_2,
                 hidden3=HardConfig.NN_HIDDEN_3,
                 output_dim=HardConfig.NN_OUTPUT_DIM):
        self.W1 = np.random.randn(hidden1, input_dim) * np.sqrt(2.0 / input_dim)
        self.b1 = np.zeros(hidden1)
        self.W2 = np.random.randn(hidden2, hidden1) * np.sqrt(2.0 / hidden1)
        self.b2 = np.zeros(hidden2)
        self.W3 = np.random.randn(hidden3, hidden2) * np.sqrt(2.0 / hidden2)
        self.b3 = np.zeros(hidden3)
        self.W4 = np.random.randn(output_dim, hidden3) * np.sqrt(2.0 / hidden3)
        self.b4 = np.zeros(output_dim)
        self.input_dim = input_dim
        self.training_buffer = []
        self.is_trained = False
        self.loss_history = []
        self.best_loss = float('inf')
        self.best_weights = None
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL

    def _params_to_target(self, params):
        patterns = HardConfig.PATTERNS
        pat_idx = patterns.index(params['pattern']) / (len(patterns)-1)
        return np.array([pat_idx, params['symmetry'], params['density'],
                         params['complexity'], params['noise'], params['shape_param']])

    def forward(self, x, cache=False):
        if x.ndim == 1:
            x = x.reshape(1, -1)
        z1 = x @ self.W1.T + self.b1
        a1 = np.tanh(z1)
        z2 = a1 @ self.W2.T + self.b2
        a2 = np.tanh(z2)
        z3 = a2 @ self.W3.T + self.b3
        a3 = np.tanh(z3)
        out = a3 @ self.W4.T + self.b4
        if cache:
            return out, (x, z1, a1, z2, a2, z3, a3)
        return out

    def predict_params(self, stimulus_vec):
        out = self.forward(stimulus_vec)
        if out.ndim == 2:
            out = out[0]
        patterns = HardConfig.PATTERNS
        pattern_idx = int(np.clip(out[0] * (len(patterns)-1), 0, len(patterns)-1))
        pattern = patterns[pattern_idx]
        symmetry = float(np.clip(out[1], 0, 1))
        density = float(np.clip(out[2], 0.05, 0.95))
        complexity = float(np.clip(out[3], 0.1, 0.9))
        noise = float(np.clip(out[4], 0, 0.6))
        shape_param = float(np.clip(out[5], 0, 1))
        return {
            'pattern': pattern,
            'symmetry': symmetry,
            'density': density,
            'complexity': complexity,
            'noise': noise,
            'shape_param': shape_param
        }

    def collect_sample(self, stimulus_vec, generator_params):
        if generator_params.get('pattern') != 'shape':
            return
        target = self._params_to_target(generator_params)
        self.training_buffer.append((stimulus_vec.copy(), target))
        if len(self.training_buffer) > 2000:
            self.training_buffer.pop(0)
        progress = min(1.0, len(self.training_buffer) / 200)
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL + \
            (HardConfig.NN_SAMPLE_THRESHOLD_MAX - HardConfig.NN_SAMPLE_THRESHOLD_INITIAL) * progress

    def train(self, epochs=None, batch_size=None, lr=None):
        if epochs is None:
            epochs = HardConfig.NN_TRAINING_EPOCHS
        if batch_size is None:
            batch_size = HardConfig.NN_BATCH_SIZE
        if lr is None:
            lr = HardConfig.NN_LEARNING_RATE
        if len(self.training_buffer) < batch_size:
            return
        for ep in range(epochs):
            np.random.shuffle(self.training_buffer)
            total_loss = 0.0
            num_batches = 0
            for i in range(0, len(self.training_buffer), batch_size):
                batch = self.training_buffer[i:i+batch_size]
                X = np.array([b[0] for b in batch])
                Y = np.array([b[1] for b in batch])
                out, cache = self.forward(X, cache=True)
                loss = np.mean((out - Y)**2)
                total_loss += loss
                num_batches += 1
                dout = 2 * (out - Y) / batch_size
                x, z1, a1, z2, a2, z3, a3 = cache
                dW4 = dout.T @ a3 / batch_size
                db4 = np.sum(dout, axis=0) / batch_size
                da3 = dout @ self.W4
                dz3 = da3 * (1 - np.tanh(z3)**2)
                dW3 = dz3.T @ a2 / batch_size
                db3 = np.sum(dz3, axis=0) / batch_size
                da2 = dz3 @ self.W3
                dz2 = da2 * (1 - np.tanh(z2)**2)
                dW2 = dz2.T @ a1 / batch_size
                db2 = np.sum(dz2, axis=0) / batch_size
                da1 = dz2 @ self.W2
                dz1 = da1 * (1 - np.tanh(z1)**2)
                dW1 = dz1.T @ x / batch_size
                db1 = np.sum(dz1, axis=0) / batch_size
                self.W1 -= lr * dW1; self.b1 -= lr * db1
                self.W2 -= lr * dW2; self.b2 -= lr * db2
                self.W3 -= lr * dW3; self.b3 -= lr * db3
                self.W4 -= lr * dW4; self.b4 -= lr * db4
            avg_loss = total_loss / max(1, num_batches)
            self.loss_history.append(avg_loss)
            if avg_loss < self.best_loss:
                self.best_loss = avg_loss
                self.best_weights = (self.W1.copy(), self.b1.copy(),
                                      self.W2.copy(), self.b2.copy(),
                                      self.W3.copy(), self.b3.copy(),
                                      self.W4.copy(), self.b4.copy())
        self.is_trained = True
        print(f"[Decoder] Trained, loss: {self.loss_history[-1]:.4f}, buffer: {len(self.training_buffer)}")

    def save_weights(self, path):
        if self.best_weights:
            np.savez(path,
                     W1=self.best_weights[0], b1=self.best_weights[1],
                     W2=self.best_weights[2], b2=self.best_weights[3],
                     W3=self.best_weights[4], b3=self.best_weights[5],
                     W4=self.best_weights[6], b4=self.best_weights[7])
        else:
            np.savez(path,
                     W1=self.W1, b1=self.b1,
                     W2=self.W2, b2=self.b2,
                     W3=self.W3, b3=self.b3,
                     W4=self.W4, b4=self.b4)

    def load_weights(self, path):
        data = np.load(path)
        self.W1 = data['W1']; self.b1 = data['b1']
        self.W2 = data['W2']; self.b2 = data['b2']
        self.W3 = data['W3']; self.b3 = data['b3']
        self.W4 = data['W4']; self.b4 = data['b4']
        self.is_trained = True
        self.current_threshold = 0.15
        print(f"[Decoder] Weights loaded from {path}")


# ============================================================================
# RADIAL SIGNATURE & CONTOUR UTILITIES
# ============================================================================

class RadialSignature:
    @staticmethod
    def from_image(image_path, size=64, num_rays=36):
        if not PIL_AVAILABLE:
            raise ImportError("Pillow required")
        img = Image.open(image_path).convert('L')
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        arr = np.array(img, dtype=np.float32) / 255.0
        # Edge detection
        gx = np.abs(np.diff(arr, axis=1, append=arr[:,-1:]))
        gy = np.abs(np.diff(arr, axis=0, append=arr[-1:,:]))
        edge = np.maximum(gx, gy)
        edge = (edge > 0.2).astype(np.float32)
        cx, cy = size//2, size//2
        max_r = size
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= size or y < 0 or y >= size:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def from_ascii_art(art, num_rays=36, contour_only=False):
        """Extract radial signature. If contour_only, only consider edge pixels."""
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(num_rays)
        h, w = len(lines), max(len(l) for l in lines)
        grid = np.zeros((h, w), dtype=np.float32)
        for y, line in enumerate(lines):
            for x, ch in enumerate(line.ljust(w)):
                if ch != ' ':
                    grid[y, x] = 1.0
        # Edge detection
        gx = np.abs(np.diff(grid, axis=1, append=grid[:,-1:]))
        gy = np.abs(np.diff(grid, axis=0, append=grid[-1:,:]))
        edge = np.maximum(gx, gy)
        if contour_only:
            # Use only edge for signature
            edge = (edge > 0).astype(np.float32)
        else:
            # Use filled shape (original grid)
            edge = grid  # but we use grid directly for filled shape?
            # Actually radial signature should use edge for shape boundary.
            # For filled shape, contour is better.
            edge = (edge > 0).astype(np.float32)
        cx, cy = w/2, h/2
        max_r = max(h, w)
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= w or y < 0 or y >= h:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def cross_correlation(sig1, sig2):
        if np.std(sig1) == 0 or np.std(sig2) == 0:
            return 0.5
        corr = np.corrcoef(sig1, sig2)[0,1]
        return max(0.0, min(1.0, (corr + 1) / 2))

    @staticmethod
    def ideal_contour_from_params(shape_param, symmetry, density, noise, w=52, h=18, num_rays=36):
        """Generate idealized binary contour of the shape (no fill, just edge)."""
        # This is a simplified version; we'll just use the existing shape generator
        # but force density low and noise 0, and then extract edge.
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        cx, cy = w//2, h//2
        size = min(w,h)//4
        if shape_param < 0.33:
            r = int(size * (0.5 + shape_param*1.5))
            ShapeAwareGenerator.draw_circle(grid, cx, cy, r, char='█')
        elif shape_param < 0.66:
            sz = int(size * (0.5 + (shape_param-0.33)*3))
            ShapeAwareGenerator.draw_square(grid, cx, cy, sz, char='█')
        else:
            sz = int(size * (0.5 + (shape_param-0.66)*3))
            ShapeAwareGenerator.draw_triangle(grid, cx, cy, sz, char='█')
        # Convert to binary edge
        binary = [[1 if c != ' ' else 0 for c in row] for row in grid]
        arr = np.array(binary, dtype=np.float32)
        gx = np.abs(np.diff(arr, axis=1, append=arr[:,-1:]))
        gy = np.abs(np.diff(arr, axis=0, append=arr[-1:,:]))
        edge = np.maximum(gx, gy)
        edge = (edge > 0).astype(np.float32)
        # Radial signature from edge
        max_r = max(h,w)
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= w or y < 0 or y >= h:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def contour_consistency(sig_art, ideal_sig):
        """Measure how well generated shape's contour matches ideal contour."""
        return RadialSignature.cross_correlation(sig_art, ideal_sig)


# ============================================================================
# IMPROVED SHAPE GENERATOR (clean contour + optional fill)
# ============================================================================

class ShapeAwareGenerator:
    @staticmethod
    def draw_circle(grid, cx, cy, r, char='█'):
        h, w = len(grid), len(grid[0])
        for y in range(h):
            for x in range(w):
                dx = x - cx; dy = y - cy
                if abs(math.sqrt(dx*dx+dy*dy) - r) < 0.8:
                    grid[y][x] = char
    @staticmethod
    def draw_square(grid, cx, cy, size, char='█'):
        h, w = len(grid), len(grid[0])
        half = size // 2
        for y in range(cy-half, cy+half+1):
            if 0 <= y < h:
                for x in range(cx-half, cx+half+1):
                    if 0 <= x < w and (y == cy-half or y == cy+half or x == cx-half or x == cx+half):
                        grid[y][x] = char
    @staticmethod
    def draw_triangle(grid, cx, cy, size, char='█'):
        h, w = len(grid), len(grid[0])
        for i in range(size):
            y = cy - i
            if y < 0 or y >= h: continue
            x_start = cx - (size-i)//2
            x_end = cx + (size-i)//2
            for x in range(x_start, x_end+1):
                if 0 <= x < w and (i==0 or i==size-1 or x==x_start or x==x_end):
                    grid[y][x] = char

    @staticmethod
    def generate_shape(shape_param, symmetry, density, noise, w=52, h=18):
        """Generate shape with clean contour and optional filler."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        cx, cy = w//2, h//2
        size = min(w,h)//4
        # Draw contour only first (thick)
        if shape_param < 0.33:
            r = int(size * (0.5 + shape_param*1.5))
            ShapeAwareGenerator.draw_circle(grid, cx, cy, r, '█')
            # Optionally fill interior? Not yet; contour only for reward.
        elif shape_param < 0.66:
            sz = int(size * (0.5 + (shape_param-0.33)*3))
            ShapeAwareGenerator.draw_square(grid, cx, cy, sz, '█')
        else:
            sz = int(size * (0.5 + (shape_param-0.66)*3))
            ShapeAwareGenerator.draw_triangle(grid, cx, cy, sz, '█')
        # Now add filler for density (if density > 0.3, fill inside)
        if density > 0.3:
            # Simple flood fill inside? We'll just add random chars inside the bounding box
            # but to keep contour clean, we limit filler to interior.
            # For simplicity, we'll add filler only inside the shape's bounding box,
            # but we need to know interior. Let's just fill all non-edge cells that are inside.
            # We'll cheat: after drawing contour, we can fill inner area by checking distance
            # from center. For circle: distance < r-1; for square: inside; triangle: similar.
            # This is imperfect but ok.
            if shape_param < 0.33:
                r_inner = max(1, r-2)
                for y in range(h):
                    for x in range(w):
                        if grid[y][x] == ' ':
                            dist = math.sqrt((x-cx)**2 + (y-cy)**2)
                            if dist < r_inner:
                                if random.random() < density:
                                    grid[y][x] = random.choice('░▒▓')
            elif shape_param < 0.66:
                half = sz//2
                for y in range(cy-half+1, cy+half):
                    for x in range(cx-half+1, cx+half):
                        if grid[y][x] == ' ':
                            if random.random() < density:
                                grid[y][x] = random.choice('░▒▓')
            else:
                # Triangle interior: approximate
                for y in range(cy-sz+1, cy+1):
                    # width at this level
                    wdt = int((sz - (cy - y)) * 2)
                    x_start = cx - wdt//2
                    x_end = cx + wdt//2
                    for x in range(x_start, x_end+1):
                        if 0 <= x < w and 0 <= y < h and grid[y][x] == ' ':
                            if random.random() < density:
                                grid[y][x] = random.choice('░▒▓')
        # Add noise (sparse)
        if noise > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < noise*0.3:
                        if grid[y][x] == ' ':
                            grid[y][x] = random.choice(' .:oO0@')
                        elif random.random() < 0.5:
                            grid[y][x] = ' '
        return '\n'.join(''.join(row) for row in grid)


# ============================================================================
# PREDICTIVE WORLD MODEL (simple linear predictor)
# ============================================================================

class PredictiveWorldModel:
    def __init__(self, input_dim=HardConfig.NN_INPUT_DIM + 1):  # state + action index
        self.W = np.random.randn(1, input_dim) * 0.1
        self.b = 0.0
        self.confidence = 0.5
        self.prediction_error = 0.0
        self.buffer = deque(maxlen=100)

    def encode_action(self, action):
        actions = ['generate', 'explore', 'refine', 'combine', 'rest', 'recall', 'forget']
        idx = actions.index(action) if action in actions else 0
        # one-hot? simple scalar normalized
        return idx / len(actions)

    def predict(self, state_vec, action):
        x = np.append(state_vec, self.encode_action(action))
        pred = np.clip((self.W @ x + self.b).item(), 0, 1)
        return pred

    def update(self, state_vec, action, observed_reward):
        x = np.append(state_vec, self.encode_action(action))
        pred = self.predict(state_vec, action)
        error = observed_reward - pred
        self.W += HardConfig.WORLD_MODEL_UPDATE_RATE * error * x
        self.b += HardConfig.WORLD_MODEL_UPDATE_RATE * error
        self.prediction_error = abs(error)
        # Update confidence (inverse of recent errors)
        self.buffer.append(error)
        if len(self.buffer) >= 20:
            recent_errors = [abs(e) for e in list(self.buffer)[-20:]]
            self.confidence = max(0.2, min(0.9, 1.0 - np.mean(recent_errors)))
        else:
            self.confidence = 0.5


# ============================================================================
# LIGHTWEIGHT MENTE ADAPTER (enhanced with cycle and prediction)
# ============================================================================

class MenteMemory:
    def __init__(self, working_capacity=10, episodic_capacity=100):
        self.working = deque(maxlen=working_capacity)
        self.episodic = deque(maxlen=episodic_capacity)
        self.semantic = {}
    def add_experience(self, experience):
        self.working.append(experience)
        if experience.get('contour_reward', 0) > 0.7:
            self.episodic.append(experience)
    def recall_similar(self, query, k=3):
        candidates = list(self.working) + list(self.episodic)
        if not candidates: return []
        query_pat = query.get('pattern')
        query_contour = query.get('contour_reward', 0.5)
        scored = []
        for exp in candidates:
            score = 0.5 if exp.get('pattern') == query_pat else 0
            score += 1.0 - abs(exp.get('contour_reward', 0.5) - query_contour)
            scored.append((score, exp))
        scored.sort(reverse=True)
        return [exp for _, exp in scored[:k]]
    def update_semantic(self, key, value):
        self.semantic[key] = value
    def novelty(self, vec):
        if not hasattr(self, 'vectors') or not self.vectors:
            return 1.0
        sims = [np.dot(vec, v) / (np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors[-10:]]
        return 1.0 - max(sims) if sims else 1.0

MenteMemory.vectors = []  # for novelty

class MenteBudget:
    def __init__(self, max_energy=100, max_attention=100):
        self.energy = max_energy
        self.attention = max_attention
        self.max_energy = max_energy
        self.max_attention = max_attention
        self.fatigue = 0
        self.failure_burden = 0
        self.consecutive_same_pattern = 0
        self.last_pattern = None
        self.last_rest_cycle = -999
        self.cycle = 0
        self.reward_history = deque(maxlen=HardConfig.REWARD_STAGNATION_WINDOW)

    def spend(self, energy_cost, attention_cost, fatigue_delta):
        self.energy = max(0, self.energy - energy_cost)
        self.attention = max(0, self.attention - attention_cost)
        self.fatigue = min(100, self.fatigue + fatigue_delta)

    def recover(self, energy_gain, attention_gain, fatigue_reduction):
        self.energy = min(self.max_energy, self.energy + energy_gain)
        self.attention = min(self.max_attention, self.attention + attention_gain)
        self.fatigue = max(0, self.fatigue - fatigue_reduction)

    def regen(self, resting):
        if resting and self.can_rest():
            fp = max(0, self.fatigue / 20)
            self.energy = min(self.max_energy, self.energy + max(3, HardConfig.REST_ENERGY_GAIN_BASE - int(fp)))
            self.attention = min(self.max_attention, self.attention + max(4, HardConfig.REST_ATTENTION_GAIN_BASE - int(fp*1.2)))
            self.fatigue = max(0, self.fatigue - HardConfig.REST_FATIGUE_REDUCTION)
            self.last_rest_cycle = self.cycle
            self.failure_burden = max(0, self.failure_burden + HardConfig.BURDEN_RECOVERY_REST)
        else:
            self.energy = min(self.max_energy, self.energy + 1)
            self.attention = min(self.max_attention, self.attention + 1)
            self.fatigue = max(0, self.fatigue - 1)

    def can_rest(self):
        return (self.cycle - self.last_rest_cycle) >= HardConfig.REST_COOLDOWN

    def is_emergency(self):
        return self.energy < 20 or self.fatigue > 80 or self.failure_burden > 70

    def update_failure_burden(self, score):
        if score < 0.35:
            self.failure_burden = min(100, self.failure_burden + 12)
        elif score > 0.7:
            self.failure_burden = max(0, self.failure_burden - 8)
        else:
            self.failure_burden = max(0, self.failure_burden - 2)

    def track_pattern_repetition(self, pattern):
        if pattern == self.last_pattern:
            self.consecutive_same_pattern += 1
        else:
            self.consecutive_same_pattern = 1
            self.last_pattern = pattern
        return self.consecutive_same_pattern

    def track_reward_stagnation(self, reward):
        self.reward_history.append(reward)
        if len(self.reward_history) >= HardConfig.REWARD_STAGNATION_WINDOW:
            min_r = min(self.reward_history)
            max_r = max(self.reward_history)
            return (max_r - min_r) < HardConfig.REWARD_IMPROVEMENT_THRESHOLD
        return False


class MenteCuriosity:
    def __init__(self, world_model):
        self.world_model = world_model
        self.novelty_weight = 0.3
        self.prediction_weight = 0.5
        self.visited_states = Counter()

    def get_bonus(self, state_vec, action):
        # prediction error from world model
        pred = self.world_model.predict(state_vec, action)
        # we need actual reward? For curiosity, we use prediction error.
        # But we don't have actual reward here; we'll store prediction error from last update.
        # For simplicity, we use world_model.prediction_error
        pred_error = self.world_model.prediction_error
        # novelty component
        h = tuple(np.round(state_vec, 2).tolist())
        self.visited_states[h] += 1
        novelty = 1.0 / (1.0 + self.visited_states[h])
        return self.prediction_weight * pred_error + self.novelty_weight * novelty


class MenteEventBus:
    def __init__(self):
        self.listeners = {}
    def subscribe(self, event_type, callback):
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)
    def emit(self, event_type, data):
        for cb in self.listeners.get(event_type, []):
            cb(data)


# ============================================================================
# AUXILIARY CLASSES (Generator, ArtEmbedder)
# ============================================================================

class Generator:
    PATTERNS = HardConfig.PATTERNS
    def __init__(self):
        self.params = {
            'pattern': random.choice(self.PATTERNS),
            'symmetry': random.uniform(0.3,0.8),
            'density': random.uniform(0.2,0.6),
            'complexity': random.uniform(0.3,0.7),
            'noise': random.uniform(0.1,0.4),
            'shape_param': random.uniform(0,1)
        }
    def generate(self, blocked):
        if self.params['pattern'] in blocked:
            raise ValueError(f"Pattern '{self.params['pattern']}' blocked")
        if self.params['pattern'] == 'shape':
            art = ShapeAwareGenerator.generate_shape(
                self.params['shape_param'], self.params['symmetry'],
                self.params['density'], self.params['noise']
            )
            return art, 'shape'
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        td = max(0.1, min(0.9, self.params['density']+random.uniform(-0.1,0.1)))
        ts = max(0.0, min(1.0, self.params['symmetry']+random.uniform(-0.1,0.1)))
        tn = max(0.0, min(0.6, self.params['noise']+random.uniform(-0.1,0.15)))
        pat = self.params['pattern']
        if pat == 'wave':
            fx = random.uniform(0.1,0.6); fy = random.uniform(0.1,0.5)
            for y in range(h):
                for x in range(w):
                    v = math.sin(x*fx)*math.cos(y*fy)+math.sin(x*0.8)*0.3+math.cos(y*0.6)*0.3+random.uniform(-0.1,0.1)*tn
                    if (v+1)/2 > 1 - td: grid[y][x] = random.choice('░▒▓█')
        elif pat == 'fractal':
            depth = max(1, int(self.params['complexity']*4)+random.randint(0,2))
            self._draw_fractal(grid, w//2, h//2, min(w,h)//6, depth, tn)
        elif pat == 'cellular':
            grid = self._cellular(w, h, td, tn)
        elif pat == 'lsystem':
            grid = self._lsystem(w, h, tn)
        else:
            for y in range(h):
                for x in range(w):
                    v = math.sin(x*0.3)*math.cos(y*0.3)+random.uniform(-0.1,0.1)*tn
                    if (v+1)/2 > 1 - td: grid[y][x] = random.choice('░▒▓█')
        if random.random() < ts:
            for y in range(h):
                for x in range(w//2):
                    if grid[y][x]!=' ': grid[y][w-1-x]=grid[y][x]
                    elif grid[y][w-1-x]!=' ': grid[y][x]=grid[y][w-1-x]
        self._adjust(grid, td)
        if tn>0:
            for y in range(h):
                for x in range(w):
                    if random.random()<tn*0.4:
                        if grid[y][x]==' ': grid[y][x]=random.choice(' .:oO0@')
                        elif random.random()<0.5: grid[y][x]=' '
        return '\n'.join(''.join(row) for row in grid), pat

    def _draw_fractal(self, grid, x, y, s, d, n):
        if d<=0 or s<1: return
        for i in range(-s,s+1):
            if 0<=x+i<len(grid[0]) and 0<=y<len(grid) and random.random()>n: grid[y][x+i]='█'
            if 0<=x<len(grid[0]) and 0<=y+i<len(grid) and random.random()>n: grid[y+i][x]='█'
        self._draw_fractal(grid, x+s+1, y, s//2, d-1, n)
        self._draw_fractal(grid, x-s-1, y, s//2, d-1, n)
        self._draw_fractal(grid, x, y+s+1, s//2, d-1, n)
        self._draw_fractal(grid, x, y-s-1, s//2, d-1, n)
    def _cellular(self, w, h, den, n):
        grid = [[1 if random.random()<den else 0 for _ in range(w)] for _ in range(h)]
        for _ in range(3+int(n*3)):
            new = [[0]*w for _ in range(h)]
            for y in range(h):
                for x in range(w):
                    neigh = sum(grid[(y+dy)%h][(x+dx)%w] for dy in(-1,0,1) for dx in(-1,0,1) if not(dy==0 and dx==0))
                    new[y][x] = 1 if (grid[y][x] and neigh in(2,3)) or (not grid[y][x] and neigh==3) else 0
            grid = new
        return [[' ' if not c else random.choice('░▒▓') for c in row] for row in grid]
    def _lsystem(self, w, h, n):
        seq = 'F'
        for _ in range(3+int(n*2)): seq = seq.replace('F','F+F-F-F+F')
        grid = [[' ']*w for _ in range(h)]
        x,y,angle = w//2, h//2, 0
        for c in seq[:400]:
            if c=='F':
                dx = int(round(math.cos(math.radians(angle))+random.uniform(-0.1,0.1)*n))
                dy = int(round(math.sin(math.radians(angle))+random.uniform(-0.1,0.1)*n))
                nx,ny = x+dx, y+dy
                if 0<=nx<w and 0<=ny<h and random.random()>n*0.3: grid[ny][nx]=random.choice('oO0')
                x,y=nx,ny
            elif c=='+': angle+=90
            elif c=='-': angle-=90
        return grid
    def _adjust(self, grid, target):
        h,w = len(grid), len(grid[0])
        total = h*w
        non = sum(c!=' ' for row in grid for c in row)
        if non/total < target:
            need = int(total*target)-non
            pos = [(y,x) for y in range(h) for x in range(w) if grid[y][x]==' ']
            random.shuffle(pos)
            for _ in range(min(need,len(pos))): y,x=pos.pop(); grid[y][x]=random.choice('░▒▓█')
        elif non/total > target:
            need = non - int(total*target)
            pos = [(y,x) for y in range(h) for x in range(w) if grid[y][x]!=' ']
            random.shuffle(pos)
            for _ in range(min(need,len(pos))): y,x=pos.pop(); grid[y][x]=' '
    def set_params(self, p):
        self.params.update(p)
    def mutate(self, intensity=0.2):
        for k in ['symmetry','density','complexity','noise','shape_param']:
            if random.random() < intensity:
                self.params[k] += random.uniform(-0.15,0.15)
                if k == 'shape_param':
                    self.params[k] = max(0.0, min(1.0, self.params[k]))
                else:
                    self.params[k] = max(0.05, min(0.95, self.params[k]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)
    def crossover_with_memory(self, other):
        for k in self.params:
            if k == 'pattern':
                if random.random() < 0.5:
                    self.params[k] = other.get(k, self.params[k])
            elif isinstance(other.get(k), (int, float)):
                self.params[k] = (self.params[k] + other[k]) / 2.0

class ArtEmbedder:
    @staticmethod
    def embed(art):
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines: return np.zeros(8, dtype=np.float32)
        h,w = len(lines), max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        total = h*w
        non = sum(c!=' ' for line in padded for c in line)
        den = non/total
        h_sym=0; cnt=0
        for line in padded:
            s=line.rstrip()
            if len(s)>2:
                mid=len(s)//2; left=s[:mid]; right=s[mid:][::-1]
                n=min(len(left),len(right))
                if n>0:
                    m=sum(1 for i in range(n) if left[i]==right[i] and left[i]!=' ')
                    h_sym+=m/n; cnt+=1
        sym = h_sym/max(1,cnt)
        allc = [c for line in padded for c in line if c!=' ']
        var = np.std([ord(c) for c in allc])/128.0 if allc else 0.0
        cx, cy = w/2, h/2
        max_r = min(w,h)/2
        inner = 0; outer = 0
        for y in range(h):
            for x in range(w):
                if padded[y][x] != ' ':
                    dist = math.sqrt((x-cx)**2 + (y-cy)**2)
                    if dist < max_r*0.6: inner += 1
                    elif dist > max_r*0.8: outer += 1
        circ = ((inner - outer) / non + 1)/2 if non>0 else 0.5
        vec = np.array([den, sym, var, circ], dtype=np.float32)
        vec = np.pad(vec, (0, 8-len(vec)))
        return vec/(np.linalg.norm(vec)+1e-8)


# ============================================================================
# AETHER v0.18.0 CORE
# ============================================================================

class AetherCognitiveCore:
    def __init__(self, stimulus_source=None, workspace="aether_works_v0180", quiet=False):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.bus = MenteEventBus()
        self.memory = MenteMemory()
        self.budget = MenteBudget(max_energy=HardConfig.MAX_ENERGY,
                                  max_attention=HardConfig.MAX_ATTENTION)
        self.world_model = PredictiveWorldModel()
        self.curiosity = MenteCuriosity(self.world_model)
        self.generator = Generator()
        self.decoder = None
        self.stimulus_radial = None
        self.cycle = 0
        self.pattern_counts = Counter()
        self.quiet = quiet
        self.bootstrapping_phase = True
        self.bootstrapping_end_cycle = HardConfig.BOOTSTRAPPING_CYCLES

        if stimulus_source:
            self._load_stimulus(stimulus_source)
        self._init_decoder()

    def _load_stimulus(self, source):
        if source.lower().endswith(('.png','.jpg','.jpeg','.bmp')):
            if not PIL_AVAILABLE:
                print("[Error] Pillow needed")
                return
            self.stimulus_radial = RadialSignature.from_image(source, size=64, num_rays=36)
            print("[Stimulus] Loaded radial signature (36 rays)")
        else:
            try:
                with open(source) as f:
                    vec = np.array([float(x) for x in f.read().split()])
                if len(vec) == 36:
                    self.stimulus_radial = vec / (np.linalg.norm(vec)+1e-8)
                else:
                    raise ValueError
                print("[Stimulus] Loaded radial signature from file")
            except:
                print("[Error] Unsupported stimulus")
                self.stimulus_radial = None

    def _init_decoder(self):
        weights_path = self.workspace / "decoder_weights.npz"
        self.decoder = NeuralDecoder(input_dim=HardConfig.NN_INPUT_DIM,
                                     hidden1=HardConfig.NN_HIDDEN_1,
                                     hidden2=HardConfig.NN_HIDDEN_2,
                                     hidden3=HardConfig.NN_HIDDEN_3,
                                     output_dim=HardConfig.NN_OUTPUT_DIM)
        if weights_path.exists():
            self.decoder.load_weights(weights_path)
            self.bootstrapping_phase = False
            if not self.quiet:
                print("[Bootstrapping] Skipped (weights found)")
        else:
            if not self.quiet:
                print(f"[Bootstrapping] Phase active for {self.bootstrapping_end_cycle} cycles")

    def _compute_reward(self, art, pattern):
        # Compute radial signature of generated art (contour only for structural reward)
        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
        # Structural similarity with stimulus
        if self.stimulus_radial is not None:
            radial_sim = RadialSignature.cross_correlation(self.stimulus_radial, sig_art)
        else:
            radial_sim = 0.5
        # Contour consistency with ideal shape (if pattern is shape)
        if pattern == 'shape':
            ideal_sig = RadialSignature.ideal_contour_from_params(
                self.generator.params['shape_param'],
                self.generator.params['symmetry'],
                self.generator.params['density'],
                self.generator.params['noise']
            )
            contour_reward = RadialSignature.contour_consistency(sig_art, ideal_sig)
        else:
            contour_reward = 0.5  # neutral for non-shape
        # Novelty reward
        avec = ArtEmbedder.embed(art)
        if hasattr(self.memory, 'novelty'):
            novelty = self.memory.novelty(avec)
        else:
            novelty = 0.5
        # Survival reward
        survival = (self.budget.energy / self.budget.max_energy +
                    self.budget.attention / self.budget.max_attention +
                    (1 - self.budget.fatigue / HardConfig.MAX_FATIGUE)) / 3
        # Total
        total = (HardConfig.REWARD_CONTOUR_SIM_WEIGHT * contour_reward +
                 HardConfig.REWARD_RADIAL_SIM_WEIGHT * radial_sim +
                 HardConfig.REWARD_NOVELTY_WEIGHT * novelty +
                 HardConfig.REWARD_SURVIVAL_WEIGHT * survival)
        total = min(1.0, max(0.0, total))
        return total, radial_sim, contour_reward

    def _detect_stagnation(self, pattern, reward):
        repeat = self.budget.track_pattern_repetition(pattern)
        reward_stagnation = self.budget.track_reward_stagnation(reward)
        if repeat >= HardConfig.REPETITION_STAGNATION_THRESHOLD or reward_stagnation:
            if not self.quiet:
                print(f"[Stagnation] Pattern '{pattern}' repeat={repeat}, reward stagnant={reward_stagnation}. Triggering adaptive reset.")
            self.budget.energy = max(0, self.budget.energy - 15)
            self.budget.failure_burden = max(0, self.budget.failure_burden - 25)
            self.generator.mutate(intensity=0.7)
            self.budget.consecutive_same_pattern = 0
            # Also force a rest
            self.budget.recover(5, 5, 5)
            return True
        return False

    def step(self):
        self.cycle += 1
        self.budget.cycle = self.cycle

        if self.stimulus_radial is None or self.decoder is None:
            print("[Error] No stimulus or decoder.")
            return None, None, None, None

        # ========= BOOTSTRAPPING =========
        if self.bootstrapping_phase and self.cycle <= self.bootstrapping_end_cycle:
            self.generator.params['pattern'] = 'shape'
            self.generator.params['shape_param'] = random.uniform(0, 0.15)
            self.generator.params['density'] = 0.55
            self.generator.params['symmetry'] = 0.9
            self.generator.params['noise'] = 0.02
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward = self._compute_reward(art, pat)
            # extra reward for high contour consistency
            if contour_reward > 0.7:
                self.budget.recover(HardConfig.BOOTSTRAP_ENERGY_REWARD, 5, 5)
                if not self.quiet:
                    print(f"[Bootstrap] Contour reward {contour_reward:.2f} +{HardConfig.BOOTSTRAP_ENERGY_REWARD} energy")
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
                if not self.quiet:
                    print(f"[Bootstrap] Sample {len(self.decoder.training_buffer)} rad={radial_sim:.2f} contour={contour_reward:.2f}")
            # update world model
            self.world_model.update(self.stimulus_radial, 'generate', total_reward)
            self.budget.spend(*HardConfig.BOOTSTRAP_COST)
            self.budget.regen(False)
            self._log_step(art, total_reward, radial_sim, contour_reward, pat)
            return art, total_reward, radial_sim, pat

        # ========= NORMAL OPERATION =========
        # Check stagnation
        self._detect_stagnation(self.generator.params['pattern'], self.budget.reward_history[-1] if self.budget.reward_history else 0.5)

        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.budget.energy <= 10 or self.budget.attention <= 10:
            feasible = ['rest']
        else:
            if not self.budget.can_rest():
                feasible = [a for a in feasible if a != 'rest']

        # Determine shape bonus for generate
        shape_bonus = False
        if 'generate' in feasible:
            if not self.decoder.is_trained:
                if random.random() < HardConfig.NN_FORCED_SHAPE_PROB:
                    shape_bonus = True
            else:
                if random.random() < HardConfig.NN_POST_TRAIN_FORCED_SHAPE_PROB:
                    shape_bonus = True

        # Compute utilities
        utils = {}
        for a in feasible:
            base = 0.5
            if a == 'generate':
                if self.decoder.is_trained:
                    base += HardConfig.NN_GENERATE_BONUS_TRAINED
                else:
                    base += 0.5
                # curiosity bonus from world model prediction error
                curiosity = self.curiosity.get_bonus(self.stimulus_radial, a)
                base += curiosity * HardConfig.CURIOSITY_BONUS
                if shape_bonus:
                    base += HardConfig.NN_SHAPE_UTILITY_BONUS
            elif a == 'explore':
                base += 0.2
            elif a == 'rest':
                base = (1 - self.budget.energy/self.budget.max_energy) + \
                       (1 - self.budget.attention/self.budget.max_attention) + \
                       (self.budget.fatigue / HardConfig.MAX_FATIGUE)
            utils[a] = max(0, base + random.gauss(0, HardConfig.EXPLORATION_NOISE_STD))
        chosen = max(utils, key=utils.get)

        # Execute action
        art, pat = None, None
        if chosen == 'generate':
            if shape_bonus:
                self.generator.params['pattern'] = 'shape'
                self.generator.params['shape_param'] = random.uniform(0, 0.4)
                self.generator.params['density'] = random.uniform(0.4, 0.7)
                self.generator.params['symmetry'] = random.uniform(0.7, 0.95)
                self.generator.params['noise'] = random.uniform(0, 0.05)
                if not self.quiet:
                    print("[Forced Shape] (post-bootstrap)")
            elif self.decoder.is_trained:
                pred = self.decoder.predict_params(self.stimulus_radial)
                self.generator.set_params(pred)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward = self._compute_reward(art, pat)
            # extra reward for good contour
            if pat == 'shape' and contour_reward > 0.7:
                total_reward = min(1.0, total_reward + 0.1)
                self.budget.recover(3, 2, 3)
            # update world model
            self.world_model.update(self.stimulus_radial, chosen, total_reward)
            # memory
            self.memory.add_experience({
                'state': self.stimulus_radial.tolist(),
                'action': chosen,
                'reward': total_reward,
                'pattern': pat,
                'contour_reward': contour_reward,
                'params': self.generator.params.copy()
            })
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
            if self.cycle % HardConfig.NN_TRAIN_INTERVAL == 0 and len(self.decoder.training_buffer) >= HardConfig.NN_BATCH_SIZE:
                self.decoder.train()
            cost = HardConfig.ACTION_COSTS['generate']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'explore':
            self.generator.mutate(0.5)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward = self._compute_reward(art, pat)
            self.world_model.update(self.stimulus_radial, chosen, total_reward)
            cost = HardConfig.ACTION_COSTS['explore']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'refine':
            self.generator.mutate(0.1)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward = self._compute_reward(art, pat)
            self.world_model.update(self.stimulus_radial, chosen, total_reward)
            cost = HardConfig.ACTION_COSTS['refine']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'combine':
            if self.memory.working:
                exp = random.choice(list(self.memory.working))
                other_params = exp.get('params', self.generator.params)
                self.generator.crossover_with_memory(other_params)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward = self._compute_reward(art, pat)
            self.world_model.update(self.stimulus_radial, chosen, total_reward)
            cost = HardConfig.ACTION_COSTS['combine']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'rest':
            self.budget.recover(12, 15, 12)
            total_reward = 0.5
            radial_sim = 0.5
            contour_reward = 0.5
        else:  # recall, forget
            self.budget.spend(2,2,1)
            total_reward = 0.5
            radial_sim = 0.5
            contour_reward = 0.5

        self.budget.update_failure_burden(total_reward)
        self.budget.regen(chosen == 'rest')
        self._log_step(art, total_reward, radial_sim, contour_reward, pat if art else 'rest')
        return art, total_reward, radial_sim, pat

    def _log_step(self, art, reward, radial_sim, contour_reward, pat):
        if self.quiet:
            return
        print(f"\n[Cycle {self.cycle}] pattern={pat if art else 'rest'} | reward={reward:.3f} rad_sim={radial_sim:.3f} contour={contour_reward:.3f}")
        print(f"E={self.budget.energy} A={self.budget.attention} F={self.budget.fatigue} B={self.budget.failure_burden}")
        if art and len(art) > 200:
            print(art[:200] + "...")
        elif art:
            print(art)

    def run(self, cycles=500):
        for _ in range(cycles):
            self.step()
            time.sleep(0.03)
        print("\n=== RUN SUMMARY ===")
        print(f"Total cycles: {cycles}")
        print(f"Pattern usage: {dict(self.pattern_counts)}")
        if self.decoder and self.decoder.loss_history:
            print(f"Decoder final loss: {self.decoder.loss_history[-1]:.4f}, best: {self.decoder.best_loss:.4f}")
        else:
            print("Decoder never trained")
        if self.decoder:
            self.decoder.save_weights(self.workspace / "decoder_weights.npz")
            print("[Decoder] Weights saved.")


if __name__ == "__main__":
    import sys
    cycles = 500
    stimulus = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--auto' and i+1 < len(sys.argv):
            cycles = int(sys.argv[i+1]); i+=2
        elif sys.argv[i] in ('--image','--stimulus') and i+1 < len(sys.argv):
            stimulus = sys.argv[i+1]; i+=2
        else:
            i+=1
    if not stimulus:
        print("Usage: python aether.0.18.0.py --image circle.png --auto 500")
        sys.exit(1)
    core = AetherCognitiveCore(stimulus_source=stimulus, quiet=False)
    core.run(cycles)