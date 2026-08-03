#!/usr/bin/env python3
"""
AETHER v0.17.0 — SPATIAL GROUNDING WITH RADIAL SIGNATURE
============================================================
Changes from v0.16.0:
- Stimulus representation: Radial signature (36 rays) instead of 8 global stats.
- Decoder input dimension: 36 → 48 → 64 → 32 → 6.
- Reward: structural similarity (radial cross-correlation) + contour continuity.
- Circularity no longer dominant; only one of several factors.
- Adaptive coma: triggered on repeated pattern stagnation (anti-local-optimum).
- Bootstrapping uses radial signature as target for decoder.
- More aggressive forced shape after training (70%) and bonus (1.5).
"""

import math
import random
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import deque, Counter
import numpy as np

try:
    from PIL import Image, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not installed. Install with: pip install Pillow")

# ============================================================================
# HARD CONFIGURATION
# ============================================================================

class HardConfig:
    MAX_ENERGY = 120
    MAX_ATTENTION = 120
    MAX_FATIGUE = 100
    MEMORY_SLOTS = 30

    ACTION_COSTS = {
        'generate': (8, 6, 0, 4),
        'explore':  (25, 18, 1, 7),
        'refine':   (6, 10, 0, 4),
        'recall':   (2, 2, 0, 1),
        'combine':  (15, 12, 1, 5),
        'rest':     (-8, -10, 0, -8),
        'forget':   (4, 2, -1, 2),
    }

    COMMITMENT_WINDOW = 6
    COMMITMENT_VIOLATION_PENALTY = {'energy': -25, 'attention': -35, 'fatigue': +20}
    COMMITMENT_THRESHOLD_CONFIDENCE = 0.7

    FAILURE_BURDEN_MAX = 100
    COST_MULTIPLIER_MAX = 2.0

    EMERGENCY_BURDEN_THRESHOLD = 75
    EMERGENCY_ENERGY_THRESHOLD = 25
    COMA_BURDEN = 100
    COMA_ENERGY = 15
    COMA_DURATION = 5

    TRAUMA_BLOCK_THRESHOLD = 0.8
    TRAUMA_BLOCK_DURATION = 15

    WORLD_MODEL_UPDATE_RATE = 0.03
    WORLD_MODEL_HIDDEN_DIM = 8
    VECTOR_DIM = 8      # Not used for stimulus now, kept for compatibility

    # Decoder: radial signature input dimension = 36 rays
    NN_INPUT_DIM = 36
    NN_HIDDEN_1 = 48
    NN_HIDDEN_2 = 64
    NN_HIDDEN_3 = 32
    NN_OUTPUT_DIM = 6

    NN_LEARNING_RATE = 0.008
    NN_TRAINING_EPOCHS = 12
    NN_BATCH_SIZE = 32
    NN_TRAIN_INTERVAL = 20
    NN_SAMPLE_THRESHOLD_INITIAL = 0.15
    NN_SAMPLE_THRESHOLD_MAX = 0.7
    NN_CONFIDENCE_LOSS_THRESH = 0.04
    NN_FORCED_SHAPE_PROB = 0.9                # before training
    NN_POST_TRAIN_FORCED_SHAPE_PROB = 0.7     # after training
    NN_GENERATE_BONUS_TRAINED = 1.0
    NN_SHAPE_UTILITY_BONUS = 1.5              # strong incentive

    BOOTSTRAPPING_CYCLES = 40                  # shorter but more focused
    BOOTSTRAP_ENERGY_REWARD = 12
    BOOTSTRAP_BURDEN_REDUCTION = -15
    BOOTSTRAP_COST = (2, 1, 1)                # very cheap during bootstrapping

    FORESIGHT_STEPS = 2
    PLANNING_DISCOUNT = 0.9

    EXPLORATION_NOISE_STD = 0.12
    CURIOSITY_BONUS = 0.25

    REPETITION_PENALTY_PER_USE = 0.06
    STATE_TRANSITION_NOISE = 0.08

    ACTION_SHIFT = {
        'explore': 0.30, 'refine': 0.10, 'generate': 0.03,
        'combine': 0.15, 'rest': -0.08, 'recall': 0.0, 'forget': 0.0
    }

    REST_COOLDOWN = 3
    REST_FATIGUE_REDUCTION = 10
    REST_ENERGY_GAIN_BASE = 8
    REST_ATTENTION_GAIN_BASE = 12
    BURDEN_RECOVERY_REST = -10

    STIMULUS_WEIGHT = 0.25
    STIMULUS_SIMILARITY_THRESHOLD = 0.1
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']

    # Adaptive coma: if same pattern repeated many times without improvement
    REPETITION_STAGNATION_THRESHOLD = 12
    COMBO_TRIGGER_ENERGY = 0     # will be set during runtime

    # Reward weights
    REWARD_STRUCTURAL_WEIGHT = 0.5
    REWARD_CONTOUR_WEIGHT = 0.2
    REWARD_NOVELTY_WEIGHT = 0.15
    REWARD_SURVIVAL_WEIGHT = 0.15


# ============================================================================
# NEURAL DECODER (NumPy) with adaptive input dimension
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
# RADIAL SIGNATURE EXTRACTOR (from image or ASCII art)
# ============================================================================

class RadialSignature:
    @staticmethod
    def from_image(image_path, size=64, num_rays=36):
        """Extract radial edge distance signature from an image."""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow required for image processing")
        img = Image.open(image_path).convert('L')
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        arr = np.array(img, dtype=np.float32) / 255.0
        # Simple edge detection: gradient magnitude
        gx = np.abs(np.diff(arr, axis=1, append=arr[:,-1:]))
        gy = np.abs(np.diff(arr, axis=0, append=arr[-1:,:]))
        edge = np.maximum(gx, gy)
        edge = (edge > 0.2).astype(np.float32)   # threshold
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
        # Normalize to [0,1]
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def from_ascii_art(art, num_rays=36):
        """Extract radial edge signature from ASCII art (for reward computation)."""
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(num_rays)
        h, w = len(lines), max(len(l) for l in lines)
        # Create binary grid: character present -> 1
        grid = np.zeros((h, w), dtype=np.float32)
        for y, line in enumerate(lines):
            for x, ch in enumerate(line.ljust(w)):
                if ch != ' ':
                    grid[y, x] = 1.0
        # Simple edge detection via difference
        gx = np.abs(np.diff(grid, axis=1, append=grid[:,-1:]))
        gy = np.abs(np.diff(grid, axis=0, append=grid[-1:,:]))
        edge = np.maximum(gx, gy)
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
        """Structural similarity between two radial signatures."""
        # Normalized cross-correlation (simple)
        if np.std(sig1) == 0 or np.std(sig2) == 0:
            return 0.5
        corr = np.corrcoef(sig1, sig2)[0,1]
        return max(0.0, min(1.0, (corr + 1) / 2))  # map -1..1 to 0..1

    @staticmethod
    def contour_continuity(sig):
        """Measure smoothness of radial distances (low variance of differences)."""
        if len(sig) < 3:
            return 0.5
        diff = np.abs(np.diff(sig))
        # circular wrap
        diff_wrap = np.abs(sig[-1] - sig[0])
        diff = np.append(diff, diff_wrap)
        var_diff = np.var(diff)
        # sigmoid-like: high continuity -> low variance -> high score
        cont = 1.0 / (1.0 + var_diff * 5)
        return max(0.0, min(1.0, cont))


# ============================================================================
# LIGHTWEIGHT MENTE ADAPTER (simplified but sufficient)
# ============================================================================

class MenteMemory:
    def __init__(self, working_capacity=10, episodic_capacity=100):
        self.working = deque(maxlen=working_capacity)
        self.episodic = deque(maxlen=episodic_capacity)
        self.semantic = {}
    def add_experience(self, experience):
        self.working.append(experience)
        if experience.get('structural_reward', 0) > 0.7:
            self.episodic.append(experience)
    def recall_similar(self, query, k=3):
        candidates = list(self.working) + list(self.episodic)
        if not candidates: return []
        query_pat = query.get('pattern')
        query_struct = query.get('structural_reward', 0.5)
        scored = []
        for exp in candidates:
            score = 0.5 if exp.get('pattern') == query_pat else 0
            score += 1.0 - abs(exp.get('structural_reward', 0.5) - query_struct)
            scored.append((score, exp))
        scored.sort(reverse=True)
        return [exp for _, exp in scored[:k]]
    def update_semantic(self, key, value):
        self.semantic[key] = value

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
    def spend(self, energy_cost, attention_cost, fatigue_delta):
        self.energy = max(0, self.energy - energy_cost)
        self.attention = max(0, self.attention - attention_cost)
        self.fatigue = min(100, self.fatigue + fatigue_delta)
    def recover(self, energy_gain, attention_gain, fatigue_reduction):
        self.energy = min(self.max_energy, self.energy + energy_gain)
        self.attention = min(self.max_attention, self.attention + attention_gain)
        self.fatigue = max(0, self.fatigue - fatigue_reduction)
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

class MenteCuriosity:
    def __init__(self, novelty_weight=0.3, uncertainty_weight=0.2):
        self.novelty_weight = novelty_weight
        self.uncertainty_weight = uncertainty_weight
        self.visited_states = Counter()
    def get_bonus(self, state_vec, prediction_error):
        h = tuple(np.round(state_vec, 2).tolist())
        self.visited_states[h] += 1
        novelty = 1.0 / (1.0 + self.visited_states[h])
        return self.novelty_weight * novelty + self.uncertainty_weight * prediction_error

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
# ASCII SHAPE GENERATOR (unchanged from previous versions)
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
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        cx, cy = w//2, h//2
        size = min(w,h)//4
        if shape_param < 0.33:
            r = int(size * (0.5 + shape_param*1.5))
            ShapeAwareGenerator.draw_circle(grid, cx, cy, r)
        elif shape_param < 0.66:
            sz = int(size * (0.5 + (shape_param-0.33)*3))
            ShapeAwareGenerator.draw_square(grid, cx, cy, sz)
        else:
            sz = int(size * (0.5 + (shape_param-0.66)*3))
            ShapeAwareGenerator.draw_triangle(grid, cx, cy, sz)
        if noise > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < noise*0.3:
                        grid[y][x] = ' ' if grid[y][x] != ' ' else random.choice('░▒▓')
        non_space = sum(c!=' ' for row in grid for c in row)
        target = int(w*h*density)
        if non_space < target:
            pos = [(y,x) for y in range(h) for x in range(w) if grid[y][x]==' ']
            random.shuffle(pos)
            for _ in range(min(target-non_space, len(pos))):
                y,x = pos.pop(); grid[y][x] = random.choice('░▒▓█')
        return '\n'.join(''.join(row) for row in grid)

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


# ============================================================================
# ART EMBEDDER (kept for memory but not used for reward)
# ============================================================================

class ArtEmbedder:
    @staticmethod
    def embed(art):
        # Still needed for memory and novelty
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
        # still compute circularity but not dominant
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
# AETHER v0.17.0 CORE
# ============================================================================

class AetherCognitiveCore:
    def __init__(self, stimulus_source=None, workspace="aether_works_v0170", quiet=False):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.bus = MenteEventBus()
        self.memory = MenteMemory()
        self.budget = MenteBudget(max_energy=HardConfig.MAX_ENERGY,
                                  max_attention=HardConfig.MAX_ATTENTION)
        self.curiosity = MenteCuriosity()
        self.generator = Generator()
        self.decoder = None
        self.stimulus_radial = None   # radial signature of stimulus
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
                print("[Error] Pillow needed for image stimulus")
                return
            self.stimulus_radial = RadialSignature.from_image(source, size=64, num_rays=36)
            print("[Stimulus] Loaded radial signature (36 rays)")
        else:
            # fallback: try to load as text file of radial signature
            try:
                with open(source) as f:
                    vec = np.array([float(x) for x in f.read().split()])
                if len(vec) == 36:
                    self.stimulus_radial = vec / (np.linalg.norm(vec)+1e-8)
                else:
                    raise ValueError("Not 36 dimensions")
                print("[Stimulus] Loaded radial signature from file")
            except:
                print("[Error] Unsupported stimulus source")
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
            # If weights exist, skip bootstrapping (assume already trained)
            if not self.quiet:
                print("[Bootstrapping] Skipped because weights found.")
            self.bootstrapping_phase = False
        else:
            if not self.quiet:
                print(f"[Bootstrapping] Phase active for first {self.bootstrapping_end_cycle} cycles.")

    def _compute_structural_reward(self, art):
        """Compute reward based on radial signature similarity and contour continuity."""
        if not art:
            return 0.5, 0.5
        sig_art = RadialSignature.from_ascii_art(art, num_rays=36)
        if self.stimulus_radial is None:
            struct_sim = 0.5
        else:
            struct_sim = RadialSignature.cross_correlation(self.stimulus_radial, sig_art)
        contour = RadialSignature.contour_continuity(sig_art)
        # combined reward
        reward = (HardConfig.REWARD_STRUCTURAL_WEIGHT * struct_sim +
                  HardConfig.REWARD_CONTOUR_WEIGHT * contour)
        return min(1.0, max(0.0, reward)), struct_sim

    def _compute_novelty_reward(self, art):
        avec = ArtEmbedder.embed(art)
        nov = self.memory.novelty(avec) if hasattr(self.memory, 'novelty') else 0.5
        return nov

    def _compute_survival_reward(self):
        # reward based on energy/attention levels
        e_ratio = self.budget.energy / self.budget.max_energy
        a_ratio = self.budget.attention / self.budget.max_attention
        f_ratio = 1.0 - (self.budget.fatigue / HardConfig.MAX_FATIGUE)
        survival = (e_ratio + a_ratio + f_ratio) / 3
        return survival

    def _compute_total_reward(self, art):
        struct_reward, struct_sim = self._compute_structural_reward(art)
        novelty_reward = self._compute_novelty_reward(art)
        survival_reward = self._compute_survival_reward()
        # total weighted
        total = (HardConfig.REWARD_STRUCTURAL_WEIGHT * struct_reward +
                 HardConfig.REWARD_NOVELTY_WEIGHT * novelty_reward +
                 HardConfig.REWARD_SURVIVAL_WEIGHT * survival_reward)
        # also return structural similarity separately for logging
        return total, struct_sim

    def _detect_stagnation(self, pattern):
        repeat = self.budget.track_pattern_repetition(pattern)
        if repeat >= HardConfig.REPETITION_STAGNATION_THRESHOLD:
            # trigger adaptive coma
            if not self.quiet:
                print(f"[Stagnation] Pattern '{pattern}' repeated {repeat} times. Triggering anti-local-optimum reset.")
            # induce mini-coma: force rest, reduce burden, randomize generator
            self.budget.energy = max(0, self.budget.energy - 15)
            self.budget.failure_burden = max(0, self.budget.failure_burden - 30)
            self.generator.mutate(intensity=0.8)  # heavy mutation
            self.budget.consecutive_same_pattern = 0
            return True
        return False

    def step(self):
        self.cycle += 1

        if self.stimulus_radial is None or self.decoder is None:
            print("[Error] No stimulus or decoder.")
            return None, None, None, None

        # ========= BOOTSTRAPPING PHASE =========
        if self.bootstrapping_phase and self.cycle <= self.bootstrapping_end_cycle:
            # Force generate shape with ideal parameters
            self.generator.params['pattern'] = 'shape'
            self.generator.params['shape_param'] = random.uniform(0, 0.15)
            self.generator.params['density'] = 0.55
            self.generator.params['symmetry'] = 0.9
            self.generator.params['noise'] = 0.02
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, struct_sim = self._compute_total_reward(art)
            # Boost reward if struct_sim high
            if struct_sim > 0.7:
                total_reward = min(1.0, total_reward + 0.2)
                self.budget.recover(energy_gain=HardConfig.BOOTSTRAP_ENERGY_REWARD,
                                    attention_gain=5, fatigue_reduction=5)
                if not self.quiet:
                    print(f"[Bootstrap Reward] struct_sim={struct_sim:.2f} +{HardConfig.BOOTSTRAP_ENERGY_REWARD} energy")
            # collect sample
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
                if not self.quiet:
                    print(f"[Bootstrap] Collected sample {len(self.decoder.training_buffer)} struct_sim={struct_sim:.2f}")
            # apply reduced cost
            en_cost, att_cost, fat_delta = HardConfig.BOOTSTRAP_COST
            self.budget.spend(energy_cost=en_cost, attention_cost=att_cost, fatigue_delta=fat_delta)
            self._log_step(art, total_reward, struct_sim, pat)
            return art, total_reward, struct_sim, pat

        # ========= NORMAL OPERATION =========
        # Check for adaptive coma (stagnation)
        self._detect_stagnation(self.generator.params['pattern'])

        # Feasible actions based on resources
        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.budget.energy <= 10 or self.budget.attention <= 10:
            feasible = ['rest']
        if not self.budget.can_rest():
            feasible = [a for a in feasible if a != 'rest']

        # Determine if we force shape for generate
        shape_bonus_for_action = False
        if 'generate' in feasible:
            if not self.decoder.is_trained:
                if random.random() < HardConfig.NN_FORCED_SHAPE_PROB:
                    shape_bonus_for_action = True
            else:
                if random.random() < HardConfig.NN_POST_TRAIN_FORCED_SHAPE_PROB:
                    shape_bonus_for_action = True

        # Utility calculation
        utils = {}
        for a in feasible:
            base = 0.5
            if a == 'generate':
                if self.decoder.is_trained:
                    base += HardConfig.NN_GENERATE_BONUS_TRAINED
                else:
                    base += 0.6
                base += self.curiosity.get_bonus(self.stimulus_radial, 0.2)  # prediction error placeholder
                if shape_bonus_for_action:
                    base += HardConfig.NN_SHAPE_UTILITY_BONUS
            elif a == 'explore':
                base += 0.2
            elif a == 'rest':
                base = (1 - self.budget.energy/self.budget.max_energy) + \
                       (1 - self.budget.attention/self.budget.max_attention) + \
                       (self.budget.fatigue / HardConfig.MAX_FATIGUE)
            utils[a] = max(0, base)
        # Add exploration noise
        for a in utils:
            utils[a] += random.gauss(0, HardConfig.EXPLORATION_NOISE_STD)
        chosen = max(utils, key=utils.get)

        # Execute action
        art, pat, total_reward, struct_sim = None, None, 0.5, 0.5
        if chosen == 'generate':
            if shape_bonus_for_action:
                # forced shape exploration
                self.generator.params['pattern'] = 'shape'
                self.generator.params['shape_param'] = random.uniform(0, 0.4)
                self.generator.params['density'] = random.uniform(0.4, 0.7)
                self.generator.params['symmetry'] = random.uniform(0.7, 0.95)
                self.generator.params['noise'] = random.uniform(0, 0.05)
                if not self.quiet:
                    print("[Forced Shape] (post-bootstrap) exploring shape")
            elif self.decoder.is_trained:
                pred = self.decoder.predict_params(self.stimulus_radial)
                self.generator.set_params(pred)
            # generate
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, struct_sim = self._compute_total_reward(art)
            # extra reward if structure matches stimulus
            if struct_sim > 0.75:
                total_reward = min(1.0, total_reward + 0.15)
                self.budget.recover(3, 2, 3)
            # store experience
            self.memory.add_experience({
                'state': self.stimulus_radial.tolist(),
                'action': chosen,
                'reward': total_reward,
                'pattern': pat,
                'structural_reward': struct_sim,
                'params': self.generator.params.copy()
            })
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
            if self.cycle % HardConfig.NN_TRAIN_INTERVAL == 0 and len(self.decoder.training_buffer) >= HardConfig.NN_BATCH_SIZE:
                self.decoder.train()
            # apply cost
            cost = HardConfig.ACTION_COSTS.get(chosen, (8,6,0,4))
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'explore':
            self.generator.mutate(0.5)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, struct_sim = self._compute_total_reward(art)
            cost = HardConfig.ACTION_COSTS['explore']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'refine':
            self.generator.mutate(0.1)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, struct_sim = self._compute_total_reward(art)
            cost = HardConfig.ACTION_COSTS['refine']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'combine':
            # simple combination: crossover with random memory
            if self.memory.working:
                exp = random.choice(list(self.memory.working))
                other_params = exp.get('params', self.generator.params)
                self.generator.crossover_with_memory(other_params)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, struct_sim = self._compute_total_reward(art)
            cost = HardConfig.ACTION_COSTS['combine']
            self.budget.spend(cost[0], cost[1], cost[3])
        elif chosen == 'rest':
            self.budget.recover(12, 15, 12)
        else:  # recall or forget
            self.budget.spend(2, 2, 1)

        # Update failure burden
        self.budget.update_failure_burden(total_reward)
        # Regularly regen (rest not required)
        self.budget.regen(resting=False)

        self._log_step(art, total_reward, struct_sim, pat if art else 'rest')
        return art, total_reward, struct_sim, pat

    def _log_step(self, art, reward, struct_sim, pat):
        if self.quiet:
            return
        print(f"\n[Cycle {self.cycle}] pattern={pat} | reward={reward:.3f} struct_sim={struct_sim:.3f}")
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
            print("Decoder never trained (no samples collected).")
        if self.decoder:
            self.decoder.save_weights(self.workspace / "decoder_weights.npz")
            print("[Decoder] Weights saved.")


# Add missing methods for MenteBudget and Generator
def can_rest(self):
    return (self.cycle - self.last_rest_cycle) >= HardConfig.REST_COOLDOWN

def regen(self, resting):
    if resting:
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

MenteBudget.can_rest = can_rest
MenteBudget.regen = regen
MenteBudget.last_rest_cycle = -999

def crossover_with_memory(self, other):
    for k in self.params:
        if k == 'pattern':
            if random.random() < 0.5:
                self.params[k] = other.get(k, self.params[k])
        elif isinstance(other.get(k), (int, float)):
            self.params[k] = (self.params[k] + other[k]) / 2.0

Generator.crossover_with_memory = crossover_with_memory

def novelty(self, vec):
    if not self.vectors:
        return 1.0
    sims = [np.dot(vec, v) / (np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors]
    return 1.0 - max(sims)

MenteMemory.novelty = novelty
MenteMemory.vectors = []  # dummy for novelty, but we don't use it heavily

# Fix missing 'vectors' attribute for novelty in MenteMemory
MenteMemory.vectors = []


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
        print("Usage: python aether.0.17.0.py --image circle.png --auto 500")
        sys.exit(1)
    core = AetherCognitiveCore(stimulus_source=stimulus, quiet=False)
    core.run(cycles)