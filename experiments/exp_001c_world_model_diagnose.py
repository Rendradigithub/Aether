"""
EXP-001C: World Model Diagnostics
=================================
Mengukur kualitas world model yang digunakan untuk curiosity (prediction error).

Pertanyaan yang dijawab:
1. Apakah prediksi next state berbeda signifikan untuk tiap aksi?
   → Variance across actions (flattened state vectors)

2. Seberapa akurat prediksi terhadap next state aktual?
   → MSE between predicted and actual next state (for chosen action)

3. Apakah model collapse menjadi prediksi yang hampir sama untuk semua aksi?
   → Cosine similarity antar prediksi untuk aksi berbeda

4. Apakah error turun seiring pengalaman?
   → Trend prediction error over time (per aksi)
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from sklearn.metrics.pairwise import cosine_similarity

from aether_exp_001a_v022 import AetherExp001A_v022

# ============================================================
#  Constants
# ============================================================

N_ACTIONS = 5
N_FEATURES = 36
DEFAULT_CYCLES = 500
DEFAULT_SEEDS = 10
DEFAULT_SEED_START = 10000

# ============================================================
#  Stimulus Generator (same as v0.22 runner)
# ============================================================

def generate_stimulus(cycle: int, seed: int):
    rng = np.random.default_rng(seed + cycle)
    base = np.sin(np.linspace(0, 2*np.pi, N_FEATURES) + cycle / 50.0) * 0.5
    state = base + 0.3 * rng.normal(size=N_FEATURES)
    phase = cycle / 50.0 * 2 * np.pi
    action_phases = np.linspace(0, 2*np.pi, N_ACTIONS, endpoint=False)
    rewards = 0.5 + 0.5 * np.cos(action_phases - phase)
    rewards += 0.1 * rng.normal(size=N_ACTIONS)
    rewards = np.clip(rewards, 0.0, 1.0)
    return state, rewards

# ============================================================
#  Single Run Diagnostic
# ============================================================

def run_diagnostic(seed: int, cycles: int):
    """Run one agent and collect world model diagnostics."""
    agent = AetherExp001A_v022(
        seed=seed,
        reward_weight=1.0,
        curiosity_weight=1.0,
        persistence_weight=1.0,
        energy_weight=0.5,
        noise_scale=0.3,
        n_actions=N_ACTIONS,
        n_features=N_FEATURES,
        history_length=50
    )

    # Storage per cycle
    pred_errors = {a: [] for a in range(N_ACTIONS)}          # prediction error per action (actual vs predicted)
    pred_states = {a: [] for a in range(N_ACTIONS)}          # predicted next state vectors
    actual_next_states = []                                   # actual next state vectors
    chosen_actions = []                                       # action taken
    variance_across_actions = []                              # variance of flattened predictions across actions
    cosine_sim_across_actions = []                            # average pairwise cosine similarity
    mse_chosen_action = []                                    # MSE for the chosen action

    for cycle in range(1, cycles + 1):
        state, action_rewards = generate_stimulus(cycle, seed)

        # ---- 1. Predictions before acting ----
        preds = []
        for a in range(N_ACTIONS):
            pred = agent.predict_next_state(a, state)
            preds.append(pred)
            pred_states[a].append(pred.flatten())

        # ---- 2. Act ----
        action = agent.act(action_rewards, state)
        chosen_actions.append(action)

        # ---- 3. Get actual next state (from agent) ----
        actual_next = agent.current_state
        actual_next_states.append(actual_next.flatten())

        # ---- 4. Compute diagnostics for this cycle ----
        # 4a. Prediction errors per action
        for a in range(N_ACTIONS):
            err = np.linalg.norm(actual_next - preds[a])
            pred_errors[a].append(err)

        # 4b. MSE for chosen action
        chosen_pred = preds[action]
        mse = np.mean((actual_next - chosen_pred) ** 2)
        mse_chosen_action.append(mse)

        # 4c. Variance across action predictions (flattened vectors)
        preds_flat = np.array([p.flatten() for p in preds])  # (n_actions, n_features)
        # Variance across actions at each feature, then average across features
        var_across_actions = np.mean(np.var(preds_flat, axis=0))
        variance_across_actions.append(var_across_actions)

        # 4d. Cosine similarity across action predictions
        if len(preds_flat) > 1:
            sim_matrix = cosine_similarity(preds_flat)
            # average over off-diagonal
            n = len(sim_matrix)
            off_diag = sim_matrix[~np.eye(n, dtype=bool)].reshape(n, -1)
            avg_sim = np.mean(off_diag)
            cosine_sim_across_actions.append(avg_sim)
        else:
            cosine_sim_across_actions.append(1.0)

    # ---- Convert to arrays ----
    result = {
        'seed': seed,
        'cycles': cycles,
        'pred_errors': {a: np.array(v) for a, v in pred_errors.items()},
        'pred_states': pred_states,
        'actual_next_states': np.array(actual_next_states),
        'chosen_actions': np.array(chosen_actions),
        'variance_across_actions': np.array(variance_across_actions),
        'cosine_sim_across_actions': np.array(cosine_sim_across_actions),
        'mse_chosen_action': np.array(mse_chosen_action),
    }
    return result

# ============================================================
#  Aggregate & Analyze
# ============================================================

def aggregate_results(all_results):
    """Aggregate across seeds and compute summary metrics."""
    n_seeds = len(all_results)
    cycles = all_results[0]['cycles']

    # 1. Prediction errors per action (average over seeds)
    pred_errors_by_action = {a: [] for a in range(N_ACTIONS)}
    for r in all_results:
        for a in range(N_ACTIONS):
            pred_errors_by_action[a].append(r['pred_errors'][a])

    # 2. Variance across actions (mean ± std over seeds)
    var_all = np.array([r['variance_across_actions'] for r in all_results])
    var_mean = np.mean(var_all, axis=0)
    var_std = np.std(var_all, axis=0)

    # 3. Cosine similarity (mean ± std over seeds)
    cos_all = np.array([r['cosine_sim_across_actions'] for r in all_results])
    cos_mean = np.mean(cos_all, axis=0)
    cos_std = np.std(cos_all, axis=0)

    # 4. MSE for chosen action (mean ± std over seeds)
    mse_all = np.array([r['mse_chosen_action'] for r in all_results])
    mse_mean = np.mean(mse_all, axis=0)
    mse_std = np.std(mse_all, axis=0)

    # 5. Summary statistics
    # Average prediction error per action (over all cycles and seeds)
    avg_error_per_action = {}
    for a in range(N_ACTIONS):
        all_errors = np.concatenate([r['pred_errors'][a] for r in all_results])
        avg_error_per_action[a] = {
            'mean': np.mean(all_errors),
            'std': np.std(all_errors),
        }

    # Global metrics
    global_variance_mean = np.mean(var_mean)
    global_cosine_mean = np.mean(cos_mean)
    global_mse_mean = np.mean(mse_mean)

    # Trend: linear regression on MSE to see if it decreases
    x = np.arange(cycles)
    if len(mse_mean) > 2:
        slope = np.polyfit(x, mse_mean, 1)[0]
        mse_trend = 'decreasing' if slope < 0 else 'increasing' if slope > 0 else 'stable'
    else:
        mse_trend = 'unknown'

    summary = {
        'n_seeds': n_seeds,
        'cycles': cycles,
        'global_variance_mean': global_variance_mean,
        'global_cosine_mean': global_cosine_mean,
        'global_mse_mean': global_mse_mean,
        'mse_trend': mse_trend,
        'avg_error_per_action': avg_error_per_action,
        'var_mean': var_mean.tolist(),
        'var_std': var_std.tolist(),
        'cos_mean': cos_mean.tolist(),
        'cos_std': cos_std.tolist(),
        'mse_mean': mse_mean.tolist(),
        'mse_std': mse_std.tolist(),
    }
    return summary

# ============================================================
#  Plotting
# ============================================================

def plot_diagnostics(summary, all_results, out_dir):
    """Generate diagnostic plots."""
    cycles = summary['cycles']
    var_mean = np.array(summary['var_mean'])
    var_std = np.array(summary['var_std'])
    cos_mean = np.array(summary['cos_mean'])
    cos_std = np.array(summary['cos_std'])
    mse_mean = np.array(summary['mse_mean'])
    mse_std = np.array(summary['mse_std'])

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Variance across actions over time
    ax = axes[0, 0]
    x = np.arange(cycles)
    ax.plot(x, var_mean, 'b-', label='Mean')
    ax.fill_between(x, var_mean - var_std, var_mean + var_std, alpha=0.3, color='b')
    ax.set_xlabel('Cycle')
    ax.set_ylabel('Variance (across action predictions)')
    ax.set_title('1. Prediction Variance Across Actions')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 2. Cosine similarity across actions over time
    ax = axes[0, 1]
    ax.plot(x, cos_mean, 'g-', label='Mean')
    ax.fill_between(x, cos_mean - cos_std, cos_mean + cos_std, alpha=0.3, color='g')
    ax.set_xlabel('Cycle')
    ax.set_ylabel('Cosine Similarity')
    ax.set_title('2. Cosine Similarity Across Predictions')
    ax.axhline(0.9, color='r', linestyle='--', alpha=0.5, label='Collapse threshold (0.9)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 3. MSE for chosen action over time
    ax = axes[1, 0]
    ax.plot(x, mse_mean, 'r-', label='Mean')
    ax.fill_between(x, mse_mean - mse_std, mse_mean + mse_std, alpha=0.3, color='r')
    ax.set_xlabel('Cycle')
    ax.set_ylabel('MSE (predicted vs actual)')
    ax.set_title('3. Prediction Accuracy (Chosen Action)')
    # Trend line
    slope = np.polyfit(x, mse_mean, 1)[0]
    trend_line = np.polyval([slope, np.mean(mse_mean) - slope * cycles/2], x)
    ax.plot(x, trend_line, 'k--', alpha=0.5, label=f'Trend: {slope:.4f}')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 4. Boxplot: Prediction errors per action (all cycles, all seeds)
    ax = axes[1, 1]
    all_errors = []
    for a in range(N_ACTIONS):
        errors = []
        for r in all_results:
            errors.extend(r['pred_errors'][a])
        all_errors.append(errors)
    bp = ax.boxplot(all_errors, labels=[f'A{a}' for a in range(N_ACTIONS)])
    ax.set_xlabel('Action')
    ax.set_ylabel('Prediction Error (L2 norm)')
    ax.set_title('4. Prediction Error Distribution per Action')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plot_file = out_dir / 'diagnostic_plots.png'
    plt.savefig(plot_file, dpi=150)
    plt.close()

    return plot_file

# ============================================================
#  Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='EXP-001C: World Model Diagnostics')
    parser.add_argument('--quick', action='store_true', help='Quick mode: 1 seed, 100 cycles')
    parser.add_argument('--seed', type=int, default=None, help='Run a single seed (default: use all seeds)')
    parser.add_argument('--cycles', type=int, default=DEFAULT_CYCLES, help='Cycles per run')
    parser.add_argument('--seeds', type=int, default=DEFAULT_SEEDS, help='Number of seeds')
    args = parser.parse_args()

    # Determine seeds and cycles
    if args.quick:
        seeds = [42]
        cycles = 100
        mode = 'quick'
    elif args.seed is not None:
        seeds = [args.seed]
        cycles = args.cycles
        mode = f'seed{args.seed}'
    else:
        seeds = [DEFAULT_SEED_START + i for i in range(args.seeds)]
        cycles = args.cycles
        mode = 'full'

    print("=" * 60)
    print("EXP-001C: World Model Diagnostics")
    print(f"Seeds: {seeds}")
    print(f"Cycles: {cycles}")
    print(f"Mode: {mode}")
    print("=" * 60)

    # Run diagnostics
    all_results = []
    for seed in tqdm(seeds, desc="Running seeds"):
        result = run_diagnostic(seed, cycles)
        all_results.append(result)

    # Aggregate
    summary = aggregate_results(all_results)
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"Seeds: {summary['n_seeds']}, Cycles: {summary['cycles']}")
    print(f"Global variance across actions: {summary['global_variance_mean']:.4f}")
    print(f"Global cosine similarity: {summary['global_cosine_mean']:.4f}")
    print(f"Global MSE (pred vs actual): {summary['global_mse_mean']:.4f}")
    print(f"MSE trend: {summary['mse_trend']}")
    print("\nAverage prediction error per action:")
    for a in range(N_ACTIONS):
        info = summary['avg_error_per_action'][a]
        print(f"  A{a}: {info['mean']:.4f} ± {info['std']:.4f}")

    # --- Interpretation ---
    print("\n" + "=" * 60)
    print("INTERPRETATION")
    print("=" * 60)

    verdict = {}

    # 1. Variance check
    if summary['global_variance_mean'] < 0.01:
        verdict['variance'] = "❌ LOW: Predictions for all actions are nearly identical."
    elif summary['global_variance_mean'] < 0.05:
        verdict['variance'] = "🟡 MODERATE: Some distinction, but weak."
    else:
        verdict['variance'] = "✅ GOOD: Predictions differ significantly across actions."

    # 2. Cosine similarity check
    if summary['global_cosine_mean'] > 0.9:
        verdict['cosine'] = "❌ COLLAPSE: All actions predicted as almost the same state."
    elif summary['global_cosine_mean'] > 0.7:
        verdict['cosine'] = "🟡 HIGH SIMILARITY: Predictions are similar but not identical."
    else:
        verdict['cosine'] = "✅ LOW SIMILARITY: Predictions are well-differentiated."

    # 3. MSE accuracy
    if summary['global_mse_mean'] > 1.0:
        verdict['mse'] = "❌ HIGH ERROR: Model predictions are very inaccurate."
    elif summary['global_mse_mean'] > 0.5:
        verdict['mse'] = "🟡 MODERATE ERROR: Model is learning but not yet accurate."
    else:
        verdict['mse'] = "✅ LOW ERROR: Model predictions are reasonably accurate."

    # 4. Trend
    if summary['mse_trend'] == 'decreasing':
        verdict['trend'] = "✅ LEARNING: Error decreases over time."
    elif summary['mse_trend'] == 'increasing':
        verdict['trend'] = "❌ DIVERGING: Error increases over time (bad)."
    else:
        verdict['trend'] = "🟡 STABLE: Error does not improve significantly."

    for key, msg in verdict.items():
        print(f"  {key}: {msg}")

    # Overall verdict
    if all('✅' in v for v in verdict.values()):
        overall = "✅ World model is healthy. Curiosity signal is reliable."
    elif any('❌' in v for v in verdict.values()):
        overall = "❌ World model has critical issues. Curiosity will be weak."
    else:
        overall = "🟡 World model is functional but needs improvement."

    print(f"\nOverall verdict: {overall}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"exp_001c_{timestamp}")
    out_dir.mkdir(exist_ok=True)

    # Save summary JSON
    with open(out_dir / 'diagnostic_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    # Save full raw results (for deeper analysis)
    raw_out = []
    for r in all_results:
        raw_out.append({
            'seed': r['seed'],
            'cycles': r['cycles'],
            'variance_across_actions': r['variance_across_actions'].tolist(),
            'cosine_sim_across_actions': r['cosine_sim_across_actions'].tolist(),
            'mse_chosen_action': r['mse_chosen_action'].tolist(),
            'pred_errors': {a: r['pred_errors'][a].tolist() for a in range(N_ACTIONS)}
        })
    with open(out_dir / 'raw_data.json', 'w') as f:
        json.dump(raw_out, f, indent=2)

    # Generate plots
    plot_file = plot_diagnostics(summary, all_results, out_dir)
    print(f"\nPlots saved to {plot_file}")
    print(f"Results saved to {out_dir}/")
    print("=" * 60)

if __name__ == "__main__":
    main()