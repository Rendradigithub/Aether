"""
EXP-001C.5 (v0.23): Verify P-00 with new environment.
"""

from environment_v023 import EnvironmentV023
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

def main():
    env = EnvironmentV023(seed=42)

    print("=" * 60)
    print("EXP-001C.5 (v0.23): P-00 Verification")
    print("=" * 60)

    # 1. Operator separability
    op_sep = env.get_operator_separability()
    print(f"Operator separability (Frobenius distance): {op_sep:.4f}")

    # 2. Reality separability
    real_sep = env.get_reality_separability(n_states=20)
    print(f"Reality separability (distance between futures): {real_sep:.4f}")

    # 3. Operator diversity
    div = env.get_operator_diversity()
    print(f"Mean operator similarity (cosine): {div['mean_similarity']:.4f}")

    # 4. Health check
    health = env.is_healthy(threshold_sep=0.5, threshold_sim=0.8)
    print(f"\n--- Health Check ---")
    print(f"  Healthy: {health['healthy']}")
    print(f"  Operator separability: {health['operator_separability']:.4f} (need > 0.5)")
    print(f"  Reality separability: {health['reality_separability']:.4f} (need > 0.5)")
    print(f"  Mean similarity: {health['mean_operator_similarity']:.4f} (need < 0.8)")

    # 5. Visualize: run random actions and show state trajectory
    env.reset()
    states = [env.state.copy()]
    actions = np.random.randint(0, env.n_actions, size=500)
    for a in actions:
        s = env.step(a)
        states.append(s)

    states = np.array(states)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # First 10 dimensions over time
    for i in range(min(10, env.state_dim)):
        axes[0].plot(states[:, i], alpha=0.7, label=f'dim{i+1}')
    axes[0].set_title('State Dimensions Over Time (500 steps)')
    axes[0].set_xlabel('Step')
    axes[0].set_ylabel('Activation')
    axes[0].grid(True, alpha=0.3)

    # Action sequence
    axes[1].plot(actions, '.', alpha=0.3, markersize=3)
    axes[1].set_title('Action Sequence (0-4)')
    axes[1].set_xlabel('Step')
    axes[1].set_ylabel('Action Index')
    axes[1].set_ylim(-0.5, 4.5)
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"exp_001c5_v023_{timestamp}")
    out_dir.mkdir(exist_ok=True)
    plt.savefig(out_dir / 'p00_verification.png', dpi=150)
    plt.close()

    print(f"\nPlots saved to {out_dir / 'p00_verification.png'}")
    print("=" * 60)

if __name__ == "__main__":
    main()