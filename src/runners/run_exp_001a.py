"""
Runner for EXP-001A: Decision Sensitivity Analysis
Performs parameter sweeps over reward, curiosity, persistence, and noise.
"""

import os
import json
import logging
from datetime import datetime
from tqdm import tqdm
import numpy as np
from aether_exp_001a import AetherExp001A

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Parameters
SEEDS_PER_CONDITION = 10
CYCLES = 500
N_ACTIONS = 5
N_FEATURES = 36

# Sweep parameters (multipliers)
SWEEPS = {
    'reward': [0.2, 0.5, 1.0, 2.0, 5.0],
    'curiosity': [0.2, 0.5, 1.0, 2.0, 5.0],
    'persistence': [0.2, 0.5, 1.0, 2.0, 5.0],
    'noise': [0.2, 0.5, 1.0, 2.0, 5.0],
}

# Stimulus simulation (simplified world)
def generate_stimulus(cycle, seed):
    """Generate state and rewards for each action."""
    rng = np.random.default_rng(seed + cycle)
    state = rng.normal(0, 1, size=N_FEATURES)
    # Hidden pattern: each action corresponds to a preferred phase
    # Reward for action i: how close its phase is to current time phase
    phase = cycle / 50.0 * 2 * np.pi
    action_phases = np.linspace(0, 2*np.pi, N_ACTIONS, endpoint=False)
    rewards = 0.5 + 0.5 * np.cos(action_phases - phase)  # values in [0,1]
    rewards += 0.1 * rng.normal(size=N_ACTIONS)
    rewards = np.clip(rewards, 0, 1)
    return state, rewards

def run_experiment(seed, sweep_param, sweep_value, base_seed=10000):
    """Run a single condition."""
    # Initialize agent with given weights
    agent = AetherExp001A(
        seed=seed,
        reward_weight=sweep_value if sweep_param == 'reward' else 1.0,
        curiosity_weight=sweep_value if sweep_param == 'curiosity' else 1.0,
        persistence_weight=sweep_value if sweep_param == 'persistence' else 1.0,
        noise_scale=sweep_value if sweep_param == 'noise' else 1.0,
        n_actions=N_ACTIONS,
        n_features=N_FEATURES,
    )
    
    # Run cycles
    for cycle in range(1, CYCLES + 1):
        state, reward = generate_stimulus(cycle, seed)
        action = agent.act(reward, state)
    
    # Get summary
    summary = agent.get_summary()
    summary['sweep_param'] = sweep_param
    summary['sweep_value'] = sweep_value
    summary['history'] = agent.history  # raw cycle data
    return summary

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"exp_001a_{timestamp}"
    os.makedirs(out_dir, exist_ok=True)
    
    all_results = []
    
    logger.info("Starting EXP-001A: Decision Sensitivity Analysis")
    logger.info(f"Sweeps: {SWEEPS}")
    logger.info(f"Seeds per condition: {SEEDS_PER_CONDITION}")
    total_runs = sum(len(v) for v in SWEEPS.values()) * SEEDS_PER_CONDITION
    logger.info(f"Total runs: {total_runs}")
    
    run_id = 0
    for param, values in SWEEPS.items():
        for val in values:
            logger.info(f"Running {param}={val} with {SEEDS_PER_CONDITION} seeds")
            for seed_offset in range(SEEDS_PER_CONDITION):
                seed = 10000 + seed_offset  # reuse seeds for reproducibility
                run_id += 1
                try:
                    result = run_experiment(seed, param, val)
                    result['run_id'] = run_id
                    all_results.append(result)
                    # Save raw history separately to avoid memory bloat
                    history = result.pop('history')
                    hist_file = os.path.join(out_dir, f"run_{run_id}_history.json")
                    with open(hist_file, 'w') as f:
                        json.dump(history, f)
                except Exception as e:
                    logger.error(f"Run {run_id} failed: {e}")
                    continue
    
    # Save aggregated results
    summary_file = os.path.join(out_dir, "summary.json")
    with open(summary_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    logger.info(f"All runs completed. Results saved to {out_dir}")
    logger.info(f"Total successful runs: {len(all_results)}")

if __name__ == "__main__":
    main()