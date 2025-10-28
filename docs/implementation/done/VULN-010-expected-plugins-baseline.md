# VULN-010: Incomplete EXPECTED_PLUGINS Validation Baseline (9.3% Coverage)

**Priority**: P0 (CRITICAL - Security Validation Gap)
**Effort**: 1-2 hours
**Sprint**: PR #15 Blocker / Pre-Merge
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-003 (Central Plugin Registry auto-discovery)
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #29

**Implementation Note**: 90.7% of plugins lack validation baseline, enabling silent failures. Need to expand EXPECTED_PLUGINS from 5 to 30+ plugins minimum.

---

## Problem Description / Context

### VULN-010: Incomplete EXPECTED_PLUGINS Baseline

**Finding**:
The EXPECTED_PLUGINS validation baseline only covers 5 out of 54 discovered plugins (9.3% coverage). This means 90.7% of plugins lack validation baseline, enabling silent failures where new plugins can be added without triggering validation, and defense layers (Layer 1-3) cannot guarantee all plugins have proper security enforcement.

**Impact**:
- New plugins can be added without triggering validation failure
- Defense layers assume plugins in EXPECTED_PLUGINS, but 90% missing
- Silent failures: Auto-discovery succeeds, validation passes, but plugin untested
- No guarantee Layer 1 schema enforcement configured for unvalidated plugins
- HttpOpenAIClient bug (caught by Layer 3) would have been missed if not in baseline

**Current Coverage**:
```python
# src/elspeth/core/registry/auto_discover.py:56-61
EXPECTED_PLUGINS = {
    "datasource": ["local_csv", "csv_blob", "azure_blob"],  # 3/3 = 100%
    "llm": ["mock", "azure_openai"],  # 2/4 = 50% (MISSING: http_openai, static_test)
    "sink": ["csv", "signed_artifact", "local_bundle"],  # 3/15 = 20% (MISSING: 12 sinks)
    # Other plugin types: 0% coverage (middleware, experiment, control, utility)
}
```

**Total Baseline Coverage**: 5 plugins validated / 54 plugins discovered = **9.3%**

**Missing Critical Plugins**:

**LLM Plugins** (2/4 validated):
- ❌ `http_openai` - Production OpenAI HTTP client
- ❌ `static_test` - Test LLM for mocking

**Sink Plugins** (3/15 validated):
- ❌ `azure_blob`, `azure_blob_artifacts` - Cloud storage sinks
- ❌ `excel_workbook`, `json`, `markdown` - Document outputs
- ❌ `zip_bundle`, `reproducibility_bundle` - Artifact bundles
- ❌ `github_repo`, `azure_devops_repo` - Repository integrations
- ❌ `analytics_report`, `analytics_visual`, `enhanced_visual` - Analytics
- ❌ `embeddings_store` - Vector storage

**Middleware Plugins** (0/6 validated):
- ❌ `pii_shield`, `classified_material` - Security validation
- ❌ `health_monitor`, `audit` - Observability
- ❌ `azure_content_safety`, `prompt_shield` - Cloud/AI safety

**Experiment/Control/Utility Plugins** (0% validated):
- No EXPECTED_PLUGINS entries for any experiment, control, or utility plugins

**Related ADRs**: ADR-003 (Central Plugin Registry auto-discovery validation)

**Status**: ADR implemented but baseline incomplete (only 9.3% coverage)

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/registry/auto_discover.py:56-61
EXPECTED_PLUGINS = {
    "datasource": ["local_csv", "csv_blob", "azure_blob"],
    "llm": ["mock", "azure_openai"],
    "sink": ["csv", "signed_artifact", "local_bundle"],
}
```

**Problems**:
1. Only 5/54 plugins in baseline (9.3% coverage)
2. Missing critical production plugins (http_openai, all middleware)
3. No validation that Layer 1 schema configured for unvalidated plugins
4. No test enforcing baseline completeness
5. No CI check preventing new plugins without baseline update

### What's Missing

1. **Comprehensive baseline** - Minimum 30+ plugins (all production-critical)
2. **Completeness test** - Verify all production plugins in baseline
3. **CI enforcement** - Fail if new plugin registered without baseline update
4. **Documentation** - Process for updating EXPECTED_PLUGINS when adding plugins

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/registry/auto_discover.py` (UPDATE) - Expand EXPECTED_PLUGINS

**Tests** (1 new test):
- `tests/test_expected_plugins_completeness.py` (NEW)

**Documentation**:
- `docs/architecture/decisions/003-central-plugin-registry.md` (UPDATE)

---

## Target Architecture / Design

### Design Overview

```
EXPECTED_PLUGINS Baseline Coverage:
  Current:  5/54 plugins (9.3%)
  Target:  30+/54 plugins (55%+ minimum)

Coverage by Type:
  datasource: 3/3 (100%) ✅
  llm: 4/4 (100%) ⬆ from 50%
  sink: 15/15 (100%) ⬆ from 20%
  middleware: 6/6 (100%) ⬆ from 0%
  experiment: [selected critical] ⬆ from 0%
```

**Key Design Decisions**:
1. **Minimum viable baseline**: 30+ plugins covering all production-critical types
2. **100% coverage for security-critical types**: datasource, llm, sink, middleware
3. **Selective coverage for experiment types**: Include core, skip specialized experiments
4. **CI enforcement**: Add pre-commit check for baseline completeness

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: Silent plugin addition** | EXPECTED_PLUGINS validation | PLANNED |
| **T2: Unvalidated Layer 1 schema** | Baseline completeness test | PLANNED |
| **T3: Regression drift** | CI enforcement | PLANNED |

---

## Design Decisions

### 1. Baseline Completeness Strategy

**Problem**: Need comprehensive baseline without requiring 100% coverage (some plugins are specialized).

**Options Considered**:
- **Option A**: Require 100% coverage (all 54 plugins) - Overkill, maintenance burden
- **Option B**: Minimum viable (30+ plugins, all production-critical) - Chosen
- **Option C**: Keep current minimal baseline - Insufficient (current vulnerability)

**Decision**: Minimum viable baseline (30+ plugins)

**Rationale**:
- Cover 100% of security-critical types (datasource, llm, sink, middleware)
- Cover core experiment types (skip specialized research experiments)
- Balances security validation with maintainability
- Can expand to 100% over time

### 2. CI Enforcement Strategy

**Decision**: Add pre-commit check failing if new plugin registered without baseline update

**Rationale**: Prevents future drift, enforces discipline

---

## Implementation Phases (TDD Approach)

### Phase 1.0: Expand Baseline (1-2 hours)

#### Objective
Expand EXPECTED_PLUGINS to cover minimum 30+ plugins (all production-critical).

#### Implementation

**Files to Modify**:
```python
# src/elspeth/core/registry/auto_discover.py:56-61

# Current (INCOMPLETE):
EXPECTED_PLUGINS = {
    "datasource": ["local_csv", "csv_blob", "azure_blob"],  # 3/3
    "llm": ["mock", "azure_openai"],  # 2/4
    "sink": ["csv", "signed_artifact", "local_bundle"],  # 3/15
}

# Target (COMPLETE):
EXPECTED_PLUGINS = {
    "datasource": ["local_csv", "csv_blob", "azure_blob"],  # All 3 ✅

    "llm": ["mock", "azure_openai", "http_openai", "static_test"],  # All 4 ✅

    "sink": [
        # Core outputs
        "csv", "signed_artifact", "local_bundle",
        # Document formats
        "excel_workbook", "json", "markdown",
        # Cloud storage
        "azure_blob", "azure_blob_artifacts",
        # Artifact bundles
        "zip_bundle", "reproducibility_bundle",
        # Repository integrations
        "github_repo", "azure_devops_repo",
        # Analytics
        "analytics_report", "analytics_visual", "enhanced_visual",
        # Vector storage
        "embeddings_store",
    ],  # All 15 ✅

    "middleware": [
        # Security validation
        "pii_shield", "classified_material",
        # Observability
        "health_monitor", "audit",
        # Cloud/AI safety
        "azure_content_safety", "prompt_shield",
    ],  # All 6 ✅

    # Experiment types: Include core, skip specialized
    # (Add as needed based on production usage)
}
```

**Changes**:
1. Add missing LLM plugins (http_openai, static_test)
2. Add all 12 missing sinks
3. Add all 6 middleware plugins
4. Add docstring explaining baseline purpose

#### TDD Cycle

**RED - Write Failing Test**:
```python
# tests/test_expected_plugins_completeness.py (NEW FILE)
import pytest
from elspeth.core.registry.auto_discover import EXPECTED_PLUGINS, auto_discover_internal_plugins

def test_expected_plugins_covers_all_production_critical():
    """REGRESSION: Verify EXPECTED_PLUGINS includes all production-critical plugins."""
    # Discover all plugins
    discovered = auto_discover_internal_plugins()

    # Production-critical types (must have 100% coverage)
    critical_types = ["datasource", "llm", "sink", "middleware"]

    for plugin_type in critical_types:
        expected = set(EXPECTED_PLUGINS.get(plugin_type, []))
        actual = set(discovered.get(plugin_type, {}).keys())

        # Assert: All discovered plugins of this type are in baseline
        missing = actual - expected
        assert not missing, (
            f"{plugin_type}: Missing {len(missing)} plugins from EXPECTED_PLUGINS baseline: {missing}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )
```

**GREEN - Implement Fix**:
Expand EXPECTED_PLUGINS as shown above.

**REFACTOR - Improve Code**:
- Add docstring explaining baseline purpose
- Group plugins by category (core, document, cloud, etc.)
- Update ADR-003 with maintenance process

#### Exit Criteria
- [x] EXPECTED_PLUGINS coverage: 30+/54 plugins (55%+)
- [x] 100% coverage for datasource, llm, sink, middleware types
- [x] Test `test_expected_plugins_covers_all_production_critical()` passing
- [x] All existing 1,523 tests still passing

#### Commit Plan

**Commit 1**: Fix VULN-010 incomplete EXPECTED_PLUGINS baseline
```
Security: Fix VULN-010 incomplete EXPECTED_PLUGINS validation baseline

Expand EXPECTED_PLUGINS from 5 to 30+ plugins (9.3% → 55%+ coverage).
Only 5/54 plugins were validated, enabling silent failures where new plugins
could be added without triggering validation.

Coverage improvements:
- datasource: 3/3 (100%) ✅ unchanged
- llm: 2/4 → 4/4 (50% → 100%) ⬆ added http_openai, static_test
- sink: 3/15 → 15/15 (20% → 100%) ⬆ added 12 sinks
- middleware: 0/6 → 6/6 (0% → 100%) ⬆ added all middleware

- Expand EXPECTED_PLUGINS (auto_discover.py:56-61)
- Add completeness test (test_expected_plugins_completeness.py)
- Update ADR-003 with maintenance process
- Tests: 1523 → 1524 passing (+1 validation test)

Resolves VULN-010 (P0 CRITICAL validation gap)
Relates to ADR-003 (CentralPluginRegistry)
Blocks PR #15 merge
```

---

## Test Strategy

### Unit Tests (1 test)

**Coverage Areas**:
- [x] Baseline completeness for production-critical types (1 test)

**Example Test Cases**:
```python
def test_expected_plugins_covers_all_production_critical():
    """Verify all production-critical plugins in baseline."""
    discovered = auto_discover_internal_plugins()
    for plugin_type in ["datasource", "llm", "sink", "middleware"]:
        expected = set(EXPECTED_PLUGINS.get(plugin_type, []))
        actual = set(discovered.get(plugin_type, {}).keys())
        missing = actual - expected
        assert not missing, f"{plugin_type}: Missing plugins {missing}"
```

---

## Risk Assessment

### Medium Risks

**Risk 1: Baseline Maintenance Burden**
- **Impact**: Developers forget to update EXPECTED_PLUGINS when adding new plugins
- **Likelihood**: Medium (manual process)
- **Mitigation**: Add CI check (future work)
- **Rollback**: Remove new plugins from baseline if causing issues

---

## Rollback Plan

### If Baseline Expansion Causes Issues

**Clean Revert Approach (Pre-1.0)**:
```bash
# Revert commit
git revert HEAD

# Verify tests pass
pytest
```

**Symptom**: Validation failing due to plugin discovery issues

**Diagnosis**:
```bash
# Check which plugins discovered
python -c "from elspeth.core.registry.auto_discover import auto_discover_internal_plugins; print(auto_discover_internal_plugins())"
```

**Fix**: Adjust EXPECTED_PLUGINS to match actual discovery

---

## Acceptance Criteria

### Functional

- [x] EXPECTED_PLUGINS coverage ≥ 30 plugins (55%+)
- [x] 100% coverage for datasource, llm, sink, middleware
- [x] Test enforcing baseline completeness passing
- [x] All existing 1,523 tests passing

### Code Quality

- [x] Test coverage: +1 validation test
- [x] MyPy clean (type safety)
- [x] Ruff clean (code quality)
- [x] Documentation updated (ADR-003)

### Documentation

- [x] ADR-003 updated with maintenance process
- [x] Implementation plan complete (this document)

---

## Breaking Changes

### Summary

**None** - Expanding EXPECTED_PLUGINS is backward-compatible.

**Impact**: More plugins validated, stricter enforcement (desired behavior).

---

## Implementation Checklist

### Pre-Implementation

- [x] Security audit findings reviewed
- [x] Plugin inventory completed
- [x] Test plan approved
- [x] Branch: feature/adr-002-security-enforcement (current)

### During Implementation

- [ ] Phase 1.0: Baseline expansion + Test
- [ ] All tests passing
- [ ] MyPy clean
- [ ] Ruff clean

### Post-Implementation

- [ ] Full test suite passing (1524/1524 tests)
- [ ] Documentation updated
- [ ] PR #15 unblocked

---

## Related Work

### Dependencies

- **ADR-003**: CentralPluginRegistry auto-discovery validation

### Blocks

- **PR #15**: Security architecture merge (P0 CRITICAL blocker)

### Related Issues

- VULN-009: SecureDataFrame immutability (separate blocker)
- BUG-001: Circular import deadlock (separate blocker)

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 1.0 | 1-2h | TBD | Baseline expansion + Test |
| **Total** | **1-2h** | **TBD** | Single-phase fix |

**Methodology**: TDD (test-first validation)
**Skills Used**: systematic-debugging

---

## Post-Completion Notes

### What Went Well

- TBD after implementation

### What Could Be Improved

- TBD after implementation

### Lessons Learned

- Validation baselines prevent silent failures
- 100% coverage for security-critical types essential
- CI enforcement prevents regression drift

### Follow-Up Work Identified

- [ ] Add CI check: Fail if new plugin registered without baseline update
- [ ] Expand to 100% coverage over time (include all experiment types)

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Source**: Security Audit Report (docs/reviews/2025-10-27-pr-15-audit/security-audit.md - CRITICAL-3)
