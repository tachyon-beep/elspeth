# Fuzzing Implementation Roadmap (Concise)

This document provides a concise, execution‑focused roadmap for fuzzing. It defers strategy/targets/invariants to the canonical guide ([fuzzing.md](./fuzzing.md)) and risk treatment to the design review ([fuzzing_design_review.md](./fuzzing_design_review.md)).

## Scope & Links
- Strategy & targets (canonical): [fuzzing.md](./fuzzing.md)
- Risks, mitigations, acceptance: [fuzzing_design_review.md](./fuzzing_design_review.md)
- CI: nightly fuzz on Python 3.11 (Atheris), PR property tests on 3.12

## Phases & Milestones

### Phase 0 — Discovery & Risk Assessment (1–2 weeks)
- Validate threat surfaces; prioritize high‑risk modules
- Generate coverage heatmap for security‑critical code
- Define input domains + invariants per target
- Record ADR on tooling choices (Hypothesis + Atheris, corpus policy, coverage goal)

Deliverables:
- Updated threat model + prioritized targets
- Invariants spec per module; initial seeds/corpus policy
- ADR summarizing key decisions

### Phase 1 — Implementation & Integration (2–3 weeks)
- Add Hypothesis properties for top targets (path_guard, name/URI sanitize, endpoint validators)
- Implement Atheris harnesses for the highest‑risk targets
- Nightly fuzz workflow (10–15 min per harness; crash artifact policy)
- Turn crashes into regression properties; document triage

Deliverables:
- Property suites merged into tests/fuzz_props/
- Atheris harnesses under fuzz/
- CI workflow .github/workflows/fuzz.yml (nightly + on‑demand)
- Crash triage notes and follow‑up issues (if any)

### Phase 2 — Expansion & Hardening (ongoing)
- Add additional targets based on crash data and code churn
- Track coverage/branch deltas on fuzzed modules
- Periodically prune corpus; keep only minimized interesting seeds

## Success Criteria (references)
- Use the authoritative “Success Criteria (Phase 1)” in [fuzzing.md](./fuzzing.md).

## Ownership & RACI (lightweight)
- Strategy/targets: Security Eng (A), Tech Lead (C)
- Properties/harnesses: Contributors/Owners of modules (R), Security Eng (C)
- CI integration & retention policy: DevOps (R), Security Eng (C)

## Notes
- Nightly fuzz runs on Python 3.11 for Atheris; runtime stays 3.12.
- Resource caps: time‑box jobs, upload minimized crashes only, 7‑day retention.

### Weeks 1-2: Foundation (40-60 hours)

#### Task 1: Atheris Harness Development (15-20 hours)

**Modules to Fuzz** (Priority Order):

1. `path_guard.py` - Path traversal protection
2. `approved_endpoints.py` - URL validation
3. `sanitizers.py` - Input sanitization
4. `prompt_renderer.py` - Template injection
5. `config_parser.py` - YAML/JSON parsing

**Example Harness Structure**:

```python
# fuzz/fuzz_path_guard.py
import atheris
import tempfile
from pathlib import Path
from elspeth.core.utils.path_guard import resolve_under_base

def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    
    # Generate fuzzed inputs
    candidate = fdp.ConsumeUnicodeNoSurrogates(
        fdp.ConsumeIntInRange(0, 1000)
    )
    base = fdp.ConsumeUnicodeNoSurrogates(
        fdp.ConsumeIntInRange(0, 1000)
    )
    
    # Test with oracle assertions
    with tempfile.TemporaryDirectory() as tmpdir:
        # ... implementation ...
        
if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
```

#### Task 2: Hypothesis Test Suite (10-15 hours)

**Property Tests to Write**:

- Path resolution properties
- URL validation properties
- Sanitization effectiveness
- Template safety properties
- Configuration parsing robustness

#### Task 3: Seed Corpus Creation (5-10 hours)

**Corpus Sources**:

- Existing test fixtures
- Known attack patterns (OWASP Top 10)
- Production config samples (anonymized)
- CVE exploit patterns

**Target**: 50+ seeds per fuzzing target

### Weeks 3-4: Integration (15-25 hours)

#### Task 4: CI/CD Pipeline Integration (5-10 hours)

**Implementation Requirements**:

- Fast property tests (<5 min) on every PR
- Deep Atheris fuzzing (15 min) nightly
- Crash artifact collection
- Automated issue creation for findings

#### Task 5: Crash Triage Process (10-15 hours)

**Triage Workflow**:

1. **Reproduce**: `python fuzz/fuzz_path_guard.py crash-abc123.txt`
2. **Minimize**: `atheris --minimize_crash=crash-abc123.txt`
3. **Debug**: Identify root cause and impact
4. **Test**: Write regression test
5. **Fix**: Implement security patch
6. **Document**: Add to corpus and update docs

### Weeks 5-6: Stabilization (20-30 hours)

#### Task 6: Coverage Optimization (5-10 hours)

**Activities**:

- Run coverage analysis
- Identify uncovered branches
- Design targeted seeds
- Optimize harness performance

#### Task 7: Performance Tuning (5-10 hours)

**Optimization Targets**:

- Achieve >10,000 executions/second
- Reduce test flakiness
- Optimize resource usage
- Implement smart mocking

#### Task 8: Documentation & Training (5-10 hours)

**Documentation Deliverables**:

- Fuzzing user guide
- Crash triage playbook
- Coverage reports
- Compliance narrative

---

## Implementation Options

### Option A: Incremental Approach (Recommended)

**Total Investment**: 15-20 hours initially, expand based on results

**Phase 1a**: Hypothesis Only (Week 1-2)

- Implement property-based tests
- Integrate with existing CI
- Evaluate bug discovery rate

**Decision Point**: Assess value and findings

**Phase 1b**: Add Atheris (If justified)

- Implement for highest-risk modules only
- Deploy in dedicated fuzzing infrastructure

### Option B: Full Implementation

**Total Investment**: 60-100 hours

**When Appropriate**:

- ✅ Security compliance mandates
- ✅ Dedicated sprint allocation
- ✅ Senior developer with fuzzing expertise
- ✅ High-risk code justifying investment

---

## Resource Requirements

### Team Skills Needed

| Skill | Level | Hours |
|-------|-------|-------|
| Python Development | Senior | 40-60 |
| Security Testing | Intermediate+ | 20-30 |
| CI/CD Configuration | Intermediate | 5-10 |
| Documentation | Any | 5-10 |

### Infrastructure

- **CI Resources**: Additional 15-30 min/day compute time
- **Storage**: 100MB-1GB for corpus management
- **Monitoring**: Crash tracking and alerting system

---

## Success Criteria

### Phase 0 Success Metrics

- ✅ 3 property tests passing
- ✅ 1+ bug discovered and fixed
- ✅ CI integration functional
- ✅ Documentation complete

### Phase 1 Success Metrics

- ✅ >95% branch coverage on security modules
- ✅ 5+ security issues identified and resolved
- ✅ <5 min PR test runtime maintained
- ✅ Continuous fuzzing operational

---

## Risk Analysis

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| No bugs found | Low | Medium | Inject known bugs to validate |
| Too many false positives | Medium | High | Refine oracle functions |
| Performance degradation | Medium | Medium | Implement smart mocking |
| CI timeout issues | Low | Low | Configure appropriate limits |

### Resource Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Skill gap | Medium | High | Start with Hypothesis, training |
| Time overrun | Medium | Medium | Incremental approach |
| Maintenance burden | Low | Medium | Automate triage process |

---

## Recommendations

### Immediate Actions (Week 1)

1. **Run coverage analysis** on security modules
2. **Select top 3 targets** based on risk assessment
3. **Write first Hypothesis test** as proof of concept
4. **Allocate resources** for Phase 0 (1 developer, 2-3 weeks)

### Go/No-Go Decision Criteria

**Proceed to full implementation if**:

- Hypothesis finds 2+ real bugs in Phase 0
- Security audit requirements mandate fuzzing
- Team has bandwidth for 60-100 hour investment

**Defer/scale back if**:

- No bugs found in initial testing
- Resource constraints exist
- Lower-risk codebase assessment

---

## Appendix A: Tool Selection Rationale

### Hypothesis vs. Atheris

| Aspect | Hypothesis | Atheris |
|--------|------------|---------|
| Setup Complexity | Low | High |
| Bug Finding | Good | Excellent |
| Debugging | Excellent | Moderate |
| CI Integration | Easy | Complex |
| Maintenance | Low | High |
| Coverage-Guided | No | Yes |

**Recommendation**: Start with Hypothesis, add Atheris for critical modules

---

## Appendix B: Example Fuzzing Targets

### Priority 1: Path Traversal (`path_guard.py`)

- **Risk**: High (filesystem access)
- **Complexity**: Medium
- **Test Strategy**: Property + coverage-guided
- **Expected Bugs**: 2-5

### Priority 2: URL Validation (`approved_endpoints.py`)

- **Risk**: High (SSRF potential)
- **Complexity**: High (URL parsing edge cases)
- **Test Strategy**: Property-based
- **Expected Bugs**: 3-7

### Priority 3: Input Sanitization

- **Risk**: Medium (XSS/injection)
- **Complexity**: Medium
- **Test Strategy**: Property-based
- **Expected Bugs**: 1-3

---

## Appendix C: Compliance & Audit Trail

### Documentation for Accreditation

1. Fuzzing strategy and rationale
2. Coverage metrics and trends
3. Bug discovery and remediation log
4. Continuous testing evidence
5. Security posture improvements

### Audit Evidence

- Timestamped fuzzing runs
- Coverage reports
- Issue tracking integration
- Fix verification tests
- Corpus evolution metrics
