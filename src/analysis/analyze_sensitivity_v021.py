"""
Analyze EXP-001A v0.21.0 results
- Handles autocorrelation as dict
- Generates sensitivity matrix, heatmap, pre-registration check
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys

def load_results(exp_dir):
    summary_file = Path(exp_dir) / "summary.json"
    with open(summary_file, 'r') as f:
        data = json.load(f)
    return pd.DataFrame(data)

def compute_sensitivity_matrix(df):
    metrics = ['avg_reward', 'entropy', 'autocorrelation_1', 'reversal_rate', 'persistence_duration']
    params = ['reward', 'curiosity', 'persistence', 'noise']
    
    sens = {}
    for param in params:
        sub = df[df['sweep_param'] == param]
        if sub.empty:
            continue
        corrs = {}
        for metric in metrics:
            if metric not in sub.columns:
                # For autocorrelation, extract from dict
                if metric == 'autocorrelation_1':
                    if 'autocorrelation' in sub.columns:
                        vals = sub['autocorrelation'].apply(lambda x: x.get('1', np.nan) if isinstance(x, dict) else np.nan)
                    else:
                        continue
                else:
                    continue
            else:
                vals = sub[metric]
            # Drop NaN
            vals = vals.dropna()
            if len(vals) < 2:
                corrs[metric] = np.nan
                continue
            corr = sub.loc[vals.index, 'sweep_value'].corr(vals)
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

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_sensitivity_v021.py <exp_dir>")
        sys.exit(1)
    exp_dir = sys.argv[1]
    
    df = load_results(exp_dir)
    print(f"Loaded {len(df)} runs.")
    
    sens = compute_sensitivity_matrix(df)
    print("\n=== Sensitivity Matrix (Correlation Coeffs) ===\n")
    print(sens.round(3))
    
    print("\n=== Color-coded Sensitivity Matrix ===")
    for param in sens.index:
        row = sens.loc[param]
        colored = [f"{color_code(c)} {c:.2f}" if not np.isnan(c) else "⚪ nan" for c in row]
        print(f"{param:>12}: " + " | ".join(colored))
    
    # Pre-registration check
    expected_file = Path(exp_dir).parent / "pre_registration.json"
    if expected_file.exists():
        with open(expected_file, 'r') as f:
            expected = json.load(f)
        print("\n=== Pre-registration Check ===")
        for param in expected:
            for metric, pred in expected[param].items():
                if param in sens.index and metric in sens.columns:
                    obs = sens.loc[param, metric]
                    if not np.isnan(obs):
                        diff = obs - pred
                        print(f"{param}:{metric} | Expected: {pred:.2f} | Observed: {obs:.2f} | Diff: {diff:.2f}")
    
    # Heatmap
    plt.figure(figsize=(10,6))
    sns.heatmap(sens, annot=True, cmap='coolwarm', center=0, fmt='.2f')
    plt.title("Decision Sensitivity Matrix (v0.21.0)")
    plt.tight_layout()
    plt.savefig(Path(exp_dir) / "sensitivity_matrix.png")
    print(f"\nSaved heatmap to {Path(exp_dir) / 'sensitivity_matrix.png'}")

if __name__ == "__main__":
    main()