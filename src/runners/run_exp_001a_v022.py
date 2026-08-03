"""
Runner for EXP-001A with Aether v0.22.0
- Uses state-based prediction error curiosity
- Normalized utility components
- Full decomposition logging
- Fixed autocorrelation
"""

import os
import json
import logging
import argparse
from datetime import datetime
import numpy as np
from tqdm import tqdm
from aether_exp_001a_v022 import AetherExp001A_v022

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default experiment parameters
N_ACTIONS = 5
N_FEATURES = 36
CYCLES = 500
SEEDS_PER_CONDITION = 10

# Sweep parameters (multipliers for each component)
SWEEPS = {
    'reward': [0.2, 0.5, 1.0, 2.0, 5.0],
    'curiosity': [0.2, 0.5, 1.0, 2.0, 5.0],
    'persistence': [0.2, 0.5, 1.0, 2.0, 5.0],
    'noise': [0.2, 0.5, 1.0, 2.0, 5.0],
}

def generate_stimulus(cycle: int, seed: int) -> tuple:
    """
    Generate synthetic state and action-specific rewards.
    State: 36-dim random normal with slight temporal correlation.
    Rewards: each action corresponds to a phase preference, cycles slowly.
    """
    rng = np.random.default_rng(seed + cycle)
    # State: random walk with small drift
    base = np.sin(np.linspace(0, 2*np.pi, N_FEATURES) + cycle / 50.0) * 0.5
    state = base + 0.3 * rng.normal(size=N_FEATURES)
    
    # Action rewards: each action has a preferred phase
    phase = cycle / 50.0 * 2 * np.pi
    action_phases = np.linspace(0, 2*np.pi, N_ACTIONS, endpoint=False)
    rewards = 0.5 + 0.5 * np.cos(action_phases - phase)
    rewards += 0.1 * rng.normal(size=N_ACTIONS)
    rewards = np.clip(rewards, 0.0, 1.0)
    return state, rewards

def run_single_experiment(seed: int, sweep_param: str, sweep_value: float) -> dict:
    """
    Run one agent with given seed and sweep parameter.
    Returns summary dictionary.
    """
    # Build weight kwargs
    weights = {
        'reward_weight': sweep_value if sweep_param == 'reward' else 1.0,
        'curiosity_weight': sweep_value if sweep_param == 'curiosity' else 1.0,
        'persistence_weight': sweep_value if sweep_param == 'persistence' else 1.0,
        'noise_scale': sweep_value if sweep_param == 'noise' else 1.0,
        'energy_weight': 0.5,  # fixed
    }
    
    agent = AetherExp001A_v022(
        seed=seed,
        n_actions=N_ACTIONS,
        n_features=N_FEATURES,
        history_length=50,
        **weights
    )
    
    for cycle in range(1, CYCLES + 1):
        state, action_rewards = generate_stimulus(cycle, seed)
        agent.act(action_rewards, state)
    
    summary = agent.get_summary()
    summary['sweep_param'] = sweep_param
    summary['sweep_value'] = sweep_value
    summary['history'] = agent.history  # full detailed history
    return summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='Run quick verification (1 seed, 100 cycles)')
    args = parser.parse_args()
    
    if args.quick:
        cycles = 100
        seeds_per_cond = 1
        logger.info("QUICK MODE: 1 seed, 100 cycles per condition")
    else:
        cycles = CYCLES
        seeds_per_cond = SEEDS_PER_CONDITION
        logger.info("FULL MODE: 10 seeds, 500 cycles per condition")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"exp_001a_v022_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)
    
    all_results = []
    total_runs = sum(len(v) for v in SWEEPS.values()) * seeds_per_cond
    logger.info(f"Starting EXP-001A v0.22.0 – State Prediction Error Curiosity + Normalization")
    logger.info(f"Sweeps: {SWEEPS}")
    logger.info(f"Seeds per condition: {seeds_per_cond}")
    logger.info(f"Total runs: {total_runs}")
    
    run_id = 0
    for param, values in SWEEPS.items():
        for val in values:
            logger.info(f"Running {param}={val} with {seeds_per_cond} seeds")
            for seed_offset in range(seeds_per_cond):
                seed = 10000 + seed_offset
                run_id += 1
                try:
                    result = run_single_experiment(seed, param, val)
                    result['run_id'] = run_id
                    all_results.append(result)
                    
                    # Save raw history separately to keep summary manageable
                    history = result.pop('history')
                    hist_file = os.path.join(out_dir, f"run_{run_id}_history.json")
                    with open(hist_file, 'w') as f:
                        json.dump(history, f)
                        
                except Exception as e:
                    logger.error(f"Run {run_id} failed: {e}")
                    continue
    
    # Save aggregated summary
    summary_file = os.path.join(out_dir, "summary.json")
    with open(summary_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    logger.info(f"All runs completed. Results saved to {out_dir}")
    logger.info(f"Total successful runs: {len(all_results)}")

if __name__ == "__main__":
    main()