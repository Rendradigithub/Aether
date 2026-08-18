from collections import deque

import numpy as np

try:
    from .config import HardConfig
except ImportError:
    from config import HardConfig


class PredictiveWorldModel:
    def __init__(self, state_dim=HardConfig.VECTOR_DIM, action_dim=7):
        input_dim = state_dim
        hidden_dim = HardConfig.WORLD_MODEL_HIDDEN_DIM
        self.W1 = np.random.randn(hidden_dim, input_dim + 1) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(input_dim, hidden_dim) * 0.1
        self.b2 = np.zeros(input_dim)
        self.confidence = 0.5
        self.prediction_error = 0.0
        self.buffer = deque(maxlen=100)
        self.action_map = {a: i for i, a in enumerate(HardConfig.ACTION_COSTS.keys())}

    def encode_action(self, action):
        idx = self.action_map.get(action, 0)
        return idx / len(self.action_map)

    def predict(self, state_vec, action):
        x = np.append(state_vec, self.encode_action(action))
        h = np.tanh(self.W1 @ x + self.b1)
        pred_state = self.W2 @ h + self.b2
        return pred_state

    def update(self, state_vec, action, next_state_vec):
        pred = self.predict(state_vec, action)
        error = next_state_vec - pred
        rmse = np.sqrt(np.mean(error**2))
        norm_pred = np.linalg.norm(pred)
        norm_next = np.linalg.norm(next_state_vec)
        if norm_pred > 1e-8 and norm_next > 1e-8:
            cos_sim = np.dot(pred, next_state_vec) / (norm_pred * norm_next)
        else:
            cos_sim = 0.0
        cos_dist = 1.0 - cos_sim
        self.prediction_error = float(np.clip(0.5 * rmse + 0.5 * cos_dist, 0.0, 1.0))
        x = np.append(state_vec, self.encode_action(action))
        h = np.tanh(self.W1 @ x + self.b1)
        dW2 = np.outer(error, h)
        db2 = error
        dh = self.W2.T @ error
        dz = dh * (1 - h**2)
        dW1 = np.outer(dz, x)
        db1 = dz
        lr = HardConfig.WORLD_MODEL_UPDATE_RATE
        self.W2 -= lr * dW2
        self.b2 -= lr * db2
        self.W1 -= lr * dW1
        self.b1 -= lr * db1
        self.buffer.append(self.prediction_error)
        if len(self.buffer) >= 20:
            recent_err = np.mean(list(self.buffer)[-20:])
            self.confidence = max(0.2, min(0.9, 1.0 - recent_err))
        else:
            self.confidence = 0.5
