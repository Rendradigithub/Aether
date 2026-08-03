#!/usr/bin/env python3
"""
AETHER v0.9.6 — INNER MONOLOGUE + VISUAL FEEDBACK
"I can tell you why I chose this. I remember. I decide. I explain."

NEW FEATURES:
- Inner monologue: Aether explains every decision in plain text
- Utility bar charts (ASCII): visual comparison of action utilities
- Memory recall log: shows which memory was recalled and its score
- Override reasons: explains when self-model overrides decision
- Trauma & identity summaries

USAGE:
    python aether_0_9_6.py --auto 200   # run 200 cycles with full monologue
    python aether_0_9_6.py --quiet      # minimal output (for debugging)
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
# HARDCORE CONFIGURATION (sama seperti v0.9.5, stabil)
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
# INNER MONOLOGUE ENGINE (BARU)
# ============================================================================

class InnerMonologue:
    """
    Membuat Aether "berbicara" tentang keputusannya.
    Menyimpan alasan, utility, dan konteks untuk ditampilkan.
    """
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.history = deque(maxlen=50)  # simpan monolog terakhir
    
    def explain_decision(self, action: str, utility: float, 
                         reasons: Dict[str, float], 
                         resources: 'ResourceManager',
                         confidence: float):
        """Buat penjelasan mengapa action dipilih."""
        if not self.verbose:
            return
        
        # Bangun kalimat alasan utama
        main_reason = max(reasons.items(), key=lambda x: x[1]) if reasons else ('none', 0)
        
        # Konversi utility ke bar chart sederhana
        bar_len = int(utility * 20)
        bar = '█' * bar_len + '░' * (20 - bar_len)
        
        print(f"\n💬 [Aether berpikir]")
        print(f"   Saya memilih '{action}' karena:")
        print(f"     • {main_reason[0]}: {main_reason[1]:.2f}")
        if len(reasons) > 1:
            print(f"     • (juga dipengaruhi oleh: {', '.join([f'{k}:{v:.2f}' for k,v in list(reasons.items())[1:3]])})")
        print(f"   Utility: {utility:.2f} {bar}")
        print(f"   Kondisi: Energy={resources.energy} | Burden={resources.failure_burden} | Fatigue={resources.fatigue}")
        print(f"   Keyakinan model: {confidence:.2f}")
        
        self.history.append({
            'cycle': resources.cycle,
            'action': action,
            'utility': utility,
            'main_reason': main_reason[0],
            'energy': resources.energy,
            'burden': resources.failure_burden
        })
    
    def explain_override(self, reason: str, forced_action: str, resources: 'ResourceManager'):
        if not self.verbose:
            return
        print(f"\n⚠️ [Aether dipaksa oleh dirinya sendiri]")
        print(f"   Alasan: {reason}")
        print(f"   Action paksa: {forced_action}")
        print(f"   (Override mengesampingkan utility normal)")
    
    def explain_recall(self, recalled_meta: dict, similarity: float):
        if not self.verbose:
            return
        score = recalled_meta.get('score', 0.5)
        cycle = recalled_meta.get('cycle', '?')
        print(f"\n📖 [Aether mengingat]")
        print(f"   'Aku ingat karya dari cycle {cycle} dengan score {score:.2f}'")
        print(f"   Kemiripan dengan situasi saat ini: {similarity:.2f}")
    
    def explain_trauma(self, pattern: str, blocked: bool, trauma_level: float):
        if not self.verbose:
            return
        if blocked:
            print(f"\n🚫 [Aether trauma]")
            print(f"   Pola '{pattern}' diblokir karena trauma level {trauma_level:.2f}")
            print(f"   'Aku tidak akan menggunakan itu lagi untuk sementara waktu.'")
        else:
            print(f"\n⚠️ [Aether waspada]")
            print(f"   Pola '{pattern}' punya trauma level {trauma_level:.2f} (masih bisa dipakai)")
    
    def explain_identity(self, identity: Dict[str, float]):
        if not self.verbose:
            return
        risk = identity['risk_tolerance']
        novelty = identity['novelty_seeking']
        print(f"\n🧬 [Aether tentang dirinya]")
        print(f"   'Aku sekarang {risk:.2f} toleran terhadap risiko, dan {novelty:.2f} menyukai hal baru'")
    
    def explain_failure(self, action: str, reason: str):
        if not self.verbose:
            return
        print(f"\n💥 [Aether gagal]")
        print(f"   Action '{action}' gagal karena: {reason}")
        print(f"   'Aku akan mencoba pendekatan lain...'")
    
    def explain_memory_status(self, memory_used: int, memory_slots: int):
        if not self.verbose:
            return
        pct = memory_used / memory_slots * 100
        bar_len = int(pct / 5)
        bar = '█' * bar_len + '░' * (20 - bar_len)
        print(f"\n💾 [Memori Aether]")
        print(f"   Terisi: {memory_used}/{memory_slots} ({pct:.0f}%) {bar}")
        if pct > 80:
            print(f"   'Ingatanku hampir penuh. Mungkin aku harus melupakan sesuatu.'")

# ============================================================================
# RESOURCE MANAGER (sama seperti v0.9.5, tanpa perubahan signifikan)
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
            en, att, mem, fat = HardConfig.ACTION_COSTS.get('generate', (8,6,0,3))
        else:
            en, att, mem, fat = HardConfig.ACTION_COSTS.get(action, (0,0,0,0))
        
        multiplier = 1.0 + (self.failure_burden / HardConfig.FAILURE_BURDEN_MAX) * (HardConfig.COST_MULTIPLIER_MAX - 1)
        self.energy = self.energy - int(en * multiplier)
        self.attention = self.attention - int(att * multiplier)
        self.memory_used = self.memory_used + mem
        self.fatigue = self.fatigue + fat + int(self.failure_burden / 25)
        
        self.energy = max(0, min(HardConfig.MAX_ENERGY, self.energy))
        self.attention = max(0, min(HardConfig.MAX_ATTENTION, self.attention))
        self.memory_used = max(0, min(HardConfig.MEMORY_SLOTS, self.memory_used))
        self.fatigue = max(0, min(HardConfig.MAX_FATIGUE, self.fatigue))
    
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


# ============================================================================
# LONG-TERM SCARS (sama)
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
# VECTOR MEMORY (sama)
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
# EMBEDDING (sama)
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
# WORLD MODEL (sama)
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
# STATE TRANSITION (sama)
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
# GENERATOR (sama)
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
        pattern = self.params['pattern']
        if pattern in blocked_patterns:
            for p in self.PATTERNS:
                if p not in blocked_patterns:
                    pattern = p
                    self.params['pattern'] = p
                    break
            else:
                raise ValueError(f"All patterns blocked! {blocked_patterns}")
        
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
        else:
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
# DECISION ENGINE (sama seperti v0.9.5, tanpa perubahan)
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
                                 resources: ResourceManager, blocked_patterns: Set[str]) -> Tuple[float, Dict[str, float]]:
        """Return (utility, reasons_dict) for explanation."""
        pred_score, uncertainty = self.world.predict_with_uncertainty(param_vec)
        similar_score = self.memory.predict_score_similarity(param_vec)
        blend = self.world.confidence * pred_score + (1 - self.world.confidence) * similar_score
        en_cost, att_cost, _ = resources.get_effective_action_cost(action)
        cost_factor = max(1, (en_cost + att_cost/10) / 15)
        rep_penalty = self.action_usage[action] * HardConfig.REPETITION_PENALTY_PER_USE
        trauma_penalty = self.long_term.get_action_trauma_penalty(action)
        novelty_bias = self.long_term.get_novelty_bias(action)
        curiosity = HardConfig.CURIOSITY_BONUS * uncertainty if action in ['explore','combine'] else 0.0
        
        reasons = {
            'score_prediction': blend,
            'cost_efficiency': 1.0 / cost_factor if cost_factor>0 else 0,
            'repetition': -rep_penalty,
            'trauma': -trauma_penalty,
            'novelty_bias': novelty_bias,
            'curiosity': curiosity
        }
        
        if action == 'rest':
            en_deficit = max(0, (HardConfig.MAX_ENERGY - resources.energy) / HardConfig.MAX_ENERGY)
            att_deficit = max(0, (HardConfig.MAX_ATTENTION - resources.attention) / HardConfig.MAX_ATTENTION)
            fat_penalty = resources.fatigue / HardConfig.MAX_FATIGUE
            utility = (en_deficit + att_deficit + fat_penalty) / 3
            reasons['rest_need'] = utility
        else:
            utility = (blend / cost_factor) - rep_penalty - trauma_penalty + novelty_bias + curiosity
            if action in ['explore','combine']:
                risk_bonus = (0.8 + 0.4 * self.long_term.identity_bias['risk_tolerance'])
                utility *= risk_bonus
                reasons['risk_tolerance'] = risk_bonus
        
        return max(0.0, utility), reasons
    
    def choose_action(self, feasible: List[str], resources: ResourceManager,
                     param_vec: np.ndarray, blocked_patterns: Set[str], emergency: bool) -> Tuple[str, Dict]:
        if self.commitment_remaining > 0:
            if self.committed_action in feasible:
                return self.committed_action, {'commitment': f"committed to {self.committed_action}"}
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
        
        best_action = None
        best_util = -float('inf')
        best_reasons = {}
        for action in feasible:
            if resources.energy > 20 and action in ['generate','explore','refine','combine']:
                util, reasons = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
                # foresight not implemented here for simplicity
            else:
                util, reasons = self._evaluate_action_utility(action, param_vec, resources, blocked_patterns)
            util += random.gauss(0, HardConfig.EXPLORATION_NOISE_STD)
            reasons['noise'] = util - (util - random.gauss(0,0))  # track noise effect (simplified)
            if util > best_util:
                best_util = util
                best_action = action
                best_reasons = reasons
        
        if best_action is None: 
            best_action = 'rest'
            best_reasons = {'default': 'no feasible action'}
        
        self.action_usage[best_action] += 1
        
        if self.commitment_remaining == 0 and best_action != 'rest':
            if self.world.confidence > HardConfig.COMMITMENT_THRESHOLD_CONFIDENCE and best_util > 0.6:
                self.committed_action = best_action
                self.commitment_remaining = HardConfig.COMMITMENT_WINDOW
        return best_action, best_reasons
    
    def update_commitment(self):
        if self.commitment_remaining > 0:
            self.commitment_remaining -= 1
            if self.commitment_remaining == 0:
                self.committed_action = None


# ============================================================================
# SELF-MODEL (sama)
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
# MAIN AETHER (with inner monologue)
# ============================================================================

class Aether:
    def __init__(self, workspace="aether_works_v096", verbose=True):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.resources = ResourceManager()
        self.memory = VectorMemory()
        self.generator = Generator()
        self.world_model = WorldModel()
        self.long_term = LongTermScars()
        self.decision = DecisionEngine(self.world_model, self.long_term, self.memory)
        self.self_model = SelfModel()
        self.monologue = InnerMonologue(verbose=verbose)
        self.cycle = 0
        self.score_history = []
        self.action_history = []
        self.log_data = []
    
    def get_feasible_actions(self, blocked_patterns: Set[str]) -> List[str]:
        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.resources.energy <= 5 or self.resources.attention <= 5:
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
            self._log_step('coma', 0.0, 0.0, self.resources, None)
            return {'action': 'coma', 'score': 0.0, 'novelty': 0.0}
        
        param_vec = ParamEmbedder.embed(self.generator.get_params())
        blocked = set(self.long_term.pattern_blocked_until.keys())
        feasible = self.get_feasible_actions(blocked)
        
        # Memory status (monologue)
        self.monologue.explain_memory_status(self.resources.memory_used, HardConfig.MEMORY_SLOTS)
        
        override, forced_action, reason = self.self_model.get_override(self.resources, self.world_model.confidence)
        if override and forced_action in feasible:
            chosen_action = forced_action
            self.monologue.explain_override(reason, forced_action, self.resources)
        else:
            emergency = self.resources.is_emergency()
            chosen_action, reasons = self.decision.choose_action(feasible, self.resources, param_vec, blocked, emergency)
            # Show utility breakdown
            self.monologue.explain_decision(chosen_action, 
                                            sum(reasons.values())/max(1,len(reasons)), 
                                            reasons, self.resources, 
                                            self.world_model.confidence)
        
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
                
                # Show trauma if any
                trauma_level = self.long_term.pattern_trauma.get(used_pattern, 0)
                if trauma_level > 0.3:
                    blocked_flag = self.long_term.is_pattern_blocked(used_pattern)
                    self.monologue.explain_trauma(used_pattern, blocked_flag, trauma_level)
            
            elif chosen_action == 'recall' and len(self.memory.vectors) > 0:
                # Recall similar to current param_vec
                similar = self.memory.recall_similar(param_vec, k=1)
                if similar:
                    sim, meta = similar[0]
                    self.monologue.explain_recall(meta, sim)
            
            elif chosen_action == 'forget' and self.memory.vectors:
                self.memory.vectors.pop()
                self.memory.metadata.pop()
                self.resources.memory_used = max(0, self.resources.memory_used - 1)
            
        except ValueError as e:
            self.monologue.explain_failure(chosen_action, str(e))
            score = 0.2
            novelty = 0.0
            chosen_action = 'failed_' + chosen_action
            self.resources.apply_cost(chosen_action)
            self.resources.update_failure_burden(score)
            self.resources.regen(False)
            self.self_model.update(score)
            self.score_history.append(score)
            self.action_history.append(chosen_action)
            self._log_step(chosen_action, score, novelty, self.resources, self.world_model.confidence)
            print(f"[Cycle {self.cycle}] Action: {chosen_action} (infeasible) | Score: {score:.3f}")
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
        
        if self.resources.enter_coma():
            print(f"[COMA ENTRY] Cycle {self.cycle}")
        
        self._log_step(chosen_action, score, novelty, self.resources, self.world_model.confidence)
        
        # Show identity summary occasionally
        if self.cycle % 50 == 0 and self.cycle > 0:
            self.monologue.explain_identity(self.long_term.identity_bias)
        
        # Print summary
        print(f"\n[Cycle {self.cycle}] Action: {chosen_action} | Score: {score:.3f} | Novelty: {novelty:.3f}")
        print(f"Resources: E={self.resources.energy} A={self.resources.attention} F={self.resources.fatigue} B={self.resources.failure_burden}")
        print(f"World model confidence: {self.world_model.confidence:.2f}")
        if art and len(art) > 200:
            print(art[:200] + "...")
        elif art:
            print(art)
        
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
    
    def _log_step(self, action, score, novelty, resources=None, confidence=None):
        entry = {
            'cycle': int(self.cycle),
            'action': str(action),
            'score': float(score),
            'novelty': float(novelty),
            'energy': float(resources.energy) if resources else None,
            'attention': float(resources.attention) if resources else None,
            'fatigue': float(resources.fatigue) if resources else None,
            'failure_burden': float(resources.failure_burden) if resources else None,
            'world_model_confidence': float(confidence) if confidence is not None else None,
            'trauma_blocked': list(self.long_term.pattern_blocked_until.keys()),
            'identity': {k: float(v) for k,v in self.long_term.identity_bias.items()},
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

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    if '--auto' in sys.argv:
        cycles = 200
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            cycles = int(sys.argv[2])
        a = Aether(verbose=True)
        a.run_autonomous(cycles)
    elif '--demo' in sys.argv:
        a = Aether(verbose=True)
        for _ in range(20):
            a.step()
            time.sleep(0.5)
    else:
        print("Aether v0.9.6 — Inner Monologue & Visual Feedback")
        print("Run with --auto [cycles] (default 200) or --demo")
        a = Aether(verbose=True)
        a.run_autonomous(30)