"""
Analyze EXP-001A v0.22.0 results
- Sensitivity Matrix (correlation between sweep params and metrics)
- Utility Decomposition: average contribution of reward, curiosity, persistence, energy, noise
- Heatmap visualization
- Pre-registration check (if available)
- Stacked bar chart of utility components
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
from collections import defaultdict

# ----------------------------------------------------------------------
#  Helper Functions
# ----------------------------------------------------------------------

def load_results(exp_dir):
    """Load summary.json from experiment directory."""
    summary_file = Path(exp_dir) / "summary.json"
    if not summary_file.exists():
        print(f"ERROR: {summary_file} not found.")
        sys.exit(1)
    with open(summary_file, 'r') as f:
        data = json.load(f)
    return pd.DataFrame(data)

def extract_autocorr(df, lag=1):
    """Extract autocorrelation for a given lag from the autocorrelation dict."""
    if 'autocorrelation' not in df.columns:
        return pd.Series([np.nan] * len(df), index=df.index)
    vals = df['autocorrelation'].apply(
        lambda x: x.get(str(lag), np.nan) if isinstance(x, dict) else np.nan
    )
    return vals

def compute_sensitivity_matrix(df):
    """
    Compute correlation between sweep_value and each metric for each sweep_param.
    Returns DataFrame (params as index, metrics as columns).
    """
    metrics = ['avg_reward', 'entropy', 'reversal_rate', 'persistence_duration']
    # Add autocorrelation_1 explicitly
    params = ['reward', 'curiosity', 'persistence', 'noise']
    
    # Pre-extract autocorrelation_1
    df['autocorrelation_1'] = extract_autocorr(df, lag=1)
    
    all_metrics = metrics + ['autocorrelation_1']
    
    sens = {}
    for param in params:
        sub = df[df['sweep_param'] == param]
        if sub.empty:
            continue
        corrs = {}
        for metric in all_metrics:
            if metric not in sub.columns:
                continue
            vals = sub[metric].dropna()
            if len(vals) < 2:
                corrs[metric] = np.nan
                continue
            # Align indices with sweep_value
            idx = vals.index
            sweep_vals = sub.loc[idx, 'sweep_value']
            corr = sweep_vals.corr(vals)
            corrs[metric] = corr
        sens[param] = corrs
    return pd.DataFrame(sens).T

def color_code(val):
    if np.isnan(val):
        return '⚪'
    if val > 0.3:
        return '🟢'
    elif val < -0.3:
        return '🔴'
    else:
        return '⚪'

def compute_avg_utility_components(df):
    """
    Compute average utility component contributions (weighted u_*) across all runs,
    grouped by sweep_param and sweep_value.
    Also compute overall average.
    """
    results = []
    for _, row in df.iterrows():
        comps = row.get('average_utility_components', {})
        if comps:
            results.append({
                'sweep_param': row['sweep_param'],
                'sweep_value': row['sweep_value'],
                'u_reward': comps.get('u_reward', 0),
                'u_curiosity': comps.get('u_curiosity', 0),
                'u_persistence': comps.get('u_persistence', 0),
                'u_energy': comps.get('u_energy', 0),
                'u_noise': comps.get('u_noise', 0),
            })
    return pd.DataFrame(results)

# ----------------------------------------------------------------------
#  Main Analysis
# ----------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_sensitivity_v022.py <exp_dir>")
        sys.exit(1)
    exp_dir = sys.argv[1]
    
    df = load_results(exp_dir)
    print(f"Loaded {len(df)} runs from {exp_dir}")
    
    # --- 1. Sensitivity Matrix ---
    sens = compute_sensitivity_matrix(df)
    print("\n" + "="*60)
    print("SENSITIVITY MATRIX (Correlation Coeffs)")
    print("="*60)
    print(sens.round(3))
    
    print("\n" + "="*60)
    print("COLOR-CODED SENSITIVITY MATRIX")
    print("="*60)
    for param in sens.index:
        row = sens.loc[param]
        colored = [f"{color_code(c)} {c:.2f}" if not np.isnan(c) else "⚪ nan" for c in row]
        print(f"{param:>12}: " + " | ".join(colored))
    
    # --- 2. Utility Decomposition Analysis ---
    print("\n" + "="*60)
    print("UTILITY DECOMPOSITION - AVERAGE COMPONENT CONTRIBUTIONS")
    print("="*60)
    
    decomp_df = compute_avg_utility_components(df)
    if not decomp_df.empty:
        # Overall average across all runs
        overall_avg = decomp_df[['u_reward', 'u_curiosity', 'u_persistence', 'u_energy', 'u_noise']].mean()
        print("\nOverall average (all runs):")
        for key, val in overall_avg.items():
            print(f"  {key:>14}: {val:.4f}")
        
        # Grouped by sweep_param to see how each component's contribution changes
        print("\nAverage components per sweep parameter (at sweep_value=1.0 baseline):")
        for param in ['reward', 'curiosity', 'persistence', 'noise']:
            sub = decomp_df[decomp_df['sweep_param'] == param]
            if sub.empty:
                continue
            # Get baseline (sweep_value == 1.0) if exists, else first value
            baseline = sub[sub['sweep_value'] == 1.0]
            if baseline.empty:
                baseline = sub[sub['sweep_value'] == sub['sweep_value'].min()]
            avg = baseline[['u_reward', 'u_curiosity', 'u_persistence', 'u_energy', 'u_noise']].mean()
            print(f"\n  {param} (at value={baseline['sweep_value'].iloc[0]}):")
            for key, val in avg.items():
                print(f"    {key:>14}: {val:.4f}")
    
    # --- 3. Pre-registration Check (if available) ---
    expected_file = Path(exp_dir).parent / "pre_registration.json"
    if expected_file.exists():
        with open(expected_file, 'r') as f:
            expected = json.load(f)
        print("\n" + "="*60)
        print("PRE-REGISTRATION CHECK")
        print("="*60)
        for param in expected:
            for metric, pred in expected[param].items():
                if param in sens.index and metric in sens.columns:
                    obs = sens.loc[param, metric]
                    if not np.isnan(obs):
                        diff = obs - pred
                        status = "✅" if abs(diff) < 0.2 else "⚠️"
                        print(f"{status} {param}:{metric} | Expected: {pred:.2f} | Observed: {obs:.2f} | Diff: {diff:.2f}")
    
    # --- 4. Visualizations ---
    print("\n" + "="*60)
    print("GENERATING VISUALIZATIONS")
    print("="*60)
    
    # 4a. Heatmap: Sensitivity Matrix
    plt.figure(figsize=(10, 6))
    sns.heatmap(sens, annot=True, cmap='coolwarm', center=0, fmt='.2f', 
                linewidths=0.5, cbar_kws={'label': 'Correlation'})
    plt.title("Decision Sensitivity Matrix (v0.22.0)", fontsize=14)
    plt.tight_layout()
    heatmap_file = Path(exp_dir) / "sensitivity_matrix.png"
    plt.savefig(heatmap_file, dpi=150)
    print(f"  Saved heatmap: {heatmap_file}")
    plt.close()
    
    # 4b. Bar chart: Utility Decomposition (overall average)
    if not decomp_df.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        overall = decomp_df[['u_reward', 'u_curiosity', 'u_persistence', 'u_energy', 'u_noise']].mean()
        colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#95a5a6']
        bars = ax.bar(overall.index, overall.values, color=colors, edgecolor='black', linewidth=1)
        ax.set_ylabel('Average Contribution')
        ax.set_title('Average Utility Component Contributions (All Runs)', fontsize=14)
        ax.axhline(0, color='black', linestyle='-', linewidth=0.5)
        # Add value labels on bars
        for bar, val in zip(bars, overall.values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{val:.3f}', ha='center', va='bottom', fontsize=9)
        plt.tight_layout()
        bar_file = Path(exp_dir) / "utility_decomposition_overall.png"
        plt.savefig(bar_file, dpi=150)
        print(f"  Saved bar chart: {bar_file}")
        plt.close()
        
        # 4c. Stacked bar chart per sweep parameter (at baseline)
        # Show how decomposition changes when each parameter is at 1.0
        fig, ax = plt.subplots(figsize=(12, 6))
        params = ['reward', 'curiosity', 'persistence', 'noise']
        baseline_comps = {}
        for param in params:
            sub = decomp_df[decomp_df['sweep_param'] == param]
            if sub.empty:
                continue
            baseline = sub[sub['sweep_value'] == 1.0]
            if baseline.empty:
                baseline = sub[sub['sweep_value'] == sub['sweep_value'].min()]
            avg = baseline[['u_reward', 'u_curiosity', 'u_persistence', 'u_energy', 'u_noise']].mean()
            baseline_comps[param] = avg
        
        if baseline_comps:
            df_plot = pd.DataFrame(baseline_comps).T
            df_plot.plot(kind='bar', stacked=True, ax=ax, color=colors, edgecolor='black', linewidth=0.5)
            ax.set_xlabel('Sweep Parameter (at value=1.0)')
            ax.set_ylabel('Average Utility Contribution')
            ax.set_title('Utility Decomposition by Sweep Parameter (Baseline)', fontsize=14)
            ax.legend(loc='upper right')
            ax.axhline(0, color='black', linestyle='-', linewidth=0.5)
            plt.tight_layout()
            stacked_file = Path(exp_dir) / "utility_decomposition_stacked.png"
            plt.savefig(stacked_file, dpi=150)
            print(f"  Saved stacked chart: {stacked_file}")
            plt.close()
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()