# ADR 001 – Design Philosophy

## Status

Accepted (2025-10-23)

## Context

Elspeth orchestrates experiments that may process sensitive data subject to stringent
regulatory requirements (government, healthcare, finance). The system must support
confidentiality controls, reproducible analytics, and operational resilience while remaining
usable for engineering teams. To avoid ad-hoc trade-offs, the core engineering priorities are
defined up front.

Without an explicit priority hierarchy, teams face inconsistent trade-off decisions when
security conflicts with usability, or when availability pressures threaten data integrity.
This ADR establishes a clear, security-first ordering that governs all subsequent architectural
decisions.

## Decision

We will establish the following order of priorities for all architectural and implementation
decisions:

1. **Security** – Prevent unauthorised access, leakage, or downgrade of classified data.
2. **Data Integrity** – Ensure results, artefacts, and provenance are trustworthy and
   reproducible; maintain tamper-evident audit trails.
3. **Availability** – Keep orchestration reliable and recoverable (checkpointing, retries,
   graceful failure), subject to security/integrity constraints.
4. **Usability / Functionality** – Provide developer ergonomics, extensibility, and feature
   depth, without compromising higher priorities.

When priorities conflict, the higher-ranked concern wins. For example:

- Fail closed rather than serve data to a low-level sink (Security > Availability)
- Drop features that would break reproducibility (Integrity > Functionality)
- Require additional authentication even if it impacts UX (Security > Usability)

## Consequences

### Benefits

- **Clear trade-off resolution** – Teams have explicit guidance when priorities conflict
- **Security by design** – Security considerations are baked into every architectural decision
  from the start
- **Regulatory confidence** – Priority hierarchy aligns with compliance frameworks (PSPF, HIPAA,
  PCI-DSS)
- **Predictable behaviour** – Fail-fast, fail-closed patterns reduce unexpected security
  incidents

### Limitations / Trade-offs

- **Developer friction** – Security-first approach may require more ceremony (authentication,
  validation, audit logging) than developers expect. *Mitigation*: Invest in tooling and
  clear documentation to reduce friction.
- **Conservative posture** – System will abort operations when lower priorities (availability,
  usability) conflict with higher ones. *Mitigation*: This is intentional; operational
  resilience comes from security, not vice versa.
- **Feature velocity** – Some features may be rejected or delayed if they cannot meet
  security/integrity requirements. *Mitigation*: Plan security requirements during design
  phase, not as an afterthought.

### Implementation Impact

- All ADRs must reference this priority hierarchy when justifying decisions
- Code reviews evaluate whether implementations respect the priority ordering
- CI guardrails enforce security and integrity checks before availability optimizations
- Plugin acceptance criteria require security level declarations before functionality review

## Related Documents

- [ADR-002](002-security-architecture.md) – Multi-Level Security Enforcement
- `docs/architecture/security-controls.md` – Security control inventory
- `docs/architecture/plugin-security-model.md` – Plugin security architecture
- `docs/compliance/` – Compliance and accreditation documentation

---

**Last Updated**: 2025-10-24
**Author(s)**: Architecture Team
