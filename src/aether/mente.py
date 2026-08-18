from collections import deque
import numpy as np

try:
    from .config import HardConfig
except ImportError:
    from config import HardConfig


class MenteBudget:
    def __init__(self, max_energy=100, max_attention=100):
        self.energy = max_energy
        self.attention = max_attention
        self.max_energy = max_energy
        self.max_attention = max_attention
        self.fatigue = 0
        self.failure_burden = 0
        self.consecutive_same_pattern = 0
        self.last_pattern = None
        self.last_rest_cycle = -999
        self.cycle = 0
        self.reward_history = deque(maxlen=HardConfig.REWARD_STAGNATION_WINDOW)
        self.persistence_counter = 0

    def spend(self, energy_cost, attention_cost, fatigue_delta):
        self.energy = max(0, self.energy - energy_cost)
        self.attention = max(0, self.attention - attention_cost)
        self.fatigue = min(100, self.fatigue + fatigue_delta)

    def recover(self, energy_gain, attention_gain, fatigue_reduction):
        self.energy = min(self.max_energy, self.energy + energy_gain)
        self.attention = min(self.max_attention, self.attention + attention_gain)
        self.fatigue = max(0, self.fatigue - fatigue_reduction)

    def regen(self, resting):
        if resting and self.can_rest():
            fp = max(0, self.fatigue / 20)
            self.energy = min(self.max_energy, self.energy + max(3, HardConfig.REST_ENERGY_GAIN_BASE - int(fp)))
            self.attention = min(self.max_attention, self.attention + max(4, HardConfig.REST_ATTENTION_GAIN_BASE - int(fp*1.2)))
            self.fatigue = max(0, self.fatigue - HardConfig.REST_FATIGUE_REDUCTION)
            self.last_rest_cycle = self.cycle
            self.failure_burden = max(0, self.failure_burden + HardConfig.BURDEN_RECOVERY_REST)
        else:
            self.energy = min(self.max_energy, self.energy + 1)
            self.attention = min(self.max_attention, self.attention + 1)
            self.fatigue = max(0, self.fatigue - 1)

    def can_rest(self):
        return (self.cycle - self.last_rest_cycle) >= HardConfig.REST_COOLDOWN

    def is_emergency(self):
        return self.energy < 20 or self.fatigue > 80 or self.failure_burden > 70

    def update_failure_burden(self, score):
        if score < 0.35:
            self.failure_burden = min(100, self.failure_burden + 12)
        elif score > 0.7:
            self.failure_burden = max(0, self.failure_burden - 8)
        else:
            self.failure_burden = max(0, self.failure_burden - 2)

    def track_pattern_repetition(self, pattern):
        if pattern == self.last_pattern:
            self.consecutive_same_pattern += 1
        else:
            self.consecutive_same_pattern = 1
            self.last_pattern = pattern
        return self.consecutive_same_pattern

    def track_reward_stagnation(self, reward):
        self.reward_history.append(reward)
        if len(self.reward_history) >= HardConfig.REWARD_STAGNATION_WINDOW:
            min_r = min(self.reward_history)
            max_r = max(self.reward_history)
            return (max_r - min_r) < HardConfig.REWARD_IMPROVEMENT_THRESHOLD
        return False

    def should_reset(self, reward):
        if self.persistence_counter > 0:
            self.persistence_counter -= 1
            return False
        repeat = self.consecutive_same_pattern
        stagnant = self.track_reward_stagnation(reward) if len(self.reward_history)>=HardConfig.REWARD_STAGNATION_WINDOW else False
        if repeat >= HardConfig.REPETITION_STAGNATION_THRESHOLD and stagnant:
            return True
        return False

    def give_persistence_bonus(self, reward):
        if reward > 0.7:
            self.persistence_counter = HardConfig.PERSISTENCE_BONUS_CYCLES


class MenteCuriosity:
    def __init__(self, world_model):
        self.world_model = world_model
        self.novelty_weight = 0.3
        self.prediction_weight = 0.7

    def get_bonus(self, state_vec, action):
        pred_error = self.world_model.prediction_error
        quantized_state = tuple(np.floor(np.asarray(state_vec) * 10).astype(int).tolist())
        h = (quantized_state, action)
        if not hasattr(self, 'visited_states'):
            self.visited_states = {}
        self.visited_states[h] = self.visited_states.get(h, 0) + 1
        novelty = 1.0 / (1.0 + self.visited_states[h])
        return self.prediction_weight * pred_error + self.novelty_weight * novelty


class MenteEventBus:
    def __init__(self):
        self.listeners = {}
    def subscribe(self, event_type, callback):
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)
    def emit(self, event_type, data):
        for cb in self.listeners.get(event_type, []):
            cb(data)
