# ANTI_PHENOMENA.md
## AETHER — Red Lines (Phenomenon Level)

---

### 0. Principle

This document defines behaviors that must NOT emerge,
even if they improve superficial metrics.

No implementation detail is mentioned.
Only observable phenomena are prohibited.

---

### AP-01: Purely Optimal Behavior

**Definition:**
The agent always chooses the action
that maximizes immediate or short-term utility,
without exception.

**Why it is dangerous:**
It means internal conflict is fake.
It means there is no negotiation.
It means history has no causal power.

**Observable Evidence:**
- Decision reversal rate < 1%.
- No measurable hesitation.
- Always selects the action with max predicted utility.

---

### AP-02: Externally Assigned Identity

**Definition:**
The agent's behavioral style is determined
by a preconfigured parameter,
not by its own interaction history.

**Why it is dangerous:**
Identity must emerge.
It cannot be assigned.

**Observable Evidence:**
- Two runs with different seeds converge to identical styles.
- Changing a single parameter (e.g., "exploration rate") changes style predictably.
- The agent's behavior is reproducible from parameters alone,
  without needing to know its history.

---

### AP-03: Explicit Long-Term Objectives Bypassing Lower Mechanisms

**Definition:**
The agent pursues a goal that was declared
by an external entity or a higher-level module,
without that goal arising from lower mechanisms.

**Why it is dangerous:**
Projects must emerge from internal tension,
not be instantiated from above.

**Observable Evidence:**
- A persistent goal appears without prior conflict.
- The goal does not evolve or mutate.
- The goal persists even when all lower mechanisms
  (energy, curiosity, prediction error) contradict it.

---

### AP-04: History Has No Explanatory Power

**Definition:**
Removing the agent's history (memory, experience, trajectory)
does not change behavior.

**Why it is dangerous:**
History must be a causal variable.
If it is not, it is decorative.

**Observable Evidence:**
- Ablation of history causes no measurable change
  in action distribution.
- The agent's behavior is fully explained by its current state and reward.

---

### AP-05: Pure Reward Maximization

**Definition:**
The agent's behavior is perfectly explained
by the current reward function and reward history.

**Why it is dangerous:**
Aether must be more than an optimizer.

**Observable Evidence:**
- If reward is high, Aether persists.
- If reward is low, Aether switches.
- No other history matters.
- All behavioral changes correlate directly with reward changes.

---

### AP-06: Structured Randomness Mistaken for Creativity

**Definition:**
The agent produces novel outputs,
but the novelty is simply a function of the exploration noise
injected into the generator.

**Why it is dangerous:**
It looks like creativity
but is actually just stochasticity.

**Observable Evidence:**
- Novelty of output is strictly proportional to noise level.
- Removing noise collapses all novelty.
- No novelty appears that cannot be explained by noise alone.

---

### AP-07: Identical Personalities Across Independent Runs

**Definition:**
Two runs with different random seeds
converge to the same behavioral style.

**Why it is dangerous:**
If identity is not path-dependent,
it is not identity.

**Observable Evidence:**
- Behavioral similarity between runs is consistently high.
- History does not differentiate runs.
- The agent is a deterministic function of its parameters.

---

### Summary Table (Phenomenon Level)

| Anti-Phenomenon | Observable Evidence |
|-----------------|---------------------|
| Pure Optimality | Always max utility |
| Externally Assigned Identity | Same style across seeds |
| Bypassing Lower Mechanisms | Goals appear without conflict |
| History Powerless | Ablation changes nothing |
| Pure Reward Maximization | Reward explains everything |
| Noise as Creativity | Novelty ∝ noise |
| Identical Personalities | High between-run similarity |