"""
AETHER v0.19.1 – Extended for EXP-001A: Decision Sensitivity Analysis

This module implements the Aether agent with explicit utility components
that can be weighted independently for parameter ablation experiments.

Utility = α * reward + β * curiosity + γ * persistence + δ * energy + ε * noise

All weights are configurable via constructor arguments.
"""

import numpy as np
from collections import deque
import json
import logging

class AetherExp001A:
    def __init__(self, 
                 seed: int,
                 reward_weight: float = 1.0,
                 curiosity_weight: float = 1.0,
                 persistence_weight: float = 1.0,
                 energy_weight: float = 1.0,
                 noise_scale: float = 1.0,
                 n_actions: int = 5,
                 n_features: int = 36,
                 history_length: int = 10):
        """
        Args:
            seed: Random seed for reproducibility.
            reward_weight: Multiplier for extrinsic reward signal.
            curiosity_weight: Multiplier for intrinsic curiosity (novelty).
            persistence_weight: Multiplier for momentum (prefer repeating actions).
            energy_weight: Multiplier for energy cost (negative).
            noise_scale: Scale of exploration noise added to action probabilities.
            n_actions: Number of possible patterns (shape, wave, fractal, cellular, lsystem).
            n_features: Dimensionality of the world state representation.
            history_length: Number of past states to store for autocorrelation.
        """
        self.seed = seed
        np.random.seed(seed)
        self.rng = np.random.default_rng(seed)

        self.n_actions = n_actions
        self.n_features = n_features
        self.history_length = history_length

        # Utility weights
        self.reward_weight = reward_weight
        self.curiosity_weight = curiosity_weight
        self.persistence_weight = persistence_weight
        self.energy_weight = energy_weight
        self.noise_scale = noise_scale

        # Internal state
        self.current_state = np.zeros(n_features)
        self.action_history = deque(maxlen=history_length)
        self.state_history = deque(maxlen=history_length)
        self.reward_history = deque(maxlen=history_length)
        
        # Energy and fatigue dynamics
        self.energy = 100.0
        self.fatigue = 0.0
        self.attention = 100.0
        
        # Curiosity / novelty tracking
        self.novelty_memory = []
        self.novelty_threshold = 0.5
        
        # Persistence tracking
        self.last_action = None
        self.persistent_counter = 0
        
        # Logging
        self.history = []
        self.logger = logging.getLogger(f"Aether-{seed}")

    def observe(self, state: np.ndarray) -> None:
        """Update internal state with new observation."""
        self.current_state = state.copy()
        self.state_history.append(state)
        # Update energy (cost of observing)
        self.energy -= 0.5
        self.fatigue += 0.1
        self.attention = max(0, min(100, self.attention - 0.2 + 0.1 * np.random.randn()))

    def compute_utility(self, action: int, reward: float) -> float:
        """
        Compute total utility for a given action, incorporating all components.
        This is the core decision function.
        """
        # 1. Extrinsic reward
        u_reward = reward * self.reward_weight

        # 2. Curiosity (novelty) – measured as distance to nearest past state
        if len(self.state_history) > 1:
            current = self.current_state.flatten()
            distances = [np.linalg.norm(current - past.flatten()) for past in list(self.state_history)[:-1]]
            novelty = np.mean(distances) if distances else 0.0
        else:
            novelty = 0.0
        u_curiosity = novelty * self.curiosity_weight

        # 3. Persistence – reward for repeating last action
        if self.last_action is not None and action == self.last_action:
            u_persistence = 1.0 * self.persistence_weight
        else:
            u_persistence = 0.0

        # 4. Energy cost – negative utility for high energy consumption
        energy_cost = (100 - self.energy) / 100.0
        u_energy = -energy_cost * self.energy_weight

        # 5. Noise – adds stochasticity to avoid deterministic lock-in
        noise = self.rng.normal(0, self.noise_scale * 0.1)  # small perturbation

        total = u_reward + u_curiosity + u_persistence + u_energy + noise
        return total

    def act(self, reward: float, state: np.ndarray) -> int:
        """Select an action based on current utility."""
        self.observe(state)
        
        utilities = []
        for action in range(self.n_actions):
            u = self.compute_utility(action, reward)
            utilities.append(u)
        
        # Softmax with temperature
        temp = 0.5 + 0.5 * (1 - self.fatigue / 100)  # higher fatigue -> more random
        exp_util = np.exp(np.array(utilities) / temp)
        probs = exp_util / exp_util.sum()
        
        # Add additional exploration noise if noise_scale > 1
        if self.noise_scale > 1.0:
            noise_vec = self.rng.uniform(0.8, 1.2, size=self.n_actions)
            probs = probs * noise_vec
            probs = probs / probs.sum()
        
        action = self.rng.choice(self.n_actions, p=probs)
        
        # Update persistence
        self.last_action = action
        if len(self.action_history) > 0 and self.action_history[-1] == action:
            self.persistent_counter += 1
        else:
            self.persistent_counter = 1
        self.action_history.append(action)
        
        # Update energy/fatigue based on action (simulated cost)
        self.energy -= 0.2 * (action + 1)  # different actions cost different energy
        self.fatigue += 0.05 * (action + 1)
        self.energy = max(0, min(100, self.energy))
        self.fatigue = max(0, min(100, self.fatigue))
        
        # Log cycle data
        self.history.append({
            'cycle': len(self.history) + 1,
            'action': action,
            'reward': reward,
            'energy': self.energy,
            'fatigue': self.fatigue,
            'attention': self.attention,
            'persistence': self.persistent_counter,
            'utilities': utilities,
            'probs': probs.tolist(),
            'state': state.tolist(),
        })
        
        return action

    def get_autocorrelation(self, lag: int = 1) -> float:
        """Compute autocorrelation of actions for given lag."""
        if len(self.action_history) < lag + 1:
            return 0.0
        actions = np.array(list(self.action_history))
        if len(actions) == 0:
            return 0.0
        mean = np.mean(actions)
        var = np.var(actions)
        if var == 0:
            return 0.0
        corr = np.correlate(actions - mean, actions - mean, mode='valid')
        if len(corr) == 0:
            return 0.0
        return corr[0] / (len(actions) * var)

    def get_entropy(self) -> float:
        """Entropy of action distribution over history."""
        if len(self.action_history) == 0:
            return 0.0
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        probs = counts / counts.sum()
        probs = probs[probs > 0]
        return -np.sum(probs * np.log(probs))

    def get_reversal_rate(self) -> float:
        """Fraction of actions that are different from previous."""
        if len(self.action_history) < 2:
            return 0.0
        changes = sum(1 for i in range(1, len(self.action_history)) if self.action_history[i] != self.action_history[i-1])
        return changes / (len(self.action_history) - 1)

    def get_pattern_counts(self) -> dict:
        """Count of each action pattern."""
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        return {i: int(c) for i, c in enumerate(counts)}

    def get_summary(self) -> dict:
        """Return summary metrics for the run."""
        autocorr = {lag: self.get_autocorrelation(lag) for lag in [1,2,3,4,5]}
        return {
            'seed': self.seed,
            'cycles': len(self.history),
            'avg_reward': np.mean([h['reward'] for h in self.history]) if self.history else 0,
            'std_reward': np.std([h['reward'] for h in self.history]) if self.history else 0,
            'avg_energy': np.mean([h['energy'] for h in self.history]) if self.history else 0,
            'avg_fatigue': np.mean([h['fatigue'] for h in self.history]) if self.history else 0,
            'entropy': self.get_entropy(),
            'autocorrelation': autocorr,
            'reversal_rate': self.get_reversal_rate(),
            'pattern_counts': self.get_pattern_counts(),
            'persistence_duration': max(self.persistent_counter, 0),
        }