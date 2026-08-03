"""
AETHER v0.21.0 – Fixes for EXP-001A findings
- Reward per action (differentiated)
- Curiosity based on action frequency (inverse)
- Normalized utility components
- Corrected autocorrelation calculation
"""

import numpy as np
from collections import deque
import logging

class AetherExp001A_v021:
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
        
        # Persistence tracking
        self.last_action = None
        self.persistent_counter = 0
        
        # Action frequency for curiosity (inverse frequency)
        self.action_counts = np.zeros(n_actions, dtype=int)
        
        # Logging
        self.history = []
        self.logger = logging.getLogger(f"Aether-{seed}")

    def observe(self, state: np.ndarray) -> None:
        self.current_state = state.copy()
        self.state_history.append(state)
        self.energy -= 0.5
        self.fatigue += 0.1
        self.attention = max(0, min(100, self.attention - 0.2 + 0.1 * np.random.randn()))

    def compute_utility(self, action: int, action_rewards: np.ndarray) -> float:
        """
        Compute total utility for a given action.
        action_rewards: array of rewards per action (length n_actions).
        """
        # 1. Extrinsic reward (now action-specific)
        reward_val = action_rewards[action] if action < len(action_rewards) else 0.0
        u_reward = reward_val * self.reward_weight

        # 2. Curiosity – based on inverse action frequency (novelty of action)
        total_actions = max(1, sum(self.action_counts))
        freq = self.action_counts[action] / total_actions if total_actions > 0 else 0.0
        novelty = 1.0 - freq  # higher for rarely chosen actions
        u_curiosity = novelty * self.curiosity_weight

        # 3. Persistence – reward for repeating last action
        if self.last_action is not None and action == self.last_action:
            u_persistence = 1.0 * self.persistence_weight
        else:
            u_persistence = 0.0

        # 4. Energy cost (negative, but same for all actions, we keep it)
        energy_cost = (100 - self.energy) / 100.0
        u_energy = -energy_cost * self.energy_weight

        # 5. Noise (per action)
        noise = self.rng.normal(0, self.noise_scale * 0.1)

        total = u_reward + u_curiosity + u_persistence + u_energy + noise
        return total

    def act(self, action_rewards: np.ndarray, state: np.ndarray) -> int:
        """Select an action based on action-specific rewards and state."""
        self.observe(state)
        
        utilities = []
        for action in range(self.n_actions):
            u = self.compute_utility(action, action_rewards)
            utilities.append(u)
        
        # Softmax with temperature
        temp = 0.5 + 0.5 * (1 - self.fatigue / 100)
        exp_util = np.exp(np.array(utilities) / temp)
        probs = exp_util / exp_util.sum()
        
        # Additional exploration noise if noise_scale > 1
        if self.noise_scale > 1.0:
            noise_vec = self.rng.uniform(0.8, 1.2, size=self.n_actions)
            probs = probs * noise_vec
            probs = probs / probs.sum()
        
        action = self.rng.choice(self.n_actions, p=probs)
        
        # Update persistence and action counts
        self.last_action = action
        self.action_counts[action] += 1
        if len(self.action_history) > 0 and self.action_history[-1] == action:
            self.persistent_counter += 1
        else:
            self.persistent_counter = 1
        self.action_history.append(action)
        
        # Update energy/fatigue
        self.energy -= 0.2 * (action + 1)
        self.fatigue += 0.05 * (action + 1)
        self.energy = max(0, min(100, self.energy))
        self.fatigue = max(0, min(100, self.fatigue))
        
        # Log cycle data
        self.history.append({
            'cycle': len(self.history) + 1,
            'action': action,
            'action_rewards': action_rewards.tolist(),
            'utilities': utilities,
            'probs': probs.tolist(),
            'energy': self.energy,
            'fatigue': self.fatigue,
            'attention': self.attention,
            'persistence': self.persistent_counter,
            'state': state.tolist(),
        })
        
        return action

    def get_autocorrelation(self, lag: int = 1) -> float:
        """Compute autocorrelation of action sequence for given lag (corrected)."""
        actions = np.array(list(self.action_history))
        if len(actions) < lag + 1:
            return 0.0
        if np.std(actions) == 0:
            return 1.0  # constant sequence → perfect correlation
        # Use corrcoef between sequence and lag-shifted sequence
        corr = np.corrcoef(actions[:-lag], actions[lag:])[0,1]
        return float(corr) if not np.isnan(corr) else 0.0

    def get_entropy(self) -> float:
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        probs = counts / counts.sum()
        probs = probs[probs > 0]
        return -np.sum(probs * np.log(probs))

    def get_reversal_rate(self) -> float:
        if len(self.action_history) < 2:
            return 0.0
        changes = sum(1 for i in range(1, len(self.action_history)) if self.action_history[i] != self.action_history[i-1])
        return changes / (len(self.action_history) - 1)

    def get_pattern_counts(self) -> dict:
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        return {i: int(c) for i, c in enumerate(counts)}

    def get_summary(self) -> dict:
        autocorr = {lag: self.get_autocorrelation(lag) for lag in [1,2,3,4,5]}
        return {
            'seed': self.seed,
            'cycles': len(self.history),
            'avg_reward': np.mean([h.get('action_rewards', [0])[h['action']] for h in self.history]) if self.history else 0,
            'std_reward': np.std([h.get('action_rewards', [0])[h['action']] for h in self.history]) if self.history else 0,
            'avg_energy': np.mean([h['energy'] for h in self.history]) if self.history else 0,
            'avg_fatigue': np.mean([h['fatigue'] for h in self.history]) if self.history else 0,
            'entropy': self.get_entropy(),
            'autocorrelation': autocorr,
            'reversal_rate': self.get_reversal_rate(),
            'pattern_counts': self.get_pattern_counts(),
            'persistence_duration': max(self.persistent_counter, 0),
        }