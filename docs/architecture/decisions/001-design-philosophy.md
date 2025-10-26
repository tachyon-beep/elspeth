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

### Fail-Closed Principle (Security-First Enforcement)

**Mandatory Requirement**: All security controls in Elspeth **MUST fail-closed** when the control itself is unavailable, degraded, or cannot be verified.

**Definition**:
- **Fail-closed** (secure): Deny the operation when security cannot be validated
- **Fail-open** (insecure): Allow the operation when security cannot be validated

**Policy**:
When a security control cannot operate (missing dependencies, runtime limitations, verification failure):
- ✅ **REQUIRED**: Raise an error and deny the operation (fail-closed)
- ❌ **FORBIDDEN**: Log a warning and allow the operation (fail-open)

**Rationale**:
Fail-open behavior creates attack surfaces where adversaries can trigger control failures to bypass security. In classified data systems, allowing operations when security is unverifiable violates the Security-First principle (#1 priority).

**Examples**:

| Scenario | Fail-Open (Insecure) | Fail-Closed (Secure) |
|----------|----------------------|----------------------|
| Stack inspection unavailable | Allow frame creation | `SecurityValidationError` |
| Authentication service down | Grant access | Deny access |
| Encryption key not found | Store plaintext | Refuse to store |
| Security level unknown | Assume UNOFFICIAL | Require explicit declaration |
| Signature verification fails | Accept artifact | Reject artifact |
| Operating level not set | Return declared level | `RuntimeError` (fail loudly) |

### Fail-Loud Principle (NO Graceful Degradation)

**Mandatory Requirement**: When anything is not 100% correct in security-critical paths, we **FAIL LOUD** immediately with obvious errors.

**Policy - FAIL LOUD**:
- ✅ **REQUIRED**: Raise `RuntimeError`, `SecurityValidationError`, or similar exception
- ✅ **REQUIRED**: Include detailed diagnostic message explaining WHAT failed and WHY
- ✅ **REQUIRED**: Fail immediately at point of detection (don't defer or accumulate errors)
- ❌ **FORBIDDEN**: Graceful degradation (fallbacks, defaults, "best effort")
- ❌ **FORBIDDEN**: Silent failures (logging warning and continuing)
- ❌ **FORBIDDEN**: Returning None/False/empty values on security failures

**Rationale**:
In high-security systems, graceful degradation is an attack vector. If a security control fails,
we want to **FAIL LOUD** immediately:
1. **Stops execution immediately** (prevents damage from propagating)
2. **Makes the failure impossible to ignore** (forces investigation)
3. **Provides diagnostic context** (enables rapid root cause analysis)
4. **Prevents partial operations** (all-or-nothing, no half-broken states)

Graceful degradation creates situations where:
- Operators don't notice security failures until damage is done
- Attackers can trigger fallback paths to bypass controls
- Systems limp along in insecure states ("works on my machine")
- Root causes are hidden by layers of fallback logic

**Examples - FAIL LOUD**:

| Scenario | ❌ Graceful Degradation (FORBIDDEN) | ✅ Fail Loud (REQUIRED) |
|----------|-------------------------------------|----------------------------------------|
| Operating level not set | `return self.security_level` | `RuntimeError` with diagnostic message |
| Plugin context missing | Return default context | `RuntimeError` - context must be attached |
| Security level validation fails | Log warning, continue | `SecurityValidationError` - abort pipeline |
| Signature missing from artifact | Accept unsigned artifact | `SignatureValidationError` - reject artifact |
| Clearance insufficient | Skip plugin, continue | `SecurityValidationError` - abort experiment |

**Implementation Requirements**:
- All security validation functions MUST raise exceptions on failure (never return `False` or `None`)
- Exception messages MUST be detailed and actionable (include what/why/where/when)
- No "try to recover" logic in security-critical paths (fail immediately, recover at boundaries)
- Convenience fallbacks for security controls are FORBIDDEN (no "skip SSL verification" flags)
- Feature flags for security controls FORBIDDEN in production (testing/development only)
- Audit logging for attempted bypasses (capture security control failure attempts)
- Programming errors (wrong lifecycle usage) MUST raise `RuntimeError` (loud and obvious)

**Reference Implementations**:
- `secure_data.py:90-102` – Fail-closed when stack inspection unavailable (CVE-ADR-002-A-003 fix)
- `path_guard.py` – Fail-closed when `allowed_base_path` missing (test_runner_characterization.py:378)
- `plugin.py:get_effective_level()` – `RuntimeError` if operating_level not set (no fallback to security_level)
- `suite_runner._validate_experiment_security()` – `SecurityValidationError` on insufficient clearance (aborts pipeline)

**Related**: ADR-002 (MLS enforcement), ADR-002-A (Trusted container model), ADR-004 (BasePlugin security bones)

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

**Last Updated**: 2025-10-26 (Added Fail-Loud Principle - no graceful degradation in security controls)
**Author(s)**: Architecture Team
