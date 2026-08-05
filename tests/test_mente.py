import unittest
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "archive" / "versions"))

from aether.mente import MenteBudget, MenteCuriosity, MenteEventBus
from aether.config import HardConfig
from aether.world_model import PredictiveWorldModel


class TestMenteBudgetExtraction(unittest.TestCase):
    """Test MenteBudget behavior matches archive implementation."""
    
    def setUp(self):
        self.budget = MenteBudget(max_energy=120, max_attention=120)
    
    def test_initialization(self):
        """Test initial state matches archive."""
        self.assertEqual(self.budget.energy, 120)
        self.assertEqual(self.budget.attention, 120)
        self.assertEqual(self.budget.max_energy, 120)
        self.assertEqual(self.budget.max_attention, 120)
        self.assertEqual(self.budget.fatigue, 0)
        self.assertEqual(self.budget.failure_burden, 0)
        self.assertEqual(self.budget.consecutive_same_pattern, 0)
        self.assertIsNone(self.budget.last_pattern)
        self.assertEqual(self.budget.last_rest_cycle, -999)
        self.assertEqual(self.budget.cycle, 0)
        self.assertEqual(len(self.budget.reward_history), 0)
        self.assertEqual(self.budget.persistence_counter, 0)
    
    def test_spend(self):
        """Test spending resources."""
        self.budget.spend(10, 5, 3)
        self.assertEqual(self.budget.energy, 110)
        self.assertEqual(self.budget.attention, 115)
        self.assertEqual(self.budget.fatigue, 3)
        
        # Test floor at 0
        self.budget.spend(200, 200, 10)
        self.assertEqual(self.budget.energy, 0)
        self.assertEqual(self.budget.attention, 0)
        self.assertEqual(self.budget.fatigue, 13)
    
    def test_recover(self):
        """Test recovery of resources."""
        self.budget.energy = 50
        self.budget.attention = 60
        self.budget.fatigue = 40
        
        self.budget.recover(20, 15, 10)
        self.assertEqual(self.budget.energy, 70)
        self.assertEqual(self.budget.attention, 75)
        self.assertEqual(self.budget.fatigue, 30)
        
        # Test ceiling
        self.budget.recover(200, 200, 100)
        self.assertEqual(self.budget.energy, 120)
        self.assertEqual(self.budget.attention, 120)
        self.assertEqual(self.budget.fatigue, 0)
    
    def test_regen_with_rest(self):
        """Test regeneration when resting."""
        self.budget.energy = 50
        self.budget.attention = 60
        self.budget.fatigue = 40
        self.budget.failure_burden = 30
        self.budget.cycle = 10
        self.budget.last_rest_cycle = 0
        
        self.budget.regen(resting=True)
        
        # Check rest was applied
        self.assertTrue(self.budget.energy > 50)
        self.assertTrue(self.budget.attention > 60)
        self.assertTrue(self.budget.fatigue < 40)
        self.assertEqual(self.budget.last_rest_cycle, 10)
        self.assertTrue(self.budget.failure_burden < 30)
    
    def test_regen_without_rest(self):
        """Test regeneration when not resting."""
        self.budget.energy = 50
        self.budget.attention = 60
        self.budget.fatigue = 10
        
        self.budget.regen(resting=False)
        
        self.assertEqual(self.budget.energy, 51)
        self.assertEqual(self.budget.attention, 61)
        self.assertEqual(self.budget.fatigue, 9)
    
    def test_can_rest(self):
        """Test rest cooldown logic."""
        self.budget.cycle = 10
        self.budget.last_rest_cycle = 6
        
        self.assertFalse(self.budget.can_rest())
        
        self.budget.cycle = 11
        self.assertTrue(self.budget.can_rest())
    
    def test_is_emergency(self):
        """Test emergency detection."""
        self.assertFalse(self.budget.is_emergency())
        
        self.budget.energy = 15
        self.assertTrue(self.budget.is_emergency())
        
        self.budget.energy = 120
        self.budget.fatigue = 85
        self.assertTrue(self.budget.is_emergency())
        
        self.budget.fatigue = 0
        self.budget.failure_burden = 75
        self.assertTrue(self.budget.is_emergency())
    
    def test_update_failure_burden(self):
        """Test failure burden updates."""
        self.budget.failure_burden = 50
        
        # Low score increases burden
        self.budget.update_failure_burden(0.3)
        self.assertEqual(self.budget.failure_burden, 62)
        
        # High score decreases burden
        self.budget.update_failure_burden(0.8)
        self.assertEqual(self.budget.failure_burden, 54)
        
        # Medium score slightly decreases
        self.budget.update_failure_burden(0.5)
        self.assertEqual(self.budget.failure_burden, 52)
    
    def test_track_pattern_repetition(self):
        """Test pattern repetition tracking."""
        count = self.budget.track_pattern_repetition('wave')
        self.assertEqual(count, 1)
        self.assertEqual(self.budget.last_pattern, 'wave')
        
        count = self.budget.track_pattern_repetition('wave')
        self.assertEqual(count, 2)
        
        count = self.budget.track_pattern_repetition('fractal')
        self.assertEqual(count, 1)
        self.assertEqual(self.budget.last_pattern, 'fractal')
    
    def test_track_reward_stagnation(self):
        """Test reward stagnation detection."""
        # Not enough history
        self.assertFalse(self.budget.track_reward_stagnation(0.5))
        
        # Fill window with similar values
        for _ in range(HardConfig.REWARD_STAGNATION_WINDOW):
            self.budget.reward_history.append(0.5)
        
        stagnant = self.budget.track_reward_stagnation(0.51)
        self.assertTrue(stagnant)
        
        # Add diverse value
        self.budget.track_reward_stagnation(0.9)
        stagnant = self.budget.track_reward_stagnation(0.5)
        self.assertFalse(stagnant)
    
    def test_should_reset(self):
        """Test reset decision logic."""
        # Fill reward history with stagnant values
        for _ in range(HardConfig.REWARD_STAGNATION_WINDOW):
            self.budget.reward_history.append(0.5)
        
        # Repeat pattern
        for _ in range(HardConfig.REPETITION_STAGNATION_THRESHOLD):
            self.budget.track_pattern_repetition('wave')
        
        self.assertTrue(self.budget.should_reset(0.5))
        
        # Persistence bonus prevents reset
        self.budget.give_persistence_bonus(0.75)
        self.assertFalse(self.budget.should_reset(0.5))
    
    def test_give_persistence_bonus(self):
        """Test persistence bonus grant."""
        self.assertEqual(self.budget.persistence_counter, 0)
        
        self.budget.give_persistence_bonus(0.6)
        self.assertEqual(self.budget.persistence_counter, 0)
        
        self.budget.give_persistence_bonus(0.75)
        self.assertEqual(self.budget.persistence_counter, HardConfig.PERSISTENCE_BONUS_CYCLES)


class TestMenteCuriosityExtraction(unittest.TestCase):
    """Test MenteCuriosity behavior matches archive implementation."""
    
    def setUp(self):
        self.world_model = PredictiveWorldModel(state_dim=36, action_dim=7)
        self.curiosity = MenteCuriosity(self.world_model)
    
    def test_initialization(self):
        """Test initial state."""
        self.assertEqual(self.curiosity.novelty_weight, 0.3)
        self.assertEqual(self.curiosity.prediction_weight, 0.7)
        self.assertFalse(hasattr(self.curiosity, 'visited_states'))
    
    def test_get_bonus_first_visit(self):
        """Test curiosity bonus for first state visit."""
        state = np.random.randn(36)
        self.world_model.prediction_error = 0.5
        
        bonus = self.curiosity.get_bonus(state, 'explore')
        
        # Should create visited_states
        self.assertTrue(hasattr(self.curiosity, 'visited_states'))
        
        # First visit has high novelty
        expected_novelty = 1.0 / (1.0 + 1)
        expected_bonus = 0.7 * 0.5 + 0.3 * expected_novelty
        self.assertAlmostEqual(bonus, expected_bonus, places=5)
    
    def test_get_bonus_repeated_visit(self):
        """Test curiosity bonus decreases with repeated visits."""
        state = np.random.randn(36)
        self.world_model.prediction_error = 0.5
        
        bonus1 = self.curiosity.get_bonus(state, 'explore')
        bonus2 = self.curiosity.get_bonus(state, 'explore')
        bonus3 = self.curiosity.get_bonus(state, 'explore')
        
        # Bonus should decrease with each visit
        self.assertGreater(bonus1, bonus2)
        self.assertGreater(bonus2, bonus3)
    
    def test_state_rounding(self):
        """Test state vectors are rounded for hashing."""
        state1 = np.array([0.501, 0.499])
        state2 = np.array([0.504, 0.496])
        
        self.world_model.prediction_error = 0.5
        
        self.curiosity.get_bonus(state1, 'explore')
        visit_count_1 = len(self.curiosity.visited_states)
        
        self.curiosity.get_bonus(state2, 'explore')
        visit_count_2 = len(self.curiosity.visited_states)
        
        # Should be same state after rounding
        self.assertEqual(visit_count_1, visit_count_2)


class TestMenteEventBusExtraction(unittest.TestCase):
    """Test MenteEventBus behavior matches archive implementation."""
    
    def test_initialization(self):
        """Test initial state."""
        bus = MenteEventBus()
        self.assertEqual(bus.listeners, {})
    
    def test_subscribe_and_emit(self):
        """Test event subscription and emission."""
        bus = MenteEventBus()
        events = []
        
        def handler(data):
            events.append(data)
        
        bus.subscribe('test_event', handler)
        bus.emit('test_event', {'value': 42})
        
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], {'value': 42})
    
    def test_multiple_listeners(self):
        """Test multiple listeners for same event."""
        bus = MenteEventBus()
        events1 = []
        events2 = []
        
        bus.subscribe('test', lambda d: events1.append(d))
        bus.subscribe('test', lambda d: events2.append(d))
        
        bus.emit('test', 'data')
        
        self.assertEqual(len(events1), 1)
        self.assertEqual(len(events2), 1)
    
    def test_different_event_types(self):
        """Test different event types are independent."""
        bus = MenteEventBus()
        events_a = []
        events_b = []
        
        bus.subscribe('event_a', lambda d: events_a.append(d))
        bus.subscribe('event_b', lambda d: events_b.append(d))
        
        bus.emit('event_a', 'A')
        bus.emit('event_b', 'B')
        
        self.assertEqual(events_a, ['A'])
        self.assertEqual(events_b, ['B'])
    
    def test_emit_nonexistent_event(self):
        """Test emitting event with no listeners doesn't error."""
        bus = MenteEventBus()
        bus.emit('nonexistent', 'data')  # Should not raise


if __name__ == '__main__':
    unittest.main()
