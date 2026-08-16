#!/usr/bin/env python3
"""
Minimal Aether experiment to trace state flow through one cognitive cycle.
Uses the modular AetherCognitiveCore from src.aether.orchestrator.

Instruments the active runtime to observe:
1. stimulus_radial (fixed)
2. current_state before generation
3. current_state after cycle
4. reward calculation
5. radial similarity
6. world model prediction error and buffer state
"""

import sys
import numpy as np
from pathlib import Path

# Import from the modular orchestrator
from src.aether.orchestrator import AetherCognitiveCore


def run_single_cycle_experiment(stimulus_path):
    """Run exactly one cognitive cycle with instrumentation."""

    print("="*60)
    print("AETHER v0.20.0 SINGLE-CYCLE EXPERIMENT")
    print("(Using modular orchestrator)")
    print("="*60)

    # Initialize core with modular orchestrator
    print("\n[PHASE: Initialization]")
    core = AetherCognitiveCore(stimulus_source=stimulus_path, quiet=True)

    print(f"stimulus_radial shape: {core.stimulus_radial.shape if core.stimulus_radial is not None else 'None'}")
    print(f"stimulus_radial[:5]: {core.stimulus_radial[:5] if core.stimulus_radial is not None else 'None'}")
    print(f"current_state shape: {core.current_state.shape if core.current_state is not None else 'None'}")
    print(f"current_state[:5]: {core.current_state[:5] if core.current_state is not None else 'None'}")
    print(f"Are they identical? {np.array_equal(core.stimulus_radial, core.current_state) if core.current_state is not None else 'N/A'}")

    # Capture state before cycle
    print("\n[PHASE: Before Cycle 1]")
    state_before = core.current_state.copy() if core.current_state is not None else None
    print(f"current_state before cycle: {state_before[:5] if state_before is not None else 'None'}")

    # Run one cycle
    print("\n[PHASE: Executing Cycle 1]")
    art, reward, radial_sim, pattern = core.step()

    # Capture state after cycle
    print("\n[PHASE: After Cycle 1]")
    state_after = core.current_state.copy() if core.current_state is not None else None
    print(f"current_state after cycle: {state_after[:5] if state_after is not None else 'None'}")

    # Verify state evolution
    print("\n[VERIFICATION]")
    print(f"Pattern generated: {pattern}")
    print(f"Reward: {reward:.4f}")
    print(f"Radial similarity: {radial_sim:.4f}")

    if state_before is not None and state_after is not None:
        print(f"\nState changed? {not np.array_equal(state_before, state_after)}")
        if not np.array_equal(state_before, state_after):
            diff_norm = np.linalg.norm(state_after - state_before)
            print(f"State difference norm: {diff_norm:.4f}")
            print(f"State before[:5]: {state_before[:5]}")
            print(f"State after[:5]: {state_after[:5]}")

        # Verify stimulus_radial unchanged
        print(f"\nstimulus_radial unchanged? {np.array_equal(core.stimulus_radial, state_before)}")

    # Check world model state
    print(f"\nWorld model prediction error: {core.world_model.prediction_error:.4f}")
    print(f"World model buffer size: {len(core.world_model.buffer)}")

    print("\n" + "="*60)
    print("EXPERIMENT COMPLETE")
    print("="*60)

    return {
        'stimulus_radial': core.stimulus_radial,
        'state_before': state_before,
        'state_after': state_after,
        'pattern': pattern,
        'reward': reward,
        'art': art,
        'world_model_error': core.world_model.prediction_error
    }


if __name__ == "__main__":
    stimulus_file = Path(__file__).parent / "test_stimulus.txt"
    if not stimulus_file.exists():
        print(f"Error: {stimulus_file} not found")
        sys.exit(1)

    results = run_single_cycle_experiment(str(stimulus_file))
