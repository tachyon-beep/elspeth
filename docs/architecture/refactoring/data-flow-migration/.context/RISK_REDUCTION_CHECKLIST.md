# Risk Reduction Checklist

**Use this checklist to track progress through risk reduction activities**

---

## Activity 1: Silent Default Audit (2-3 hours) ⚠️ CRITICAL

### Phase 1A: Search for Defaults
- [ ] Run: `rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/ > silent_defaults_audit.txt`
- [ ] Run: `rg "\|\|\s*['\"]" src/elspeth/ >> silent_defaults_audit.txt`
- [ ] Run: `rg "def create_.*\(.*=.*\):" src/elspeth/ >> silent_defaults_audit.txt`
- [ ] Review `silent_defaults_audit.txt` - count findings

### Phase 1B: Categorize by Severity
- [ ] CRITICAL (security_level, authentication, validation):
  - [ ] List found: _______________
  - [ ] Action plan: _______________

- [ ] HIGH (model, endpoint, temperature, timeout):
  - [ ] List found: _______________
  - [ ] Action plan: _______________

- [ ] MEDIUM (retry_count, buffer_size):
  - [ ] List found: _______________
  - [ ] Action plan: _______________

- [ ] LOW (display_name, formatting):
  - [ ] List found: _______________
  - [ ] Action plan: _______________

### Phase 1C: Create Security Enforcement Tests
- [ ] Create `tests/security/test_explicit_configuration.py`
- [ ] Test: datasources require security_level
- [ ] Test: LLM clients require model
- [ ] Test: LLM clients require temperature
- [ ] Test: sinks require security_level
- [ ] Test: all plugins fail without critical fields
- [ ] Run tests: `python -m pytest tests/security/` - all pass

### Phase 1D: Document and Remove
- [ ] Document all CRITICAL defaults found
- [ ] Remove or replace all CRITICAL defaults
- [ ] Document all HIGH defaults found
- [ ] Remove or replace all HIGH defaults
- [ ] Update schemas to mark fields as `required`
- [ ] Verify: Zero P0/P1 silent defaults remain

### Deliverables
- [ ] `silent_defaults_audit.txt` exists and reviewed
- [ ] Categorization complete (CRITICAL/HIGH/MEDIUM/LOW)
- [ ] Security enforcement tests created and passing
- [ ] All CRITICAL/HIGH defaults documented and removed
- [ ] Schemas updated with `required` fields

---

## Activity 2: Test Coverage Audit (2-3 hours) ⚠️ HIGH

### Phase 2A: Generate Coverage Report
- [ ] Run: `python -m pytest --cov=elspeth --cov-report=html --cov-report=term-missing --cov-report=json`
- [ ] Open: `htmlcov/index.html` in browser
- [ ] Note overall coverage: ____%
- [ ] Target: >85% coverage

### Phase 2B: Identify Gaps
- [ ] List files <80% coverage:
  - [ ] File: ______________ Coverage: ____%
  - [ ] File: ______________ Coverage: ____%
  - [ ] File: ______________ Coverage: ____%

- [ ] Identify critical paths with no tests:
  - [ ] Path: _______________
  - [ ] Path: _______________

### Phase 2C: Create Characterization Tests
- [ ] Create `tests/characterization/test_registry_behavior.py`
- [ ] Test: datasource registry lookup behavior
- [ ] Test: LLM registry lookup behavior
- [ ] Test: sink registry lookup behavior
- [ ] Test: plugin creation with context
- [ ] Test: configuration merge behavior
- [ ] Test: security level resolution
- [ ] Test: all 18 registries documented
- [ ] Run tests: all characterization tests pass

### Phase 2D: Create End-to-End Smoke Tests
- [ ] Create `tests/smoke/test_end_to_end.py`
- [ ] Test 1: Load datasource → LLM → sink (basic)
- [ ] Test 2: Configuration merge (defaults → pack → config)
- [ ] Test 3: Security level enforcement
- [ ] Test 4: Artifact pipeline dependency resolution
- [ ] Test 5: Suite runner with multiple experiments
- [ ] Run tests: all smoke tests pass

### Phase 2E: Verify Baseline
- [ ] Run: `python -m pytest` - all 545+ tests pass
- [ ] Run: `python -m pytest -v` - no failures
- [ ] Run: `make sample-suite` - completes successfully
- [ ] Coverage: ____% (target: >85%)

### Deliverables
- [ ] Coverage report generated (HTML + JSON)
- [ ] Coverage >85% OR gaps documented with plan
- [ ] Characterization tests for all 18 registries
- [ ] 5+ end-to-end smoke tests created
- [ ] All 545+ tests passing
- [ ] Sample suite runs successfully

---

## Activity 3: Import Chain Mapping (2-3 hours) ⚠️ HIGH

### Phase 3A: Map Registry Imports
- [ ] Run: `rg "from elspeth\.core\.registry" src/ tests/ > registry_imports.txt`
- [ ] Run: `rg "from elspeth\.core\.datasource_registry" src/ tests/ >> registry_imports.txt`
- [ ] Run: `rg "from elspeth\.core\.llm_registry" src/ tests/ >> registry_imports.txt`
- [ ] Run: `rg "from elspeth\.plugins\.llms" src/ tests/ >> registry_imports.txt`
- [ ] Run: `rg "from elspeth\.plugins\.datasources" src/ tests/ >> registry_imports.txt`
- [ ] Run: `rg "from elspeth\.plugins\.outputs" src/ tests/ >> registry_imports.txt`
- [ ] Run: `rg "from elspeth\.plugins\.experiments" src/ tests/ >> registry_imports.txt`
- [ ] Review `registry_imports.txt` - count import sites

### Phase 3B: Identify External API Surface
- [ ] What do users import? (from docs, examples):
  - [ ] Import: _______________
  - [ ] Import: _______________

- [ ] What do tests import? (from tests/):
  - [ ] Import: _______________
  - [ ] Import: _______________

- [ ] What's in `__all__` exports?:
  - [ ] Module: _______________ Exports: _______________
  - [ ] Module: _______________ Exports: _______________

- [ ] Document external API contract

### Phase 3C: Design Backward Compatibility Shims
- [ ] For each moved module, design shim:
  - [ ] Old: `elspeth.plugins.datasources.*` → New: `elspeth.plugins.nodes.sources.*`
    - [ ] Shim location: _______________
    - [ ] Re-export strategy: _______________

  - [ ] Old: `elspeth.plugins.llms.*` → New: `elspeth.plugins.nodes.transforms.llm.*`
    - [ ] Shim location: _______________
    - [ ] Re-export strategy: _______________

  - [ ] Old: `elspeth.plugins.outputs.*` → New: `elspeth.plugins.nodes.sinks.*`
    - [ ] Shim location: _______________
    - [ ] Re-export strategy: _______________

- [ ] Document shim creation in migration plan

### Deliverables
- [ ] `registry_imports.txt` complete with all import sites
- [ ] External API surface identified and documented
- [ ] Backward compatibility shim design complete
- [ ] Migration plan updated to include shim creation
- [ ] Deprecation timeline planned (optional)

---

## Activity 4: Performance Baseline (1-2 hours) ⚠️ MEDIUM

### Phase 4A: Establish Baseline Metrics
- [ ] Run: `time python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 100`
- [ ] Note execution time: _____ seconds
- [ ] Run: `python -m cProfile -o registry_profile.prof -m elspeth.cli ...`
- [ ] Analyze profile: `python -m pstats registry_profile.prof`

### Phase 4B: Time Critical Paths
- [ ] Registry lookup time:
  - [ ] Measure: _____ ms (target: <1ms)
  - [ ] Method: _______________

- [ ] Plugin creation time:
  - [ ] Measure: _____ ms (target: <10ms)
  - [ ] Method: _______________

- [ ] Configuration merge time:
  - [ ] Measure: _____ ms (target: <50ms)
  - [ ] Method: _______________

- [ ] Artifact pipeline resolution:
  - [ ] Measure: _____ ms (target: <100ms)
  - [ ] Method: _______________

### Phase 4C: Create Regression Tests
- [ ] Create `tests/performance/test_registry_performance.py`
- [ ] Test: Registry lookups <1ms
- [ ] Test: Plugin creation <10ms
- [ ] Test: Config merge <50ms
- [ ] Test: Artifact pipeline <100ms
- [ ] Run tests: all performance tests pass

### Deliverables
- [ ] Performance baseline metrics documented
- [ ] Critical path timings recorded
- [ ] Performance regression tests created
- [ ] Acceptable thresholds defined and documented

---

## Activity 5: Configuration Audit (1-2 hours) ⚠️ MEDIUM

### Phase 5A: Inventory Configs
- [ ] Run: `find . -name "*.yaml" -o -name "*.yml" | grep -v ".venv" > configs_inventory.txt`
- [ ] Run: `rg "plugin:\s*" config/ tests/ >> plugin_references.txt`
- [ ] Count configs found: _____
- [ ] Review `configs_inventory.txt`

### Phase 5B: Test Config Parsing
- [ ] Test: Load `config/sample_suite/settings.yaml` - succeeds
- [ ] Test: Load all prompt pack configs - succeeds
- [ ] Test: Load all experiment configs - succeeds
- [ ] Document current config structure
- [ ] Identify any deprecated patterns

### Phase 5C: Design Compatibility Layer
- [ ] Support old plugin names:
  - [ ] Alias: _______________ → _______________
  - [ ] Alias: _______________ → _______________

- [ ] Support old config keys:
  - [ ] Old key: _______________ → New key: _______________
  - [ ] Old key: _______________ → New key: _______________

- [ ] Add validation warnings for deprecated structure
- [ ] Document config migration path

### Deliverables
- [ ] `configs_inventory.txt` complete
- [ ] All sample configs parse successfully
- [ ] Configuration compatibility layer designed
- [ ] Old config formats will still work post-migration
- [ ] Migration guide for config updates (optional)

---

## Activity 6: Migration Safety (2-3 hours) ⚠️ MEDIUM

### Phase 6A: Define Phase Checkpoints
- [ ] Phase 1 checkpoint:
  - [ ] State: _______________
  - [ ] Tests: _______________
  - [ ] Rollback: _______________

- [ ] Phase 2 checkpoint:
  - [ ] State: _______________
  - [ ] Tests: _______________
  - [ ] Rollback: _______________

- [ ] Phase 3 checkpoint:
  - [ ] State: _______________
  - [ ] Tests: _______________
  - [ ] Rollback: _______________

- [ ] Phase 4 checkpoint:
  - [ ] State: _______________
  - [ ] Tests: _______________
  - [ ] Rollback: _______________

- [ ] Phase 5 checkpoint:
  - [ ] State: _______________
  - [ ] Tests: _______________
  - [ ] Rollback: _______________

### Phase 6B: Create Migration Checklist
- [ ] Detailed task list per phase created
- [ ] Success criteria per phase documented
- [ ] Testing requirements per phase defined
- [ ] Rollback procedure per phase documented

### Phase 6C: Set Up Feature Flags (Optional)
- [ ] Environment variable: `USE_NEW_REGISTRIES`
- [ ] Code: Check flag before using new vs old
- [ ] Test: Flag works correctly
- [ ] Document: How to enable/disable

### Phase 6D: Document Rollback Procedures
- [ ] Rollback if tests fail:
  - [ ] Step 1: _______________
  - [ ] Step 2: _______________

- [ ] Rollback if performance degrades:
  - [ ] Step 1: _______________
  - [ ] Step 2: _______________

- [ ] Rollback if external breakage:
  - [ ] Step 1: _______________
  - [ ] Step 2: _______________

### Deliverables
- [ ] Each phase has clear checkpoint
- [ ] Migration checklist created (detailed)
- [ ] Rollback procedures documented
- [ ] (Optional) Feature flags implemented and tested

---

## GATE: All Must Pass Before Migration

### Critical (MUST PASS)
- [ ] Silent default audit complete
- [ ] Zero P0/P1 silent defaults remain
- [ ] Security enforcement tests created and passing
- [ ] Test coverage >85%
- [ ] All 545+ tests passing
- [ ] Characterization tests for all 18 registries

### High Priority (MUST PASS)
- [ ] 5+ end-to-end smoke tests created and passing
- [ ] Import chain map complete
- [ ] External API surface identified
- [ ] Backward compatibility shims designed

### Medium Priority (SHOULD PASS)
- [ ] Performance baseline established
- [ ] Performance regression tests created
- [ ] Configuration compatibility layer designed
- [ ] Migration checklist created
- [ ] Rollback procedures documented

### Optional (NICE TO HAVE)
- [ ] Feature flags implemented
- [ ] Config migration guide created
- [ ] Deprecation timeline defined

---

## Gate Review Meeting

**Date**: _______________
**Attendees**: _______________

### Gate Results
- [ ] All CRITICAL gates passed
- [ ] All HIGH gates passed
- [ ] All MEDIUM gates passed
- [ ] Decision: PROCEED / BLOCKED / NEEDS REVIEW

### Issues Found
- Issue 1: _______________
- Issue 2: _______________

### Action Items
- Action 1: _______________
- Action 2: _______________

### Approval
- [ ] Technical lead approval
- [ ] Security review approval
- [ ] Architecture review approval
- [ ] Ready to proceed to migration

---

## Notes & Observations

Use this space to track findings, issues, or insights during risk reduction:

_______________________________________________________________________________

_______________________________________________________________________________

_______________________________________________________________________________

_______________________________________________________________________________
