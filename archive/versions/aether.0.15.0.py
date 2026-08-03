#!/usr/bin/env python3
"""
AETHER v0.15.0 — COGNITIVE ARCHITECTURE with MENTE & TINYGRAD

Filosofi:
- Resource management menggunakan energy budget Mente.
- Tiered memory (working, episodic, semantic) menggantikan VectorMemory & LongTermScars.
- Curiosity loop untuk eksplorasi shape.
- Decoder neural network dengan TinyGrad (dapat diperdalam kapan saja).
- Generator tetap sebagai ASCII engine.

Instalasi diperlukan:
  pip install tinygrad
  pip install mente   # jika tersedia, atau kita implementasi ringan sendiri

Catatan: Mente asli mungkin belum stabil. Saya akan membuat lightweight adapter
dengan konsep Mente (tiered memory, bus, budget). Jika Mente official tidak
tersedia, kode ini tetap berjalan dengan implementasi internal.
"""

import math, random, time, json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import deque, Counter
import numpy as np

try:
    from tinygrad import Tensor
    from tinygrad.nn import Linear
    from tinygrad.optim import SGD
    TINYGRAD_AVAILABLE = True
except ImportError:
    TINYGRAD_AVAILABLE = False
    print("[Warning] TinyGrad not installed. Install with: pip install tinygrad")
    # Fallback ke numpy (tidak ideal, tapi agar kode tetap jalan)
    # Kita akan tetap pakai numpy jika tinygrad tidak ada

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not installed. Install with: pip install Pillow")


# ============================================================================
# LIGHTWEIGHT MENTE ADAPTER (implementasi prinsip Mente jika pustaka tidak tersedia)
# ============================================================================

class MenteMemory:
    """Tiered memory: working (short term), episodic (long term), semantic (abstractions)."""
    def __init__(self, working_capacity=10, episodic_capacity=100):
        self.working = deque(maxlen=working_capacity)   # recent experiences
        self.episodic = deque(maxlen=episodic_capacity) # important events
        self.semantic = {}  # key -> abstracted knowledge
    
    def add_experience(self, experience: dict):
        """Experience: {state, action, reward, outcome, circularity, pattern, score}"""
        self.working.append(experience)
        # Jika experience penting (misal circularity > 0.7), pindahkan ke episodic
        if experience.get('circularity', 0) > 0.7:
            self.episodic.append(experience)
    
    def recall_similar(self, query: dict, k: int = 3) -> list:
        """Recall from working + episodic based on similarity (simple heuristic)."""
        candidates = list(self.working) + list(self.episodic)
        if not candidates: return []
        # Simple similarity: match pattern, shape_param range, circularity
        query_pat = query.get('pattern')
        query_circ = query.get('circularity', 0.5)
        scored = []
        for exp in candidates:
            score = 0
            if exp.get('pattern') == query_pat: score += 0.5
            score += 1.0 - abs(exp.get('circularity', 0.5) - query_circ)
            scored.append((score, exp))
        scored.sort(reverse=True)
        return [exp for _, exp in scored[:k]]
    
    def update_semantic(self, key, value):
        self.semantic[key] = value


class MenteBudget:
    """Energy and attention budget to prevent starvation."""
    def __init__(self, max_energy=100, max_attention=100):
        self.energy = max_energy
        self.attention = max_attention
        self.max_energy = max_energy
        self.max_attention = max_attention
        self.fatigue = 0
        self.failure_burden = 0
    
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
        if score < 0.4:
            self.failure_burden = min(100, self.failure_burden + 15)
        elif score > 0.7:
            self.failure_burden = max(0, self.failure_burden - 10)
        else:
            self.failure_burden = max(0, self.failure_burden - 2)


class MenteCuriosity:
    """Curiosity-driven exploration: bonus for novel or uncertain states."""
    def __init__(self, novelty_weight=0.3, uncertainty_weight=0.2):
        self.novelty_weight = novelty_weight
        self.uncertainty_weight = uncertainty_weight
        self.visited_states = Counter()  # hash of state vector
    
    def get_bonus(self, state_vec, prediction_error):
        # state_vec: embedding of current generator params or stimulus similarity
        # For simplicity, hash state using rounded values
        h = tuple(np.round(state_vec, 2).tolist())
        self.visited_states[h] += 1
        novelty = 1.0 / (1.0 + self.visited_states[h])
        return self.novelty_weight * novelty + self.uncertainty_weight * prediction_error


class MenteEventBus:
    """Simple event bus for communication between components."""
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
# TINYGRAD NEURAL DECODER
# ============================================================================

class TinyGradDecoder:
    def __init__(self, input_dim=8, hidden1=32, hidden2=64, hidden3=32, output_dim=6):
        if not TINYGRAD_AVAILABLE:
            raise ImportError("TinyGrad not available. Install with: pip install tinygrad")
        self.input_dim = input_dim
        self.model = [
            Linear(input_dim, hidden1), Tensor.relu,
            Linear(hidden1, hidden2), Tensor.relu,
            Linear(hidden2, hidden3), Tensor.relu,
            Linear(hidden3, output_dim)
        ]
        self.optim = SGD([p for layer in self.model if hasattr(layer, 'parameters') for p in layer.parameters()], lr=0.01)
        self.training_buffer = []
        self.is_trained = False
        self.loss_history = []
        self.best_loss = float('inf')
        self.best_weights = None
        self.current_threshold = 0.15  # similarity threshold for collecting samples
    
    def forward(self, x_tensor):
        out = x_tensor
        for layer in self.model:
            if callable(layer) and not hasattr(layer, 'parameters'):
                out = layer(out)
            else:
                out = layer(out)
        return out
    
    def predict_params(self, stimulus_vec: np.ndarray) -> Dict:
        x = Tensor(stimulus_vec.reshape(1, -1))
        out = self.forward(x).numpy().flatten()
        # map output to parameters (pattern index, symmetry, density, complexity, noise, shape_param)
        patterns = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']
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
    
    def collect_sample(self, stimulus_vec: np.ndarray, generator_params: Dict):
        if generator_params.get('pattern') != 'shape':
            return  # only learn shape
        target = self._params_to_target(generator_params)
        self.training_buffer.append((stimulus_vec.copy(), target))
        if len(self.training_buffer) > 2000:
            self.training_buffer.pop(0)
        progress = min(1.0, len(self.training_buffer) / 200)
        self.current_threshold = 0.15 + (0.7 - 0.15) * progress
    
    def _params_to_target(self, params):
        patterns = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']
        pat_idx = patterns.index(params['pattern']) / (len(patterns)-1)
        return np.array([pat_idx, params['symmetry'], params['density'],
                         params['complexity'], params['noise'], params['shape_param']])
    
    def train(self, epochs=10, batch_size=32):
        if len(self.training_buffer) < batch_size:
            return
        import random
        for ep in range(epochs):
            random.shuffle(self.training_buffer)
            total_loss = 0.0
            num_batches = 0
            for i in range(0, len(self.training_buffer), batch_size):
                batch = self.training_buffer[i:i+batch_size]
                X = np.array([b[0] for b in batch])
                Y = np.array([b[1] for b in batch])
                Xt = Tensor(X)
                Yt = Tensor(Y)
                out = self.forward(Xt)
                loss = ((out - Yt) ** 2).mean()
                self.optim.zero_grad()
                loss.backward()
                self.optim.step()
                total_loss += loss.numpy().item()
                num_batches += 1
            avg_loss = total_loss / num_batches
            self.loss_history.append(avg_loss)
            if avg_loss < self.best_loss:
                self.best_loss = avg_loss
                # save weights (simplified: store model parameters)
                self.best_weights = [p.detach().numpy().copy() for layer in self.model if hasattr(layer, 'parameters') for p in layer.parameters()]
        self.is_trained = True
        print(f"[Decoder] Trained, loss: {self.loss_history[-1]:.4f}, buffer: {len(self.training_buffer)}")
    
    def save_weights(self, path):
        # Implement saving (simplified)
        if self.best_weights:
            np.savez(path, *self.best_weights)
    
    def load_weights(self, path):
        data = np.load(path)
        # restore weights (simplified: assume same architecture)
        idx = 0
        for layer in self.model:
            if hasattr(layer, 'parameters'):
                for p in layer.parameters():
                    p.assign(Tensor(data[f'arr_{idx}']))
                    idx += 1
        self.is_trained = True
        self.current_threshold = 0.15
        print(f"[Decoder] Weights loaded from {path}")


# ============================================================================
# ASCII SHAPE GENERATOR (sama seperti sebelumnya, dengan perbaikan circularity)
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
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']
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
        # other patterns simplified for brevity (wave, etc.)
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        # simple wave simulation
        for y in range(h):
            for x in range(w):
                v = math.sin(x*0.3)*math.cos(y*0.3) + random.uniform(-0.1,0.1)
                if (v+1)/2 > 0.7:
                    grid[y][x] = random.choice('░▒▓█')
        return '\n'.join(''.join(row) for row in grid), self.params['pattern']
    
    def set_params(self, p):
        self.params.update(p)
    
    def mutate(self, intensity=0.2):
        for k in ['symmetry','density','complexity','noise','shape_param']:
            if random.random() < intensity:
                self.params[k] += random.uniform(-0.15,0.15)
                self.params[k] = max(0.0, min(1.0, self.params[k])) if k=='shape_param' else max(0.05, min(0.95, self.params[k]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)


# ============================================================================
# ART EMBEDDER (circularity, symmetry, density, diversity)
# ============================================================================

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
        # symmetry
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
        # diversity
        allc = [c for line in padded for c in line if c!=' ']
        var = np.std([ord(c) for c in allc])/128.0 if allc else 0.0
        # circularity
        cx, cy = w/2, h/2
        max_r = min(w,h)/2
        inner = sum(1 for y in range(h) for x in range(w) if padded[y][x]!=' ' and ((x-cx)**2+(y-cy)**2)**0.5 < max_r*0.6)
        outer = sum(1 for y in range(h) for x in range(w) if padded[y][x]!=' ' and ((x-cx)**2+(y-cy)**2)**0.5 > max_r*0.8)
        circ = ((inner - outer) / non + 1)/2 if non>0 else 0.5
        vec = np.array([den, sym, var, circ], dtype=np.float32)
        vec = np.pad(vec, (0, 8-len(vec)))
        return vec/(np.linalg.norm(vec)+1e-8)


# ============================================================================
# AETHER COGNITIVE CORE with MENTE ADAPTER
# ============================================================================

class AetherCognitiveCore:
    def __init__(self, stimulus_source=None):
        self.bus = MenteEventBus()
        self.memory = MenteMemory()
        self.budget = MenteBudget()
        self.curiosity = MenteCuriosity()
        self.generator = Generator()
        self.decoder = None  # akan diinisialisasi setelah stimulus aktif
        self.stimulus = None
        if stimulus_source:
            self._load_stimulus(stimulus_source)
        self.cycle = 0
        self.pattern_counts = Counter()
        self.training_buffer_size = 0  # for decoder
        self._setup_subscriptions()
    
    def _load_stimulus(self, source):
        if source.lower().endswith(('.png','.jpg','.jpeg','.bmp')):
            if not PIL_AVAILABLE:
                print("[Error] Pillow needed for image stimulus")
                return
            img = Image.open(source).convert('L').resize((100,100))
            arr = np.array(img, dtype=np.float32)/255.0
            # compute 8-d vector (sama seperti sebelumnya)
            h,w = arr.shape
            den = float(np.mean(arr))
            left = arr[:,:w//2]; right = np.fliplr(arr[:,w//2:])
            min_w = min(left.shape[1], right.shape[1])
            h_sym = 1.0 - float(np.mean(np.abs(left[:,:min_w]-right[:,:min_w]))) if min_w>0 else 0.5
            top = arr[:h//2,:]; bottom = np.flipud(arr[h//2:,:])
            min_h = min(top.shape[0], bottom.shape[0])
            v_sym = 1.0 - float(np.mean(np.abs(top[:min_h,:]-bottom[:min_h,:]))) if min_h>0 else 0.5
            gx = np.abs(np.diff(arr, axis=1)); gy = np.abs(np.diff(arr, axis=0))
            edge = (np.mean(gx)+np.mean(gy))/2.0
            comp = float(np.std(arr))
            hist,_ = np.histogram(arr, bins=32, range=(0,1))
            hist = hist/(hist.sum()+1e-8)
            ent = -np.sum(hist*np.log2(hist+1e-8))/np.log2(32)
            lw = np.sum(arr[:,:w//2]); rw = np.sum(arr[:,w//2:])
            h_bal = min(lw,rw)/max(lw,rw) if max(lw,rw)>0 else 1.0
            tw = np.sum(arr[:h//2,:]); bw = np.sum(arr[h//2:,:])
            v_bal = min(tw,bw)/max(tw,bw) if max(tw,bw)>0 else 1.0
            self.stimulus_vector = np.array([den, h_sym, v_sym, edge, comp, ent, h_bal, v_bal])
            self.stimulus_vector /= (np.linalg.norm(self.stimulus_vector)+1e-8)
            print("[Stimulus] Loaded image vector")
        else:
            # treat as vector file
            with open(source) as f:
                vec = np.array([float(x) for x in f.read().split()])
            self.stimulus_vector = vec / (np.linalg.norm(vec)+1e-8)
            print("[Stimulus] Loaded vector from file")
        
        # Inisialisasi decoder dengan TinyGrad
        try:
            self.decoder = TinyGradDecoder()
            # Coba load weights jika ada
            weights_path = Path("aether_works_v0122/decoder_weights.npz")
            if weights_path.exists():
                self.decoder.load_weights(weights_path)
            else:
                print("[Decoder] No pre-trained weights. Random init.")
        except ImportError:
            print("[Decoder] TinyGrad not available. Decoder disabled.")
            self.decoder = None
    
    def _setup_subscriptions(self):
        # Subscribe to events if needed
        pass
    
    def step(self):
        self.cycle += 1
        
        # Jika tidak ada stimulus, tidak bisa belajar
        if self.stimulus_vector is None or self.decoder is None:
            print("[Error] No stimulus or decoder. Exiting.")
            return
        
        # ===== BOOTSTRAPPING PHASE (first 50 cycles) =====
        if self.cycle <= 50:
            # Force generate shape with good parameters
            self.generator.params['pattern'] = 'shape'
            self.generator.params['shape_param'] = random.uniform(0, 0.15)
            self.generator.params['density'] = 0.55
            self.generator.params['symmetry'] = 0.9
            self.generator.params['noise'] = 0.02
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            avec = ArtEmbedder.embed(art)
            # compute circularity
            circ = self._compute_circularity(art)
            score = self._compute_score(art)
            # reward high circularity
            if circ > 0.7:
                self.budget.recover(energy_gain=15, attention_gain=5, fatigue_reduction=10)
                print(f"[Bootstrap Reward] circ={circ:.2f} +15 energy")
            # collect sample
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_vector, self.generator.params)
                print(f"[Bootstrap] Collected sample {len(self.decoder.training_buffer)} circ={circ:.2f}")
            # Apply cost (reduced for bootstrapping)
            self.budget.spend(energy_cost=5, attention_cost=4, fatigue_delta=2)
            self.budget.regen(resting=False)  # no rest during bootstrap
            self._log(art, score, circ, pat)
            return art, score, circ, pat
        
        # ===== NORMAL OPERATION =====
        # Determine action using curiosity and memory
        # Simple epsilon-greedy with curiosity bonus
        actions = ['generate', 'explore', 'refine', 'combine', 'rest', 'recall', 'forget']
        # Filter feasible berdasarkan budget
        if self.budget.energy < 10 or self.budget.attention < 10:
            feasible = ['rest']
        else:
            feasible = actions.copy()
        
        # Get current state (stimulus similarity, recent memory, etc.)
        # For simplicity, just use curiosity bonus for generate
        state_vec = self.stimulus_vector  # placeholder
        pred_error = 0.2  # dummy
        curiosity_bonus = self.curiosity.get_bonus(state_vec, pred_error)
        
        # Utility for each action
        utils = {}
        for a in feasible:
            base = 0.5
            if a == 'generate':
                # Jika decoder trained, gunakan prediksi; else forced shape
                if self.decoder.is_trained:
                    # bonus from decoder
                    base += 0.4
                else:
                    # forced shape bonus
                    base += 0.6
                base += curiosity_bonus
            elif a == 'explore':
                base += 0.2
            elif a == 'rest':
                base = (1 - self.budget.energy/100) + (1 - self.budget.attention/100) + (self.budget.fatigue/100)
            utils[a] = max(0, base)
        # Add noise
        for a in utils:
            utils[a] += random.gauss(0, 0.1)
        chosen = max(utils, key=utils.get)
        
        # Execute action
        if chosen == 'generate':
            # Jika decoder trained dan tidak dipaksa shape, gunakan prediksi
            if self.decoder.is_trained and random.random() < 0.7:
                pred = self.decoder.predict_params(self.stimulus_vector)
                self.generator.set_params(pred)
            else:
                # forced shape untuk eksplorasi
                self.generator.params['pattern'] = 'shape'
                self.generator.params['shape_param'] = random.uniform(0, 0.4)
                self.generator.params['density'] = random.uniform(0.4, 0.7)
                self.generator.params['symmetry'] = random.uniform(0.7, 0.95)
                self.generator.params['noise'] = random.uniform(0, 0.05)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            avec = ArtEmbedder.embed(art)
            circ = self._compute_circularity(art)
            score = self._compute_score(art)
            # Reward high circularity
            if pat == 'shape' and circ > 0.7:
                score = min(1.0, score + 0.2)
                self.budget.recover(5, 2, 5)
            # Update memory
            self.memory.add_experience({
                'state': self.stimulus_vector.tolist(),
                'action': chosen,
                'reward': score,
                'pattern': pat,
                'circularity': circ,
                'params': self.generator.params.copy()
            })
            # Collect sample for decoder
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_vector, self.generator.params)
            # Train decoder periodically
            if self.cycle % 25 == 0 and len(self.decoder.training_buffer) >= 32:
                self.decoder.train()
            # Apply cost
            self.budget.spend(energy_cost=8, attention_cost=6, fatigue_delta=4)
        elif chosen == 'explore':
            self.generator.mutate(0.5)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            avec = ArtEmbedder.embed(art)
            circ = self._compute_circularity(art)
            score = self._compute_score(art)
            self.budget.spend(energy_cost=12, attention_cost=10, fatigue_delta=6)
        elif chosen == 'rest':
            self.budget.recover(15, 20, 15)
            art = None; pat = None; score = 0.5; circ = 0
        else:
            # recall, forget, refine, combine - simplified
            art = None; pat = None; score = 0.5; circ = 0
            self.budget.spend(2,2,1)
        
        # Update failure burden based on score
        self.budget.update_failure_burden(score)
        
        # Log
        self._log(art, score, circ, pat if art else 'none')
        return art, score, circ, pat
    
    def _compute_circularity(self, art):
        if not art: return 0
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines: return 0
        h,w = len(lines), max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        non = sum(c!=' ' for line in padded for c in line)
        if non == 0: return 0
        cx, cy = w/2, h/2
        max_r = min(w,h)/2
        inner = sum(1 for y in range(h) for x in range(w) if padded[y][x]!=' ' and ((x-cx)**2+(y-cy)**2)**0.5 < max_r*0.6)
        outer = sum(1 for y in range(h) for x in range(w) if padded[y][x]!=' ' and ((x-cx)**2+(y-cy)**2)**0.5 > max_r*0.8)
        circ = ((inner - outer) / non + 1) / 2
        return circ
    
    def _compute_score(self, art):
        if not art: return 0.5
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines: return 0.5
        h,w = len(lines), max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        non = sum(c!=' ' for line in padded for c in line)
        den = non/(h*w)
        # symmetry
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
        # diversity
        allc = [c for line in padded for c in line if c!=' ']
        div = len(set(allc))/min(30,max(1,len(allc))) if allc else 0
        # entropy
        if allc:
            freq = Counter(allc); probs=[f/len(allc) for f in freq.values()]
            ent = -sum(p*math.log2(p) for p in probs)/max(1,math.log2(len(freq)))
        else: ent=0
        circ = self._compute_circularity(art)
        d = 1 - abs(den-0.4)*2.5
        return max(0, min(1, d*0.2 + sym*0.3 + div*0.2 + ent*0.1 + circ*0.2))
    
    def _log(self, art, score, circ, pat):
        print(f"\n[Cycle {self.cycle}] action: {pat if art else 'rest'} | score={score:.3f} circ={circ:.3f}")
        print(f"E={self.budget.energy} A={self.budget.attention} F={self.budget.fatigue} B={self.budget.failure_burden}")
        if art and len(art)>200:
            print(art[:200]+"...")
        elif art:
            print(art)
    
    def run(self, cycles=500):
        for _ in range(cycles):
            self.step()
            time.sleep(0.05)
        print("\n=== RUN SUMMARY ===")
        print(f"Total cycles: {cycles}")
        print(f"Pattern usage: {dict(self.pattern_counts)}")
        if self.decoder and self.decoder.loss_history:
            print(f"Decoder final loss: {self.decoder.loss_history[-1]:.4f}, best: {self.decoder.best_loss:.4f}")
        # Save weights
        if self.decoder:
            self.decoder.save_weights("aether_works_v0122/decoder_weights.npz")


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
        print("Usage: python aether_v0.15.0.py --image circle.png --auto 500")
        sys.exit(1)
    core = AetherCognitiveCore(stimulus_source=stimulus)
    core.run(cycles)