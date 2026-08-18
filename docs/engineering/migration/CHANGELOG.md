# Changelog

All notable architectural and engineering changes to Aether are documented in this file.

This changelog records meaningful evolution of the project.

Minor implementation details, bug fixes, formatting changes, and routine maintenance should remain in version control history rather than this document.

---

# Changelog Format

Each entry should include:

- Date
- Version (if applicable)
- Category
- Summary
- Motivation
- Impact

Template:

```text
## YYYY-MM-DD

Category:
Architecture | Module | API | Research | Migration | Hardware | Documentation

Summary:
A brief description of the change.

Motivation:
Why the change was made.

Impact:
What changed for the project.
```

---

# Categories

## Architecture

Changes affecting the overall system structure.

Examples:

- New subsystem introduced
- Major architectural redesign
- Core workflow changes

---

## Module

Changes affecting module responsibilities.

Examples:

- New module added
- Module removed
- Responsibility reassigned

---

## Public API

Changes affecting communication between modules.

Examples:

- New interface
- Deprecated interface
- Breaking API changes

---

## Migration

Major migration milestones.

Examples:

- Legacy system removed
- New architecture adopted
- Compatibility layer introduced

---

## Research

Changes driven by validated experimental results.

Examples:

- New architectural direction
- Rejected hypothesis
- Research milestone

---

## Hardware

Major hardware-related changes.

Examples:

- New sensor platform
- New actuator system
- Computing platform migration

---

## Documentation

Major documentation milestones.

Examples:

- Documentation structure redesigned
- Engineering standards introduced
- Research methodology updated

---

# Entries

## 2026-08-16

Category:
Migration

Summary:
Completed experiment cleanup: migrated experiment_trace.py to modular orchestrator API and removed obsolete experiment_two_cycles.py.

Motivation:
Legacy experiments were using runpy to load archive/versions/aether.0.20.0.py instead of the active modular runtime. This created a disconnect between the research code and the actual production implementation, making experiments unreliable and difficult to maintain.

Impact:
- `experiment_trace.py` now imports and uses AetherCognitiveCore directly from src.aether.orchestrator.
- Removed `experiment_two_cycles.py` as redundant (functionality covered by existing test suite).
- Eliminated runpy-based archive execution from experiment scripts.
- Experiments now run against the actual modular implementation, ensuring consistency between research and production code.

---

## 2026-08-14

Category:
Migration

Summary:
Migrated the active Aether runtime from the historical archive implementation to the modular orchestrator.

Motivation:
Complete the transition from archive-based execution to the modular architecture while preserving the established runtime behavior.

Impact:
`src/aether/core.py` now delegates directly to the modular orchestrator instead of executing the historical archive. Behavioral equivalence was verified through component tests, 3-cycle parity, 60-cycle extended parity, `run()` parity, decoder weight persistence checks, and a CLI smoke test. The full test suite passed with 56 tests.

The historical archive remains available as a reference and regression baseline rather than as part of the active runtime path.

---

## 2026-08-06

Category:
Documentation

Summary:
Established the initial engineering documentation structure.

Motivation:
Create a stable knowledge base for long-term development and AI-assisted engineering.

Impact:
Introduced foundational engineering documents, including architecture, module boundaries, public APIs, testing guidelines, migration protocol, inventory, and changelog.

---

# Writing Guidelines

A changelog entry should describe **what changed**, not **how it was implemented**.

Prefer:

> Introduced a dedicated Decision Engine module.

Instead of:

> Added `decision_engine.py` with 437 lines of code.

---

# What Belongs Here

Include:

- Architectural milestones
- New subsystems
- Major refactoring
- Interface changes
- Migration milestones
- Research-driven engineering decisions

Do not include:

- Variable renames
- Formatting changes
- Small bug fixes
- Comment updates
- Dependency version bumps
- Routine maintenance

Those belong in version control history.

---

# Relationship to Research

When a change is motivated by experimental evidence:

1. Record the experiment in `docs/research/`.
2. Record the architectural consequence here.
3. Update architecture documentation if required.

Research explains *why*.

The changelog records *what* changed.

---

# Final Principle

The purpose of this changelog is not to preserve every modification.

Its purpose is to preserve the evolution of Aether.

A reader should be able to understand how the project changed over time without reading the complete commit history.
