#!/usr/bin/env python3
# =============================================================================
# AETHER v0.6: KARYA HIDUP — Cognitive Architecture dengan Vector Memory
# =============================================================================
#
# PRINCIPLES:
#   1. Ada vector representation (embedding) dari setiap karya
#   2. Ada memory berbasis similarity (cosine) untuk recall
#   3. Ada feedback numerik yang konsisten (0.0-1.0)
#   4. Ada generator yang bisa dievolusi (evolusi parameter)
#   5. Ada novelty detection (bukan random, berdasar similarity)
#   6. Ada evolution REAL: parameter berubah berdasarkan hasil
#
# COGNITIVE ARCHITECTURE:
#   - Episodic Memory: vector-based, similarity retrieval
#   - Semantic Memory: feature associations
#   - Procedural Memory: generator parameters that evolve
#   - Curiosity Engine: novelty-driven exploration
#   - Reflection Loop: meta-cognitive evaluation
#
# USAGE:
#   python aether_0_6.py          # Interactive mode
#   python aether_0_6.py --auto   # Autonomous evolution
#   python aether_0_6.py --demo   # Demonstration
#
# =============================================================================

import math
import random
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import deque
import numpy as np

# =============================================================================
# LAYER 1: CORE STORAGE & VECTOR SPACE (Protected)
# =============================================================================

class VectorMemory:
    """
    Semantic/Episodic memory berdasarkan vector embedding.
    Bukan JSON kosong — setiap memory punya vector representation.
    
    Operasi:
      - store(vector, metadata)  → simpan
      - recall(query_vector, k)  → k terdekat dengan cosine similarity
      - novelty(vector)          → 1 - max_similarity (semakin beda, semakin baru)
    """
    
    def __init__(self, max_size: int = 500, vector_dim: int = 16):
        self.max_size = max_size
        self.vector_dim = vector_dim
        self.vectors: List[np.ndarray] = []
        self.metadata: List[Dict] = []
        
    def store(self, vector: np.ndarray, metadata: Dict):
        """Simpan vector + metadata ke memory."""
        if len(self.vectors) >= self.max_size:
            # Hapus yang paling lama (FIFO sederhana)
            self.vectors.pop(0)
            self.metadata.pop(0)
        
        self.vectors.append(vector)
        self.metadata.append(metadata)
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity antara dua vector."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def recall(self, query: np.ndarray, k: int = 3) -> List[Tuple[float, Dict]]:
        """Cari k memory paling mirip dengan query."""
        if not self.vectors:
            return []
        
        similarities = [(self._cosine_similarity(query, vec), idx) 
                        for idx, vec in enumerate(self.vectors)]
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        for sim, idx in similarities[:k]:
            if sim > 0:  # Hanya yang positif
                results.append((sim, self.metadata[idx].copy()))
        return results
    
    def novelty(self, vector: np.ndarray) -> float:
        """
        Seberapa baru vector ini?
        novelty = 1 - max_similarity
        0 = sudah pernah lihat (sangat mirip)
        1 = belum pernah lihat (sangat berbeda)
        """
        if not self.vectors:
            return 1.0
        
        max_sim = max(self._cosine_similarity(vector, v) for v in self.vectors)
        return 1.0 - max_sim
    
    def get_all_vectors(self) -> List[np.ndarray]:
        return self.vectors.copy()
    
    def size(self) -> int:
        return len(self.vectors)


# =============================================================================
# LAYER 2: EMBEDDING ENGINE (Grid → Vector Representation)
# =============================================================================

class EmbeddingEngine:
    """
    Mengubah grid ASCII art menjadi vector representation.
    Bukan JSON kosong — vector yang bermakna secara statistik.
    
    Feature extraction:
      1. Density: proporsi karakter non-spasi
      2. Horizontal symmetry: mirror similarity
      3. Vertical symmetry: mirror similarity
      4. Character diversity: unique chars / total
      5. Edge density: perubahan karakter di batas
      6. Clustering: seberapa mengelompok
      7. Entropy: information content
    """
    
    DIMENSION = 16  # embedding size
    
    @staticmethod
    def from_grid(grid: str) -> np.ndarray:
        """Ekstrak fitur dari grid ASCII menjadi vector 16 dimensi."""
        lines = [l.rstrip('\n') for l in grid.split('\n') if l.strip()]
        if not lines:
            return np.zeros(EmbeddingEngine.DIMENSION)
        
        # Hitung dimensi grid
        height = len(lines)
        width = max(len(l) for l in lines) if lines else 0
        
        # Pad semua line ke width yang sama
        padded = [l.ljust(width) for l in lines]
        
        features = []
        
        # 1. Density (0-1)
        total_cells = width * height
        non_space = sum(1 for line in padded for c in line if c != ' ')
        density = non_space / max(1, total_cells)
        features.append(density)
        
        # 2. Horizontal symmetry
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
        
        # 3. Vertical symmetry
        v_sym = 0.0
        v_count = 0
        for x in range(width):
            top_half = ''.join(padded[y][x] for y in range(height // 2))
            bottom_half = ''.join(padded[height - 1 - y][x] for y in range(height // 2))
            if top_half and bottom_half:
                matches = sum(1 for a, b in zip(top_half, bottom_half) if a == b and a != ' ')
                v_sym += matches / max(1, len(top_half))
                v_count += 1
        features.append(v_sym / max(1, v_count))
        
        # 4. Character diversity
        all_chars = [c for line in padded for c in line if c != ' ']
        if all_chars:
            unique = len(set(all_chars))
            diversity = unique / min(30, len(all_chars))
        else:
            diversity = 0.0
        features.append(diversity)
        
        # 5. Edge density (perubahan karakter)
        edge_count = 0
        edge_total = 0
        for y in range(height):
            for x in range(width - 1):
                if padded[y][x] != ' ' and padded[y][x+1] != ' ' and padded[y][x] != padded[y][x+1]:
                    edge_count += 1
                edge_total += 1
        for y in range(height - 1):
            for x in range(width):
                if padded[y][x] != ' ' and padded[y+1][x] != ' ' and padded[y][x] != padded[y+1][x]:
                    edge_count += 1
                edge_total += 1
        edge_density = edge_count / max(1, edge_total)
        features.append(edge_density)
        
        # 6. Clustering (average distance between non-space chars)
        positions = [(y, x) for y in range(height) for x in range(width) if padded[y][x] != ' ']
        if len(positions) > 1:
            distances = []
            sampled = positions[:min(50, len(positions))]
            for i, (y1, x1) in enumerate(sampled):
                for j, (y2, x2) in enumerate(sampled[i+1:i+10]):
                    distances.append(math.sqrt((y1-y2)**2 + (x1-x2)**2))
            avg_dist = sum(distances) / max(1, len(distances))
            clustering = 1 - min(1.0, avg_dist / max(width, height))
        else:
            clustering = 0.0
        features.append(clustering)
        
        # 7. Entropy
        if all_chars:
            from collections import Counter
            freq = Counter(all_chars)
            probs = [count / len(all_chars) for count in freq.values()]
            entropy = -sum(p * math.log2(p) for p in probs)
            max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
            entropy_norm = entropy / max_entropy if max_entropy > 0 else 0
        else:
            entropy_norm = 0.0
        features.append(entropy_norm)
        
        # 8-16. Statistical moments dari grid values
        # Convert char ke nilai numerik sederhana (0-1)
        char_values = []
        for line in padded:
            for c in line:
                if c == ' ':
                    char_values.append(0.0)
                else:
                    char_values.append((ord(c) % 128) / 128.0)
        
        if char_values:
            arr = np.array(char_values)
            features.append(float(np.mean(arr)))           # 8
            features.append(float(np.std(arr)))            # 9
            features.append(float(np.median(arr)))         # 10
            features.append(float(np.percentile(arr, 25))) # 11
            features.append(float(np.percentile(arr, 75))) # 12
            features.append(float(np.max(arr)))            # 13
            features.append(float(np.min(arr)))            # 14
            features.append(float(np.sum(arr) / len(arr))) # 15
        else:
            features.extend([0.0] * 8)
        
        # Normalisasi ke range [0,1]
        features = np.array(features)
        features = np.clip(features, 0.0, 1.0)
        
        # Pastikan dimensi tepat
        if len(features) < EmbeddingEngine.DIMENSION:
            features = np.pad(features, (0, EmbeddingEngine.DIMENSION - len(features)))
        elif len(features) > EmbeddingEngine.DIMENSION:
            features = features[:EmbeddingEngine.DIMENSION]
        
        return features


# =============================================================================
# LAYER 3: GENERATOR (Procedural + Evolvable)
# =============================================================================

class EvolvableGenerator:
    """
    Generator ASCII art yang param-nya bisa berevolusi.
    
    Parameter (bisa diubah berdasarkan feedback):
      - symmetry: bias simetri (0.0-1.0)
      - density: kepadatan karakter (0.0-1.0)
      - complexity: kompleksitas struktur (0.0-1.0)
      - noise: randomness level (0.0-1.0)
      - pattern_type: 'wave', 'fractal', 'cellular', 'lsystem'
    """
    
    PATTERN_TYPES = ['wave', 'fractal', 'cellular', 'lsystem', 'random']
    CHARS = " .:-=+*#%@@@"
    
    def __init__(self, params: Dict = None):
        self.params = params or {
            'symmetry': 0.5,
            'density': 0.3,
            'complexity': 0.5,
            'noise': 0.2,
            'pattern_type': 'wave'
        }
        self.generation_count = 0
    
    def generate(self, width: int = 52, height: int = 18) -> str:
        """Generate ASCII art berdasarkan parameter saat ini."""
        self.generation_count += 1
        seed = hash(f"{self.generation_count}{time.time()}{random.random()}") % 100000
        
        rng = random.Random(seed)
        
        # Pilih pattern type (bisa override dari params)
        pattern = self.params.get('pattern_type', 'wave')
        if pattern == 'random':
            pattern = rng.choice(self.PATTERN_TYPES[:-1])
        
        # Generate pattern
        if pattern == 'wave':
            grid = self._gen_wave(width, height, rng)
        elif pattern == 'fractal':
            grid = self._gen_fractal(width, height, rng)
        elif pattern == 'cellular':
            grid = self._gen_cellular(width, height, rng)
        elif pattern == 'lsystem':
            grid = self._gen_lsystem(width, height, rng)
        else:
            grid = self._gen_wave(width, height, rng)
        
        # Apply symmetry
        if self.params['symmetry'] > rng.random():
            grid = self._apply_symmetry(grid, width, height)
        
        # Apply density adjustment
        grid = self._adjust_density(grid, self.params['density'])
        
        # Apply noise
        if self.params['noise'] > 0:
            grid = self._apply_noise(grid, self.params['noise'], rng)
        
        return self._grid_to_str(grid)
    
    def _gen_wave(self, w: int, h: int, rng) -> List[List[str]]:
        """Wave interference pattern."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        
        n_waves = 1 + int(self.params['complexity'] * 3)
        waves = []
        for _ in range(n_waves):
            waves.append({
                'freq_x': rng.uniform(0.5, 2.5),
                'freq_y': rng.uniform(0.3, 2.0),
                'phase': rng.uniform(0, 2*math.pi),
                'amp': rng.uniform(0.3, 1.0),
            })
        
        for y in range(h):
            for x in range(w):
                value = sum(
                    wv['amp'] * math.sin(
                        wv['freq_x'] * x * 2*math.pi/w +
                        wv['freq_y'] * y * 2*math.pi/h +
                        wv['phase']
                    )
                    for wv in waves
                ) / max(1, len(waves))
                
                norm = (value + 1) / 2
                threshold = 1.0 - self.params['density']
                if norm > threshold:
                    idx = int(norm * (len(self.CHARS)-1))
                    grid[y][x] = self.CHARS[min(idx, len(self.CHARS)-1)]
        
        return grid
    
    def _gen_fractal(self, w: int, h: int, rng) -> List[List[str]]:
        """Recursive fractal pattern."""
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        
        depth = 2 + int(self.params['complexity'] * 3)
        cx, cy = w // 2, h // 2
        
        def draw_cross(x: int, y: int, size: int, d: int):
            if d <= 0 or size < 1:
                return
            if x < 0 or x >= w or y < 0 or y >= h:
                return
            
            char_idx = d % len(self.CHARS)
            for i in range(-size, size+1):
                if 0 <= x+i < w and 0 <= y < h:
                    if grid[y][x+i] == ' ' or rng.random() < 0.7:
                        grid[y][x+i] = self.CHARS[char_idx]
                if 0 <= x < w and 0 <= y+i < h:
                    if grid[y+i][x] == ' ' or rng.random() < 0.7:
                        grid[y+i][x] = self.CHARS[char_idx]
            
            new_size = max(1, size // 2)
            for dx, dy in [(size+1,0), (-size-1,0), (0,size+1), (0,-size-1)]:
                draw_cross(x+dx, y+dy, new_size, d-1)
        
        draw_cross(cx, cy, min(w, h)//6, depth)
        return grid
    
    def _gen_cellular(self, w: int, h: int, rng) -> List[List[str]]:
        """Cellular automaton (Game of Life variant)."""
        density = self.params['density']
        grid = [[1 if rng.random() < density else 0 for _ in range(w)] for _ in range(h)]
        
        steps = 2 + int(self.params['complexity'] * 5)
        for _ in range(steps):
            new_grid = [[0]*w for _ in range(h)]
            for y in range(h):
                for x in range(w):
                    neighbors = sum(
                        grid[(y+dy) % h][(x+dx) % w]
                        for dy in [-1,0,1] for dx in [-1,0,1]
                        if not (dy == 0 and dx == 0)
                    )
                    if grid[y][x]:
                        new_grid[y][x] = 1 if neighbors in [2,3] else 0
                    else:
                        new_grid[y][x] = 1 if neighbors == 3 else 0
            grid = new_grid
        
        result = [[' ' for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if grid[y][x]:
                    idx = int(rng.random() * len(self.CHARS))
                    result[y][x] = self.CHARS[idx]
        return result
    
    def _gen_lsystem(self, w: int, h: int, rng) -> List[List[str]]:
        """L-system string rewriting."""
        rules = {
            'A': 'AB',
            'B': 'A'
        }
        axiom = 'A'
        depth = 2 + int(self.params['complexity'] * 4)
        
        seq = axiom
        for _ in range(min(depth, 6)):
            seq = ''.join(rules.get(c, c) for c in seq)
        
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        x, y = w // 2, h // 2
        angle = 0
        chars = self.CHARS
        
        for cmd in seq[:300]:
            if cmd in 'AB':
                dx = int(round(math.cos(math.radians(angle))))
                dy = int(round(math.sin(math.radians(angle))))
                x = max(0, min(w-1, x + dx))
                y = max(0, min(h-1, y + dy))
                if grid[y][x] == ' ' or rng.random() < 0.3:
                    grid[y][x] = chars[int(rng.random() * len(chars))]
            elif cmd == '+':
                angle = (angle + 90) % 360
            elif cmd == '-':
                angle = (angle - 90) % 360
        
        return grid
    
    def _apply_symmetry(self, grid: List[List[str]], w: int, h: int) -> List[List[str]]:
        """Apply horizontal and/or vertical symmetry."""
        result = [row[:] for row in grid]
        
        # Horizontal mirror
        for y in range(h):
            for x in range(w // 2):
                if result[y][x] != ' ':
                    result[y][w-1-x] = result[y][x]
                elif result[y][w-1-x] != ' ':
                    result[y][x] = result[y][w-1-x]
        
        # Vertical mirror jika symmetry tinggi
        if self.params['symmetry'] > 0.7:
            for y in range(h // 2):
                for x in range(w):
                    if result[y][x] != ' ':
                        result[h-1-y][x] = result[y][x]
                    elif result[h-1-y][x] != ' ':
                        result[y][x] = result[h-1-y][x]
        
        return result
    
    def _adjust_density(self, grid: List[List[str]], target_density: float) -> List[List[str]]:
        """Adjust density to target value."""
        h, w = len(grid), len(grid[0])
        total_cells = h * w
        current_non_space = sum(1 for row in grid for c in row if c != ' ')
        current_density = current_non_space / total_cells
        
        if abs(current_density - target_density) < 0.1:
            return grid
        
        result = [row[:] for row in grid]
        target_non_space = int(total_cells * target_density)
        
        if current_non_space < target_non_space:
            # Need more characters
            needed = target_non_space - current_non_space
            positions = [(y, x) for y in range(h) for x in range(w) if result[y][x] == ' ']
            for y, x in random.sample(positions, min(needed, len(positions))):
                result[y][x] = self.CHARS[random.randint(2, len(self.CHARS)-1)]
        else:
            # Need fewer characters
            to_remove = current_non_space - target_non_space
            positions = [(y, x) for y in range(h) for x in range(w) if result[y][x] != ' ']
            for y, x in random.sample(positions, min(to_remove, len(positions))):
                result[y][x] = ' '
        
        return result
    
    def _apply_noise(self, grid: List[List[str]], noise_level: float, rng) -> List[List[str]]:
        """Add random noise to grid."""
        result = [row[:] for row in grid]
        h, w = len(grid), len(grid[0])
        
        for y in range(h):
            for x in range(w):
                if rng.random() < noise_level * 0.3:
                    # Flip atau random char
                    if result[y][x] != ' ' and rng.random() < 0.5:
                        result[y][x] = ' '
                    elif result[y][x] == ' ' and rng.random() < 0.3:
                        result[y][x] = self.CHARS[int(rng.random() * len(self.CHARS))]
        
        return result
    
    def _grid_to_str(self, grid: List[List[str]]) -> str:
        """Convert grid ke string."""
        return '\n'.join(''.join(row) for row in grid)
    
    def mutate(self, rate: float = 0.2):
        """Mutasi parameter generator."""
        for key in self.params:
            if key == 'pattern_type':
                if random.random() < rate:
                    self.params[key] = random.choice(self.PATTERN_TYPES)
            else:
                if random.random() < rate:
                    delta = random.uniform(-0.15, 0.15)
                    self.params[key] = max(0.0, min(1.0, self.params[key] + delta))
    
    def get_params(self) -> Dict:
        return self.params.copy()
    
    def set_params(self, params: Dict):
        self.params.update(params)


# =============================================================================
# LAYER 4: FEEDBACK ENGINE (Evolution berbasis hasil)
# =============================================================================

class FeedbackEngine:
    """
    Feedback numerik konsisten (0.0-1.0) untuk setiap karya.
    Parameter generator berevolusi berdasarkan feedback.
    """
    
    # Target ideal untuk setiap metric
    IDEAL = {
        'density': (0.25, 0.55),
        'symmetry': (0.4, 0.75),
        'diversity': (0.3, 0.7),
        'edge_density': (0.05, 0.25),
        'clustering': (0.3, 0.6),
        'entropy': (0.5, 0.85)
    }
    
    LEARNING_RATE = 0.06
    
    def __init__(self, generator: EvolvableGenerator):
        self.generator = generator
        self.history: List[float] = []
    
    def evaluate(self, vector: np.ndarray, features: Dict) -> float:
        """
        Evaluasi kualitas karya dari features.
        Returns score 0.0-1.0.
        """
        total_score = 0.0
        count = 0
        
        for metric, (low, high) in self.IDEAL.items():
            val = features.get(metric, 0.0)
            if low <= val <= high:
                total_score += 1.0
            elif val < low:
                total_score += max(0, val / low)
            else:
                total_score += max(0, high / val)
            count += 1
        
        score = total_score / count if count > 0 else 0.0
        self.history.append(score)
        return score
    
    def evolve_generator(self, features: Dict, score: float):
        """
        Evolusi parameter generator berdasarkan gap dengan ideal.
        REAL evolution — parameter berubah berdasarkan hasil.
        """
        # Adjust symmetry
        actual_sym = features.get('symmetry', 0.5)
        ideal_sym = sum(self.IDEAL['symmetry']) / 2
        delta_sym = self.LEARNING_RATE * (ideal_sym - actual_sym) * (score if score > 0.5 else -0.1)
        new_sym = self.generator.params['symmetry'] + delta_sym
        self.generator.params['symmetry'] = max(0.0, min(1.0, new_sym))
        
        # Adjust density
        actual_dens = features.get('density', 0.3)
        ideal_dens = sum(self.IDEAL['density']) / 2
        delta_dens = self.LEARNING_RATE * (ideal_dens - actual_dens) * (0.5 + score)
        new_dens = self.generator.params['density'] + delta_dens
        self.generator.params['density'] = max(0.1, min(0.8, new_dens))
        
        # Adjust complexity (dari diversity + edge_density)
        actual_div = features.get('diversity', 0.3)
        actual_edge = features.get('edge_density', 0.1)
        actual_complexity = (actual_div + actual_edge) / 2
        delta_complex = self.LEARNING_RATE * (0.5 - actual_complexity) * score
        new_complex = self.generator.params['complexity'] + delta_complex
        self.generator.params['complexity'] = max(0.1, min(0.9, new_complex))
        
        # Adjust noise: lebih tinggi jika score rendah (eksplorasi)
        if score < 0.4:
            self.generator.params['noise'] = min(0.6, self.generator.params['noise'] + 0.02)
        elif score > 0.7:
            self.generator.params['noise'] = max(0.05, self.generator.params['noise'] - 0.01)
        
        # Pattern type evolution
        if score < 0.3:
            # Jika gagal terus, ganti pattern type
            patterns = EvolvableGenerator.PATTERN_TYPES
            current = self.generator.params.get('pattern_type', 'wave')
            others = [p for p in patterns if p != current and p != 'random']
            if others:
                self.generator.params['pattern_type'] = random.choice(others)
                print(f"[Feedback] Evolving pattern: {current} → {self.generator.params['pattern_type']}")
    
    def get_avg_score(self, last_n: int = 10) -> float:
        if not self.history:
            return 0.0
        return sum(self.history[-last_n:]) / min(len(self.history), last_n)


# =============================================================================
# LAYER 5: CURIOSITY ENGINE (Novelty-driven exploration)
# =============================================================================

class CuriosityEngine:
    """
    Bukan random — tapi novelty-driven exploration.
    Semakin novelty tinggi, semakin penasaran.
    """
    
    def __init__(self, memory: VectorMemory):
        self.memory = memory
        self.curiosity_temp = 0.5  # Semakin tinggi, semakin suka eksplorasi
    
    def curiosity_score(self, vector: np.ndarray) -> float:
        """
        Seberapa penasaran Aether dengan karya ini?
        = novelty * (1 - average_score_from_similar)
        """
        novelty = self.memory.novelty(vector)
        
        similar = self.memory.recall(vector, k=3)
        if similar:
            avg_score = sum(s[1].get('score', 0) for s in similar) / len(similar)
        else:
            avg_score = 0.0
        
        # Curiosity tinggi jika (novelty tinggi) DAN (hasil serupa sebelumnya buruk)
        curiosity = novelty * (1 - avg_score)
        return min(1.0, curiosity * self.curiosity_temp * 2)
    
    def should_explore(self, vector: np.ndarray, threshold: float = 0.3) -> bool:
        """Apakah perlu eksplorasi? True jika curiosity > threshold."""
        return self.curiosity_score(vector) > threshold
    
    def set_temperature(self, temp: float):
        self.curiosity_temp = max(0.1, min(1.0, temp))


# =============================================================================
# LAYER 6: REFLECTION ENGINE (Meta-cognitive evaluation)
# =============================================================================

class ReflectionEngine:
    """
    Aether mengevaluasi dirinya sendiri per siklus.
    Menghasilkan insight dan rekomendasi.
    """
    
    def __init__(self):
        self.total_cycles = 0
        self.total_successes = 0
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.session_log: List[Dict] = []
    
    def reflect(self, score: float, novelty: float, curiosity: float) -> Dict:
        """Proses hasil satu siklus."""
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
        
        # Deteksi kondisi
        if self.consecutive_failures >= 3:
            state = 'stagnant'
            recommendation = "STAGNANT: Perlu eksplorasi lebih agresif atau evolve generator"
        elif self.consecutive_successes >= 2:
            state = 'momentum'
            recommendation = "MOMENTUM: Lanjutkan, parameter di jalur yang benar"
        elif novelty > 0.7 and curiosity > 0.5:
            state = 'curious'
            recommendation = "CURIOUS: Eksplorasi area baru yang menjanjikan"
        else:
            state = 'normal'
            recommendation = "NORMAL: Lanjutkan siklus"
        
        insight = {
            'cycle': self.total_cycles,
            'score': round(score, 3),
            'novelty': round(novelty, 3),
            'curiosity': round(curiosity, 3),
            'state': state,
            'recommendation': recommendation,
            'success_rate': round(success_rate, 3),
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'timestamp': datetime.now().isoformat()
        }
        
        self.session_log.append(insight)
        self._print_reflection(insight)
        return insight
    
    def _print_reflection(self, insight: Dict):
        icons = {'momentum': '🚀', 'stagnant': '⚠️', 'curious': '🔍', 'normal': '🔄'}
        icon = icons.get(insight['state'], '❓')
        print(f"\n[Reflection] {icon} Cycle {insight['cycle']}: "
              f"score={insight['score']:.2f} | {insight['state']}")
        print(f"             → {insight['recommendation']}")
    
    def get_summary(self) -> Dict:
        return {
            'total_cycles': self.total_cycles,
            'total_successes': self.total_successes,
            'success_rate': round(self.total_successes / max(1, self.total_cycles), 2),
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
        }


# =============================================================================
# LAYER 7: AETHER MAIN (Cognitive Architecture)
# =============================================================================

class Aether:
    """
    AETHER v0.6 — "Karya Hidup"
    
    Cognitive components:
      - VectorMemory: similarity-based recall
      - EmbeddingEngine: grid → vector representation (16 dimensi!)
      - EvolvableGenerator: parameter berevolusi
      - FeedbackEngine: consistent numeric feedback (0.0-1.0)
      - CuriosityEngine: novelty-driven exploration
      - ReflectionEngine: meta-cognitive evaluation
    
    Core loop:
      1. Generate karya (dengan parameter saat ini)
      2. Extract vector representation
      3. Compute novelty (vs memory)
      4. Compute curiosity score
      5. Get feedback score (0.0-1.0)
      6. Store vector + metadata ke memory
      7. Evolve generator berdasarkan feedback
      8. Reflect dan learn
    """
    
    def __init__(self, project_dir: str = "aether_works"):
        print("=" * 70)
        print("  AETHER v0.6 — KARYA HIDUP")
        print("  Cognitive Architecture dengan Vector Memory")
        print("  Similarity-based recall | Novelty-driven exploration")
        print("  Parameter evolution based on REAL feedback")
        print("=" * 70)
        
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(exist_ok=True)
        self.works_dir = self.project_dir / "works"
        self.works_dir.mkdir(exist_ok=True)
        
        # Cognitive components
        self.memory = VectorMemory(max_size=500, vector_dim=16)
        self.generator = EvolvableGenerator()
        self.feedback = FeedbackEngine(self.generator)
        self.curiosity = CuriosityEngine(self.memory)
        self.reflection = ReflectionEngine()
        
        # State
        self.cycle = 0
        self.works_count = 0
        
        # Load saved state
        self._load_state()
        
        print(f"\n[System] Vector Memory: {self.memory.size()} stored works")
        print(f"[System] Generator params: {self.generator.get_params()}")
        print(f"[System] Ready for autonomous evolution\n")
    
    def _load_state(self):
        """Load saved memory and generator state."""
        memory_file = self.project_dir / "memory.json"
        if memory_file.exists():
            try:
                data = json.loads(memory_file.read_text())
                for item in data:
                    vec = np.array(item['vector'])
                    self.memory.store(vec, item['metadata'])
                print(f"[System] Loaded {len(data)} works from memory")
            except:
                pass
        
        params_file = self.project_dir / "generator_params.json"
        if params_file.exists():
            try:
                params = json.loads(params_file.read_text())
                self.generator.set_params(params)
            except:
                pass
    
    def _save_state(self):
        """Save memory and generator state."""
        memory_data = []
        for vec, meta in zip(self.memory.vectors, self.memory.metadata):
            memory_data.append({
                'vector': vec.tolist(),
                'metadata': meta
            })
        (self.project_dir / "memory.json").write_text(json.dumps(memory_data, indent=2))
        (self.project_dir / "generator_params.json").write_text(
            json.dumps(self.generator.get_params(), indent=2)
        )
    
    def step(self, verbose: bool = True) -> Dict:
        """
        Satu siklus lengkap Aether:
        Generate → Embed → Evaluate → Store → Evolve → Reflect
        """
        self.cycle += 1
        
        # 1. Generate
        art = self.generator.generate()
        
        # 2. Extract vector representation (16 dimensi!)
        vector = EmbeddingEngine.from_grid(art)
        
        # 3. Extract features untuk evaluasi
        features = self._extract_features(art)
        
        # 4. Compute novelty dan curiosity
        novelty = self.memory.novelty(vector)
        curiosity = self.curiosity.curiosity_score(vector)
        
        # 5. Feedback evaluation (score 0.0-1.0)
        score = self.feedback.evaluate(vector, features)
        
        # 6. Adjust curiosity temperature based on success
        if score > 0.7:
            self.curiosity.set_temperature(self.curiosity.curiosity_temp * 0.98)
        elif score < 0.3 and self.cycle > 20:
            self.curiosity.set_temperature(min(0.9, self.curiosity.curiosity_temp * 1.03))
        
        # 7. Store to memory
        metadata = {
            'score': score,
            'novelty': novelty,
            'curiosity': curiosity,
            'cycle': self.cycle,
            'features': features,
            'params_snapshot': self.generator.get_params()
        }
        self.memory.store(vector, metadata)
        
        # 8. Evolve generator based on feedback (REAL evolution!)
        self.feedback.evolve_generator(features, score)
        
        # 9. Simpan karya ke file
        self.works_count += 1
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"work_{timestamp}_score_{int(score*100)}.txt"
        filepath = self.works_dir / filename
        
        header = f"""
╔{'═'*66}╗
║  AETHER v0.6 — Work #{self.works_count}                                 ║
║  Cycle: {self.cycle:<8} | Score: {score:.3f} | Novelty: {novelty:.3f}           ║
║  Symmetry: {features.get('symmetry',0):.2f} | Density: {features.get('density',0):.2f}                 ║
║  Diversity: {features.get('diversity',0):.2f} | Entropy: {features.get('entropy',0):.2f}                 ║
║  Generator: {self.generator.params.get('pattern_type','unknown')}                                   ║
╚{'═'*66}╝
"""
        filepath.write_text(header + "\n" + art)
        
        # 10. Reflection
        insight = self.reflection.reflect(score, novelty, curiosity)
        
        # 11. Save state periodically
        if self.cycle % 10 == 0:
            self._save_state()
        
        if verbose:
            self._print_step(art, score, novelty, curiosity, features)
        
        return {
            'art': art,
            'score': score,
            'novelty': novelty,
            'curiosity': curiosity,
            'vector': vector,
            'features': features,
            'insight': insight
        }
    
    def _extract_features(self, art: str) -> Dict:
        """Extract features from art string."""
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines:
            return {k: 0.0 for k in FeedbackEngine.IDEAL.keys()}
        
        width = max(len(l) for l in lines)
        height = len(lines)
        padded = [l.ljust(width) for l in lines]
        
        # Density
        total_cells = width * height
        non_space = sum(1 for line in padded for c in line if c != ' ')
        density = non_space / max(1, total_cells)
        
        # Symmetry (horizontal)
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
        
        # Edge density
        edge_count = 0
        edge_total = 0
        for y in range(height):
            for x in range(width - 1):
                if padded[y][x] != ' ' and padded[y][x+1] != ' ' and padded[y][x] != padded[y][x+1]:
                    edge_count += 1
                edge_total += 1
        for y in range(height - 1):
            for x in range(width):
                if padded[y][x] != ' ' and padded[y+1][x] != ' ' and padded[y][x] != padded[y+1][x]:
                    edge_count += 1
                edge_total += 1
        edge_density = edge_count / max(1, edge_total)
        
        # Clustering
        positions = [(y, x) for y in range(height) for x in range(width) if padded[y][x] != ' ']
        if len(positions) > 1:
            distances = []
            sampled = positions[:min(50, len(positions))]
            for i, (y1, x1) in enumerate(sampled):
                for j, (y2, x2) in enumerate(sampled[i+1:i+10]):
                    distances.append(math.sqrt((y1-y2)**2 + (x1-x2)**2))
            avg_dist = sum(distances) / max(1, len(distances))
            clustering = 1 - min(1.0, avg_dist / max(width, height))
        else:
            clustering = 0.0
        
        # Entropy
        if all_chars:
            from collections import Counter
            freq = Counter(all_chars)
            probs = [c / len(all_chars) for c in freq.values()]
            entropy = -sum(p * math.log2(p) for p in probs) if probs else 0
            max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
            entropy_norm = entropy / max_entropy if max_entropy > 0 else 0
        else:
            entropy_norm = 0.0
        
        return {
            'density': density,
            'symmetry': symmetry,
            'diversity': diversity,
            'edge_density': edge_density,
            'clustering': clustering,
            'entropy': entropy_norm
        }
    
    def _print_step(self, art: str, score: float, novelty: float, curiosity: float, features: Dict):
        """Print step result."""
        print(f"\n{'─'*70}")
        print(f"CYCLE {self.cycle} | Score: {score:.3f} | Novelty: {novelty:.3f} | Curiosity: {curiosity:.3f}")
        print(f"Params: sym={self.generator.params['symmetry']:.2f}, "
              f"dens={self.generator.params['density']:.2f}, "
              f"pat={self.generator.params['pattern_type']}")
        print(f"Features: sym={features.get('symmetry',0):.2f}, "
              f"dens={features.get('density',0):.2f}, "
              f"div={features.get('diversity',0):.2f}, "
              f"ent={features.get('entropy',0):.2f}")
        print(f"\n{art[:400]}..." if len(art) > 400 else f"\n{art}")
        print(f"{'─'*70}")
    
    def run_autonomous(self, cycles: int = None, verbose: bool = True):
        """Run autonomous evolution loop."""
        print("\n" + "=" * 70)
        print("AUTONOMOUS EVOLUTION MODE")
        print("Aether akan berevolusi sendiri berdasarkan feedback")
        print("Tekan Ctrl+C untuk berhenti")
        print("=" * 70 + "\n")
        
        try:
            cycle = 0
            while cycles is None or cycle < cycles:
                self.step(verbose)
                cycle += 1
                
                # Adaptive sleep: lebih cepat jika momentum
                insight = self.reflection.session_log[-1] if self.reflection.session_log else {}
                if insight.get('state') == 'momentum':
                    time.sleep(1)
                elif insight.get('state') == 'stagnant':
                    time.sleep(2)
                else:
                    time.sleep(1.5)
        
        except KeyboardInterrupt:
            print("\n\n[Interrupt] Stopping autonomous evolution...")
        
        self._save_state()
        print(f"\n[Session End] Total cycles: {self.cycle}, Works: {self.works_count}")
        self.print_status()
    
    def print_status(self):
        """Print current status."""
        print("\n" + "=" * 70)
        print("AETHER STATUS")
        print("=" * 70)
        
        print(f"\n[Memory] {self.memory.size()} works stored")
        print(f"[Generator] {self.generator.get_params()}")
        print(f"[Reflection] {self.reflection.get_summary()}")
        print(f"[Avg Score (last 10)] {self.feedback.get_avg_score():.3f}")
        
        # Tampilkan beberapa works terbaru
        print(f"\n[Recent Works]")
        works = sorted(self.works_dir.glob("work_*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        for w in works:
            size = w.stat().st_size
            print(f"  - {w.name} ({size} bytes)")
        
        print("=" * 70)
    
    def generate_one(self) -> str:
        """Generate one work without storing (manual)."""
        art = self.generator.generate()
        print(f"\n[Generated]")
        print(art)
        return art
    
    def show_memory(self, k: int = 5):
        """Show top k works from memory."""
        if self.memory.size() == 0:
            print("[Memory] Empty")
            return
        
        # Sort by score
        sorted_mem = sorted(zip(self.memory.vectors, self.memory.metadata), 
                          key=lambda x: x[1].get('score', 0), reverse=True)
        
        print(f"\n[Top {k} Works from Memory]")
        for i, (vec, meta) in enumerate(sorted_mem[:k]):
            print(f"  {i+1}. Score: {meta.get('score',0):.3f} | "
                  f"Novelty: {meta.get('novelty',0):.3f} | "
                  f"Cycle: {meta.get('cycle',0)}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        print("DEMO MODE — 10 cycles of autonomous evolution\n")
        aether = Aether()
        aether.run_autonomous(cycles=10, verbose=True)
        aether.print_status()
    
    elif len(sys.argv) > 1 and sys.argv[1] == '--auto':
        aether = Aether()
        aether.run_autonomous(cycles=None, verbose=True)
    
    else:
        # Interactive mode
        aether = Aether()
        print("\n" + "=" * 70)
        print("INTERACTIVE MODE")
        print("Commands:")
        print("  step()          - Run one evolution cycle")
        print("  status()        - Show current status")
        print("  generate()      - Generate one work (no store)")
        print("  memory()        - Show top works from memory")
        print("  auto(n)         - Run n autonomous cycles")
        print("  exit()          - Quit")
        print("=" * 70 + "\n")
        
        while True:
            try:
                cmd = input("Aether> ").strip()
                if not cmd:
                    continue
                
                if cmd.lower() in ['exit', 'quit']:
                    aether._save_state()
                    print("\n[Shutdown] State saved. Goodbye.")
                    break
                
                elif cmd == 'step()':
                    aether.step()
                
                elif cmd == 'status()':
                    aether.print_status()
                
                elif cmd == 'generate()':
                    aether.generate_one()
                
                elif cmd == 'memory()':
                    aether.show_memory()
                
                elif cmd.startswith('auto(') and cmd.endswith(')'):
                    n = int(cmd[5:-1])
                    aether.run_autonomous(cycles=n)
                
                else:
                    print("Unknown command. Try: step(), status(), generate(), memory(), auto(10), exit()")
            
            except KeyboardInterrupt:
                print("\n\n[Interrupt] Use exit() to quit.")
            except Exception as e:
                print(f"[Error] {e}")


if __name__ == "__main__":
    main()