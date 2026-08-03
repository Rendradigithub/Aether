"""
EXP-001C.5: Reality Separability
================================
Mengukur apakah aksi yang berbeda benar-benar menghasilkan state berikutnya yang berbeda
di lingkungan aktual (bukan model).

Jika jarak antar state hasil aksi berbeda mendekati 0 → environment tidak responsif.
Jika jarak besar → environment responsif, masalah ada di world model.
"""

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from collections import defaultdict
import argparse
from pathlib import Path
from datetime import datetime

# Constants (sama dengan runner)
N_ACTIONS = 5
N_FEATURES = 36
N_STATES = 10   # jumlah state awal yang diuji
N_SEEDS = 10
CYCLES_PER_STATE = 1  # transisi per aksi

def generate_stimulus(cycle, seed, action=None):
    """
    Generate state dan rewards.
    Catatan: state TIDAK bergantung pada action.
    """
    rng = np.random.default_rng(seed + cycle)
    base = np.sin(np.linspace(0, 2*np.pi, N_FEATURES) + cycle / 50.0) * 0.5
    state = base + 0.3 * rng.normal(size=N_FEATURES)
    
    # Reward tetap dihitung (tapi untuk separability kita abaikan)
    phase = cycle / 50.0 * 2 * np.pi
    action_phases = np.linspace(0, 2*np.pi, N_ACTIONS, endpoint=False)
    rewards = 0.5 + 0.5 * np.cos(action_phases - phase)
    rewards += 0.1 * rng.normal(size=N_ACTIONS)
    rewards = np.clip(rewards, 0.0, 1.0)
    return state, rewards

def get_next_state(cycle, seed, action):
    """Generate next state for a given action (state is independent of action!)."""
    # Dalam environment saat ini, state tidak peduli action.
    # Kita gunakan cycle+1 untuk mendapatkan next state.
    # Action hanya digunakan untuk konsistensi signature.
    next_state, _ = generate_stimulus(cycle + 1, seed, action)
    return next_state

def run_separability_test(seed, cycles_offset=100):
    """
    Uji separabilitas reality.
    Ambil N_STATES state awal dari cycle tertentu, lalu untuk setiap aksi,
    dapatkan next_state, lalu ukur jarak antar aksi.
    """
    all_distances = []
    all_pairwise = defaultdict(list)
    
    for i in range(N_STATES):
        cycle = cycles_offset + i * 10  # ambil state yang berbeda
        state, _ = generate_stimulus(cycle, seed)
        
        next_states = []
        for a in range(N_ACTIONS):
            ns, _ = generate_stimulus(cycle + 1, seed, a)  # next state
            next_states.append(ns)
        
        # Hitung pairwise distances antara next_states
        for a1 in range(N_ACTIONS):
            for a2 in range(a1 + 1, N_ACTIONS):
                dist = np.linalg.norm(next_states[a1] - next_states[a2])
                all_distances.append(dist)
                all_pairwise[f"{a1}-{a2}"].append(dist)
    
    return {
        'seed': seed,
        'all_distances': np.array(all_distances),
        'pairwise': {k: np.array(v) for k, v in all_pairwise.items()},
        'mean_distance': np.mean(all_distances),
        'std_distance': np.std(all_distances),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='Quick test: 1 seed, 3 states')
    parser.add_argument('--seeds', type=int, default=N_SEEDS, help='Number of seeds')
    args = parser.parse_args()
    
    if args.quick:
        seeds = [42]
        n_states = 3
    else:
        seeds = [10000 + i for i in range(args.seeds)]
        n_states = N_STATES
    
    print("=" * 60)
    print("EXP-001C.5: Reality Separability")
    print(f"Seeds: {seeds}")
    print(f"States per seed: {n_states}")
    print("=" * 60)
    
    results = []
    for seed in tqdm(seeds, desc="Testing seeds"):
        res = run_separability_test(seed)
        results.append(res)
    
    # Aggregasi
    all_means = [r['mean_distance'] for r in results]
    all_stds = [r['std_distance'] for r in results]
    global_mean = np.mean(all_means)
    global_std = np.std(all_means)
    
    print("\n" + "=" * 60)
    print("REALITY SEPARABILITY RESULTS")
    print("=" * 60)
    print(f"Mean distance between next_states across actions: {global_mean:.4f} ± {global_std:.4f}")
    
    # Interpretasi
    print("\n--- Interpretation ---")
    if global_mean < 0.02:
        print("❌ LOW SEPARABILITY: Actions produce nearly identical next states.")
        print("   → Environment is NOT action-responsive (Kasus A).")
        print("   → Curiosity cannot exist in this environment.")
        print("   → Harus ubah environment sebelum lanjut.")
    elif global_mean < 0.05:
        print("🟡 MODERATE SEPARABILITY: Some difference, but weak.")
        print("   → Environment has weak action-response.")
        print("   → Mungkin representasi state (36 dim) kehilangan informasi penting (Kasus B).")
        print("   → Atau world model terlalu lemah (Kasus C).")
    else:
        print("✅ GOOD SEPARABILITY: Actions clearly produce different next states.")
        print("   → Environment IS responsive to actions.")
        print("   → Masalah ada di world model (Kasus C).")
        print("   → v0.23 (Action-Conditioned Model) adalah langkah tepat.")
    
    # Plot distribusi distance
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # 1. Histogram semua jarak
    all_dists = np.concatenate([r['all_distances'] for r in results])
    ax = axes[0]
    ax.hist(all_dists, bins=30, alpha=0.7, color='blue', edgecolor='black')
    ax.axvline(global_mean, color='red', linestyle='--', label=f'Mean: {global_mean:.4f}')
    ax.set_xlabel('Pairwise Distance between Next States')
    ax.set_ylabel('Frequency')
    ax.set_title('Distribution of State Separability')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 2. Boxplot per action pair
    ax = axes[1]
    pair_keys = sorted(results[0]['pairwise'].keys())
    pair_data = []
    for key in pair_keys:
        vals = np.concatenate([r['pairwise'][key] for r in results])
        pair_data.append(vals)
    ax.boxplot(pair_data, labels=pair_keys)
    ax.set_xlabel('Action Pair')
    ax.set_ylabel('Distance')
    ax.set_title('Separability per Action Pair')
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    # Simpan
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"exp_001c5_{timestamp}")
    out_dir.mkdir(exist_ok=True)
    plt.savefig(out_dir / 'separability_plots.png', dpi=150)
    plt.close()
    
    # Simpan data
    summary = {
        'seeds': seeds,
        'n_states': n_states,
        'global_mean': global_mean,
        'global_std': global_std,
        'interpretation': 'low' if global_mean < 0.02 else 'moderate' if global_mean < 0.05 else 'good'
    }
    import json
    with open(out_dir / 'separability_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nPlots saved to {out_dir / 'separability_plots.png'}")
    print(f"Results saved to {out_dir / 'separability_summary.json'}")
    print("=" * 60)

if __name__ == "__main__":
    main()