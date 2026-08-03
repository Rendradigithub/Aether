#!/usr/bin/env python3
"""
AETHER v0.9.1 — STABILIZATION PHASE
"Predict, act, observe, adapt. Learn the cause and effect."

Changes from v0.9:
1. State transition model: next_state_vec = f(current_vec, action, outcome)
2. Aligned world model input: uses param embedding (consistent)
3. Foresight now mutates state using transition model
4. Added comprehensive logging for stability analysis
5. Fixed world model training/prediction consistency

USAGE:
    python aether_v09_finetune.py --auto 200   # run 200 cycles, save log
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
# HARDCORE CONFIGURATION
# ============================================================================

class HardConfig:
    MAX_ENERGY = 100
    MAX_ATTENTION = 100
    MAX_FATIGUE = 100
    MEMORY_SLOTS = 25
    
    ACTION_COSTS = {
        'generate': (12, 6, 0, 3),
        'explore':  (35, 20, 1, 7),
        'refine':   (10, 14, 0, 4),
        'recall':   (4, 3, 0, 1),
        'combine':  (18, 12, 1, 5),
        'rest':     (-5, -8, 0, -6),
        'forget':   (7, 4, -1, 3),
    }
    
    COMMITMENT_WINDOW = 6
    COMMITMENT_VIOLATION_PENALTY = {'energy': -35, 'attention': -45, 'fatigue': +25}
    COMMITMENT_THRESHOLD_CONFIDENCE = 0.7
    
    FAILURE_BURDEN_MAX = 100
    COST_MULTIPLIER_MAX = 2.0
    
    EMERGENCY_BURDEN_THRESHOLD = 70
    EMERGENCY_ENERGY_THRESHOLD = 20
    COMA_BURDEN = 100
    COMA_ENERGY = 10
    COMA_DURATION = 5
    
    TRAUMA_BLOCK_THRESHOLD = 0.7
    TRAUMA_BLOCK_DURATION = 20
    
    WORLD_MODEL_UPDATE_RATE = 0.05
    WORLD_MODEL_HIDDEN_DIM = 32
    VECTOR_DIM = 24   # parameter embedding dimension
    
    FORESIGHT_STEPS = 2
    PLANNING_DISCOUNT = 0.9
    
    EXPLORATION_NOISE_STD = 0.1
    CURIOSITY_BONUS = 0.15
    
    REPETITION_PENALTY_PER_USE = 0.04
    REPETITION_WINDOW = 15
    
    # State transition parameters
    STATE_TRANSITION_NOISE = 0.05
    ACTION_SHIFT = {
        'explore': 0.25,
        'refine': 0.08,
        'generate': 0.02,
        'combine': 0.12,
        'rest': -0.05,
        'recall': 0.0,
        'forget': 0.0
    }

# ============================================================================
# RESOURCE MANAGER (unchanged from v0.9)
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
        if action not in HardConfig.ACTION_COSTS:
            return
        en, att, mem_delta, fat = HardConfig.ACTION_COSTS[action]
        multiplier = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        self.energy += int(en * multiplier)
        self.attention += int(att * multiplier)
        self.memory_used += mem_delta
        self.fatigue += fat + int(self.failure_burden / 20)
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
# LONG-TERM SCARS (unchanged)
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
                if self.pattern_trauma[p] == 0: del self.pattern_trauma[p]
            for a in list(self.action_trauma.keys()):
                self.action_trauma[a] = max(0, self.action_trauma[a] - 1)
                if self.action_trauma[a] == 0: del self.action_trauma[a]
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
        if len(recent_scores) < 30: return
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
# VECTOR MEMORY (with prediction)
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
        if not self.vectors: return []
        sims = []
        for i, v in enumerate(self.vectors):
            sim = np.dot(query, v) / (np.linalg.norm(query)*np.linalg.norm(v)+1e-8)
            sims.append((sim, i))
        sims.sort(reverse=True)
        return [(sim, self.metadata[idx].copy()) for sim, idx in sims[:k]]
    
    def novelty(self, vec: np.ndarray) -> float:
        if not self.vectors: return 1.0
        max_sim = max(np.dot(vec, v)/(np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors)
        return 1.0 - max_sim
    
    def predict_score_similarity(self, query: np.ndarray) -> float:
        if not self.vectors: return 0.5
        sims = []
        scores = []
        for i, v in enumerate(self.vectors):
            sim = np.dot(query, v) / (np.linalg.norm(query)*np.linalg.norm(v)+1e-8)
            if sim > 0.05:
                sims.append(sim)
                scores.append(self.metadata[i].get('score', 0.5))
        if not sims: return 0.5
        total = sum(sims)
        return sum(sim * sc for sim, sc in zip(sims, scores)) / total

# ============================================================================
# EMBEDDING: parameter vector (consistent for world model)
# ============================================================================

class ParamEmbedder:
    """Convert generator params to fixed vector (world model input)"""
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
        vec = np.array(features[:HardConfig.VECTOR_DIM])
        # normalize
        if np.linalg.norm(vec) > 0:
            vec = vec / np.linalg.norm(vec)
        return vec

class ArtEmbedder:
    """Convert art to vector (for memory storage)"""
    @staticmethod
    def embed(art: str) -> np.ndarray:
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(HardConfig.VECTOR_DIM)
        h = len(lines)
        w = max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        features = []
        total = h*w
        non_space = sum(c!=' ' for line in padded for c in line)
        features.append(non_space / max(1, total))
        # symmetry
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
        features.append(h_sym/max(1,cnt))
        # vertical symmetry
        v_sym=0; vc=0
        for x in range(w):
            top=''.join(padded[y][x] for y in range(h//2))
            bot=''.join(padded[h-1-y][x] for y in range(h//2))
            if top and bot:
                matches=sum(1 for a,b in zip(top,bot) if a==b and a!=' ')
                v_sym+=matches/max(1,len(top))
                vc+=1
        features.append(v_sym/max(1,vc))
        all_chars = [c for line in padded for c in line if c!=' ']
        if all_chars:
            unique = len(set(all_chars))
            features.append(unique/min(30, len(all_chars)))
            from collections import Counter
            freq = Counter(all_chars)
            probs = [f/len(all_chars) for f in freq.values()]
            entropy = -sum(p*math.log2(p) for p in probs)
            max_ent = math.log2(len(freq)) if len(freq)>1 else 1
            features.append(entropy/max_ent if max_ent>0 else 0)
        else:
            features.extend([0,0])
        # edge density
        h_edges=v_edges=0; total_edges=0
        for y in range(h):
            for x in range(w-1):
                if padded[y][x]!=' ' and padded[y][x+1]!=' ' and padded[y][x]!=padded[y][x+1]:
                    h_edges+=1
                total_edges+=1
        for y in range(h-1):
            for x in range(w):
                if padded[y][x]!=' ' and padded[y+1][x]!=' ' and padded[y][x]!=padded[y+1][x]:
                    v_edges+=1
                total_edges+=1
        features.append((h_edges+v_edges)/max(1,total_edges))
        # clustering
        positions = [(y,x) for y in range(h) for x in range(w) if padded[y][x]!=' ']
        if len(positions)>1:
            dists=[]
            sampled = positions[:min(50,len(positions))]
            for i,(y1,x1) in enumerate(sampled):
                for j,(y2,x2) in enumerate(sampled[i+1:i+10]):
                    dists.append(math.hypot(y1-y2, x1-x2))
            avg_dist = sum(dists)/len(dists) if dists else 0
            clustering = 1 - min(1.0, avg_dist/max(w,h))
        else:
            clustering=0
        features.append(clustering)
        while len(features) < HardConfig.VECTOR_DIM:
            features.append(0)
        vec = np.array(features[:HardConfig.VECTOR_DIM])
        if np.linalg.norm(vec) > 0:
            vec = vec / np.linalg.norm(vec)
        return vec

# ============================================================================
# WORLD MODEL (trained on param vectors)
# ============================================================================

class WorldModel:
    def __init__(self, input_dim=HardConfig.VECTOR_DIM, hidden_dim=HardConfig.WORLD_MODEL_HIDDEN_DIM):
        self.W1 = np.random.randn(hidden_dim, input_dim) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(1, hidden_dim) * 0.1
        self.b2 = 0.0
        self.confidence = 0.5
        self.buffer = deque(maxlen=200)
    
    def predict(self, param_vec: np.ndarray) -> float:
        h = np.tanh(self.W1 @ param_vec + self.b1)
        out = float(self.W2 @ h + self.b2)
        return np.clip(out, 0.0, 1.0)
    
    def predict_with_uncertainty(self, param_vec: np.ndarray) -> Tuple[float, float]:
        pred = self.predict(param_vec)
        uncertainty = 1.0 - self.confidence
        return pred, uncertainty
    
    def update(self, param_vec: np.ndarray, actual_score: float):
        self.buffer.append((param_vec, actual_score))
        if len(self.buffer) % 10 == 0 and len(self.buffer) >= 20:
            indices = random.sample(range(len(self.buffer)), min(20, len(self.buffer)))
            for idx in indices:
                v, a = self.buffer[idx]
                pred = self.predict(v)
                error = a - pred
                h = np.tanh(self.W1 @ v + self.b1)
                self.W2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error * h.reshape(1,-1)
                self.b2 += HardConfig.WORLD_MODEL_UPDATE_RATE * error
                delta_h = error * self.W2.T * (1 - h**2)
                self.W1 += HardConfig.WORLD_MODEL_UPDATE_RATE * np.outer(delta_h, v)
                self.b1 += HardConfig.WORLD_MODEL_UPDATE_RATE * delta_h.flatten()
        if len(self.buffer) >= 30:
            errors = [abs(self.predict(v)-a) for v,a in list(self.buffer)[-30:]]
            self.confidence = max(0.2, min(0.95, 1.0 - sum(errors)/30))

# ============================================================================
# STATE TRANSITION MODEL (new)
# ============================================================================

class StateTransition:
    """Predict next parameter vector given action and outcome"""
    @staticmethod
    def transition(current_param_vec: np.ndarray, action: str, outcome_score: float) -> np.ndarray:
        shift = HardConfig.ACTION_SHIFT.get(action, 0.0)
        # direction based on outcome: success reinforces similar style, failure pushes away
        if outcome_score > 0.7:
            # success: keep similar direction
            factor = 1.0 + shift
        elif outcome_score < 0.3:
            # failure: move away from current style
            factor = 1.0 - shift
        else:
            factor = 1.0 + shift * (outcome_score - 0.5) * 2
        
        # Apply factor to vector components
        new_vec = current_param_vec * factor
        # Add noise
        noise = np.random.randn(len(current_param_vec)) * HardConfig.STATE_TRANSITION_NOISE
        new_vec += noise
        # renormalize
        norm = np.linalg.norm(new_vec)
        if norm > 0:
            new_vec = new_vec / norm
        return new_vec

# ============================================================================
# GENERATOR (unchanged but uses ParamEmbedder for world model)
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
    
    def generate(self, blocked_patterns: Set[str]) -> Tuple[str, str]:
        pattern = self.params['pattern']
        if pattern in blocked_patterns:
            raise ValueError(f"Pattern {pattern} blocked")
        self.usage_counter[pattern] += 1
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        if pattern == 'wave':
            for y in range(h):
                for x in range(w):
                    val = (math.sin(x*0.2)*math.cos(y*0.3) + math.sin(x*0.5)*0.5 + math.cos(y*0.4)*0.3)
                    norm = (val+1)/2
                    if norm > 1 - self.params['density']:
                        grid[y][x] = random.choice('░▒▓█')
        elif pattern == 'fractal':
            self._draw_fractal(grid, w//2, h//2, min(w,h)//6, int(self.params['complexity']*3+2))
        elif pattern == 'cellular':
            grid = self._cellular_automaton(w, h)
        else:
            grid = self._lsystem_draw(w, h)
        if self.params['symmetry'] > random.random():
            for y in range(h):
                for x in range(w//2):
                    if grid[y][x] != ' ':
                        grid[y][w-1-x] = grid[y][x]
        self._adjust_density(grid, self.params['density'])
        if self.params['noise'] > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < self.params['noise']*0.3:
                        grid[y][x] = random.choice(' .:oO0@') if grid[y][x]==' ' else ' '
        art = '\n'.join(''.join(row) for row in grid)
        return art, pattern
    
    def _draw_fractal(self, grid, x, y, size, depth):
        if depth<=0 or size<1: return
        for i in range(-size, size+1):
            if 0<=x+i<len(grid[0]) and 0<=y<len(grid): grid[y][x+i] = '█'
            if 0<=x<len(grid[0]) and 0<=y+i<len(grid): grid[y+i][x] = '█'
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
        for _ in range(3): seq = ''.join(rules.get(c,c) for c in seq)
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
            if random.random() < 0.5:
                self.params[k] = (self.params[k] + other_params.get(k, self.params[k])) / 2
    
    def get_params(self) -> Dict:
        return self.params.copy()

# ============================================================================
# DECISION ENGINE (with foresight that uses state transition)
# ============================================================================

class DecisionEngine:
    def __init__(self, world_model: WorldModel, long_term: LongTermScars, memory: VectorMemory):
        self.world = world_model
        self.long_term = long_term
        self.memory = memory
        self.action_usage = Counter()
        self.committed_action = None
        self.commitment_remaining = 0
    
    def _evaluate_action_utility(self, action: str, param_vec: np.ndarray,
                                 resources: ResourceManager, blocked_patterns: Set[str]) -> float:
        # Predict score using world model
        pred_score, uncertainty = self.world.predict_with_uncertainty(param_vec)
        # Blend with memory similarity
        similar_score = self.memory.predict_score_similarity(param_vec)
        blend = self.world.confidence * pred_score + (1 - self.world.confidence) * similar_score
        # Cost
        en_cost, att_cost, _ = resources.get_effective_action_cost(action)
        cost_factor = max(1, (en_cost + att_cost/10) / 15)
        # Penalties
        rep_penalty = self.action_usage[action] * HardConfig.REPETITION_PENALTY_PER_USE
        trauma_penalty = self.long_term.get_action_trauma_penalty(action)
        novelty_bias = self.long_term.get_novelty_bias(action)
        curiosity = HardConfig.CURIOSITY_BONUS * uncertainty if action in ['explore','combine'] else 0.0
        if action == 'rest':
            deficit = max(0, (HardConfig.MAX_ENERGY - resources.energy) / HardConfig.MAX_ENERGY)
            utility = deficit * 0.5
        else:
            utility = (blend / cost_factor) - rep_penalty - trauma_penalty + novelty_bias + curiosity
        if action in ['explore','combine']:
            utility *= (0.8 + 0.4 * self.long_term.identity_bias['risk_tolerance'])
        return max(0.0, utility)
    
    def _simulate_foresight(self, action: str, param_vec: np.ndarray,
                           resources: ResourceManager, blocked_patterns: Set[str]) -> float:
        # First step utility
        first_util = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
        # Estimate outcome from prediction (simulate score)
        pred_score, _ = self.world.predict_with_uncertainty(param_vec)
        # Apply state transition
        next_vec = StateTransition.transition(param_vec, action, pred_score)
        # Simulate resources after first action
        en_cost, att_cost, _ = resources.get_effective_action_cost(action)
        sim_energy = resources.energy - en_cost
        if sim_energy <= 0:
            return first_util * 0.5
        # Create simulated resource container
        sim_res = ResourceManager()
        sim_res.energy = sim_energy
        sim_res.attention = max(0, resources.attention - att_cost)
        sim_res.fatigue = resources.fatigue + 5
        sim_res.failure_burden = resources.failure_burden
        # Find best next action
        best_next_util = 0.0
        for a2 in HardConfig.ACTION_COSTS.keys():
            if a2 in blocked_patterns and a2 in ['generate','explore','refine','combine']:
                continue
            util2 = self._evaluate_action_utility(a2, next_vec, sim_res, blocked_patterns)
            if util2 > best_next_util:
                best_next_util = util2
        total = first_util + HardConfig.PLANNING_DISCOUNT * best_next_util
        return total
    
    def choose_action(self, feasible: List[str], resources: ResourceManager,
                     param_vec: np.ndarray, blocked_patterns: Set[str], emergency: bool) -> str:
        if self.commitment_remaining > 0:
            if self.committed_action in feasible:
                return self.committed_action
            else:
                resources.apply_cost('forget')
                resources.energy += HardConfig.COMMITMENT_VIOLATION_PENALTY['energy']
                resources.attention += HardConfig.COMMITMENT_VIOLATION_PENALTY['attention']
                resources.fatigue += HardConfig.COMMITMENT_VIOLATION_PENALTY['fatigue']
                self.commitment_remaining = 0
                self.committed_action = None
        
        if emergency:
            feasible = [a for a in feasible if a in ['rest', 'recall']]
            if not feasible: feasible = ['rest']
        
        best_action = None
        best_util = -float('inf')
        for action in feasible:
            if resources.energy > 30 and action in ['generate','explore','refine','combine']:
                util = self._simulate_foresight(action, param_vec, resources, blocked_patterns)
            else:
                util = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
            util += random.gauss(0, HardConfig.EXPLORATION_NOISE_STD)
            if util > best_util:
                best_util = util
                best_action = action
        
        if best_action is None: best_action = 'rest'
        self.action_usage[best_action] += 1
        
        if self.commitment_remaining == 0 and best_action != 'rest':
            if self.world.confidence > HardConfig.COMMITMENT_THRESHOLD_CONFIDENCE and best_util > 0.6:
                self.committed_action = best_action
                self.commitment_remaining = HardConfig.COMMITMENT_WINDOW
        return best_action
    
    def update_commitment(self):
        if self.commitment_remaining > 0:
            self.commitment_remaining -= 1
            if self.commitment_remaining == 0:
                self.committed_action = None

# ============================================================================
# SELF-MODEL (unchanged)
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
        if random.random() < 0.08:
            return True, random.choice(['generate','explore','refine','combine','recall']), 'chaotic_impulse'
        return False, '', ''

# ============================================================================
# MAIN AETHER CLASS with LOGGING for analysis
# ============================================================================

class Aether:
    def __init__(self, workspace="aether_works_v09_stable"):
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
        self.log_data = []  # for analysis
        self.load_state()
    
    def load_state(self):
        pass
    
    def save_state(self):
        pass
    
    def get_feasible_actions(self, blocked_patterns: Set[str]) -> List[str]:
        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.resources.energy <= 0 or self.resources.attention <= 0:
            return ['rest']
        if self.resources.memory_used >= HardConfig.MEMORY_SLOTS:
            if 'forget' not in feasible:
                feasible.append('forget')
        if not self.resources.can_rest():
            feasible = [a for a in feasible if a != 'rest']
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
        
        if self.resources.is_coma():
            self.resources.update_coma()
            print(f"[COMA] Cycle {self.cycle} - Recovering...")
            return {'action': 'coma', 'score': 0.0, 'novelty': 0.0}
        
        param_vec = ParamEmbedder.embed(self.generator.get_params())
        blocked = set(self.long_term.pattern_blocked_until.keys())
        feasible = self.get_feasible_actions(blocked)
        
        override, forced_action, reason = self.self_model.get_override(self.resources, self.world_model.confidence)
        if override and forced_action in feasible:
            chosen_action = forced_action
            print(f"[Override] {reason} -> {chosen_action}")
        else:
            emergency = self.resources.is_emergency()
            chosen_action = self.decision.choose_action(feasible, self.resources, param_vec, blocked, emergency)
        
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
                # Score function (external world feedback)
                features = self._extract_features(art)
                score = self._compute_score(features)
                # Update world model with current params vector
                current_param_vec = ParamEmbedder.embed(self.generator.get_params())
                self.world_model.update(current_param_vec, score)
                # Store art vector (for similarity) and param vector as metadata
                self.memory.store(art_vec, {
                    'score': score, 'novelty': novelty, 'action': chosen_action,
                    'pattern': used_pattern, 'params': self.generator.get_params().copy(),
                    'cycle': self.cycle, 'param_vec': current_param_vec.tolist()
                })
                self.long_term.update(chosen_action, used_pattern, score, self.cycle)
            
            elif chosen_action == 'forget' and self.memory.vectors:
                self.memory.vectors.pop()
                self.memory.metadata.pop()
                self.resources.memory_used = max(0, self.resources.memory_used - 1)
            
            # rest and recall do nothing special
        except ValueError as e:
            print(f"[Infeasible] {e}")
            score = 0.2
            novelty = 0.0
            chosen_action = 'failed_' + chosen_action
            self.resources.apply_cost(chosen_action)
            self.resources.update_failure_burden(score)
            self.resources.regen(False)
            self.self_model.update(score)
            self.score_history.append(score)
            self.action_history.append(chosen_action)
            self._log_step(chosen_action, score, novelty)
            print(f"[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f}")
            return {'action': chosen_action, 'score': score, 'novelty': 0.0}
        
        self.resources.apply_cost(chosen_action)
        self.resources.update_failure_burden(score)
        self.resources.regen(chosen_action == 'rest')
        
        self.self_model.update(score)
        self.score_history.append(score)
        self.action_history.append(chosen_action)
        
        self.long_term.apply_identity_drift(self.score_history)
        self.decision.update_commitment()
        
        if self.resources.enter_coma():
            print(f"[COMA ENTRY] Cycle {self.cycle}")
        
        self._log_step(chosen_action, score, novelty, self.resources, self.world_model.confidence)
        
        print(f"\n[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f} | Novelty: {novelty:.3f}")
        print(f"Resources: E={self.resources.energy} A={self.resources.attention} F={self.resources.fatigue} B={self.resources.failure_burden}")
        print(f"World model confidence: {self.world_model.confidence:.2f}")
        if art and len(art) > 0:
            print(art[:250] + "..." if len(art) > 250 else art)
        
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
        d_score = 1 - abs(density - 0.4) * 2
        return d_score*0.3 + symmetry*0.3 + diversity*0.2 + entropy*0.2
    
    def _log_step(self, action, score, novelty, resources=None, confidence=None):
        entry = {
            'cycle': self.cycle,
            'action': action,
            'score': score,
            'novelty': novelty,
            'energy': resources.energy if resources else None,
            'attention': resources.attention if resources else None,
            'fatigue': resources.fatigue if resources else None,
            'failure_burden': resources.failure_burden if resources else None,
            'world_model_confidence': confidence,
            'trauma_blocked': list(self.long_term.pattern_blocked_until.keys()),
            'identity': self.long_term.identity_bias.copy(),
            'timestamp': datetime.now().isoformat()
        }
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
        self.save_state()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    if '--auto' in sys.argv:
        cycles = 200
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            cycles = int(sys.argv[2])
        a = Aether()
        a.run_autonomous(cycles)
    elif '--demo' in sys.argv:
        a = Aether()
        for _ in range(20):
            a.step()
            time.sleep(0.5)
    else:
        print("Aether v0.9.1 — Stabilization Phase")
        print("Run with --auto [cycles] (default 200) or --demo")
        a = Aether()
        a.run_autonomous(30)