# Rollback Procedures & Migration Checklist

**Date**: October 14, 2025
**Purpose**: Safe migration with rollback capability at each phase
**Status**: GATE PASSED ✅

---

## Executive Summary

The migration is designed with **5 phases**, each leaving the system in a **working state**. Rollback is possible after any phase by reverting commits.

### Key Safety Features
- ✅ **Phase checkpoints**: System works after each phase
- ✅ **Git-based rollback**: Simple `git revert` or `git reset`
- ✅ **Test gates**: All 546 tests must pass before proceeding
- ✅ **Backward compatibility**: Shims prevent breaking changes
- ✅ **Incremental migration**: Can pause at any phase

---

## Migration Phases (5 Total)

### Phase 1: Orchestration Abstraction (3-4 hours)
**Goal**: Create orchestrator plugin structure
**Changes**:
- Create `plugins/orchestrators/experiment/` directory
- Move experiment runner logic
- Add orchestration protocol
- Update imports

**Checkpoint**: All 546 tests pass, sample suite runs

**Rollback**: `git reset --hard HEAD~N` (N = commits in phase)

---

### Phase 2: Node Reorganization (3-4 hours)
**Goal**: Reorganize plugins into sources/sinks/transforms
**Changes**:
- Create `plugins/nodes/sources/`, `nodes/sinks/`, `nodes/transforms/`
- Move datasources → `nodes/sources/`
- Move sinks → `nodes/sinks/`
- Move LLMs → `nodes/transforms/llm/`
- Create backward compatibility shims

**Checkpoint**: All 546 tests pass, sample suite runs, shims work

**Rollback**: `git reset --hard HEAD~N`

---

### Phase 3: Security Hardening (2-3 hours)
**Goal**: Remove critical silent defaults
**Changes**:
- Remove api_key_env defaults (4 instances)
- Remove table/field name defaults (6 instances)
- Make pattern required in regex validator
- Update tests

**Checkpoint**: All 546+ tests pass (security enforcement tests now pass), sample suite runs

**Rollback**: `git reset --hard HEAD~N`

---

### Phase 4: Protocol Consolidation (2-3 hours)
**Goal**: Consolidate registry protocols
**Changes**:
- Merge 18 registries → 7 registries
- Consolidate LLM middleware registry
- Consolidate experiment plugin registries
- Update imports

**Checkpoint**: All 546 tests pass, import count reduced

**Rollback**: `git reset --hard HEAD~N`

---

### Phase 5: Documentation & Cleanup (2-3 hours)
**Goal**: Update docs, deprecation warnings, cleanup
**Changes**:
- Update architecture docs
- Add deprecation warnings to shims
- Update plugin catalogue
- Remove temporary files

**Checkpoint**: All tests pass, docs updated, warnings appear

**Rollback**: `git reset --hard HEAD~N`

---

## Rollback Procedures

### Immediate Rollback (Within Same Session)
```bash
# If tests fail during a phase
git status  # See what changed
git reset --hard HEAD  # Discard all uncommitted changes

# If already committed but not pushed
git log --oneline -10  # See recent commits
git reset --hard HEAD~N  # N = number of commits to revert

# Re-run tests
python -m pytest
make sample-suite
```

### Rollback After Push (Coordinated)
```bash
# Create revert commits (preserves history)
git log --oneline -10  # Identify commits to revert
git revert COMMIT_HASH  # Revert specific commit
git revert HEAD~3..HEAD  # Revert range of commits

# Push revert
git push origin main

# Verify
python -m pytest
make sample-suite
```

### Emergency Rollback (Production)
```bash
# If deployed to production and issues found
git checkout KNOWN_GOOD_COMMIT  # e.g., commit before migration
git checkout -b hotfix/rollback-migration

# Deploy this branch
# ... deployment steps ...

# Verify
python -m pytest
make sample-suite

# Once stable, merge hotfix
git checkout main
git merge hotfix/rollback-migration
```

---

## Phase Checkpoints

### Checkpoint Criteria (ALL must pass)
1. ✅ All 546+ tests pass (`python -m pytest`)
2. ✅ Mypy: 0 errors (`.venv/bin/python -m mypy src/elspeth`)
3. ✅ Ruff: Clean (`make lint`)
4. ✅ Sample suite runs (`make sample-suite`)
5. ✅ No unexpected warnings or errors in logs
6. ✅ Coverage >= 85%

### Checkpoint Commands
```bash
# Run full checkpoint verification
./scripts/verify_checkpoint.sh

# Manual verification
python -m pytest  # 546+ passing
.venv/bin/python -m mypy src/elspeth  # 0 errors
make lint  # Passing
make sample-suite  # Completes successfully
python -m pytest --cov=elspeth --cov-report=term | grep "TOTAL"  # >= 85%
```

---

## Migration Checklist

### Pre-Migration (MUST COMPLETE FIRST)
- [x] Risk Reduction Activity 1: Silent Default Audit
- [x] Risk Reduction Activity 2: Test Coverage >85%
- [x] Risk Reduction Activity 3: Import Chain Mapping
- [x] Risk Reduction Activity 4: Performance Baseline
- [x] Risk Reduction Activity 5: Configuration Compatibility
- [x] Risk Reduction Activity 6: Rollback Procedures (this document)
- [x] All gates verified passing

### Phase 1: Orchestration (3-4 hours)
- [ ] Create `plugins/orchestrators/` directory structure
- [ ] Define `OrchestratorPlugin` protocol in `interfaces.py`
- [ ] Create `plugins/orchestrators/experiment/runner.py`
- [ ] Move experiment logic from `core/experiments/runner.py`
- [ ] Add orchestrator registry
- [ ] Update imports in suite runner
- [ ] **CHECKPOINT**: Run tests, verify sample suite
- [ ] **COMMIT**: "feat: Extract experiment runner as orchestrator plugin"

### Phase 2: Node Reorganization (3-4 hours)
- [ ] Create `plugins/nodes/sources/` directory
- [ ] Create `plugins/nodes/sinks/` directory
- [ ] Create `plugins/nodes/transforms/llm/` directory
- [ ] Move datasources to `nodes/sources/`
- [ ] Move sinks to `nodes/sinks/`
- [ ] Move LLMs to `nodes/transforms/llm/`
- [ ] Create shims in old locations (8 shim files)
- [ ] Add deprecation warnings to shims
- [ ] Update internal imports to new locations
- [ ] **CHECKPOINT**: Run tests, verify shims work
- [ ] **COMMIT**: "refactor: Reorganize plugins into data flow structure with backward compat shims"

### Phase 3: Security Hardening (2-3 hours)
- [ ] Remove `api_key_env` default in `retrieval/providers.py:161`
- [ ] Remove `api_key_env` default in `plugins/outputs/embeddings_store.py:389`
- [ ] Remove endpoint default in `plugins/outputs/embeddings_store.py:417`
- [ ] Remove API version default in `retrieval/embedding.py:62`
- [ ] Remove table name default in `retrieval/providers.py:155`
- [ ] Remove field name defaults in `retrieval/providers.py:168-170`
- [ ] Make pattern required in `plugins/experiments/validation.py:136`
- [ ] Update all affected tests
- [ ] Uncomment security enforcement test assertions
- [ ] **CHECKPOINT**: Run tests (security tests now pass)
- [ ] **COMMIT**: "security: Remove critical silent defaults, enforce explicit configuration"

### Phase 4: Protocol Consolidation (2-3 hours)
- [ ] Merge datasource/LLM/sink registries → `plugins/nodes/registry.py`
- [ ] Merge experiment plugin registries → `plugins/orchestrators/experiment/plugin_registry.py`
- [ ] Consolidate middleware registry
- [ ] Update factory function locations
- [ ] Update shims to point to new factories
- [ ] **CHECKPOINT**: Run tests, verify import count reduced
- [ ] **COMMIT**: "refactor: Consolidate 18 registries into 7 unified registries"

### Phase 5: Documentation & Cleanup (2-3 hours)
- [ ] Update `docs/architecture/README.md`
- [ ] Update `docs/architecture/plugin-catalogue.md`
- [ ] Update `CLAUDE.md` with new structure
- [ ] Add migration notes to `CHANGELOG.md`
- [ ] Test deprecation warnings appear
- [ ] Remove temporary files
- [ ] **CHECKPOINT**: Final verification
- [ ] **COMMIT**: "docs: Update architecture documentation for data flow model"

### Post-Migration Verification
- [ ] Run full test suite: `python -m pytest` (546+ passing)
- [ ] Run sample suite: `make sample-suite` (completes successfully)
- [ ] Run performance tests: Compare to baseline (~30s)
- [ ] Verify deprecation warnings appear on old imports
- [ ] Generate coverage report: >= 85%
- [ ] Run mypy: 0 errors
- [ ] Run ruff: Clean
- [ ] Manual smoke test: Run 3 different experiment configs
- [ ] **FINAL GATE**: All verification complete

---

## Rollback Triggers

### Automatic Rollback (Tests Fail)
- **Trigger**: Any test fails at checkpoint
- **Action**: `git reset --hard HEAD`, fix issue, retry
- **Threshold**: 0 test failures allowed

### Manual Rollback (Performance Regression)
- **Trigger**: Suite execution > 40s (33% regression from 30s baseline)
- **Action**: Investigate bottleneck, optimize, or rollback
- **Threshold**: +33% performance degradation

### Manual Rollback (Coverage Drop)
- **Trigger**: Coverage < 85%
- **Action**: Add tests or rollback
- **Threshold**: 85% minimum coverage

### Manual Rollback (Breaking Change)
- **Trigger**: External code breaks (user reports, CI failures)
- **Action**: Fix shims or rollback
- **Threshold**: 0 breaking changes without shims

---

## Communication Plan

### Before Migration
- [ ] Announce migration plan to team
- [ ] Schedule migration window (low-traffic period)
- [ ] Notify users of potential deprecation warnings
- [ ] Document rollback contact (who to call if issues)

### During Migration
- [ ] Update status after each phase
- [ ] Report checkpoint results
- [ ] Notify if delays or issues
- [ ] Keep rollback option open

### After Migration
- [ ] Announce completion
- [ ] Share performance results
- [ ] Document any issues encountered
- [ ] Provide migration summary report

---

## Risk Mitigation

### High-Risk Scenarios

#### Scenario 1: Circular Import Breaks System
**Risk**: Moving files creates new circular imports
**Mitigation**:
- Test imports after each file move
- Use `python -c "import elspeth"` quick check
- Rollback immediately if import fails

#### Scenario 2: Shim Doesn't Work
**Risk**: Backward compatibility shim missing or broken
**Mitigation**:
- Test each shim individually
- Verify external code still works
- Fix shim before proceeding

#### Scenario 3: Test Failure in Production
**Risk**: Tests pass locally but fail in CI/production
**Mitigation**:
- Run CI before merging each phase
- Use feature flags (optional) for gradual rollout
- Have rollback commit ready

#### Scenario 4: Performance Degradation
**Risk**: Migration introduces performance regression
**Mitigation**:
- Run performance tests at each checkpoint
- Compare to baseline (30s)
- Profile if slowdown detected
- Rollback if > 33% degradation

---

## Activity 6 Deliverables

### ✅ Phase Checkpoints Defined
- 5 phases with clear checkpoints
- Each phase leaves system working
- Test gates defined for each checkpoint

### ✅ Migration Checklist Created
- Pre-migration: 6 activities (complete)
- Phase 1-5: Detailed task lists
- Post-migration: 9 verification steps
- Communication plan included

### ✅ Rollback Procedures Documented
- Immediate rollback: `git reset --hard HEAD`
- After push: `git revert`
- Emergency: Checkout known-good commit
- All procedures tested

### ✅ Rollback Triggers Defined
- Test failures: Automatic
- Performance: > 33% degradation
- Coverage: < 85%
- Breaking changes: User reports

**GATE PASSED: Activity 6 Complete** ✅

---

## Final Safety Check

Before starting migration, verify:
- [ ] All 6 risk reduction activities complete
- [ ] All gates passing
- [ ] Rollback procedures understood
- [ ] Team notified
- [ ] Backup/snapshot taken (optional)
- [ ] Migration window scheduled
- [ ] This checklist printed/bookmarked

**🚀 READY FOR MIGRATION**
