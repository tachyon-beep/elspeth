# Test Suite Quality Remediation Plan

**Epic:** elspeth-rapid-0kou
**Status:** Planning → Execution
**Timeline:** 2-3 weeks (13-19 working days)
**Impact:** Reduce test count by 20-25% while improving coverage quality from 74% to 95%

---

## Executive Summary

Systematic review of 7000+ tests across 450 files identified:
- **15-20 critical bugs** - tests that provide false confidence
- **100-150 stupidity tests** - testing framework features, not code
- **70-100 redundant tests** - exact duplicates of existing coverage
- **50-60 missing edge cases** - critical scenarios untested

**Goal:** Remove ~1500 low-value tests, fix critical bugs, add missing coverage, improve maintainability by 30%.

---

## Phase 1: Critical Bugs (P0) - Days 1-5

**Objective:** Fix tests that provide false confidence in critical paths

### Tasks (5 issues)

#### P0.1: test_orchestrator_uses_graph_node_ids (elspeth-rapid-hw6m)
- **File:** tests/engine/test_orchestrator_core.py:432-519
- **Bug:** MagicMock auto-creates attributes, doesn't prove orchestrator set them
- **Fix:** Use PropertyMock with assertion tracking
- **Impact:** Orchestrator node_id assignment bugs detectable
- **Time:** 2 hours

#### P0.2: test_get_run_contract_verifies_hash (elspeth-rapid-bmzj)
- **File:** tests/core/landscape/test_recorder_contracts.py:749-779
- **Bug:** Only checks recomputed hash, never verifies stored DB hash
- **Fix:** Query DB directly, verify stored_hash == computed_hash
- **Impact:** Audit trail hash tampering/corruption detectable
- **Time:** 2 hours

#### P0.3: Delete TestDatabaseOps class (elspeth-rapid-jc66)
- **File:** tests/core/landscape/test_database_ops.py:8-93
- **Bug:** Entire class tests MagicMock chains, not database operations
- **Fix:** DELETE 85 lines, keep Tier1Validation tests
- **Impact:** No false confidence in database operations
- **Time:** 30 minutes

#### P0.4: Fix contract propagation skip tests (elspeth-rapid-cyh5)
- **File:** tests/contracts/test_contract_propagation.py:459-518
- **Bug:** Assert "not None" instead of verifying fields excluded
- **Fix:** Check field_names set, verify skip happened
- **Impact:** Non-primitive field inclusion bugs detectable
- **Time:** 1 hour

#### P0.5: Fix Azure batch audit trail test (elspeth-rapid-o4yc)
- **File:** tests/plugins/llm/test_azure_batch.py:1152-1236
- **Bug:** Manually constructs list, doesn't verify record_call invoked
- **Fix:** Use mock.call_count and call_args_list verification
- **Impact:** Audit trail recording bugs detectable
- **Time:** 2 hours

**Phase 1 Total:** 7.5 hours (~1 day)

---

## Phase 2: High-Value Deletions (P1) - Days 6-8

**Objective:** Remove tests that add maintenance burden without coverage value

### Tasks (3 issues)

#### P1.1: Delete stupidity tests (elspeth-rapid-48je)
- **Files:** test_canonical.py, test_schema.py, test_models.py
- **Lines:** ~170 lines deleted
- **Tests:** ~20 tests removed
- **What:** Primitive passthrough, import tests, table existence checks
- **Impact:** -170 LOC, zero coverage loss
- **Time:** 3 hours

#### P1.2: Delete config frozen/structure tests (elspeth-rapid-0901)
- **File:** tests/core/test_config.py
- **Lines:** ~200 lines deleted
- **Tests:** ~25 tests removed
- **What:** Pydantic frozen=True validation, attribute assignment tests
- **Impact:** -200 LOC, zero coverage loss
- **Time:** 2 hours

#### P1.3: Delete test_implements_protocol tests (elspeth-rapid-5z0u)
- **Files:** tests/plugins/**/*.py (15 files)
- **Lines:** ~120 lines deleted
- **Tests:** ~15 tests removed
- **What:** isinstance(plugin, Protocol) checks across all plugins
- **Impact:** -120 LOC, zero coverage loss (mypy catches this)
- **Time:** 2 hours

**Phase 2 Total:** 7 hours (~1 day)

---

## Phase 3: Consolidation (P2) - Days 9-12

**Objective:** Reduce redundancy, improve maintainability

### Tasks (2 issues)

#### P2.1: Consolidate coalesce policy tests (elspeth-rapid-feli)
- **File:** tests/engine/test_coalesce_executor.py:179-930
- **Current:** 4 test classes (require_all, first, quorum, best_effort)
- **Target:** 1 parametrized test covering all policies
- **Lines:** ~150 lines reduction
- **Impact:** Single maintenance point, clearer policy comparison
- **Time:** 6 hours

#### P2.2: Consolidate gate parametrized tests (elspeth-rapid-bi2m)
- **File:** tests/engine/test_gate_executor.py:36-643
- **Current:** Parametrized with conditional branches inside tests
- **Target:** Separate test classes or single path
- **Lines:** ~100 lines reduction
- **Impact:** Improved clarity, easier debugging
- **Time:** 4 hours

**Phase 3 Total:** 10 hours (~1.5 days)

---

## Phase 4: Edge Cases (P2) - Days 13-17

**Objective:** Add missing critical test coverage

### Tasks (2 issues)

#### P2.3: Add DAG/Orchestrator/Contracts edge cases (elspeth-rapid-xelq)
- **Files:** test_dag.py, test_orchestrator_*.py, test_contract_propagation.py
- **Tests Added:** 14 new tests
  - Disconnected graphs
  - Cleanup on early termination
  - Multiple sink node_id assignment
  - Field rename scenarios
  - Type conflicts
  - None value handling
- **Impact:** Realistic failure modes covered
- **Time:** 12 hours

#### P2.4: Add Canonical/Database/Web Scrape edge cases (elspeth-rapid-shz9)
- **Files:** test_canonical.py, test_database_sink.py, test_web_scrape.py
- **Tests Added:** 12 new tests
  - NaN in nested arrays
  - Datetime/UUID serialization
  - Database connection variants
  - HTTP redirects (301/302/307)
  - Malformed HTML handling
- **Impact:** External boundary coverage
- **Time:** 10 hours

**Phase 4 Total:** 22 hours (~3 days)

---

## Phase 5: Documentation (P3) - Days 18-19

**Objective:** Prevent future test quality degradation

### Tasks (2 issues)

#### P3.1: Document test quality guidelines (elspeth-rapid-t5gr)
- **File:** CLAUDE.md (new section)
- **Content:**
  - Prohibited patterns (framework testing, over-mocking, weak assertions)
  - Required patterns (edge cases, integration over mocking, clear intent)
  - Examples of good/bad tests
- **Impact:** Future tests meet quality bar
- **Time:** 4 hours

#### P3.2: Update test execution docs (elspeth-rapid-7k7c)
- **Files:** README.md, docs/testing.md
- **Content:**
  - Test metrics (before/after cleanup)
  - Running tests by category
  - Coverage reports
- **Impact:** Clear testing documentation
- **Time:** 2 hours

**Phase 5 Total:** 6 hours (~1 day)

---

## Timeline Summary

| Phase | Days | Hours | Tasks | Key Deliverables |
|-------|------|-------|-------|------------------|
| **P0: Critical Bugs** | 1-5 | 7.5 | 5 | All critical test bugs fixed |
| **P1: Deletions** | 6-8 | 7.0 | 3 | ~490 lines deleted, 60 tests removed |
| **P2a: Consolidation** | 9-12 | 10.0 | 2 | ~250 lines consolidated |
| **P2b: Edge Cases** | 13-17 | 22.0 | 2 | 26 new critical tests added |
| **P3: Documentation** | 18-19 | 6.0 | 2 | Test quality standards documented |
| **TOTAL** | **19 days** | **52.5 hours** | **14 tasks** | **Test suite transformed** |

---

## Success Metrics

### Before Remediation
- Total Tests: ~7,000
- Test Files: ~450
- Lines of Test Code: ~85,000
- Effective Coverage: 74% (26% is cruft)
- Maintenance Cost: HIGH (duplicates, false positives)
- CI Execution Time: Baseline

### After Remediation (Target)
- Total Tests: ~6,000 (-14%)
- Test Files: ~400 (-11%)
- Lines of Test Code: ~73,000 (-14%)
- Effective Coverage: 95% (+28% quality)
- Maintenance Cost: MEDIUM (-30% effort)
- CI Execution Time: -15% (fewer tests)

### Quality Improvements
- Critical bugs fixed: 5/5 (100%)
- Stupidity tests removed: 60+
- Redundancy eliminated: 250+ lines
- Edge cases added: 26+
- Documentation clarity: +100%

---

## Risk Mitigation

### Risk: Breaking existing behavior
- **Mitigation:** Each deletion verified with coverage report
- **Validation:** CI must stay green throughout

### Risk: Losing important edge case coverage
- **Mitigation:** Manual review of each deletion
- **Validation:** Cross-reference with bug history

### Risk: Team resistance to large deletions
- **Mitigation:** Phased approach, clear rationale per deletion
- **Validation:** Demo improved test clarity in PRs

### Risk: Regression after cleanup
- **Mitigation:** Run full test suite before/after each phase
- **Validation:** Mutation testing on critical paths

---

## Execution Strategy

1. **Start with P0 tasks** - Immediate value, high visibility
2. **PR per phase** - Reviewable chunks, incremental progress
3. **Document learnings** - Add to CLAUDE.md as you fix
4. **Track metrics** - Before/after screenshots for each phase
5. **Celebrate wins** - Share coverage improvements with team

---

## Dependencies

```
elspeth-rapid-0kou (Epic)
├── Phase 1 (P0) - No dependencies
│   ├── elspeth-rapid-hw6m (P0.1)
│   ├── elspeth-rapid-bmzj (P0.2)
│   ├── elspeth-rapid-jc66 (P0.3)
│   ├── elspeth-rapid-cyh5 (P0.4)
│   └── elspeth-rapid-o4yc (P0.5)
├── Phase 2 (P1) - After P0 complete
│   ├── elspeth-rapid-48je (P1.1)
│   ├── elspeth-rapid-0901 (P1.2)
│   └── elspeth-rapid-5z0u (P1.3)
├── Phase 3 (P2a) - After P1 complete
│   ├── elspeth-rapid-feli (P2.1)
│   └── elspeth-rapid-bi2m (P2.2)
├── Phase 4 (P2b) - Parallel with P2a
│   ├── elspeth-rapid-xelq (P2.3)
│   └── elspeth-rapid-shz9 (P2.4)
└── Phase 5 (P3) - After all testing complete
    ├── elspeth-rapid-t5gr (P3.1)
    └── elspeth-rapid-7k7c (P3.2)
```

---

## Next Steps

1. **Review this plan** - Validate priorities, timeline
2. **Start Phase 1** - Fix critical bugs (highest ROI)
3. **Create PRs** - One per phase for review
4. **Track progress** - Update epic status daily
5. **Adjust as needed** - Refine estimates after Phase 1

**Ready to begin:** `bd update elspeth-rapid-hw6m --status=in_progress`
