"""
EXP-001B: Prediction Error Separability Diagnosis
-----------------------------------------------
Mengukur apakah prediction error (curiosity) cukup informatif untuk membedakan aksi,
dan apakah utility memanfaatkannya dengan baik.

Pengukuran:
- Variance prediction error antar aksi per cycle
- Korelasi antara prediction error dan utility per aksi
- Separability index: seberapa besar error pada aksi yang dipilih vs rata-rata
- Plot error per action over time, variance over time, scatter error vs utility

Keputusan berdasarkan data:
- Jika var_error < 0.01: prediction error tidak informatif → ganti mekanisme curiosity
- Jika var_error > 0.05 dan korelasi error-utility rendah: utility mengabaikan curiosity → perbaiki normalisasi
- Jika var_error > 0.05 dan korelasi error-utility tinggi: curiosity sudah berfungsi → lanjut ke P-03
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from datetime import datetime
from tqdm import tqdm
from aether_exp_001a_v022 import AetherExp001A_v022

# Konfigurasi
N_ACTIONS = 5
N_FEATURES = 36
CYCLES = 500
SEEDS = 10
BASELINE_WEIGHTS = {
    'reward_weight': 1.0,
    'curiosity_weight': 1.0,
    'persistence_weight': 1.0,
    'noise_scale': 1.0,
    'energy_weight': 0.5,
}

def generate_stimulus(cycle, seed):
    """Sama dengan run_exp_001a_v022.py untuk konsistensi."""
    rng = np.random.default_rng(seed + cycle)
    # State: random walk with drift
    base = np.sin(np.linspace(0, 2*np.pi, N_FEATURES) + cycle / 50.0) * 0.5
    state = base + 0.3 * rng.normal(size=N_FEATURES)
    # Action rewards: phase preference
    phase = cycle / 50.0 * 2 * np.pi
    action_phases = np.linspace(0, 2*np.pi, N_ACTIONS, endpoint=False)
    rewards = 0.5 + 0.5 * np.cos(action_phases - phase)
    rewards += 0.1 * rng.normal(size=N_ACTIONS)
    rewards = np.clip(rewards, 0.0, 1.0)
    return state, rewards

def run_diagnostic(seed):
    """Jalankan satu seed dan kumpulkan data diagnostik."""
    agent = AetherExp001A_v022(
        seed=seed,
        n_actions=N_ACTIONS,
        n_features=N_FEATURES,
        history_length=50,
        **BASELINE_WEIGHTS
    )
    
    # Data koleksi
    per_cycle = {
        'cycle': [],
        'chosen_action': [],
        'prediction_errors': [],   # list of arrays (n_actions,)
        'utilities': [],           # list of arrays (n_actions,)
        'var_error': [],
        'chosen_error': [],
        'mean_error': [],
    }
    
    for cycle in range(1, CYCLES + 1):
        state, rewards = generate_stimulus(cycle, seed)
        
        # Sebelum act, kita perlu prediction error untuk setiap aksi.
        # Kita akan menghitung ulang di sini karena agent tidak menyimpannya.
        # Tapi kita bisa mengambil dari agent setelah observe, tapi agent 
        # hanya menyimpan last_prediction_error untuk aksi terakhir.
        # Untuk diagnostik, kita perlu error untuk SEMUA aksi.
        # Kita akan menggunakan metode agent untuk memprediksi per aksi.
        
        # Simpan state sebelumnya untuk prediksi
        if len(agent.state_history) > 0:
            prev_state = agent.state_history[-1]
        else:
            prev_state = state  # fallback
        
        # Hitung prediction error untuk setiap aksi
        errors = []
        for a in range(N_ACTIONS):
            predicted = agent.predict_next_state(a, prev_state)
            # Actual state setelah aksi? Kita belum tahu karena belum act.
            # Kita perlu memprediksi error sebelum act? 
            # Untuk diagnostik, yang kita inginkan adalah error dari aksi yang DIPILIH vs lainnya.
            # Tapi kita belum tahu aksi mana yang akan dipilih.
            # Kita bisa menghitung error setelah act, menggunakan state aktual.
            # Atau kita bisa menghitung prediksi error sebelum act (berdasarkan model saat ini).
            # Yang lebih informatif adalah error aktual setelah aksi diambil.
            # Kita akan simpan prediksi untuk nanti dibandingkan dengan state aktual.
            pass
        
        # Untuk simplicity, kita akan gunakan pendekatan:
        # - Simpan prediksi untuk setiap aksi sebelum act.
        # - Setelah act, dapatkan state aktual, hitung error untuk action yang dipilih.
        # - Untuk aksi lain, kita tidak tahu state aktualnya (karena tidak diambil).
        # Jadi kita hanya bisa menghitung error untuk aksi yang dipilih secara akurat.
        # Untuk aksi lain, kita gunakan prediksi error berdasarkan model saat ini (sebelum act).
        # Atau kita bisa gunakan pendekatan: prediksi error = error dari prediksi state
        # berdasarkan model, tanpa melihat state aktual.
        # Mari kita lakukan: error = ||predicted_state - current_state||,
        # di mana current_state adalah state SEBELUM act, dan predicted_state
        # adalah prediksi dari state saat ini. Ini adalah "intrinsic" error.
        # Ini bukan error aktual (yang butuh state setelah act), 
        # tapi ini adalah ukuran ketidakpastian model.
        
        # Saya akan gunakan pendekatan yang lebih sederhana dan konsisten:
        # Prediction error untuk aksi a = jarak antara state saat ini dan 
        # prediksi state berikutnya menggunakan model untuk aksi a.
        # Ini adalah "uncertainty" tentang aksi a, tanpa perlu act.
        errors = []
        for a in range(N_ACTIONS):
            predicted = agent.predict_next_state(a, state)
            # State saat ini sebagai "ground truth" untuk prediksi
            # (ini bukan error aktual, tapi error prediksi tanpa transisi)
            err = np.linalg.norm(state - predicted)
            errors.append(err)
        
        # Sekarang kita pilih aksi menggunakan utility (agent.act akan lakukan)
        # Tapi kita perlu utility untuk setiap aksi juga.
        # Kita bisa hitung utility untuk setiap aksi menggunakan agent.compute_utility
        # tanpa mempengaruhi state internal agent.
        utilities = []
        for a in range(N_ACTIONS):
            # compute_utility membutuhkan action_rewards, yang kita miliki
            u, _ = agent.compute_utility(a, rewards)
            utilities.append(u)
        
        # Pilih aksi dengan utility tertinggi (softmax akan dilakukan di agent.act, 
        # tapi untuk konsistensi kita ambil dari agent setelah act)
        # Kita jalankan act dan catat hasilnya.
        chosen = agent.act(rewards, state)
        
        # Simpan data
        per_cycle['cycle'].append(cycle)
        per_cycle['chosen_action'].append(chosen)
        per_cycle['prediction_errors'].append(np.array(errors))
        per_cycle['utilities'].append(np.array(utilities))
        per_cycle['var_error'].append(np.var(errors))
        per_cycle['chosen_error'].append(errors[chosen])
        per_cycle['mean_error'].append(np.mean(errors))
    
    # Hitung metrik agregat
    var_error_mean = np.mean(per_cycle['var_error'])
    var_error_std = np.std(per_cycle['var_error'])
    
    # Korelasi antara error dan utility (per action, per cycle)
    # Kita kumpulkan semua pasangan (error, utility) dari semua cycle dan aksi
    all_errors = []
    all_utils = []
    for err_arr, util_arr in zip(per_cycle['prediction_errors'], per_cycle['utilities']):
        all_errors.extend(err_arr)
        all_utils.extend(util_arr)
    corr_error_utility = np.corrcoef(all_errors, all_utils)[0, 1] if len(all_errors) > 1 else np.nan
    
    # Separability index: rata-rata selisih error pada aksi yang dipilih vs rata-rata
    sep_index = np.mean([per_cycle['chosen_error'][i] - per_cycle['mean_error'][i] 
                         for i in range(len(per_cycle['cycle']))])
    
    return {
        'seed': seed,
        'var_error_mean': var_error_mean,
        'var_error_std': var_error_std,
        'corr_error_utility': corr_error_utility,
        'separability_index': sep_index,
        'per_cycle': per_cycle,
    }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='Quick run: 1 seed, 100 cycles')
    parser.add_argument('--seed', type=int, default=None, help='Specific seed to run')
    args = parser.parse_args()
    
    if args.quick:
        seeds = [42]
        cycles = 100
        out_suffix = "quick"
    elif args.seed is not None:
        seeds = [args.seed]
        cycles = CYCLES
        out_suffix = f"seed{args.seed}"
    else:
        seeds = list(range(10000, 10000 + SEEDS))
        cycles = CYCLES
        out_suffix = "full"
    
    print(f"EXP-001B: Prediction Error Separability Diagnosis")
    print(f"Seeds: {seeds}")
    print(f"Cycles: {cycles}")
    print(f"Mode: {out_suffix}")
    
    all_results = []
    for seed in tqdm(seeds, desc="Running seeds"):
        result = run_diagnostic(seed)
        all_results.append(result)
    
    # Agregasi antar seed
    var_error_means = [r['var_error_mean'] for r in all_results]
    corr_values = [r['corr_error_utility'] for r in all_results if not np.isnan(r['corr_error_utility'])]
    sep_indices = [r['separability_index'] for r in all_results]
    
    summary = {
        'seeds': seeds,
        'cycles': cycles,
        'var_error_mean_avg': np.mean(var_error_means),
        'var_error_mean_std': np.std(var_error_means),
        'corr_error_utility_avg': np.mean(corr_values) if corr_values else np.nan,
        'corr_error_utility_std': np.std(corr_values) if corr_values else np.nan,
        'separability_index_avg': np.mean(sep_indices),
        'separability_index_std': np.std(sep_indices),
        'per_seed': all_results,
    }
    
    # Tampilkan hasil
    print("\n" + "="*60)
    print("EXP-001B RESULTS")
    print("="*60)
    print(f"Rata-rata variance error antar aksi: {summary['var_error_mean_avg']:.4f} ± {summary['var_error_mean_std']:.4f}")
    print(f"Korelasi error-utility: {summary['corr_error_utility_avg']:.4f} ± {summary['corr_error_utility_std']:.4f}")
    print(f"Separability index: {summary['separability_index_avg']:.4f} ± {summary['separability_index_std']:.4f}")
    
    # Interpretasi
    print("\n--- Interpretasi ---")
    if summary['var_error_mean_avg'] < 0.01:
        print("⚠️  Prediction error variance sangat kecil (< 0.01).")
        print("    → Curiosity tidak informatif. Perlu ganti mekanisme curiosity.")
        verdict = "GANTI_CURIOSITY"
    elif summary['var_error_mean_avg'] > 0.05 and summary['corr_error_utility_avg'] < 0.2:
        print("⚠️  Prediction error variance cukup (> 0.05) tetapi korelasi dengan utility rendah.")
        print("    → Utility mengabaikan curiosity. Perlu perbaiki normalisasi utility.")
        verdict = "PERBAIKI_UTILITY"
    elif summary['var_error_mean_avg'] > 0.05 and summary['corr_error_utility_avg'] >= 0.2:
        print("✅  Prediction error variance cukup dan berkorelasi dengan utility.")
        print("    → Curiosity sudah berfungsi dengan baik. Bisa lanjut ke P-03.")
        verdict = "LANJUT_P03"
    else:
        print("🟡  Hasil tidak jelas. Perlu investigasi lebih lanjut.")
        verdict = "INVESTIGASI"
    
    print(f"Verdict: {verdict}")
    summary['verdict'] = verdict
    
    # Simpan hasil
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"exp_001b_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), 'w') as f:
        # Convert numpy arrays to lists for JSON
        json_summary = {
            'seeds': seeds,
            'cycles': cycles,
            'var_error_mean_avg': float(summary['var_error_mean_avg']),
            'var_error_mean_std': float(summary['var_error_mean_std']),
            'corr_error_utility_avg': float(summary['corr_error_utility_avg']) if not np.isnan(summary['corr_error_utility_avg']) else None,
            'corr_error_utility_std': float(summary['corr_error_utility_std']) if not np.isnan(summary['corr_error_utility_std']) else None,
            'separability_index_avg': float(summary['separability_index_avg']),
            'separability_index_std': float(summary['separability_index_std']),
            'verdict': verdict,
            'per_seed': []  # too large to include fully; we'll save separately
        }
        json.dump(json_summary, f, indent=2)
    
    # Simpan per-seed data ringkas
    for r in all_results:
        seed = r['seed']
        seed_file = os.path.join(out_dir, f"seed_{seed}_summary.json")
        # Simpan ringkasan per seed tanpa per_cycle (terlalu besar)
        seed_summary = {
            'seed': seed,
            'var_error_mean': float(r['var_error_mean']),
            'var_error_std': float(r['var_error_std']),
            'corr_error_utility': float(r['corr_error_utility']) if not np.isnan(r['corr_error_utility']) else None,
            'separability_index': float(r['separability_index']),
        }
        with open(seed_file, 'w') as f:
            json.dump(seed_summary, f, indent=2)
    
    # Buat plot (ambil seed pertama untuk visualisasi)
    if all_results:
        r0 = all_results[0]
        cycles_range = r0['per_cycle']['cycle']
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # Plot 1: Variance per cycle
        axes[0, 0].plot(cycles_range, r0['per_cycle']['var_error'], alpha=0.7)
        axes[0, 0].axhline(y=summary['var_error_mean_avg'], color='r', linestyle='--', label=f'Mean: {summary["var_error_mean_avg"]:.3f}')
        axes[0, 0].set_xlabel('Cycle')
        axes[0, 0].set_ylabel('Variance of Prediction Errors')
        axes[0, 0].set_title('Prediction Error Variance Over Time')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        
        # Plot 2: Scatter error vs utility (all actions)
        all_errors = []
        all_utils = []
        for err_arr, util_arr in zip(r0['per_cycle']['prediction_errors'], r0['per_cycle']['utilities']):
            all_errors.extend(err_arr)
            all_utils.extend(util_arr)
        axes[0, 1].scatter(all_errors, all_utils, alpha=0.3, s=10)
        axes[0, 1].set_xlabel('Prediction Error')
        axes[0, 1].set_ylabel('Utility')
        axes[0, 1].set_title(f'Error vs Utility (corr = {r0["corr_error_utility"]:.3f})')
        axes[0, 1].grid(True, alpha=0.3)
        
        # Plot 3: Chosen error vs mean error
        chosen_errors = r0['per_cycle']['chosen_error']
        mean_errors = r0['per_cycle']['mean_error']
        axes[1, 0].plot(cycles_range, chosen_errors, label='Chosen action error', alpha=0.7)
        axes[1, 0].plot(cycles_range, mean_errors, label='Mean error (all actions)', alpha=0.7)
        axes[1, 0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        axes[1, 0].set_xlabel('Cycle')
        axes[1, 0].set_ylabel('Prediction Error')
        axes[1, 0].set_title('Chosen vs Mean Prediction Error')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        
        # Plot 4: Distribution of errors per action (average over cycles)
        n_actions = N_ACTIONS
        action_errors = [[] for _ in range(n_actions)]
        for err_arr in r0['per_cycle']['prediction_errors']:
            for a in range(n_actions):
                action_errors[a].append(err_arr[a])
        axes[1, 1].boxplot(action_errors, labels=[f'A{a}' for a in range(n_actions)])
        axes[1, 1].set_xlabel('Action')
        axes[1, 1].set_ylabel('Prediction Error')
        axes[1, 1].set_title('Distribution of Errors per Action')
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, "diagnostic_plots.png"), dpi=150)
        print(f"\nPlots saved to {out_dir}/diagnostic_plots.png")
    
    print(f"\nResults saved to {out_dir}/")
    print("="*60)

if __name__ == "__main__":
    main()