# ADR-002 Implementation Checklist

**Quick reference checklist - expand details in METHODOLOGY.md**

---

## Pre-Flight Check

- [x] ADR-002 documentation complete and reviewed
- [x] Existing plugin-level security passing (9 tests)
- [x] 8-12 hours available over 1-2 days
- [x] Security reviewer available
- [x] CI/CD infrastructure working
- [x] Branch created: `feature/adr-002-security-enforcement`

---

## Phase 0: Security Properties & Threat Model (2-3 hours)

### Step 1: Define Security Invariants (1 hour)
- [ ] Create `tests/test_adr002_invariants.py`
- [ ] Write `test_INVARIANT_orchestrator_operates_at_minimum_level`
- [ ] Write `test_INVARIANT_high_security_plugins_reject_low_envelope`
- [ ] Write `test_INVARIANT_classification_uplifting_automatic`
- [ ] All invariant tests RED (expected - no implementation yet)
- [ ] Property-based test skeleton with Hypothesis

### Step 2: Threat Model Documentation (30 min)
- [ ] Create `THREAT_MODEL.md`
- [ ] Document T1: Classification breach
- [ ] Document T2: Security downgrade attack
- [ ] Document T3: Runtime bypass
- [ ] Document T4: Classification mislabeling
- [ ] Document out-of-scope threats (certification handles)
- [ ] Map threats to defense layers (start-time, runtime, certification)

### Step 3: Risk Assessment (30 min)
- [ ] Identify implementation risks (false negatives, false positives, performance)
- [ ] Document mitigations
- [ ] Add to THREAT_MODEL.md

### Checkpoint
- [ ] **Commit Phase 0**: `Docs: ADR-002 security invariants and threat model`
- [ ] THREAT_MODEL.md exists
- [ ] tests/test_adr002_invariants.py exists with 3+ failing tests
- [ ] Update PROGRESS.md

---

## Phase 1: Core Security Primitives (1-2 hours)

### Step 1: ClassifiedDataFrame (30 min)
- [ ] Write test: `test_classified_dataframe_immutable_classification` (RED)
- [ ] Implement ClassifiedDataFrame with frozen dataclass (GREEN)
- [ ] Add `with_uplifted_classification()` method
- [ ] Test passes

### Step 2: Minimum Clearance Envelope (30 min)
- [ ] Write test: `test_compute_minimum_clearance_envelope_basic` (RED)
- [ ] Implement `compute_minimum_clearance_envelope()` (GREEN)
- [ ] Test passes

### Step 3: Plugin Validation (30 min)
- [ ] Write test: `test_validate_plugin_accepts_envelope_rejects_too_low` (RED)
- [ ] Add `get_security_level()` to BasePlugin (abstract method)
- [ ] Add `validate_can_operate_at_level()` to BasePlugin (GREEN)
- [ ] Test passes

### Checkpoint
- [ ] **Commit Phase 1**: `Feat: Core ADR-002 security primitives`
- [ ] All Phase 1 tests GREEN
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Update PROGRESS.md

---

## Phase 2: Suite Runner Integration (1-2 hours)

### Step 1: Security Context (30 min)
- [ ] Write test: `test_suite_execution_context_includes_security_envelope` (RED)
- [ ] Add `operating_security_level` to SuiteExecutionContext
- [ ] Update `SuiteExecutionContext.create()` to compute envelope (GREEN)
- [ ] Test passes

### Step 2: Start-Time Validation (30 min)
- [ ] Write test: `test_suite_runner_validates_all_plugins_at_start` (RED)
- [ ] Add `_validate_security_envelope()` to ExperimentSuiteRunner
- [ ] Call validation in `run()` BEFORE data retrieval (GREEN)
- [ ] Test passes

### Step 3: Runtime Failsafe (30 min)
- [ ] Write test: `test_classified_dataframe_rejects_access_above_clearance` (RED)
- [ ] Add `validate_access_by()` to ClassifiedDataFrame (GREEN)
- [ ] Test passes

### Checkpoint
- [ ] **Commit Phase 2**: `Feat: ADR-002 suite-level security enforcement`
- [ ] All Phase 2 tests GREEN
- [ ] Integration with existing suite_runner working
- [ ] All existing tests still pass (39 suite_runner tests + new security tests)
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Update PROGRESS.md

---

## Phase 3: Integration Tests & Certification Evidence (1-2 hours)

### Step 1: End-to-End Security Scenarios (1 hour)
- [ ] Create `tests/test_adr002_integration.py`
- [ ] Write `test_INTEGRATION_secret_datasource_rejects_unofficial_sink`
- [ ] Write `test_INTEGRATION_mixed_security_suite_operates_at_minimum`
- [ ] Write `test_INTEGRATION_classification_uplifting_through_secret_llm`
- [ ] Write 2+ additional integration tests
- [ ] All integration tests GREEN

### Step 2: Property-Based Adversarial Testing (30 min)
- [ ] Create `tests/test_adr002_properties.py`
- [ ] Write `test_PROPERTY_minimum_envelope_never_exceeds_weakest_link`
- [ ] Write `test_PROPERTY_no_configuration_allows_classification_breach`
- [ ] Run with 1000+ Hypothesis examples
- [ ] All property tests GREEN

### Step 3: Certification Evidence Package (30 min)
- [ ] Create `CERTIFICATION_EVIDENCE.md`
- [ ] Map each threat to specific test
- [ ] Document test results (15+ tests passing)
- [ ] Document coverage on security-critical paths

### Checkpoint
- [ ] **Commit Phase 3**: `Test: ADR-002 integration tests and certification evidence`
- [ ] Total tests: 15+ (5 invariants + 5 integration + 5 property-based)
- [ ] All tests GREEN
- [ ] Coverage ≥ 95% on security-critical code
- [ ] Update PROGRESS.md

---

## Phase 4: Documentation & Certification (1 hour)

### Step 1: Update ADR-002 Status (15 min)
- [ ] Update `docs/security/README-ADR002-IMPLEMENTATION.md`
- [ ] Mark suite-level enforcement as ✅ DONE
- [ ] Document test coverage
- [ ] Link to commits

### Step 2: Complete Certification Evidence (30 min)
- [ ] Finalize `CERTIFICATION_EVIDENCE.md`
- [ ] Add threat coverage table
- [ ] Add test results summary
- [ ] Add security reviewer sign-off section

### Step 3: Update Main Documentation (15 min)
- [ ] Update `docs/security/adr-002-orchestrator-security-model.md`
- [ ] Add "Implementation Status: ✅ Complete" header
- [ ] Link to test files as examples
- [ ] Document any deviations from spec

### Checkpoint
- [ ] **Commit Phase 4**: `Docs: ADR-002 implementation complete with certification evidence`
- [ ] All documentation updated
- [ ] Ready for security review
- [ ] Update PROGRESS.md

---

## Quality Gates (Must Pass Before Merge)

### Automated Gates
- [ ] All 15+ security tests passing
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] Coverage ≥ 95% on security-critical paths
- [ ] Property-based tests passed 1000+ examples each
- [ ] No new warnings in CI/CD
- [ ] All existing tests still passing (39 suite_runner + new security)

### Manual Gates
- [ ] Security reviewer approved code
- [ ] Threat model verified complete
- [ ] Documentation reviewed by peer
- [ ] Integration tests cover all threat scenarios
- [ ] Error messages are actionable

### Certification Gates
- [ ] Certification evidence package complete
- [ ] All ADR-002 requirements satisfied
- [ ] Test coverage documented
- [ ] No known security gaps

---

## Final Cleanup

- [ ] Move THREAT_MODEL.md → `docs/security/adr-002-threat-model.md`
- [ ] Move CERTIFICATION_EVIDENCE.md → `docs/security/adr-002-certification-evidence.md`
- [ ] Archive PROGRESS.md → `docs/security/archive/adr-002-implementation-progress.md`
- [ ] Update main README if needed
- [ ] Delete or archive `ADR002_IMPLEMENTATION/` directory

---

**Current Phase**: Phase 0 - Security Properties & Threat Model
**Next Action**: Create tests/test_adr002_invariants.py with failing invariant tests
