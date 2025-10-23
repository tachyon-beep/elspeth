# ADR 001 – Design Philosophy

## Status

Accepted (2025‑10‑23). Governs all subsequent decisions unless superseded.

## Context

Elspeth orchestrates experiments that may process sensitive data subject to stringent
regulatory requirements (government, healthcare, finance). The system must support
confidentiality controls, reproducible analytics, and operational resilience while remaining
usable for engineering teams. To avoid ad-hoc trade-offs, the core engineering priorities are
defined up front.

## Decision

Establish the following order of priorities for all architectural and implementation decisions:

1. **Security** – Prevent unauthorised access, leakage, or downgrade of classified data.
2. **Data Integrity** – Ensure results, artefacts, and provenance are trustworthy and
   reproducible; maintain tamper-evident audit trails.
3. **Availability** – Keep orchestration reliable and recoverable (checkpointing, retries,
   graceful failure), subject to security/integrity constraints.
4. **Usability / Functionality** – Provide developer ergonomics, extensibility, and feature
   depth, without compromising higher priorities.

When priorities conflict, the higher-ranked concern wins (e.g., fail closed rather than serve
data to a low-level sink; drop features that would break reproducibility).

## Consequences

- **Security-first posture**: Multi-level security enforcement, clearance checks, and endpoint
  allowlists may abort runs, block plugins, or require additional controls even at the cost of
  availability or developer convenience.
- **Integrity safeguards**: Schema validation, signed bundles, audit logging, and pipeline
  determinism are mandatory; features must preserve provenance and verifiability.
- **Availability trade-offs**: When security or integrity are at risk, the system is allowed
  (and expected) to fail fast; availability enhancements (retries, checkpoint resume) must
  maintain higher-priority guarantees.
- **Usability considerations**: Developer tooling, DX improvements, and new functionality are
  encouraged, provided they do not dilute the preceding priorities.

This ordering guides ADRs, implementation reviews, and CI guardrails.

## Related Documents

- ADR‑002 – Multi-Level Security Enforcement
- `docs/architecture/security-controls.md`
- `docs/architecture/plugin-security-model.md`
