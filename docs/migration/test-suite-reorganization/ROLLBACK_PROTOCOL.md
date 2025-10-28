# Test Reorganization Rollback Protocol

**Objective**: Provide clear, tested procedures for rolling back test reorganization at any phase

**Execution Time**: 10-30 minutes per phase rollback
**Risk Level**: Low (git makes rollback straightforward)

---

## Overview

This protocol ensures test reorganization can be safely reversed at any point without data loss or test breakage. Each phase has specific rollback procedures tested before execution.

**Key Principle**: **Commit frequently** during reorganization to enable granular rollback.

---

## Rollback Decision Matrix

| Situation | Rollback Scope | Procedure |
|-----------|----------------|-----------|
| Tests failing after Phase 0 | Phase 0 only | Rollback P0 |
| Import errors after Phase 2 | Phase 2 only | Rollback P2 |
| Coverage drop after Phase 3 | Phase 3 only | Rollback P3 |
| CI completely broken | All phases | Full Rollback |
| Merge conflicts with main | Rebase/resolve | Conflict Resolution |

---

## Pre-Rollback Checklist

**BEFORE rolling back**:

- [ ] **Document the issue**: Why are we rolling back? (tests failing, import errors, etc.)
- [ ] **Capture logs**: Save pytest output, CI logs, error messages
- [ ] **Check git status**: `git status` to see uncommitted changes
- [ ] **Identify rollback point**: Which phase/commit to roll back to?
- [ ] **Backup uncommitted work**: `git stash` if needed

---

## Phase 0 Rollback: Consolidate Existing Subdirectories

**When**: Tests fail after consolidating subdirectories

**Symptoms**:
- Import errors (fixtures not found)
- Tests in `tests/plugins/nodes/sinks/` fail
- Duplicate test names

**Rollback Procedure**:

```bash
# 1. Identify Phase 0 commits
git log --oneline --grep="phase0" --grep="Phase 0" -i

# 2. Find commit BEFORE Phase 0 started
git log --oneline | grep "Checkpoint: Before Phase 0"

# 3. Hard reset to pre-Phase 0
git reset --hard <commit-before-phase0>

# 4. Verify tests pass
pytest tests/ -v

# 5. Clean up untracked files
git clean -fd

# 6. Verify file structure restored
ls tests/sinks/  # Should exist again
ls tests/plugins/sinks/  # Should exist again
```

**Verification**:
```bash
# Test count should match pre-Phase 0
pytest --collect-only -q | tail -1

# All tests should pass
pytest -v

# Coverage should be unchanged
pytest --cov=elspeth --cov-report=term | grep "TOTAL"
```

---

## Phase 1 Rollback: Audit & Documentation

**When**: Audit reports contain errors or need regeneration

**Symptoms**:
- Incorrect duplicate counts
- Missing fixture analysis
- Report generation errors

**Rollback Procedure**:

```bash
# Phase 1 is analysis-only (no code changes)
# Just delete generated reports and re-run

# 1. Remove generated reports
rm -f docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md
rm -f docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md
rm -f docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md
rm -f docs/migration/test-suite-reorganization/POINTLESS_TESTS_CANDIDATES.md

# 2. Re-run analysis with corrected parameters
python docs/migration/test-suite-reorganization/audit_tests.py \\
    --test-dir tests \\
    --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md

python docs/migration/test-suite-reorganization/find_duplicates.py \\
    --test-dir tests \\
    --output docs/migration/test-suite-reorganization/DUPLICATES_ANALYSIS.md \\
    --threshold 0.85

python docs/migration/test-suite-reorganization/analyze_fixtures.py \\
    --test-dir tests \\
    --output docs/migration/test-suite-reorganization/FIXTURE_ANALYSIS.md
```

**No code rollback needed** - Phase 1 is read-only analysis.

---

## Phase 2 Rollback: Reorganization

**When**: Tests break after moving files

**Symptoms**:
- Import errors (`ModuleNotFoundError`)
- Fixture not found errors
- Tests in `tests/unit/` or `tests/integration/` fail
- CI fails to discover tests

**Rollback Procedure**:

### Option A: Revert Last Batch (Preferred)

If only most recent batch failed:

```bash
# 1. Identify Phase 2 batch commits
git log --oneline --grep="phase2" --grep="Phase 2" -i | head -10

# 2. Revert specific batch
git revert <failing-batch-commit>

# 3. Verify tests pass
pytest tests/ -v

# 4. Clean up empty directories
find tests -type d -empty -delete
```

### Option B: Full Phase 2 Rollback

If multiple batches failed or imports completely broken:

```bash
# 1. Find commit BEFORE Phase 2 started
git log --oneline | grep "Checkpoint: Before Phase 2"

# 2. Hard reset to pre-Phase 2 (DESTRUCTIVE)
git reset --hard <commit-before-phase2>

# WARNING: This loses all Phase 2 work

# 3. Verify file structure restored
ls tests/test_*.py | wc -l  # Should show 136 root files

# 4. Verify tests pass
pytest -v

# 5. Clean up
git clean -fd
```

### Option C: Selective File Restoration

If only specific files need restoration:

```bash
# 1. List files in their original locations
git show HEAD~5:tests/test_adr002_invariants.py > /tmp/original.py

# 2. Restore specific files
git checkout <commit-before-phase2> -- tests/test_adr002_invariants.py

# 3. Remove incorrectly moved files
rm tests/compliance/adr002/test_invariants.py

# 4. Verify
pytest tests/test_adr002_invariants.py -v
```

**Verification**:
```bash
# Test discovery should work
pytest --collect-only -q

# Test count should match baseline
pytest --collect-only -q | tail -1

# All tests should pass
pytest -v

# Import paths should resolve
python -c "from tests.conftest import assert_sanitized_artifact; print('OK')"
```

---

## Phase 3 Rollback: Deduplication

**When**: Coverage drops or tests deleted incorrectly

**Symptoms**:
- Coverage regression >2%
- Critical tests missing
- Test count too low (<175)
- Stakeholders disagree with deletions

**Rollback Procedure**:

```bash
# 1. Identify Phase 3 deletion commits
git log --oneline --grep="phase3" --grep="Phase 3" --grep="deduplicate" -i

# 2. Revert specific deletions
git revert <deletion-commit>

# 3. Verify tests restored
pytest --collect-only -q | tail -1

# 4. Verify coverage restored
pytest --cov=elspeth --cov-report=term | grep "TOTAL"

# 5. If multiple deletions, revert batch
git revert <commit1> <commit2> <commit3>
```

**Verification**:
```bash
# Coverage should be within ±2% of baseline
pytest --cov=elspeth --cov-report=term | grep "TOTAL"

# Test count should be reasonable (>175)
pytest --collect-only -q | tail -1

# No critical tests missing (check stakeholder list)
pytest --collect-only -q | grep "test_adr002"
pytest --collect-only -q | grep "test_security"
```

---

## Full Rollback: Nuclear Option

**When**: Everything is broken, faster to start over

**Symptoms**:
- CI completely broken
- Local tests don't run
- Multiple phases need rollback
- Time-critical (need working main branch NOW)

**Rollback Procedure**:

```bash
# 1. Abandon reorganization branch
git checkout main

# 2. Delete reorganization branch (locally)
git branch -D test-suite-reorganization-phase0
git branch -D test-suite-reorganization-phase2

# 3. Delete remote branch (if pushed)
git push origin --delete test-suite-reorganization-phase2

# 4. Verify main branch works
pytest -v

# 5. Start fresh later (after fixing issues)
```

**Communication**:
```bash
# Notify team
gh pr comment <pr-number> --body "Rollback: Test reorganization abandoned due to [REASON]. Will restart after fixing [ISSUE]."
```

---

## Conflict Resolution (During Rebase)

**When**: Main branch moved forward, reorganization branch has conflicts

**Symptoms**:
- `git pull origin main` shows conflicts
- Files added/modified in main overlap with reorganization

**Resolution Procedure**:

```bash
# 1. Assess conflict scale
git pull origin main
git status

# 2. If < 5 files, resolve manually
git checkout --ours tests/test_new_feature.py  # Keep our version
# OR
git checkout --theirs tests/test_new_feature.py  # Keep main version

# 3. If > 5 files, consider rollback + restart
git merge --abort
git checkout main

# 4. Document conflicts for next attempt
```

**Decision Matrix**:
| Conflicts | Resolution |
|-----------|-----------|
| < 3 files | Resolve manually |
| 3-10 files | Assess case-by-case |
| > 10 files | Rollback, restart after main stabilizes |

---

## Post-Rollback Actions

**After rolling back**:

### 1. Document Failure

```markdown
# rollback-report-YYYY-MM-DD.md

## Rollback Summary
- **Date**: 2025-10-27
- **Phase**: Phase 2
- **Reason**: Import errors in tests/compliance/adr002/
- **Commits reverted**: abc123f, def456a
- **Resolution**: Fixture import paths incorrect

## Root Cause
[Detailed explanation]

## Prevention
[What to do differently next time]

## Next Steps
[How to retry successfully]
```

### 2. Communicate to Team

```bash
# Post in Slack/Teams
"Test reorganization Phase 2 rolled back due to [REASON].
Tests passing again on main. Will retry [TIMELINE] after [FIX]."

# Update PR
gh pr comment <pr-number> --body "Rolled back Phase 2. See rollback-report-*.md for details."
```

### 3. Verify System Stable

```bash
# Verify main branch works
git checkout main
pytest -v --cov=elspeth

# Verify CI passes
gh pr checks

# Verify team can work
# (No blocked PRs due to test failures)
```

### 4. Plan Retry

- Review rollback report
- Fix root cause
- Update plan to prevent recurrence
- Schedule retry (allow buffer for stability)

---

## Rollback Testing (Pre-Migration)

**BEFORE starting migration**, test rollback procedures:

```bash
# 1. Create test branch
git checkout -b rollback-drill

# 2. Make fake changes
mkdir -p tests/fake_structure
git mv tests/test_config.py tests/fake_structure/
git commit -m "TEST: Fake reorganization"

# 3. Test rollback
git reset --hard HEAD~1

# 4. Verify restored
ls tests/test_config.py  # Should exist

# 5. Clean up
git checkout main
git branch -D rollback-drill
```

---

## Emergency Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| Architecture Lead | TBD | Approve rollback decisions |
| DevOps | TBD | Fix CI issues |
| Security Lead | TBD | If ADR-002 tests affected |

---

## Rollback Decision Flowchart

```
Test reorganization failing?
  ↓
Can issue be fixed in <30 minutes?
  Yes → Fix, continue
  No → Consider rollback
    ↓
Is issue isolated to one phase?
  Yes → Rollback that phase only
  No → Full rollback
    ↓
Is issue blocking team?
  Yes → Immediate rollback (communicate)
  No → Schedule rollback (off-hours)
```

---

## Success Criteria

After rollback:

- ✅ All tests passing: `pytest -v`
- ✅ Coverage at baseline: `pytest --cov`
- ✅ CI passing
- ✅ Team unblocked
- ✅ Rollback documented
- ✅ Root cause identified
- ✅ Retry plan created

---

**Last Updated**: 2025-10-27
**Author**: Architecture Team
**Status**: Tested procedures (rollback drill passed)
