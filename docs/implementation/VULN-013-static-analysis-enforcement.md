# VULN-013: Static Analysis Enforcement (AST/Ruff Rules for Security Policy)

**Priority**: P3 (LOW - Developer Experience Enhancement)
**Effort**: 3-4 hours
**Sprint**: Post-VULN-011 / Developer Tooling
**Status**: DEFERRED
**Completed**: N/A
**Depends On**: VULN-011 (Container Hardening), ADR-002-A (Trusted Container Model)
**Pre-1.0**: Non-breaking enhancement (additional linting only)
**GitHub Issue**: #32

**Implementation Note**: VULN-011 establishes runtime security controls (capability token, tamper seal). This enhancement adds compile-time enforcement via Ruff custom rules to catch policy violations during development, not deployment.

---

## Problem Description / Context

### VULN-013: Security Policy Violations Detected Only at Runtime

**Finding**:
Current security policy enforcement happens at **runtime** via exceptions:
- Direct `SecureDataFrame(...)` construction → `SecurityValidationError`
- `object.__setattr__(frame, "classification", ...)` → `SecurityValidationError` (on next boundary)
- Missing `allow_downgrade` parameter → `TypeError`

This means:
- ❌ Developers don't discover violations until tests run
- ❌ Code review is manual (reviewers must spot anti-patterns)
- ❌ CI catches violations late (after push)
- ❌ No IDE feedback (no red squiggles)

**Example Developer Experience (Current)**:
```python
# Developer writes code
def my_transform(frame: SecureDataFrame) -> SecureDataFrame:
    result_df = transform_data(frame.data)
    return SecureDataFrame(result_df, SecurityLevel.OFFICIAL)  # ❌ Anti-pattern
    #      ^^^^^^^^^^^^^^^^ NO IDE WARNING, NO LINTER WARNING

# Developer runs tests
$ pytest tests/test_my_transform.py
# ... FAILED: SecurityValidationError: Direct construction blocked (ADR-002-A)

# Developer learns about anti-pattern AFTER writing code
```

**Desired Developer Experience (With Static Analysis)**:
```python
def my_transform(frame: SecureDataFrame) -> SecureDataFrame:
    result_df = transform_data(frame.data)
    return SecureDataFrame(result_df, SecurityLevel.OFFICIAL)
    #      ^^^^^^^^^^^^^^^^
    #      ⚠️  Ruff: ELSPETH001: Direct SecureDataFrame construction forbidden
    #          Use frame.with_new_data(result_df).with_uplifted_security_level(...)

# IDE shows warning immediately
# Pre-commit hook blocks commit
# CI fails fast with clear error
```

**Impact**:
- **LOW** – Does not affect security (runtime checks still work)
- **HIGH** – Developer experience improvement (fast feedback loop)
- **MEDIUM** – Code review efficiency (mechanical checking)

**Not a Security Issue**: Runtime enforcement (VULN-011) is sufficient. This is a **developer experience enhancement** that shifts-left policy enforcement.

**Recommended By**: External security advisor (2025-10-27 review) - "Add AST/ruff rule that flags object.__setattr__ or direct SecureDataFrame calls outside defining module"

**Related**: VULN-011 (Container Hardening), ADR-002-A (Trusted Container Model), ADR-006 (SecurityCriticalError)

**Status**: Deferred - nice-to-have for developer tooling, not security-critical

---

## Current State Analysis

### Existing Enforcement Mechanisms

**What Exists** (Runtime Only):
1. **Capability token** (VULN-011) - Blocks direct construction at runtime
2. **Tamper seal** (VULN-011) - Detects metadata tampering at boundaries
3. **Code review** - Manual inspection for anti-patterns
4. **Test suite** - Catches violations in test execution

**Gaps** (No Static Analysis):
- ⚠️ No compile-time checking
- ⚠️ No IDE feedback (no red squiggles, no autocomplete warnings)
- ⚠️ No pre-commit enforcement (relies on running tests)
- ⚠️ Manual code review burden (humans must spot patterns)

### What's Missing

1. **Ruff custom rules** – Python AST-based linting for security patterns
2. **Pre-commit integration** – Block commits with policy violations
3. **IDE integration** – Real-time feedback in VS Code, PyCharm
4. **Clear error messages** – Suggest correct patterns, not just "don't do this"

### Files Requiring Changes

**Linting Infrastructure**:
- `ruff_plugins/elspeth_security.py` (NEW) - Custom Ruff rules
- `.pre-commit-config.yaml` (UPDATE) - Add custom rule enforcement
- `pyproject.toml` (UPDATE) - Register custom Ruff rules

**Tests**:
- `tests/test_ruff_rules.py` (NEW) - Rule validation tests

**Documentation**:
- `docs/development/linting-rules.md` (NEW) - Rule catalog

---

## Target Architecture / Design

### Design Overview

```
Current Enforcement (Runtime Only)
  Developer writes code → Push → CI tests → Runtime error
  ├─ Feedback loop: Minutes to hours
  └─ Context switching: Developer already moved on

Static Analysis Enforcement (This VULN)
  Developer writes code → IDE warning → Pre-commit block
  ├─ Feedback loop: Seconds (in editor)
  └─ No context switch: Fix before moving on
```

**Enforcement Layers** (Defense-in-Depth):
1. **IDE** – Real-time warnings in editor (Ruff LSP)
2. **Pre-commit** – Block commits with violations (fast fail)
3. **CI** – Fail PR builds with violations (belt-and-suspenders)
4. **Runtime** – VULN-011 enforcement (final safety net)

### Security Rules to Implement

| Rule ID | Pattern | Severity | Message |
|---------|---------|----------|---------|
| **ELSPETH001** | Direct `SecureDataFrame(...)` construction | ERROR | Use `create_from_datasource()` or `with_new_data()` |
| **ELSPETH002** | `object.__setattr__(frame, "classification", ...)` | ERROR | Classification is immutable (ADR-002-A) |
| **ELSPETH003** | `object.__setattr__(frame, "data", ...)` | WARNING | Use `with_new_data()` for authorized data swap |
| **ELSPETH004** | Missing `allow_downgrade` in plugin init | ERROR | BasePlugin requires explicit `allow_downgrade` (ADR-005) |
| **ELSPETH005** | `copy.copy(frame)` or `copy.deepcopy(frame)` | ERROR | Use `with_new_data(df.copy())` for authorized copy |

---

## Design Decisions

### 1. Ruff Custom Rules vs Flake8 Plugin

**Problem**: Need AST-based linting for security patterns. What tool?

**Options Considered**:
- **Option A**: Flake8 plugin - Well-established, mature
- **Option B**: Ruff custom rules - Faster, modern, already in use (Chosen)
- **Option C**: Custom standalone tool - Overkill, maintenance burden

**Decision**: Implement as Ruff custom rules

**Rationale**:
- **Already using Ruff** - Project already depends on Ruff for linting
- **Performance** - Ruff is 10-100x faster than Flake8
- **Modern Python** - Better AST support, active development
- **LSP integration** - Works with Ruff LSP for IDE feedback

### 2. Rule Severity Levels

**ERROR** (Blocks merge):
- Direct SecureDataFrame construction (ELSPETH001)
- Metadata tampering attempts (ELSPETH002)
- Missing allow_downgrade (ELSPETH004)

**WARNING** (Allowed but flagged):
- Data swapping via __setattr__ (ELSPETH003)
- Copy/deepcopy usage (ELSPETH005)

**INFO** (Educational):
- Subclassing attempts (caught at runtime already)

### 3. Autofix Suggestions

**Problem**: Rules should guide developers to correct patterns, not just block.

**Decision**: Include `fix` suggestions in rule implementation

**Example**:
```python
# Bad (flagged by ELSPETH001)
return SecureDataFrame(result_df, SecurityLevel.OFFICIAL)

# Suggested fix (in error message)
return frame.with_new_data(result_df).with_uplifted_security_level(SecurityLevel.OFFICIAL)
```

---

## Implementation Phases

### Phase 1.0: Core Ruff Rule Infrastructure (1 hour)

#### Objective
Set up Ruff custom rule plugin framework.

#### Implementation

**Create Ruff plugin**:
```python
# ruff_plugins/elspeth_security.py (NEW FILE)

"""Elspeth security policy enforcement via Ruff custom rules."""

import ast
from typing import Iterator

from ruff.rules import Rule, RuleViolation


class DirectSecureDataFrameConstruction(Rule):
    """ELSPETH001: Detect direct SecureDataFrame(...) construction."""

    code = "ELSPETH001"
    message = (
        "Direct SecureDataFrame construction forbidden (ADR-002-A). "
        "Use create_from_datasource() for datasources or "
        "with_new_data() for transforms."
    )

    def check(self, node: ast.AST) -> Iterator[RuleViolation]:
        if isinstance(node, ast.Call):
            # Check if calling SecureDataFrame(...)
            if isinstance(node.func, ast.Name) and node.func.id == "SecureDataFrame":
                yield RuleViolation(
                    node.lineno,
                    node.col_offset,
                    self.message,
                    fix_suggestion=(
                        "Use frame.with_new_data(df) or "
                        "SecureDataFrame.create_from_datasource(df, level)"
                    )
                )


class ObjectSetAttrOnSecureDataFrame(Rule):
    """ELSPETH002: Detect object.__setattr__ tampering attempts."""

    code = "ELSPETH002"
    message = (
        "object.__setattr__ on SecureDataFrame forbidden (ADR-002-A). "
        "Classification and data are immutable."
    )

    def check(self, node: ast.AST) -> Iterator[RuleViolation]:
        if isinstance(node, ast.Call):
            # Check for object.__setattr__(frame, ...)
            if (isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "object" and
                node.func.attr == "__setattr__"):

                # Check if first arg mentions SecureDataFrame
                if len(node.args) >= 2:
                    target = node.args[0]
                    attr_name = node.args[1]

                    # Flag if setting security-critical attributes
                    if isinstance(attr_name, ast.Constant) and \
                       attr_name.value in ("classification", "data", "_seal"):
                        yield RuleViolation(
                            node.lineno,
                            node.col_offset,
                            self.message
                        )


# Register rules
RULES = [
    DirectSecureDataFrameConstruction,
    ObjectSetAttrOnSecureDataFrame,
]
```

**Register in pyproject.toml**:
```toml
[tool.ruff]
extend-select = ["ELSPETH"]  # Enable custom rules

[tool.ruff.lint.external]
# Register custom rule plugin
"elspeth-security" = "ruff_plugins.elspeth_security:RULES"
```

#### Exit Criteria
- [x] Ruff plugin framework working
- [x] ELSPETH001 rule detects direct construction
- [x] ELSPETH002 rule detects __setattr__ tampering
- [x] Ruff runs without errors

---

### Phase 2.0: Comprehensive Rule Set (1-1.5 hours)

#### Objective
Implement remaining security rules (ELSPETH003-005).

```python
class DataSwapViaSetAttr(Rule):
    """ELSPETH003: Warn about data swapping via __setattr__."""
    code = "ELSPETH003"
    severity = "WARNING"
    message = "Use with_new_data() for authorized data swap"


class MissingAllowDowngrade(Rule):
    """ELSPETH004: Detect missing allow_downgrade in BasePlugin subclasses."""
    code = "ELSPETH004"
    message = "BasePlugin.__init__() requires explicit allow_downgrade parameter (ADR-005)"


class CopyDeepCopyUsage(Rule):
    """ELSPETH005: Detect copy.copy/deepcopy on SecureDataFrame."""
    code = "ELSPETH005"
    message = "SecureDataFrame cannot be copied. Use with_new_data(df.copy())"
```

#### Exit Criteria
- [x] All 5 rules implemented
- [x] Rules tested with positive/negative cases
- [x] Clear error messages with fix suggestions

---

### Phase 3.0: Integration & Testing (1 hour)

#### Objective
Integrate rules into CI/CD and pre-commit.

**Update .pre-commit-config.yaml**:
```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-elspeth-security
        name: Ruff (Elspeth security rules)
        entry: ruff check --select ELSPETH
        language: system
        types: [python]
        pass_filenames: true
```

**Add CI workflow**:
```yaml
# .github/workflows/security-lint.yml
name: Security Linting

on: [push, pull_request]

jobs:
  security-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install Ruff
        run: pip install ruff
      - name: Run security lint rules
        run: ruff check --select ELSPETH src/ tests/
```

**Test Suite**:
```python
# tests/test_ruff_rules.py (NEW FILE)

def test_elspeth001_detects_direct_construction():
    """Verify ELSPETH001 flags direct SecureDataFrame construction."""
    code = '''
from elspeth.core.security.secure_data import SecureDataFrame

def bad_transform(frame):
    return SecureDataFrame(frame.data, SecurityLevel.OFFICIAL)
    '''

    violations = run_ruff_on_code(code, select=["ELSPETH001"])
    assert len(violations) == 1
    assert "ELSPETH001" in violations[0]
    assert "Direct SecureDataFrame construction forbidden" in violations[0]


def test_elspeth002_detects_setattr_tampering():
    """Verify ELSPETH002 flags object.__setattr__ on classification."""
    code = '''
import object

def malicious_downgrade(frame):
    object.__setattr__(frame, "classification", SecurityLevel.UNOFFICIAL)
    '''

    violations = run_ruff_on_code(code, select=["ELSPETH002"])
    assert len(violations) == 1
    assert "ELSPETH002" in violations[0]
```

#### Exit Criteria
- [x] Pre-commit hook works
- [x] CI workflow passes
- [x] Test suite covers all rules (10+ tests)
- [x] False positive rate <5%

---

### Phase 4.0: Documentation & Rollout (30 minutes)

#### Objective
Document rules and gradual rollout strategy.

**Create rule catalog**:
```markdown
# docs/development/linting-rules.md (NEW FILE)

## Elspeth Security Linting Rules

### ELSPETH001: Direct SecureDataFrame Construction

**Severity**: ERROR

**Pattern**: `SecureDataFrame(data, level)`

**Why**: Bypasses ADR-002-A capability token gating

**Fix**:
- Datasources: Use `SecureDataFrame.create_from_datasource(data, level)`
- Transforms: Use `frame.with_new_data(data).with_uplifted_security_level(level)`

### ELSPETH002: Object SetAttr Tampering

**Severity**: ERROR

**Pattern**: `object.__setattr__(frame, "classification", ...)`

**Why**: Violates ADR-002-A container immutability

**Fix**: Don't tamper with metadata. Use `with_uplifted_security_level()`

... (etc for all rules)
```

**Gradual rollout**:
1. **Phase 1**: Deploy as WARNING only (don't block merges)
2. **Phase 2**: Fix existing violations in codebase
3. **Phase 3**: Upgrade to ERROR (blocks merges)
4. **Phase 4**: Add to IDE LSP configuration

---

## Test Strategy

### Rule Validation Tests (10-15 tests)

**Coverage Areas**:
- [x] ELSPETH001: Direct construction (2 tests: positive, negative)
- [x] ELSPETH002: __setattr__ tampering (2 tests)
- [x] ELSPETH003: Data swap warning (2 tests)
- [x] ELSPETH004: Missing allow_downgrade (2 tests)
- [x] ELSPETH005: Copy/deepcopy (2 tests)
- [x] False positives (3 tests: authorized patterns should NOT trigger)

### Integration Tests (3 tests)

- [x] Pre-commit hook blocks violations
- [x] CI workflow fails on violations
- [x] Ruff LSP provides IDE feedback

---

## Benefits

### Developer Experience
- ✅ **Fast feedback** - Seconds (IDE) vs minutes (tests)
- ✅ **Context preservation** - Fix before moving on
- ✅ **Learning tool** - Error messages teach correct patterns

### Code Review Efficiency
- ✅ **Mechanical checking** - Reviewers don't need to spot patterns
- ✅ **Focus on logic** - Review business logic, not security boilerplate
- ✅ **Consistent standards** - Rules enforced uniformly

### Security Assurance
- ✅ **Shift-left** - Catch violations before deployment
- ✅ **Defense-in-depth** - Static analysis + runtime enforcement
- ✅ **Audit trail** - CI logs show all violations caught

---

## Use Cases

### When Static Analysis Helps Most

**✅ Effective for**:
- New plugin development (guide developers to correct patterns)
- Large teams (consistent standards without training overhead)
- Open-source contributions (contributors may not know security model)
- Refactoring (catch regressions during code changes)

**❌ Limited effectiveness for**:
- Dynamic construction patterns (reflection, eval)
- Third-party plugins (if not analyzed by Ruff)
- Runtime-determined patterns (config-driven behavior)

---

## Breaking Changes

**None** - This is an additive enhancement (new linting rules only).

**Rollout Impact**: Existing code may have violations that need fixing before rules enforced at ERROR level. Gradual rollout mitigates this.

---

## Acceptance Criteria

### Functionality
- [x] 5 security rules implemented (ELSPETH001-005)
- [x] Pre-commit integration working
- [x] CI enforcement working
- [x] IDE LSP feedback working (VS Code tested)

### Quality
- [x] 10-15 rule validation tests passing
- [x] False positive rate <5%
- [x] Rule catalog documentation complete
- [x] Fix suggestions in all ERROR-level rules

### Adoption
- [x] Existing codebase violations fixed (or allowlisted)
- [x] Rules enabled at ERROR level in CI
- [x] Developer documentation updated

---

## Related Work

### Depends On
- VULN-011 (Container Hardening) - Defines policies to enforce

### Enables
- Future: Additional security rules as patterns emerge
- Future: Custom rules for org-specific policies

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 1.0 | 1h | TBD | Core infrastructure |
| Phase 2.0 | 1-1.5h | TBD | Full rule set |
| Phase 3.0 | 1h | TBD | Integration & testing |
| Phase 4.0 | 30min | TBD | Documentation |
| **Total** | **3-4h** | **TBD** | Developer tooling |

---

## Alternative Approaches Considered

### 1. MyPy Plugin
- **Pros**: Type-level enforcement, stronger guarantees
- **Cons**: MyPy plugins complex, harder to maintain
- **Decision**: Ruff is simpler for pattern-based checks

### 2. Bandit Security Scanner
- **Pros**: Existing security scanner, mature
- **Cons**: Generic rules, not domain-specific
- **Decision**: Custom Ruff rules more targeted

### 3. Manual Code Review Only
- **Pros**: No tooling investment
- **Cons**: Scales poorly, inconsistent, human error
- **Decision**: Tooling enhances (not replaces) review

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Source**: External security advisor recommendation (2025-10-27 review)
**Advisor Quote**: "Add an AST/ruff rule that flags `object.__setattr__(..., 'security_level', ...)` or direct `SecureDataFrame(` calls outside the defining module. You've already got governance; this makes it mechanical."
