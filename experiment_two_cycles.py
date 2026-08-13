#!/usr/bin/env python3
"""
Two-cycle experiment to trace temporal continuity across multiple cycles.
Verifies that current_state continues to evolve and is not reset.
"""

import sys
import runpy
import numpy as np
from pathlib import Path

def run_two_cycle_experiment(stimulus_path):
    """Run exactly TWO cognitive cycles to trace temporal continuity."""

    print("="*60)
    print("AETHER v0.20.0 TWO-CYCLE TEMPORAL CONTINUITY EXPERIMENT")
    print("="*60)

    # Load the module
    archive_path = Path(__file__).parent / "archive" / "versions" / "aether.0.20.0.py"
    aether_module = runpy.run_path(str(archive_path))
    AetherCognitiveCore = aether_module['AetherCognitiveCore']

    # Initialize
    print("\n[INITIALIZATION]")
    core = AetherCognitiveCore(stimulus_source=stimulus_path, quiet=True)

    stimulus_initial = core.stimulus_radial.copy()
    state_init = core.current_state.copy()

    print(f"stimulus_radial: {stimulus_initial[:5]}")
    print(f"current_state (init): {state_init[:5]}")
    print(f"Identical at init? {np.array_equal(stimulus_initial, state_init)}")

    # === CYCLE 1 ===
    print("\n" + "="*60)
    print("CYCLE 1")
    print("="*60)

    state_before_c1 = core.current_state.copy()
    print(f"current_state before cycle 1: {state_before_c1[:5]}")

    art1, reward1, radial_sim1, pattern1 = core.step()

    state_after_c1 = core.current_state.copy()
    print(f"current_state after cycle 1: {state_after_c1[:5]}")
    print(f"Pattern: {pattern1}, Reward: {reward1:.4f}")
    print(f"State changed in cycle 1? {not np.array_equal(state_before_c1, state_after_c1)}")
    print(f"World model error: {core.world_model.prediction_error:.4f}")

    # === CYCLE 2 ===
    print("\n" + "="*60)
    print("CYCLE 2")
    print("="*60)

    state_before_c2 = core.current_state.copy()
    print(f"current_state before cycle 2: {state_before_c2[:5]}")
    print(f"Is this the same as state after cycle 1? {np.array_equal(state_before_c2, state_after_c1)}")

    art2, reward2, radial_sim2, pattern2 = core.step()

    state_after_c2 = core.current_state.copy()
    print(f"current_state after cycle 2: {state_after_c2[:5]}")
    print(f"Pattern: {pattern2}, Reward: {reward2:.4f}")
    print(f"State changed in cycle 2? {not np.array_equal(state_before_c2, state_after_c2)}")
    print(f"World model error: {core.world_model.prediction_error:.4f}")
    print(f"World model buffer size: {len(core.world_model.buffer)}")

    # === VERIFICATION ===
    print("\n" + "="*60)
    print("TEMPORAL CONTINUITY VERIFICATION")
    print("="*60)

    print(f"\nstimulus_radial unchanged across both cycles? {np.array_equal(stimulus_initial, core.stimulus_radial)}")
    print(f"current_state evolved from init to cycle 1? {not np.array_equal(state_init, state_after_c1)}")
    print(f"current_state evolved from cycle 1 to cycle 2? {not np.array_equal(state_after_c1, state_after_c2)}")
    print(f"current_state carried forward between cycles? {np.array_equal(state_after_c1, state_before_c2)}")

    print(f"\nState trajectory:")
    print(f"  Init:        {state_init[:5]}")
    print(f"  After C1:    {state_after_c1[:5]}")
    print(f"  After C2:    {state_after_c2[:5]}")

    print(f"\nDifference norms:")
    print(f"  Init → C1:   {np.linalg.norm(state_after_c1 - state_init):.4f}")
    print(f"  C1 → C2:     {np.linalg.norm(state_after_c2 - state_after_c1):.4f}")

    print("\n" + "="*60)
    print("EXPERIMENT COMPLETE")
    print("="*60)

if __name__ == "__main__":
    stimulus_file = Path(__file__).parent / "test_stimulus.txt"
    run_two_cycle_experiment(str(stimulus_file))
