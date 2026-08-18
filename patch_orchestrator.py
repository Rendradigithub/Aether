import sys

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # 1. Update workspace.mkdir
    content = content.replace("self.workspace.mkdir(parents=True)", "self.workspace.mkdir(parents=True, exist_ok=True)")
    
    # 2. Check emergency before action selection
    target_emergency = '''        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.budget.energy <= 10 or self.budget.attention <= 10:
            feasible = ['rest']'''
    
    replacement_emergency = '''        feasible = list(HardConfig.ACTION_COSTS.keys())
        if self.budget.is_emergency() or self.budget.energy <= 10 or self.budget.attention <= 10:
            feasible = ['rest']'''
    
    content = content.replace(target_emergency, replacement_emergency)

    # 3. Add state_t capture and refactor actions
    # We will replace the entire step() action block from "art, pat = None, None" downwards.
    # To do this safely, we locate the "chosen = max(utils, key=utils.get)" and "def _log_step" boundaries.
    
    start_str = "        chosen = max(utils, key=utils.get)\n\n"
    end_str = "    def _log_step("
    
    start_idx = content.find(start_str)
    end_idx = content.find(end_str)
    if start_idx == -1 or end_idx == -1:
        print(f"Failed to find step block in {filepath}")
        return
    
    start_idx += len(start_str)
    
    new_action_block = '''        state_t = self.current_state.tolist() if hasattr(self.current_state, 'tolist') else self.current_state
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
                pred = self.decoder.predict_params(self._representation_vector(self.stimulus_representation))
                self.generator.set_params(pred)
            art, pat = self.generator.generate(set())
            self.pattern_counts[pat] += 1
            total_reward, radial_sim, contour_reward, coherence = self._compute_reward(art, pat)
            if pat == 'shape' and contour_reward > 0.7:
                total_reward = min(1.0, total_reward + 0.1)
                self.budget.recover(3, 2, 3)
                self.budget.give_persistence_bonus(total_reward)
            next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
            self.world_model.update(self.current_state, chosen, next_sig)
            self.current_state = next_sig
            if pat == 'shape':
                self.decoder.collect_sample(self._representation_vector(self.stimulus_representation), self.generator.params)
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
                import random as rnd
                exp = rnd.choice(list(self.memory.working))
                other_params = exp.get('metadata', {}).get('params', self.generator.params)
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
            old_energy = self.budget.energy
            old_attention = self.budget.attention
            old_burden = self.budget.failure_burden
            self.budget.recover(12, 15, 12)
            energy_gain = min(12, self.budget.max_energy - old_energy)
            attention_gain = min(15, self.budget.max_attention - old_attention)
            burden_reduced = old_burden - self.budget.failure_burden
            total_reward = min(1.0, 0.2 + 0.4*(energy_gain/12.0) + 0.4*(attention_gain/15.0))
            radial_sim = 0.5
            contour_reward = 0.5
            coherence = 0.5
            # current_state unchanged

        elif chosen == 'recall':
            self.budget.spend(2, 2, 1)
            query = {'pattern': self.generator.params.get('pattern'), 'contour_reward': 0.8}
            recalled = self.memory.recall_similar(query, k=1)
            if recalled:
                exp = recalled[0]
                if 'metadata' in exp and 'params' in exp['metadata']:
                    self.generator.params.update(exp['metadata']['params'])
            total_reward = 0.6 if recalled else 0.5
            radial_sim = 0.5
            contour_reward = 0.5
            coherence = 0.5

        elif chosen == 'forget':
            self.budget.spend(2, 2, 1)
            if len(self.memory.working) > 0:
                import collections
                self.memory.working = collections.deque([exp for exp in self.memory.working if exp['metadata'].get('contour_reward', 0) >= 0.4], maxlen=self.memory.working.maxlen)
            total_reward = 0.5
            radial_sim = 0.5
            contour_reward = 0.5
            coherence = 0.5

        self.budget.update_failure_burden(total_reward)
        self.budget.regen(chosen == 'rest')
        self.budget.reward_history.append(total_reward)
        
        if pat:
            self.budget.track_pattern_repetition(pat)
            
        state_t_plus_1 = self.current_state.tolist() if hasattr(self.current_state, 'tolist') else self.current_state
        self.memory.add_experience(
            state_t,
            chosen,
            total_reward,
            state_t_plus_1,
            {
                'pattern': pat,
                'contour_reward': contour_reward,
                'coherence': coherence,
                'params': self.generator.params.copy()
            }
        )

        self._log_step(art, total_reward, radial_sim, contour_reward, coherence, pat if art else chosen)
        return art, total_reward, radial_sim, pat

'''
    
    content = content[:start_idx] + new_action_block + content[end_idx:]

    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Patched {filepath}")

patch_file('src/aether/orchestrator.py')
patch_file('archive/versions/aether.0.20.0.py')
