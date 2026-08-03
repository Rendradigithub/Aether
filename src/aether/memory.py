from collections import deque

import numpy as np


class MenteMemory:
    def __init__(self, working_capacity=10, episodic_capacity=100):
        self.working = deque(maxlen=working_capacity)
        self.episodic = deque(maxlen=episodic_capacity)
        self.semantic = {}
        self.vectors = []

    def add_experience(self, experience):
        self.working.append(experience)
        if experience.get('contour_reward', 0) > 0.7:
            self.episodic.append(experience)
        if 'state' in experience:
            self.vectors.append(np.array(experience['state']))
            if len(self.vectors) > 200:
                self.vectors.pop(0)

    def recall_similar(self, query, k=3):
        candidates = list(self.working) + list(self.episodic)
        if not candidates: return []
        query_pat = query.get('pattern')
        query_contour = query.get('contour_reward', 0.5)
        scored = []
        for exp in candidates:
            score = 0.5 if exp.get('pattern') == query_pat else 0
            score += 1.0 - abs(exp.get('contour_reward', 0.5) - query_contour)
            scored.append((score, exp))
        scored.sort(reverse=True)
        return [exp for _, exp in scored[:k]]

    def update_semantic(self, key, value):
        self.semantic[key] = value

    def novelty(self, vec):
        if not self.vectors:
            return 1.0
        sims = [np.dot(vec, v) / (np.linalg.norm(vec)*np.linalg.norm(v)+1e-8) for v in self.vectors[-10:]]
        return 1.0 - max(sims) if sims else 1.0
