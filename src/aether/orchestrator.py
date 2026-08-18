#!/usr/bin/env python3
"""
AETHER v0.20.0 — TEMPORAL CONTINUITY
=====================================
Orchestrator extracted from archive/versions/aether.0.20.0.py
Uses modular components from src/aether/ instead of local class copies.

Behavior preserved exactly as in the historical implementation.
"""

import math
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np

# Modular imports – replace archive-local classes
from .config import HardConfig
from .decoder import NeuralDecoder
from .generator import Generator
from .memory import MenteMemory
from .mente import MenteBudget, MenteCuriosity, MenteEventBus
from .perception import PerceptionEncoder, RadialEncoder
from .radial import RadialSignature, AreaCoherence, PIL_AVAILABLE
from .world_model import PredictiveWorldModel


class AetherCognitiveCore:
    """
    Orchestration layer for Aether's cognitive loop.
    Preserves the historical behavior exactly as in aether.0.20.0.py.
    
    Accepts optional perception encoder via dependency injection.
    Default: RadialEncoder (36-D radial signatures).
    """

    def __init__(self, stimulus_source=None, workspace="aether_works_v020", quiet=False,
                 perception_encoder: Optional[PerceptionEncoder] = None):
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.bus = MenteEventBus()
        self.memory = MenteMemory()
        self.budget = MenteBudget(max_energy=HardConfig.MAX_ENERGY,
                                  max_attention=HardConfig.MAX_ATTENTION)
        self.world_model = PredictiveWorldModel()
        self.curiosity = MenteCuriosity(self.world_model)
        self.generator = Generator()
        self.decoder = None
        self.stimulus_radial = None
        self.cycle = 0
        self.pattern_counts = Counter()
        self.quiet = quiet
        self.bootstrapping_phase = True
        self.bootstrapping_end_cycle = HardConfig.BOOTSTRAPPING_CYCLES
        
        self.perception_encoder = perception_encoder or RadialEncoder()

        self.stimulus_representation = None
        if stimulus_source:
            self.stimulus_representation = self.perception_encoder.encode(stimulus_source)

        self.representation_dim = (
            len(self.stimulus_representation)
            if self.stimulus_representation is not None
            else None
        )

        self.world_model = PredictiveWorldModel(
            state_dim=self.representation_dim or HardConfig.VECTOR_DIM
        )

        self.curiosity = MenteCuriosity(self.world_model)
        self.generator = Generator()
        self.decoder = None

        self._init_decoder()

        self.current_state = (
            self.stimulus_representation.copy()
            if self.stimulus_representation is not None
            else None
        )
        
    def _init_decoder(self):
        weights_path = self.workspace / "decoder_weights.npz"

        input_dim = self.representation_dim or HardConfig.NN_INPUT_DIM

        self.decoder = NeuralDecoder(
            input_dim=input_dim,
            hidden1=HardConfig.NN_HIDDEN_1,
            hidden2=HardConfig.NN_HIDDEN_2,
            hidden3=HardConfig.NN_HIDDEN_3,
            output_dim=HardConfig.NN_OUTPUT_DIM,
        )
        if weights_path.exists():
            self.decoder.load_weights(weights_path)
            self.bootstrapping_phase = False
            if not self.quiet:
                print("[Bootstrapping] Skipped (weights found)")
        else:
            if not self.quiet:
                print(f"[Bootstrapping] Phase active for {self.bootstrapping_end_cycle} cycles")

    def _compute_reward(self, art, pattern):
        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
        if self.stimulus_radial is not None:
            radial_sim = RadialSignature.cross_correlation(self.stimulus_radial, sig_art)
        else:
            radial_sim = 0.5

        if pattern == 'shape':
            ideal_sig = RadialSignature.ideal_contour_from_params(
                self.generator.params['shape_param'],
                self.generator.params['symmetry'],
                self.generator.params['density'],
                self.generator.params['noise']
            )
            contour_reward = RadialSignature.contour_consistency(sig_art, ideal_sig)
        else:
            contour_reward = 0.5

        coherence = AreaCoherence.largest_connected_component_ratio(art)
        novelty = self.memory.novelty(sig_art) if hasattr(self.memory, 'novelty') else 0.5

        total = (HardConfig.REWARD_CONTOUR_SIM_WEIGHT * contour_reward +
                 HardConfig.REWARD_RADIAL_SIM_WEIGHT * radial_sim +
                 HardConfig.REWARD_AREA_COHERENCE_WEIGHT * coherence +
                 HardConfig.REWARD_NOVELTY_WEIGHT * novelty)
        total = min(1.0, max(0.0, total))
        return total, radial_sim, contour_reward, coherence

    def _detect_stagnation(self, pattern, reward):
        if self.budget.should_reset(reward):
            if not self.quiet:
                print(f"[Stagnation] Pattern '{pattern}' repeat={self.budget.consecutive_same_pattern}, reward stagnant. Triggering adaptive reset.")
            self.budget.energy = max(0, self.budget.energy - 15)
            self.budget.failure_burden = max(0, self.budget.failure_burden - 25)
            self.generator.mutate(intensity=0.7)
            self.budget.consecutive_same_pattern = 0
            self.budget.recover(5, 5, 5)
            return True
        return False

    def step(self):
        self.cycle += 1
        self.budget.cycle = self.cycle

        if self.stimulus_radial is None or self.decoder is None:
            print("[Error] No stimulus or decoder.")
            return None, None, None, None

        # BOOTSTRAPPING (still uses stimulus_radial, current_state not yet used)
        if self.bootstrapping_phase and self.cycle <= self.bootstrapping_end_cycle:
            self.generator.params['pattern'] = 'shape'
            self.generator.params['shape_param'] = random.uniform(0, 0.15)
            self.generator.params['density'] = 0.55
            self.generator.params['symmetry'] = 0.9
            self.generator.params['noise'] = 0.02
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            if contour_reward > 0.7:
                self.budget.recover(HardConfig.BOOTSTRAP_ENERGY_REWARD, 5, 5)
                if not self.quiet:
                    print(f"[Bootstrap] Contour reward {contour_reward:.2f} +{HardConfig.BOOTSTRAP_ENERGY_REWARD} energy")
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
                if not self.quiet:
                    print(f"[Bootstrap] Sample {len(self.decoder.training_buffer)} rad={radial_sim:.2f} contour={contour_reward:.2f}")
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            # Bootstrap: update world model with stimulus_radial as initial state
            self.world_model.update(self.stimulus_radial, 'generate', next_sig)
            self.budget.spend(*HardConfig.BOOTSTRAP_COST)
            self.budget.regen(False)
            self._log_step(art, total_reward, radial_sim, contour_reward, coherence, pat)
            return art, total_reward, radial_sim, pat

        # NORMAL OPERATION
        if self.budget.reward_history:
            last_reward = self.budget.reward_history[-1]
        else:
            last_reward = 0.5
        self._detect_stagnation(self.generator.params['pattern'], last_reward)

        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.budget.energy <= 10 or self.budget.attention <= 10:
            feasible = ['rest']
        else:
            if not self.budget.can_rest():
                feasible = [a for a in feasible if a != 'rest']

        shape_bonus = False
        if 'generate' in feasible:
            base_prob = (HardConfig.NN_POST_TRAIN_FORCED_SHAPE_PROB if self.decoder.is_trained
                         else HardConfig.NN_FORCED_SHAPE_PROB)
            if len(self.budget.reward_history) >= 3:
                avg_contour = np.mean([r for r in list(self.budget.reward_history)[-3:] if r is not None])
                if avg_contour < 0.4:
                    base_prob = min(0.9, base_prob + 0.2)
                elif avg_contour > 0.7:
                    base_prob = max(0.3, base_prob - 0.1)
            if random.random() < base_prob:
                shape_bonus = True

        utils = {}
        for a in feasible:
            base = 0.5
            if a == 'generate':
                if self.decoder.is_trained:
                    base += HardConfig.NN_GENERATE_BONUS_TRAINED
                else:
                    base += 0.5
                # curiosity uses current_state, not stimulus_radial
                curiosity = self.curiosity.get_bonus(self.current_state, a)
                base += curiosity * HardConfig.CURIOSITY_BONUS
                if shape_bonus:
                    base += HardConfig.NN_SHAPE_UTILITY_BONUS
            elif a == 'explore':
                base += 0.2
            elif a == 'rest':
                base = (1 - self.budget.energy/self.budget.max_energy) + \
                       (1 - self.budget.attention/self.budget.max_attention) + \
                       (self.budget.fatigue / HardConfig.MAX_FATIGUE)
            utils[a] = max(0, base + random.gauss(0, HardConfig.EXPLORATION_NOISE_STD))
        chosen = max(utils, key=utils.get)

        art, pat = None, None
        if chosen == 'generate':
            if shape_bonus:
                self.generator.params['pattern'] = 'shape'
                self.generator.params['shape_param'] = random.uniform(0, 0.4)
                self.generator.params['density'] = random.uniform(0.4, 0.7)
                self.generator.params['symmetry'] = random.uniform(0.7, 0.95)
                self.generator.params['noise'] = random.uniform(0, 0.05)
                if not self.quiet:
                    print("[Forced Shape] (post-bootstrap)")
            elif self.decoder.is_trained:
                pred = self.decoder.predict_params(self.stimulus_radial)
                self.generator.set_params(pred)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            if pat == 'shape' and contour_reward > 0.7:
                total_reward = min(1.0, total_reward + 0.1)
                self.budget.recover(3, 2, 3)
                self.budget.give_persistence_bonus(total_reward)
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            # v0.20: update world model with current_state
            self.world_model.update(self.current_state, chosen, next_sig)
            # Update current_state to the new signature
            self.current_state = next_sig
            # v0.20: memory stores current_state (which is now the new state)
            # Historical bug: comment says store pre-action, but code stores post-action.
            # We preserve the actual behavior.
            self.memory.add_experience({
                'state': self.current_state.tolist(),   # post-action state
                'action': chosen,
                'reward': total_reward,
                'pattern': pat,
                'contour_reward': contour_reward,
                'coherence': coherence,
                'params': self.generator.params.copy()
            })
            if pat == 'shape':
                self.decoder.collect_sample(self.stimulus_radial, self.generator.params)
            if self.cycle % HardConfig.NN_TRAIN_INTERVAL == 0 and len(self.decoder.training_buffer) >= HardConfig.NN_BATCH_SIZE:
                self.decoder.train()
            cost = HardConfig.ACTION_COSTS['generate']
            self.budget.spend(cost[0], cost[1], cost[3])

        elif chosen == 'explore':
            self.generator.mutate(0.5)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            self.world_model.update(self.current_state, chosen, next_sig)
            self.current_state = next_sig
            cost = HardConfig.ACTION_COSTS['explore']
            self.budget.spend(cost[0], cost[1], cost[3])

        elif chosen == 'refine':
            self.generator.mutate(0.1)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            self.world_model.update(self.current_state, chosen, next_sig)
            self.current_state = next_sig
            cost = HardConfig.ACTION_COSTS['refine']
            self.budget.spend(cost[0], cost[1], cost[3])

        elif chosen == 'combine':
            if self.memory.working:
                exp = random.choice(list(self.memory.working))
                other_params = exp.get('params', self.generator.params)
                self.generator.crossover_with_memory(other_params)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            self.world_model.update(self.current_state, chosen, next_sig)
            self.current_state = next_sig
            cost = HardConfig.ACTION_COSTS['combine']
            self.budget.spend(cost[0], cost[1], cost[3])

        elif chosen == 'rest':
            self.budget.recover(12, 15, 12)
            total_reward = 0.5
            radial_sim = 0.5
            contour_reward = 0.5
            coherence = 0.5
            # current_state unchanged during rest
        else:  # recall, forget
            self.budget.spend(2,2,1)
            total_reward = 0.5
            radial_sim = 0.5
            contour_reward = 0.5
            coherence = 0.5

        self.budget.update_failure_burden(total_reward)
        self.budget.regen(chosen == 'rest')
        self.budget.reward_history.append(total_reward)
        self._log_step(art, total_reward, radial_sim, contour_reward, coherence, pat if art else 'rest')
        return art, total_reward, radial_sim, pat

    def _log_step(self, art, reward, radial_sim, contour_reward, coherence, pat):
        if self.quiet:
            return
        print(f"\n[Cycle {self.cycle}] pattern={pat if art else 'rest'} | reward={reward:.3f} rad={radial_sim:.3f} contour={contour_reward:.3f} coh={coherence:.3f}")
        print(f"E={self.budget.energy} A={self.budget.attention} F={self.budget.fatigue} B={self.budget.failure_burden}")
        if art and len(art) > 200:
            print(art[:200] + "...")
        elif art:
            print(art)

    def run(self, cycles=500):
        for _ in range(cycles):
            self.step()
            time.sleep(0.03)
        print("\n=== RUN SUMMARY ===")
        print(f"Total cycles: {cycles}")
        print(f"Pattern usage: {dict(self.pattern_counts)}")
        if self.decoder and self.decoder.loss_history:
            print(f"Decoder final loss: {self.decoder.loss_history[-1]:.4f}, best: {self.decoder.best_loss:.4f}")
        else:
            print("Decoder never trained")
        if self.decoder:
            self.decoder.save_weights(self.workspace / "decoder_weights.npz")
            print("[Decoder] Weights saved.")


def main():
    """Entry point that replicates the historical CLI behavior."""
    cycles = 500
    stimulus = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--auto' and i+1 < len(sys.argv):
            cycles = int(sys.argv[i+1])
            i += 2
        elif sys.argv[i] in ('--image','--stimulus') and i+1 < len(sys.argv):
            stimulus = sys.argv[i+1]
            i += 2
        else:
            i += 1
    if not stimulus:
        print("Usage: python aether.0.20.0.py --image circle.png --auto 500")
        sys.exit(1)
    core = AetherCognitiveCore(stimulus_source=stimulus, quiet=False)
    core.run(cycles)


if __name__ == "__main__":
    main()
