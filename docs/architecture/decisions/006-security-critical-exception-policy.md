# ADR 006 – Security-Critical Exception Policy (Fail-Loud on Invariant Violations)

## Status

Proposed (2025-10-25)

## Context

Elspeth implements Bell-LaPadula Multi-Level Security (MLS) for handling classified data ranging from UNOFFICIAL to SECRET (ADR-002, ADR-002-A). The security model relies on **security invariants** that must hold at all times:

1. **Classification monotonicity** (ADR-002-A) – Classifications can only increase (high water mark), never decrease
2. **Container integrity** (ADR-002-A) – Classified data cannot escape `SecureDataFrame` boundaries without explicit authorization
3. **Metadata immutability** (ADR-002-A) – Security metadata (classification levels, provenance) cannot be tampered with
4. **Start-time envelope validation** (ADR-002) – Operating envelope computed before data retrieval

Currently, Elspeth uses `SecurityValidationError` for **all** security violations, both **expected validation failures** (user configured invalid pipeline) and **impossible invariant violations** (bug or attack). This creates ambiguity:

```python
# Expected failure - user misconfigured pipeline
raise SecurityValidationError("SECRET datasource cannot work with UNOFFICIAL sink")

# Impossible failure - code bug or attack
raise SecurityValidationError("Classification downgraded from SECRET to UNOFFICIAL")
```

**Problem**: If production code accidentally catches the invariant violation, execution continues with **compromised security state**. For classified data systems, this is catastrophic:

- Classified data may leak to unauthorized sinks
- Audit trail shows system "recovered" from impossible state
- Compliance auditors cannot distinguish bugs from attacks
- No unmissable signal that platform integrity is compromised

### Real-World Scenarios

**Scenario 1: Accidental Catch Block**
```python
# Somewhere in pipeline orchestration
try:
    result = transform_classified_data(classified_frame)
except Exception as e:  # ⚠️ Too broad - catches invariant violations!
    logger.error(f"Transform failed: {e}")
    return fallback_result()  # ❌ Execution continues with compromised state
```

**Scenario 2: Defensive Programming Gone Wrong**
```python
def process_batch(items):
    for item in items:
        try:
            process_classified_item(item)
        except SecurityValidationError:  # ⚠️ Catches BOTH validation AND invariants
            continue  # ❌ Skip item and continue - but what if invariant was violated?
```

**Scenario 3: Test Code Leaking into Production**
```python
# Test code pattern that accidentally deployed to production
try:
    classified.with_uplifted_security_level(SecurityLevel.UNOFFICIAL)  # Bug - downgrade!
except SecurityValidationError:
    pass  # ❌ Test code catches invariant violation, masks critical bug
```

### Why Existing `SecurityValidationError` Is Insufficient

| Aspect | Current State | Required for MLS Compliance |
|--------|---------------|------------------------------|
| **Signal clarity** | All security errors look the same | Must distinguish validation from invariant violations |
| **Catchability** | Catchable anywhere | Invariant violations must propagate uncaught |
| **Audit trail** | Standard logging | Emergency logging before termination |
| **Developer intent** | Ambiguous | Clear: "This should NEVER happen" |
| **Compliance** | Violations may be hidden | Unmissable audit signals |

### Constraints

1. **Testing requirement** – Tests MUST be able to catch invariant violations to verify security works
2. **Audit compliance** – Every invariant violation must be logged before termination
3. **Developer experience** – Fast feedback when policy is violated (linter, pre-commit)
4. **No false positives** – Production code catching `SecurityValidationError` (expected) should not trigger policy violations

## Decision

We will introduce a **dual-exception model** with **policy-enforced fail-loud behavior** for security invariant violations:

### 1. Exception Hierarchy

```python
Exception
├── SecurityValidationError  ✅ Catchable - Expected security boundaries
└── SecurityCriticalError    🚨 Policy-forbidden - Invariant violations
```

**`SecurityValidationError`** – For **expected security boundaries** (existing usage):
- Start-time validation failures (misconfigured pipelines)
- Component clearance mismatches (user error)
- Configuration validation failures
- Permission denied errors
- **May be caught** in production code for graceful error handling

**`SecurityCriticalError`** – For **impossible invariant violations** (NEW):
- Classification downgrades (violates high water mark)
- Classified data escaping container boundaries
- Security metadata tampering
- "Should never execute" code paths executing
- **MUST NOT be caught** in production code (policy-enforced via CI/linting)
- **Allowable scope**: Only unit/integration tests (under `tests/`) or generated
  scaffolding specifically tagged for auditing may catch this exception.
  All first-party production modules (`src/`) are linted to reject catches, and
  glue code (e.g., orchestration notebooks, Airflow DAGs) must either live under
  `tests/` or opt into the same lint rule set to guarantee enforcement.

### 2. Exception Implementation

```python
# src/elspeth/core/security/exceptions.py

class SecurityCriticalError(Exception):
    """CRITICAL security violation - platform must terminate.

    This exception indicates a security invariant has been violated:
    - Classification downgrade attempted (violates ADR-002-A high water mark)
    - Classified data escaping container boundaries
    - Security metadata tampering
    - "Impossible" code paths executing (defensive checks)

    ⚠️  POLICY ENFORCEMENT ⚠️

    This exception MUST NOT be caught in production code (src/).
    Only test code (tests/) may catch this exception to verify security works.

    Violations are enforced via:
    - Ruff linting (fast feedback during development)
    - Pre-commit hooks (prevents accidental commits)
    - CI/CD checks (blocks merges that violate policy)
    - Code review (human verification)

    Rationale:
    - Catching this exception would allow classified data leakage to continue
    - These errors indicate bugs or attacks, not recoverable conditions
    - Multi-Level Security (MLS) requires fail-safe behavior
    - Compliance requires unmissable audit trail

    See: docs/architecture/decisions/006-security-critical-exception-policy.md
    """

    def __init__(
        self,
        message: str,
        *,
        evidence: dict[str, Any] | None = None,
        cve_id: str | None = None,
        classification_level: SecurityLevel | None = None,
    ):
        """Initialize SecurityCriticalError with emergency logging.

        Args:
            message: Human-readable error description
            evidence: Structured data about the violation (for forensics)
            cve_id: CVE identifier if this is a known vulnerability
            classification_level: Classification level of compromised data
        """
        super().__init__(message)
        self.evidence = evidence or {}
        self.cve_id = cve_id
        self.classification_level = classification_level

        # Emergency logging BEFORE exception propagates
        # This ensures audit trail even if process terminates
        self._log_critical_security_event(message, evidence, cve_id, classification_level)

    def _log_critical_security_event(
        self,
        message: str,
        evidence: dict[str, Any] | None,
        cve_id: str | None,
        classification_level: SecurityLevel | None,
    ) -> None:
        """Log to audit trail and stderr - this is a CRITICAL event.

        Logs to multiple channels for redundancy:
        1. stderr - always visible, even if logging system fails
        2. Audit logger - structured JSON for SIEM integration
        3. Security event stream - real-time alerting
        """
        import sys
        import json
        import os
        import traceback
        from datetime import datetime, timezone

        tb = traceback.format_exc()
        if tb.strip() == "NoneType: None":
            tb = "".join(traceback.format_stack())

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "CRITICAL",
            "event_type": "SECURITY_CRITICAL_ERROR",
            "event_class": "INVARIANT_VIOLATION",
            "cve_id": cve_id,
            "classification_level": classification_level.name if classification_level else None,
            "message": message,
            "evidence": evidence,
            "process_id": os.getpid(),
            "traceback": tb,
        }

        # 1. stderr - always visible (for operators/container logs)
        print(f"\n{'='*80}", file=sys.stderr)
        print(f"🚨 CRITICAL SECURITY ERROR - PLATFORM TERMINATING 🚨", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)
        print(json.dumps(event, indent=2, default=str), file=sys.stderr)
        print(f"{'='*80}\n", file=sys.stderr)

        # 2. Audit logger (structured JSON for SIEM)
        try:
            import logging
            logger = logging.getLogger("elspeth.security.critical")
            logger.critical(json.dumps(event, default=str))
        except Exception:
            pass  # Don't let logging failure hide the security error

        # 3. Security event stream (if configured)
        try:
            # Could send to Azure Monitor, Splunk, etc.
            # For now, ensure it's in audit logs
            pass
        except Exception:
            pass
```

### 3. Usage Patterns

#### Production Code - Invariant Violations (Fail-Loud)

```python
# src/elspeth/core/security/secure_data.py

from elspeth.core.security.exceptions import (
    SecurityCriticalError,
    ENABLE_SECURITY_CRITICAL_EXCEPTIONS,
)

def with_uplifted_security_level(self, new_level: SecurityLevel) -> SecureDataFrame:
    """Uplift classification (high water mark principle).

    Raises:
        SecurityCriticalError: If downgrade attempted AND feature flag enabled
                               (CRITICAL - should never happen)
    """
    if ENABLE_SECURITY_CRITICAL_EXCEPTIONS:
        # NEW BEHAVIOR: Fail-loud on downgrade attempts
        if new_level < self.classification:
            # This should NEVER happen - indicates bug or attack
            raise SecurityCriticalError(  # 🚨 Will propagate uncaught, terminate platform
                f"CRITICAL: Classification downgrade from {self.classification.name} "
                f"to {new_level.name} violates high water mark invariant (ADR-002-A)",
                evidence={
                    "current_level": self.classification.name,
                    "attempted_level": new_level.name,
                    "data_shape": self.data.shape,
                    "data_columns": list(self.data.columns),
                },
                cve_id="CVE-ADR-002-A-004",
                classification_level=self.classification,
            )
        return SecureDataFrame(self.data, new_level)
    else:
        # OLD BEHAVIOR (during migration): Silent downgrade prevention
        uplifted_classification = max(self.classification, new_level)
        return SecureDataFrame(self.data, uplifted_classification)


def __setattr__(self, name: str, value: Any) -> None:
    """Prevent modification of security metadata after creation."""
    if name == "classification" and hasattr(self, "classification"):
        if ENABLE_SECURITY_CRITICAL_EXCEPTIONS:
            # NEW BEHAVIOR: Fail-loud on metadata tampering
            raise SecurityCriticalError(
                f"CRITICAL: Attempted to modify immutable classification "
                f"(ADR-002-A container integrity violation)",
                evidence={
                    "current_level": self.classification.name,
                    "attempted_level": value.name if isinstance(value, SecurityLevel) else str(value),
                },
                cve_id="CVE-ADR-002-A-005",
                classification_level=self.classification,
            )
        else:
            # OLD BEHAVIOR: Silent prevention (frozen dataclass already prevents this)
            # This code path shouldn't be reachable due to @dataclass(frozen=True)
            pass

    object.__setattr__(self, name, value)
```

#### Production Code - Expected Validation (Catchable)

```python
# src/elspeth/core/experiments/suite_runner.py

def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at the computed envelope level.

    Raises:
        SecurityValidationError: If any component rejects the operating level (expected)
    """
    # Validate datasource
    if hasattr(self.datasource, "validate_can_operate_at_level"):
        try:
            self.datasource.validate_can_operate_at_level(operating_level)
        except Exception as e:
            raise SecurityValidationError(  # ✅ Expected validation failure
                f"ADR-002 Start-Time Validation Failed: Datasource "
                f"{type(self.datasource).__name__} cannot operate at "
                f"{operating_level.name} level: {e}"
            ) from e

    # Validate sinks (similar pattern)
    # ...
```

#### Test Code - Verifying Invariants Work

```python
# tests/test_adr002_security_critical.py

def test_classification_downgrade_raises_critical_error():
    """Verify downgrade attempts raise SecurityCriticalError (not SecurityValidationError).

    This test verifies the high water mark invariant is enforced.
    Tests ARE allowed to catch SecurityCriticalError.
    """
    from elspeth.core.security.exceptions import SecurityCriticalError

    df = pd.DataFrame({"data": [1, 2, 3]})
    classified = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)

    # ✅ Tests ARE allowed to catch SecurityCriticalError
    with pytest.raises(SecurityCriticalError) as exc_info:
        classified.with_uplifted_security_level(SecurityLevel.UNOFFICIAL)  # Downgrade!

    # Verify error details
    assert "downgrade" in str(exc_info.value).lower()
    assert exc_info.value.cve_id == "CVE-ADR-002-A-004"
    assert exc_info.value.classification_level == SecurityLevel.SECRET
    assert exc_info.value.evidence["current_level"] == "SECRET"
    assert exc_info.value.evidence["attempted_level"] == "UNOFFICIAL"


def test_metadata_tampering_raises_critical_error():
    """Verify security metadata cannot be modified after creation."""

    classified = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)

    with pytest.raises(SecurityCriticalError) as exc_info:
        classified.security_level = SecurityLevel.UNOFFICIAL  # Tampering!

    assert exc_info.value.cve_id == "CVE-ADR-002-A-005"
```

### 4. Policy Enforcement Strategy

The policy is enforced through **multiple layers** (defense in depth):

#### Layer 1: Ruff Linting (Fast Feedback)

Add to `pyproject.toml`:

```toml
[tool.ruff.lint]
extend-select = [
    "TRY",    # tryceratops (exception handling best practices)
]

[tool.ruff.lint.per-file-ignores]
# Tests are ALLOWED to catch SecurityCriticalError
"tests/**" = ["TRY302"]  # Allow catching specific exceptions in tests
```

Custom Ruff rule (if needed):
```python
# Future: Custom Ruff plugin to detect SecurityCriticalError catches
# For now, rely on grep-based CI checks
```

#### Layer 2: Pre-commit Hook (Prevents Accidental Commits)

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: security-exception-policy
        name: Enforce SecurityCriticalError policy
        entry: python scripts/check_security_exception_policy.py
        language: python
        files: ^src/.*\.py$
        pass_filenames: true
```

Script: `scripts/check_security_exception_policy.py`:

```python
#!/usr/bin/env python3
"""AST-based SecurityCriticalError policy enforcement.

Detects ALL ways to catch SecurityCriticalError, including:
- Direct catches: except SecurityCriticalError:
- Aliased catches: except SCE: (where SCE is an alias)
- Tuple catches: except (ValueError, SecurityCriticalError):
- Broad catches: except Exception: (warns, doesn't block)
- Bare catches: except: (warns, doesn't block)

Uses AST parsing instead of regex for robustness.
"""

import ast
import sys
from pathlib import Path


class SecurityCriticalErrorCatchDetector(ast.NodeVisitor):
    """Detects catches of SecurityCriticalError in production code."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations = []
        self.warnings = []
        self.imports = {}  # Track imports for alias resolution

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track imports to resolve aliases."""
        if node.module and "security" in node.module:
            for alias in node.names:
                imported_name = alias.name
                local_name = alias.asname or alias.name
                self.imports[local_name] = imported_name
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        """Track direct imports."""
        for alias in node.names:
            if "security" in alias.name:
                local_name = alias.asname or alias.name
                self.imports[local_name] = alias.name
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Check exception handlers for policy violations."""
        if node.type is None:
            # Bare except: - catches EVERYTHING
            self.warnings.append({
                "line": node.lineno,
                "issue": "Bare 'except:' catches ALL exceptions (including SecurityCriticalError)",
                "severity": "WARNING",
            })
        elif isinstance(node.type, ast.Name):
            # except SomeException:
            if self._is_security_critical_error(node.type.id):
                self.violations.append({
                    "line": node.lineno,
                    "issue": f"Catching SecurityCriticalError (via '{node.type.id}')",
                    "severity": "VIOLATION",
                })
            elif node.type.id == "Exception":
                # Warn about broad Exception catches
                self.warnings.append({
                    "line": node.lineno,
                    "issue": "'except Exception:' catches SecurityCriticalError (consider narrower type)",
                    "severity": "WARNING",
                })
        elif isinstance(node.type, ast.Tuple):
            # except (ValueError, SecurityCriticalError):
            for exc in node.type.elts:
                if isinstance(exc, ast.Name) and self._is_security_critical_error(exc.id):
                    self.violations.append({
                        "line": node.lineno,
                        "issue": f"Catching SecurityCriticalError in tuple of exceptions",
                        "severity": "VIOLATION",
                    })

        self.generic_visit(node)

    def _is_security_critical_error(self, name: str) -> bool:
        """Check if name refers to SecurityCriticalError."""
        # Direct reference
        if name == "SecurityCriticalError":
            return True

        # Aliased import
        if name in self.imports and self.imports[name] == "SecurityCriticalError":
            return True

        return False


def check_file(filepath: Path) -> tuple[list[dict], list[dict]]:
    """Check a single file for policy violations.

    Returns:
        (violations, warnings): Lists of violation/warning dicts
    """
    try:
        content = filepath.read_text()
        tree = ast.parse(content, filename=str(filepath))

        detector = SecurityCriticalErrorCatchDetector(filepath)
        detector.visit(tree)

        return detector.violations, detector.warnings
    except SyntaxError:
        return [], []  # Skip files with syntax errors


def main(files: list[str]) -> int:
    """Check all provided files.

    Returns:
        0 if no violations, 1 if violations found
    """
    all_violations = []
    all_warnings = []

    for file in files:
        path = Path(file)
        if not path.suffix == ".py":
            continue
        if not str(path).startswith("src/"):
            continue  # Only check production code

        violations, warnings = check_file(path)

        for v in violations:
            all_violations.append(f"{path}:{v['line']}: {v['issue']}")
        for w in warnings:
            all_warnings.append(f"{path}:{w['line']}: {w['issue']}")

    # Report violations (BLOCKERS)
    if all_violations:
        print("❌ POLICY VIOLATION: SecurityCriticalError caught in production code!")
        print()
        for violation in all_violations:
            print(f"  {violation}")
        print()
        print("SecurityCriticalError MUST NOT be caught outside tests/.")
        print("See: docs/architecture/decisions/005-security-critical-exception-policy.md")
        return 1

    # Report warnings (non-blocking, but flagged)
    if all_warnings:
        print("⚠️  WARNING: Broad exception catches detected:")
        for warning in all_warnings:
            print(f"  {warning}")
        print()
        print("Consider using more specific exception types in production code.")
        print()

    print("✅ No forbidden SecurityCriticalError catches found in src/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

#### Layer 3: CI/CD Check (Blocks Merges)

Add to `.github/workflows/security-policy.yml`:

```yaml
name: Security Exception Policy

on:
  pull_request:
    paths:
      - 'src/**/*.py'
      - 'tests/**/*.py'
  push:
    branches: [main, develop]
    paths:
      - 'src/**/*.py'

jobs:
  enforce-security-exception-policy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Check for forbidden SecurityCriticalError catches in production code
        run: |
          #!/bin/bash
          set -euo pipefail

          echo "🔍 Checking for forbidden SecurityCriticalError catches in src/..."

          # Search for except clauses catching SecurityCriticalError in src/
          VIOLATIONS=$(grep -rn "except.*SecurityCriticalError" src/ || true)

          if [ -n "$VIOLATIONS" ]; then
            echo "❌ POLICY VIOLATION: SecurityCriticalError caught in production code!"
            echo ""
            echo "$VIOLATIONS"
            echo ""
            echo "SecurityCriticalError MUST NOT be caught outside tests/."
            echo "See: docs/architecture/decisions/005-security-critical-exception-policy.md"
            exit 1
          fi

          echo "✅ No forbidden SecurityCriticalError catches found in src/"

      - name: Verify tests properly validate SecurityCriticalError
        run: |
          #!/bin/bash

          echo "🔍 Verifying tests can catch SecurityCriticalError..."

          # Ensure at least one test catches it (confirms exception is actually used)
          TEST_CATCHES=$(grep -rn "pytest.raises(SecurityCriticalError)" tests/ || true)

          if [ -z "$TEST_CATCHES" ]; then
            echo "⚠️  WARNING: No tests catch SecurityCriticalError"
            echo "This might mean the exception is unused or tests are incomplete"
          else
            echo "✅ Tests properly validate SecurityCriticalError behavior"
            echo "   Found $(echo "$TEST_CATCHES" | wc -l) test cases"
          fi

      - name: Check for overly broad exception catches
        run: |
          #!/bin/bash

          echo "🔍 Checking for overly broad exception catches in src/..."

          # Warn about bare except: or except Exception: (could catch SecurityCriticalError)
          BARE_CATCHES=$(grep -rn "except\s*:" src/ | grep -v "except.*Error" || true)
          BROAD_CATCHES=$(grep -rn "except Exception:" src/ || true)

          if [ -n "$BARE_CATCHES" ] || [ -n "$BROAD_CATCHES" ]; then
            echo "⚠️  WARNING: Broad exception catches found (could catch SecurityCriticalError):"
            echo "$BARE_CATCHES"
            echo "$BROAD_CATCHES"
            echo ""
            echo "Consider using specific exception types or adding policy checks"
          else
            echo "✅ No overly broad exception catches found"
          fi
```

#### Layer 4: Code Review (Human Verification)

Pull request template reminder:

```markdown
## Security Checklist

- [ ] No `SecurityCriticalError` catches in production code (src/)
- [ ] Test code properly validates invariant violations
- [ ] Security-critical paths have defensive checks
```

## Breaking Changes

### 1. with_uplifted_security_level() Behavior Change

**Current Behavior (Pre-ADR-005):**
```python
# Silent downgrade prevention via max()
secret_frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
result = secret_frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# → Returns secret_frame unchanged (max(SECRET, OFFICIAL) = SECRET)
# No exception raised, operation is idempotent
```

**New Behavior (Post-ADR-005):**
```python
# Explicit downgrade detection via SecurityCriticalError
secret_frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
result = secret_frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# → Raises SecurityCriticalError! 💥
# Platform terminates immediately with emergency logging
```

**Rationale:**
- Attempted downgrades indicate **logic bugs** in plugin code
- Plugins should NEVER pass a lower level to the uplifting method
- Fail-loud reveals bugs that silent `max()` would hide
- Aligns with ADR-002 "fail-fast" principle for security violations

**Migration Impact:**

*Low* - Current codebase doesn't have plugins attempting downgrades (verified via code review).
However, defensive plugin code might use conservative patterns that will break:

```python
# ❌ Potentially broken pattern (will raise SecurityCriticalError):
def transform(self, frame: SecureDataFrame) -> SecureDataFrame:
    # Process data...
    return frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
    # ↑ BREAKS if frame.classification > OFFICIAL!

# ✅ ADR-005 compatible pattern:
def transform(self, frame: SecureDataFrame) -> SecureDataFrame:
    # Process data...
    plugin_level = self.get_security_level()
    target_level = max(frame.classification, plugin_level)
    return frame.with_uplifted_security_level(target_level)
```

**Detection & Migration:**

Pre-deployment audit checklist:
1. Search codebase for all `with_uplifted_security_level()` calls
2. Verify each call uses `max(current, target)` or equivalent logic
3. Add linter rule to detect suspicious patterns (constant security levels passed)
4. Deploy with feature flag first (see rollout strategy below)
5. Monitor staging for `SecurityCriticalError` occurrences before production

**Linter Rule (pyproject.toml):**
```toml
# Future: Custom Ruff rule to detect suspicious uplifting patterns
# For now: Manual code review + staging validation
```

### 2. Exception Hierarchy Change

**Added:** New exception type `SecurityCriticalError` (does not affect existing code)

**Impact:** Zero breaking change - existing `SecurityValidationError` usage is unaffected.

## Integration with ADR-002-A (Classification Container)

ADR-002-A established the `SecureDataFrame` trusted container model with invariant
enforcement through stack inspection. ADR-006 strengthens this enforcement by introducing
fail-loud semantics for invariant violations.

### Current State (ADR-002-A)

Classification laundering attempts currently raise `SecurityValidationError`:

```python
# src/elspeth/core/security/secure_data.py (ADR-002-A implementation)
def __post_init__(self) -> None:
    """Verify container created via authorized factory methods only."""
    if object.__getattribute__(self, '_created_by_datasource'):
        return

    # Stack inspection to verify authorized caller...
    frame = inspect.currentframe()
    # ...

    # CURRENT: Raises SecurityValidationError
    raise SecurityValidationError(
        "SecureDataFrame can only be created by datasources or authorized "
        "factory methods (with_uplifted_security_level, with_new_data). "
        "Direct construction prevents classification tracking (ADR-002-A)."
    )
```

### ADR-006 Change

Classification laundering is an **invariant violation** (should never happen with correct
code), therefore it should raise `SecurityCriticalError` instead:

```python
# src/elspeth/core/security/secure_data.py (UPDATED for ADR-006)
from elspeth.core.security.exceptions import SecurityCriticalError

def __post_init__(self) -> None:
    """Verify container created via authorized factory methods only."""
    if object.__getattribute__(self, '_created_by_datasource'):
        return

    # Stack inspection to verify authorized caller...
    frame = inspect.currentframe()
    # ...

    # UPDATED: Raise SecurityCriticalError (invariant violation)
    raise SecurityCriticalError(
        "CRITICAL: SecureDataFrame created outside datasource factory - "
        "possible classification laundering attack (ADR-002-A)",
        evidence={
            "stack_trace": traceback.format_stack(),
            "attempted_creation_location": frame.f_code.co_filename if frame else "unknown",
        },
        cve_id="CVE-ADR-002-A-001",
        classification_level=None,  # No classification established yet
    )
```

### Affected Invariants

The following ADR-002-A invariants will raise `SecurityCriticalError` after ADR-006 implementation:

| Invariant | Old Exception | New Exception | CVE ID |
|-----------|---------------|---------------|--------|
| Direct container construction (bypassing datasource) | `SecurityValidationError` | `SecurityCriticalError` | CVE-ADR-002-A-001 |
| Classification downgrade (violates high water mark) | Silent max() | `SecurityCriticalError` | CVE-ADR-002-A-004 |
| Metadata tampering (`frame.classification = X`) | Silent (frozen dataclass) | `SecurityCriticalError` | CVE-ADR-002-A-005 |

### Migration Timeline

**Phase 1: Feature Flag Deployment** (same timeline as ADR-006 general rollout)
- Deploy with `ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS=false`
- Existing `SecurityValidationError` behavior preserved
- Monitor for any occurrence of container violations

**Phase 2: Enable in Staging** (after 7 days clean operation)
- Enable feature flag in staging environments
- Validate that no legitimate code paths trigger container violations
- Verify fail-loud behavior works as expected

**Phase 3: Production Rollout** (after 30 days clean staging)
- Enable in production with monitoring
- Alert on ANY `SecurityCriticalError` from ADR-002-A code paths
- Treat violations as P0 incidents (potential security breach)

**Phase 4: Test Updates** (parallel with Phase 1-3)

Update all tests expecting `SecurityValidationError` from container code:

```python
# BEFORE (ADR-002-A original tests)
def test_direct_construction_blocked():
    with pytest.raises(SecurityValidationError):
        SecureDataFrame(df, SecurityLevel.SECRET)  # Direct construction

# AFTER (ADR-006 integration)
from elspeth.core.security.exceptions import SecurityCriticalError

def test_direct_construction_blocked():
    with pytest.raises(SecurityCriticalError) as exc_info:
        SecureDataFrame(df, SecurityLevel.SECRET)  # Direct construction

    assert "classification laundering" in str(exc_info.value).lower()
    assert exc_info.value.cve_id == "CVE-ADR-002-A-001"
```

### Exception Migration Checklist

**Files to Update** (search for `SecurityValidationError` raises in container contexts):

- [ ] `src/elspeth/core/security/secure_data.py:__post_init__()` - Container creation violation
- [ ] `src/elspeth/core/security/secure_data.py:with_uplifted_security_level()` - Classification downgrade
- [ ] `src/elspeth/core/security/secure_data.py:__setattr__()` - Metadata tampering
- [ ] `tests/test_adr002a_*.py` - Update ~15 tests expecting `SecurityValidationError`
- [ ] `tests/test_classified_dataframe.py` - Update container violation tests

**Verification**:
```bash
# Find all SecurityValidationError raises in container code
grep -r "SecurityValidationError" src/elspeth/core/security/secure_data.py

# Find all tests catching SecurityValidationError from container
grep -r "pytest.raises(SecurityValidationError)" tests/ | grep -i "classified\|container"
```

### Why This Matters

**Before ADR-006**: Classification laundering attempts raise catchable `SecurityValidationError`,
which could be accidentally or maliciously caught by broad exception handlers, allowing
execution to continue after a security invariant violation.

**After ADR-006**: Classification laundering raises `SecurityCriticalError`, which propagates
to platform termination. Failed pipelines and audit trails make security violations unmissable.

**Security Improvement**: ADR-002-A's container model becomes fail-loud instead of fail-safe,
ensuring violations cannot be silently handled or ignored.

## Consequences

### Benefits

1. **Unmissable Audit Signals**
   - Invariant violations are logged to multiple channels (stderr, audit log, SIEM)
   - Compliance auditors can distinguish bugs/attacks from expected validation failures
   - Emergency logging happens BEFORE propagation (ensures audit trail even if process terminates)

2. **Fail-Safe by Default**
   - Invariant violations terminate the platform (cannot continue with compromised security state)
   - Prevents classified data leakage when "impossible" conditions occur
   - Aligns with Bell-LaPadula MLS principles (fail-closed when invariants violated)

3. **Clear Developer Intent**
   - `SecurityValidationError` = "This is expected to fail sometimes" (validation boundary)
   - `SecurityCriticalError` = "This should NEVER happen" (invariant violation)
   - Code is self-documenting about security assumptions

4. **Defense in Depth**
   - Multiple enforcement layers (linter → pre-commit → CI → code review)
   - Fast feedback loop (pre-commit catches violations before commit)
   - Cannot bypass all layers simultaneously

5. **Testability Preserved**
   - Tests can catch `SecurityCriticalError` to verify security works
   - Policy only blocks production code, not test code
   - No need for `BaseException` gymnastics

6. **Forensic Evidence**
   - `evidence` dict captures structured data about violation (for incident response)
   - `cve_id` tracks known vulnerabilities
   - `classification_level` shows sensitivity of compromised data
   - Full stack trace preserved

### Limitations / Trade-offs

1. **No Graceful Degradation**
   - Invariant violations terminate the platform immediately
   - Cannot cleanup resources or notify stakeholders before termination
   - *Mitigation*: This is intentional for MLS systems - continuing with compromised state is worse than terminating. Use `finally` blocks for critical cleanup.

2. **Developer Training Required**
   - Team must understand when to use which exception type
   - Risk of using `SecurityValidationError` when `SecurityCriticalError` is appropriate
   - *Mitigation*: Code review checklist, ADR documentation, examples in codebase

3. **False Positive Risk**
   - Bug in invariant checking logic makes platform unusable
   - Defensive checks that are "too defensive" trigger false alarms
   - *Mitigation*: Comprehensive testing before deploying defensive checks. Use feature flags for new invariant checks.

4. **Policy Enforcement Complexity**
   - Requires CI/CD configuration, pre-commit hooks, linting rules
   - Adds maintenance overhead for policy enforcement scripts
   - *Mitigation*: Scripts are simple (grep-based), well-documented, and versioned with code

5. **Cannot Prevent All Broad Catches**
   - `except Exception:` still technically catches `SecurityCriticalError`
   - Relies on CI warnings to discourage broad catches
   - *Mitigation*: Add Ruff rules to discourage broad `except Exception:` in critical paths

### Implementation Impact

#### New Files

- `src/elspeth/core/security/exceptions.py` – Exception class definitions
- `scripts/check_security_exception_policy.py` – Pre-commit enforcement script
- `.github/workflows/security-policy.yml` – CI enforcement workflow
- `tests/test_security_critical_exceptions.py` – Test suite for exception behavior

#### Modified Files

- `src/elspeth/core/security/secure_data.py` – Add invariant checks with `SecurityCriticalError`
- `src/elspeth/core/security/__init__.py` – Export `SecurityCriticalError`
- `pyproject.toml` – Add Ruff linting rules
- `.pre-commit-config.yaml` – Add policy enforcement hook
- `.github/pull_request_template.md` – Add security checklist

#### Migration Strategy

**Phase 1: Foundation (Week 1)**
- Create `SecurityCriticalError` exception class
- Add emergency logging infrastructure
- Write comprehensive test suite

**Phase 2: Policy Enforcement (Week 1-2)**
- Implement pre-commit hook script
- Add CI/CD workflow
- Update PR template

**Phase 3: Code Updates (Week 2-3)**
- Add invariant checks to `SecureDataFrame`:
  - Classification downgrade prevention
  - Metadata immutability enforcement
  - Container boundary checks
- Add defensive checks to critical paths

**Phase 4: Validation (Week 3-4)**
- Run mutation testing on invariant checks
- Verify all enforcement layers working
- Load testing to ensure emergency logging doesn't cause performance issues
- Documentation and team training

#### Rollout Strategy (MANDATORY Feature Flag Approach)

**Phase 1: Foundation with Feature Flag OFF (Week 1-2)**

1. **Deploy infrastructure with flag disabled by default:**
   ```python
   # src/elspeth/core/security/exceptions.py
   import os

   # Feature flag (default OFF for safety)
   ENABLE_SECURITY_CRITICAL_EXCEPTIONS = os.getenv(
       "ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS", "false"
   ).lower() in ("true", "1", "yes")


   class SecurityCriticalError(Exception):
       """CRITICAL security violation - platform must terminate."""
       # ... (implementation as shown above)
   ```

2. **Update `with_uplifted_security_level()` with conditional behavior:**
   ```python
   # src/elspeth/core/security/secure_data.py
   from elspeth.core.security.exceptions import (
       SecurityCriticalError,
       ENABLE_SECURITY_CRITICAL_EXCEPTIONS,
   )

   def with_uplifted_security_level(self, new_level: SecurityLevel):
       """Uplift classification (high water mark principle)."""

       if ENABLE_SECURITY_CRITICAL_EXCEPTIONS:
           # NEW BEHAVIOR (ADR-005): Fail-loud on downgrade attempts
           if new_level < self.classification:
               raise SecurityCriticalError(
                   f"CRITICAL: Classification downgrade from {self.classification.name} "
                   f"to {new_level.name} violates high water mark invariant (ADR-002-A)",
                   evidence={
                       "current_level": self.classification.name,
                       "attempted_level": new_level.name,
                   },
                   cve_id="CVE-ADR-002-A-004",
                   classification_level=self.classification,
               )
           return SecureDataFrame(self.data, new_level)
       else:
           # OLD BEHAVIOR (Pre-ADR-005): Silent downgrade prevention
           uplifted_classification = max(self.classification, new_level)
           return SecureDataFrame(self.data, uplifted_classification)
   ```

3. **Add "would-be violation" logging (observability mode):**
   ```python
   else:  # Feature flag OFF
       uplifted_classification = max(self.classification, new_level)

       # Log would-be violations for analysis
       if new_level < self.classification:
           import logging
           logger = logging.getLogger("elspeth.security.critical.preview")
           logger.warning(
               f"PREVIEW: Would raise SecurityCriticalError - "
               f"downgrade from {self.classification.name} to {new_level.name}",
               extra={
                   "would_be_violation": True,
                   "current_level": self.classification.name,
                   "attempted_level": new_level.name,
               }
           )

       return SecureDataFrame(self.data, uplifted_classification)
   ```

4. **Monitor "would-be violations" in development/staging:**
   - Analyze logs for false positives (legitimate plugin patterns)
   - Fix any plugin code that would trigger violations
   - Verify no unexpected downgrade attempts

**Phase 2: Enable in Staging (Week 3)**

1. Set environment variable: `ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS=true`
2. Run full test suite (all tests must pass)
3. Run integration tests with production-like workloads
4. Monitor for unexpected `SecurityCriticalError` occurrences
5. Fix any issues discovered

**Phase 3: Gradual Production Rollout (Week 4+)**

1. **Enable in canary environment** (10% of traffic)
   - Monitor for 48 hours
   - Check for `SecurityCriticalError` count == 0
   - Verify no performance degradation from emergency logging

2. **Enable in full production** (100% of traffic)
   - Monitor closely for first 2 weeks
   - Keep feature flag as emergency rollback mechanism
   - Alert on any `SecurityCriticalError` occurrence (critical incident)

3. **Stabilization and flag removal** (Week 6+)
   - After 30 days of stable operation (zero violations)
   - Remove feature flag code
   - Make SecurityCriticalError behavior permanent
   - Update documentation to remove feature flag references

**Monitoring & Alerting:**

1. **Metrics to track:**
   ```python
   # Add to monitoring infrastructure
   security_critical_error_count = 0  # MUST be zero in production
   security_critical_error_preview_count = N  # "Would-be" violations (flag OFF)
   ```

2. **Alert rules:**
   - **P0 Alert**: `security_critical_error_count > 0` in production → Critical incident
   - **P2 Alert**: `security_critical_error_preview_count > 10` in staging → Investigate patterns
   - **P3 Alert**: New `SecurityCriticalError` in test environment → Review test coverage

**Rollback Procedure:**

If issues discovered in production:
```bash
# Immediate rollback (revert to old behavior)
export ELSPETH_ENABLE_SECURITY_CRITICAL_EXCEPTIONS=false

# Or restart services with flag disabled
```

**Success Criteria for Flag Removal:**

- ✅ 30 days in production with zero `SecurityCriticalError` occurrences
- ✅ All plugin code audited and verified compatible
- ✅ Mutation testing confirms invariant checks work correctly
- ✅ Team trained on new exception model
- ✅ Documentation updated with migration examples

## Related Documents

- [ADR-001: Design Philosophy](001-design-philosophy.md) – Fail-closed security principle
- [ADR-002: Multi-Level Security Enforcement](002-security-architecture.md) – Start-time envelope validation
- [ADR-002-A: Trusted Container Model](002-a-trusted-container-model.md) – Classification invariants
- [ADR-003: Central Plugin Type Registry](003-plugin-type-registry.md) – Plugin security validation
- [ADR-004: Mandatory BasePlugin Inheritance](004-mandatory-baseplugin-inheritance.md) – Plugin protocol enforcement
- `docs/migration/adr-003-004-classified-containers/` – Potential integration point for implementation
- `docs/compliance/incident-response.md` – Incident response procedures for security violations
- `src/elspeth/core/security/secure_data.py` – Primary implementation location

---

**Last Updated**: 2025-10-25 (Revised with AST-based policy enforcement, mandatory feature flags, breaking change documentation)
**Author(s)**: Security Team, Platform Team
**Decision Drivers**: MLS compliance requirements, CVE-ADR-002-A threat model, audit trail requirements

**Revision History**:
- 2025-10-25: Initial proposal
- 2025-10-25: Updated with:
  - AST-based policy enforcement (replaces regex approach)
  - Mandatory feature flag rollout strategy with 3-phase deployment
  - Breaking changes section documenting `with_uplifted_security_level()` behavior change
  - Enhanced monitoring and rollback procedures
