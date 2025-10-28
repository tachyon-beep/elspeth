# ADR 001 – Design Philosophy (LITE)

## Status

Accepted (2025-10-23)

## Core Priority Hierarchy

When priorities conflict, higher rank wins:

1. **Security** – Prevent unauthorized access/leakage of classified data
2. **Data Integrity** – Ensure reproducible, tamper-evident results
3. **Availability** – Reliable orchestration (subject to security/integrity)
4. **Usability** – Developer ergonomics (without compromising above)

## Fail-Closed Principle (Mandatory)

**REQUIRED**: All security controls MUST fail-closed when unavailable/degraded/unverifiable.

**Policy**:

- ✅ Deny operation when security cannot be validated
- ❌ FORBIDDEN: Log warning and allow operation (fail-open)

**Critical Examples**:

- Stack inspection unavailable → `SecurityValidationError` (not allow frame creation)
- Operating level not set → `RuntimeError` (not return declared level)
- Security level unknown → Require explicit declaration (not assume UNOFFICIAL)

## Fail-Loud Principle (Mandatory)

**REQUIRED**: Security failures MUST raise exceptions immediately with diagnostic messages.

**Policy - FAIL LOUD**:

- ✅ Raise `RuntimeError`/`SecurityValidationError` immediately at detection point
- ✅ Include detailed diagnostic (what/why/where)
- ❌ FORBIDDEN: Graceful degradation, fallbacks, silent failures
- ❌ FORBIDDEN: Return None/False/empty on security failures
- ❌ FORBIDDEN: "Try to recover" logic in security paths

**Rationale**: Graceful degradation = attack vector. Make failures impossible to ignore.

**Critical Examples**:

- Operating level not set → `RuntimeError` (not return `self.security_level`)
- Plugin context missing → `RuntimeError` (not return default)
- Clearance insufficient → `SecurityValidationError` (not skip plugin)

## Implementation Requirements

- Security validation MUST raise exceptions (never return False/None)
- NO convenience security bypasses (no "skip SSL" flags)
- NO feature flags for security controls in production
- Programming errors (lifecycle misuse) → `RuntimeError`

## Reference Implementations

- `secure_data.py:90-102` – Fail-closed stack inspection
- `plugin.py:get_effective_level()` – RuntimeError if operating_level not set
- `suite_runner._validate_experiment_security()` – SecurityValidationError aborts pipeline

## Related

ADR-002 (MLS), ADR-002-A (Trusted container), ADR-004 (BasePlugin security)

---
**Last Updated**: 2025-10-26
