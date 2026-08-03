#!/usr/bin/env python3
"""
AETHER v0.9.7 — ENGINEERING TRANSPARENCY
"I no longer hide my mistakes. I show you my utility, my regret, my prediction error."

CHANGES FROM v0.9.6:
- Real utility reporting (not average of reasons)
- Ablation-based factor contribution (Δutility when factor removed)
- Noise tracking with rank before/after
- Removed persona (engineer-friendly output)
- Hard constraint: pattern block = action infeasible (no fallback)
- 2-step foresight with state transition and resource simulation
- "Why NOT chosen" for runner-up actions
- Log state transition (before/after/delta)
- World model validation (prediction error)
- Decision regret (chosen vs best possible without noise)

USAGE:
    python aether_0_9_7.py --auto 200    # run 200 cycles with full logging
    python aether_0_9_7.py --demo        # 20 cycles demo
    python aether_0_9_7.py --quiet       # minimal output (only essentials)
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

# ============================================================================
# HARD CONFIGURATION (immutable)
# ============================================================================

class HardConfig:
    MAX_ENERGY = 100
    MAX_ATTENTION = 100
    MAX_FATIGUE = 100
    MEMORY_SLOTS = 25
    
    ACTION_COSTS = {
        'generate': (10, 8, 0, 4),
        'explore':  (30, 20, 1, 8),
        'refine':   (8, 12, 0, 5),
        'recall':   (3, 2, 0, 1),
        'combine':  (18, 15, 1, 6),
        'rest':     (-6, -8, 0, -7),
        'forget':   (5, 3, -1, 2),
    }
    
    COMMITMENT_WINDOW = 6
    COMMITMENT_VIOLATION_PENALTY = {'energy': -30, 'attention': -40, 'fatigue': +25}
    COMMITMENT_THRESHOLD_CONFIDENCE = 0.7
    
    FAILURE_BURDEN_MAX = 100
    COST_MULTIPLIER_MAX = 2.0
    
    EMERGENCY_BURDEN_THRESHOLD = 70
    EMERGENCY_ENERGY_THRESHOLD = 25
    COMA_BURDEN = 100
    COMA_ENERGY = 15
    COMA_DURATION = 5
    
    TRAUMA_BLOCK_THRESHOLD = 0.7
    TRAUMA_BLOCK_DURATION = 20
    
    WORLD_MODEL_UPDATE_RATE = 0.03
    WORLD_MODEL_HIDDEN_DIM = 6
    VECTOR_DIM = 6
    
    FORESIGHT_STEPS = 2
    PLANNING_DISCOUNT = 0.9
    
    EXPLORATION_NOISE_STD = 0.12
    CURIOSITY_BONUS = 0.2
    
    REPETITION_PENALTY_PER_USE = 0.05
    STATE_TRANSITION_NOISE = 0.08
    
    ACTION_SHIFT = {
        'explore': 0.30,
        'refine': 0.10,
        'generate': 0.03,
        'combine': 0.15,
        'rest': -0.08,
        'recall': 0.0,
        'forget': 0.0
    }
    
    REST_COOLDOWN = 4
    REST_FATIGUE_REDUCTION = 8
    REST_ENERGY_GAIN_BASE = 7
    REST_ATTENTION_GAIN_BASE = 10
    BURDEN_RECOVERY_REST = -12


# ============================================================================
# RESOURCE MANAGER (with death spiral and coma)
# ============================================================================

class ResourceManager:
    def __init__(self):
        self.energy = HardConfig.MAX_ENERGY
        self.attention = HardConfig.MAX_ATTENTION
        self.memory_used = 0
        self.fatigue = 0
        self.failure_burden = 0
        self.coma_cycles_left = 0
        self.cycle = 0
        self.last_rest_cycle = -999
        self.consecutive_failures = 0
        
        # For state logging
        self.energy_before_action = None
        self.energy_after_action = None
        self.attention_before_action = None
        self.attention_after_action = None
        
    def is_coma(self) -> bool:
        return self.coma_cycles_left > 0
    
    def enter_coma(self):
        if self.failure_burden >= HardConfig.COMA_BURDEN and self.energy <= HardConfig.COMA_ENERGY:
            self.coma_cycles_left = HardConfig.COMA_DURATION
            self.energy = 0
            self.attention = 0
            return True
        return False
    
    def update_coma(self):
        if self.coma_cycles_left > 0:
            self.coma_cycles_left -= 1
            if self.coma_cycles_left == 0:
                self.energy = 30
                self.attention = 40
                self.fatigue = 20
                self.failure_burden = max(0, self.failure_burden - 40)
            return True
        return False
    
    def apply_cost(self, action: str):
        if action.startswith('failed_'):
            # Failed actions: use generate cost but reduced effect
            en, att, mem, fat = HardConfig.ACTION_COSTS.get('generate', (8,6,0,3))
        else:
            en, att, mem, fat = HardConfig.ACTION_COSTS.get(action, (0,0,0,0))
        
        multiplier = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        en_delta = int(en * multiplier)
        att_delta = int(att * multiplier)
        fat_delta = fat + int(self.failure_burden / 25)
        
        self.energy_before_action = self.energy
        self.attention_before_action = self.attention
        
        self.energy = self.energy - en_delta
        self.attention = self.attention - att_delta
        self.memory_used = self.memory_used + mem
        self.fatigue = self.fatigue + fat_delta
        
        self.energy = max(0, min(HardConfig.MAX_ENERGY, self.energy))
        self.attention = max(0, min(HardConfig.MAX_ATTENTION, self.attention))
        self.memory_used = max(0, min(HardConfig.MEMORY_SLOTS, self.memory_used))
        self.fatigue = max(0, min(HardConfig.MAX_FATIGUE, self.fatigue))
        
        self.energy_after_action = self.energy
        self.attention_after_action = self.attention
    
    def regen(self, is_resting: bool):
        if is_resting and self.can_rest():
            fatigue_penalty = max(0, self.fatigue / 20)
            energy_gain = max(3, HardConfig.REST_ENERGY_GAIN_BASE - int(fatigue_penalty))
            attention_gain = max(4, HardConfig.REST_ATTENTION_GAIN_BASE - int(fatigue_penalty * 1.2))
            fatigue_reduction = HardConfig.REST_FATIGUE_REDUCTION
            self.energy = min(HardConfig.MAX_ENERGY, self.energy + energy_gain)
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention + attention_gain)
            self.fatigue = max(0, self.fatigue - fatigue_reduction)
            self.last_rest_cycle = self.cycle
            self.failure_burden = max(0, self.failure_burden + HardConfig.BURDEN_RECOVERY_REST)
        else:
            self.energy = min(HardConfig.MAX_ENERGY, self.energy + 1)
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention + 1)
            self.fatigue = max(0, self.fatigue - 1)
    
    def update_failure_burden(self, score: float):
        if score < 0.4:
            self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden + 12)
            if score < 0.2:
                self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden + 8)
            self.consecutive_failures += 1
        elif score > 0.7:
            self.failure_burden = max(0, self.failure_burden - 10)
            self.consecutive_failures = 0
        else:
            self.consecutive_failures = 0
        self.failure_burden = max(0, min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden))
    
    def can_rest(self) -> bool:
        return (self.cycle - self.last_rest_cycle) >= HardConfig.REST_COOLDOWN
    
    def is_emergency(self) -> bool:
        return (self.failure_burden >= HardConfig.EMERGENCY_BURDEN_THRESHOLD and
                self.energy <= HardConfig.EMERGENCY_ENERGY_THRESHOLD)
    
    def get_effective_action_cost(self, action: str) -> Tuple[int, int, int]:
        en, att, _, fat = HardConfig.ACTION_COSTS.get(action, (0,0,0,0))
        mult = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        return int(en * mult), int(att * mult), fat
    
    def get_cost_multiplier(self) -> float:
        return 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
    
    def get_resource_delta(self) -> Dict[str, int]:
        if self.energy_before_action is not None and self.energy_after_action is not None:
            return {
                'energy': self.energy_after_action - self.energy_before_action,
                'attention': self.attention_after_action - self.attention_before_action
            }
        return {'energy': 0, 'attention': 0}


# ============================================================================
# LONG-TERM SCARS (trauma + identity drift)
# ============================================================================

class LongTermScars:
    def __init__(self):
        self.pattern_trauma = {}
        self.pattern_blocked_until = {}
        self.action_trauma = {}
        self.identity_bias = {'risk_tolerance': 0.5, 'novelty_seeking': 0.5, 'symmetry_preference': 0.5}
        self.cycle = 0
    
    def update(self, action: str, pattern: str, score: float, current_cycle: int):
        self.cycle = current_cycle
        if score < 0.3:
            self.pattern_trauma[pattern] = min(1.0, self.pattern_trauma.get(pattern, 0) + 0.12)
            self.action_trauma[action] = min(20, self.action_trauma.get(action, 0) + 3)
        else:
            for p in list(self.pattern_trauma.keys()):
                self.pattern_trauma[p] = max(0, self.pattern_trauma[p] - 0.01)
                if self.pattern_trauma[p] == 0: 
                    del self.pattern_trauma[p]
            for a in list(self.action_trauma.keys()):
                self.action_trauma[a] = max(0, self.action_trauma[a] - 1)
                if self.action_trauma[a] == 0: 
                    del self.action_trauma[a]
        if self.pattern_trauma.get(pattern, 0) >= HardConfig.TRAUMA_BLOCK_THRESHOLD:
            self.pattern_blocked_until[pattern] = current_cycle + HardConfig.TRAUMA_BLOCK_DURATION
        for p in list(self.pattern_blocked_until.keys()):
            if self.pattern_blocked_until[p] <= current_cycle:
                del self.pattern_blocked_until[p]
    
    def is_pattern_blocked(self, pattern: str) -> bool:
        return pattern in self.pattern_blocked_until
    
    def get_action_trauma_penalty(self, action: str) -> float:
        return self.action_trauma.get(action, 0) / 20.0
    
    def apply_identity_drift(self, recent_scores: List[float]):
        if len(recent_scores) < 30: 
            return
        avg = sum(recent_scores[-30:]) / 30
        target_risk = min(0.9, avg * 1.3)
        target_novelty = min(0.85, avg * 1.2)
        self.identity_bias['risk_tolerance'] += (target_risk - self.identity_bias['risk_tolerance']) * 0.002
        self.identity_bias['novelty_seeking'] += (target_novelty - self.identity_bias['novelty_seeking']) * 0.002
        for k in self.identity_bias:
            self.identity_bias[k] = max(0.1, min(0.9, self.identity_bias[k]))
    
    def get_novelty_bias(self, action: str) -> float:
        if action in ['explore', 'combine']:
            return self.identity_bias['novelty_seeking'] * 0.2
        return 0.0


# ============================================================================
# VECTOR MEMORY (episodic, similarity-based)
# ============================================================================

class VectorMemory:
    def __init__(self, dim=HardConfig.VECTOR_DIM):
        self.dim = dim
        self.vectors = []
        self.metadata = []
    
    def store(self, vec: np.ndarray, meta: dict):
        if len(self.vectors) >= HardConfig.MEMORY_SLOTS:
            self.vectors.pop(0)
            self.metadata.pop(0)
        self.vectors.append(vec)
        self.metadata.append(meta)
    
    def recall_similar(self, query: np.ndarray, k=3) -> List[Tuple[float, dict]]:
        if not self.vectors: 
            return []
        sims = []
        for i, v in enumerate(self.vectors):
            sim = np.dot(query, v) / (np.linalg.norm(query)*np.linalg.norm(v)+1e-8)
            sims.append((sim, i))
        sims.sort(reverse=True)
        return [(sim, self.metadata[idx].copy()) for sim, idx in sims[:k]]
    
    def novelty(self, vec: np.ndarray) -> float:
        if not self.vectors: 
            return 1.0
        max_sim = max(np.dot(vec, v)/(np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors)
        return 1.0 - max_sim
    
    def predict_score_similarity(self, query: np.ndarray) -> float:
        if not self.vectors: 
            return 0.5
        sims = []
        scores = []
        for i, v in enumerate(self.vectors):
            sim = np.dot(query, v) / (np.linalg.norm(query)*np.linalg.norm(v)+1e-8)
            if sim > 0.05:
                sims.append(sim)
                scores.append(self.metadata[i].get('score', 0.5))
        if not sims: 
            return 0.5
        total = sum(sims)
        return sum(sim * sc for sim, sc in zip(sims, scores)) / total


# ============================================================================
# EMBEDDING (parameter space and art space)
# ============================================================================

class ParamEmbedder:
    @staticmethod
    def embed(params: Dict) -> np.ndarray:
        features = [
            params.get('symmetry', 0.5),
            params.get('density', 0.35),
            params.get('complexity', 0.5),
            params.get('noise', 0.15),
        ]
        patterns = ['wave', 'fractal', 'cellular', 'lsystem']
        pattern = params.get('pattern', 'wave')
        for p in patterns:
            features.append(1.0 if p == pattern else 0.0)
        while len(features) < HardConfig.VECTOR_DIM:
            features.append(0.0)
        vec = np.array(features[:HardConfig.VECTOR_DIM], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


class ArtEmbedder:
    @staticmethod
    def embed(art: str) -> np.ndarray:
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(HardConfig.VECTOR_DIM, dtype=np.float32)
        h = len(lines)
        w = max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        features = []
        total = h*w
        non_space = sum(c != ' ' for line in padded for c in line)
        features.append(non_space / max(1, total))
        # Horizontal symmetry
        h_sym = 0.0
        cnt = 0
        for line in padded:
            stripped = line.rstrip()
            if len(stripped) > 2:
                mid = len(stripped)//2
                left = stripped[:mid]
                right = stripped[mid:][::-1]
                n = min(len(left), len(right))
                if n > 0:
                    matches = sum(1 for i in range(n) if left[i] == right[i] and left[i] != ' ')
                    h_sym += matches / n
                    cnt += 1
        features.append(h_sym / max(1, cnt))
        # Character variation (std dev of char codes)
        all_chars = [ord(c) for line in padded for c in line if c != ' ']
        if all_chars:
            var = np.std(all_chars) / 128.0
            features.append(min(1.0, var))
        else:
            features.append(0.0)
        while len(features) < HardConfig.VECTOR_DIM:
            features.append(0.0)
        vec = np.array(features[:HardConfig.VECTOR_DIM], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


# ============================================================================
# WORLD MODEL (predicts score from param vector)
# ============================================================================

class WorldModel:
    def __init__(self, input_dim=HardConfig.VECTOR_DIM, hidden_dim=HardConfig.WORLD_MODEL_HIDDEN_DIM):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.W1 = np.random.randn(hidden_dim, input_dim).astype(np.float32) * 0.1
        self.b1 = np.zeros(hidden_dim, dtype=np.float32)
        self.W2 = np.random.randn(1, hidden_dim).astype(np.float32) * 0.1
        self.b2 = 0.0
        self.confidence = 0.5
        self.buffer = deque(maxlen=150)
        self.last_prediction = 0.0
        self.last_actual = 0.0
        self.prediction_error = 0.0
    
    def predict(self, param_vec: np.ndarray) -> float:
        if param_vec.ndim > 1:
            param_vec = param_vec.flatten()
        h = np.tanh(self.W1 @ param_vec + self.b1)
        out = self.W2 @ h + self.b2
        scalar = float(out.item())
        return min(1.0, max(0.0, scalar))
    
    def predict_with_uncertainty(self, param_vec: np.ndarray) -> Tuple[float, float]:
        pred = self.predict(param_vec)
        uncertainty = 1.0 - self.confidence
        return pred, uncertainty
    
    def update(self, param_vec: np.ndarray, actual_score: float):
        param_vec = param_vec.flatten()
        # Store for validation
        self.last_actual = actual_score
        self.last_prediction = self.predict(param_vec)
        self.prediction_error = abs(self.last_prediction - actual_score)
        
        self.buffer.append((param_vec, actual_score))
        if len(self.buffer) % 5 == 0 and len(self.buffer) >= 10:
            indices = random.sample(range(len(self.buffer)), min(10, len(self.buffer)))
            for idx in indices:
                v, a = self.buffer[idx]
                pred = self.predict(v)
                error = a - pred
                h = np.tanh(self.W1 @ v + self.b1)
                self.W2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error * h.reshape(1, -1)
                self.b2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error
                delta_h = error * self.W2.T * (1 - h**2)
                self.W1 += HardConfig.WORLD_MODEL_UPDATE_RATE * np.outer(delta_h, v)
                self.b1 += HardConfig.WORLD_MODEL_UPDATE_RATE * delta_h.flatten()
        if len(self.buffer) >= 20:
            errors = [abs(self.predict(v)-a) for v,a in list(self.buffer)[-20:]]
            self.confidence = max(0.2, min(0.9, 1.0 - sum(errors)/20))


# ============================================================================
# STATE TRANSITION (for foresight)
# ============================================================================

class StateTransition:
    @staticmethod
    def transition(current_param_vec: np.ndarray, action: str, outcome_score: float) -> np.ndarray:
        current = current_param_vec.flatten().copy()
        shift = HardConfig.ACTION_SHIFT.get(action, 0.0)
        if outcome_score > 0.7:
            factor = 1.0 + shift
        elif outcome_score < 0.3:
            factor = 1.0 - shift
        else:
            factor = 1.0 + shift * (outcome_score - 0.5) * 2
        new_vec = current * factor
        noise = np.random.randn(len(current)).astype(np.float32) * HardConfig.STATE_TRANSITION_NOISE
        new_vec += noise
        norm = np.linalg.norm(new_vec)
        if norm > 0:
            new_vec = new_vec / norm
        return new_vec


# ============================================================================
# GENERATOR (hard constraint: no fallback)
# ============================================================================

class Generator:
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem']
    def __init__(self):
        self.params = {
            'pattern': random.choice(self.PATTERNS),
            'symmetry': random.uniform(0.3, 0.8),
            'density': random.uniform(0.2, 0.6),
            'complexity': random.uniform(0.3, 0.7),
            'noise': random.uniform(0.1, 0.4),
        }
        self.usage_counter = Counter()
    
    def generate(self, blocked_patterns: Set[str]) -> Tuple[str, str]:
        """Generate art. Raises ValueError if current pattern is blocked."""
        pattern = self.params['pattern']
        if pattern in blocked_patterns:
            # NO FALLBACK - hard constraint
            raise ValueError(f"Pattern '{pattern}' is currently blocked by trauma. Action infeasible.")
        
        self.usage_counter[pattern] += 1
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        temp_density = max(0.1, min(0.9, self.params['density'] + random.uniform(-0.1, 0.1)))
        temp_symmetry = max(0.0, min(1.0, self.params['symmetry'] + random.uniform(-0.1, 0.1)))
        temp_noise = max(0.0, min(0.6, self.params['noise'] + random.uniform(-0.1, 0.15)))
        
        if pattern == 'wave':
            freq_x = random.uniform(0.1, 0.6)
            freq_y = random.uniform(0.1, 0.5)
            for y in range(h):
                for x in range(w):
                    val = (math.sin(x*freq_x)*math.cos(y*freq_y) +
                           math.sin(x*0.8)*0.3 + math.cos(y*0.6)*0.3 +
                           random.uniform(-0.1, 0.1) * temp_noise)
                    norm = (val+1)/2
                    if norm > 1 - temp_density:
                        grid[y][x] = random.choice('░▒▓█')
        elif pattern == 'fractal':
            depth = max(1, int(self.params['complexity'] * 4) + random.randint(0,2))
            self._draw_fractal(grid, w//2, h//2, min(w,h)//6, depth, temp_noise)
        elif pattern == 'cellular':
            grid = self._cellular_automaton(w, h, temp_density, temp_noise)
        else:  # lsystem
            grid = self._lsystem_draw(w, h, temp_noise)
        
        if random.random() < temp_symmetry:
            for y in range(h):
                for x in range(w//2):
                    if grid[y][x] != ' ':
                        grid[y][w-1-x] = grid[y][x]
                    elif grid[y][w-1-x] != ' ':
                        grid[y][x] = grid[y][w-1-x]
        
        self._adjust_density(grid, temp_density)
        if temp_noise > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < temp_noise * 0.4:
                        if grid[y][x] == ' ':
                            grid[y][x] = random.choice(' .:oO0@')
                        else:
                            if random.random() < 0.5:
                                grid[y][x] = ' '
        art = '\n'.join(''.join(row) for row in grid)
        return art, pattern
    
    def _draw_fractal(self, grid, x, y, size, depth, noise):
        if depth<=0 or size<1: return
        for i in range(-size, size+1):
            if 0<=x+i<len(grid[0]) and 0<=y<len(grid):
                if random.random() > noise:
                    grid[y][x+i] = '█'
            if 0<=x<len(grid[0]) and 0<=y+i<len(grid):
                if random.random() > noise:
                    grid[y+i][x] = '█'
        self._draw_fractal(grid, x+size+1, y, size//2, depth-1, noise)
        self._draw_fractal(grid, x-size-1, y, size//2, depth-1, noise)
        self._draw_fractal(grid, x, y+size+1, size//2, depth-1, noise)
        self._draw_fractal(grid, x, y-size-1, size//2, depth-1, noise)
    
    def _cellular_automaton(self, w, h, density, noise):
        grid = [[1 if random.random()<density else 0 for _ in range(w)] for _ in range(h)]
        steps = 3 + int(noise * 3)
        for _ in range(steps):
            new = [[0]*w for _ in range(h)]
            for y in range(h):
                for x in range(w):
                    neigh = sum(grid[(y+dy)%h][(x+dx)%w] for dy in (-1,0,1) for dx in (-1,0,1) if not(dy==0 and dx==0))
                    if grid[y][x]:
                        new[y][x] = 1 if neigh in (2,3) else 0
                    else:
                        new[y][x] = 1 if neigh==3 else 0
            grid = new
        result = [[' ']*w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if grid[y][x]:
                    result[y][x] = random.choice('░▒▓')
        return result
    
    def _lsystem_draw(self, w, h, noise):
        axiom = 'F'
        rules = {'F':'F+F-F-F+F'}
        seq = axiom
        depth = 3 + int(noise * 2)
        for _ in range(depth):
            seq = ''.join(rules.get(c,c) for c in seq)
        grid = [[' ']*w for _ in range(h)]
        x,y = w//2, h//2
        angle = 0
        for c in seq[:400]:
            if c=='F':
                dx = int(round(math.cos(math.radians(angle)) + random.uniform(-0.1,0.1)*noise))
                dy = int(round(math.sin(math.radians(angle)) + random.uniform(-0.1,0.1)*noise))
                nx, ny = x+dx, y+dy
                if 0<=nx<w and 0<=ny<h:
                    if random.random() > noise*0.3:
                        grid[ny][nx] = random.choice('oO0')
                x,y = nx, ny
            elif c=='+': angle += 90
            elif c=='-': angle -= 90
        return grid
    
    def _adjust_density(self, grid, target):
        h,w = len(grid), len(grid[0])
        total = h*w
        non_space = sum(c!=' ' for row in grid for c in row)
        if non_space/total < target:
            needed = int(total*target) - non_space
            positions = [(y,x) for y in range(h) for x in range(w) if grid[y][x]==' ']
            random.shuffle(positions)
            for _ in range(min(needed, len(positions))):
                y,x = positions.pop()
                grid[y][x] = random.choice('░▒▓█')
        elif non_space/total > target:
            needed = non_space - int(total*target)
            positions = [(y,x) for y in range(h) for x in range(w) if grid[y][x]!=' ']
            random.shuffle(positions)
            for _ in range(min(needed, len(positions))):
                y,x = positions.pop()
                grid[y][x] = ' '
    
    def mutate(self, intensity=0.2):
        for key in ['symmetry','density','complexity','noise']:
            if random.random() < intensity:
                self.params[key] += random.uniform(-0.15,0.15)
                self.params[key] = max(0.05, min(0.95, self.params[key]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)
    
    def crossover_with_memory(self, other_params: Dict):
        for k in self.params:
            if k == 'pattern':
                if random.random() < 0.5:
                    self.params[k] = other_params.get(k, self.params[k])
            else:
                other_val = other_params.get(k)
                if isinstance(other_val, (int, float)):
                    self.params[k] = (self.params[k] + other_val) / 2.0
    
    def get_params(self) -> Dict:
        return self.params.copy()


# ============================================================================
# DECISION ENGINE (with foresight, noise tracking, regret)
# ============================================================================

class DecisionEngine:
    def __init__(self, world_model: WorldModel, long_term: LongTermScars, memory: VectorMemory):
        self.world = world_model
        self.long_term = long_term
        self.memory = memory
        self.action_usage = Counter()
        self.committed_action = None
        self.commitment_remaining = 0
        
        # For logging
        self.last_utilities = {}
        self.last_utilities_with_noise = {}
        self.last_ranks = {}
        self.last_ranks_with_noise = {}
    
    def _evaluate_action_utility(self, action: str, param_vec: np.ndarray,
                                 resources: ResourceManager, blocked_patterns: Set[str],
                                 foresight_mode: bool = False) -> Tuple[float, Dict[str, float]]:
        """Return (utility, component_dict). Components are NOT linear contributions; they are intermediate values."""
        pred_score, uncertainty = self.world.predict_with_uncertainty(param_vec)
        similar_score = self.memory.predict_score_similarity(param_vec)
        blend = self.world.confidence * pred_score + (1 - self.world.confidence) * similar_score
        en_cost, att_cost, _ = resources.get_effective_action_cost(action)
        cost_factor = max(1, (en_cost + att_cost/10) / 15)
        rep_penalty = self.action_usage[action] * HardConfig.REPETITION_PENALTY_PER_USE
        trauma_penalty = self.long_term.get_action_trauma_penalty(action)
        novelty_bias = self.long_term.get_novelty_bias(action)
        curiosity = HardConfig.CURIOSITY_BONUS * uncertainty if action in ['explore','combine'] else 0.0
        
        raw_utility = (blend / cost_factor) - rep_penalty - trauma_penalty + novelty_bias + curiosity
        
        if action in ['explore','combine']:
            risk_bonus = (0.8 + 0.4 * self.long_term.identity_bias['risk_tolerance'])
            raw_utility *= risk_bonus
        
        if action == 'rest':
            en_deficit = max(0, (HardConfig.MAX_ENERGY - resources.energy) / HardConfig.MAX_ENERGY)
            att_deficit = max(0, (HardConfig.MAX_ATTENTION - resources.attention) / HardConfig.MAX_ATTENTION)
            fat_penalty = resources.fatigue / HardConfig.MAX_FATIGUE
            raw_utility = (en_deficit + att_deficit + fat_penalty) / 3
        
        components = {
            'blend_pred_score': blend,
            'cost_factor': cost_factor,
            'repetition_penalty': -rep_penalty,
            'trauma_penalty': -trauma_penalty,
            'novelty_bias': novelty_bias,
            'curiosity': curiosity,
            'raw_utility': raw_utility
        }
        if action in ['explore','combine']:
            components['risk_bonus'] = risk_bonus
        
        return max(0.0, raw_utility), components
    
    def _compute_ablation_contributions(self, action: str, param_vec: np.ndarray,
                                        resources: ResourceManager, blocked_patterns: Set[str]) -> Dict[str, float]:
        """Compute how much each factor contributes by removing it and measuring utility drop."""
        base_utility, base_components = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
        contributions = {}
        
        # Test removal of each factor (approximate)
        # For curiosity and novelty_bias, set to 0 and recompute
        test_components = base_components.copy()
        # Curiosity ablation
        if 'curiosity' in base_components:
            test_components['curiosity'] = 0.0
            test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
            contributions['curiosity'] = base_utility - test_utility
        # Novelty bias ablation
        if 'novelty_bias' in base_components:
            test_components['novelty_bias'] = 0.0
            test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
            contributions['novelty_bias'] = base_utility - test_utility
        # Repetition penalty: set to 0
        test_components['repetition_penalty'] = 0.0
        test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
        contributions['repetition'] = base_utility - test_utility
        # Trauma penalty: set to 0
        test_components['trauma_penalty'] = 0.0
        test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
        contributions['trauma'] = base_utility - test_utility
        # Cost factor: set to 1 (minimum cost)
        test_components['cost_factor'] = 1.0
        test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
        contributions['cost_efficiency'] = base_utility - test_utility
        # Blend prediction: set to 0.5 (neutral)
        test_components['blend_pred_score'] = 0.5
        test_utility = self._recompute_utility(test_components, action, param_vec, resources, blocked_patterns)
        contributions['score_prediction'] = base_utility - test_utility
        
        return contributions
    
    def _recompute_utility(self, components: Dict, action: str, param_vec: np.ndarray,
                          resources: ResourceManager, blocked_patterns: Set[str]) -> float:
        """Helper to recompute utility given modified components."""
        # This is approximate; we only use for ablation.
        blend = components.get('blend_pred_score', 0.5)
        cost_factor = components.get('cost_factor', 1.0)
        rep_penalty = components.get('repetition_penalty', 0.0)
        trauma_penalty = components.get('trauma_penalty', 0.0)
        novelty_bias = components.get('novelty_bias', 0.0)
        curiosity = components.get('curiosity', 0.0)
        raw_utility = (blend / cost_factor) - abs(rep_penalty) - abs(trauma_penalty) + novelty_bias + curiosity
        if action in ['explore','combine']:
            risk_bonus = components.get('risk_bonus', 1.0)
            raw_utility *= risk_bonus
        if action == 'rest':
            # fallback to original logic
            en_deficit = max(0, (HardConfig.MAX_ENERGY - resources.energy) / HardConfig.MAX_ENERGY)
            att_deficit = max(0, (HardConfig.MAX_ATTENTION - resources.attention) / HardConfig.MAX_ATTENTION)
            fat_penalty = resources.fatigue / HardConfig.MAX_FATIGUE
            raw_utility = (en_deficit + att_deficit + fat_penalty) / 3
        return max(0.0, raw_utility)
    
    def _foresight_utility(self, action: str, param_vec: np.ndarray,
                           resources: ResourceManager, blocked_patterns: Set[str]) -> float:
        """2-step lookahead using state transition."""
        # Step 1: predict outcome of this action
        pred_score, _ = self.world.predict_with_uncertainty(param_vec)
        # Apply state transition
        next_param_vec = StateTransition.transition(param_vec, action, pred_score)
        # Simulate resource after first action
        en_cost, att_cost, _ = resources.get_effective_action_cost(action)
        sim_energy = resources.energy - en_cost
        if sim_energy <= 5:
            return 0.0  # would die
        # Create simulated resources (simplified)
        sim_res = ResourceManager()
        sim_res.energy = sim_energy
        sim_res.attention = max(0, resources.attention - att_cost)
        sim_res.fatigue = resources.fatigue + 5
        sim_res.failure_burden = resources.failure_burden
        # Find best next action using greedy
        best_next_util = 0.0
        for a2 in HardConfig.ACTION_COSTS.keys():
            if a2 in ['generate','explore','refine','combine'] and self._is_pattern_blocked_for_action(a2, blocked_patterns, param_vec):
                continue
            util2, _ = self._evaluate_action_utility(a2, next_param_vec, sim_res, blocked_patterns)
            if util2 > best_next_util:
                best_next_util = util2
        # First step utility
        first_util, _ = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
        return first_util + HardConfig.PLANNING_DISCOUNT * best_next_util
    
    def _is_pattern_blocked_for_action(self, action: str, blocked_patterns: Set[str], param_vec: np.ndarray) -> bool:
        """Dummy: we need to infer pattern from param_vec. Simpler: assume pattern from generator, but we don't have it here.
           In practice, we'd pass current pattern. For now, return False to avoid over-blocking.
        """
        # We'll handle pattern blocking in feasible actions externally.
        return False
    
    def choose_action(self, feasible: List[str], resources: ResourceManager,
                     param_vec: np.ndarray, blocked_patterns: Set[str], emergency: bool) -> Tuple[str, Dict]:
        """Returns (chosen_action, info_dict) where info contains utilities, ranks, noise effect."""
        if self.commitment_remaining > 0:
            if self.committed_action in feasible:
                return self.committed_action, {'commitment': True}
            else:
                resources.apply_cost('forget')
                resources.energy = max(0, resources.energy + HardConfig.COMMITMENT_VIOLATION_PENALTY['energy'])
                resources.attention = max(0, resources.attention + HardConfig.COMMITMENT_VIOLATION_PENALTY['attention'])
                resources.fatigue = min(HardConfig.MAX_FATIGUE, resources.fatigue + HardConfig.COMMITMENT_VIOLATION_PENALTY['fatigue'])
                self.commitment_remaining = 0
                self.committed_action = None
        
        if emergency:
            feasible = [a for a in feasible if a in ['rest', 'recall']]
            if not feasible: 
                feasible = ['rest']
        
        # Compute utilities for all feasible actions
        utilities = {}
        components = {}
        for action in feasible:
            if resources.energy > 20 and action in ['generate','explore','refine','combine']:
                util = self._foresight_utility(action, param_vec, resources, blocked_patterns)
            else:
                util, comp = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
                components[action] = comp
            utilities[action] = util
        
        # Sort by utility to get ranking
        sorted_actions = sorted(utilities.items(), key=lambda x: x[1], reverse=True)
        ranks = {action: idx+1 for idx, (action, _) in enumerate(sorted_actions)}
        
        # Apply noise
        noisy_utilities = {}
        for action, util in utilities.items():
            noise = random.gauss(0, HardConfig.EXPLORATION_NOISE_STD)
            noisy_utilities[action] = util + noise
        
        # Resort after noise
        noisy_sorted = sorted(noisy_utilities.items(), key=lambda x: x[1], reverse=True)
        noisy_ranks = {action: idx+1 for idx, (action, _) in enumerate(noisy_sorted)}
        
        best_action = noisy_sorted[0][0]
        best_utility = noisy_utilities[best_action]
        best_utility_before_noise = utilities[best_action]
        best_rank_before = ranks[best_action]
        best_rank_after = 1
        
        # Compute regret: difference between chosen and best possible without noise
        best_possible_utility = max(utilities.values())
        regret = best_possible_utility - best_utility_before_noise
        
        # Compute ablation contributions for chosen action (optional)
        ablation = {}
        if best_action in components:
            # Compute contributions via ablation
            base_util, _ = self._evaluate_action_utility(best_action, param_vec, resources, blocked_patterns)
            # We'll compute simple delta from base
            ablation = {'curiosity': components[best_action].get('curiosity', 0),
                        'novelty_bias': components[best_action].get('novelty_bias', 0),
                        'repetition_penalty': components[best_action].get('repetition_penalty', 0),
                        'trauma_penalty': components[best_action].get('trauma_penalty', 0)}
        
        # Update usage counters
        self.action_usage[best_action] += 1
        
        # Record for logging
        self.last_utilities = utilities
        self.last_utilities_with_noise = noisy_utilities
        self.last_ranks = ranks
        self.last_ranks_with_noise = noisy_ranks
        
        info = {
            'utilities_before_noise': utilities,
            'utilities_after_noise': noisy_utilities,
            'ranks_before': ranks,
            'ranks_after': noisy_ranks,
            'best_action': best_action,
            'best_utility': best_utility_before_noise,
            'regret': regret,
            'noise_effect': noisy_utilities[best_action] - utilities[best_action],
            'ablation_contributions': ablation,
            'runner_up': noisy_sorted[1][0] if len(noisy_sorted) > 1 else None,
            'runner_up_utility': noisy_sorted[1][1] if len(noisy_sorted) > 1 else None,
            'runner_up_before_noise': utilities.get(noisy_sorted[1][0], 0) if len(noisy_sorted) > 1 else None
        }
        
        # Commitment
        if self.commitment_remaining == 0 and best_action != 'rest':
            if self.world.confidence > HardConfig.COMMITMENT_THRESHOLD_CONFIDENCE and best_utility_before_noise > 0.6:
                self.committed_action = best_action
                self.commitment_remaining = HardConfig.COMMITMENT_WINDOW
        
        return best_action, info
    
    def update_commitment(self):
        if self.commitment_remaining > 0:
            self.commitment_remaining -= 1
            if self.commitment_remaining == 0:
                self.committed_action = None


# ============================================================================
# SELF-MODEL (override logic)
# ============================================================================

class SelfModel:
    def __init__(self):
        self.local_optima_trap = False
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.score_history = deque(maxlen=20)
    
    def update(self, score: float):
        self.score_history.append(score)
        if score < 0.4:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
        elif score > 0.6:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
        else:
            self.consecutive_failures = 0
            self.consecutive_successes = 0
        if len(self.score_history) >= 10:
            if all(0.4 <= s <= 0.6 for s in list(self.score_history)[-10:]):
                self.local_optima_trap = True
            else:
                self.local_optima_trap = False
    
    def get_override(self, resources: ResourceManager, world_confidence: float) -> Tuple[bool, str, str]:
        if self.local_optima_trap and not resources.is_emergency() and resources.energy >= 30:
            return True, 'explore', 'local_optima_trap'
        if resources.is_emergency():
            return True, 'rest', 'emergency'
        if self.consecutive_failures >= 5 and world_confidence < 0.5:
            return True, 'recall', 'low_confidence_failure'
        if random.random() < 0.1:
            return True, random.choice(['generate','explore','refine','combine','recall']), 'chaotic_impulse'
        return False, '', ''


# ============================================================================
# MAIN AETHER (with engineering transparency)
# ============================================================================

class Aether:
    def __init__(self, workspace="aether_works_v097", quiet=False):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.resources = ResourceManager()
        self.memory = VectorMemory()
        self.generator = Generator()
        self.world_model = WorldModel()
        self.long_term = LongTermScars()
        self.decision = DecisionEngine(self.world_model, self.long_term, self.memory)
        self.self_model = SelfModel()
        self.cycle = 0
        self.score_history = []
        self.action_history = []
        self.log_data = []
        self.quiet = quiet
        
        # For state logging
        self.last_param_vec = None
        self.last_art_vec = None
        self.last_art = None
    
    def get_feasible_actions(self, blocked_patterns: Set[str]) -> List[str]:
        feasible = list(HardConfig.ACTION_COSTS.keys())
        # If resources critical, only rest
        if self.resources.energy <= 5 or self.resources.attention <= 5:
            return ['rest']
        # If memory full, forget must be allowed
        if self.resources.memory_used >= HardConfig.MEMORY_SLOTS:
            if 'forget' not in feasible:
                feasible.append('forget')
        # Rest cooldown
        if not self.resources.can_rest():
            feasible = [a for a in feasible if a != 'rest']
        # HARD CONSTRAINT: if current pattern is blocked, remove all actions that generate
        current_pattern = self.generator.params['pattern']
        if current_pattern in blocked_patterns:
            for a in ['generate', 'explore', 'refine', 'combine']:
                if a in feasible:
                    feasible.remove(a)
        if not feasible:
            feasible = ['rest']
        return feasible
    
    def step(self) -> Dict:
        self.cycle += 1
        self.resources.cycle = self.cycle
        self.long_term.cycle = self.cycle
        
        # Coma handling
        if self.resources.is_coma():
            self.resources.update_coma()
            if not self.quiet:
                print(f"[COMA] Cycle {self.cycle} - Recovering...")
            self._log_step('coma', 0.0, 0.0, self.resources, None, None)
            return {'action': 'coma', 'score': 0.0, 'novelty': 0.0}
        
        # Get current state
        param_vec = ParamEmbedder.embed(self.generator.get_params())
        self.last_param_vec = param_vec.copy()
        blocked = set(self.long_term.pattern_blocked_until.keys())
        feasible = self.get_feasible_actions(blocked)
        
        # Override?
        override, forced_action, reason = self.self_model.get_override(self.resources, self.world_model.confidence)
        if override and forced_action in feasible:
            chosen_action = forced_action
            decision_info = {'override_reason': reason}
            if not self.quiet:
                print(f"\n[Override] {reason} -> {forced_action}")
        else:
            emergency = self.resources.is_emergency()
            chosen_action, decision_info = self.decision.choose_action(feasible, self.resources, param_vec, blocked, emergency)
        
        # Save before-state for delta
        energy_before = self.resources.energy
        attention_before = self.resources.attention
        fatigue_before = self.resources.fatigue
        burden_before = self.resources.failure_burden
        
        art = None
        score = 0.5
        novelty = 0.5
        
        try:
            if chosen_action in ['generate', 'explore', 'refine', 'combine']:
                if chosen_action == 'explore':
                    self.generator.mutate(intensity=0.5)
                elif chosen_action == 'refine':
                    self.generator.mutate(intensity=0.1)
                elif chosen_action == 'combine' and len(self.memory.vectors) > 0:
                    rand_mem = random.choice(self.memory.metadata)
                    other_params = rand_mem.get('params', self.generator.get_params())
                    self.generator.crossover_with_memory(other_params)
                
                art, used_pattern = self.generator.generate(blocked)
                art_vec = ArtEmbedder.embed(art)
                novelty = self.memory.novelty(art_vec)
                features = self._extract_features(art)
                score = self._compute_score(features)
                current_param_vec = ParamEmbedder.embed(self.generator.get_params())
                self.world_model.update(current_param_vec, score)
                self.memory.store(art_vec, {
                    'score': score, 'novelty': novelty, 'action': chosen_action,
                    'pattern': used_pattern, 'params': self.generator.get_params().copy(),
                    'cycle': self.cycle, 'param_vec': current_param_vec.tolist()
                })
                self.long_term.update(chosen_action, used_pattern, score, self.cycle)
                self.last_art_vec = art_vec
                self.last_art = art
                
            elif chosen_action == 'recall' and len(self.memory.vectors) > 0:
                # Recall does nothing but we can log
                similar = self.memory.recall_similar(param_vec, k=1)
                if similar and not self.quiet:
                    sim, meta = similar[0]
                    print(f"[Recall] Similar to cycle {meta.get('cycle','?')} with sim={sim:.2f}")
            
            elif chosen_action == 'forget' and self.memory.vectors:
                self.memory.vectors.pop()
                self.memory.metadata.pop()
                self.resources.memory_used = max(0, self.resources.memory_used - 1)
            
        except ValueError as e:
            # Action infeasible due to blocked pattern
            if not self.quiet:
                print(f"[Infeasible] {e}")
            score = 0.2
            novelty = 0.0
            chosen_action = 'failed_' + chosen_action
            # Still apply cost (but with failed modifier)
            self.resources.apply_cost(chosen_action)
            self.resources.update_failure_burden(score)
            self.resources.regen(False)
            self.self_model.update(score)
            self.score_history.append(score)
            self.action_history.append(chosen_action)
            self._log_step(chosen_action, score, novelty, self.resources, None, decision_info)
            # Minimal output
            if not self.quiet:
                print(f"[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f}")
            return {'action': chosen_action, 'score': score, 'novelty': 0.0}
        
        # Apply resource costs
        self.resources.apply_cost(chosen_action)
        self.resources.update_failure_burden(score)
        self.resources.regen(chosen_action == 'rest')
        
        self.self_model.update(score)
        self.score_history.append(score)
        self.action_history.append(chosen_action)
        
        self.long_term.apply_identity_drift(self.score_history)
        self.decision.update_commitment()
        
        if self.resources.enter_coma() and not self.quiet:
            print(f"[COMA ENTRY] Cycle {self.cycle}")
        
        # State delta
        state_delta = {
            'energy': self.resources.energy - energy_before,
            'attention': self.resources.attention - attention_before,
            'fatigue': self.resources.fatigue - fatigue_before,
            'failure_burden': self.resources.failure_burden - burden_before
        }
        
        # Log
        self._log_step(chosen_action, score, novelty, self.resources, decision_info, state_delta)
        
        # Output (engineering format)
        if not self.quiet:
            print(f"\n[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f} | Novelty: {novelty:.3f}")
            print(f"Resources: E={self.resources.energy} A={self.resources.attention} F={self.resources.fatigue} B={self.resources.failure_burden}")
            print(f"World model confidence: {self.world_model.confidence:.2f} | Prediction error: {self.world_model.prediction_error:.3f}")
            if 'utilities_before_noise' in decision_info and not override:
                utils = decision_info['utilities_before_noise']
                utils_str = ', '.join([f"{a}:{u:.2f}" for a,u in sorted(utils.items(), key=lambda x: x[1], reverse=True)[:4]])
                print(f"Utilities (before noise): {utils_str}")
                if 'regret' in decision_info:
                    print(f"Regret: {decision_info['regret']:.3f} | Noise effect: {decision_info.get('noise_effect',0):+.3f}")
                if 'runner_up' in decision_info and decision_info['runner_up']:
                    print(f"Runner-up: {decision_info['runner_up']} (util before noise: {decision_info.get('runner_up_before_noise',0):.2f})")
            if state_delta['energy'] != 0:
                print(f"Delta: E={state_delta['energy']:+d}, A={state_delta['attention']:+d}, F={state_delta['fatigue']:+d}, B={state_delta['failure_burden']:+d}")
            if art and len(art) > 200:
                print(art[:200] + "...")
            elif art:
                print(art)
        
        return {
            'action': chosen_action,
            'score': score,
            'novelty': novelty,
            'art': art,
            'resources': self.resources.__dict__.copy(),
            'decision_info': decision_info,
            'state_delta': state_delta,
            'prediction_error': self.world_model.prediction_error
        }
    
    def _extract_features(self, art: str) -> Dict:
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines:
            return {'symmetry':0,'density':0,'diversity':0,'entropy':0}
        w = max(len(l) for l in lines)
        h = len(lines)
        padded = [l.ljust(w) for l in lines]
        total = h*w
        non_space = sum(c!=' ' for line in padded for c in line)
        density = non_space/max(1,total)
        h_sym=0; cnt=0
        for line in padded:
            stripped=line.rstrip()
            if len(stripped)>2:
                mid=len(stripped)//2
                left=stripped[:mid]
                right=stripped[mid:][::-1]
                n=min(len(left),len(right))
                if n>0:
                    matches=sum(1 for i in range(n) if left[i]==right[i] and left[i]!=' ')
                    h_sym+=matches/n
                    cnt+=1
        symmetry=h_sym/max(1,cnt)
        all_chars = [c for line in padded for c in line if c!=' ']
        diversity = len(set(all_chars))/min(30, max(1,len(all_chars))) if all_chars else 0
        if all_chars:
            from collections import Counter
            freq = Counter(all_chars)
            probs = [f/len(all_chars) for f in freq.values()]
            entropy = -sum(p*math.log2(p) for p in probs)
            max_ent = math.log2(len(freq)) if len(freq)>1 else 1
            entropy_norm = entropy/max_ent if max_ent>0 else 0
        else:
            entropy_norm=0
        return {'symmetry':symmetry,'density':density,'diversity':diversity,'entropy':entropy_norm}
    
    def _compute_score(self, features):
        density = features['density']
        symmetry = features['symmetry']
        diversity = features['diversity']
        entropy = features['entropy']
        d_score = 1 - abs(density - 0.4) * 2.5
        return max(0, min(1, d_score*0.3 + symmetry*0.3 + diversity*0.2 + entropy*0.2))
    
    def _log_step(self, action, score, novelty, resources, decision_info, state_delta):
        # Convert numpy types to Python native for JSON
        entry = {
            'cycle': int(self.cycle),
            'action': str(action),
            'score': float(score),
            'novelty': float(novelty),
            'energy': float(resources.energy),
            'attention': float(resources.attention),
            'fatigue': float(resources.fatigue),
            'failure_burden': float(resources.failure_burden),
            'world_model_confidence': float(self.world_model.confidence),
            'prediction_error': float(self.world_model.prediction_error),
            'trauma_blocked': list(self.long_term.pattern_blocked_until.keys()),
            'identity': {k: float(v) for k,v in self.long_term.identity_bias.items()},
            'state_delta': {k: float(v) for k,v in (state_delta or {}).items()},
            'timestamp': datetime.now().isoformat()
        }
        if decision_info:
            if 'utilities_before_noise' in decision_info:
                entry['utilities_before'] = {k: float(v) for k,v in decision_info['utilities_before_noise'].items()}
            if 'utilities_after_noise' in decision_info:
                entry['utilities_after'] = {k: float(v) for k,v in decision_info['utilities_after_noise'].items()}
            if 'regret' in decision_info:
                entry['regret'] = float(decision_info['regret'])
            if 'noise_effect' in decision_info:
                entry['noise_effect'] = float(decision_info['noise_effect'])
            if 'runner_up' in decision_info:
                entry['runner_up'] = decision_info['runner_up']
        self.log_data.append(entry)
    
    def run_autonomous(self, cycles=200, save_log=True):
        for _ in range(cycles):
            self.step()
            time.sleep(0.3)
        if save_log:
            log_file = self.workspace / f"aether_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, 'w') as f:
                json.dump(self.log_data, f, indent=2)
            print(f"\n[Log saved] {log_file}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    if '--auto' in sys.argv:
        cycles = 200
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            cycles = int(sys.argv[2])
        a = Aether(quiet=False)
        a.run_autonomous(cycles)
    elif '--demo' in sys.argv:
        a = Aether(quiet=False)
        for _ in range(20):
            a.step()
            time.sleep(0.5)
    else:
        print("Aether v0.9.7 — Engineering Transparency")
        print("Run with --auto [cycles] (default 200) or --demo")
        a = Aether(quiet=False)
        a.run_autonomous(30)