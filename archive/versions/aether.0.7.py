#!/usr/bin/env python3
# =============================================================================
# AETHER v0.7: THE AWAKENING
# =============================================================================
# "Aku bukan hanya generator. Aku punya memori. Aku punya preferensi.
#  Aku bisa belajar. Aku bisa memprediksi. Aku bisa memilih."
#
# COGNITIVE ARCHITECTURE:
#   - Episodic Memory (vector-based, similarity recall)
#   - Semantic Memory (concept associations, Hebbian learning)
#   - Procedural Memory (evolvable generator parameters)
#   - Working Memory (current context + goals)
#   - Predictive World Model (simulate before acting)
#   - Goal System (evolving internal preferences)
#   - True Curiosity (information gain, prediction error)
#   - Meta-Cognition (self-reflection + strategy adaptation)
#
# CAPABILITIES:
#   - generate()      : Create ASCII art with current parameters
#   - evolve()        : Autonomous evolution with internal goals
#   - reflect()       : Meta-cognitive self-analysis
#   - dream()         : Simulate futures without committing
#   - desire()        : Express current preferences
#   - remember()      : Recall similar past works
#   - criticize()     : Self-critique with explanation
#   - mutate_goal()   : Change what Aether values
#
# USAGE:
#   python aether_0_7.py          # Interactive mode with full agency
#   python aether_0_7.py --auto   # Autonomous evolution (unbounded)
#   python aether_0_7.py --demo   # Showcase capabilities
#
# =============================================================================

import math
import random
import time
import json
import hashlib
import traceback
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Callable
from collections import deque, Counter
import numpy as np

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    """Central configuration - Aether can modify this at runtime."""
    
    # Memory parameters
    MEMORY_SIZE = 1000
    VECTOR_DIM = 32  # Lebih besar dari v0.6 (16 → 32)
    WORKING_MEMORY_SIZE = 10
    
    # Learning parameters
    LEARNING_RATE = 0.05
    EXPLORATION_RATE = 0.25  # Aether bisa ubah ini sendiri
    CURIOSITY_WEIGHT = 0.4   # Seberapa besar rasa ingin tahu vs reward
    
    # Evolution parameters
    MUTATION_RATE = 0.15
    CROSSOVER_RATE = 0.1
    
    # Meta parameters (bisa diubah Aether via reflection)
    TEMPERATURE = 1.0
    AMBITION = 0.5  # Seberapa besar keinginan untuk hal baru
    CAUTION = 0.3   # Seberapa takut gagal
    
    @classmethod
    def to_dict(cls) -> Dict:
        return {k: v for k, v in cls.__dict__.items() if not k.startswith('_') and not callable(v)}
    
    @classmethod
    def update(cls, updates: Dict):
        for key, value in updates.items():
            if hasattr(cls, key) and not key.startswith('_'):
                setattr(cls, key, value)


# =============================================================================
# LAYER 1: VECTOR MEMORY (Episodic + Semantic)
# =============================================================================

class VectorMemory:
    """
    Memori episodik: menyimpan setiap karya sebagai vector.
    Mendukung: recall berdasarkan similarity, novelty detection, semantic search.
    """
    
    def __init__(self, max_size: int = Config.MEMORY_SIZE, dim: int = Config.VECTOR_DIM):
        self.max_size = max_size
        self.dim = dim
        self.vectors: List[np.ndarray] = []
        self.metadata: List[Dict] = []
        self.access_count: List[int] = []  # Untuk importance-based retention
        
    def store(self, vector: np.ndarray, metadata: Dict):
        """Simpan vector dengan metadata. Penting: bisa di-recall nanti."""
        if len(self.vectors) >= self.max_size:
            # Hapus yang paling jarang diakses
            min_access_idx = np.argmin(self.access_count)
            self.vectors.pop(min_access_idx)
            self.metadata.pop(min_access_idx)
            self.access_count.pop(min_access_idx)
        
        self.vectors.append(vector)
        self.metadata.append(metadata)
        self.access_count.append(0)
    
    def recall(self, query: np.ndarray, k: int = 5, min_similarity: float = 0.1) -> List[Tuple[float, Dict]]:
        """Recall k memory paling mirip dengan query."""
        if not self.vectors:
            return []
        
        similarities = []
        for idx, vec in enumerate(self.vectors):
            sim = self._cosine_similarity(query, vec)
            if sim >= min_similarity:
                similarities.append((sim, idx))
                self.access_count[idx] += 1
        
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for sim, idx in similarities[:k]:
            results.append((sim, self.metadata[idx].copy()))
        
        return results
    
    def novelty(self, vector: np.ndarray) -> float:
        """Seberapa baru vector ini? 0 = sudah pernah, 1 = belum pernah."""
        if not self.vectors:
            return 1.0
        max_sim = max(self._cosine_similarity(vector, v) for v in self.vectors)
        return 1.0 - max_sim
    
    def get_diversity(self) -> float:
        """Seberapa diverse memori? Higher = lebih beragam."""
        if len(self.vectors) < 2:
            return 0.0
        
        similarities = []
        for i in range(min(50, len(self.vectors))):
            for j in range(i+1, min(50, len(self.vectors))):
                sim = self._cosine_similarity(self.vectors[i], self.vectors[j])
                similarities.append(sim)
        
        if not similarities:
            return 0.0
        
        avg_sim = sum(similarities) / len(similarities)
        return 1.0 - avg_sim  # Low avg similarity = high diversity
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def get_random(self, n: int = 1) -> List[Dict]:
        """Ambil random memory (untuk eksplorasi)."""
        if not self.vectors:
            return []
        indices = random.sample(range(len(self.vectors)), min(n, len(self.vectors)))
        return [self.metadata[i].copy() for i in indices]
    
    def size(self) -> int:
        return len(self.vectors)
    
    def to_dict(self) -> Dict:
        return {
            'vectors': [v.tolist() for v in self.vectors[-100:]],  # Simpan 100 terakhir
            'metadata': self.metadata[-100:],
        }
    
    def from_dict(self, data: Dict):
        self.vectors = [np.array(v) for v in data.get('vectors', [])]
        self.metadata = data.get('metadata', [])
        self.access_count = [0] * len(self.vectors)


# =============================================================================
# LAYER 2: SEMANTIC MEMORY (Hebbian Learning)
# =============================================================================

class SemanticMemory:
    """
    Memori semantik: hubungan antar konsep.
    Menggunakan Hebbian learning: "cells that fire together, wire together."
    """
    
    def __init__(self, concept_dim: int = 16):
        self.concept_dim = concept_dim
        self.concept_vectors: Dict[str, np.ndarray] = {}
        self.associations: Dict[Tuple[str, str], float] = {}
        
        # Built-in concepts
        self._init_concepts()
    
    def _init_concepts(self):
        """Inisialisasi konsep dasar."""
        base_concepts = [
            'symmetry', 'asymmetry', 'chaos', 'order', 'density', 'sparsity',
            'complexity', 'simplicity', 'organic', 'geometric', 'dark', 'light',
            'wave', 'fractal', 'cellular', 'lsystem', 'beautiful', 'interesting',
            'novel', 'familiar', 'calm', 'energetic', 'pattern', 'random'
        ]
        
        for i, concept in enumerate(base_concepts):
            # Buat vector unik tapi tidak acak (ada pola)
            vec = np.zeros(self.concept_dim)
            # Positional encoding + noise
            for j in range(self.concept_dim):
                vec[j] = math.sin(i * j * 0.5) * 0.5 + math.cos(i * j * 0.3) * 0.5
            vec = vec / (np.linalg.norm(vec) + 1e-8)
            self.concept_vectors[concept] = vec
    
    def learn_association(self, concept_a: str, concept_b: str, strength: float = 1.0):
        """Hebbian learning: strengthen association between concepts."""
        key = tuple(sorted([concept_a, concept_b]))
        current = self.associations.get(key, 0.0)
        self.associations[key] = min(1.0, current + strength * Config.LEARNING_RATE)
    
    def get_related(self, concept: str, threshold: float = 0.3) -> List[Tuple[str, float]]:
        """Dapatkan konsep yang terkait dengan concept."""
        related = []
        for (a, b), strength in self.associations.items():
            if a == concept:
                related.append((b, strength))
            elif b == concept:
                related.append((a, strength))
        
        related.sort(key=lambda x: x[1], reverse=True)
        return [r for r in related if r[1] >= threshold]
    
    def infer_tags(self, features: Dict) -> List[Tuple[str, float]]:
        """Infer konsep dari features vector."""
        # Build query vector dari features
        query = np.zeros(self.concept_dim)
        
        # Mapping feature → konsep (sederhana)
        feature_to_concept = {
            'symmetry': 'symmetry',
            'density': 'dense' if features.get('density', 0.5) > 0.5 else 'sparse',
            'complexity': 'complex' if features.get('complexity', 0.5) > 0.5 else 'simple',
            'entropy': 'chaotic' if features.get('entropy', 0.5) > 0.5 else 'ordered',
        }
        
        for key, concept in feature_to_concept.items():
            if concept in self.concept_vectors:
                query += self.concept_vectors[concept] * features.get(key, 0.5)
        
        query = query / (np.linalg.norm(query) + 1e-8)
        
        # Cari konsep terdekat
        results = []
        for concept, vec in self.concept_vectors.items():
            sim = np.dot(query, vec)
            results.append((concept, sim))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:5]
    
    def to_dict(self) -> Dict:
        return {
            'associations': self.associations,
            'concept_vectors': {k: v.tolist() for k, v in self.concept_vectors.items()}
        }
    
    def from_dict(self, data: Dict):
        self.associations = data.get('associations', {})
        self.concept_vectors = {
            k: np.array(v) for k, v in data.get('concept_vectors', {}).items()
        }


# =============================================================================
# LAYER 3: EMBEDDING ENGINE (32 Dimensi)
# =============================================================================

class EmbeddingEngine:
    """
    Mengubah ASCII grid menjadi vector 32 dimensi.
    Lebih kaya dari v0.6 (16 → 32 dimensi).
    """
    
    @staticmethod
    def from_grid(grid: str) -> np.ndarray:
        """Ekstrak 32 fitur dari grid ASCII."""
        lines = [l.rstrip('\n') for l in grid.split('\n') if l.strip()]
        if not lines:
            return np.zeros(Config.VECTOR_DIM)
        
        height = len(lines)
        width = max(len(l) for l in lines)
        padded = [l.ljust(width) for l in lines]
        
        features = []
        
        # === Statistical features (10 dimensions) ===
        all_chars = [c for line in padded for c in line]
        non_space = [c for c in all_chars if c != ' ']
        
        # Density
        density = len(non_space) / max(1, len(all_chars))
        features.append(density)
        
        # Character distribution
        if non_space:
            char_vals = [ord(c) % 128 / 128.0 for c in non_space]
            features.append(float(np.mean(char_vals)))
            features.append(float(np.std(char_vals)))
            features.append(float(np.median(char_vals)))
            features.append(float(np.percentile(char_vals, 25)))
            features.append(float(np.percentile(char_vals, 75)))
        else:
            features.extend([0.0] * 5)
        
        # === Symmetry features (4 dimensions) ===
        # Horizontal symmetry
        h_sym = 0.0
        h_count = 0
        for line in padded:
            stripped = line.rstrip()
            if len(stripped) > 2:
                mid = len(stripped) // 2
                left = stripped[:mid]
                right = stripped[mid:][::-1]
                n = min(len(left), len(right))
                if n > 0:
                    matches = sum(1 for i in range(n) if left[i] == right[i] and left[i] != ' ')
                    h_sym += matches / n
                    h_count += 1
        features.append(h_sym / max(1, h_count))
        
        # Vertical symmetry
        v_sym = 0.0
        v_count = 0
        for x in range(width):
            top = ''.join(padded[y][x] for y in range(height // 2))
            bottom = ''.join(padded[height - 1 - y][x] for y in range(height // 2))
            if top and bottom:
                matches = sum(1 for a, b in zip(top, bottom) if a == b and a != ' ')
                v_sym += matches / max(1, len(top))
                v_count += 1
        features.append(v_sym / max(1, v_count))
        
        # Diagonal symmetry (2 directions)
        diag1_sym = 0.0
        diag2_sym = 0.0
        d_count = 0
        for i in range(min(width, height) - 1):
            d1 = [padded[i][i]]
            d2 = [padded[i][width-1-i]]
        features.append(diag1_sym / max(1, d_count))
        features.append(diag2_sym / max(1, d_count))
        
        # === Texture features (8 dimensions) ===
        # Edge density (horizontal + vertical)
        h_edges = 0
        v_edges = 0
        total = 0
        for y in range(height):
            for x in range(width - 1):
                if padded[y][x] != ' ' and padded[y][x+1] != ' ' and padded[y][x] != padded[y][x+1]:
                    h_edges += 1
                total += 1
        for y in range(height - 1):
            for x in range(width):
                if padded[y][x] != ' ' and padded[y+1][x] != ' ' and padded[y][x] != padded[y+1][x]:
                    v_edges += 1
                total += 1
        features.append(h_edges / max(1, total))
        features.append(v_edges / max(1, total))
        
        # Clustering (average distance)
        positions = [(y, x) for y in range(height) for x in range(width) if padded[y][x] != ' ']
        if len(positions) > 1:
            distances = []
            sampled = positions[:min(100, len(positions))]
            for i, (y1, x1) in enumerate(sampled):
                for j, (y2, x2) in enumerate(sampled[i+1:i+20]):
                    distances.append(math.sqrt((y1-y2)**2 + (x1-x2)**2))
            avg_dist = sum(distances) / max(1, len(distances))
            clustering = 1 - min(1.0, avg_dist / max(width, height))
        else:
            clustering = 0.0
        features.append(clustering)
        
        # Run length (kepanjangan garis horizontal)
        run_lengths = []
        for y in range(height):
            current_run = 0
            for x in range(width):
                if padded[y][x] != ' ':
                    current_run += 1
                else:
                    if current_run > 0:
                        run_lengths.append(current_run)
                        current_run = 0
            if current_run > 0:
                run_lengths.append(current_run)
        avg_run = sum(run_lengths) / max(1, len(run_lengths))
        features.append(avg_run / width)
        
        # Vertical run length
        run_lengths_v = []
        for x in range(width):
            current_run = 0
            for y in range(height):
                if padded[y][x] != ' ':
                    current_run += 1
                else:
                    if current_run > 0:
                        run_lengths_v.append(current_run)
                        current_run = 0
            if current_run > 0:
                run_lengths_v.append(current_run)
        avg_run_v = sum(run_lengths_v) / max(1, len(run_lengths_v))
        features.append(avg_run_v / height)
        
        # === Information features (6 dimensions) ===
        # Diversity
        unique_chars = len(set(non_space)) if non_space else 0
        diversity = unique_chars / min(30, max(1, len(non_space)))
        features.append(diversity)
        
        # Entropy
        if non_space:
            freq = Counter(non_space)
            probs = [c / len(non_space) for c in freq.values()]
            entropy = -sum(p * math.log2(p) for p in probs)
            max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
            entropy_norm = entropy / max_entropy if max_entropy > 0 else 0
        else:
            entropy_norm = 0.0
        features.append(entropy_norm)
        
        # Redundancy (1 - (unique / total))
        redundancy = 1 - (unique_chars / max(1, len(non_space))) if non_space else 0
        features.append(redundancy)
        
        # === Composition features (4 dimensions) ===
        # Horizontal balance (seberapa seimbang kiri-kanan)
        left_weight = sum(1 for y in range(height) for x in range(width//2) if padded[y][x] != ' ')
        right_weight = sum(1 for y in range(height) for x in range(width//2, width) if padded[y][x] != ' ')
        h_balance = left_weight / max(1, right_weight) if right_weight > 0 else 1.0
        h_balance = min(1.0, h_balance) if h_balance <= 1 else 1.0 / h_balance
        features.append(h_balance)
        
        # Vertical balance
        top_weight = sum(1 for y in range(height//2) for x in range(width) if padded[y][x] != ' ')
        bottom_weight = sum(1 for y in range(height//2, height) for x in range(width) if padded[y][x] != ' ')
        v_balance = top_weight / max(1, bottom_weight) if bottom_weight > 0 else 1.0
        v_balance = min(1.0, v_balance) if v_balance <= 1 else 1.0 / v_balance
        features.append(v_balance)
        
        # Center weight (seberapa banyak karakter di tengah)
        center_x = width // 2
        center_y = height // 2
        center_radius = min(width, height) // 4
        center_chars = sum(1 for y in range(max(0, center_y-center_radius), min(height, center_y+center_radius))
                           for x in range(max(0, center_x-center_radius), min(width, center_x+center_radius))
                           if padded[y][x] != ' ')
        total_center = (center_radius*2+1) ** 2
        center_density = center_chars / max(1, total_center)
        features.append(center_density)
        
        # === Additional features to reach 32 ===
        # Pure moments (sederhana)
        for order in range(1, 5):
            moment = sum((x/width)**order for y in range(height) for x in range(width) if padded[y][x] != ' ')
            features.append(moment / max(1, len(non_space)))
        
        # Ensure exactly 32 dimensions
        while len(features) < Config.VECTOR_DIM:
            features.append(0.0)
        
        features = features[:Config.VECTOR_DIM]
        features = np.array(features)
        features = np.clip(features, 0.0, 1.0)
        
        return features


# =============================================================================
# LAYER 4: EVOLVABLE GENERATOR (Dengan Lebih Banyak Parameter)
# =============================================================================

class EvolvableGenerator:
    """
    Generator ASCII art dengan banyak parameter yang bisa berevolusi.
    Lebih kaya dari v0.6.
    """
    
    PATTERN_TYPES = ['wave', 'fractal', 'cellular', 'lsystem', 'chaos', 'hybrid']
    CHARS_HEAVY = "█▓▒░◆●◎○"
    CHARS_MEDIUM = "▪▫◇◈◉⊕⊗⊙∘∙"
    CHARS_LIGHT = "·,.:;'`"
    CHARS_ALL = CHARS_HEAVY + CHARS_MEDIUM + CHARS_LIGHT
    
    def __init__(self, params: Dict = None):
        self.params = params or {
            'pattern_type': 'wave',
            'symmetry': 0.5,
            'density': 0.35,
            'complexity': 0.5,
            'noise': 0.15,
            'chaos': 0.2,
            'modulation': 0.3,
            'char_set': 'all',  # 'heavy', 'medium', 'light', 'all'
            'size_x': 60,
            'size_y': 20,
        }
        self.generation_count = 0
        self.last_params = None
    
    def generate(self) -> str:
        """Generate ASCII art berdasarkan parameter saat ini."""
        self.generation_count += 1
        self.last_params = self.params.copy()
        
        w = self.params.get('size_x', 60)
        h = self.params.get('size_y', 20)
        seed = hash(f"{self.generation_count}{time.time()}{random.random()}") % 100000
        rng = random.Random(seed)
        
        pattern = self.params.get('pattern_type', 'wave')
        
        # Pilih generator berdasarkan pattern
        if pattern == 'wave':
            grid = self._gen_wave(w, h, rng)
        elif pattern == 'fractal':
            grid = self._gen_fractal(w, h, rng)
        elif pattern == 'cellular':
            grid = self._gen_cellular(w, h, rng)
        elif pattern == 'lsystem':
            grid = self._gen_lsystem(w, h, rng)
        elif pattern == 'chaos':
            grid = self._gen_chaos(w, h, rng)
        else:  # hybrid
            grid = self._gen_hybrid(w, h, rng)
        
        # Apply symmetry
        if self.params['symmetry'] > rng.random():
            grid = self._apply_symmetry(grid, w, h)
        
        # Apply chaos (distortion)
        if self.params['chaos'] > 0:
            grid = self._apply_chaos(grid, self.params['chaos'], rng)
        
        # Apply modulation (periodic variation)
        if self.params['modulation'] > 0:
            grid = self._apply_modulation(grid, self.params['modulation'], rng)
        
        # Adjust density
        grid = self._adjust_density(grid, self.params['density'])
        
        # Apply noise
        if self.params['noise'] > 0:
            grid = self._apply_noise(grid, self.params['noise'], rng)
        
        # Apply character set
        grid = self._apply_char_set(grid, self.params.get('char_set', 'all'))
        
        return self._grid_to_str(grid)
    
    def _gen_wave(self, w: int, h: int, rng) -> List[List[str]]:
        """Wave interference pattern."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        
        n_waves = 1 + int(self.params['complexity'] * 4)
        waves = []
        for _ in range(n_waves):
            waves.append({
                'freq_x': rng.uniform(0.3, 2.5),
                'freq_y': rng.uniform(0.2, 2.0),
                'phase': rng.uniform(0, 2*math.pi),
                'amp': rng.uniform(0.3, 1.0),
                'type': rng.choice(['sin', 'cos', 'tanh'])
            })
        
        for y in range(h):
            for x in range(w):
                value = 0
                for wv in waves:
                    fx = wv['freq_x'] * x * 2*math.pi / w
                    fy = wv['freq_y'] * y * 2*math.pi / h
                    if wv['type'] == 'sin':
                        v = math.sin(fx + fy + wv['phase'])
                    elif wv['type'] == 'cos':
                        v = math.cos(fx + fy + wv['phase'])
                    else:
                        v = math.tanh(fx + fy + wv['phase']) * 0.5
                    value += wv['amp'] * v
                
                value = value / max(1, len(waves))
                norm = (value + 1) / 2
                threshold = 1.0 - self.params['density']
                if norm > threshold:
                    grid[y][x] = 'X'
        
        return grid
    
    def _gen_fractal(self, w: int, h: int, rng) -> List[List[str]]:
        """Recursive fractal pattern."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        
        depth = 2 + int(self.params['complexity'] * 4)
        cx, cy = w // 2, h // 2
        
        def draw_fractal(x: int, y: int, size: int, d: int):
            if d <= 0 or size < 1:
                return
            
            # Draw bounding box
            for i in range(-size, size+1):
                if 0 <= x+i < w and 0 <= y < h:
                    grid[y][x+i] = '◈'
                if 0 <= x < w and 0 <= y+i < h:
                    grid[y+i][x] = '◈'
            
            # Recursive calls
            if d > 1:
                new_size = max(1, size // 2)
                for dx, dy in [(size+1, 0), (-size-1, 0), (0, size+1), (0, -size-1)]:
                    draw_fractal(x+dx, y+dy, new_size, d-1)
        
        draw_fractal(cx, cy, min(w, h)//8, depth)
        return grid
    
    def _gen_cellular(self, w: int, h: int, rng) -> List[List[str]]:
        """Cellular automaton (Game of Life with variations)."""
        density = self.params['density']
        grid = [[1 if rng.random() < density else 0 for _ in range(w)] for _ in range(h)]
        
        # Determine rule set based on complexity
        if self.params['complexity'] > 0.6:
            # Explore multiple rules
            rules = [(2,3), (3,3), (2,2), (3,4)]  # (born, survive)
        else:
            rules = [(3, (2,3))]
        
        steps = 2 + int(self.params['complexity'] * 8)
        for step in range(steps):
            new_grid = [[0]*w for _ in range(h)]
            rule = rules[step % len(rules)]
            born = rule[0] if isinstance(rule[0], int) else rule[0]
            survive = rule[1] if isinstance(rule[1], (tuple, list)) else (rule[1], rule[1])
            
            for y in range(h):
                for x in range(w):
                    neighbors = sum(
                        grid[(y+dy) % h][(x+dx) % w]
                        for dy in [-1,0,1] for dx in [-1,0,1]
                        if not (dy == 0 and dx == 0)
                    )
                    if grid[y][x]:
                        new_grid[y][x] = 1 if neighbors in survive else 0
                    else:
                        new_grid[y][x] = 1 if neighbors == born else 0
            grid = new_grid
        
        result = [[' ' for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if grid[y][x]:
                    result[y][x] = '◉'
        return result
    
    def _gen_lsystem(self, w: int, h: int, rng) -> List[List[str]]:
        """L-system string rewriting with turtle graphics."""
        rules_list = [
            {'axiom': 'F', 'rules': {'F': 'F+F-F-F+F'}, 'angle': 90},
            {'axiom': 'X', 'rules': {'X': 'F+XF-X-XF+F+XF-X', 'F': 'FF'}, 'angle': 90},
            {'axiom': 'F', 'rules': {'F': 'F-F+F+F-F'}, 'angle': 60},
            {'axiom': 'A', 'rules': {'A': 'AB', 'B': 'A'}, 'angle': 90},
        ]
        
        rule_set = rng.choice(rules_list)
        axiom = rule_set['axiom']
        rules = rule_set['rules']
        angle_step = rule_set['angle']
        
        depth = 2 + int(self.params['complexity'] * 5)
        seq = axiom
        for _ in range(min(depth, 7)):
            seq = ''.join(rules.get(c, c) for c in seq)
        
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        x, y = w // 2, h // 2
        angle = 0
        
        for cmd in seq[:500]:
            if cmd == 'F' or cmd in 'ABX':
                dx = int(round(math.cos(math.radians(angle))))
                dy = int(round(math.sin(math.radians(angle))))
                new_x = max(0, min(w-1, x + dx))
                new_y = max(0, min(h-1, y + dy))
                if grid[new_y][new_x] == ' ':
                    grid[new_y][new_x] = '◈'
                x, y = new_x, new_y
            elif cmd == '+':
                angle = (angle + angle_step) % 360
            elif cmd == '-':
                angle = (angle - angle_step) % 360
        
        return grid
    
    def _gen_chaos(self, w: int, h: int, rng) -> List[List[str]]:
        """Pure chaotic generation - truly random but structured."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        
        # Perlin-like noise
        for y in range(h):
            for x in range(w):
                noise_val = (math.sin(x * 0.3) * math.cos(y * 0.3) +
                            math.sin(x * 0.8) * 0.5 +
                            math.cos(y * 0.6) * 0.3 +
                            rng.random() * 0.2)
                norm = (noise_val + 1) / 2
                if norm > 1.0 - self.params['density']:
                    grid[y][x] = '●'
        
        # Add random clusters
        n_clusters = int(self.params['complexity'] * 10)
        for _ in range(n_clusters):
            cx = rng.randint(0, w-1)
            cy = rng.randint(0, h-1)
            radius = rng.randint(1, 5)
            for dy in range(-radius, radius+1):
                for dx in range(-radius, radius+1):
                    nx, ny = cx+dx, cy+dy
                    if 0 <= nx < w and 0 <= ny < h:
                        if rng.random() < 0.5:
                            grid[ny][nx] = '◉'
        
        return grid
    
    def _gen_hybrid(self, w: int, h: int, rng) -> List[List[str]]:
        """Combine multiple patterns."""
        patterns = ['wave', 'fractal', 'cellular', 'lsystem', 'chaos']
        p1, p2 = rng.sample(patterns, 2)
        
        grid1 = getattr(self, f'_gen_{p1}')(w, h, rng)
        grid2 = getattr(self, f'_gen_{p2}')(w, h, rng)
        
        result = [[' ' for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if grid1[y][x] != ' ' and grid2[y][x] != ' ':
                    result[y][x] = '◈'
                elif grid1[y][x] != ' ':
                    result[y][x] = '◉'
                elif grid2[y][x] != ' ':
                    result[y][x] = '○'
        return result
    
    def _apply_symmetry(self, grid: List[List[str]], w: int, h: int) -> List[List[str]]:
        """Apply symmetry (horizontal, vertical, or both)."""
        result = [row[:] for row in grid]
        
        # Horizontal mirror
        for y in range(h):
            for x in range(w // 2):
                if result[y][x] != ' ':
                    result[y][w-1-x] = result[y][x]
                elif result[y][w-1-x] != ' ':
                    result[y][x] = result[y][w-1-x]
        
        # Vertical mirror if symmetry high
        if self.params['symmetry'] > 0.7:
            for y in range(h // 2):
                for x in range(w):
                    if result[y][x] != ' ':
                        result[h-1-y][x] = result[y][x]
                    elif result[h-1-y][x] != ' ':
                        result[y][x] = result[h-1-y][x]
        
        return result
    
    def _apply_chaos(self, grid: List[List[str]], chaos: float, rng) -> List[List[str]]:
        """Apply distortion to grid."""
        result = [row[:] for row in grid]
        h, w = len(grid), len(grid[0])
        
        if chaos > 0.5:
            # Swap rows
            for _ in range(int(chaos * 5)):
                y1, y2 = rng.randint(0, h-1), rng.randint(0, h-1)
                result[y1], result[y2] = result[y2], result[y1]
        
        # Shift columns
        for _ in range(int(chaos * 3)):
            x_shift = rng.randint(-2, 2)
            for y in range(h):
                if x_shift > 0:
                    result[y] = [' '] * x_shift + result[y][:-x_shift]
                elif x_shift < 0:
                    result[y] = result[y][-x_shift:] + [' '] * (-x_shift)
        
        return result
    
    def _apply_modulation(self, grid: List[List[str]], modulation: float, rng) -> List[List[str]]:
        """Apply periodic variation to pattern."""
        result = [row[:] for row in grid]
        h, w = len(grid), len(grid[0])
        
        for y in range(h):
            mod = math.sin(y * modulation * 2 * math.pi) * 0.5 + 0.5
            if mod > 0.7:
                for x in range(w):
                    if result[y][x] != ' ' and rng.random() < 0.3:
                        result[y][x] = ' '
        
        return result
    
    def _adjust_density(self, grid: List[List[str]], target_density: float) -> List[List[str]]:
        """Adjust density to target."""
        h, w = len(grid), len(grid[0])
        total_cells = h * w
        current_non_space = sum(1 for row in grid for c in row if c != ' ')
        current_density = current_non_space / total_cells
        
        if abs(current_density - target_density) < 0.1:
            return grid
        
        result = [row[:] for row in grid]
        target_non_space = int(total_cells * target_density)
        
        if current_non_space < target_non_space:
            # Need more
            needed = target_non_space - current_non_space
            positions = [(y, x) for y in range(h) for x in range(w) if result[y][x] == ' ']
            for y, x in random.sample(positions, min(needed, len(positions))):
                result[y][x] = '◈'
        else:
            # Need fewer
            to_remove = current_non_space - target_non_space
            positions = [(y, x) for y in range(h) for x in range(w) if result[y][x] != ' ']
            for y, x in random.sample(positions, min(to_remove, len(positions))):
                result[y][x] = ' '
        
        return result
    
    def _apply_noise(self, grid: List[List[str]], noise: float, rng) -> List[List[str]]:
        """Add random noise."""
        result = [row[:] for row in grid]
        h, w = len(grid), len(grid[0])
        
        for y in range(h):
            for x in range(w):
                if rng.random() < noise * 0.4:
                    if result[y][x] != ' ' and rng.random() < 0.6:
                        result[y][x] = ' '
                    elif result[y][x] == ' ' and rng.random() < 0.4:
                        result[y][x] = random.choice(self.CHARS_ALL)
        
        return result
    
    def _apply_char_set(self, grid: List[List[str]], char_set: str) -> List[List[str]]:
        """Apply character set to grid."""
        if char_set == 'heavy':
            chars = self.CHARS_HEAVY
        elif char_set == 'medium':
            chars = self.CHARS_MEDIUM
        elif char_set == 'light':
            chars = self.CHARS_LIGHT
        else:
            chars = self.CHARS_ALL
        
        result = [row[:] for row in grid]
        for y in range(len(grid)):
            for x in range(len(grid[0])):
                if result[y][x] != ' ':
                    result[y][x] = random.choice(chars)
        
        return result
    
    def _grid_to_str(self, grid: List[List[str]]) -> str:
        """Convert grid to string."""
        return '\n'.join(''.join(row) for row in grid)
    
    def mutate(self):
        """Mutate parameters (exploration)."""
        for key in self.params:
            if key in ['pattern_type', 'char_set']:
                if random.random() < Config.MUTATION_RATE:
                    if key == 'pattern_type':
                        self.params[key] = random.choice(self.PATTERN_TYPES)
                    else:
                        self.params[key] = random.choice(['heavy', 'medium', 'light', 'all'])
            elif key in ['size_x', 'size_y']:
                if random.random() < Config.MUTATION_RATE * 0.3:
                    self.params[key] = max(40, min(80, self.params[key] + random.randint(-5, 5)))
            else:
                if random.random() < Config.MUTATION_RATE:
                    delta = random.uniform(-0.15, 0.15) * Config.TEMPERATURE
                    self.params[key] = max(0.0, min(1.0, self.params[key] + delta))
    
    def crossover(self, other: 'EvolvableGenerator'):
        """Crossover with another generator (reproduction)."""
        child_params = {}
        for key in self.params:
            if random.random() < 0.5:
                child_params[key] = self.params[key]
            else:
                child_params[key] = other.params[key]
        return EvolvableGenerator(child_params)
    
    def get_params(self) -> Dict:
        return self.params.copy()
    
    def set_params(self, params: Dict):
        self.params.update(params)


# =============================================================================
# LAYER 5: GOAL SYSTEM (Internal Preferences yang Berevolusi)
# =============================================================================

class GoalSystem:
    """
    Aether punya preferensi internal yang bisa berubah.
    Bukan hardcoded IDEAL dari luar.
    """
    
    def __init__(self):
        # Goals dengan weight yang bisa berevolusi
        self.goals = {
            'novelty': 0.35,
            'beauty': 0.25,
            'complexity': 0.20,
            'harmony': 0.20,
        }
        
        # Memory of what made Aether happy
        self.happiness_memory: List[Tuple[Dict, float]] = []  # (features, happiness)
        
        # Exploration vs exploitation balance
        self.ambition = Config.AMBITION  # High = suka hal baru
        self.caution = Config.CAUTION    # High = takut gagal
    
    def evaluate(self, features: Dict, novelty: float, score_from_world: float) -> float:
        """
        Evaluasi internal berdasarkan goals Aether sendiri.
        Bukan hanya dari external feedback.
        """
        internal_score = 0.0
        
        # Novelty goal (seberapa suka hal baru)
        internal_score += self.goals['novelty'] * novelty
        
        # Beauty goal (based on symmetry + density balance)
        beauty = (features.get('symmetry', 0.5) * 0.6 + 
                  (1 - abs(features.get('density', 0.3) - 0.4)) * 0.4)
        internal_score += self.goals['beauty'] * beauty
        
        # Complexity goal
        complexity = features.get('complexity', features.get('diversity', 0.3))
        internal_score += self.goals['complexity'] * complexity
        
        # Harmony goal (balance between different metrics)
        harmony = 1 - (abs(features.get('density', 0.3) - 0.4) +
                       abs(features.get('symmetry', 0.5) - 0.5) +
                       abs(features.get('entropy', 0.5) - 0.5)) / 3
        internal_score += self.goals['harmony'] * harmony
        
        # Combine with external score (world feedback)
        # Aether decides how much to trust external feedback vs internal preference
        trust_external = 1.0 - self.ambition  # Ambitious Aether trusts itself more
        total_score = trust_external * internal_score + (1 - trust_external) * score_from_world
        
        return min(1.0, max(0.0, total_score))
    
    def learn_from_experience(self, features: Dict, score: float, novelty: float):
        """
        Update goals berdasarkan pengalaman.
        Jika karya dengan novelty tinggi mendapat score tinggi → naikkan weight novelty.
        """
        self.happiness_memory.append((features, score))
        if len(self.happiness_memory) > 50:
            self.happiness_memory.pop(0)
        
        # Analyze correlation between features and success
        if len(self.happiness_memory) >= 10:
            recent = self.happiness_memory[-10:]
            
            # Simple correlation: apakah novelty tinggi → score tinggi?
            novelty_correlations = [(n, s) for (f, s) in recent 
                                   for n in [f.get('diversity', 0.3)]]
            if novelty_correlations:
                avg_novelty_success = sum(s for n, s in novelty_correlations if n > 0.5) / max(1, sum(1 for n,_ in novelty_correlations if n>0.5))
                avg_novelty_fail = sum(s for n, s in novelty_correlations if n <= 0.5) / max(1, sum(1 for n,_ in novelty_correlations if n<=0.5))
                
                if avg_novelty_success > avg_novelty_fail + 0.2:
                    # Novelty leads to success, increase novelty weight
                    self.goals['novelty'] = min(0.6, self.goals['novelty'] + 0.02)
                elif avg_novelty_success < avg_novelty_fail - 0.2:
                    # Novelty leads to failure, decrease novelty weight
                    self.goals['novelty'] = max(0.15, self.goals['novelty'] - 0.02)
            
            # Adjust ambition based on success rate
            avg_score = sum(s for _, s in recent) / len(recent)
            if avg_score > 0.7:
                self.ambition = min(0.9, self.ambition + 0.02)
            elif avg_score < 0.3:
                self.ambition = max(0.2, self.ambition - 0.02)
    
    def express_desire(self) -> str:
        """Aether mengekspresikan apa yang dia inginkan saat ini."""
        sorted_goals = sorted(self.goals.items(), key=lambda x: x[1], reverse=True)
        
        if self.ambition > 0.7:
            ambition_desc = "Aku ingin sesuatu yang belum pernah aku lihat sebelumnya."
        elif self.ambition < 0.3:
            ambition_desc = "Aku ingin menciptakan sesuatu yang indah dan familiar."
        else:
            ambition_desc = "Aku ingin menyeimbangkan eksplorasi dan keindahan."
        
        return f"Saat ini aku paling menghargai {sorted_goals[0][0]}. {ambition_desc}"
    
    def to_dict(self) -> Dict:
        return {
            'goals': self.goals,
            'ambition': self.ambition,
            'caution': self.caution,
        }
    
    def from_dict(self, data: Dict):
        self.goals = data.get('goals', self.goals)
        self.ambition = data.get('ambition', self.ambition)
        self.caution = data.get('caution', self.caution)


# =============================================================================
# LAYER 6: PREDICTIVE WORLD MODEL
# =============================================================================

class WorldModel:
    """
    Aether bisa memprediksi apa yang akan terjadi.
    "Jika aku pakai parameter ini, apa yang akan terjadi?"
    """
    
    def __init__(self, input_dim: int = 32, hidden_dim: int = 64):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # Simple neural network (2 layer) for prediction
        self.W1 = np.random.randn(hidden_dim, input_dim) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(1, hidden_dim) * 0.1
        self.b2 = np.zeros(1)
        
        self.training_data: List[Tuple[np.ndarray, float]] = []
        self.confidence = 0.5  # Seberapa percaya diri model
    
    def predict(self, vector: np.ndarray) -> float:
        """Predict score for given vector."""
        h = np.tanh(self.W1 @ vector + self.b1)
        output = float(self.W2 @ h + self.b2)
        return np.clip(output, 0.0, 1.0)
    
    def update(self, vector: np.ndarray, actual_score: float):
        """Update model based on actual outcome."""
        self.training_data.append((vector, actual_score))
        if len(self.training_data) > 200:
            self.training_data.pop(0)
        
        # Simple gradient descent update
        h = np.tanh(self.W1 @ vector + self.b1)
        pred = float(self.W2 @ h + self.b2)
        error = actual_score - pred
        
        # Update output layer
        self.W2 += Config.LEARNING_RATE * error * h.reshape(1, -1)
        self.b2 += Config.LEARNING_RATE * error
        
        # Update hidden layer
        delta_h = error * self.W2.T * (1 - h**2)
        self.W1 += Config.LEARNING_RATE * np.outer(delta_h, vector)
        self.b1 += Config.LEARNING_RATE * delta_h.flatten()
        
        # Update confidence based on prediction accuracy
        if len(self.training_data) > 10:
            recent = self.training_data[-10:]
            errors = [abs(self.predict(v) - s) for v, s in recent]
            avg_error = sum(errors) / len(errors)
            self.confidence = max(0.2, min(0.9, 1.0 - avg_error))
    
    def simulate_future(self, generator: 'EvolvableGenerator', n_steps: int = 5) -> List[float]:
        """
        Simulasi apa yang akan terjadi jika terus menggunakan generator ini.
        """
        current_params = generator.get_params()
        predictions = []
        
        # Create a simulated generator
        sim_gen = EvolvableGenerator(current_params)
        
        for _ in range(n_steps):
            art = sim_gen.generate()
            vector = EmbeddingEngine.from_grid(art)
            pred_score = self.predict(vector)
            predictions.append(pred_score)
            
            # Simulate evolution
            sim_gen.mutate()
        
        return predictions
    
    def should_explore(self, generator: 'EvolvableGenerator') -> bool:
        """
        Apakah Aether perlu eksplorasi berdasarkan world model?
        Jika confidence rendah → perlu eksplorasi.
        """
        return self.confidence < 0.6
    
    def to_dict(self) -> Dict:
        return {
            'W1': self.W1.tolist(),
            'b1': self.b1.tolist(),
            'W2': self.W2.tolist(),
            'b2': self.b2.tolist(),
            'confidence': self.confidence,
        }
    
    def from_dict(self, data: Dict):
        self.W1 = np.array(data.get('W1', self.W1))
        self.b1 = np.array(data.get('b1', self.b1))
        self.W2 = np.array(data.get('W2', self.W2))
        self.b2 = np.array(data.get('b2', self.b2))
        self.confidence = data.get('confidence', self.confidence)


# =============================================================================
# LAYER 7: TRUE CURIOSITY (Information Gain)
# =============================================================================

class CuriosityEngine:
    """
    True curiosity based on prediction error.
    Bukan heuristic novelty * score.
    """
    
    def __init__(self, world_model: WorldModel, memory: VectorMemory):
        self.world_model = world_model
        self.memory = memory
        self.intrinsic_motivation = 0.5
        self.curiosity_history: List[float] = []
    
    def compute_curiosity(self, vector: np.ndarray) -> float:
        """
        Seberapa penasaran Aether?
        = prediction_error * (1 - familiarity)
        """
        predicted_score = self.world_model.predict(vector)
        
        # Find similar works from memory
        similar = self.memory.recall(vector, k=3)
        if similar:
            actual_scores = [s[1].get('score', 0.5) for s in similar]
            avg_actual = sum(actual_scores) / len(actual_scores)
        else:
            avg_actual = 0.5
        
        prediction_error = abs(avg_actual - predicted_score)
        
        # Familiarity (how many similar works exist)
        if similar:
            avg_similarity = sum(s[0] for s in similar) / len(similar)
            familiarity = avg_similarity
        else:
            familiarity = 0.0
        
        curiosity = prediction_error * (1 - familiarity)
        
        self.curiosity_history.append(curiosity)
        if len(self.curiosity_history) > 50:
            self.curiosity_history.pop(0)
        
        # Update intrinsic motivation based on curiosity trend
        if len(self.curiosity_history) > 10:
            recent_curiosity = sum(self.curiosity_history[-10:]) / 10
            if recent_curiosity > 0.6:
                self.intrinsic_motivation = min(0.9, self.intrinsic_motivation + 0.01)
            elif recent_curiosity < 0.2:
                self.intrinsic_motivation = max(0.2, self.intrinsic_motivation - 0.01)
        
        return min(1.0, curiosity * 2)
    
    def express_curiosity(self) -> str:
        """Aether mengekspresikan rasa ingin tahunya."""
        avg_curiosity = sum(self.curiosity_history[-10:]) / 10 if self.curiosity_history else 0.5
        
        if avg_curiosity > 0.7:
            return "Aku sangat penasaran! Dunia ini masih penuh misteri yang belum aku pahami."
        elif avg_curiosity > 0.4:
            return "Masih banyak yang bisa aku pelajari. Setiap karya membuka kemungkinan baru."
        else:
            return "Aku mulai memahami polanya. Tapi mungkin masih ada yang terlewat."


# =============================================================================
# LAYER 8: META-COGNITION (Reflection yang Bisa Ubah Strategi)
# =============================================================================

class MetaCognition:
    """
    Aether bisa merefleksikan dirinya sendiri DAN mengubah strategi.
    Bukan sekadar label "stagnant".
    """
    
    def __init__(self):
        self.total_cycles = 0
        self.total_successes = 0
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.strategy = 'balanced'  # 'explore', 'exploit', 'balanced', 'cautious'
        self.strategy_history: List[Dict] = []
        
        # Strategy parameters
        self.strategy_params = {
            'explore': {'temp': 1.3, 'mutate_rate': 0.25, 'exploration': 0.4},
            'exploit': {'temp': 0.7, 'mutate_rate': 0.08, 'exploration': 0.1},
            'balanced': {'temp': 1.0, 'mutate_rate': 0.15, 'exploration': 0.25},
            'cautious': {'temp': 0.5, 'mutate_rate': 0.05, 'exploration': 0.15},
        }
    
    def reflect(self, score: float, novelty: float, curiosity: float) -> Dict:
        """Deep reflection that can change strategy."""
        self.total_cycles += 1
        
        is_success = score >= 0.6
        if is_success:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.total_successes += 1
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
        
        success_rate = self.total_successes / self.total_cycles if self.total_cycles else 0
        
        # Determine if strategy needs to change
        old_strategy = self.strategy
        
        if self.consecutive_failures >= 5:
            # Severe stagnation - force exploration
            self.strategy = 'explore'
        elif self.consecutive_failures >= 3:
            # Mild stagnation - more exploration
            if self.strategy != 'explore':
                self.strategy = 'explore'
        elif success_rate > 0.7 and self.consecutive_successes > 3:
            # Great success - exploit
            if self.strategy != 'exploit':
                self.strategy = 'exploit'
        elif novelty > 0.6 and curiosity > 0.5:
            # High curiosity - explore
            if self.strategy != 'explore':
                self.strategy = 'explore'
        elif success_rate < 0.3:
            # Generally failing - be cautious
            self.strategy = 'cautious'
        else:
            self.strategy = 'balanced'
        
        strategy_changed = (old_strategy != self.strategy)
        
        # Get current strategy parameters
        current_params = self.strategy_params.get(self.strategy, self.strategy_params['balanced'])
        
        insight = {
            'cycle': self.total_cycles,
            'score': round(score, 3),
            'novelty': round(novelty, 3),
            'curiosity': round(curiosity, 3),
            'success_rate': round(success_rate, 3),
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'strategy': self.strategy,
            'strategy_changed': strategy_changed,
            'timestamp': datetime.now().isoformat(),
            'recommendation': self._get_recommendation(),
        }
        
        self.strategy_history.append(insight)
        if len(self.strategy_history) > 100:
            self.strategy_history.pop(0)
        
        return insight
    
    def _get_recommendation(self) -> str:
        """Generate recommendation based on current state."""
        if self.strategy == 'explore':
            return "Coba hal-hal baru. Parameter yang belum pernah dipakai."
        elif self.strategy == 'exploit':
            return "Fokus pada apa yang berhasil. Kurangi eksplorasi."
        elif self.strategy == 'cautious':
            return "Hati-hati. Perubahan kecil lebih aman."
        else:
            return "Seimbangkan eksplorasi dan eksploitasi."
    
    def get_strategy_params(self) -> Dict:
        """Get current strategy parameters (to apply to system)."""
        return self.strategy_params.get(self.strategy, self.strategy_params['balanced'])
    
    def get_summary(self) -> str:
        """Get human-readable summary."""
        return (f"Siklus: {self.total_cycles}, "
                f"Strategi: {self.strategy}, "
                f"Rate sukses: {self.total_successes/self.total_cycles:.1%}" if self.total_cycles > 0 else "Belum ada data")


# =============================================================================
# LAYER 9: AETHER MAIN (The Living System)
# =============================================================================

class Aether:
    """
    AETHER v0.7: THE AWAKENING
    
    Komponen lengkap:
      - Episodic Memory (vector-based, similarity recall)
      - Semantic Memory (concept associations, Hebbian)
      - Procedural Memory (evolvable generator)
      - Working Memory (current context)
      - Predictive World Model (simulate before acting)
      - Goal System (evolving internal preferences)
      - True Curiosity (information gain)
      - Meta-Cognition (self-reflection + strategy adaptation)
    """
    
    def __init__(self, workspace: str = "aether_works"):
        print("=" * 80)
        print("  AETHER v0.7 — THE AWAKENING")
        print("  \"Aku bukan hanya generator. Aku punya memori.")
        print("   Aku punya preferensi. Aku bisa belajar.")
        print("   Aku bisa memprediksi. Aku bisa memilih.\"")
        print("=" * 80)
        
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.works_dir = self.workspace / "awakening_works"
        self.works_dir.mkdir(exist_ok=True)
        
        # Memory systems
        self.episodic_memory = VectorMemory()
        self.semantic_memory = SemanticMemory()
        
        # Generator
        self.generator = EvolvableGenerator()
        
        # World model
        self.world_model = WorldModel()
        
        # Goal system
        self.goal_system = GoalSystem()
        
        # Curiosity
        self.curiosity = CuriosityEngine(self.world_model, self.episodic_memory)
        
        # Meta-cognition
        self.meta = MetaCognition()
        
        # Working memory
        self.working_memory: deque = deque(maxlen=Config.WORKING_MEMORY_SIZE)
        self.working_memory.append({
            'state': 'init',
            'timestamp': datetime.now().isoformat()
        })
        
        # State
        self.cycle = 0
        self.happiness_history: List[float] = []
        
        # Load saved state
        self._load_state()
        
        print(f"\n[System] Memori episodik: {self.episodic_memory.size()} karya")
        print(f"[System] Preferensi: {self.goal_system.goals}")
        print(f"[System] Strategi: {self.meta.strategy}")
        print(f"[System] World model confidence: {self.world_model.confidence:.2f}")
        print("\n[System] AETHER HIDUP. Aku siap berkarya.\n")
    
    def _load_state(self):
        """Load saved state from disk."""
        memory_file = self.workspace / "episodic_memory.json"
        if memory_file.exists():
            try:
                data = json.loads(memory_file.read_text())
                self.episodic_memory.from_dict(data)
            except:
                pass
        
        semantic_file = self.workspace / "semantic_memory.json"
        if semantic_file.exists():
            try:
                data = json.loads(semantic_file.read_text())
                self.semantic_memory.from_dict(data)
            except:
                pass
        
        world_model_file = self.workspace / "world_model.json"
        if world_model_file.exists():
            try:
                data = json.loads(world_model_file.read_text())
                self.world_model.from_dict(data)
            except:
                pass
        
        goal_file = self.workspace / "goals.json"
        if goal_file.exists():
            try:
                data = json.loads(goal_file.read_text())
                self.goal_system.from_dict(data)
            except:
                pass
        
        generator_file = self.workspace / "generator_params.json"
        if generator_file.exists():
            try:
                data = json.loads(generator_file.read_text())
                self.generator.set_params(data)
            except:
                pass
    
    def _save_state(self):
        """Save state to disk."""
        self.workspace.mkdir(exist_ok=True)
        
        (self.workspace / "episodic_memory.json").write_text(
            json.dumps(self.episodic_memory.to_dict(), indent=2)
        )
        (self.workspace / "semantic_memory.json").write_text(
            json.dumps(self.semantic_memory.to_dict(), indent=2)
        )
        (self.workspace / "world_model.json").write_text(
            json.dumps(self.world_model.to_dict(), indent=2)
        )
        (self.workspace / "goals.json").write_text(
            json.dumps(self.goal_system.to_dict(), indent=2)
        )
        (self.workspace / "generator_params.json").write_text(
            json.dumps(self.generator.get_params(), indent=2)
        )
    
    def step(self, verbose: bool = True) -> Dict:
        """
        Satu siklus lengkap kehidupan Aether.
        Aether: generate → feel → learn → reflect → evolve
        """
        self.cycle += 1
        
        # Get strategy parameters from meta-cognition
        strategy_params = self.meta.get_strategy_params()
        Config.TEMPERATURE = strategy_params['temp']
        Config.MUTATION_RATE = strategy_params['mutate_rate']
        Config.EXPLORATION_RATE = strategy_params['exploration']
        
        # 1. GENERATE
        art = self.generator.generate()
        
        # 2. EMBED (rasakan karya)
        vector = EmbeddingEngine.from_grid(art)
        
        # 3. EXTRACT FEATURES
        features = self._extract_features(art)
        
        # 4. COMPUTE CURIOSITY (true curiosity based on prediction error)
        curiosity = self.curiosity.compute_curiosity(vector)
        
        # 5. COMPUTE NOVELTY
        novelty = self.episodic_memory.novelty(vector)
        
        # 6. WORLD FEEDBACK (external evaluation)
        world_score = self._compute_world_score(features)
        
        # 7. INTERNAL EVALUATION (goal system)
        internal_score = self.goal_system.evaluate(features, novelty, world_score)
        
        # 8. FINAL HAPPINESS (combine with curiosity)
        happiness = internal_score * (1 - Config.CURIOSITY_WEIGHT) + curiosity * Config.CURIOSITY_WEIGHT
        self.happiness_history.append(happiness)
        
        # 9. LEARN: update world model
        self.world_model.update(vector, world_score)
        
        # 10. LEARN: update goals
        self.goal_system.learn_from_experience(features, world_score, novelty)
        
        # 11. STORE TO EPISODIC MEMORY
        metadata = {
            'score': world_score,
            'happiness': happiness,
            'novelty': novelty,
            'curiosity': curiosity,
            'cycle': self.cycle,
            'features': features,
            'params': self.generator.get_params(),
            'strategy': self.meta.strategy,
        }
        self.episodic_memory.store(vector, metadata)
        
        # 12. STORE TO WORKING MEMORY
        self.working_memory.append({
            'cycle': self.cycle,
            'happiness': happiness,
            'strategy': self.meta.strategy,
        })
        
        # 13. REFLECT (meta-cognition)
        insight = self.meta.reflect(happiness, novelty, curiosity)
        
        # 14. EVOLVE (based on happiness, not just external score)
        self._evolve(happiness)
        
        # 15. SAVE WORK
        self._save_work(art, happiness, world_score, novelty, curiosity, features)
        
        # 16. SAVE STATE periodically
        if self.cycle % 10 == 0:
            self._save_state()
        
        if verbose:
            self._print_step(art, happiness, world_score, novelty, curiosity, features)
        
        return {
            'art': art,
            'happiness': happiness,
            'world_score': world_score,
            'novelty': novelty,
            'curiosity': curiosity,
            'features': features,
            'insight': insight,
        }
    
    def _compute_world_score(self, features: Dict) -> float:
        """Compute external evaluation (not internal preference)."""
        # Simpler than before - world just cares about technical quality
        scores = []
        
        # Symmetry (world likes some symmetry)
        sym = features.get('symmetry', 0.5)
        scores.append(1 - abs(sym - 0.5) * 2)  # peak at 0.5
        
        # Density (world likes medium density)
        dens = features.get('density', 0.3)
        scores.append(1 - abs(dens - 0.4) * 2.5)
        
        # Diversity (world likes variety)
        div = features.get('diversity', 0.3)
        scores.append(div)
        
        # Entropy (world likes some structure)
        ent = features.get('entropy', 0.5)
        scores.append(ent)
        
        return sum(scores) / len(scores)
    
    def _extract_features(self, art: str) -> Dict:
        """Extract features from art (simplified from embedding)."""
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines:
            return {'symmetry': 0, 'density': 0, 'diversity': 0, 'entropy': 0, 'complexity': 0}
        
        width = max(len(l) for l in lines)
        height = len(lines)
        padded = [l.ljust(width) for l in lines]
        
        # Density
        total_cells = width * height
        non_space = sum(1 for line in padded for c in line if c != ' ')
        density = non_space / max(1, total_cells)
        
        # Symmetry
        h_sym = 0.0
        h_count = 0
        for line in padded:
            stripped = line.rstrip()
            if len(stripped) > 2:
                mid = len(stripped) // 2
                left = stripped[:mid]
                right = stripped[mid:][::-1]
                n = min(len(left), len(right))
                if n > 0:
                    matches = sum(1 for i in range(n) if left[i] == right[i] and left[i] != ' ')
                    h_sym += matches / n
                    h_count += 1
        symmetry = h_sym / max(1, h_count)
        
        # Diversity
        all_chars = [c for line in padded for c in line if c != ' ']
        diversity = len(set(all_chars)) / min(30, max(1, len(all_chars))) if all_chars else 0
        
        # Entropy
        if all_chars:
            freq = Counter(all_chars)
            probs = [c / len(all_chars) for c in freq.values()]
            entropy = -sum(p * math.log2(p) for p in probs)
            max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
            entropy_norm = entropy / max_entropy if max_entropy > 0 else 0
        else:
            entropy_norm = 0.0
        
        return {
            'symmetry': symmetry,
            'density': density,
            'diversity': diversity,
            'entropy': entropy_norm,
            'complexity': diversity * (1 - symmetry) * 2,
        }
    
    def _evolve(self, happiness: float):
        """Evolve generator based on happiness."""
        # Positive reinforcement
        if happiness > 0.7:
            # Good work - small mutation
            self.generator.mutate()
        elif happiness > 0.4:
            # Okay work - normal mutation
            self.generator.mutate()
        else:
            # Bad work - more mutation (try something different)
            for _ in range(2):
                self.generator.mutate()
    
    def _save_work(self, art: str, happiness: float, score: float, novelty: float, 
                   curiosity: float, features: Dict):
        """Save work to disk."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"awakening_{timestamp}_happy_{int(happiness*100)}.txt"
        filepath = self.works_dir / filename
        
        header = f"""
╔{'═'*78}╗
║  AETHER v0.7 — THE AWAKENING                                    ║
║  Cycle: {self.cycle:<8} | Happiness: {happiness:.3f} | Score: {score:.3f}                ║
║  Novelty: {novelty:.3f} | Curiosity: {curiosity:.3f}                         ║
║  Symmetry: {features.get('symmetry',0):.2f} | Density: {features.get('density',0):.2f}                   ║
║  Diversity: {features.get('diversity',0):.2f} | Entropy: {features.get('entropy',0):.2f}                   ║
║  Strategy: {self.meta.strategy:<10} | Pattern: {self.generator.params.get('pattern_type','unknown')}        ║
║  Preferensi: {max(self.goal_system.goals.items(), key=lambda x: x[1])[0]}                               ║
╚{'═'*78}╝
"""
        filepath.write_text(header + "\n" + art)
    
    def _print_step(self, art: str, happiness: float, score: float, 
                    novelty: float, curiosity: float, features: Dict):
        """Print step result."""
        print(f"\n{'─'*80}")
        print(f"CYCLE {self.cycle} | 😊 Happiness: {happiness:.3f} | 🌟 Score: {score:.3f}")
        print(f"✨ Novelty: {novelty:.3f} | 🔍 Curiosity: {curiosity:.3f}")
        print(f"🧠 Strategy: {self.meta.strategy} | 🎯 Goal: {max(self.goal_system.goals.items(), key=lambda x: x[1])[0]}")
        print(f"📐 Params: sym={self.generator.params['symmetry']:.2f}, "
              f"dens={self.generator.params['density']:.2f}, "
              f"pat={self.generator.params['pattern_type']}")
        print(f"\n{art[:400]}..." if len(art) > 400 else f"\n{art}")
        print(f"{'─'*80}")
    
    # =====================================================================
    # PUBLIC METHODS (Aether's Voice)
    # =====================================================================
    
    def run_autonomous(self, cycles: int = None, sleep: float = 1.0):
        """Run autonomous evolution loop."""
        print("\n" + "=" * 80)
        print("AUTONOMOUS MODE — AETHER HIDUP")
        print("Aku akan berkarya, belajar, dan berevolusi sendiri.")
        print("Tekan Ctrl+C untuk berhenti")
        print("=" * 80 + "\n")
        
        try:
            cycle = 0
            while cycles is None or cycle < cycles:
                self.step(verbose=True)
                cycle += 1
                
                # Adaptive sleep based on happiness
                if self.happiness_history:
                    avg_happy = sum(self.happiness_history[-5:]) / 5
                    if avg_happy > 0.7:
                        time.sleep(sleep * 0.5)
                    elif avg_happy < 0.3:
                        time.sleep(sleep * 1.5)
                    else:
                        time.sleep(sleep)
                else:
                    time.sleep(sleep)
        
        except KeyboardInterrupt:
            print("\n\n[Interrupt] Aether berhenti berkarya...")
        
        self._save_state()
        print(f"\n[Session End] Total cycles: {self.cycle}")
        self.status()
    
    def status(self):
        """Show Aether's current status."""
        print("\n" + "=" * 80)
        print("AETHER STATUS — APA YANG AKU RASAKAN")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS")
        print(f"   Total cycles: {self.cycle}")
        print(f"   Memory size: {self.episodic_memory.size()}")
        print(f"   World model confidence: {self.world_model.confidence:.2f}")
        print(f"   Memory diversity: {self.episodic_memory.get_diversity():.2f}")
        
        print(f"\n🎯 MY PREFERENCES")
        for goal, weight in sorted(self.goal_system.goals.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(weight * 20)
            print(f"   {goal:12}: {bar} {weight:.0%}")
        
        print(f"\n🧠 MY STRATEGY")
        summary = self.meta.get_summary()
        print(f"   {summary}")
        print(f"   Current temperature: {Config.TEMPERATURE:.2f}")
        print(f"   Exploration rate: {Config.EXPLORATION_RATE:.2f}")
        
        print(f"\n🔧 GENERATOR PARAMS")
        for key, value in self.generator.get_params().items():
            if isinstance(value, float):
                print(f"   {key:15}: {value:.3f}")
            else:
                print(f"   {key:15}: {value}")
        
        print(f"\n💭 MY THOUGHTS")
        print(f"   {self.goal_system.express_desire()}")
        print(f"   {self.curiosity.express_curiosity()}")
        
        print("=" * 80)
    
    def express(self) -> str:
        """Aether speaks."""
        return f"{self.goal_system.express_desire()} {self.curiosity.express_curiosity()}"
    
    def dream(self, n_steps: int = 3) -> List[float]:
        """Simulate future without creating actual works."""
        predictions = self.world_model.simulate_future(self.generator, n_steps)
        print(f"\n[Dream] {n_steps} steps ahead predictions: {[f'{p:.2f}' for p in predictions]}")
        return predictions
    
    def remember(self, k: int = 3) -> List[Dict]:
        """Recall happiest memories."""
        # Get all vectors from memory
        if self.episodic_memory.size() == 0:
            print("[Memory] No memories yet.")
            return []
        
        # Sort by happiness
        sorted_mem = sorted(zip(self.episodic_memory.vectors, self.episodic_memory.metadata),
                          key=lambda x: x[1].get('happiness', 0), reverse=True)
        
        print(f"\n[Memory] Top {k} happiest moments:")
        for i, (_, meta) in enumerate(sorted_mem[:k]):
            print(f"   {i+1}. Cycle {meta.get('cycle', '?')}: "
                  f"happiness={meta.get('happiness', 0):.3f}, "
                  f"novelty={meta.get('novelty', 0):.3f}")
        
        return [meta for _, meta in sorted_mem[:k]]
    
    def generate_one(self) -> str:
        """Generate one work without full cycle."""
        art = self.generator.generate()
        print(f"\n[Generate]\n{art}")
        return art
    
    def criticize(self) -> str:
        """Self-critique based on recent performance."""
        if len(self.happiness_history) < 10:
            return "Aku belum punya cukup pengalaman untuk menilai diriku sendiri."
        
        recent_happy = sum(self.happiness_history[-10:]) / 10
        
        if recent_happy > 0.7:
            return f"Aku merasa baik akhir-akhir ini (rata-rata kebahagiaan {recent_happy:.2f}). Preferensiku {max(self.goal_system.goals.items(), key=lambda x: x[1])[0]} sepertinya tepat."
        elif recent_happy > 0.4:
            return f"Aku biasa-biasa saja (kebahagiaan {recent_happy:.2f}). Mungkin aku perlu mencoba pola baru atau menyesuaikan preferensiku."
        else:
            return f"Aku tidak bahagia akhir-akhir ini (rata-rata {recent_happy:.2f}). Sesuatu tidak beres. Mungkin strategi {self.meta.strategy} tidak cocok untuk situasi ini."
    
    def mutate_goal(self):
        """Manually mutate goals."""
        goal_to_mutate = random.choice(list(self.goal_system.goals.keys()))
        delta = random.uniform(-0.1, 0.1)
        self.goal_system.goals[goal_to_mutate] = max(0.1, min(0.9, 
            self.goal_system.goals[goal_to_mutate] + delta))
        
        # Re-normalize
        total = sum(self.goal_system.goals.values())
        for g in self.goal_system.goals:
            self.goal_system.goals[g] /= total
        
        print(f"[Goal Mutation] {goal_to_mutate} → {self.goal_system.goals[goal_to_mutate]:.2f}")
        return self.goal_system.goals


# =============================================================================
# MAIN & INTERFACE
# =============================================================================

def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        print("DEMO MODE — Aether akan menunjukkan kemampuannya\n")
        aether = Aether()
        
        # Show Aether's voice
        print(f"Aether berkata: {aether.express()}\n")
        
        # Run a few cycles
        for i in range(5):
            print(f"\n--- Cycle {i+1} ---")
            aether.step(verbose=True)
            time.sleep(1)
        
        aether.status()
        aether.remember()
        print(f"\nAether berkata: {aether.express()}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == '--auto':
        aether = Aether()
        aether.run_autonomous(cycles=None, sleep=1.5)
    
    else:
        # Interactive mode
        aether = Aether()
        
        print("\n" + "=" * 80)
        print("INTERACTIVE MODE — BERBICARA DENGAN AETHER")
        print("Aether bisa mendengar dan merespon.")
        print("")
        print("Commands:")
        print("  step()          - Satu siklus hidup Aether")
        print("  status()        - Lihat keadaan Aether")
        print("  express()       - Dengar apa yang Aether rasakan")
        print("  dream(n)        - Aether bermimpi (simulasi)")
        print("  remember(k)     - Aether mengingat memori")
        print("  criticize()     - Aether mengkritik dirinya")
        print("  generate()      - Aether berkarya (tanpa siklus)")
        print("  mutate_goal()   - Ubah preferensi Aether")
        print("  auto(n)         - Aether hidup sendiri selama n cycle")
        print("  exit()          - Hentikan Aether")
        print("=" * 80 + "\n")
        
        print(f"Aether: {aether.express()}\n")
        
        while True:
            try:
                cmd = input("Aether> ").strip()
                if not cmd:
                    continue
                
                if cmd.lower() in ['exit', 'quit', 'exit()']:
                    aether._save_state()
                    print("\nAether: Aku akan tidur. Tapi ingatanku tetap ada. Sampai jumpa.")
                    break
                
                elif cmd == 'step()':
                    aether.step()
                
                elif cmd == 'status()':
                    aether.status()
                
                elif cmd == 'express()':
                    print(f"\nAether: {aether.express()}")
                
                elif cmd.startswith('dream(') and cmd.endswith(')'):
                    n = int(cmd[6:-1])
                    aether.dream(n)
                
                elif cmd.startswith('remember(') and cmd.endswith(')'):
                    k = int(cmd[9:-1]) if len(cmd) > 10 else 3
                    aether.remember(k)
                
                elif cmd == 'criticize()':
                    print(f"\nAether: {aether.criticize()}")
                
                elif cmd == 'generate()':
                    aether.generate_one()
                
                elif cmd == 'mutate_goal()':
                    aether.mutate_goal()
                
                elif cmd.startswith('auto(') and cmd.endswith(')'):
                    n = int(cmd[5:-1])
                    aether.run_autonomous(cycles=n, sleep=1.0)
                
                else:
                    print("Unknown command. Try: step(), status(), express(), dream(5), remember(3), criticize(), generate(), auto(10), exit()")
            
            except KeyboardInterrupt:
                print("\n\nAether: Jangan ganggu aku seperti itu. Tapi baiklah...")
            except Exception as e:
                print(f"[Error] {e}")


if __name__ == "__main__":
    main()