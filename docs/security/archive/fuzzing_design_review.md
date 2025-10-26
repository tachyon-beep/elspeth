# Fuzzing Plan – Internal Risk Review

Reviewer: Internal self‑review of the canonical strategy in `docs/security/fuzzing/fuzzing.md`.

**Related docs**:
- **Canonical strategy**: [fuzzing.md](./fuzzing.md) - Complete strategy with oracles, implementation details
- **Concise roadmap**: [fuzzing_plan.md](./fuzzing_plan.md) - Quick reference implementation timeline
- **External review**: [fuzzing_design_review_external.md](./fuzzing_design_review_external.md) - External validation and additional recommendations

**Note**: This internal review has been updated to align with external review recommendations. See fuzzing.md "Recommendations" section for integration details.

## Summary

We will use Hypothesis property-based testing on Python 3.12 for security-critical modules (path guards, URL validators, sanitizers). Key innovations from external review: explicit oracle specifications (invariants table), bug injection smoke tests, and severity taxonomy with SLAs. CI adds fast PR tests (5 min) and nightly deep exploration (15 min). This balances bug-finding effectiveness with operational simplicity for Python security testing.

## Strengths

- **Explicit oracles**: Complete invariants table for each target (fuzzing.md Section 1.3) - CRITICAL addition from external review
- **Validation built-in**: Bug injection smoke tests prove property tests catch vulnerabilities (fuzzing.md Section 2.2)
- **Clear triage**: Severity taxonomy (S0-S4) with SLAs for crash response (fuzzing.md Section 3.1)
- **Targets the riskiest surfaces**: Path normalization, URL validation, sanitization, template rendering
- **Resource-bounded**: CI guardrails with hard timeouts (5 min PR, 15 min nightly), crash artifact limits
- **Reproducible**: Hypothesis seeds enable deterministic crash reproduction
- **Low operational overhead**: No dedicated fuzzing infrastructure, runs in standard pytest/CI

## Gaps / Risks & Mitigations

### Risks from External Review Analysis

1) **Weak oracles (false negatives)**
   - Risk: Property tests pass but don't catch real bugs (fuzzing without assertions).
   - Mitigation: Bug injection smoke tests (fuzzing.md Section 2.2) - MUST fail when bugs injected; validates oracle effectiveness.
   - Evidence: 100% bug detection rate required in Phase 0 before proceeding.

2) **Strict oracles (false positives)**
   - Risk: Property tests too strict, fail on valid inputs, create alert fatigue.
   - Mitigation: Start with permissive oracles, tighten based on data; track false positive rate <10% (Success Criteria); iterate oracle specifications.
   - Monitoring: False positive rate in crash triage metrics.

3) **Resource runaway (disk, time, memory)**
   - Risk: Excessive file creation/large inputs slow jobs or fill disk.
   - Mitigation: Hard timeout limits (5 min PR, 15 min nightly); per-test `deadline=500ms`; `TemporaryDirectory()` cleanup; artifact retention 7 days only.
   - Guardrails: CI workflow timeout-minutes, pytest --maxfail=3, Hypothesis derandomize in CI.

4) **Flaky triage due to non-determinism**
   - Risk: Non-deterministic failures hinder root-cause analysis.
   - Mitigation: Hypothesis automatic shrinking provides minimal example; record seed in GitHub issue template; `derandomize=true` in CI profile; turn crashes into regression tests in `seeds.py`.
   - Reproducibility: `HYPOTHESIS_SEED=<seed>` for deterministic replay.

5) **Test cross-talk via filesystem state**
   - Risk: Property tests interfere with each other's temp directories.
   - Mitigation: Use `tmp_path` pytest fixture (automatic cleanup); `TemporaryDirectory()` context managers; randomize dir names; avoid shared global state.
   - Testing: Parallel pytest execution should pass without conflicts.

6) **Coverage blind spots**
   - Risk: Only 5 modules fuzzed; bugs persist in untested code.
   - Mitigation: Expand targets iteratively based on crash data and code churn; quarterly review of security module coverage; target 85% branch coverage (not 95%) on security-critical paths.
   - Monitoring: Coverage reports from pytest --cov, untested critical branches <20.

7) **False sense of security**
   - Risk: Team assumes fuzzing catches all bugs, reduces other security practices.
   - Mitigation: Document fuzzing limitations (complements, doesn't replace manual review); property tests enforce known invariants, not discover new attack vectors; maintain threat modeling and security reviews.

8) **Maintenance burden / technical debt**
   - Risk: Property tests become stale, break on refactoring, ignored by team.
   - Mitigation: Keep tests close to code (tests/fuzz_props/); fast PR feedback (<5 min); clear documentation (crash triage playbook); training materials for team.
   - Sustainability: Track maintenance time <4h/month in Phase 2.

### Risks Addressed by External Review Recommendations

✅ **Oracle specifications** (Risk 1) - Explicit invariants table prevents weak oracles
✅ **Bug injection validation** (Risk 1) - Proves tests actually catch vulnerabilities
✅ **Severity taxonomy** (Risk 4) - Clear S0-S4 SLAs prevent triage chaos
✅ **CI guardrails** (Risk 3) - Hard limits prevent resource exhaustion
✅ **Hypothesis-appropriate metrics** (Risk 6) - Realistic 85% coverage target, not aspirational 95%

### Deferred Risks (Out of Scope)

❌ **Secret exposure in artifacts** - Handle with pre-commit hooks and log sanitization (not fuzzing layer)
❌ **Network operation false positives** - Validators only, no network clients in current scope
❌ **Python version drift** - Using Python 3.12 only (no version juggling with Atheris)

## Action Items (Integrated with External Review)

See [fuzzing_plan.md](./fuzzing_plan.md) for complete week-by-week checklist. Critical items:

### Phase 0 (Week 1)
- [ ] **Define oracle specifications** - Complete invariants table (fuzzing.md Section 1.3) ⭐ CRITICAL
- [ ] **Add Hypothesis profiles** - Configure `pyproject.toml` with ci/explore profiles
- [ ] **Implement bug injection tests** - 2-3 smoke tests in `tests/fuzz_smoke/` ⭐ CRITICAL
- [ ] **Write initial property tests** - 3-5 properties for `path_guard.py`
- [ ] **Add CI workflows** - `.github/workflows/fuzz.yml` (fast PR) and `fuzz-nightly.yml`

### Phase 1 (Weeks 2-3)
- [ ] **Expand property suites** - 15-20 properties under `tests/fuzz_props/` across 5 modules
- [ ] **Add regression seeds** - `tests/fuzz_props/seeds.py` with documented attack patterns
- [ ] **Document severity taxonomy** - S0-S4 with SLAs (fuzzing.md Section 3.1)
- [ ] **Create GitHub issue template** - `.github/ISSUE_TEMPLATE/fuzz-crash.md`
- [ ] **Verify CI guardrails** - Confirm 5 min PR limit, crash artifact upload working

### Phase 2 (Week 4)
- [ ] **Coverage analysis** - Identify untested branches, target 85% on security modules
- [ ] **Performance optimization** - Slow properties, mocking improvements
- [ ] **IRAP documentation** - Evidence package for compliance
- [ ] **Training materials** - Crash triage playbook for team

## Acceptance Criteria

See complete "Success Criteria" in [fuzzing.md](./fuzzing.md). Key criteria:

**Phase 0** (Must pass to proceed):
- ✅ Bug injection tests catch 100% of injected vulnerabilities
- ✅ Oracle table complete with invariants for all 5 target modules
- ✅ 1+ real security bug found and fixed
- ✅ CI integration functional with <5 min runtime

**Phase 1** (Production readiness):
- ✅ 15+ property tests across 5 security modules
- ✅ False positive rate <10%
- ✅ Branch coverage ≥85% on security modules
- ✅ Severity taxonomy documented with SLAs
- ✅ Crash triage procedures operational

**Phase 2** (Long-term sustainability):
- ✅ Maintenance time <4h/month
- ✅ Team trained on crash triage and property writing
- ✅ IRAP evidence package complete
