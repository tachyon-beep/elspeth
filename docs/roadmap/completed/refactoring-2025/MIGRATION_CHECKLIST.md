# Registry Consolidation Migration Checklist

**Quick Reference for Implementation Teams**

---

## Pre-Flight Checklist

### Environment Setup
- [ ] Create feature branch: `git checkout -b refactor/registry-consolidation`
- [ ] Backup current codebase
- [ ] Run baseline tests: `python -m pytest`
- [ ] Record baseline metrics (test count, coverage %, execution time)
- [ ] Set up test watcher: `python -m pytest -m "not slow" --looponfail`

### Team Communication
- [ ] Notify team of refactoring start
- [ ] Block concurrent changes to registry files
- [ ] Schedule daily standup for status updates

---

## Phase 1: Foundation (Days 1-5)

### Day 1: Module Structure
- [ ] Create `src/elspeth/core/registry/` directory
- [ ] Create `__init__.py` (empty, add exports later)
- [ ] Create `base.py` (empty, add code incrementally)
- [ ] Create `context_utils.py` (empty)
- [ ] Create `schemas.py` (empty)
- [ ] Create `validation.py` (if needed)
- [ ] Git commit: `"chore: create registry module structure"`

### Day 2: Base Factory
- [ ] Implement `BasePluginFactory` class in `base.py`
- [ ] Add docstrings and type hints
- [ ] Create `tests/test_registry_base.py`
- [ ] Write tests for `BasePluginFactory.validate()`
- [ ] Write tests for `BasePluginFactory.instantiate()`
- [ ] Run tests: `python -m pytest tests/test_registry_base.py -v`
- [ ] Coverage check: `python -m pytest tests/test_registry_base.py --cov=elspeth.core.registry.base`
- [ ] Git commit: `"feat: implement BasePluginFactory"`

### Day 3: Context Utilities
- [ ] Implement `extract_security_levels()` in `context_utils.py`
- [ ] Implement `create_plugin_context()`
- [ ] Implement `prepare_plugin_payload()`
- [ ] Create `tests/test_registry_context_utils.py`
- [ ] Write 8+ test cases covering all branches
- [ ] Run tests: `python -m pytest tests/test_registry_context_utils.py -v`
- [ ] Coverage check: Should be >95%
- [ ] Git commit: `"feat: implement context utility functions"`

### Day 4: Schemas & Base Registry
- [ ] Implement common schemas in `schemas.py`
- [ ] Implement schema builder functions
- [ ] Create `tests/test_registry_schemas.py`
- [ ] Implement `BasePluginRegistry` in `base.py`
- [ ] Add tests for `BasePluginRegistry`
- [ ] Run full test suite: `python -m pytest tests/test_registry_*.py`
- [ ] Git commit: `"feat: implement schemas and BasePluginRegistry"`

### Day 5: Public API & Integration Tests
- [ ] Complete `__init__.py` with all exports
- [ ] Write integration test in `tests/test_registry_integration.py`
- [ ] Test creating a mock plugin end-to-end
- [ ] Run ALL existing tests: `python -m pytest`
- [ ] Verify no regressions
- [ ] Update `CHANGELOG.md`: Add "Internal: Base registry framework"
- [ ] Git commit: `"feat: complete base registry framework"`
- [ ] Create PR for Phase 1 review
- [ ] **GATE: Get approval before Phase 2**

**Phase 1 Success Criteria:**
- [ ] All new tests pass (>90% coverage)
- [ ] All existing tests still pass (100%)
- [ ] No performance regression
- [ ] 2+ code reviews completed
- [ ] Documentation updated

---

## Phase 2: Migration (Days 6-15)

### Day 6: Utilities Registry
- [ ] Create backup: `cp src/elspeth/core/utilities/plugin_registry.py{,.bak}`
- [ ] Import `BasePluginRegistry` at top of file
- [ ] Replace `_PluginFactory` with `BasePluginRegistry[Any]("utility")`
- [ ] Update `register_utility_plugin()`
- [ ] Update `create_utility_plugin()`
- [ ] Keep `create_named_utility()` unchanged
- [ ] Run tests: `python -m pytest tests/ -k utility`
- [ ] Check imports: `python -c "from elspeth.core.utilities.plugin_registry import *"`
- [ ] Git commit: `"refactor: migrate utilities registry to base framework"`

### Day 7: Controls Registry
- [ ] Create backup: `cp src/elspeth/core/controls/registry.py{,.bak}`
- [ ] Create `_rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")`
- [ ] Create `_cost_tracker_registry = BasePluginRegistry[CostTracker]("cost_tracker")`
- [ ] Migrate `create_rate_limiter()` - reduce from ~50 to ~15 lines
- [ ] Migrate `create_cost_tracker()` - reduce from ~50 to ~15 lines
- [ ] Keep `register_*` functions for backward compat
- [ ] Run tests: `python -m pytest tests/ -k "rate_limit or cost_track"`
- [ ] Git commit: `"refactor: migrate controls registry"`

### Day 8: LLM Middleware Registry
- [ ] Create backup: `cp src/elspeth/core/llm/registry.py{,.bak}`
- [ ] Replace `_Factory` with `BasePluginRegistry`
- [ ] Update `create_middleware()`
- [ ] Keep `create_middlewares()` list helper
- [ ] Run tests: `python -m pytest tests/test_llm_middleware.py`
- [ ] Run integration test: `python -m pytest tests/test_suite_runner_integration.py -k middleware`
- [ ] Git commit: `"refactor: migrate LLM middleware registry"`

### Day 9-10: Experiment Plugins Registry (Complex)
- [ ] Create backup: `cp src/elspeth/core/experiments/plugin_registry.py{,.bak}`
- [ ] Create 5 registry instances (row, agg, baseline, validation, early-stop)
- [ ] Migrate `create_row_plugin()` (~80 lines → ~15 lines)
- [ ] Migrate `create_aggregation_plugin()`
- [ ] Migrate `create_baseline_plugin()`
- [ ] Migrate `create_validation_plugin()`
- [ ] Migrate `create_early_stop_plugin()`
- [ ] Keep `normalize_early_stop_definitions()` unchanged
- [ ] Update validation functions to use registries
- [ ] Run experiments tests: `python -m pytest tests/ -k experiment`
- [ ] Git commit: `"refactor: migrate experiment plugins registry"`

### Day 11-13: Main Registry (Most Critical)
- [ ] Create backup: `cp src/elspeth/core/registry.py{,.bak}`
- [ ] Refactor `PluginRegistry.__init__()` to use 3 BasePluginRegistry instances
- [ ] Create `_register_datasources()` method
- [ ] Create `_register_llms()` method
- [ ] Create `_register_sinks()` method
- [ ] Update `create_datasource()` to delegate
- [ ] Update `create_llm()` to delegate
- [ ] Update `create_sink()` to delegate
- [ ] Keep `create_llm_from_definition()` special logic
- [ ] Move schemas to `schemas.py`
- [ ] Run datasource tests: `python -m pytest tests/ -k datasource`
- [ ] Run LLM tests: `python -m pytest tests/ -k llm`
- [ ] Run sink tests: `python -m pytest tests/ -k sink`
- [ ] Git commit: `"refactor: migrate main plugin registry"`

### Day 14: Integration Testing
- [ ] Run full test suite: `python -m pytest`
- [ ] Run sample suite: `make sample-suite`
- [ ] Check all outputs generated correctly
- [ ] Test artifact pipeline: Verify sink dependencies work
- [ ] Test security propagation: Check context flows correctly
- [ ] Performance benchmark: Compare to baseline
- [ ] Git commit: `"test: verify registry consolidation integration"`

### Day 15: Phase 2 Review
- [ ] Create comprehensive PR for Phase 2
- [ ] Include before/after metrics (LOC, test coverage)
- [ ] Document any behavior changes (should be none)
- [ ] Request 2+ code reviews
- [ ] **GATE: Get approval before Phase 3**

**Phase 2 Success Criteria:**
- [ ] All 5 registries migrated
- [ ] 100% existing tests pass
- [ ] No behavior changes
- [ ] Performance within ±5% of baseline
- [ ] Code reviews approved

---

## Phase 3: Cleanup (Days 16-20)

### Day 16: Remove Duplicate Code
- [ ] Search for old `_Factory` classes: `grep -r "class _Factory" src/`
- [ ] Delete `_Factory` from `controls/registry.py`
- [ ] Delete `_Factory` from `llm/registry.py`
- [ ] Delete `_PluginFactory` from `experiments/plugin_registry.py`
- [ ] Delete `_PluginFactory` from `utilities/plugin_registry.py`
- [ ] Delete duplicate context extraction blocks
- [ ] Run tests: `python -m pytest`
- [ ] Git commit: `"chore: remove duplicate factory classes"`

### Day 17: Rename Datasource Folders
- [ ] Create `src/elspeth/adapters/` directory
- [ ] Move `datasources/blob_store.py` → `adapters/blob_storage.py`
- [ ] Update imports in `plugins/datasources/blob.py`
- [ ] Update imports in `plugins/datasources/csv_blob.py`
- [ ] Update `adapters/__init__.py`
- [ ] Search for remaining imports: `grep -r "from elspeth.datasources" src/`
- [ ] Update all import statements
- [ ] Run tests: `python -m pytest`
- [ ] Delete old `datasources/` folder
- [ ] Git commit: `"refactor: rename datasources to adapters for clarity"`

### Day 18: Update Documentation
- [ ] Update `CLAUDE.md` - registry architecture section
- [ ] Update `docs/architecture/plugin-catalogue.md` - plugin registration examples
- [ ] Create `docs/architecture/registry-architecture.md` - new doc
- [ ] Update `docs/developer-guide/creating-plugins.md` - if exists
- [ ] Update `CONTRIBUTING.md` - plugin development section
- [ ] Update `README.md` - if architecture mentioned
- [ ] Git commit: `"docs: update for new registry architecture"`

### Day 19: Performance Validation
- [ ] Create `tests/benchmark_registry.py`
- [ ] Benchmark datasource creation (1000x)
- [ ] Benchmark LLM creation (1000x)
- [ ] Benchmark sink creation (1000x)
- [ ] Compare to baseline (should be ±5%)
- [ ] Profile context creation overhead
- [ ] Document results in `docs/refactoring/PERFORMANCE_RESULTS.md`
- [ ] Git commit: `"test: validate registry performance"`

### Day 20: Final Cleanup
- [ ] Update `CHANGELOG.md` with summary
- [ ] Remove all `.bak` backup files
- [ ] Run linter: `make lint`
- [ ] Run type checker: `mypy src/elspeth`
- [ ] Generate coverage report: `python -m pytest --cov=elspeth --cov-report=html`
- [ ] Review coverage report for gaps
- [ ] Create final PR for Phase 3
- [ ] **GATE: Get approval before Phase 4**

**Phase 3 Success Criteria:**
- [ ] ~900 lines of code removed
- [ ] Folder structure clearer
- [ ] Documentation updated
- [ ] Performance validated
- [ ] No regressions

---

## Phase 4: Validation & Release (Days 21+)

### Pre-Release Testing
- [ ] Run full test suite: `python -m pytest`
- [ ] Run integration tests: `python -m pytest tests/test_*_integration.py`
- [ ] Run sample suite: `make sample-suite`
- [ ] Test all sink types
- [ ] Test all datasource types
- [ ] Test all LLM client types
- [ ] Test middleware chains
- [ ] Test experiment plugins
- [ ] Test artifact pipeline
- [ ] Test security propagation
- [ ] Test error handling

### Backward Compatibility Testing
- [ ] Test existing config files
- [ ] Test all prompt packs
- [ ] Test custom plugin registration
- [ ] Verify API unchanged
- [ ] Check for breaking changes

### Security Review
- [ ] Review context propagation
- [ ] Verify security levels enforced
- [ ] Check provenance tracking
- [ ] Test privilege escalation scenarios
- [ ] Validate artifact pipeline security

### Release Preparation
- [ ] Update version number in `pyproject.toml`
- [ ] Finalize `CHANGELOG.md`
- [ ] Create migration guide: `docs/refactoring/MIGRATION_GUIDE.md`
- [ ] Tag release: `git tag -a v0.2.0 -m "Registry consolidation refactor"`
- [ ] Merge to main
- [ ] Deploy to staging (if applicable)

### Post-Release
- [ ] Monitor for issues
- [ ] Update project board
- [ ] Celebrate success! 🎉
- [ ] Schedule retrospective

**Phase 4 Success Criteria:**
- [ ] All tests pass
- [ ] Security review approved
- [ ] Documentation complete
- [ ] Release tagged and merged
- [ ] No critical issues

---

## Emergency Rollback Procedures

### If Phase 1 Issues
```bash
# Delete new module
rm -rf src/elspeth/core/registry/
git checkout src/elspeth/core/registry/
git commit -m "rollback: remove registry base framework"
```

### If Phase 2 Issues (per registry)
```bash
# Example: rollback main registry
git checkout src/elspeth/core/registry.py
# Restore from backup if needed
cp src/elspeth/core/registry.py.bak src/elspeth/core/registry.py
git commit -m "rollback: revert main registry migration"
```

### Complete Rollback
```bash
# Find start commit of refactor
git log --oneline | grep "registry-consolidation"

# Revert all commits
git revert <start-commit>..<end-commit>

# Or reset if not pushed
git reset --hard <commit-before-refactor>
```

---

## Daily Standup Template

**Date:** _______
**Day:** ___/20
**Phase:** _______

**Yesterday:**
- Completed: _______________________
- Challenges: _____________________

**Today:**
- Plan: ___________________________
- Estimated time: _________________

**Blockers:**
- _________________________________

**Metrics:**
- Tests passing: ___/%
- Coverage: ___%
- Code removed: ___ lines

---

## Metrics Tracking

### Baseline (Pre-Refactor)
- Total LOC in registries: 2,087
- Test count: _______
- Test coverage: ______%
- Sample suite execution time: _______s
- Registry instantiation time: _______ms

### Target (Post-Refactor)
- Total LOC in registries: ~1,200 (-900)
- Test count: _______ (same or more)
- Test coverage: ______% (>85%)
- Sample suite execution time: _______s (±5%)
- Registry instantiation time: _______ms (±5%)

### Actual (Fill in during migration)
- Phase 1 complete: _______
- Phase 2 complete: _______
- Phase 3 complete: _______
- Phase 4 complete: _______
- Final LOC: _______
- Final coverage: _______%

---

## Quick Command Reference

```bash
# Run fast tests
python -m pytest -m "not slow"

# Run specific registry tests
python -m pytest tests/ -k registry

# Run with coverage
python -m pytest --cov=elspeth.core.registry --cov-report=term-missing

# Watch mode for TDD
python -m pytest -m "not slow" --looponfail

# Full test suite
python -m pytest

# Lint check
make lint

# Type check
mypy src/elspeth

# Run sample suite
make sample-suite

# Find duplicate code
grep -r "class _Factory" src/
grep -r "def extract_security_levels" src/

# Check imports
python -c "from elspeth.core.registry import *; print('OK')"
```

---

## Success Indicators ✅

You'll know you're on track when:

1. **Phase 1:** New tests pass, old tests unchanged
2. **Phase 2:** Each registry migration takes <1 day
3. **Phase 3:** Folder structure makes immediate sense
4. **Phase 4:** Sample suite runs without modification

---

## Warning Signs ⚠️

Stop and reassess if:

1. Tests start failing unexpectedly (>5% failure rate)
2. Migration taking >2x estimated time
3. Performance degradation >10%
4. Breaking changes required in configs
5. Security context not propagating correctly

---

**Last Updated:** 2025-10-14
**Document Owner:** Development Team
**Review Frequency:** Daily during migration
