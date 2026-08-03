#!/usr/bin/env python3
"""
AETHER v0.12.1 — ADAPTIVE THRESHOLD, FORCED SHAPE EXPLORATION, BEST WEIGHTS
"""

import math, random, time, json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import deque, Counter
import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not installed. Install with: pip install Pillow")

# ============================================================================
# HARD CONFIGURATION
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
    WORLD_MODEL_HIDDEN_DIM = 8
    VECTOR_DIM = 8
    
    NN_INPUT_DIM = 8
    NN_HIDDEN_1 = 32
    NN_HIDDEN_2 = 64
    NN_HIDDEN_3 = 32
    NN_OUTPUT_DIM = 6
    
    NN_LEARNING_RATE = 0.01
    NN_TRAINING_EPOCHS = 10
    NN_BATCH_SIZE = 32
    NN_TRAIN_INTERVAL = 25
    NN_SAMPLE_THRESHOLD_INITIAL = 0.15
    NN_SAMPLE_THRESHOLD_MAX = 0.7
    NN_CONFIDENCE_LOSS_THRESH = 0.05
    NN_FORCED_SHAPE_PROB = 0.2
    
    FORESIGHT_STEPS = 2
    PLANNING_DISCOUNT = 0.9
    
    EXPLORATION_NOISE_STD = 0.12
    CURIOSITY_BONUS = 0.2
    
    REPETITION_PENALTY_PER_USE = 0.05
    STATE_TRANSITION_NOISE = 0.08
    
    ACTION_SHIFT = {
        'explore': 0.30, 'refine': 0.10, 'generate': 0.03,
        'combine': 0.15, 'rest': -0.08, 'recall': 0.0, 'forget': 0.0
    }
    
    REST_COOLDOWN = 4
    REST_FATIGUE_REDUCTION = 8
    REST_ENERGY_GAIN_BASE = 7
    REST_ATTENTION_GAIN_BASE = 10
    BURDEN_RECOVERY_REST = -12
    
    STIMULUS_WEIGHT = 0.25
    STIMULUS_SIMILARITY_THRESHOLD = 0.1
    PATTERNS = ['wave', 'fractal', 'cellular', 'lsystem', 'shape']


# ============================================================================
# NEURAL DECODER (with adaptive threshold & best weights)
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
        self.hidden1 = hidden1
        self.hidden2 = hidden2
        self.hidden3 = hidden3
        self.output_dim = output_dim
        self.training_buffer = []
        self.is_trained = False
        self.loss_history = []
        self.best_loss = float('inf')
        self.best_weights = None
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL
    
    def _params_to_target(self, params: Dict) -> np.ndarray:
        pat = HardConfig.PATTERNS.index(params['pattern']) / max(1, len(HardConfig.PATTERNS)-1)
        return np.array([pat, params['symmetry'], params['density'],
                         params['complexity'], params['noise'], params['shape_param']])
    
    def forward(self, x: np.ndarray, cache: bool = False):
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
    
    def predict_params(self, embedding: np.ndarray) -> Dict:
        out = self.forward(embedding)
        if out.ndim == 2:
            out = out[0]
        pattern_idx = int(np.clip(out[0] * len(HardConfig.PATTERNS), 0, len(HardConfig.PATTERNS) - 1))
        pattern = HardConfig.PATTERNS[pattern_idx]
        symmetry = float(np.clip(out[1], 0.0, 1.0))
        density = float(np.clip(out[2], 0.05, 0.95))
        complexity = float(np.clip(out[3], 0.1, 0.9))
        noise = float(np.clip(out[4], 0.0, 0.6))
        shape_param = float(np.clip(out[5], 0.0, 1.0))
        return {
            'pattern': pattern,
            'symmetry': symmetry,
            'density': density,
            'complexity': complexity,
            'noise': noise,
            'shape_param': shape_param
        }
    
    def collect_sample(self, stimulus_vec: np.ndarray, generator_params: Dict):
        target = self._params_to_target(generator_params)
        self.training_buffer.append((stimulus_vec.copy(), target))
        if len(self.training_buffer) > 2000:
            self.training_buffer.pop(0)
        progress = min(1.0, len(self.training_buffer) / 200)
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL + \
            (HardConfig.NN_SAMPLE_THRESHOLD_MAX - HardConfig.NN_SAMPLE_THRESHOLD_INITIAL) * progress
    
    def backward(self, cache, dout):
        x, z1, a1, z2, a2, z3, a3 = cache
        batch_size = x.shape[0]
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
        return dW1, db1, dW2, db2, dW3, db3, dW4, db4
    
    def train_on_buffer(self, epochs=None, batch_size=None, lr=None):
        if epochs is None: epochs = HardConfig.NN_TRAINING_EPOCHS
        if batch_size is None: batch_size = HardConfig.NN_BATCH_SIZE
        if lr is None: lr = HardConfig.NN_LEARNING_RATE
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
                grads = self.backward(cache, dout)
                self.W1 -= lr * grads[0]; self.b1 -= lr * grads[1]
                self.W2 -= lr * grads[2]; self.b2 -= lr * grads[3]
                self.W3 -= lr * grads[4]; self.b3 -= lr * grads[5]
                self.W4 -= lr * grads[6]; self.b4 -= lr * grads[7]
            avg_loss = total_loss / max(1, num_batches)
            self.loss_history.append(avg_loss)
            if avg_loss < self.best_loss:
                self.best_loss = avg_loss
                self.best_weights = {
                    'W1': self.W1.copy(), 'b1': self.b1.copy(),
                    'W2': self.W2.copy(), 'b2': self.b2.copy(),
                    'W3': self.W3.copy(), 'b3': self.b3.copy(),
                    'W4': self.W4.copy(), 'b4': self.b4.copy()
                }
        self.is_trained = len(self.loss_history) > 0
        if len(self.loss_history) >= 3 and self.loss_history[-1] < HardConfig.NN_CONFIDENCE_LOSS_THRESH:
            self.is_trained = True
        print(f"[Decoder] Trained, final loss: {self.loss_history[-1]:.4f}, best loss: {self.best_loss:.4f}, buffer: {len(self.training_buffer)}, threshold: {self.current_threshold:.2f}")
    
    def save_weights(self, filepath: str):
        if self.best_weights is not None:
            np.savez(filepath, **self.best_weights)
            print(f"[Decoder] Best weights saved to {filepath} (loss: {self.best_loss:.4f})")
        else:
            np.savez(filepath, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2,
                     W3=self.W3, b3=self.b3, W4=self.W4, b4=self.b4)
            print(f"[Decoder] Weights saved to {filepath}")
    
    def load_weights(self, filepath: str):
        data = np.load(filepath)
        self.W1 = data['W1']; self.b1 = data['b1']
        self.W2 = data['W2']; self.b2 = data['b2']
        self.W3 = data['W3']; self.b3 = data['b3']
        self.W4 = data['W4']; self.b4 = data['b4']
        self.is_trained = True
        self.best_weights = {k: data[k] for k in data.keys()}
        print(f"[Decoder] Weights loaded from {filepath}")


# ============================================================================
# SHAPE GENERATOR
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


# ============================================================================
# GENERATOR (with forced shape exploration)
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
        self.usage_counter = Counter()
    
    def generate(self, blocked):
        if self.params['pattern'] in blocked:
            raise ValueError(f"Pattern '{self.params['pattern']}' blocked")
        self.usage_counter[self.params['pattern']] += 1
        if self.params['pattern'] == 'shape':
            return ShapeAwareGenerator.generate_shape(
                self.params['shape_param'], self.params['symmetry'],
                self.params['density'], self.params['noise']
            ), 'shape'
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
    
    def mutate(self, intensity=0.2):
        for k in ['symmetry','density','complexity','noise','shape_param']:
            if random.random() < intensity:
                self.params[k] += random.uniform(-0.15,0.15)
                self.params[k] = max(0.0, min(1.0, self.params[k])) if k=='shape_param' else max(0.05, min(0.95, self.params[k]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)
    
    def crossover_with_memory(self, other):
        for k in self.params:
            if k=='pattern':
                if random.random()<0.5: self.params[k]=other.get(k, self.params[k])
            elif isinstance(other.get(k), (int,float)):
                self.params[k] = (self.params[k]+other[k])/2.0
    
    def get_params(self): return self.params.copy()
    def set_params(self, p): self.params.update(p)


# ============================================================================
# EXTERNAL STIMULUS (unchanged)
# ============================================================================

class ExternalStimulus:
    def __init__(self, source=None):
        self.vector = None; self.metadata = {}; self.is_active = False
        if source:
            if source.lower().endswith(('.png','.jpg','.jpeg','.bmp')): self.load_image(source)
            elif source.endswith('.json'): self.load(source)
            else: self.load_vector_from_file(source)
    
    def load_image(self, path, size=(100,100)):
        if not PIL_AVAILABLE: return False
        img = Image.open(path).convert('L').resize(size, Image.Resampling.LANCZOS)
        arr = np.array(img, dtype=np.float32)/255.0
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
        vec = np.array([den, h_sym, v_sym, edge, comp, ent, h_bal, v_bal])
        self.vector = vec / (np.linalg.norm(vec)+1e-8)
        self.metadata = {'source':'image','path':path}
        self.is_active = True
        return True
    
    def load(self, path):
        with open(path) as f: data = json.load(f)
        if 'vector' in data:
            vec = np.array(data['vector'], dtype=np.float32)
            self.vector = vec / (np.linalg.norm(vec)+1e-8)
            self.metadata = {k:v for k,v in data.items() if k!='vector'}
            self.is_active = True
            return True
        return False
    
    def load_vector_from_file(self, path):
        with open(path) as f: parts = f.read().strip().split()
        vec = np.array([float(p) for p in parts], dtype=np.float32)
        self.vector = vec / (np.linalg.norm(vec)+1e-8)
        self.is_active = True
        return True
    
    def similarity(self, other):
        if self.vector is None or other is None: return 0.0
        return float(np.dot(self.vector, other.flatten())/(np.linalg.norm(self.vector)*np.linalg.norm(other)+1e-8))
    
    def clear(self): self.vector=None; self.is_active=False


# ============================================================================
# RESOURCE MANAGER, LONG-TERM SCARS, MEMORY, EMBEDDERS, WORLD MODEL, DECISION, SELF-MODEL
# ============================================================================

class ResourceManager:
    def __init__(self):
        self.energy = HardConfig.MAX_ENERGY; self.attention = HardConfig.MAX_ATTENTION
        self.memory_used = 0; self.fatigue = 0; self.failure_burden = 0
        self.coma_cycles_left = 0; self.cycle = 0; self.last_rest_cycle = -999
        self.consecutive_failures = 0
    def is_coma(self): return self.coma_cycles_left>0
    def enter_coma(self):
        if self.failure_burden>=HardConfig.COMA_BURDEN and self.energy<=HardConfig.COMA_ENERGY:
            self.coma_cycles_left=HardConfig.COMA_DURATION; self.energy=0; self.attention=0; return True
        return False
    def update_coma(self):
        if self.coma_cycles_left>0:
            self.coma_cycles_left-=1
            if self.coma_cycles_left==0: self.energy=30; self.attention=40; self.fatigue=20; self.failure_burden=max(0,self.failure_burden-40)
            return True
        return False
    def apply_cost(self, action):
        if action.startswith('failed_'): en,att,mem,fat = HardConfig.ACTION_COSTS.get('generate',(8,6,0,3))
        else: en,att,mem,fat = HardConfig.ACTION_COSTS.get(action,(0,0,0,0))
        mult = 1.0 + (self.failure_burden/HardConfig.FAILURE_BURDEN_MAX)*(HardConfig.COST_MULTIPLIER_MAX-1)
        self.energy = max(0, min(HardConfig.MAX_ENERGY, self.energy - int(en*mult)))
        self.attention = max(0, min(HardConfig.MAX_ATTENTION, self.attention - int(att*mult)))
        self.memory_used += mem
        self.fatigue = max(0, min(HardConfig.MAX_FATIGUE, self.fatigue + fat + int(self.failure_burden/25)))
    def regen(self, resting):
        if resting and self.can_rest():
            fp = max(0, self.fatigue/20)
            self.energy = min(HardConfig.MAX_ENERGY, self.energy + max(3, HardConfig.REST_ENERGY_GAIN_BASE - int(fp)))
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention + max(4, HardConfig.REST_ATTENTION_GAIN_BASE - int(fp*1.2)))
            self.fatigue = max(0, self.fatigue - HardConfig.REST_FATIGUE_REDUCTION)
            self.last_rest_cycle = self.cycle
            self.failure_burden = max(0, self.failure_burden + HardConfig.BURDEN_RECOVERY_REST)
        else:
            self.energy = min(HardConfig.MAX_ENERGY, self.energy+1)
            self.attention = min(HardConfig.MAX_ATTENTION, self.attention+1)
            self.fatigue = max(0, self.fatigue-1)
    def update_failure_burden(self, score):
        if score<0.4:
            self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden+12)
            if score<0.2: self.failure_burden = min(HardConfig.FAILURE_BURDEN_MAX, self.failure_burden+8)
            self.consecutive_failures+=1
        elif score>0.7:
            self.failure_burden = max(0, self.failure_burden-10)
            self.consecutive_failures=0
        else: self.consecutive_failures=0
    def can_rest(self): return (self.cycle - self.last_rest_cycle) >= HardConfig.REST_COOLDOWN
    def is_emergency(self): return self.failure_burden>=HardConfig.EMERGENCY_BURDEN_THRESHOLD and self.energy<=HardConfig.EMERGENCY_ENERGY_THRESHOLD
    def get_effective_action_cost(self, action):
        en,att,_,_ = HardConfig.ACTION_COSTS.get(action,(0,0,0,0))
        mult = 1.0 + (self.failure_burden/HardConfig.FAILURE_BURDEN_MAX)*(HardConfig.COST_MULTIPLIER_MAX-1)
        return int(en*mult), int(att*mult), 0

class LongTermScars:
    def __init__(self):
        self.pattern_trauma={}; self.pattern_blocked_until={}; self.action_trauma={}
        self.identity_bias={'risk_tolerance':0.5,'novelty_seeking':0.5,'symmetry_preference':0.5}; self.cycle=0
    def update(self, action, pattern, score, cycle):
        self.cycle=cycle
        if score<0.3:
            self.pattern_trauma[pattern]=min(1.0, self.pattern_trauma.get(pattern,0)+0.12)
            self.action_trauma[action]=min(20, self.action_trauma.get(action,0)+3)
        else:
            for p in list(self.pattern_trauma): self.pattern_trauma[p]=max(0,self.pattern_trauma[p]-0.01)
            for a in list(self.action_trauma): self.action_trauma[a]=max(0,self.action_trauma[a]-1)
        if self.pattern_trauma.get(pattern,0)>=HardConfig.TRAUMA_BLOCK_THRESHOLD:
            self.pattern_blocked_until[pattern]=cycle+HardConfig.TRAUMA_BLOCK_DURATION
        for p in list(self.pattern_blocked_until):
            if self.pattern_blocked_until[p]<=cycle: del self.pattern_blocked_until[p]
    def is_pattern_blocked(self, p): return p in self.pattern_blocked_until
    def get_action_trauma_penalty(self, a): return self.action_trauma.get(a,0)/20.0
    def apply_identity_drift(self, scores):
        if len(scores)<30: return
        avg = sum(scores[-30:])/30
        self.identity_bias['risk_tolerance'] += (min(0.9,avg*1.3)-self.identity_bias['risk_tolerance'])*0.002
        self.identity_bias['novelty_seeking'] += (min(0.85,avg*1.2)-self.identity_bias['novelty_seeking'])*0.002
        for k in self.identity_bias: self.identity_bias[k]=max(0.1,min(0.9,self.identity_bias[k]))
    def get_novelty_bias(self, action): return self.identity_bias['novelty_seeking']*0.2 if action in ['explore','combine'] else 0.0

class VectorMemory:
    def __init__(self, dim=HardConfig.VECTOR_DIM):
        self.dim=dim; self.vectors=[]; self.metadata=[]
    def store(self, vec, meta):
        if len(self.vectors)>=HardConfig.MEMORY_SLOTS: self.vectors.pop(0); self.metadata.pop(0)
        self.vectors.append(vec); self.metadata.append(meta)
    def recall_similar(self, query, k=3):
        if not self.vectors: return []
        sims = [(np.dot(query,v)/(np.linalg.norm(query)*np.linalg.norm(v)+1e-8), i) for i,v in enumerate(self.vectors)]
        sims.sort(reverse=True)
        return [(s, self.metadata[i].copy()) for s,i in sims[:k]]
    def novelty(self, vec):
        if not self.vectors: return 1.0
        return 1.0 - max(np.dot(vec,v)/(np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors)
    def predict_score_similarity(self, query):
        if not self.vectors: return 0.5
        sims, scores = [], []
        for v,m in zip(self.vectors, self.metadata):
            s = np.dot(query,v)/(np.linalg.norm(query)*np.linalg.norm(v)+1e-8)
            if s>0.05: sims.append(s); scores.append(m.get('score',0.5))
        if not sims: return 0.5
        return sum(ss*sc for ss,sc in zip(sims,scores))/sum(sims)

class ParamEmbedder:
    @staticmethod
    def embed(params):
        features = [params.get('symmetry',0.5), params.get('density',0.35), params.get('complexity',0.5), params.get('noise',0.15)]
        pat = params.get('pattern','wave')
        for p in HardConfig.PATTERNS: features.append(1.0 if p==pat else 0.0)
        features.append(params.get('shape_param',0.5))
        vec = np.array(features[:HardConfig.VECTOR_DIM], dtype=np.float32)
        return vec/(np.linalg.norm(vec)+1e-8)

class ArtEmbedder:
    @staticmethod
    def embed(art):
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines: return np.zeros(HardConfig.VECTOR_DIM, dtype=np.float32)
        h,w = len(lines), max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        total = h*w
        non = sum(c!=' ' for line in padded for c in line)
        den = non/total
        h_sym=0; cnt=0
        for line in padded:
            s = line.rstrip()
            if len(s)>2:
                mid=len(s)//2; left=s[:mid]; right=s[mid:][::-1]
                n=min(len(left),len(right))
                if n>0:
                    m = sum(1 for i in range(n) if left[i]==right[i] and left[i]!=' ')
                    h_sym += m/n; cnt+=1
        sym = h_sym/max(1,cnt)
        allc = [c for line in padded for c in line if c!=' ']
        var = np.std([ord(c) for c in allc])/128.0 if allc else 0.0
        vec = np.array([den, sym, var], dtype=np.float32)
        vec = np.pad(vec, (0, max(0, HardConfig.VECTOR_DIM-len(vec))))
        return vec/(np.linalg.norm(vec)+1e-8)

class WorldModel:
    def __init__(self, dim=HardConfig.VECTOR_DIM, hdim=HardConfig.WORLD_MODEL_HIDDEN_DIM):
        self.W1 = np.random.randn(hdim,dim).astype(np.float32)*0.1; self.b1 = np.zeros(hdim,dtype=np.float32)
        self.W2 = np.random.randn(1,hdim).astype(np.float32)*0.1; self.b2 = 0.0
        self.confidence=0.5; self.buffer=deque(maxlen=150); self.prediction_error=0.0
    def predict(self, vec):
        h = np.tanh(self.W1 @ vec.flatten() + self.b1)
        return float(np.clip((self.W2 @ h + self.b2).item(), 0,1))
    def predict_with_uncertainty(self, vec):
        p = self.predict(vec); return p, 1.0-self.confidence
    def update(self, vec, score):
        self.buffer.append((vec, score))
        if len(self.buffer)<20: return
        for _ in range(20):
            v,a = random.choice(list(self.buffer))
            h = np.tanh(self.W1 @ v + self.b1)
            out = self.W2 @ h + self.b2
            err = a - out
            self.W2 += HardConfig.WORLD_MODEL_UPDATE_RATE * err * h
            self.b2 += HardConfig.WORLD_MODEL_UPDATE_RATE * err
            delta = err * self.W2.flatten() * (1-h**2)
            self.W1 += HardConfig.WORLD_MODEL_UPDATE_RATE * np.outer(delta, v)
            self.b1 += HardConfig.WORLD_MODEL_UPDATE_RATE * delta
        if len(self.buffer)>=20:
            errs = [abs(self.predict(v)-a) for v,a in list(self.buffer)[-20:]]
            self.confidence = max(0.2, min(0.9, 1.0 - sum(errs)/20))
        self.prediction_error = abs(self.predict(vec)-score)

class StateTransition:
    @staticmethod
    def transition(vec, action, score):
        v = vec.flatten().copy()
        shift = HardConfig.ACTION_SHIFT.get(action,0.0)
        factor = 1.0+shift if score>0.7 else (1.0-shift if score<0.3 else 1.0+shift*(score-0.5)*2)
        v = v*factor + np.random.randn(len(v)).astype(np.float32)*HardConfig.STATE_TRANSITION_NOISE
        return v/(np.linalg.norm(v)+1e-8)

class DecisionEngine:
    def __init__(self, wm, lt, mem):
        self.world=wm; self.long=lt; self.memory=mem; self.action_usage=Counter()
        self.committed_action=None; self.commitment_remaining=0
    def _evaluate(self, action, vec, res, blocked, stim):
        pred, unc = self.world.predict_with_uncertainty(vec)
        sim_score = self.memory.predict_score_similarity(vec)
        blend = self.world.confidence*pred + (1-self.world.confidence)*sim_score
        en, att, _ = res.get_effective_action_cost(action)
        cost = max(1, (en+att/10)/15)
        rep = self.action_usage[action]*HardConfig.REPETITION_PENALTY_PER_USE
        trau = self.long.get_action_trauma_penalty(action)
        novel = self.long.get_novelty_bias(action)
        cur = HardConfig.CURIOSITY_BONUS*unc if action in ['explore','combine'] else 0.0
        stim_bonus = 0.0
        if stim and stim.is_active:
            sim = stim.similarity(vec)
            if sim>HardConfig.STIMULUS_SIMILARITY_THRESHOLD: stim_bonus = sim*HardConfig.STIMULUS_WEIGHT
        if action=='rest':
            ed = (HardConfig.MAX_ENERGY-res.energy)/HardConfig.MAX_ENERGY
            ad = (HardConfig.MAX_ATTENTION-res.attention)/HardConfig.MAX_ATTENTION
            fp = res.fatigue/HardConfig.MAX_FATIGUE
            return (ed+ad+fp)/3, {}
        u = (blend/cost) - rep - trau + novel + cur + stim_bonus
        if action in ['explore','combine']: u *= (0.8+0.4*self.long.identity_bias['risk_tolerance'])
        return max(0.0, u), {}
    def _foresight(self, action, vec, res, blocked, stim):
        u1,_ = self._evaluate(action, vec, res, blocked, stim)
        pred,_ = self.world.predict_with_uncertainty(vec)
        next_vec = StateTransition.transition(vec, action, pred)
        en, att, _ = res.get_effective_action_cost(action)
        if res.energy-en <=5: return u1*0.5
        sim = ResourceManager(); sim.energy=res.energy-en; sim.attention=max(0,res.attention-att)
        sim.fatigue=res.fatigue+5; sim.failure_burden=res.failure_burden
        best = max((self._evaluate(a2, next_vec, sim, blocked, stim)[0] for a2 in HardConfig.ACTION_COSTS if a2 not in blocked), default=0.0)
        return u1 + HardConfig.PLANNING_DISCOUNT*best
    def choose_action(self, feasible, res, vec, blocked, emergency, stim):
        if self.commitment_remaining>0:
            if self.committed_action in feasible: return self.committed_action, {'commitment':True}
            res.apply_cost('forget')
            res.energy+=HardConfig.COMMITMENT_VIOLATION_PENALTY['energy']
            res.attention+=HardConfig.COMMITMENT_VIOLATION_PENALTY['attention']
            res.fatigue+=HardConfig.COMMITMENT_VIOLATION_PENALTY['fatigue']
            self.commitment_remaining=0; self.committed_action=None
        if emergency: feasible = [a for a in feasible if a in ['rest','recall']] or ['rest']
        utils = {}
        for a in feasible:
            if res.energy>20 and a in ['generate','explore','refine','combine']:
                utils[a] = self._foresight(a, vec, res, blocked, stim)
            else: utils[a],_ = self._evaluate(a, vec, res, blocked, stim)
        noisy = {a: u+random.gauss(0,HardConfig.EXPLORATION_NOISE_STD) for a,u in utils.items()}
        chosen = max(noisy, key=noisy.get)
        self.action_usage[chosen]+=1
        if self.commitment_remaining==0 and chosen!='rest':
            if self.world.confidence>HardConfig.COMMITMENT_THRESHOLD_CONFIDENCE and utils[chosen]>0.6:
                self.committed_action=chosen; self.commitment_remaining=HardConfig.COMMITMENT_WINDOW
        info = {'utilities':utils,'chosen':chosen,'noise_effect':noisy[chosen]-utils[chosen],
                'runner_up': sorted(noisy, key=noisy.get, reverse=True)[1] if len(noisy)>1 else None}
        return chosen, info
    def update_commitment(self):
        if self.commitment_remaining>0:
            self.commitment_remaining-=1
            if self.commitment_remaining==0: self.committed_action=None

class SelfModel:
    def __init__(self):
        self.local_optima_trap=False; self.consecutive_failures=0; self.consecutive_successes=0
        self.score_history=deque(maxlen=20)
    def update(self, score):
        self.score_history.append(score)
        if score<0.4: self.consecutive_failures+=1; self.consecutive_successes=0
        elif score>0.6: self.consecutive_successes+=1; self.consecutive_failures=0
        else: self.consecutive_failures=0; self.consecutive_successes=0
        if len(self.score_history)>=10:
            self.local_optima_trap = all(0.4<=s<=0.6 for s in list(self.score_history)[-10:])
        else: self.local_optima_trap=False
    def get_override(self, res, wconf):
        if self.local_optima_trap and not res.is_emergency() and res.energy>=30: return True,'explore','local_optima'
        if res.is_emergency(): return True,'rest','emergency'
        if self.consecutive_failures>=5 and wconf<0.5: return True,'recall','low_confidence'
        if random.random()<0.1: return True, random.choice(['generate','explore','refine','combine','recall']),'chaotic'
        return False,'',''


# ============================================================================
# MAIN AETHER v0.12.1
# ============================================================================

class Aether:
    def __init__(self, workspace="aether_works_v0121", quiet=False, stimulus_source=None):
        self.workspace = Path(workspace); self.workspace.mkdir(exist_ok=True)
        self.resources = ResourceManager()
        self.memory = VectorMemory()
        self.generator = Generator()
        self.world_model = WorldModel()
        self.long_term = LongTermScars()
        self.stimulus = ExternalStimulus(stimulus_source)
        self.decision = DecisionEngine(self.world_model, self.long_term, self.memory)
        self.self_model = SelfModel()
        self.decoder = NeuralDecoder()
        self.cycle = 0; self.score_history = []; self.log_data = []; self.quiet = quiet
        weights_path = self.workspace / "decoder_weights.npz"
        if weights_path.exists(): self.decoder.load_weights(weights_path)
        else: print("[Decoder] No pre-trained weights. Random init.")
        if self.stimulus.is_active:
            print(f"[Aether] Stimulus active: {self.stimulus.metadata.get('source','?')}")
            if not self.decoder.is_trained and self.stimulus.vector is not None:
                pred = self.decoder.predict_params(self.stimulus.vector)
                self.generator.set_params(pred)
                print(f"[Decoder] Init params from stimulus: pattern={pred['pattern']}")
        else: print("[Aether] No stimulus.")
    
    def get_feasible_actions(self, blocked):
        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.resources.energy<=5 or self.resources.attention<=5: return ['rest']
        if self.resources.memory_used>=HardConfig.MEMORY_SLOTS:
            if 'forget' not in feasible: feasible.append('forget')
        if not self.resources.can_rest(): feasible = [a for a in feasible if a!='rest']
        if self.generator.params['pattern'] in blocked:
            for a in ['generate','explore','refine','combine']:
                if a in feasible: feasible.remove(a)
        return feasible or ['rest']
    
    def step(self):
        self.cycle+=1; self.resources.cycle=self.cycle; self.long_term.cycle=self.cycle
        if self.resources.is_coma():
            self.resources.update_coma()
            self._log_step('coma',0,0,self.resources,None)
            return {'action':'coma','score':0,'novelty':0}
        param_vec = ParamEmbedder.embed(self.generator.get_params())
        blocked = set(self.long_term.pattern_blocked_until.keys())
        feasible = self.get_feasible_actions(blocked)
        # Train decoder more frequently
        if self.stimulus.is_active and self.cycle%HardConfig.NN_TRAIN_INTERVAL==0 and self.cycle>0:
            if len(self.decoder.training_buffer)>=HardConfig.NN_BATCH_SIZE:
                self.decoder.train_on_buffer()
        override, forced, reason = self.self_model.get_override(self.resources, self.world_model.confidence)
        if override and forced in feasible:
            chosen = forced; info = {'override':reason}
        else:
            emergency = self.resources.is_emergency()
            chosen, info = self.decision.choose_action(feasible, self.resources, param_vec, blocked, emergency, self.stimulus)
        e0,a0,f0,b0 = self.resources.energy, self.resources.attention, self.resources.fatigue, self.resources.failure_burden
        art = None; score=0.5; nov=0.5
        try:
            if chosen in ['generate','explore','refine','combine']:
                if chosen=='explore': self.generator.mutate(0.5)
                elif chosen=='refine': self.generator.mutate(0.1)
                elif chosen=='combine' and self.memory.vectors:
                    meta = random.choice(self.memory.metadata)
                    self.generator.crossover_with_memory(meta.get('params',self.generator.get_params()))
                # Forced shape exploration if decoder not trained and stimulus active
                if chosen=='generate' and self.stimulus.is_active:
                    if not self.decoder.is_trained and random.random() < HardConfig.NN_FORCED_SHAPE_PROB:
                        self.generator.params['pattern'] = 'shape'
                        self.generator.params['shape_param'] = random.uniform(0,1)
                        if not self.quiet: print("[Forced Shape] Exploring geometric shape")
                    elif self.decoder.is_trained and random.random()<0.7:
                        pred = self.decoder.predict_params(self.stimulus.vector)
                        self.generator.set_params(pred)
                art, pat = self.generator.generate(blocked)
                avec = ArtEmbedder.embed(art)
                nov = self.memory.novelty(avec)
                feats = self._extract_features(art)
                score = self._compute_score(feats)
                new_vec = ParamEmbedder.embed(self.generator.get_params())
                self.world_model.update(new_vec, score)
                self.memory.store(avec, {'score':score,'novelty':nov,'action':chosen,'pattern':pat,'params':self.generator.get_params().copy(),'cycle':self.cycle})
                self.long_term.update(chosen, pat, score, self.cycle)
                if self.stimulus.is_active:
                    sim = self.stimulus.similarity(avec)
                    current_thresh = self.decoder.current_threshold
                    if sim > current_thresh:
                        self.decoder.collect_sample(self.stimulus.vector, self.generator.get_params())
                        if not self.quiet: print(f"[Decoder] Collected sample, sim={sim:.3f} (thresh={current_thresh:.2f}, buffer={len(self.decoder.training_buffer)})")
            elif chosen=='recall' and self.memory.vectors:
                sims = self.memory.recall_similar(param_vec,1)
                if sims and not self.quiet: print(f"[Recall] cycle {sims[0][1].get('cycle','?')} sim={sims[0][0]:.2f}")
            elif chosen=='forget' and self.memory.vectors:
                self.memory.vectors.pop(); self.memory.metadata.pop()
                self.resources.memory_used = max(0, self.resources.memory_used-1)
        except ValueError as e:
            if not self.quiet: print(f"[Infeasible] {e}")
            score=0.2; nov=0; chosen='failed_'+chosen
            self.resources.apply_cost(chosen); self.resources.update_failure_burden(score)
            self.resources.regen(False); self.self_model.update(score)
            self.score_history.append(score); self._log_step(chosen,score,nov,self.resources,info)
            return {'action':chosen,'score':score,'novelty':0}
        self.resources.apply_cost(chosen)
        self.resources.update_failure_burden(score)
        self.resources.regen(chosen=='rest')
        self.self_model.update(score)
        self.score_history.append(score)
        self.long_term.apply_identity_drift(self.score_history)
        self.decision.update_commitment()
        if self.resources.enter_coma() and not self.quiet: print(f"[COMA] cycle {self.cycle}")
        delta = {'energy':self.resources.energy-e0, 'attention':self.resources.attention-a0, 'fatigue':self.resources.fatigue-f0, 'failure_burden':self.resources.failure_burden-b0}
        self._log_step(chosen,score,nov,self.resources,info,delta)
        if not self.quiet:
            print(f"\n[Cycle {self.cycle}] {chosen} | score={score:.3f} nov={nov:.3f}")
            print(f"E={self.resources.energy} A={self.resources.attention} F={self.resources.fatigue} B={self.resources.failure_burden}")
            if art and len(art)>200: print(art[:200]+"...")
            elif art: print(art)
        return {'action':chosen,'score':score,'novelty':nov,'art':art}
    
    def _extract_features(self, art):
        lines = [l for l in art.split('\n') if l.strip()]
        if not lines: return {'symmetry':0,'density':0,'diversity':0,'entropy':0}
        w = max(len(l) for l in lines); h=len(lines)
        padded = [l.ljust(w) for l in lines]
        non = sum(c!=' ' for line in padded for c in line)
        den = non/(w*h)
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
        div = len(set(allc))/min(30,max(1,len(allc))) if allc else 0
        if allc:
            freq = Counter(allc); probs=[f/len(allc) for f in freq.values()]
            ent = -sum(p*math.log2(p) for p in probs)/max(1,math.log2(len(freq)))
        else: ent=0
        return {'symmetry':sym,'density':den,'diversity':div,'entropy':ent}
    
    def _compute_score(self, f):
        d = 1 - abs(f['density']-0.4)*2.5
        return max(0, min(1, d*0.3 + f['symmetry']*0.3 + f['diversity']*0.2 + f['entropy']*0.2))
    
    def _log_step(self, action, score, nov, res, info=None, delta=None):
        entry = {
            'cycle':self.cycle, 'action':str(action), 'score':float(score), 'novelty':float(nov),
            'energy':res.energy, 'attention':res.attention, 'fatigue':res.fatigue, 'failure_burden':res.failure_burden,
            'world_model_confidence':self.world_model.confidence, 'prediction_error':self.world_model.prediction_error,
            'trauma_blocked':list(self.long_term.pattern_blocked_until.keys()),
            'identity':{k:float(v) for k,v in self.long_term.identity_bias.items()},
            'timestamp':datetime.now().isoformat()
        }
        if self.stimulus.is_active:
            entry['stimulus_similarity'] = float(self.stimulus.similarity(ParamEmbedder.embed(self.generator.get_params())))
        if info:
            if 'utilities' in info: entry['utilities'] = {k:float(v) for k,v in info['utilities'].items()}
            if 'noise_effect' in info: entry['noise_effect'] = float(info['noise_effect'])
            if info.get('runner_up'): entry['runner_up'] = info['runner_up']
        if delta: entry['state_delta'] = {k:int(v) for k,v in delta.items()}
        if self.decoder.loss_history: entry['decoder_loss'] = float(self.decoder.loss_history[-1])
        self.log_data.append(entry)
    
    def run_autonomous(self, cycles=200, save_log=True):
        for _ in range(cycles):
            self.step()
            time.sleep(0.3)
        if save_log:
            log_file = self.workspace / f"aether_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, 'w') as f: json.dump(self.log_data, f, indent=2)
            print(f"[Log] {log_file}")
            self.decoder.save_weights(self.workspace / "decoder_weights.npz")


if __name__ == "__main__":
    import sys
    cycles = 200
    stimulus_source = None
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == '--auto' and i+1 < len(sys.argv) and sys.argv[i+1].isdigit():
            cycles = int(sys.argv[i+1]); i+=2
        elif a == '--auto':
            cycles = 200; i+=1
        elif a == '--demo':
            cycles = 20; i+=1
        elif a in ('--image','--stimulus') and i+1 < len(sys.argv):
            stimulus_source = sys.argv[i+1]; i+=2
        else:
            i+=1
    aether = Aether(quiet=False, stimulus_source=stimulus_source)
    aether.run_autonomous(cycles)