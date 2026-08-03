"""
Analyze EXP-001A results:
- Generate Sensitivity Matrix (color-coded)
- Regression coefficients for each metric
- Compare expected vs observed (for pre-registration check)
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from pathlib import Path

def load_results(exp_dir):
    """Load summary from experiment directory."""
    summary_file = Path(exp_dir) / "summary.json"
    with open(summary_file, 'r') as f:
        data = json.load(f)
    return pd.DataFrame(data)

def compute_sensitivity_matrix(df):
    """
    Compute regression coefficients for each sweep parameter vs each metric.
    Returns a DataFrame with params as index and metrics as columns.
    """
    metrics = ['avg_reward', 'entropy', 'autocorrelation_1', 'reversal_rate', 'persistence_duration']
    params = ['reward', 'curiosity', 'persistence', 'noise']
    
    # Filter only baseline (sweep_value=1.0) for comparison? Actually we need all.
    # We'll compute correlation between sweep_value and metric per param.
    sens = {}
    for param in params:
        sub = df[df['sweep_param'] == param]
        if sub.empty:
            continue
        # Compute correlation coefficient
        corrs = {}
        for metric in metrics:
            if metric not in sub.columns:
                continue
            # Use actual metric column names
            col = 'autocorrelation_1' if metric == 'autocorrelation_1' else metric
            if col not in sub.columns:
                continue
            # For autocorrelation, extract from dict
            if col == 'autocorrelation_1':
                vals = sub[col].apply(lambda x: x.get('1', 0) if isinstance(x, dict) else x)
            else:
                vals = sub[col]
            corr = sub['sweep_value'].corr(vals)
            corrs[metric] = corr
        sens[param] = corrs
    
    return pd.DataFrame(sens).T

def color_code(val):
    """Return color based on value magnitude."""
    if val > 0.3:
        return '🟢'
    elif val < -0.3:
        return '🔴'
    else:
        return '⚪'

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python analyze_sensitivity.py <exp_dir>")
        sys.exit(1)
    exp_dir = sys.argv[1]
    
    df = load_results(exp_dir)
    print(f"Loaded {len(df)} runs.")
    
    # Compute sensitivity matrix
    sens = compute_sensitivity_matrix(df)
    print("\n=== Sensitivity Matrix (Correlation Coeffs) ===\n")
    print(sens.round(3))
    
    # Color-coded version
    print("\n=== Color-coded Sensitivity Matrix ===")
    for param in sens.index:
        row = sens.loc[param]
        colored = [f"{color_code(c)} {c:.2f}" for c in row]
        print(f"{param:>12}: " + " | ".join(colored))
    
    # Pre-registration check: compare expected vs observed
    # For each metric, we predicted certain direction.
    # We'll load expected from a pre-reg file if exists.
    expected_file = Path(exp_dir).parent / "pre_registration.json"
    if expected_file.exists():
        with open(expected_file, 'r') as f:
            expected = json.load(f)
        print("\n=== Pre-registration Check ===")
        for param in expected:
            for metric, pred in expected[param].items():
                if param in sens.index and metric in sens.columns:
                    obs = sens.loc[param, metric]
                    diff = obs - pred
                    print(f"{param}:{metric} | Expected: {pred:.2f} | Observed: {obs:.2f} | Diff: {diff:.2f}")
    
    # Optionally plot
    plt.figure(figsize=(10,6))
    sns.heatmap(sens, annot=True, cmap='coolwarm', center=0)
    plt.title("Decision Sensitivity Matrix")
    plt.tight_layout()
    plt.savefig(Path(exp_dir) / "sensitivity_matrix.png")
    print(f"\nSaved heatmap to {Path(exp_dir) / 'sensitivity_matrix.png'}")

if __name__ == "__main__":
    main()