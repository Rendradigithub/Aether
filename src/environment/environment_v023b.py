"""
Environment v0.23b: Integrator Dynamics (Structural Persistence - P-00b)
========================================================================
Layer 0 with persistence:
- State = 36-dim vector.
- Action = index 0..4.
- Transition: state += alpha * tanh(W[action] @ state + b[action]) + noise.
- Changes accumulate → structural persistence.
- Still no reward, no semantic names.

P-00a (Action Separability): ✅ maintained (operators differ).
P-00b (Structural Persistence): ✅ changes accumulate; world has memory.
"""

import numpy as np
from typing import Tuple, List

class EnvironmentV023b:
    def __init__(self,
                 seed: int = 42,
                 state_dim: int = 36,
                 n_actions: int = 5,
                 alpha: float = 0.1,
                 noise_scale: float = 0.01,
                 clip_range: float = 2.0):
        """
        Args:
            seed: Random seed.
            state_dim: Dimensionality of state.
            n_actions: Number of actions (operators).
            alpha: Integration step size (persistence strength).
            noise_scale: Small noise for stability.
            clip_range: State values clamped to [-clip_range, clip_range].
        """
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.state_dim = state_dim
        self.n_actions = n_actions
        self.alpha = alpha
        self.noise_scale = noise_scale
        self.clip_range = clip_range

        # ---- Initialize operators ----
        self.W = []
        self.b = []
        for _ in range(n_actions):
            w = self.rng.normal(0, 0.2, size=(state_dim, state_dim))
            b = self.rng.normal(0, 0.1, size=state_dim)
            self.W.append(w)
            self.b.append(b)

        # ---- Initialize state ----
        self.state = np.zeros(state_dim)
        self.cycle = 0
        self.history = [self.state.copy()]

    def reset(self) -> np.ndarray:
        """Reset state to zero and clear history."""
        self.state = np.zeros(self.state_dim)
        self.cycle = 0
        self.history = [self.state.copy()]
        return self.state.copy()

    def step(self, action: int) -> np.ndarray:
        """
        Apply action, update state with integrator dynamics.
        Returns next_state.
        """
        if action < 0 or action >= self.n_actions:
            raise ValueError(f"Action {action} out of range")

        # Compute delta (candidate change)
        delta = np.tanh(self.W[action] @ self.state + self.b[action])

        # Integrate (persistence)
        self.state += self.alpha * delta
        self.state += self.noise_scale * self.rng.normal(size=self.state_dim)
        self.state = np.clip(self.state, -self.clip_range, self.clip_range)

        self.cycle += 1
        self.history.append(self.state.copy())
        return self.state.copy()

    # ============================================================
    #  P-00a Metrics (Action Separability) - same as before
    # ============================================================

    def get_operator_separability(self) -> float:
        """Average Frobenius distance between W matrices."""
        distances = []
        for i in range(self.n_actions):
            for j in range(i + 1, self.n_actions):
                dist = np.linalg.norm(self.W[i] - self.W[j], ord='fro')
                distances.append(dist)
        return np.mean(distances) if distances else 0.0

    def get_reality_separability(self, n_states: int = 20) -> float:
        """
        For random starting states, compute pairwise distance between
        futures produced by different actions.
        """
        distances = []
        for _ in range(n_states):
            s = self.rng.normal(0, 1, size=self.state_dim)
            next_states = []
            for a in range(self.n_actions):
                # Compute next state without modifying world
                delta = np.tanh(self.W[a] @ s + self.b[a])
                ns = s + self.alpha * delta
                next_states.append(ns)
            for i in range(self.n_actions):
                for j in range(i + 1, self.n_actions):
                    dist = np.linalg.norm(next_states[i] - next_states[j])
                    distances.append(dist)
        return np.mean(distances) if distances else 0.0

    def get_operator_diversity(self) -> dict:
        """Pairwise cosine similarity between W matrices."""
        similarities = []
        for i in range(self.n_actions):
            for j in range(i + 1, self.n_actions):
                wi = self.W[i].flatten()
                wj = self.W[j].flatten()
                cos_sim = np.dot(wi, wj) / (np.linalg.norm(wi) * np.linalg.norm(wj) + 1e-8)
                similarities.append(cos_sim)
        return {
            'mean_similarity': np.mean(similarities) if similarities else 0.0,
            'max_similarity': np.max(similarities) if similarities else 0.0,
            'min_similarity': np.min(similarities) if similarities else 0.0,
        }

    def check_p00a(self, threshold_sep: float = 0.5, threshold_sim: float = 0.8) -> bool:
        """Return True if P-00a is satisfied."""
        op_sep = self.get_operator_separability()
        real_sep = self.get_reality_separability()
        sim = self.get_operator_diversity()['mean_similarity']
        return (op_sep > threshold_sep and real_sep > threshold_sep and sim < threshold_sim)

    # ============================================================
    #  P-00b Metrics (Structural Persistence)
    # ============================================================

    def get_persistence_index(self, n_steps: int = 100) -> float:
        """
        Measure how much state has moved from initial after n_steps of random actions.
        Higher = more persistent change.
        """
        env = EnvironmentV023b(
            seed=self.seed + 999,
            state_dim=self.state_dim,
            n_actions=self.n_actions,
            alpha=self.alpha,
            noise_scale=self.noise_scale,
            clip_range=self.clip_range
        )
        env.W = [w.copy() for w in self.W]
        env.b = [b.copy() for b in self.b]

        initial = env.state.copy()
        actions = self.rng.integers(0, self.n_actions, size=n_steps)
        for a in actions:
            env.step(a)
        final = env.state.copy()
        displacement = np.linalg.norm(final - initial)
        return displacement

    def get_accumulation_effect(self, n_steps: int = 100, n_samples: int = 5) -> float:
        """
        Measure whether different action sequences lead to systematically different
        final states. If persistence works, the same sequence should lead to similar
        final states, and different sequences should lead to different states.
        """
        # Generate two different action sequences
        sequences = []
        for _ in range(n_samples):
            seq = self.rng.integers(0, self.n_actions, size=n_steps)
            sequences.append(seq)

        # Run each sequence from same initial state (copy environment)
        final_states = []
        for seq in sequences:
            env = EnvironmentV023b(
                seed=self.seed + 999 + len(final_states),
                state_dim=self.state_dim,
                n_actions=self.n_actions,
                alpha=self.alpha,
                noise_scale=self.noise_scale,
                clip_range=self.clip_range
            )
            env.W = [w.copy() for w in self.W]
            env.b = [b.copy() for b in self.b]
            env.state = np.zeros(self.state_dim)  # same start
            for a in seq:
                env.step(a)
            final_states.append(env.state.copy())

        # Compute pairwise distances between final states from different sequences
        distances = []
        for i in range(len(final_states)):
            for j in range(i + 1, len(final_states)):
                d = np.linalg.norm(final_states[i] - final_states[j])
                distances.append(d)
        return np.mean(distances) if distances else 0.0

    def check_p00b(self, threshold_persistence: float = 0.5, threshold_accumulation: float = 0.3) -> bool:
        """
        Return True if P-00b is satisfied:
        - Persistence index > threshold_persistence
        - Accumulation effect > threshold_accumulation
        """
        pers = self.get_persistence_index(n_steps=100)
        accum = self.get_accumulation_effect(n_steps=100, n_samples=5)
        return (pers > threshold_persistence and accum > threshold_accumulation)

    def diagnostic_summary(self) -> dict:
        """Return full diagnostic dictionary for P-00a and P-00b."""
        p00a = self.check_p00a()
        p00b = self.check_p00b()
        return {
            'p00a': p00a,
            'p00b': p00b,
            'operator_separability': self.get_operator_separability(),
            'reality_separability': self.get_reality_separability(),
            'mean_operator_similarity': self.get_operator_diversity()['mean_similarity'],
            'persistence_index': self.get_persistence_index(n_steps=100),
            'accumulation_effect': self.get_accumulation_effect(n_steps=100, n_samples=5),
        }