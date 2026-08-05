# System Inventory

---

# Purpose

This document provides a high-level inventory of Aether's major systems, modules, and architectural assets.

It serves as the project's master index, allowing contributors to quickly understand what currently exists, what is planned, and what has been retired.

Detailed implementation belongs elsewhere.

This document only records the current architectural inventory.

---

# Status Definitions

| Status | Meaning |
|----------|---------|
| Planned | Intended but not yet implemented. |
| In Progress | Currently under active development. |
| Active | Stable and actively maintained. |
| Experimental | Research or prototype stage. |
| Deprecated | Scheduled for removal. |
| Removed | No longer part of the architecture. |

---

# Core Architecture

| Module | Status | Description |
|---------|--------|-------------|
| Perception | Planned | Observes the environment through sensors and external inputs. |
| Interpretation | Planned | Converts observations into structured understanding. |
| Memory | Planned | Maintains knowledge across time. |
| Decision Engine | Planned | Determines the next objective or action. |
| Action Planner | Planned | Converts decisions into executable plans. |
| Execution | Planned | Interacts with the physical or digital environment. |

---

# Infrastructure

| Component | Status | Description |
|------------|--------|-------------|
| Logging | Planned | Centralized event logging. |
| Configuration | Planned | Runtime configuration management. |
| Diagnostics | Planned | Internal system diagnostics. |
| Telemetry | Planned | Performance and runtime monitoring. |

---

# Research Systems

| Component | Status | Description |
|------------|--------|-------------|
| Experiment Framework | Planned | Standardized experiment workflow. |
| Research Database | Planned | Stores experimental records. |
| Knowledge Base | Planned | Structured engineering and research knowledge. |

---

# Hardware

| Component | Status | Description |
|------------|--------|-------------|
| Processing Unit | Planned | Primary onboard computing platform. |
| Sensors | Planned | Environmental observation devices. |
| Actuators | Planned | Physical interaction hardware. |
| Power System | Planned | Energy supply and management. |
| Communication | Planned | External communication interfaces. |

---

# External Interfaces

| Interface | Status | Description |
|------------|--------|-------------|
| Human Interaction | Planned | Communication between users and Aether. |
| Hardware Drivers | Planned | Communication with physical devices. |
| External APIs | Planned | Integration with external systems. |

---

# Documentation

| Document | Status |
|-----------|--------|
| README | Active |
| ARCHITECTURE | Active |
| MODULE_BOUNDARIES | Active |
| PUBLIC_API | Active |
| CONTRIBUTING | Active |
| TESTING | Active |
| MIGRATION_PROTOCOL | Active |
| INVENTORY | Active |
| CHANGELOG | Planned |

---

# Inventory Rules

When introducing a new architectural component:

1. Add it to this inventory.
2. Assign an initial status.
3. Provide a concise description.
4. Update the architecture documentation if necessary.

When removing a component:

- Do not delete its inventory entry immediately.
- Change its status to **Deprecated** or **Removed**.
- Record the migration in `CHANGELOG.md`.

---

# Scope

This inventory tracks architecture, not implementation.

Examples of items that belong here:

- Core modules
- Infrastructure
- Major subsystems
- Hardware categories
- Public interfaces

Examples of items that do **not** belong here:

- Classes
- Functions
- Source files
- Variables
- Individual algorithms

---

# Final Principle

The inventory reflects the current architecture of Aether.

It should answer one question clearly:

> **"What officially exists within Aether today?"**