"""
Environment v0.23: Minimal Constructive World
===============================================
Layer 0: Pure world dynamics.

Rules:
- State: 36-dim vector.
- Action: index 0..4 (no semantic names).
- Transition: next_state = tanh(W[action] @ state + b[action]) + noise.
- No reward. No curiosity. No planning. Just dynamics.

P-00 Prerequisite:
- Different actions must produce statistically distinguishable future states.
- Measured by reality_separability() and operator_separability().
"""

import numpy as np
from typing import Tuple, List

class EnvironmentV023:
    def __init__(self, seed: int = 42, state_dim: int = 36, n_actions: int = 5):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.state_dim = state_dim
        self.n_actions = n_actions

        # ---- Initialize operators ----
        # Each action has a matrix W (state_dim x state_dim) and bias b.
        # Random initialization ensures actions produce different futures.
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

    def reset(self) -> np.ndarray:
        """Reset state to zero (or small noise)."""
        self.state = np.zeros(self.state_dim)
        self.cycle = 0
        return self.state.copy()

    def step(self, action: int) -> np.ndarray:
        """
        Apply action to world.
        Returns next_state (no reward).
        """
        if action < 0 or action >= self.n_actions:
            raise ValueError(f"Action {action} out of range [0, {self.n_actions-1}]")

        # Transition: deterministic + tiny noise for exploration stability
        next_state = np.tanh(self.W[action] @ self.state + self.b[action])
        next_state += 0.01 * self.rng.normal(size=self.state_dim)

        self.state = next_state
        self.cycle += 1
        return self.state.copy()

    # ============================================================
    #  P-00 Diagnostic Methods (Layer 0 health checks)
    # ============================================================

    def get_operator_separability(self) -> float:
        """
        Measure separability between action operators.
        Returns average Frobenius norm distance between W matrices.
        Higher = more separable.
        """
        distances = []
        for i in range(self.n_actions):
            for j in range(i + 1, self.n_actions):
                # Frobenius norm of difference
                dist = np.linalg.norm(self.W[i] - self.W[j], ord='fro')
                distances.append(dist)
        return np.mean(distances) if distances else 0.0

    def get_reality_separability(self, n_states: int = 10) -> float:
        """
        Measure whether different actions lead to different futures.
        For n_states different starting points, compute next_state for all actions,
        then average pairwise distance across actions.
        Higher = more separable.
        """
        states = []
        for _ in range(n_states):
            # Generate random starting states (or use current history)
            s = self.rng.normal(0, 1, size=self.state_dim)
            states.append(s)

        all_distances = []
        for s in states:
            next_states = []
            for a in range(self.n_actions):
                # Compute next state without modifying world
                ns = np.tanh(self.W[a] @ s + self.b[a])
                next_states.append(ns)

            for i in range(self.n_actions):
                for j in range(i + 1, self.n_actions):
                    dist = np.linalg.norm(next_states[i] - next_states[j])
                    all_distances.append(dist)

        return np.mean(all_distances) if all_distances else 0.0

    def get_operator_diversity(self) -> dict:
        """
        Returns pair-wise cosine similarity between W matrices.
        Helps detect collapse (similarity > 0.9 means all actions do same thing).
        """
        similarities = []
        for i in range(self.n_actions):
            for j in range(i + 1, self.n_actions):
                # Flatten matrices and compute cosine similarity
                wi = self.W[i].flatten()
                wj = self.W[j].flatten()
                cos_sim = np.dot(wi, wj) / (np.linalg.norm(wi) * np.linalg.norm(wj) + 1e-8)
                similarities.append(cos_sim)
        return {
            'mean_similarity': np.mean(similarities) if similarities else 0.0,
            'max_similarity': np.max(similarities) if similarities else 0.0,
            'min_similarity': np.min(similarities) if similarities else 0.0,
        }

    def is_healthy(self, threshold_sep: float = 0.5, threshold_sim: float = 0.7) -> dict:
        """
        Check if environment satisfies P-00.
        - operator_separability > threshold_sep
        - reality_separability > threshold_sep
        - mean_operator_similarity < threshold_sim
        """
        op_sep = self.get_operator_separability()
        real_sep = self.get_reality_separability(n_states=10)
        div = self.get_operator_diversity()

        healthy = (
            op_sep > threshold_sep and
            real_sep > threshold_sep and
            div['mean_similarity'] < threshold_sim
        )

        return {
            'healthy': healthy,
            'operator_separability': op_sep,
            'reality_separability': real_sep,
            'mean_operator_similarity': div['mean_similarity'],
            'max_operator_similarity': div['max_similarity'],
            'threshold_sep': threshold_sep,
            'threshold_sim': threshold_sim,
        }