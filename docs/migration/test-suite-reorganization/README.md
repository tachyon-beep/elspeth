# Test Suite Reorganization Migration

**Status**: 🔴 **BLOCKED** - Waiting for ADR-002-003-004 unified migration to complete
**Created**: 2025-10-26
**Estimated Effort**: 14-20 hours (spread over 3-5 days)
**Owner**: TBD

---

## Executive Summary

Reorganize Elspeth's test suite from **136 root-level test files** into a structured, maintainable hierarchy aligned with the source code architecture. This migration addresses test duplication, improves discoverability, and reduces maintenance overhead.

### The Problem

**Current State**:
- 📁 **218 total test files**, **136 in root directory** (should be 0)
- 🔄 **Duplicate tests**: 5 identified duplicate test function names across files
- 🎯 **Poor organization**: 28 sink tests, 12 CLI tests scattered in root
- 📈 **High maintenance cost**: Largest file is 1,342 LOC
- 🗂️ **Incomplete subdirectories**: Existing `tests/plugins/`, `tests/core/` underutilized

**Impact**:
- Developers struggle to find relevant tests
- Duplicate effort when writing new tests
- Fragile test suite (changes break unrelated tests)
- Slow test discovery and execution

### The Solution

Three-phase migration with **aggressive deduplication** and **fresh reorganization**:

1. **Phase 1: Audit** - Automated analysis, duplication detection, value assessment
2. **Phase 2: Reorganization** - Move to structure aligned with `src/elspeth/`
3. **Phase 3: Deduplication** - Remove/consolidate redundant tests

**Expected Outcomes**:
- ✅ **0 test files in root**
- ✅ **15-20% reduction in test count** (~175-185 files remaining)
- ✅ **Improved performance**: 10-20% faster test suite
- ✅ **Maintained coverage**: ≥80% on critical paths
- ✅ **Better developer experience**: Tests easy to find and understand

---

## Prerequisites

### ⚠️ BLOCKERS

1. **ADR-002-003-004 Unified Migration Must Complete**
   - Current refactor touches `BasePlugin`, security model, registries
   - Test suite changes would conflict with ongoing work
   - Wait for `docs/migration/adr-002-003-004-unified/00-STATUS.md` to show "✅ Complete"

2. **Test Suite Must Be Stable**
   - All tests passing (or xfail where appropriate)
   - No pending security enforcement changes
   - Coverage baseline established

### Requirements

- ✅ Python 3.12+
- ✅ pytest with all plugins installed
- ✅ Git (for preserving file history with `git mv`)
- ✅ ~20 hours developer time (can be split across multiple days)

---

## Migration Phases

### Phase 1: Audit & Documentation (4-6 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] `TEST_AUDIT_REPORT.md` - Comprehensive test metadata analysis
- [ ] `DUPLICATES_ANALYSIS.md` - Duplication detection results
- [ ] `POINTLESS_TESTS_CANDIDATES.md` - Low-value test assessment
- [ ] `PROPOSED_STRUCTURE.md` - Final directory tree with file mappings

**Key Activities**:
- Run automated analysis scripts (see `TOOLS.md`)
- Identify exact duplicates, functional duplicates, overlapping coverage
- Apply aggressive value assessment criteria
- Design final directory structure

**See**: `00-AUDIT_METHODOLOGY.md`

---

### Phase 2: Reorganization (6-8 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] New directory structure created (`tests/unit/`, `tests/integration/`, etc.)
- [ ] All 136 root files moved to appropriate subdirectories
- [ ] Imports updated (all tests passing)
- [ ] Git history preserved (via `git mv`)
- [ ] `REORGANIZATION_SUMMARY.md` generated

**Key Activities**:
- Create new directory structure
- Move tests using `git mv` (preserves history)
- Update import paths
- Verify `pytest --collect-only -q` passes
- Run full test suite to ensure no breakage

**See**: `01-REORGANIZATION_PLAN.md`

---

### Phase 3: Deduplication & Cleanup (4-6 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] Duplicate tests removed
- [ ] Overlapping tests consolidated via parametrization
- [ ] Test count reduced by 15-20%
- [ ] Coverage maintained/improved
- [ ] `DEDUPLICATION_SUMMARY.md` generated

**Key Activities**:
- Review `POINTLESS_TESTS_CANDIDATES.md` with stakeholders
- Delete exact duplicates and trivial tests
- Consolidate overlapping integration tests
- Refactor shared fixtures
- Verify coverage and performance improvements

**See**: `02-DEDUPLICATION_STRATEGY.md`

---

## Quick Reference

### Current State Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Total test files | 218 | ~175-185 |
| Root-level test files | 136 | 0 |
| Duplicate test names | 5 | 0 |
| Largest test file (LOC) | 1,342 | <800 |
| Test suite runtime | Baseline TBD | -10-20% |
| Coverage (critical paths) | ≥80% | ≥80% (maintained) |

### Proposed Directory Structure

```
tests/
├── unit/                          # Fast, isolated unit tests
│   ├── core/                      # Core framework logic
│   ├── plugins/                   # Plugin implementations
│   └── utils/                     # Utility functions
├── integration/                   # Multi-component integration
│   ├── cli/                       # CLI end-to-end tests
│   ├── suite_runner/              # Suite runner workflows
│   └── orchestrator/              # Orchestration scenarios
├── compliance/                    # ADR compliance tests
│   ├── adr002/                    # Multi-Level Security
│   ├── adr004/                    # BasePlugin compliance
│   └── adr005/                    # Frozen plugins
├── performance/                   # Slow performance tests
└── fixtures/                      # Shared fixtures & test data
```

See `PROPOSED_STRUCTURE.md` for complete tree.

---

## Risk Assessment

### High Risks

1. **Test Breakage During Move**
   - **Mitigation**: Verify `pytest --collect-only` after each batch of moves
   - **Mitigation**: Commit frequently, easy rollback via git

2. **Import Path Errors**
   - **Mitigation**: Automated import rewriting script
   - **Mitigation**: Comprehensive import verification before commit

3. **Coverage Regression**
   - **Mitigation**: Run `pytest --cov` before and after each phase
   - **Mitigation**: Block merge if coverage drops >2%

### Medium Risks

4. **Disagreement on "Pointless" Tests**
   - **Mitigation**: Phase 1 produces candidates for stakeholder review
   - **Mitigation**: Document rationale for each deletion recommendation

5. **Time Overrun**
   - **Mitigation**: Phases are independently completable
   - **Mitigation**: Can stop after Phase 2 if time limited

---

## Success Criteria

**Phase 1 Complete**:
- ✅ Audit reports generated
- ✅ Duplication analysis complete
- ✅ Stakeholders reviewed pointless test candidates
- ✅ Directory structure finalized

**Phase 2 Complete**:
- ✅ 0 test files in `tests/` root
- ✅ All tests passing (`pytest -v`)
- ✅ Imports updated correctly
- ✅ Git history preserved

**Phase 3 Complete**:
- ✅ Test count reduced 15-20%
- ✅ No duplicate test names
- ✅ Coverage maintained (±2%)
- ✅ Performance improved 10-20%

**Overall Success**:
- ✅ All 3 phases complete
- ✅ Test suite more maintainable
- ✅ Developers can find tests easily
- ✅ Zero regressions

---

## Related Documentation

- **Phase 1**: `00-AUDIT_METHODOLOGY.md` - Automated analysis approach
- **Phase 2**: `01-REORGANIZATION_PLAN.md` - File movement strategy
- **Phase 3**: `02-DEDUPLICATION_STRATEGY.md` - Consolidation approach
- **Structure**: `PROPOSED_STRUCTURE.md` - Complete directory tree
- **Tooling**: `TOOLS.md` - Automation script specifications

---

## Timeline Estimate

**Best Case** (14 hours, 3 days):
- Day 1: Phase 1 (4 hours), Phase 2 start (2 hours)
- Day 2: Phase 2 complete (4 hours), Phase 3 start (2 hours)
- Day 3: Phase 3 complete (2 hours)

**Realistic** (18 hours, 4-5 days):
- Day 1: Phase 1 (5 hours)
- Day 2: Phase 2 (7 hours)
- Day 3: Phase 3 (4 hours)
- Day 4: Buffer for reviews, fixes (2 hours)

**Worst Case** (20 hours, 5 days):
- Includes stakeholder reviews, unexpected test failures, import issues

---

## Contact & Escalation

**Questions**: See individual phase documentation
**Blockers**: Escalate to architecture team
**Conflicts**: With ADR-002-003-004 migration → halt and reassess

---

**Last Updated**: 2025-10-26
**Next Review**: When ADR-002-003-004 migration completes
