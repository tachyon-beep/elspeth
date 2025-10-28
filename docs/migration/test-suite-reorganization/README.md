# Test Suite Reorganization Migration

**Status**: 🔴 **BLOCKED** - Waiting for ADR-002-003-004 unified migration to complete
**Created**: 2025-10-26
**Updated**: 2025-10-27
**Estimated Effort**: 29-40 hours (spread over 6-8 days)
**Owner**: TBD

---

## Executive Summary

Reorganize Elspeth's test suite from **136 root-level test files** into a structured, maintainable hierarchy aligned with the source code architecture. This migration addresses test duplication, improves discoverability, and reduces maintenance overhead.

### The Problem

**Current State**:
- 📁 **218 total test files**, **136 in root directory** + **58 in subdirectories** (root should be 0)
- 🔄 **Competing hierarchies**: `tests/sinks/`, `tests/plugins/sinks/`, `tests/plugins/nodes/sinks/` (3 locations for same purpose)
- 🎯 **Poor organization**: 28 sink tests, 12 CLI tests scattered in root
- 📈 **High maintenance cost**: Largest file is 1,350 LOC
- 🗂️ **Incomplete subdirectories**: Existing `tests/plugins/`, `tests/core/` underutilized and conflicting

**Impact**:
- Developers struggle to find relevant tests
- Duplicate effort when writing new tests
- Fragile test suite (changes break unrelated tests)
- Slow test discovery and execution

### The Solution

Four-phase migration with **competing hierarchy consolidation**, **automated analysis**, and **aggressive deduplication**:

0. **Phase 0: Consolidate Existing** - Merge redundant subdirectories (tests/sinks/ → tests/plugins/nodes/sinks/)
1. **Phase 1: Audit** - Automated analysis, duplication detection, value assessment (scripts implemented)
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

   **Unblock Criteria** (ALL must be met):
   - ✅ `docs/migration/adr-002-003-004-unified/00-STATUS.md` shows "✅ Phase 4 Complete"
   - ✅ All BasePlugin refactor PRs merged to main
   - ✅ No security enforcement changes in-flight for ≥3 days
   - ✅ Sprint retrospective confirms no upcoming ADR-002 work planned

   **Fallback**: Unblock by **[USER TO SPECIFY DATE]** regardless of ADR status (requires merge conflict resolution strategy)

2. **Test Suite Must Be Stable**
   - All tests passing (or xfail where appropriate)
   - No pending security enforcement changes
   - Coverage baseline established (run `pytest --cov` before Phase 0)

### Requirements

- ✅ Python 3.12+
- ✅ pytest with all plugins installed
- ✅ PyYAML (for migration scripts: `pip install pyyaml`)
- ✅ Git (for preserving file history with `git mv`)
- ✅ **29-40 hours developer time** (can be split across 6-8 days)
  - Phase 0: 3-4 hours
  - Phase 1: 6-8 hours (with automation scripts)
  - Phase 2: 10-14 hours (consolidation + reorganization)
  - Phase 3: 6-8 hours (deduplication + stakeholder review)

---

## Migration Phases

### Phase 0: Consolidate Existing Subdirectories (3-4 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] Existing subdirectories consolidated (tests/sinks/ → tests/plugins/nodes/sinks/)
- [ ] Redundant hierarchies eliminated
- [ ] 58 files moved to unified structure
- [ ] All tests passing
- [ ] `PHASE0_SUMMARY.md` generated

**Key Activities**:
- Merge `tests/sinks/` and `tests/plugins/sinks/` into `tests/plugins/nodes/sinks/`
- Merge `tests/plugins/sources/` into `tests/plugins/nodes/sources/`
- Create subcategories (blob/, bundles/, repository/, visual/, etc.)
- Verify with `pytest` after each batch
- Document file mappings

**See**: `00-CONSOLIDATE_EXISTING.md`

---

### Phase 1: Audit & Documentation (6-8 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] `TEST_AUDIT_REPORT.md` - Comprehensive test metadata analysis
- [ ] `DUPLICATES_ANALYSIS.md` - Duplication detection results
- [ ] `POINTLESS_TESTS_CANDIDATES.md` - Low-value test assessment
- [ ] `PROPOSED_STRUCTURE.md` - Final directory tree with file mappings

**Key Activities**:
- Run automated analysis scripts (✅ **IMPLEMENTED**: audit_tests.py, find_duplicates.py, analyze_fixtures.py)
- Identify exact duplicates, functional duplicates, overlapping coverage
- Apply aggressive value assessment criteria
- Design final directory structure

**Prerequisites**: Phase 0 complete

**See**: `00-AUDIT_METHODOLOGY.md`, automation scripts in this directory

---

### Phase 2: Reorganization (10-14 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] New directory structure created (`tests/unit/`, `tests/integration/`, etc.)
- [ ] All 136 root files moved to appropriate subdirectories
- [ ] Imports updated (all tests passing)
- [ ] Git history preserved (via `git mv`)
- [ ] Fixture imports verified
- [ ] `REORGANIZATION_SUMMARY.md` generated

**Key Activities**:
- Create final directory structure
- Move tests using `git mv` (preserves history)
- Update import paths (✅ **SCRIPT**: migrate_tests.py)
- Verify `pytest --collect-only -q` passes after each batch
- Run full test suite to ensure no breakage
- Verify fixture scoping correct

**Prerequisites**: Phase 0 complete, Phase 1 analysis reviewed

**See**: `01-REORGANIZATION_PLAN.md`, `03-FIXTURE_STRATEGY.md`

---

### Phase 3: Deduplication & Cleanup (6-8 hours)

**Status**: ⚪ Not Started
**Deliverables**:
- [ ] Duplicate tests removed
- [ ] Overlapping tests consolidated via parametrization
- [ ] Test count reduced by 15-20%
- [ ] Coverage maintained/improved
- [ ] Stakeholder approval documented
- [ ] `DEDUPLICATION_SUMMARY.md` generated

**Key Activities**:
- Review `POINTLESS_TESTS_CANDIDATES.md` with stakeholders (architecture team, security team)
- Delete exact duplicates and trivial tests
- Consolidate overlapping integration tests
- Refactor shared fixtures
- Verify coverage and performance improvements

**Prerequisites**: Phase 0-2 complete, stakeholder review completed

**See**: `02-DEDUPLICATION_STRATEGY.md`

---

## Execution Instructions

### Pre-Execution Checklist

Before starting, verify blockers are resolved:

```bash
# 1. Check ADR-002-003-004 status
cat docs/migration/adr-002-003-004-unified/00-STATUS.md | grep "Phase 4"
# Must show: "✅ Phase 4 Complete"

# 2. Verify test suite is stable
pytest -v
# All tests must pass (or be properly xfailed)

# 3. Establish coverage baseline
pytest --cov=elspeth --cov-report=term | tee coverage_baseline.txt
grep "TOTAL" coverage_baseline.txt
# Record baseline percentage

# 4. Create migration branch
git checkout -b test-suite-reorganization
git commit -m "Checkpoint: Before test reorganization" --allow-empty
```

---

### Phase 0: Consolidate Existing Subdirectories (3-4 hours)

**Execute commands from**: `00-CONSOLIDATE_EXISTING.md`

**Quick Start**:
```bash
# Navigate to project root
cd /home/john/elspeth

# Follow batches in 00-CONSOLIDATE_EXISTING.md
# Example Batch 1 (Blob sinks):
mkdir -p tests/plugins/nodes/sinks/blob
git mv tests/sinks/test_outputs_blob_account.py tests/plugins/nodes/sinks/blob/
git mv tests/sinks/test_blob_sink_errors.py tests/plugins/nodes/sinks/blob/
# ... (continue with all files in batch)

# Verify after each batch
pytest tests/plugins/nodes/sinks/blob/ -v

# Commit after each batch
git add -A
git commit -m "test: Consolidate blob sink tests into tests/plugins/nodes/sinks/blob/"

# Repeat for all 7 batches in 00-CONSOLIDATE_EXISTING.md
```

**Verification**:
```bash
# Verify no competing hierarchies remain
ls tests/sinks/  # Should not exist
ls tests/plugins/sinks/  # Should not exist

# All tests passing
pytest tests/ -v
```

**Deliverable**: `PHASE0_SUMMARY.md` documenting file mappings

---

### Phase 1: Audit & Documentation (6-8 hours)

**Execute commands from**: `00-AUDIT_METHODOLOGY.md`

**Quick Start**:
```bash
# Step 1: Run test metadata audit
python docs/migration/test-suite-reorganization/audit_tests.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md \
    --format markdown

# Step 2: Run fixture analysis
python docs/migration/test-suite-reorganization/analyze_fixtures.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md

# Step 3: Run duplicate detection
python docs/migration/test-suite-reorganization/find_duplicates.py \
    --test-dir tests \
    --output docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md \
    --threshold 0.85

# Step 4: Review outputs
cat docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md
cat docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md
cat docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md

# Step 5: Create value assessment (manual)
# Review audit + duplicate reports
# Create POINTLESS_TESTS_CANDIDATES.md with deletion candidates

# Step 6: Stakeholder review
# Share reports with architecture team, security team
# Get approval on deletion candidates
# Finalize PROPOSED_STRUCTURE.md
```

**Deliverables**:
- `TEST_AUDIT_REPORT.md`
- `FIXTURE_ANALYSIS.md`
- `DUPLICATES_ANALYSIS.md`
- `POINTLESS_TESTS_CANDIDATES.md` (manual)
- `PROPOSED_STRUCTURE.md` (manual)

---

### Phase 2: Reorganization (10-14 hours)

**Execute commands from**: `01-REORGANIZATION_PLAN.md`

**Quick Start**:
```bash
# Step 1: Create directory structure
mkdir -p tests/unit/core/{cli,pipeline,registries,security,validation}
mkdir -p tests/unit/plugins/nodes/sources/{csv,blob}
mkdir -p tests/unit/plugins/nodes/sinks/{csv,excel,blob,signed,bundles,repository,visual,analytics,embeddings,utilities}
mkdir -p tests/unit/plugins/nodes/transforms/llm
mkdir -p tests/unit/plugins/experiments/{aggregators,validators,baselines,lifecycle}
mkdir -p tests/unit/utils
mkdir -p tests/integration/{cli,suite_runner,orchestrator,middleware,retrieval,signed}
mkdir -p tests/compliance/{adr002,adr002a,adr004,adr005,security}
mkdir -p tests/performance/baselines
mkdir -p tests/fixtures/test_data

# Step 2: Execute file moves in batches (see 01-REORGANIZATION_PLAN.md)
# Example Batch 1 (Compliance tests):
git mv tests/test_adr002_baseplugin_compliance.py tests/compliance/adr002/test_baseplugin_compliance.py
git mv tests/test_adr002_invariants.py tests/compliance/adr002/test_invariants.py
# ... (continue with all files in batch)

# Verify after each batch
pytest tests/compliance/adr002/ --collect-only -q
pytest tests/compliance/adr002/ -v

# Commit after each batch
git add -A
git commit -m "test: Move compliance tests to tests/compliance/ (Phase 2.1)"

# Step 3: Update imports (after all moves complete)
python docs/migration/test-suite-reorganization/migrate_tests.py update-imports --test-dir tests/

# Verify imports
pytest --collect-only -q

# Commit
git add -A
git commit -m "test: Update import paths after reorganization"

# Step 4: Final verification
pytest -v
pytest --cov=elspeth --cov-report=term | grep "TOTAL"
```

**Deliverable**: `REORGANIZATION_SUMMARY.md` with file mapping table

---

### Phase 3: Deduplication & Cleanup (6-8 hours)

**Execute commands from**: `02-DEDUPLICATION_STRATEGY.md`

**Quick Start**:
```bash
# Step 1: Review approved deletions
cat docs/migration/test-suite-reorganization/POINTLESS_TESTS_CANDIDATES.md | grep "APPROVED"

# Step 2: Delete exact duplicates (one at a time)
# For each approved deletion:
git rm tests/path/to/duplicate_test.py
pytest -v  # Verify tests still pass
git commit -m "test: Remove duplicate test_xyz (exact duplicate of ...)"

# Step 3: Consolidate via parametrization
# For overlapping tests, refactor to use @pytest.mark.parametrize
# Example in 02-DEDUPLICATION_STRATEGY.md

# Step 4: Verify coverage maintained
pytest --cov=elspeth --cov-report=term | tee coverage_final.txt
grep "TOTAL" coverage_final.txt
# Compare to coverage_baseline.txt (must be within ±2%)

# Step 5: Verify performance improved
pytest --durations=20
# Compare to baseline (should be 10-20% faster)

# Final commit
git add -A
git commit -m "test: Complete deduplication and cleanup (Phase 3)"
```

**Deliverable**: `DEDUPLICATION_SUMMARY.md` with metrics

---

### Post-Migration

```bash
# 1. Update CI/CD configuration (see 04-CI_CD_UPDATES.md)
# Review .github/workflows/*.yml for hardcoded test paths

# 2. Generate final summary
cat > MIGRATION_COMPLETE.md <<EOF
# Test Suite Reorganization Complete

**Date**: $(date +%Y-%m-%d)
**Duration**: [ACTUAL] hours ([ESTIMATED]: 29-40 hours)

## Metrics
- Files reorganized: [COUNT]
- Tests deleted: [COUNT]
- Coverage: [BASELINE]% → [FINAL]%
- Performance: [BASELINE]s → [FINAL]s

## Phases
- Phase 0: ✅ Complete
- Phase 1: ✅ Complete
- Phase 2: ✅ Complete
- Phase 3: ✅ Complete

## Deliverables
- TEST_AUDIT_REPORT.md
- FIXTURE_ANALYSIS.md
- DUPLICATES_ANALYSIS.md
- POINTLESS_TESTS_CANDIDATES.md
- PROPOSED_STRUCTURE.md
- PHASE0_SUMMARY.md
- REORGANIZATION_SUMMARY.md
- DEDUPLICATION_SUMMARY.md
EOF

# 3. Create pull request
git push origin test-suite-reorganization
gh pr create --title "Test Suite Reorganization" \
  --body "$(cat MIGRATION_COMPLETE.md)" \
  --base main

# 4. Monitor CI checks
gh pr checks
```

---

### Emergency Rollback

If anything goes wrong at any phase:

```bash
# See ROLLBACK_PROTOCOL.md for detailed procedures

# Quick rollback to before current phase
git log --oneline | head -10
git reset --hard <commit-before-phase>

# Or revert specific commit
git revert <failing-commit>

# Verify tests pass after rollback
pytest -v
```

---

## Quick Reference

### Current State Metrics

| Metric | Value | Target |
|--------|-------|--------|
| Total test files | 218 | ~175-185 |
| Root-level test files | 136 | 0 |
| Subdirectory test files | 58 | Organized by Phase 0 |
| Competing hierarchies | 3 (sinks/, plugins/sinks/, plugins/nodes/sinks/) | 1 |
| Largest test file (LOC) | 1,350 | <800 |
| Test suite runtime | Baseline TBD | -10-20% |
| Coverage (critical paths) | ≥80% | ≥80% (maintained) |
| **Effort estimate** | **29-40 hours** | **6-8 days** |

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

**Phase 0 Complete**:
- ✅ 58 subdirectory files consolidated into unified structure
- ✅ Redundant hierarchies eliminated (tests/sinks/, tests/plugins/sinks/ removed)
- ✅ All tests passing
- ✅ Git history preserved

**Phase 1 Complete**:
- ✅ Audit reports generated (TEST_AUDIT_REPORT.md, DUPLICATES_ANALYSIS.md, FIXTURE_ANALYSIS.md)
- ✅ Duplication analysis complete
- ✅ Stakeholders reviewed pointless test candidates
- ✅ Directory structure finalized

**Phase 2 Complete**:
- ✅ 0 test files in `tests/` root
- ✅ All tests passing (`pytest -v`)
- ✅ Imports updated correctly
- ✅ Fixture imports verified
- ✅ Git history preserved

**Phase 3 Complete**:
- ✅ Test count reduced 15-20%
- ✅ No duplicate test names
- ✅ Coverage maintained (±2%)
- ✅ Performance improved 10-20%
- ✅ Stakeholder approvals documented

**Overall Success**:
- ✅ All 4 phases complete (0-3)
- ✅ Test suite more maintainable
- ✅ Developers can find tests easily
- ✅ Zero regressions
- ✅ 29-40 hour effort target met

---

## Related Documentation

- **Phase 0**: `00-CONSOLIDATE_EXISTING.md` - Consolidate existing subdirectories
- **Phase 1**: `00-AUDIT_METHODOLOGY.md` - Automated analysis approach
- **Phase 2**: `01-REORGANIZATION_PLAN.md` - File movement strategy
- **Phase 3**: `02-DEDUPLICATION_STRATEGY.md` - Consolidation approach
- **Supporting Docs**:
  - `03-FIXTURE_STRATEGY.md` - Fixture migration strategy
  - `04-CI_CD_UPDATES.md` - CI/CD configuration updates
  - `ROLLBACK_PROTOCOL.md` - Emergency rollback procedures
  - `PROPOSED_STRUCTURE.md` - Complete directory tree
  - `TOOLS.md` - Automation script documentation
- **Automation Scripts** (in this directory):
  - `audit_tests.py` - Test metadata extraction
  - `find_duplicates.py` - Duplicate detection
  - `analyze_fixtures.py` - Fixture dependency analysis
  - `migrate_tests.py` - File movement and import updates

---

## Timeline Estimate

**Best Case** (29 hours, 6 days):
- Day 1: Phase 0 (3 hours), Phase 1 start (3 hours)
- Day 2: Phase 1 complete (3 hours), Phase 2 start (3 hours)
- Day 3: Phase 2 continue (7 hours)
- Day 4: Phase 2 complete (3 hours), Phase 3 start (3 hours)
- Day 5: Phase 3 continue (3 hours)
- Day 6: Phase 3 complete, verification (1 hour)

**Realistic** (35 hours, 7 days):
- Day 1: Phase 0 complete (4 hours)
- Day 2: Phase 1 complete (7 hours)
- Day 3: Phase 2 start (7 hours)
- Day 4: Phase 2 continue (7 hours)
- Day 5: Phase 2 complete (3 hours), Phase 3 start (3 hours)
- Day 6: Phase 3 continue (4 hours)
- Day 7: Phase 3 complete, buffer for reviews (2 hours)

**Worst Case** (40 hours, 8 days):
- Includes stakeholder reviews, unexpected test failures, import issues, fixture conflicts
- Allows 1-2 hour buffer per phase for unexpected issues

---

## Contact & Escalation

**Questions**: See individual phase documentation
**Blockers**: Escalate to architecture team
**Conflicts**: With ADR-002-003-004 migration → halt and reassess

---

**Last Updated**: 2025-10-27 (Phase 0 added, automation scripts implemented, timeline revised, execution instructions added)
**Next Review**: When ADR-002-003-004 migration completes
