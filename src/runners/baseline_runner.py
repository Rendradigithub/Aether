#!/usr/bin/env python3
"""
BASELINE RUNNER — AETHER v0.19
================================
Menjalankan banyak seed, mengumpulkan data, dan menyimpannya untuk BASELINE.md.

Usage:
    python baseline_runner.py --seeds 30 --cycles 500 --version 0.19.1
"""

import json
import sys
import time
import random
import numpy as np
from collections import Counter
from pathlib import Path
import importlib.util

def load_aether(version="0.19.1"):
    filename = f"aether.{version}.py"
    if not Path(filename).exists():
        print(f"[ERROR] File {filename} tidak ditemukan.")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("aether", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class BaselineRunner:
    def __init__(self, seeds=30, cycles=500, version="0.19.1", stimulus="circle.png"):
        self.seeds = seeds
        self.cycles = cycles
        self.version = version
        self.stimulus = stimulus
        self.aether = load_aether(version)
        self.AetherCore = self.aether.AetherCognitiveCore

    def run_seed(self, seed):
        random.seed(seed)
        np.random.seed(seed)

        # Subclass untuk menangkap data per cycle
        class CapturingCore(self.AetherCore):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.history = []

            def step(self):
                result = super().step()
                if result[0] is None:
                    return result
                art, reward, radial, pat = result
                self.history.append({
                    "cycle": self.cycle,
                    "reward": float(reward) if reward is not None else 0.0,
                    "radial": float(radial) if radial is not None else 0.0,
                    "pattern": pat if pat else "unknown",
                    "energy": int(self.budget.energy),
                    "attention": int(self.budget.attention),
                    "fatigue": int(self.budget.fatigue),
                    "burden": int(self.budget.failure_burden),
                })
                return result

        core = CapturingCore(stimulus_source=self.stimulus, quiet=True)
        core.run(self.cycles)
        history = core.history
        pattern_counts = core.pattern_counts

        rewards = [h["reward"] for h in history if h.get("reward") is not None]
        if len(rewards) == 0:
            return None

        # Autokorelasi
        autocorr = {}
        if len(rewards) > 5:
            r_np = np.array(rewards)
            for lag in range(1, 6):
                if len(r_np) > lag:
                    corr = np.corrcoef(r_np[:-lag], r_np[lag:])[0, 1]
                    autocorr[lag] = float(corr) if not np.isnan(corr) else 0.0
                else:
                    autocorr[lag] = 0.0

        # Entropi
        total = sum(pattern_counts.values())
        if total > 0:
            probs = [count/total for count in pattern_counts.values()]
            entropy = -sum(p * np.log(p + 1e-8) for p in probs)
        else:
            entropy = 0.0

        return {
            "seed": seed,
            "cycles": len(history),
            "avg_reward": float(np.mean(rewards)),
            "std_reward": float(np.std(rewards)),
            "avg_energy": float(np.mean([h["energy"] for h in history])),
            "avg_fatigue": float(np.mean([h["fatigue"] for h in history])),
            "pattern_counts": dict(pattern_counts),
            "entropy": float(entropy),
            "autocorrelation": autocorr,
            "history": history,
        }

    def run_batch(self):
        print(f"\n=== BASELINE RUNNER ===")
        print(f"Versi Aether: {self.version}")
        print(f"Seeds: {self.seeds}, Cycles: {self.cycles}")
        print(f"Stimulus: {self.stimulus}")
        print("========================\n")

        all_data = []
        for i in range(self.seeds):
            seed = 10000 + i
            print(f"[{i+1}/{self.seeds}] Running seed {seed}...", end=" ", flush=True)
            start = time.time()
            result = self.run_seed(seed)
            elapsed = time.time() - start
            if result is None:
                print("failed")
                continue
            all_data.append(result)
            print(f"done ({elapsed:.1f}s)  entropy={result['entropy']:.3f} avg_reward={result['avg_reward']:.3f}")

        timestamp = int(time.time())
        raw_file = f"baseline_raw_{timestamp}.json"
        with open(raw_file, "w") as f:
            json.dump(all_data, f, indent=2, default=str)
        print(f"\n[OK] Data mentah disimpan ke {raw_file}")

        # Statistik agregat
        avg_entropy = np.mean([d["entropy"] for d in all_data])
        avg_autocorr = np.mean([d["autocorrelation"].get(1, 0) for d in all_data])
        avg_reward = np.mean([d["avg_reward"] for d in all_data])
        avg_fatigue = np.mean([d["avg_fatigue"] for d in all_data])
        std_entropy = np.std([d["entropy"] for d in all_data])
        std_autocorr = np.std([d["autocorrelation"].get(1, 0) for d in all_data])

        summary = {
            "version": self.version,
            "seeds": self.seeds,
            "cycles": self.cycles,
            "stimulus": self.stimulus,
            "timestamp": timestamp,
            "avg_entropy": float(avg_entropy),
            "std_entropy": float(std_entropy),
            "avg_autocorr_l1": float(avg_autocorr),
            "std_autocorr_l1": float(std_autocorr),
            "avg_reward": float(avg_reward),
            "avg_fatigue": float(avg_fatigue),
            "threshold_2sigma_entropy": float(avg_entropy + 2*std_entropy),
            "threshold_2sigma_autocorr": float(avg_autocorr + 2*std_autocorr),
        }
        with open("baseline_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
        print(f"[OK] Ringkasan disimpan ke baseline_summary.json")

        print("\n=== BASELINE STATISTICS (untuk BASELINE.md) ===")
        print(f"| Metric | Mean | Std Dev | 95% CI (2σ) |")
        print(f"|--------|------|---------|-------------|")
        print(f"| Entropy | {avg_entropy:.4f} | {std_entropy:.4f} | {avg_entropy + 2*std_entropy:.4f} |")
        print(f"| Autocorr L1 | {avg_autocorr:.4f} | {std_autocorr:.4f} | {avg_autocorr + 2*std_autocorr:.4f} |")
        print(f"| Reward | {avg_reward:.4f} | - | - |")
        print(f"| Fatigue | {avg_fatigue:.2f} | - | - |")
        print("\n[OK] Selesai.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--cycles", type=int, default=500)
    parser.add_argument("--version", type=str, default="0.19.1")
    parser.add_argument("--stimulus", type=str, default="circle.png")
    args = parser.parse_args()
    runner = BaselineRunner(
        seeds=args.seeds,
        cycles=args.cycles,
        version=args.version,
        stimulus=args.stimulus
    )
    runner.run_batch()