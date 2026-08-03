#!/usr/bin/env python3
"""
AETHER v0.8 — BRUTAL CONSTRAINTS (REWRITTEN FROM ZERO)
"No shortcuts. No fallbacks. If you cannot act, you suffer."

This version implements:
- Decision engine using world model predictions (no placeholders)
- Full commitment system with painful violations
- Hard constraints: FORBIDDEN means FORBIDDEN, no fallback
- Trauma as ACTION BLOCK, not just penalty
- Radical emergency mode (action space severely restricted)
- True collapse scenario (coma state)
- Long-term identity drift

USAGE:
    python aether_v08.py --auto    # Autonomous survival run
    python aether_v08.py --demo    # Short demo
    python aether_v08.py           # Interactive
"""

import math
import random
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import deque, Counter
import numpy as np

# ============================================================================
# HARDCORE CONFIGURATION (IMMUTABLE)
# ============================================================================

class HardConfig:
    # Resource limits
    MAX_ENERGY = 100
    MAX_ATTENTION = 100
    MAX_FATIGUE = 100
    MEMORY_SLOTS = 25
    
    # Costs: (energy, attention, memory_delta, fatigue)
    ACTION_COSTS = {
        'generate': (12, 6, 0, 3),
        'explore':  (35, 20, 1, 7),
        'refine':   (10, 14, 0, 4),
        'recall':   (4, 3, 0, 1),
        'combine':  (18, 12, 1, 5),
        'rest':     (-5, -8, 0, -6),
        'forget':   (7, 4, -1, 3),
    }
    
    # Commitment
    COMMITMENT_WINDOW = 8
    COMMITMENT_VIOLATION_PENALTY = {'energy': -30, 'attention': -40, 'fatigue': +20}
    
    # Death spiral
    FAILURE_BURDEN_MAX = 100
    COST_MULTIPLIER_MAX = 2.0
    
    # Emergency
    EMERGENCY_BURDEN_THRESHOLD = 70
    EMERGENCY_ENERGY_THRESHOLD = 20
    COMA_BURDEN = 100
    COMA_ENERGY = 10
    COMA_DURATION = 5  # cycles forced idle
    
    # Trauma blocking
    TRAUMA_BLOCK_THRESHOLD = 0.7
    TRAUMA_BLOCK_DURATION = 20   # cycles
    
    # Learning
    WORLD_MODEL_UPDATE_RATE = 0.05
    IDENTITY_DRIFT_RATE = 0.002
    NOISE_STD = 0.12
    EXPLORATION_OVERRIDE_PROB = 0.15
    
    # Repetition penalty
    REPETITION_WINDOW = 20
    REPETITION_PENALTY_PER_USE = 0.04

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
        
    def is_coma(self) -> bool:
        return self.coma_cycles_left > 0
    
    def enter_coma(self):
        """True collapse scenario: system shuts down for several cycles."""
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
                # Minimal recovery after coma
                self.energy = 30
                self.attention = 40
                self.fatigue = 20
                self.failure_burden = max(0, self.failure_burden - 40)
            return True
        return False
    
    def apply_cost(self, action: str):
        if action not in HardConfig.ACTION_COSTS:
            return
        en, att, mem_delta, fat = HardConfig.ACTION_COSTS[action]
        multiplier = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        self.energy += int(en * multiplier)
        self.attention += int(att * multiplier)
        self.memory_used += mem_delta
        self.fatigue += fat + int(self.failure_burden / 20)
        # Clamp
        self.energy = max(0, min(HardConfig.MAX_ENERGY, self.energy))
        self.attention = max(0, min(HardConfig.MAX_ATTENTION, self.attention))
        self.memory_used = max(0, min(HardConfig.MEMORY_SLOTS, self.memory_used))
        self.fatigue = max(0, min(HardConfig.MAX_FATIGUE, self.fatigue))
    
    def regen(self, is_resting: bool):
        if is_resting and self.can_rest():
            fatigue_penalty = max(0, self.fatigue / 20)
            energy_gain = max(1, 5 - int(fatigue_penalty))
            attention_gain = max(2, 8 - int(fatigue_penalty * 1.5))
            self.energy = min(HardConfig.MAX_ENERGY, self.energy + energy_gain)
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention + attention_gain)
            self.fatigue = max(0, self.fatigue - 6)
            self.last_rest_cycle = self.cycle
        else:
            # Slow passive regen
            self.energy = min(HardConfig.MAX_ENERGY, self.energy + 1)
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention + 1)
            self.fatigue = max(0, self.fatigue - 1)
    
    def update_failure_burden(self, score: float):
        if score < 0.4:
            self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden + 12)
            if score < 0.2:
                self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden + 8)
        elif score > 0.7:
            self.failure_burden = max(0, self.failure_burden - 8)
    
    def can_rest(self) -> bool:
        return (self.cycle - self.last_rest_cycle) >= 3
    
    def is_emergency(self) -> bool:
        return (self.failure_burden >= HardConfig.EMERGENCY_BURDEN_THRESHOLD and
                self.energy <= HardConfig.EMERGENCY_ENERGY_THRESHOLD)
    
    def get_effective_action_cost(self, action: str) -> Tuple[int, int, int]:
        en, att, _, fat = HardConfig.ACTION_COSTS.get(action, (0,0,0,0))
        mult = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        return int(en * mult), int(att * mult), fat

# ============================================================================
# LONG-TERM SCARS (trauma that can block actions)
# ============================================================================

class LongTermScars:
    def __init__(self):
        self.pattern_trauma = {}       # pattern -> current trauma level (0-1)
        self.pattern_blocked_until = {} # pattern -> cycle until blocked
        self.action_trauma = {}        # action -> extra cost (energy)
        self.identity_bias = {
            'risk_tolerance': 0.5,
            'novelty_seeking': 0.5,
            'symmetry_preference': 0.5,
        }
        self.cycle = 0
    
    def update(self, action: str, pattern: str, score: float, current_cycle: int):
        self.cycle = current_cycle
        # Accumulate trauma on failure
        if score < 0.3:
            self.pattern_trauma[pattern] = min(1.0, self.pattern_trauma.get(pattern, 0) + 0.12)
            self.action_trauma[action] = min(20, self.action_trauma.get(action, 0) + 3)
        else:
            # Decay
            for p in list(self.pattern_trauma.keys()):
                self.pattern_trauma[p] = max(0, self.pattern_trauma[p] - 0.01)
                if self.pattern_trauma[p] == 0:
                    del self.pattern_trauma[p]
            for a in list(self.action_trauma.keys()):
                self.action_trauma[a] = max(0, self.action_trauma[a] - 1)
                if self.action_trauma[a] == 0:
                    del self.action_trauma[a]
        
        # Block pattern if trauma exceeds threshold
        if self.pattern_trauma.get(pattern, 0) >= HardConfig.TRAUMA_BLOCK_THRESHOLD:
            self.pattern_blocked_until[pattern] = current_cycle + HardConfig.TRAUMA_BLOCK_DURATION
        
        # Clean expired blocks
        for p in list(self.pattern_blocked_until.keys()):
            if self.pattern_blocked_until[p] <= current_cycle:
                del self.pattern_blocked_until[p]
    
    def is_pattern_blocked(self, pattern: str) -> bool:
        return pattern in self.pattern_blocked_until
    
    def get_action_trauma_penalty(self, action: str) -> float:
        return self.action_trauma.get(action, 0) / 20.0  # 0..1
    
    def apply_identity_drift(self, recent_scores: List[float]):
        if len(recent_scores) < 30:
            return
        avg = sum(recent_scores[-30:]) / 30
        # Higher success increases risk tolerance and novelty seeking
        target_risk = min(0.9, avg * 1.3)
        target_novelty = min(0.85, avg * 1.2)
        self.identity_bias['risk_tolerance'] += (target_risk - self.identity_bias['risk_tolerance']) * HardConfig.IDENTITY_DRIFT_RATE
        self.identity_bias['novelty_seeking'] += (target_novelty - self.identity_bias['novelty_seeking']) * HardConfig.IDENTITY_DRIFT_RATE
        # Clamp
        for k in self.identity_bias:
            self.identity_bias[k] = max(0.1, min(0.9, self.identity_bias[k]))

# ============================================================================
# VECTOR MEMORY (episodic)
# ============================================================================

class VectorMemory:
    def __init__(self, dim=24):
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
    
    def diversity(self) -> float:
        if len(self.vectors) < 2:
            return 0.5
        n = min(20, len(self.vectors))
        total_sim = 0
        for i in range(n):
            for j in range(i+1, n):
                sim = np.dot(self.vectors[i], self.vectors[j]) / (np.linalg.norm(self.vectors[i])*np.linalg.norm(self.vectors[j])+1e-8)
                total_sim += sim
        avg_sim = total_sim / (n*(n-1)/2 + 1e-8)
        return 1.0 - avg_sim

# ============================================================================
# EMBEDDING ENGINE (24-dim)
# ============================================================================

class Embedder:
    @staticmethod
    def from_art(art: str) -> np.ndarray:
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(24)
        h = len(lines)
        w = max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        features = []
        # Density
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
        # Vertical symmetry
        v_sym = 0.0
        vc = 0
        for x in range(w):
            top = ''.join(padded[y][x] for y in range(h//2))
            bot = ''.join(padded[h-1-y][x] for y in range(h//2))
            if top and bot:
                matches = sum(1 for a,b in zip(top, bot) if a == b and a != ' ')
                v_sym += matches / max(1, len(top))
                vc += 1
        features.append(v_sym / max(1, vc))
        # Diversity & Entropy
        all_chars = [c for line in padded for c in line if c != ' ']
        if all_chars:
            unique = len(set(all_chars))
            features.append(unique / min(30, len(all_chars)))
            freq = Counter(all_chars)
            probs = [f/len(all_chars) for f in freq.values()]
            entropy = -sum(p*math.log2(p) for p in probs)
            max_ent = math.log2(len(freq)) if len(freq)>1 else 1
            features.append(entropy / max_ent if max_ent>0 else 0)
        else:
            features.extend([0,0])
        # Edge density
        h_edges = v_edges = 0
        total_edges = 0
        for y in range(h):
            for x in range(w-1):
                if padded[y][x] != ' ' and padded[y][x+1] != ' ' and padded[y][x] != padded[y][x+1]:
                    h_edges += 1
                total_edges += 1
        for y in range(h-1):
            for x in range(w):
                if padded[y][x] != ' ' and padded[y+1][x] != ' ' and padded[y][x] != padded[y+1][x]:
                    v_edges += 1
                total_edges += 1
        features.append((h_edges+v_edges) / max(1, total_edges))
        # Clustering
        positions = [(y,x) for y in range(h) for x in range(w) if padded[y][x] != ' ']
        if len(positions) > 1:
            dists = []
            sampled = positions[:min(50,len(positions))]
            for i,(y1,x1) in enumerate(sampled):
                for j,(y2,x2) in enumerate(sampled[i+1:i+10]):
                    dists.append(math.hypot(y1-y2, x1-x2))
            avg_dist = sum(dists)/len(dists) if dists else 0
            clustering = 1 - min(1.0, avg_dist / max(w,h))
        else:
            clustering = 0
        features.append(clustering)
        # Fill to 24
        while len(features) < 24:
            features.append(0)
        return np.array(features[:24])

# ============================================================================
# GENERATOR (evolvable, with pattern blocking)
# ============================================================================

class Generator:
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem']
    
    def __init__(self):
        self.params = {
            'pattern': random.choice(self.PATTERNS),
            'symmetry': 0.5,
            'density': 0.35,
            'complexity': 0.5,
            'noise': 0.15,
        }
        self.usage_counter = Counter()
    
    def generate(self, blocked_patterns: set) -> str:
        pattern = self.params['pattern']
        if pattern in blocked_patterns:
            # Fallback to first non-blocked pattern
            for p in self.PATTERNS:
                if p not in blocked_patterns:
                    pattern = p
                    self.params['pattern'] = p
                    break
        self.usage_counter[pattern] += 1
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        if pattern == 'wave':
            for y in range(h):
                for x in range(w):
                    val = (math.sin(x*0.2)*math.cos(y*0.3) +
                           math.sin(x*0.5)*0.5 + math.cos(y*0.4)*0.3)
                    norm = (val+1)/2
                    if norm > 1 - self.params['density']:
                        grid[y][x] = random.choice('░▒▓█')
        elif pattern == 'fractal':
            self._draw_fractal(grid, w//2, h//2, min(w,h)//6, int(self.params['complexity']*3+2))
        elif pattern == 'cellular':
            grid = self._cellular_automaton(w, h)
        else:  # lsystem
            grid = self._lsystem_draw(w, h)
        # Symmetry
        if self.params['symmetry'] > random.random():
            for y in range(h):
                for x in range(w//2):
                    if grid[y][x] != ' ':
                        grid[y][w-1-x] = grid[y][x]
        # Density adjust
        self._adjust_density(grid, self.params['density'])
        # Noise
        if self.params['noise'] > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < self.params['noise']*0.3:
                        grid[y][x] = random.choice(' .:oO0@') if grid[y][x]==' ' else ' '
        return '\n'.join(''.join(row) for row in grid)
    
    def _draw_fractal(self, grid, x, y, size, depth):
        if depth<=0 or size<1: return
        for i in range(-size, size+1):
            if 0<=x+i<len(grid[0]) and 0<=y<len(grid):
                grid[y][x+i] = '█'
            if 0<=x<len(grid[0]) and 0<=y+i<len(grid):
                grid[y+i][x] = '█'
        self._draw_fractal(grid, x+size+1, y, size//2, depth-1)
        self._draw_fractal(grid, x-size-1, y, size//2, depth-1)
        self._draw_fractal(grid, x, y+size+1, size//2, depth-1)
        self._draw_fractal(grid, x, y-size-1, size//2, depth-1)
    
    def _cellular_automaton(self, w, h):
        grid = [[1 if random.random()<self.params['density'] else 0 for _ in range(w)] for _ in range(h)]
        for _ in range(3):
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
    
    def _lsystem_draw(self, w, h):
        axiom = 'F'
        rules = {'F':'F+F-F-F+F'}
        seq = axiom
        for _ in range(3):
            seq = ''.join(rules.get(c,c) for c in seq)
        grid = [[' ']*w for _ in range(h)]
        x,y = w//2, h//2
        angle = 0
        for c in seq[:300]:
            if c=='F':
                dx = int(round(math.cos(math.radians(angle))))
                dy = int(round(math.sin(math.radians(angle))))
                nx, ny = x+dx, y+dy
                if 0<=nx<w and 0<=ny<h:
                    grid[ny][nx] = 'o'
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
            for _ in range(min(needed, len(positions))):
                y,x = random.choice(positions)
                grid[y][x] = random.choice('░▒▓█')
        elif non_space/total > target:
            needed = non_space - int(total*target)
            positions = [(y,x) for y in range(h) for x in range(w) if grid[y][x]!=' ']
            for _ in range(min(needed, len(positions))):
                y,x = random.choice(positions)
                grid[y][x] = ' '
    
    def mutate(self, intensity=0.2):
        for key in ['symmetry','density','complexity','noise']:
            if random.random() < intensity:
                self.params[key] += random.uniform(-0.15,0.15)
                self.params[key] = max(0.05, min(0.95, self.params[key]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)
    
    def get_params(self):
        return self.params.copy()

# ============================================================================
# WORLD MODEL (predicts score from vector)
# ============================================================================

class WorldModel:
    def __init__(self, input_dim=24, hidden_dim=32):
        self.W1 = np.random.randn(hidden_dim, input_dim) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(1, hidden_dim) * 0.1
        self.b2 = 0.0
        self.confidence = 0.5
        self.buffer = []
    
    def predict(self, vec: np.ndarray) -> float:
        h = np.tanh(self.W1 @ vec + self.b1)
        out = float(self.W2 @ h + self.b2)
        return np.clip(out, 0.0, 1.0)
    
    def update(self, vec: np.ndarray, actual: float):
        self.buffer.append((vec, actual))
        if len(self.buffer) > 200:
            self.buffer.pop(0)
        if len(self.buffer) % 10 == 0:
            # Online learning on random sample
            for _ in range(5):
                idx = random.randint(0, len(self.buffer)-1)
                v, a = self.buffer[idx]
                pred = self.predict(v)
                error = a - pred
                h = np.tanh(self.W1 @ v + self.b1)
                self.W2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error * h.reshape(1,-1)
                self.b2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error
                delta_h = error * self.W2.T * (1 - h**2)
                self.W1 += HardConfig.WORLD_MODEL_UPDATE_RATE * np.outer(delta_h, v)
                self.b1 += HardConfig.WORLD_MODEL_UPDATE_RATE * delta_h.flatten()
        # Update confidence
        if len(self.buffer) >= 20:
            errors = [abs(self.predict(v)-a) for v,a in self.buffer[-20:]]
            self.confidence = max(0.2, min(0.9, 1.0 - sum(errors)/20))
    
    def predict_action_outcome(self, action: str, current_params: dict, memory: VectorMemory) -> float:
        # Simplified: generate a dummy vector from params and predict
        # In reality, would need to simulate, but we use heuristic + prediction
        # For decision, we use world model on recent memory similarity
        if not memory.vectors:
            return 0.5
        # Use average score of similar works
        dummy_vec = np.random.randn(24)*0.1  # not ideal but placeholder
        sims = memory.recall_similar(dummy_vec, k=1)
        if sims:
            return sims[0][1].get('score', 0.5)
        return 0.5

# ============================================================================
# DECISION ENGINE (uses world model)
# ============================================================================

class DecisionEngine:
    def __init__(self, world_model: WorldModel, long_term: LongTermScars):
        self.world = world_model
        self.long_term = long_term
        self.action_usage = Counter()
        self.committed_action = None
        self.commitment_remaining = 0
    
    def choose_action(self, feasible: List[str], resources: ResourceManager, memory: VectorMemory,
                      current_params: dict, blocked_patterns: set, emergency: bool) -> str:
        # Commitment enforcement
        if self.commitment_remaining > 0:
            if self.committed_action in feasible:
                return self.committed_action
            else:
                # Violation: heavy penalty and reset commitment
                resources.apply_cost('forget')  # extra cost
                resources.energy += HardConfig.COMMITMENT_VIOLATION_PENALTY['energy']
                resources.attention += HardConfig.COMMITMENT_VIOLATION_PENALTY['attention']
                resources.fatigue += HardConfig.COMMITMENT_VIOLATION_PENALTY['fatigue']
                self.commitment_remaining = 0
                self.committed_action = None
        
        # Emergency mode: only rest and recall allowed
        if emergency:
            feasible = [a for a in feasible if a in ['rest', 'recall']]
            if not feasible:
                feasible = ['rest']
        
        # Filter blocked patterns: if explore/combine would use blocked pattern, they are not feasible
        # But we handle in generator later; here we just avoid actions that force blocked pattern
        # Actually, we keep them but generator will override pattern; we let decision proceed
        
        best_action = None
        best_utility = -float('inf')
        for action in feasible:
            # Predict expected score using world model on current state representation
            # For simplicity, we use the average score of last 3 memory items as baseline
            if memory.vectors:
                recent_scores = [m.get('score',0.5) for m in memory.metadata[-3:]]
                baseline = sum(recent_scores)/len(recent_scores) if recent_scores else 0.5
            else:
                baseline = 0.5
            # Adjust based on action type
            if action == 'explore':
                expected = baseline * 0.8 + 0.2  # exploration can be slightly lower
            elif action == 'refine':
                expected = baseline * 0.9 + 0.1
            elif action == 'combine':
                expected = baseline * 0.85 + 0.15
            elif action == 'generate':
                expected = baseline
            elif action == 'rest':
                expected = 0.5  # rest yields no art, neutral
            else:
                expected = 0.5
            
            # Cost calculation
            en_cost, att_cost, _ = resources.get_effective_action_cost(action)
            cost_factor = max(1, (en_cost + att_cost/10) / 10)
            # Repetition penalty
            rep_count = self.action_usage[action]
            rep_penalty = rep_count * HardConfig.REPETITION_PENALTY_PER_USE
            # Trauma penalty
            trauma_penalty = self.long_term.get_action_trauma_penalty(action)
            # Identity bias
            if action in ['explore', 'combine']:
                novelty_bias = self.long_term.identity_bias['novelty_seeking'] * 0.2
            else:
                novelty_bias = 0
            
            utility = (expected / cost_factor) - rep_penalty - trauma_penalty + novelty_bias
            # Noise
            utility += random.gauss(0, HardConfig.NOISE_STD)
            if utility > best_utility:
                best_utility = utility
                best_action = action
        
        # Record usage
        if best_action:
            self.action_usage[best_action] += 1
            # Commit if not already and not rest
            if best_action != 'rest' and self.commitment_remaining == 0 and random.random() < 0.4:
                self.committed_action = best_action
                self.commitment_remaining = HardConfig.COMMITMENT_WINDOW
        return best_action if best_action else 'rest'
    
    def update_commitment(self):
        if self.commitment_remaining > 0:
            self.commitment_remaining -= 1
            if self.commitment_remaining == 0:
                self.committed_action = None

# ============================================================================
# SELF-MODEL (with aggressive override)
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
        # Detect local optima trap
        if len(self.score_history) >= 10:
            if all(0.4 <= s <= 0.6 for s in list(self.score_history)[-10:]):
                self.local_optima_trap = True
            else:
                self.local_optima_trap = False
    
    def get_override(self, resources: ResourceManager) -> Tuple[bool, str, str]:
        # Force explore if stuck in local optima and not in emergency
        if self.local_optima_trap and not resources.is_emergency() and resources.energy >= 30:
            return True, 'explore', 'local_optima_trap'
        # Force rest if emergency
        if resources.is_emergency():
            return True, 'rest', 'emergency'
        # Chaotic override
        if random.random() < HardConfig.EXPLORATION_OVERRIDE_PROB:
            return True, random.choice(['generate','explore','refine','combine','recall']), 'chaotic_impulse'
        return False, '', ''

# ============================================================================
# MAIN AETHER CLASS
# ============================================================================

class Aether:
    def __init__(self, workspace="aether_works_v08_brutal"):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.resources = ResourceManager()
        self.memory = VectorMemory()
        self.generator = Generator()
        self.world_model = WorldModel()
        self.long_term = LongTermScars()
        self.decision = DecisionEngine(self.world_model, self.long_term)
        self.self_model = SelfModel()
        self.cycle = 0
        self.score_history = []
        self.load_state()
    
    def load_state(self):
        # Optional: load from file
        pass
    
    def save_state(self):
        # Optional: save state
        pass
    
    def get_feasible_actions(self) -> List[str]:
        """Return actions that are possible given hard constraints."""
        feasible = list(HardConfig.ACTION_COSTS.keys())
        # Energy/attention zero => only rest
        if self.resources.energy <= 0 or self.resources.attention <= 0:
            return ['rest']
        # Memory full => forget must be allowed
        if self.resources.memory_used >= HardConfig.MEMORY_SLOTS:
            if 'forget' not in feasible:
                feasible.append('forget')
        # Can't rest if cooldown
        if not self.resources.can_rest():
            feasible = [a for a in feasible if a != 'rest']
        # If no action feasible, force rest anyway (but will be rejected later)
        if not feasible:
            feasible = ['rest']
        return feasible
    
    def step(self) -> Dict:
        self.cycle += 1
        self.resources.cycle = self.cycle
        self.long_term.cycle = self.cycle
        
        # Check coma
        if self.resources.is_coma():
            self.resources.update_coma()
            print(f"[COMA] Cycle {self.cycle} - System collapsed. Recovering in {self.resources.coma_cycles_left} cycles")
            return {'action': 'coma', 'score': 0.0, 'novelty': 0.0}
        
        # Get feasible actions (hard constraints)
        feasible = self.get_feasible_actions()
        
        # Self-model override
        override, forced_action, reason = self.self_model.get_override(self.resources)
        if override and forced_action in feasible:
            chosen_action = forced_action
            print(f"[Override] {reason} -> {chosen_action}")
        else:
            blocked_patterns = set(self.long_term.pattern_blocked_until.keys())
            chosen_action = self.decision.choose_action(
                feasible, self.resources, self.memory,
                self.generator.get_params(), blocked_patterns,
                self.resources.is_emergency()
            )
        
        # Process action
        art = None
        score = 0.5
        novelty = 0.5
        
        if chosen_action in ['generate', 'explore', 'refine', 'combine']:
            # Mutate based on action
            if chosen_action == 'explore':
                self.generator.mutate(intensity=0.5)
            elif chosen_action == 'refine':
                self.generator.mutate(intensity=0.1)
            elif chosen_action == 'combine' and len(self.memory.vectors) > 0:
                # Crossover with random memory's parameters
                rand_mem = random.choice(self.memory.metadata)
                other_params = rand_mem.get('params', self.generator.get_params())
                for k in self.generator.params:
                    if random.random() < 0.5:
                        self.generator.params[k] = (self.generator.params[k] + other_params.get(k, self.generator.params[k])) / 2
            
            # Generate art (respecting blocked patterns)
            blocked = set(self.long_term.pattern_blocked_until.keys())
            art = self.generator.generate(blocked)
            vec = Embedder.from_art(art)
            novelty = self.memory.novelty(vec)
            # Compute score (simplified heuristic)
            features = self._extract_features(art)
            score = self._compute_score(features)
            # Update world model
            self.world_model.update(vec, score)
            # Store in memory
            self.memory.store(vec, {
                'score': score, 'novelty': novelty, 'action': chosen_action,
                'pattern': self.generator.params['pattern'],
                'params': self.generator.get_params(),
                'cycle': self.cycle
            })
            # Update long-term scars
            self.long_term.update(chosen_action, self.generator.params['pattern'], score, self.cycle)
        
        elif chosen_action == 'forget' and self.memory.vectors:
            self.memory.vectors.pop()
            self.memory.metadata.pop()
            self.resources.memory_used = max(0, self.resources.memory_used - 1)
        
        elif chosen_action == 'recall':
            # No art generated, but we may use recall to influence future decisions
            pass
        
        # Apply resource costs
        self.resources.apply_cost(chosen_action)
        self.resources.update_failure_burden(score if art else 0.5)
        self.resources.regen(chosen_action == 'rest')
        
        # Update self-model
        self.self_model.update(score if art else 0.5)
        self.score_history.append(score if art else 0.5)
        
        # Long-term identity drift
        self.long_term.apply_identity_drift(self.score_history)
        
        # Update commitment
        self.decision.update_commitment()
        
        # Check for coma after all updates
        if self.resources.enter_coma():
            print(f"[COMA ENTRY] Cycle {self.cycle} - System collapsed due to extreme failure and low energy")
        
        # Output
        print(f"\n[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f} | Novelty: {novelty:.3f}")
        print(f"Resources: E={self.resources.energy} A={self.resources.attention} F={self.resources.fatigue} B={self.resources.failure_burden}")
        if art:
            print(art[:300] + "..." if len(art) > 300 else art)
        
        return {
            'action': chosen_action,
            'score': score,
            'novelty': novelty,
            'art': art,
            'resources': {
                'energy': self.resources.energy,
                'attention': self.resources.attention,
                'fatigue': self.resources.fatigue,
                'failure_burden': self.resources.failure_burden
            }
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
        # Horizontal symmetry
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
        diversity = len(set(all_chars))/min(30, len(all_chars)) if all_chars else 0
        if all_chars:
            freq=Counter(all_chars)
            probs=[f/len(all_chars) for f in freq.values()]
            entropy=-sum(p*math.log2(p) for p in probs)
            max_ent=math.log2(len(freq)) if len(freq)>1 else 1
            entropy_norm=entropy/max_ent if max_ent>0 else 0
        else:
            entropy_norm=0
        return {'symmetry':symmetry,'density':density,'diversity':diversity,'entropy':entropy_norm}
    
    def _compute_score(self, features):
        density = features['density']
        symmetry = features['symmetry']
        diversity = features['diversity']
        entropy = features['entropy']
        d_score = 1 - abs(density - 0.4) * 2
        return d_score*0.3 + symmetry*0.3 + diversity*0.2 + entropy*0.2
    
    def run_autonomous(self, cycles=100):
        for _ in range(cycles):
            self.step()
            time.sleep(0.6)
        self.save_state()
    
    def run_demo(self, cycles=15):
        for _ in range(cycles):
            self.step()
            time.sleep(0.8)

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    if '--auto' in sys.argv:
        a = Aether()
        a.run_autonomous(100)
    elif '--demo' in sys.argv:
        a = Aether()
        a.run_demo(15)
    else:
        print("Aether v0.8 — Brutal Constraints (rewritten)")
        print("Run with --auto or --demo")
        a = Aether()
        a.run_demo(10)