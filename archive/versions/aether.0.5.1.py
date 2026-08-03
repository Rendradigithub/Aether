```python
#!/usr/bin/env python3
# =============================================================================
# AETHER v0.5.1 — FULL SYSTEM RECONSTRUCTION
# "KARYA HIDUP" (Living System + Learning Core)
# =============================================================================

import numpy as np
import random
import json
import time
from pathlib import Path
from datetime import datetime

# =============================================================================
# CORE STORAGE
# =============================================================================

class Core:
    def __init__(self):
        self.dir = Path("aether_051_full")
        self.dir.mkdir(exist_ok=True)

        self.memory_file = self.dir / "memory.json"
        self.meta_file = self.dir / "meta.json"
        self.params_file = self.dir / "params.json"

        self.memory = self._load(self.memory_file, [])
        self.meta = self._load(self.meta_file, {
            "cycle": 0,
            "momentum": 0.5,
            "stagnation": 0
        })
        self.params = self._load(self.params_file, {
            "freq_x": 0.1,
            "freq_y": 0.1,
            "noise": 0.3,
            "symmetry": 0.4,
            "phase": 0.0
        })

    def _load(self, path, default):
        if path.exists():
            return json.loads(path.read_text())
        return default

    def save(self):
        self.memory_file.write_text(json.dumps(self.memory, indent=2))
        self.meta_file.write_text(json.dumps(self.meta, indent=2))
        self.params_file.write_text(json.dumps(self.params, indent=2))


# =============================================================================
# EMBEDDING (REPRESENTATION)
# =============================================================================

class Embedding:
    @staticmethod
    def encode(grid):
        flat = grid.flatten()
        return np.array([
            np.mean(flat),
            np.std(flat),
            np.max(flat),
            np.min(flat),
            np.median(flat),
            np.var(flat),
            np.sum(flat)
        ], dtype=float)

    @staticmethod
    def cosine(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


# =============================================================================
# MEMORY SYSTEM
# =============================================================================

class Memory:
    def __init__(self, core):
        self.core = core

    def vectors(self):
        return [np.array(m["vec"]) for m in self.core.memory]

    def similarity(self, vec):
        mem = self.vectors()
        if not mem:
            return 0.0
        return max(Embedding.cosine(vec, m) for m in mem)

    def store(self, vec, score, meta):
        self.core.memory.append({
            "vec": vec.tolist(),
            "score": score,
            "meta": meta,
            "time": datetime.now().isoformat()
        })
        self.core.memory = self.core.memory[-300:]


# =============================================================================
# GENERATOR
# =============================================================================

class Generator:
    def __init__(self, params):
        self.p = params

    def generate(self, size=40):
        grid = np.zeros((size, size))

        for y in range(size):
            for x in range(size):
                val = (
                    np.sin(x * self.p["freq_x"] + self.p["phase"]) +
                    np.cos(y * self.p["freq_y"])
                )

                if random.random() < self.p["symmetry"]:
                    val += abs(x - size/2) * 0.05

                val += random.uniform(-self.p["noise"], self.p["noise"])
                grid[y][x] = val

        return grid


# =============================================================================
# EVALUATOR
# =============================================================================

class Evaluator:
    @staticmethod
    def evaluate(grid, memory):
        vec = Embedding.encode(grid)
        similarity = memory.similarity(vec)
        novelty = 1 - similarity

        structure = np.std(grid)
        diversity = len(set(np.round(grid.flatten(), 2)))

        score = (
            novelty * 0.5 +
            structure * 0.3 +
            (diversity / 1000)
        )

        return {
            "vec": vec,
            "score": float(score),
            "novelty": novelty
        }


# =============================================================================
# EVOLUTION
# =============================================================================

class Evolution:
    def __init__(self, core):
        self.core = core

    def update(self, result):
        p = self.core.params
        score = result["score"]

        if score > 0.7:
            p["noise"] *= 0.9
            p["freq_x"] += random.uniform(-0.02, 0.02)
            p["freq_y"] += random.uniform(-0.02, 0.02)
        else:
            p["noise"] += 0.05
            p["phase"] += random.uniform(-0.2, 0.2)

        for k in p:
            p[k] = max(-2.0, min(2.0, p[k]))


# =============================================================================
# ART ENGINE (EXPRESSION)
# =============================================================================

class ArtEngine:
    CHARS = " .:-=+*#%@"

    @staticmethod
    def render(grid):
        out = ""
        for row in grid:
            for v in row:
                idx = int(np.clip((v + 2) / 4 * len(ArtEngine.CHARS), 0, len(ArtEngine.CHARS)-1))
                out += ArtEngine.CHARS[idx]
            out += "\n"
        return out


# =============================================================================
# GOAL ENGINE
# =============================================================================

class GoalEngine:
    def __init__(self, core):
        self.core = core

    def next(self):
        m = self.core.meta

        if m["stagnation"] > 3:
            return "explore"
        elif m["momentum"] > 0.7:
            return "refine"
        else:
            return "balance"


# =============================================================================
# REFLECTION
# =============================================================================

class Reflection:
    def __init__(self, core):
        self.core = core

    def update(self, score):
        m = self.core.meta

        if score > 0.7:
            m["momentum"] += 0.05
            m["stagnation"] = 0
        else:
            m["stagnation"] += 1
            m["momentum"] *= 0.95

        m["momentum"] = max(0.0, min(1.0, m["momentum"]))


# =============================================================================
# MAIN LOOP
# =============================================================================

class Aether:
    def __init__(self):
        self.core = Core()
        self.memory = Memory(self.core)
        self.evo = Evolution(self.core)
        self.goal = GoalEngine(self.core)
        self.reflect = Reflection(self.core)

    def step(self):
        goal = self.goal.next()

        gen = Generator(self.core.params)
        grid = gen.generate()

        result = Evaluator.evaluate(grid, self.memory)

        self.memory.store(result["vec"], result["score"], goal)
        self.evo.update(result)
        self.reflect.update(result["score"])

        self.core.meta["cycle"] += 1
        self.core.save()

        print("\n[AETHER]")
        print(f"Cycle     : {self.core.meta['cycle']}")
        print(f"Goal      : {goal}")
        print(f"Score     : {result['score']:.3f}")
        print(f"Novelty   : {result['novelty']:.3f}")
        print(f"Params    : {self.core.params}")
        print(ArtEngine.render(grid))

    def run(self):
        while True:
            self.step()
            time.sleep(0.5)


# =============================================================================
# ENTRY
# =============================================================================

if __name__ == "__main__":
    Aether().run()
```
