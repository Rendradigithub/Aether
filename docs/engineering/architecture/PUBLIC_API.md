# Public API

---

# Purpose

This document defines the public interfaces between Aether's core modules.

A public API represents the only approved communication channel between modules.

Modules should interact through these interfaces rather than accessing each other's internal implementation.

Stable interfaces reduce coupling and allow implementations to evolve independently.

---

# Design Principles

Every public interface should be:

- Minimal
- Explicit
- Predictable
- Versionable
- Independent of implementation

An API describes *what* is available.

It does not describe *how* it is implemented.

---

# Communication Model

```
Module A

↓

Public API

↓

Module B
```

Modules never communicate through internal state.

Only public interfaces are considered stable.

---

# Perception API

Purpose:

Provide observations collected from the environment.

Provides:

- Sensor observations
- Camera observations
- Audio observations
- User input
- Internal events

Consumers:

- Interpretation

Perception never exposes hardware implementation details.

---

# Interpretation API

Purpose:

Provide structured understanding of observations.

Provides:

- Recognized entities
- Estimated state
- Context
- Environmental interpretation

Consumers:

- Memory
- Decision Engine

Interpretation never exposes raw sensor processing.

---

# Memory API

Purpose:

Provide access to stored knowledge.

Provides:

- Current world state
- Historical experiences
- Learned knowledge
- Context retrieval

Consumers:

- Decision Engine
- Planning

Memory owns persistence.

Other modules must never modify stored information directly.

---

# Decision Engine API

Purpose:

Expose current intentions and selected goals.

Provides:

- Current goal
- Prioritized actions
- Decision output

Consumers:

- Action Planner

Decision Engine does not expose internal reasoning mechanisms.

Only decisions.

---

# Action Planner API

Purpose:

Transform intentions into executable plans.

Provides:

- Action sequences
- Execution plans
- Resource allocation

Consumers:

- Execution

Planning should remain implementation independent.

---

# Execution API

Purpose:

Execute validated plans.

Provides:

- Execution status
- Completion events
- Failure events

Consumers:

- Perception
- Diagnostics

Execution never exposes device-specific implementation.

---

# Event Interfaces

Certain communications are event-driven.

Examples include:

- Observation received
- Goal completed
- Plan failed
- Sensor disconnected
- Hardware fault
- Learning completed

Events describe what happened.

Events should never describe how it happened.

---

# Query Interfaces

Some interactions require requesting information.

Typical examples:

```
Decision Engine

↓

Memory

↓

Retrieve context
```

Queries should return information only.

They should never modify system state.

---

# Command Interfaces

Commands request an action.

Typical examples:

```
Planner

↓

Execution

↓

Execute plan
```

Commands may change system state.

Commands should be explicit and deterministic.

---

# Ownership Rules

Each API owns its own contract.

Internal implementation may change freely.

Breaking an interface requires:

- Architectural review
- Migration documentation
- Changelog update

---

# Versioning

Public APIs should evolve conservatively.

Preferred order:

1. Extend existing interfaces.
2. Deprecate obsolete functionality.
3. Remove deprecated interfaces only after migration.

Avoid unnecessary breaking changes.

---

# Error Handling

Public interfaces should communicate failures explicitly.

Possible outcomes include:

- Success
- Failure
- Timeout
- Invalid request
- Resource unavailable

Failures should never be hidden.

Silent failure increases system uncertainty.

---

# Security

Modules should expose only the minimum information required.

Do not expose:

- Internal state
- Private implementation
- Temporary objects
- Debug-only interfaces

Every exposed interface becomes part of the long-term architecture.

---

# API Evolution

When introducing a new interface:

- Define its responsibility.
- Identify its consumers.
- Minimize dependencies.
- Document expected behavior.
- Update architecture documentation if necessary.

Interfaces should evolve slower than implementations.

---

# Final Principle

Modules may change.

Algorithms may change.

Technologies may change.

Public interfaces should remain as stable as possible.

A stable architecture is built upon stable contracts, not stable implementations.