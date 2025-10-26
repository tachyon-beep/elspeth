# ADR 006 – Security-Critical Exception Policy (LITE)

## Status

Proposed (2025-10-25)

## Context

Elspeth's Bell-LaPadula MLS relies on **security invariants** that must always hold:

1. Classification monotonicity (can only increase)
2. Container integrity (data cannot escape boundaries)
3. Metadata immutability (classification cannot be tampered with)
4. Start-time envelope validation (computed before data retrieval)

**Problem**: Currently `SecurityValidationError` is used for BOTH:
- **Expected failures** (user misconfigured pipeline)
- **Impossible invariants** (bug or attack)

**Attack Scenario - Accidental Catch**:
```python
try:
    result = transform_classified_data(classified_frame)
except Exception as e:  # ⚠️ Catches invariant violations!
    logger.error(f"Transform failed: {e}")
    return fallback_result()  # ❌ Execution continues with compromised state
```

**Consequence**: Invariant violations can be accidentally caught, allowing execution to continue with **compromised security state** → classified data leaks.

## Decision: Dual-Exception Model

### Exception Hierarchy

```python
Exception
├── SecurityValidationError  ✅ Catchable - Expected boundaries
└── SecurityCriticalError    🚨 FORBIDDEN in production - Invariants
```

**SecurityValidationError** (existing, catchable):
- Start-time validation failures (misconfigured pipelines)
- Clearance mismatches (user error)
- Configuration/permission errors
- **MAY be caught** in production for graceful handling

**SecurityCriticalError** (NEW, policy-forbidden):
- Classification downgrades (violates high water mark)
- Classified data escaping containers
- Security metadata tampering
- "Should never happen" code paths
- **MUST NOT be caught** in production (enforced via CI/linting)
- **Allowable scope**: Only tests (`tests/`) or audit scaffolding

### Implementation

```python
# src/elspeth/core/security/exceptions.py

class SecurityCriticalError(Exception):
    """CRITICAL security violation - platform must terminate.

    ⚠️  POLICY: MUST NOT be caught in production code (src/).
    Only test code (tests/) may catch to verify security works.

    Enforced via:
    - Ruff linting (fast feedback)
    - Pre-commit hooks (prevents commits)
    - CI/CD checks (blocks merges)
    - Code review

    Rationale: Catching would allow classified data leakage to continue.
    These errors indicate bugs/attacks, not recoverable conditions.
    """

    def __init__(
        self,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
        cve_id: str | None = None,
        classification_level: SecurityLevel | None = None,
    ):
        super().__init__(message)
        self.evidence = evidence or {}
        self.cve_id = cve_id
        self.classification_level = classification_level

        # Emergency logging BEFORE exception propagates
        # Ensures audit trail even if process terminates
        self._log_critical_security_event(message, evidence, cve_id, classification_level)

    def _log_critical_security_event(self, ...):
        """Log to stderr + audit logger + security stream (redundancy)."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "CRITICAL",
            "event_type": "SECURITY_CRITICAL_ERROR",
            "cve_id": cve_id,
            "classification_level": classification_level.name if classification_level else None,
            "message": message,
            "evidence": evidence,
            "traceback": traceback.format_exc(),
        }

        # stderr - always visible
        print(f"\n🚨 CRITICAL SECURITY ERROR - PLATFORM TERMINATING 🚨", file=sys.stderr)
        print(json.dumps(event, indent=2, default=str), file=sys.stderr)

        # Audit logger (structured JSON for SIEM)
        logging.getLogger("elspeth.security.critical").critical(json.dumps(event))
```

## Usage Patterns

### Production Code - Invariant Violations (Fail-Loud)

```python
# src/elspeth/core/security/secure_data.py

from elspeth.core.security.exceptions import (
    SecurityCriticalError,
    ENABLE_SECURITY_CRITICAL_EXCEPTIONS,
)

def with_uplifted_security_level(self, new_level: SecurityLevel):
    """Uplift classification (high water mark)."""
    if ENABLE_SECURITY_CRITICAL_EXCEPTIONS:
        # NEW: Fail-loud on downgrade attempts
        if new_level < self.classification:
            raise SecurityCriticalError(  # 🚨 Propagates uncaught, terminates platform
                f"CRITICAL: Classification downgrade from {self.classification.name} "
                f"to {new_level.name} violates high water mark invariant (ADR-002-A)",
                evidence={
                    "current_level": self.classification.name,
                    "attempted_level": new_level.name,
                    "data_shape": self.data.shape,
                },
                cve_id="CVE-ADR-002-A-004",
                classification_level=self.classification,
            )
        return SecureDataFrame(self.data, new_level)
    else:
        # OLD: Silent downgrade prevention
        uplifted_classification = max(self.classification, new_level)
        return SecureDataFrame(self.data, uplifted_classification)
```

### Production Code - Expected Validation (Catchable)

```python
# src/elspeth/core/experiments/suite_runner.py

def _validate_component_clearances(self, operating_level: SecurityLevel):
    """Validate components can operate at envelope level."""
    try:
        self.datasource.validate_can_operate_at_level(operating_level)
    except Exception as e:
        raise SecurityValidationError(  # ✅ Expected validation failure
            f"ADR-002 Validation Failed: Datasource "
            f"{type(self.datasource).__name__} cannot operate at "
            f"{operating_level.name} level: {e}"
        ) from e
```

### Test Code - Verifying Invariants

```python
# tests/test_adr002_security_critical.py

def test_classification_downgrade_raises_critical_error():
    """Verify downgrade attempts raise SecurityCriticalError."""
    classified = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)

    # ✅ Tests ARE allowed to catch SecurityCriticalError
    with pytest.raises(SecurityCriticalError) as exc_info:
        classified.with_uplifted_security_level(SecurityLevel.UNOFFICIAL)  # Downgrade!

    assert "downgrade" in str(exc_info.value).lower()
    assert exc_info.value.cve_id == "CVE-ADR-002-A-004"
    assert exc_info.value.classification_level == SecurityLevel.SECRET
```

## Policy Enforcement (Multi-Layer)

### Layer 1: Ruff Linting
```toml
# pyproject.toml
[tool.ruff.lint]
extend-select = ["TRY"]  # Exception handling best practices

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["TRY302"]  # Allow catching specific exceptions in tests
```

### Layer 2: Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: security-exception-policy
        name: Enforce SecurityCriticalError policy
        entry: python scripts/check_security_exception_policy.py
        language: python
        files: ^src/.*\.py$
```

Script uses AST parsing to detect ALL catches (direct, aliased, tuple, broad `Exception`).

### Layer 3: CI/CD Check
```bash
# .github/workflows/security-policy.yml
grep -rn "except.*SecurityCriticalError" src/ || exit 0
if [ violations ]; then
  echo "❌ POLICY VIOLATION: SecurityCriticalError caught in production!"
  exit 1
fi
```

### Layer 4: Code Review
PR template includes:
- [ ] No `SecurityCriticalError` catches in src/
- [ ] Test code properly validates invariant violations

## Breaking Changes

### 1. with_uplifted_security_level() Behavior

**Current (Pre-ADR-006):**
```python
secret_frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# → Returns secret_frame unchanged (max(SECRET, OFFICIAL) = SECRET)
# No exception, operation idempotent
```

**New (Post-ADR-006):**
```python
secret_frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# → Raises SecurityCriticalError! 💥
# Platform terminates with emergency logging
```

**Rationale**: Attempted downgrades = logic bugs. Fail-loud reveals bugs that silent `max()` hides.

**Migration Pattern:**
```python
# ❌ Broken pattern (raises SecurityCriticalError if frame.classification > OFFICIAL):
def transform(self, frame: SecureDataFrame):
    return frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)

# ✅ ADR-006 compatible:
def transform(self, frame: SecureDataFrame):
    plugin_level = self.get_security_level()
    target_level = max(frame.classification, plugin_level)
    return frame.with_uplifted_security_level(target_level)
```

### 2. Exception Hierarchy Change

New `SecurityCriticalError` type (existing `SecurityValidationError` unaffected).

## Integration with ADR-002-A

ADR-002-A invariants now raise `SecurityCriticalError`:

| Invariant | Old Exception | New Exception | CVE ID |
|-----------|---------------|---------------|--------|
| Direct container construction | `SecurityValidationError` | `SecurityCriticalError` | CVE-ADR-002-A-001 |
| Classification downgrade | Silent max() | `SecurityCriticalError` | CVE-ADR-002-A-004 |
| Metadata tampering | Silent (frozen) | `SecurityCriticalError` | CVE-ADR-002-A-005 |

## Feature Flag Rollout (MANDATORY)

### Phase 1: Deploy with Flag OFF (Week 1-2)
```python
# Default OFF for safety
ENABLE_SECURITY_CRITICAL_EXCEPTIONS = os.getenv(
    "ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS", "false"
).lower() in ("true", "1", "yes")
```

Log "would-be violations" for analysis:
```python
if new_level < self.classification:
    logger.warning(
        f"PREVIEW: Would raise SecurityCriticalError - "
        f"downgrade from {self.classification.name} to {new_level.name}",
        extra={"would_be_violation": True},
    )
```

### Phase 2: Enable in Staging (Week 3)
- Set `ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS=true`
- Monitor for unexpected `SecurityCriticalError`
- Fix any issues

### Phase 3: Production Rollout (Week 4+)
- Enable in canary (10% traffic, 48hr monitor)
- Enable full production (100%, close monitoring)
- After 30 days stable: Remove flag, make permanent

**Rollback**: `export ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS=false`

**Success Criteria**:
- ✅ 30 days production, zero `SecurityCriticalError` occurrences
- ✅ All plugins audited and compatible
- ✅ Mutation testing confirms checks work
- ✅ Team trained, docs updated

## Consequences

### Benefits
- **Unmissable audit signals** - Multi-channel logging (stderr, audit, SIEM)
- **Fail-safe by default** - Platform terminates on invariant violations
- **Clear intent** - Validation vs invariant distinction self-documents
- **Defense in depth** - Multiple enforcement layers (linter → CI → review)
- **Testability preserved** - Tests can catch to verify security works
- **Forensic evidence** - Structured `evidence` dict for incident response

### Limitations
- **No graceful degradation** - Immediate termination (intentional for MLS)
- **Developer training** - Must understand when to use which exception
- **False positive risk** - Defensive checks need comprehensive testing
- **Policy complexity** - CI/linting maintenance overhead
- **Broad catches remain** - `except Exception:` still technically catches (CI warns)

## Related

ADR-001 (Philosophy), ADR-002 (MLS), ADR-002-A (Trusted container), ADR-003 (Plugin registry), ADR-004 (BasePlugin)

---
**Last Updated**: 2025-10-25
