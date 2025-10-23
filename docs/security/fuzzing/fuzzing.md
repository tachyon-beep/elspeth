# Elspeth Fuzzing Strategy (Canonical)

Fuzzing docs index: [Strategy](./fuzzing.md) • [Roadmap](./fuzzing_plan.md) • [Risk review](./fuzzing_design_review.md)

This is the canonical strategy for fuzzing in Elspeth. It defines targets, invariants, tools, and CI integration.

Notes and pointers:
- Nightly fuzzing runs under Python 3.11 (Atheris compatibility). Runtime and the rest of CI remain on Python 3.12.
- Concise implementation roadmap: [fuzzing_plan.md](./fuzzing_plan.md)
- Risk review and mitigations: [fuzzing_design_review.md](./fuzzing_design_review.md)

## Security Testing Enhancement Through Property-Based and Coverage-Guided Fuzzing

---

## Executive Summary

This document outlines a comprehensive plan to implement fuzzing for the Elspeth project's security-critical components. The plan is divided into two major phases:

- **Phase 0**: Discovery & Risk Assessment (3 weeks, 45-65 hours)
- **Phase 1**: Implementation & Integration (6 weeks, 60-100 hours)

The recommended approach is incremental, starting with Hypothesis property-based testing (15-20 hours) to demonstrate value before committing to full Atheris coverage-guided fuzzing.

---

## Project Context

### Current State

- **Test Suite**: 979+ existing tests
- **Critical Security Modules**:
  - Path traversal protection (`path_guard.py`)
  - Endpoint validation (`approved_endpoints.py`)
  - Input sanitization (CSV/Excel sanitizers)
  - Prompt rendering and template validation
  - Azure integration and pgvector queries

### Goals

1. Identify and fix security vulnerabilities before production
2. Achieve >95% branch coverage on security-critical modules
3. Establish continuous fuzzing in CI/CD pipeline
4. Support security compliance and accreditation requirements

---

## Phase 0: Discovery & Risk Assessment

### Timeline: 3 Weeks (45-65 hours)

### Week 1: Analysis & Design (20-30 hours)

#### 1.1 Threat Model Validation (4 hours)

**Objective**: Validate and prioritize threat surfaces

**Activities**:

- Review `docs/architecture/threat-surfaces.md` for completeness
- Analyze recent CVEs for similar tools (LangChain, LlamaIndex, Haystack)
- Conduct threat surface prioritization workshop
- Calculate risk scores (likelihood × impact)

**Deliverable**: Updated threat model with risk-ranked fuzzing targets

#### 1.2 Coverage Analysis (4 hours)

**Objective**: Identify security-critical code with poor test coverage

**Activities**:

```bash
pytest --cov-report=html --cov=elspeth
```

- Analyze coverage in security modules
- Identify untested branches in:
  - `path_guard.py`
  - `approved_endpoints.py`
  - Sanitizer modules
- Assess cyclomatic complexity vs. coverage

**Deliverable**: Coverage heatmap highlighting high-complexity, low-coverage modules

#### 1.3 Input Domain Specification (8 hours)

**Objective**: Define valid inputs and invariants for each fuzzing target

**Specifications to Document**:

- **Path Guard**:
  - Valid formats: relative, absolute, UNC, symlinks
  - Invariants: paths must remain within `base_dir`
  - Oracle functions: symlink escape detection
  
- **Approved Endpoints**:
  - URL schemes and patterns
  - Edge cases: IPv6, IDN, encoded characters
  
- **Template Rendering**:
  - Allowed syntax elements
  - Rejection criteria for dangerous constructs
  
- **Sanitizers**:
  - Dangerous CSV/Excel constructs (formulas, macros, hyperlinks)

**Deliverable**: Input domain specification document with invariants and oracles

#### 1.4 Fuzzing Strategy Design (4 hours)

**Objective**: Make architectural decisions for fuzzing implementation

**Key Decisions**:

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Testing Framework | Hypothesis-only vs. Dual (Hypothesis + Atheris) | Start Hypothesis, add Atheris for high-risk |
| Corpus Management | Generate vs. Extract vs. Curate | Hybrid: extract from tests + curate attacks |
| Oracle Strategy | Differential vs. Crash vs. Assertion | Assertion-based with invariant checking |
| Coverage Metrics | Line vs. Branch vs. Path | Branch coverage primary, path secondary |
| CI Integration | Every PR vs. Nightly vs. On-demand | Fast tests on PR, deep fuzzing nightly |

**Deliverable**: Architecture Decision Record (ADR) with rationale

#### 1.5 Performance Baseline (6 hours)

**Objective**: Establish performance constraints and mocking strategy

**Activities**:

- Benchmark critical paths (operations/second)
- Identify slow dependencies:
  - Azure Blob operations
  - pgvector queries
  - LLM client calls
- Design mocking strategy preserving security invariants
- Estimate coverage velocity

**Deliverable**: Performance baseline and mocking strategy document

### Week 2: Prototyping & Validation (15-20 hours)

#### 2.1 Proof of Concept (6 hours)

**Objective**: Validate fuzzing approach with concrete implementation

**Implementation**:

```python
# tests/fuzz_props/test_path_guard_props.py
from hypothesis import given, strategies as st
from elspeth.core.utils.path_guard import resolve_under_base

@given(
    candidate=st.text(min_size=1, max_size=1000),
    base=st.text(min_size=1, max_size=100)
)
def test_resolve_under_base_never_escapes(candidate, base):
    """Property: resolved path must always be under base directory."""
    # Implementation...
```

**Deliverable**: Working Hypothesis property test for `path_guard.py`

#### 2.2 Bug Injection Testing (2 hours)

**Objective**: Verify fuzzing can detect known vulnerabilities

**Activities**:

- Inject known path traversal bug
- Verify property test detects the vulnerability
- Document detection capabilities

**Deliverable**: Validation report confirming fuzzing effectiveness

#### 2.3 Atheris Prototype (6 hours)

**Objective**: Evaluate coverage-guided fuzzing feasibility

**Implementation**: Basic Atheris harness for highest-risk module

**Deliverable**: Atheris harness prototype with performance metrics

#### 2.4 CI Integration Prototype (4 hours)

**Objective**: Test fuzzing in CI/CD pipeline

**Implementation**:

```yaml
# .github/workflows/fuzz.yml
name: Fuzzing Tests
on: [push, pull_request]
jobs:
  hypothesis-tests:
    timeout-minutes: 5
    # Configuration...
```

**Deliverable**: Working CI workflow for property tests

### Week 3: Risk Reduction & Planning (10-15 hours)

#### 3.1 Risk Mitigation Planning (6 hours)

**Objective**: Prepare for fuzzing challenges

**Plans to Develop**:

- Crash triage procedure
- Severity ranking criteria (DoS vs. ACE vs. info leak)
- Reproducibility testing process
- False positive handling

**Deliverable**: Risk mitigation checklist with contingency plans

#### 3.2 Integration Planning (4 hours)

**Objective**: Ensure smooth integration with existing tools

**Activities**:

- Review reusable fixtures from `tests/conftest.py`
- Verify CI timeout compatibility
- Research SARIF reporting for security findings
- Plan corpus storage strategy

**Deliverable**: Integration design document

#### 3.3 Success Metrics Definition (3 hours)

**Objective**: Define measurable success criteria

**Metrics**:

- Bug discovery rate
- Coverage improvement (target: >95% branch coverage)
- Performance impact (<5 min for PR tests)
- Compliance documentation completeness

**Deliverable**: Success metrics dashboard template

---

## Phase 1: Implementation & Integration

### Timeline: 6 Weeks (60-100 hours)

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

---

## Conclusion

Fuzzing represents a significant but valuable investment in Elspeth's security posture. The incremental approach allows for risk mitigation while demonstrating value early. Starting with Hypothesis property-based testing (15-20 hours) provides immediate security benefits with manageable complexity, while preserving the option to expand to full coverage-guided fuzzing if warranted by initial results.

The key to success is treating fuzzing not as a one-time activity but as an ongoing security practice integrated into the development lifecycle.
