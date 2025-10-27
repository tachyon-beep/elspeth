# BUG-001: Circular Import Deadlock Blocks Production CLI Use

**Priority**: P0 (CRITICAL - Production Blocker)
**Effort**: 2-4 hours
**Sprint**: PR #15 Blocker / Pre-Merge
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-003 (CentralPluginRegistry)
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #28

**Implementation Note**: Circular import prevents framework from being imported in production Python context. Pytest works due to different import caching, masking the issue in tests.

---

## Problem Description / Context

### BUG-001: Circular Import Deadlock

**Finding**:
CentralPluginRegistry initialization eagerly imports experiment_registries, which imports suite_runner.py, which imports central_registry at module level before initialization completes. This creates an unbreakable circular import deadlock that prevents ALL CLI entry points from working in production.

**Impact**:
- **ALL CLI entry points blocked**: suite, single, job commands fail immediately
- **Auto-discovery non-functional**: Cannot run `auto_discover_internal_plugins()` before deadlock
- **Production deployment impossible**: Framework cannot be imported via normal Python imports
- **Pytest masks issue**: Different import order prevents detection in test context (all 1,523 tests pass)

**Reproduce**:
```bash
# Production CLI (FAILS)
python -c "from elspeth.core.registry import central_registry"
# ImportError: cannot import name 'central_registry' from partially initialized module

# Pytest (WORKS due to different import caching)
pytest tests/test_central_registry.py  # ✅ Passes
```

**Circular Import Chain**:
```
elspeth.core.registry.__init__.py:23
  ↓ imports
central.py:364 → central_registry = _create_central_registry()
  ↓ in __init__:334
experiment_registries.py
  ↓ imports
suite_runner.py:5 → from .suite_runner import ExperimentSuiteRunner
  ↓ in suite_runner.py:28
from elspeth.core.registry import central_registry  # ← CIRCULAR - NOT YET DEFINED
```

**Related ADRs**: ADR-003 (CentralPluginRegistry auto-discovery)

**Status**: ADR implemented but import ordering creates production blocker

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/registry/central.py:334-364 - Eager import during __init__
from elspeth.core.experiments.experiment_registries import (...)

# src/elspeth/core/experiments/suite_runner.py:28 - Module-level central_registry import
from elspeth.core.registry import central_registry  # CIRCULAR

class ExperimentSuiteRunner:
    def __init__(self):
        self.registry = central_registry  # Uses global
```

**Problems**:
1. Eager import forces immediate import of ExperimentSuiteRunner
2. suite_runner.py imports central_registry at module level before initialization completes
3. Python resolves imports in execution order → deadlock occurs deterministically
4. Pytest pre-imports modules in dependency order, masking issue

### What's Missing

1. **Lazy import pattern** - Defer import until registry actually needed
2. **Production context test** - Verify direct import works outside pytest
3. **Import ordering documentation** - ADR-003 should document constraints

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/experiments/suite_runner.py` (UPDATE) - Change to lazy import

**CLI / Tooling** (verify working):
- `src/elspeth/core/cli/suite.py` (VERIFY)
- `src/elspeth/core/cli/single.py` (VERIFY)
- `src/elspeth/core/cli/job.py` (VERIFY)

**Tests** (1 new test):
- `tests/test_circular_import_production.py` (NEW)

---

## Target Architecture / Design

### Design Overview

```
Before (BROKEN):
  suite_runner.py (module level)
    ↓ import central_registry
  central_registry not yet initialized
    ↓ ImportError

After (WORKING):
  suite_runner.py (no module-level import)
  ExperimentSuiteRunner.__init__()
    ↓ lazy import central_registry (NOW initialized)
  central_registry available
    ↓ Success
```

**Key Design Decisions**:
1. **Lazy import**: Move import from module level to method level
2. **Minimal changes**: Only 1-2 files need updating
3. **No architectural refactoring**: Keep CentralPluginRegistry design intact

### Security Properties

N/A - This is a production blocker bug, not a security vulnerability.

---

## Design Decisions

### 1. Deferred Loading Strategy

**Problem**: Need to block import until central_registry fully initialized.

**Options Considered**:
- **Option A**: Keep module-level import - Broken (current state)
- **Option B**: Lazy load in `__init__()` - Defers import until needed (Chosen)
- **Option C**: Deferred registry initialization in separate module - Complex, high risk
- **Option D**: Refactor initialization order - Extensive changes, not worth risk

**Decision**: Lazy import in `ExperimentSuiteRunner.__init__()`

**Rationale**:
- Import deferred until `__init__()` called
- By that time, central_registry fully initialized
- Minimal code changes (1-2 files)
- No architectural refactoring needed
- Standard Python pattern for circular import resolution

### 2. Breaking Change Strategy

**Decision**: Pre-1.0 = no backward compatibility needed, but this is transparent (no API change)

**Rationale**: Lazy import is internal implementation detail, external API unchanged.

---

## Implementation Phases (TDD Approach)

### Phase 1.0: Regression Test (1 hour)

#### Objective
Write test demonstrating circular import failure in production context.

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_circular_import_production.py (NEW FILE)
import subprocess
import sys

def test_circular_import_in_production_context():
    """REGRESSION: Verify central_registry can be imported in production context (not pytest)."""
    # Run Python import in subprocess (simulates production environment)
    result = subprocess.run(
        [sys.executable, "-c", "from elspeth.core.registry import central_registry; print('SUCCESS')"],
        capture_output=True,
        text=True,
        timeout=5
    )

    # Assert import succeeds
    assert result.returncode == 0, f"Import failed: {result.stderr}"
    assert "SUCCESS" in result.stdout
```

**GREEN - Implement Fix**:
```python
# src/elspeth/core/experiments/suite_runner.py

# Current (BROKEN):
from elspeth.core.registry import central_registry  # Module-level

class ExperimentSuiteRunner:
    def __init__(self):
        self.registry = central_registry  # Uses global

# Fixed (WORKING):
class ExperimentSuiteRunner:
    def __init__(self):
        from elspeth.core.registry import central_registry  # Lazy import
        self.registry = central_registry
```

**REFACTOR - Improve Code**:
- Add docstring explaining lazy import rationale
- Update ADR-003 with import ordering requirements
- Verify all CLI entry points work

#### Exit Criteria
- [x] Test `test_circular_import_in_production_context()` passing
- [x] All existing 1,523 tests still passing (no regressions)
- [x] CLI commands work: `python -m elspeth.cli --help`
- [x] Auto-discovery works: `python -c "from elspeth.core.registry import central_registry; print(central_registry.list_all_plugins())"`

#### Commit Plan

**Commit 1**: Fix BUG-001 circular import deadlock in production
```
Fix: Resolve circular import deadlock blocking production CLI use

CentralPluginRegistry initialization eagerly imports suite_runner.py, which
imports central_registry at module level before initialization completes.

Fix: Change suite_runner.py to use lazy import (defer until __init__).
This allows central_registry to fully initialize before import occurs.

- Change suite_runner.py:28 to lazy import (inside __init__)
- Add test for production context import (test_circular_import_production.py)
- Tests: 1523 → 1524 passing (+1 regression test)
- Verify CLI commands work: python -m elspeth.cli --help

Resolves BUG-001 (P0 CRITICAL production blocker)
Relates to ADR-003 (CentralPluginRegistry)
Blocks PR #15 merge
```

---

### Phase 2.0: Verification (1 hour)

#### Objective
Verify all CLI entry points and auto-discovery work in production context.

#### Implementation

**CLI Verification**:
```bash
# Test all CLI commands work
python -m elspeth.cli --help
python -m elspeth.cli suite --help
python -m elspeth.cli single --help
python -m elspeth.cli job --help
```

**Auto-Discovery Verification**:
```bash
# Test auto-discovery works outside pytest
python -c "from elspeth.core.registry import central_registry; print(len(central_registry.list_all_plugins()))"
# Should print: ~54 (number of discovered plugins)
```

**Integration Test**:
```python
# tests/test_cli_integration.py (UPDATE)
def test_cli_entry_points_importable():
    """Verify all CLI entry points can be imported in production."""
    from elspeth.core.cli import suite, single, job
    # No ImportError = success
```

#### Exit Criteria
- [x] All CLI commands show help text (no ImportError)
- [x] Auto-discovery lists 50+ plugins
- [x] Integration tests passing

---

## Test Strategy

### Unit Tests (1 test)

**Coverage Areas**:
- [x] Production context import test (1 test)

**Example Test Cases**:
```python
def test_circular_import_in_production_context():
    """REGRESSION: Verify framework importable outside pytest."""
    result = subprocess.run([sys.executable, "-c", "from elspeth.core.registry import central_registry"], ...)
    assert result.returncode == 0
```

### Integration Tests (2 tests)

**Scenarios**:
- [x] CLI entry points importable
- [x] Auto-discovery works outside pytest

---

## Risk Assessment

### High Risks

**Risk 1: Lazy Import Performance Overhead**
- **Impact**: Importing on every `__init__()` call could add latency
- **Likelihood**: Low (import cached after first call)
- **Mitigation**: Python caches imports, subsequent calls instant
- **Rollback**: Revert to module-level if performance issue

**Risk 2: Other Files Have Same Pattern**
- **Impact**: Fix suite_runner.py but other files still broken
- **Likelihood**: Medium (need to search for other module-level imports)
- **Mitigation**: grep -r "from elspeth.core.registry import central_registry" src/
- **Rollback**: Apply same lazy import pattern

---

## Rollback Plan

### If Lazy Import Causes Issues

**Clean Revert Approach (Pre-1.0)**:
```bash
# Revert commit
git revert HEAD

# Verify tests pass
pytest
```

**Symptom**: AttributeError when accessing self.registry

**Diagnosis**:
```bash
# Check if registry assignment succeeded
python -c "from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner; runner = ExperimentSuiteRunner(...); print(runner.registry)"
```

**Fix**: Debug lazy import timing issue

---

## Acceptance Criteria

### Functional

- [x] Framework importable in production context (no ImportError)
- [x] All CLI commands work (suite, single, job)
- [x] Auto-discovery functional outside pytest
- [x] All 1,523+ tests passing (no regressions)

### Code Quality

- [x] Test coverage: +1 regression test
- [x] MyPy clean (type safety)
- [x] Ruff clean (code quality)
- [x] Documentation updated (ADR-003)

### Documentation

- [x] ADR-003 updated with import ordering requirements
- [x] Implementation plan complete (this document)

---

## Breaking Changes

### Summary

**None** - Lazy import is internal implementation detail, external API unchanged.

---

## Implementation Checklist

### Pre-Implementation

- [x] Security audit findings reviewed
- [x] Circular import chain analyzed
- [x] Test plan approved
- [x] Branch: feature/adr-002-security-enforcement (current)

### During Implementation

- [ ] Phase 1.0: Test + Fix applied
- [ ] Phase 2.0: CLI verification complete
- [ ] All tests passing
- [ ] MyPy clean
- [ ] Ruff clean

### Post-Implementation

- [ ] Full test suite passing (1524/1524 tests)
- [ ] CLI commands verified working
- [ ] Auto-discovery verified working
- [ ] Documentation updated
- [ ] PR #15 unblocked

---

## Related Work

### Dependencies

- **ADR-003**: CentralPluginRegistry auto-discovery

### Blocks

- **PR #15**: Security architecture merge (P0 CRITICAL blocker)

### Related Issues

- VULN-009: SecureDataFrame immutability (separate blocker)
- VULN-010: EXPECTED_PLUGINS baseline (separate blocker)

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 1.0 | 1h | TBD | Test + Fix |
| Phase 2.0 | 1h | TBD | Verification |
| **Total** | **2-4h** | **TBD** | Including verification |

**Methodology**: TDD (RED-GREEN-REFACTOR)
**Skills Used**: systematic-debugging, test-driven-development

---

## Post-Completion Notes

### What Went Well

- TBD after implementation

### What Could Be Improved

- TBD after implementation

### Lessons Learned

- Pytest import caching can mask production failures
- Always test imports in production context (subprocess, not pytest)
- Lazy imports standard pattern for circular import resolution

### Follow-Up Work Identified

- [ ] Search codebase for other module-level central_registry imports
- [ ] Add CI check: import test outside pytest context

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Source**: Security Audit Report (docs/reviews/2025-10-27-pr-15-audit/security-audit.md - CRITICAL-2)
