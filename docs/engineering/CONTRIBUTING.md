# Contributing to Aether

Thank you for contributing to Aether.

This project is built as a long-term engineering and research effort.

The primary goal is not rapid feature development, but building a maintainable autonomous intelligence through careful experimentation and disciplined engineering.

Every contribution should improve the project without increasing unnecessary complexity.

---

# Core Principles

Before writing code, understand the architecture.

Before changing the architecture, understand the research.

Before making assumptions, perform experiments.

---

# Contribution Workflow

Every contribution should follow the same lifecycle.

```
Understand

↓

Design

↓

Implement

↓

Test

↓

Document

↓

Review
```

Skipping any of these steps increases technical debt.

---

# Before You Start

Before implementing anything:

- Read `docs/README.md`
- Read `docs/engineering/ARCHITECTURE.md`
- Understand the affected module.
- Search for existing experiments related to your idea.

Avoid implementing solutions that already exist.

---

# Coding Principles

Code should be:

- Readable
- Predictable
- Modular
- Testable

Prefer clarity over cleverness.

Code is read far more often than it is written.

---

# Keep Changes Small

Large changes should be divided into smaller logical steps.

Small changes are:

- easier to review
- easier to test
- easier to revert
- easier to understand

---

# Respect Module Boundaries

Every module has a defined responsibility.

Do not move unrelated logic into an existing module simply because it is convenient.

If a feature introduces a new responsibility, consider creating a new module instead.

Refer to:

```
engineering/architecture/MODULE_BOUNDARIES.md
```

---

# Avoid Premature Optimization

Do not optimize without evidence.

Optimization requires measurable bottlenecks.

Performance improvements should be supported by benchmarks or experiments whenever possible.

---

# Documentation

Documentation is part of the implementation.

Every significant change should update the relevant documentation.

Possible updates include:

- Architecture
- Public APIs
- Research notes
- Changelog

If documentation becomes incorrect after your change, update it immediately.

---

# Testing

Every contribution should be tested at an appropriate level.

Possible tests include:

- Unit tests
- Integration tests
- Simulation
- Hardware validation
- Manual verification

Untested code should not be considered complete.

---

# Experiments

Experimental features should not be treated as production architecture.

Record experiments inside:

```
docs/research/
```

Do not replace architectural decisions with experimental assumptions.

Research comes first.

Architecture follows evidence.

---

# Breaking Changes

Breaking changes are allowed only when they provide clear long-term benefits.

When introducing a breaking change:

- Explain why.
- Describe the migration path.
- Update migration documentation.
- Update affected APIs.

---

# Pull Requests

A contribution should answer these questions clearly:

- What problem does this solve?
- Why is this solution appropriate?
- What alternatives were considered?
- Does this change affect the architecture?
- Does this require new documentation?
- Does this introduce technical debt?

---

# AI Contributions

AI-generated code is welcome.

However, AI-generated code is held to the same standards as human-written code.

Every generated implementation must be:

- understood
- verified
- tested
- documented

Generated code should never be merged without review.

---

# Definition of Done

A contribution is considered complete only if:

- The implementation works.
- Tests pass.
- Documentation is updated.
- Module boundaries remain respected.
- No unnecessary complexity has been introduced.
- The project is easier to maintain than before.

Completion is measured by maintainability, not by the number of lines of code added.