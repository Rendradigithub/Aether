"""
AETHER v0.22.0 – Curiosity as State Prediction Error + Utility Normalization + Decomposition Logging

Changes from v0.21.0:
- Curiosity now based on prediction error of STATE (not action frequency)
- All utility components are normalized to [0,1] per-component (not total)
- Detailed utility decomposition logged every cycle (raw, norm, weighted)
- Autocorrelation now handles constant sequences gracefully (no NumPy warnings)
- Counterfactual simulation (P-03) NOT included (waiting for balanced utility)
"""

import numpy as np
from collections import deque
import logging

class AetherExp001A_v022:
    def __init__(self, 
                 seed: int,
                 reward_weight: float = 1.0,
                 curiosity_weight: float = 1.0,
                 persistence_weight: float = 1.0,
                 energy_weight: float = 0.5,
                 noise_scale: float = 0.3,
                 n_actions: int = 5,
                 n_features: int = 36,
                 history_length: int = 50):
        """
        Args:
            seed: Random seed.
            reward_weight: Multiplier for normalized reward signal [0-1].
            curiosity_weight: Multiplier for normalized prediction error [0-1].
            persistence_weight: Multiplier for repeat bonus [0-1].
            energy_weight: Multiplier for energy cost penalty [0-1].
            noise_scale: Scale of Gaussian noise added to utility.
            n_actions: Number of discrete actions.
            n_features: Dimensionality of state vector.
            history_length: Length of rolling history for metrics.
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

        # Energy and fatigue
        self.energy = 100.0
        self.fatigue = 0.0

        # Persistence tracking
        self.last_action = None
        self.persistent_counter = 0

        # --- Curiosity: Prediction Error Model (state-based) ---
        # Store observed state transitions (delta) per action
        self.transition_memory = {a: deque(maxlen=20) for a in range(n_actions)}
        # Last computed prediction error for each action (to be used in utility)
        self.last_prediction_error = {a: 0.0 for a in range(n_actions)}

        # --- Logging: full utility decomposition per cycle ---
        self.history = []
        self.logger = logging.getLogger(f"Aether-{seed}")

    # ----------------------------------------------------------------------
    #  Prediction Model for Curiosity
    # ----------------------------------------------------------------------
    def predict_next_state(self, action: int, current_state: np.ndarray) -> np.ndarray:
        """Predict next state using average transition delta for this action."""
        if len(self.transition_memory[action]) > 0:
            avg_delta = np.mean(self.transition_memory[action], axis=0)
            return current_state + avg_delta
        else:
            # No data yet: fallback to identity prediction
            return current_state

    # ----------------------------------------------------------------------
    #  Observation and Curiosity Update
    # ----------------------------------------------------------------------
    def observe(self, state: np.ndarray) -> None:
        """Receive new state, compute prediction error for the action that led here."""
        if len(self.state_history) > 0 and self.last_action is not None:
            prev_state = self.state_history[-1]
            predicted = self.predict_next_state(self.last_action, prev_state)
            error = np.linalg.norm(state - predicted)
            self.last_prediction_error[self.last_action] = error

            # Store actual delta for future predictions
            delta = state - prev_state
            self.transition_memory[self.last_action].append(delta)

        # Update current state
        self.current_state = state.copy()
        self.state_history.append(state)

        # Energy dynamics (observation cost)
        self.energy -= 0.5
        self.fatigue += 0.1
        self.energy = max(0.0, min(100.0, self.energy))
        self.fatigue = max(0.0, min(100.0, self.fatigue))

    # ----------------------------------------------------------------------
    #  Component Normalization
    # ----------------------------------------------------------------------
    @staticmethod
    def normalize_component(raw_value, method='tanh', clip_min=0.0, clip_max=1.0):
        """
        Normalize a raw component value to [0, 1].
        Methods:
        - 'clip': simple min-max clip
        - 'tanh': squash using tanh (good for unbounded positive values)
        - 'sigmoid': logistic sigmoid (alternative)
        """
        if method == 'clip':
            return np.clip((raw_value - clip_min) / (clip_max - clip_min + 1e-8), 0.0, 1.0)
        elif method == 'tanh':
            # tanh outputs [-1,1] → map to [0,1]
            return (np.tanh(raw_value) + 1.0) / 2.0
        elif method == 'sigmoid':
            return 1.0 / (1.0 + np.exp(-raw_value))
        else:
            return raw_value

    # ----------------------------------------------------------------------
    #  Core Utility Calculation (with decomposition)
    # ----------------------------------------------------------------------
    def compute_utility(self, action: int, action_rewards: np.ndarray):
        """
        Compute total utility and full decomposition for a given action.
        Returns:
            total: float
            decomp: dict containing raw, norm, weighted values for all components.
        """
        # 1. Reward (already in [0,1] by construction)
        raw_reward = float(action_rewards[action])
        norm_reward = raw_reward  # already [0,1]

        # 2. Curiosity = prediction error (state-based, unbounded positive)
        raw_curiosity = self.last_prediction_error.get(action, 0.0)
        norm_curiosity = self.normalize_component(raw_curiosity, method='tanh')

        # 3. Persistence (binary: 1 if repeat, else 0)
        raw_persistence = 1.0 if (self.last_action is not None and action == self.last_action) else 0.0
        norm_persistence = raw_persistence  # already [0,1]

        # 4. Energy cost (proportional to how tired we are)
        raw_energy_cost = (100.0 - self.energy) / 100.0  # [0,1]
        norm_energy_cost = np.clip(raw_energy_cost, 0.0, 1.0)

        # 5. Noise (zero-centered, unbounded)
        raw_noise = self.rng.normal(0.0, 0.1)
        # We do NOT normalize noise; we keep it as a small perturbation

        # ---- Weighted contributions ----
        u_reward = norm_reward * self.reward_weight
        u_curiosity = norm_curiosity * self.curiosity_weight
        u_persistence = norm_persistence * self.persistence_weight
        u_energy = -norm_energy_cost * self.energy_weight   # negative penalty
        u_noise = raw_noise * self.noise_scale

        total = u_reward + u_curiosity + u_persistence + u_energy + u_noise

        # ---- Decomposition dictionary ----
        decomp = {
            'action': action,
            'raw': {
                'reward': raw_reward,
                'curiosity': raw_curiosity,
                'persistence': raw_persistence,
                'energy_cost': raw_energy_cost,
                'noise': raw_noise,
            },
            'norm': {
                'reward': norm_reward,
                'curiosity': norm_curiosity,
                'persistence': norm_persistence,
                'energy_cost': norm_energy_cost,
            },
            'weighted': {
                'u_reward': u_reward,
                'u_curiosity': u_curiosity,
                'u_persistence': u_persistence,
                'u_energy': u_energy,
                'u_noise': u_noise,
            },
            'total': total
        }
        return total, decomp

    # ----------------------------------------------------------------------
    #  Decision Making
    # ----------------------------------------------------------------------
    def act(self, action_rewards: np.ndarray, state: np.ndarray) -> int:
        """
        Select an action given action-specific rewards and current state.
        Returns chosen action index.
        """
        self.observe(state)

        # Compute utility and decomposition for all actions
        utilities = []
        decomp_list = []
        for a in range(self.n_actions):
            u, decomp = self.compute_utility(a, action_rewards)
            utilities.append(u)
            decomp_list.append(decomp)

        # Softmax with temperature (fatigue increases randomness)
        temp = 0.5 + 0.5 * (1.0 - self.fatigue / 100.0)
        exp_util = np.exp(np.array(utilities) / max(temp, 0.1))
        probs = exp_util / exp_util.sum()

        # Additional exploration if noise_scale is large
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

        # Simulate action cost on energy/fatigue
        self.energy -= 0.2 * (action + 1)
        self.fatigue += 0.05 * (action + 1)
        self.energy = max(0.0, min(100.0, self.energy))
        self.fatigue = max(0.0, min(100.0, self.fatigue))

        # ---- Log cycle data (including full decomposition) ----
        self.history.append({
            'cycle': len(self.history) + 1,
            'chosen_action': action,
            'utilities': utilities,
            'probs': probs.tolist(),
            'decomposition_all_actions': decomp_list,   # full decomp for every action
            'chosen_decomp': decomp_list[action],       # shortcut for the chosen one
            'energy': self.energy,
            'fatigue': self.fatigue,
            'persistent_counter': self.persistent_counter,
            'state': state.tolist(),
        })

        return action

    # ----------------------------------------------------------------------
    #  Metrics (with fixed autocorrelation)
    # ----------------------------------------------------------------------
    def get_autocorrelation(self, lag: int = 1) -> float:
        """Autocorrelation of action sequence at given lag (no NumPy warnings)."""
        actions = np.array(list(self.action_history))
        if len(actions) < lag + 1:
            return 0.0
        x = actions[:-lag]
        y = actions[lag:]
        # Handle constant sequences
        if np.std(x) < 1e-8 or np.std(y) < 1e-8:
            return 1.0 if np.array_equal(x, y) else 0.0
        corr = np.corrcoef(x, y)[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0

    def get_entropy(self) -> float:
        """Shannon entropy of action distribution."""
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        probs = counts / counts.sum()
        probs = probs[probs > 0]
        return -np.sum(probs * np.log(probs)) if len(probs) > 0 else 0.0

    def get_reversal_rate(self) -> float:
        """Fraction of actions that switch from previous."""
        if len(self.action_history) < 2:
            return 0.0
        changes = sum(1 for i in range(1, len(self.action_history))
                       if self.action_history[i] != self.action_history[i-1])
        return changes / (len(self.action_history) - 1)

    def get_pattern_counts(self) -> dict:
        counts = np.bincount(list(self.action_history), minlength=self.n_actions)
        return {i: int(c) for i, c in enumerate(counts)}

    def get_average_decomposition(self) -> dict:
        """Average contribution of each utility component over all cycles."""
        if not self.history:
            return {}
        n = len(self.history)
        avg_weighted = {
            'u_reward': 0.0,
            'u_curiosity': 0.0,
            'u_persistence': 0.0,
            'u_energy': 0.0,
            'u_noise': 0.0,
        }
        for h in self.history:
            decomp = h['chosen_decomp']['weighted']
            for key in avg_weighted:
                avg_weighted[key] += decomp[key] / n
        return avg_weighted

    def get_summary(self) -> dict:
        """Return summary metrics for the run."""
        autocorr = {lag: self.get_autocorrelation(lag) for lag in [1, 2, 3, 4, 5]}
        avg_decomp = self.get_average_decomposition()

        return {
            'seed': self.seed,
            'cycles': len(self.history),
            'avg_reward': np.mean([h['chosen_decomp']['raw']['reward'] for h in self.history]) if self.history else 0,
            'std_reward': np.std([h['chosen_decomp']['raw']['reward'] for h in self.history]) if self.history else 0,
            'avg_energy': np.mean([h['energy'] for h in self.history]) if self.history else 0,
            'avg_fatigue': np.mean([h['fatigue'] for h in self.history]) if self.history else 0,
            'entropy': self.get_entropy(),
            'autocorrelation': autocorr,
            'reversal_rate': self.get_reversal_rate(),
            'pattern_counts': self.get_pattern_counts(),
            'persistence_duration': max(self.persistent_counter, 0),
            'average_utility_components': avg_decomp,   # <-- NEW: decomposition summary
        }