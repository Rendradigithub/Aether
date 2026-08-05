# BASELINE.md
## AETHER — v0.19 Characterization

---

### 0. Purpose

This document establishes the baseline behavior of v0.19
**before any experiment begins**.

All thresholds for falsification will be derived from this baseline.

Thresholds are locked after this document is finalized.

---

### 1. Baseline Runs

**Protocol:**
- Run v0.19 with 100 different seeds.
- Each run: 500 cycles.
- Record all metrics.

**Metrics to Record:**
- Action autocorrelation (lag-1 to lag-5)
- Behavioral entropy
- Decision reversal rate
- Conflict duration
- Identity stability (cosine similarity between consecutive blocks)
- Simulation usage (N/A for v0.19 — baseline = 0)
- History dependence (predictive power of history)

---

### 2. Baseline Statistics

*To be filled after runs.*

| Metric | Mean | Std Dev | 95% CI |
|--------|------|---------|--------|
| Autocorrelation lag-1 | ... | ... | ... |
| Autocorrelation lag-2 | ... | ... | ... |
| Autocorrelation lag-3 | ... | ... | ... |
| Autocorrelation lag-4 | ... | ... | ... |
| Autocorrelation lag-5 | ... | ... | ... |
| Behavioral Entropy | ... | ... | ... |
| Decision Reversal Rate | ... | ... | ... |
| Conflict Duration | ... | ... | ... |
| Identity Stability | ... | ... | ... |
| History Dependence | ... | ... | ... |

---

### 3. Threshold Definition

Based on baseline statistics:

- **Measurable Increase:**
  > Mean + 2 x Std Dev
  (i.e., beyond normal variation)

- **Meaningful Increase:**
  > Mean + 3 x Std Dev
  (i.e., compelling evidence)

These thresholds are **frozen** after this document is finalized.

No post-hoc adjustment.

---

### 4. Conclusion

If an experiment produces an effect
that is **not distinguishable from baseline variation**,
the hypothesis is rejected.

If an experiment produces an effect
that is **clearly above baseline variation**,
the hypothesis is supported.

---

### 5. Update Policy

This document is updated **only** when:

1. A new version (v0.20, v0.21, ...) is released.
2. The baseline characteristics of that version are established.

No updates are made during an experiment cycle.