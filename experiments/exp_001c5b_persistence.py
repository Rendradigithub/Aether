"""
EXP-001C.5b: Verify P-00b (Structural Persistence)
====================================================
- Run environment with integrator dynamics.
- Measure persistence index and accumulation effect.
- Compare with previous environment (v0.23a) to ensure persistence improves.
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
from environment_v023b import EnvironmentV023b

def run_verification(seed=42):
    env = EnvironmentV023b(seed=seed)

    print("=" * 60)
    print("EXP-001C.5b: P-00b Verification (Structural Persistence)")
    print("=" * 60)

    # 1. P-00a check (should still pass)
    p00a = env.check_p00a()
    print(f"P-00a (Action Separability): {'✅ PASS' if p00a else '❌ FAIL'}")
    print(f"  Operator separability: {env.get_operator_separability():.4f}")
    print(f"  Reality separability: {env.get_reality_separability():.4f}")
    print(f"  Mean operator similarity: {env.get_operator_diversity()['mean_similarity']:.4f}")

    # 2. P-00b check
    p00b = env.check_p00b(threshold_persistence=0.5, threshold_accumulation=0.3)
    print(f"\nP-00b (Structural Persistence): {'✅ PASS' if p00b else '❌ FAIL'}")
    print(f"  Persistence index: {env.get_persistence_index(100):.4f} (need > 0.5)")
    print(f"  Accumulation effect: {env.get_accumulation_effect(100, 5):.4f} (need > 0.3)")

    # 3. Visualize persistence: run a single action repeatedly and see state drift
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 3a. Single action repeated 200 times
    env.reset()
    single_action = 0
    states = [env.state.copy()]
    for _ in range(200):
        s = env.step(single_action)
        states.append(s)
    states = np.array(states)

    ax = axes[0, 0]
    for i in range(min(10, env.state_dim)):
        ax.plot(states[:, i], alpha=0.7, label=f'dim{i+1}')
    ax.set_title(f'Repeated Action {single_action} (200 steps)')
    ax.set_xlabel('Step')
    ax.set_ylabel('Activation')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)

    # 3b. Compare two different action sequences (accumulation effect)
    env.reset()
    seq1 = np.random.randint(0, env.n_actions, size=100)
    seq2 = np.random.randint(0, env.n_actions, size=100)
    # but ensure they are different
    while np.array_equal(seq1, seq2):
        seq2 = np.random.randint(0, env.n_actions, size=100)

    env1 = EnvironmentV023b(seed=999)
    env1.W = [w.copy() for w in env.W]
    env1.b = [b.copy() for b in env.b]
    env1.state = np.zeros(env.state_dim)

    env2 = EnvironmentV023b(seed=888)
    env2.W = [w.copy() for w in env.W]
    env2.b = [b.copy() for b in env.b]
    env2.state = np.zeros(env.state_dim)

    states1 = [env1.state.copy()]
    for a in seq1:
        states1.append(env1.step(a))
    states2 = [env2.state.copy()]
    for a in seq2:
        states2.append(env2.step(a))

    states1 = np.array(states1)
    states2 = np.array(states2)

    ax = axes[0, 1]
    # Plot first dimension of each sequence
    ax.plot(states1[:, 0], 'b-', label='Sequence 1 (dim0)', alpha=0.7)
    ax.plot(states2[:, 0], 'r-', label='Sequence 2 (dim0)', alpha=0.7)
    ax.set_title('Accumulation Effect: Two Different Action Sequences')
    ax.set_xlabel('Step')
    ax.set_ylabel('Dimension 0')
    ax.grid(True, alpha=0.3)
    ax.legend()

    # 3c. Distribution of final states after many random sequences
    n_seq = 20
    final_states = []
    env_base = EnvironmentV023b(seed=42)
    for i in range(n_seq):
        e = EnvironmentV023b(seed=42 + i*100)
        e.W = [w.copy() for w in env_base.W]
        e.b = [b.copy() for b in env_base.b]
        e.state = np.zeros(env_base.state_dim)
        for _ in range(100):
            e.step(np.random.randint(0, e.n_actions))
        final_states.append(e.state.copy())
    final_states = np.array(final_states)

    ax = axes[1, 0]
    # Plot first 5 dims as scatter
    for i in range(min(5, env.state_dim)):
        ax.scatter(np.arange(n_seq), final_states[:, i], alpha=0.6, label=f'dim{i+1}')
    ax.set_title('Final States from 20 Random Sequences')
    ax.set_xlabel('Sequence Index')
    ax.set_ylabel('Activation')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)

    # 3d. Persistence index over time (cumulative displacement)
    env = EnvironmentV023b(seed=42)
    steps = 200
    displacements = []
    initial = env.state.copy()
    for t in range(steps):
        env.step(np.random.randint(0, env.n_actions))
        displacements.append(np.linalg.norm(env.state - initial))

    ax = axes[1, 1]
    ax.plot(displacements, 'b-', label='Displacement from initial')
    ax.axhline(0.5, color='r', linestyle='--', label='Threshold (0.5)')
    ax.set_title('Persistence Index Over Time')
    ax.set_xlabel('Step')
    ax.set_ylabel('Displacement (L2 norm)')
    ax.grid(True, alpha=0.3)
    ax.legend()

    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"exp_001c5b_{timestamp}")
    out_dir.mkdir(exist_ok=True)
    plt.savefig(out_dir / 'p00b_verification.png', dpi=150)
    plt.close()

    print(f"\nPlots saved to {out_dir / 'p00b_verification.png'}")
    print("=" * 60)

    return env.diagnostic_summary()

if __name__ == "__main__":
    summary = run_verification()
    print("\n=== Full Diagnostic Summary ===")
    for key, val in summary.items():
        print(f"{key:>25}: {val}")