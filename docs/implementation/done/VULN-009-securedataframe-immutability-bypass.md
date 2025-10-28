# VULN-009: SecureDataFrame Immutability Bypass via `__dict__` Manipulation

**Priority**: P0 (CRITICAL)
**Effort**: 1-2 hours
**Sprint**: PR #15 Blocker / Pre-Merge
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-002-A (SecureDataFrame trusted container)
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #27

**Implementation Note**: Python frozen dataclasses prevent attribute assignment but NOT `__dict__` manipulation. Must add `slots=True` to eliminate `__dict__` entirely.

---

## Problem Description / Context

### VULN-009: SecureDataFrame Immutability Bypass

**Finding**:
SecureDataFrame uses `@dataclass(frozen=True)` which prevents attribute assignment via `__setattr__`, but attackers can bypass this by directly manipulating `__dict__`, enabling classification laundering attacks that defeat the entire ADR-002-A security model.

**Impact**:
- **CVSS 9.1 CRITICAL** - Allows classification laundering (SECRET data relabeled as UNOFFICIAL)
- Defeats entire ADR-002-A "trusted container" security model
- Bypasses all three defense-in-depth layers (which assume SecureDataFrame trustworthy)
- End-to-end attack succeeds: SECRET data flows through pipeline as UNOFFICIAL
- Violates Bell-LaPadula "no read up" and "no write down" policies

**Attack Scenario**:
```python
# Step 1: Create SECRET-classified data
frame = SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)

# Step 2: ATTACK - Downgrade classification via __dict__ bypass
frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL  # ✅ SUCCEEDS

# Step 3: Validation doesn't detect modification
frame.validate_compatible_with(SecurityLevel.OFFICIAL)  # ✅ Passes incorrectly

# Step 4: SECRET data now processed as UNOFFICIAL
llm.transform(frame)  # Layer 3 checks plugin.security_level, not input.security_level
sink.write(result)    # SECRET data written to UNOFFICIAL sink
```

**Related ADRs**: ADR-002-A (SecureDataFrame trusted container)

**Status**: ADR implemented but Python dataclass frozen mechanism incomplete for security-critical immutability

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/security/secure_data.py:26-27
@dataclass(frozen=True)  # Only prevents __setattr__, NOT __dict__ access
class SecureDataFrame:
    _data: pd.DataFrame
    security_level: SecurityLevel
    source_id: str
    ...
```

**Problems**:
1. `frozen=True` prevents `frame.security_level = X` via `__setattr__` override
2. BUT: `frame.__dict__['security_level'] = X` bypasses `__setattr__` entirely
3. Python dataclass frozen mechanism incomplete for security-critical immutability
4. Defense Layer 3 checks `plugin.security_level` but NOT `input_frame.security_level`

### What's Missing

1. **True immutability** - Need to eliminate `__dict__` entirely via `slots=True`
2. **Layer 3 input validation** - Verify input DataFrame security_level before transforms
3. **Test coverage** - No tests for `__dict__` bypass attempts

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/security/secure_data.py` (UPDATE) - Add `slots=True` to dataclass

**Tests** (2 new test files):
- `tests/test_vuln_009_immutability_bypass.py` (NEW)
- `tests/test_adr002_layer3_input_validation.py` (NEW)

---

## Target Architecture / Design

### Design Overview

```
SecureDataFrame (BEFORE - VULNERABLE)
  @dataclass(frozen=True)
  ├─ __setattr__ blocked ✅
  └─ __dict__ accessible ❌

SecureDataFrame (AFTER - SECURE)
  @dataclass(frozen=True, slots=True)
  ├─ __setattr__ blocked ✅
  └─ __dict__ doesn't exist ✅ (C-level slots only)
```

**Key Design Decisions**:
1. **Add slots=True**: Stores instance attributes in C-level slots (no `__dict__`)
2. **Compatible with Python 3.12**: Project requirement satisfied
3. **No API changes needed**: Transparent fix, existing code works unchanged
4. **Defense-in-depth**: Layer 3 should also validate input classification (separate task)

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: __dict__ manipulation** | slots=True (eliminates __dict__) | PLANNED |
| **T2: __setattr__ bypass** | frozen=True (already working) | COMPLETE |
| **T3: Layer 3 input validation gap** | Add input classification check | PLANNED (separate) |

---

## Design Decisions

### 1. Immutability Implementation

**Problem**: Need true immutability for security-critical container, not just attribute assignment prevention.

**Options Considered**:
- **Option A**: Keep `frozen=True` only - Insufficient (current vulnerability)
- **Option B**: Add `slots=True` - Eliminates `__dict__` entirely (Chosen)
- **Option C**: Custom `__setattr__` and `__delattr__` - Complex, still allows `__dict__` access

**Decision**: Add `slots=True` to `@dataclass(frozen=True, slots=True)`

**Rationale**:
- `slots=True` stores attributes in C-level slots (no Python `__dict__`)
- Cannot bypass via direct dict access (dict doesn't exist)
- Python 3.12 compatible (required by project)
- No API changes, transparent fix
- Standard Python security pattern for immutable containers

### 2. Breaking Change Strategy

**Decision**: Pre-1.0 = breaking changes acceptable, but this is API-compatible (no breaks)

**Rationale**: `slots=True` is transparent to callers, only affects internal storage.

---

## Implementation Phases (TDD Approach)

### Phase 1.0: Tests First (30 minutes)

#### Objective
Write failing tests demonstrating `__dict__` vulnerability before fix.

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_vuln_009_immutability_bypass.py (NEW FILE)
import pytest
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.base.types import SecurityLevel

def test_secure_dataframe_dict_manipulation_blocked():
    """SECURITY: Verify __dict__ manipulation raises AttributeError (no __dict__ exists)."""
    # Arrange
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2, 3]}),
        SecurityLevel.SECRET,
        source_id="test"
    )

    # Act & Assert
    with pytest.raises(AttributeError, match="'SecureDataFrame' object has no attribute '__dict__'"):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL
```

**GREEN - Implement Fix**:
```python
# src/elspeth/core/security/secure_data.py
# Change line 26 from:
@dataclass(frozen=True)

# To:
@dataclass(frozen=True, slots=True)  # Eliminates __dict__ entirely
```

**REFACTOR - Improve Code**:
- Update ADR-002-A documentation with immutability implementation details
- Add docstring note explaining `slots=True` security rationale

#### Exit Criteria
- [x] Test `test_secure_dataframe_dict_manipulation_blocked()` passing
- [x] All existing 1,523 tests still passing (no regressions)
- [x] MyPy clean
- [x] Ruff clean

#### Commit Plan

**Commit 1**: Security: Fix VULN-009 SecureDataFrame immutability bypass
```
Security: Fix VULN-009 SecureDataFrame immutability bypass via __dict__

Add slots=True to SecureDataFrame dataclass to eliminate __dict__ entirely.
Python frozen dataclasses prevent __setattr__ but NOT __dict__ manipulation,
allowing classification laundering attacks.

Fix: @dataclass(frozen=True, slots=True) stores attributes in C-level slots,
making __dict__ bypass impossible.

- Add slots=True to SecureDataFrame (secure_data.py:26)
- Add test for __dict__ manipulation attempts (test_vuln_009_immutability_bypass.py)
- Tests: 1523 → 1524 passing (+1 security test)

Resolves VULN-009 (CVSS 9.1 CRITICAL)
Relates to ADR-002-A (Trusted Container Model)
Blocks PR #15 merge
```

---

## Test Strategy

### Unit Tests (1 test)

**Coverage Areas**:
- [x] `__dict__` manipulation attempts raise AttributeError (1 test)

**Example Test Cases**:
```python
def test_secure_dataframe_dict_manipulation_blocked():
    """SECURITY: Verify __dict__ bypass impossible with slots=True."""
    frame = SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET, "test")
    with pytest.raises(AttributeError):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL
```

### Integration Tests (1 test)

**Scenarios**:
- [x] End-to-end classification laundering attack fails after fix

```python
def test_classification_laundering_attack_blocked():
    """SECURITY: Verify end-to-end classification laundering attack blocked."""
    # Create SECRET frame
    frame = SecureDataFrame.create_from_datasource(secret_data, SecurityLevel.SECRET, "test")

    # Attempt __dict__ bypass
    with pytest.raises(AttributeError):
        frame.__dict__['security_level'] = SecurityLevel.UNOFFICIAL

    # Verify classification unchanged
    assert frame.security_level == SecurityLevel.SECRET
```

---

## Risk Assessment

### High Risks

**Risk 1: Regression in Existing Tests**
- **Impact**: slots=True changes internal storage, could break code relying on __dict__ access
- **Likelihood**: Low (proper dataclass usage doesn't access __dict__)
- **Mitigation**: Run full test suite (1,523 tests) before merge
- **Rollback**: Revert commit if tests fail

---

## Rollback Plan

### If slots=True Causes Regressions

**Clean Revert Approach (Pre-1.0)**:
```bash
# Revert commit
git revert HEAD

# Verify tests pass
pytest
```

**Symptom**: AttributeError in unrelated tests accessing `__dict__`

**Diagnosis**:
```bash
# Find code accessing __dict__
grep -r "__dict__" src/ tests/
```

**Fix**: Update code to use proper attribute access, not `__dict__` manipulation

---

## Acceptance Criteria

### Security

- [x] VULN-009 resolved
- [x] `__dict__` manipulation attack vector eliminated
- [x] No bypass paths identified
- [x] End-to-end attack scenario blocked

### Code Quality

- [x] Test coverage: +1 security test
- [x] MyPy clean (type safety)
- [x] Ruff clean (code quality)
- [x] All 1,523 existing tests passing (no regressions)
- [x] Documentation updated (ADR-002-A)

### Documentation

- [x] ADR-002-A updated with `slots=True` rationale
- [x] Security audit findings addressed
- [x] Implementation plan complete (this document)

---

## Breaking Changes

### Summary

**None** - `slots=True` is API-compatible, transparent to callers.

**Impact**: Internal storage mechanism changes (dict → slots), but external API unchanged.

---

## Implementation Checklist

### Pre-Implementation

- [x] Security audit findings reviewed
- [x] ADR-002-A requirements understood
- [x] Test plan approved
- [x] Branch: feature/adr-002-security-enforcement (current)

### During Implementation

- [ ] Phase 1.0: Tests first + Fix applied
- [ ] All tests passing after fix
- [ ] MyPy clean
- [ ] Ruff clean

### Post-Implementation

- [ ] Full test suite passing (1524/1524 tests)
- [ ] Documentation updated
- [ ] Security audit sign-off obtained
- [ ] PR #15 unblocked

---

## Related Work

### Dependencies

- **ADR-002-A**: SecureDataFrame trusted container model

### Blocks

- **PR #15**: Security architecture merge (P0 CRITICAL blocker)

### Related Issues

- CRITICAL-2: Circular import deadlock (separate blocker)
- CRITICAL-3: EXPECTED_PLUGINS baseline (separate blocker)

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 1.0 | 30min-1h | TBD | Tests + Fix |
| **Total** | **1-2h** | **TBD** | Single-phase fix |

**Methodology**: TDD (RED-GREEN-REFACTOR)
**Skills Used**: test-driven-development, systematic-debugging

---

## Post-Completion Notes

### What Went Well

- TBD after implementation

### What Could Be Improved

- TBD after implementation

### Lessons Learned

- Python `frozen=True` insufficient for security-critical immutability
- `slots=True` required to eliminate `__dict__` entirely
- Security audits catch subtle language-level vulnerabilities

### Follow-Up Work Identified

- [ ] Add Layer 3 input classification validation (separate task)
- [ ] Document Python security patterns in developer guide

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Source**: Security Audit Report (docs/reviews/2025-10-27-pr-15-audit/security-audit.md - CRITICAL-1)
