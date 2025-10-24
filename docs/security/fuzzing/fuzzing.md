# Elspeth Fuzzing Strategy (Canonical)

**Phase 1 (Active)**: [Strategy](./fuzzing.md) • [Roadmap](./fuzzing_plan.md) • [Risk Review](../archive/fuzzing_design_review.md) • [IRAP Risk Acceptance](./fuzzing_irap_risk_acceptance.md)

**Phase 2 (Archived - Blocked)**: [Why Archived?](../archive/phase2_blocked_atheris/README.md) • Awaiting Atheris Python 3.12 support (Q2 2025+)

---

## Phase 1: Property-Based Fuzzing (This Document)

This is the canonical strategy for **Phase 1** fuzzing in Elspeth using Hypothesis property-based testing on Python 3.12.

**Phase 2 note**: For mission-critical systems with classified/PII data, coverage-guided fuzzing (Atheris) provides additional security depth by discovering unknown edge cases. See [Phase 2 documentation](../archive/phase2_blocked_atheris/fuzzing_coverage_guided.md) for the complementary coverage-guided strategy (blocked on Atheris Python 3.12 support).

**Current focus**: Phase 1 (Hypothesis property-based testing)

Notes and pointers:

- All Phase 1 fuzzing uses Python 3.12 with Hypothesis property-based testing
- Concise implementation roadmap: [fuzzing_plan.md](./fuzzing_plan.md)
- Internal risk review: [fuzzing_design_review.md](../archive/fuzzing_design_review.md)
- External review recommendations: [fuzzing_design_review_external.md](../archive/fuzzing_design_review_external.md)

## Security Testing Enhancement Through Property-Based and Coverage-Guided Fuzzing

---

## Executive Summary

This document outlines a comprehensive plan to implement property-based fuzzing for Elspeth's security-critical components using Hypothesis on Python 3.12. The plan is divided into two major phases:

- **Phase 0**: Discovery & Risk Assessment (1-2 weeks, 8-15 hours)
- **Phase 1**: Implementation & Integration (2-3 weeks, 15-30 hours)

The approach focuses on Hypothesis property-based testing with explicit oracle specifications, bug injection validation, and CI integration with appropriate guardrails. This balanced strategy provides strong security testing without the operational complexity of coverage-guided fuzzing infrastructure.

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
2. Achieve ≥85% branch coverage on security-critical modules (realistic target for property-based testing)
3. Establish continuous fuzzing in CI/CD pipeline
4. Support security compliance and accreditation requirements

**Coverage Philosophy**: Target 85% branch coverage, not 95%. Rationale:

- Last 15% often unreachable code (error handlers, edge cases, dead code)
- Property-based testing naturally achieves ~85% with well-designed oracles
- Diminishing returns: 85%→95% requires 3x effort for minimal security improvement
- Better ROI: Cover more security modules at 85% than fewer modules at 95%

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

**Oracle Specifications**:

The following table defines the security invariants (properties that MUST always hold) and allowed exceptions for each fuzzing target. Every property test must enforce these invariants:

| Target | Module | Invariants (MUST hold) | Allowed Exceptions |
|--------|--------|------------------------|-------------------|
| **Path Guard** | `path_guard.py` | • Result always under `base_dir`<br>• No symlink escape<br>• Normalized (no `..` in result)<br>• Absolute paths rejected | `ValueError`, `SecurityError` |
| **URL Validation** | `approved_endpoints.py` | • Scheme in {`https`, `http`}<br>• Host in approved list<br>• No credentials in URL<br>• IDN punycode valid<br>• Port in allowed range | `ValueError`, `URLError` |
| **CSV Sanitizer** | `sanitizers.py` | • Output never starts with `=+-@`<br>• No formula injection<br>• Unicode preserved (NFC)<br>• Hyperlinks removed or quoted | `None` (silent sanitization) |
| **Template Renderer** | `prompt_renderer.py` | • No `eval()` or `exec()` constructs<br>• All variables resolved or error<br>• Output encoding matches input<br>• Template depth < 10 (recursion limit) | `TemplateError`, `SecurityError` |
| **Config Parser** | `config_parser.py` | • Parse → serialize → parse = identity<br>• Required fields present or error<br>• Type coercion consistent<br>• No code execution in YAML | `ConfigError`, `ValidationError` |

**Implementation Requirements**:

1. Each property test must document which invariant(s) it enforces in its docstring
2. Oracle assertions must use descriptive failure messages referencing the invariant
3. Allowed exceptions must be explicitly tested (e.g., "rejects absolute paths with ValueError")
4. Edge cases must map to specific invariants (e.g., symlink escape → "Result always under base_dir")

**Deliverable**: Input domain specification document with invariants and oracles (table above serves as canonical reference)

#### 1.4 Fuzzing Strategy Design (4 hours)

**Objective**: Make architectural decisions for fuzzing implementation

**Key Decisions**:

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Testing Framework | Hypothesis property-based testing | Hypothesis-only (Python 3.12) |
| Corpus Management | Hypothesis native vs. Manual | Use Hypothesis `.hypothesis/examples/` native corpus |
| Oracle Strategy | Differential vs. Crash vs. Assertion | Assertion-based with explicit invariant checking (see oracle table) |
| Coverage Metrics | Line vs. Branch vs. Path | Branch coverage on security modules, target 85% realistic |
| CI Integration | Every PR vs. Nightly vs. On-demand | Fast tests (5min) on PR, deep exploration (15min) nightly |
| Hypothesis Profiles | Single vs. Multiple | Multiple: `ci` (200 examples, derandomized), `explore` (5000 examples) |

**Hypothesis Configuration** (`pyproject.toml`):

```toml
# Pytest marker for fuzzing tests
[tool.pytest.ini_options]
markers = [
    "fuzz: Property-based fuzzing tests (pytest -m fuzz)",
]

# Hypothesis settings
[tool.hypothesis]
# Default profile (local development)
max_examples = 100
deadline = 500  # milliseconds per example

[tool.hypothesis.profiles.ci]
max_examples = 200
deadline = 500
derandomize = true
# Note: print_blob is a CLI flag (--hypothesis-show-statistics), not a config setting

[tool.hypothesis.profiles.explore]
max_examples = 5000
deadline = 5000
derandomize = false
verbosity = "verbose"
```

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

#### 2.2 Bug Injection Smoke Tests (3 hours) ⭐ **CRITICAL**

**Objective**: Verify property tests actually catch bugs (not just exercise code)

**Implementation**:

Create `tests/fuzz_smoke/` directory with intentionally vulnerable implementations:

```python
# tests/fuzz_smoke/test_bug_injection_path_guard.py
"""
Smoke test: Verify property tests catch intentionally injected bugs.
MUST FAIL when BUG_INJECTION_ENABLED=1
"""
import os
import pytest
from hypothesis import given, strategies as st, settings
from pathlib import Path

BUG_INJECTION = os.getenv("BUG_INJECTION_ENABLED") == "1"

def vulnerable_resolve_under_base(base: Path, candidate: str) -> Path:
    """Intentionally vulnerable version for testing."""
    if BUG_INJECTION:
        # VULNERABILITY: Skip normalization, allow traversal
        return base / candidate
    else:
        # Correct implementation
        from elspeth.core.utils.path_guard import resolve_under_base
        return resolve_under_base(base, candidate)

@given(candidate=st.text(min_size=1, max_size=100))
@settings(max_examples=100, deadline=500)
def test_path_traversal_injection_caught(tmp_path, candidate):
    """Property: Path never escapes base (should catch injected bug)."""
    try:
        result = vulnerable_resolve_under_base(tmp_path, candidate)
        # Oracle: Result must be under base_dir
        assert result.is_relative_to(tmp_path), \
            f"BUG DETECTED: Path escaped base: {result}"
    except (ValueError, SecurityError):
        # Allowed exceptions for invalid inputs
        pass
```

**CI Integration** (`.github/workflows/fuzz-smoke.yml`):

```yaml
- name: Verify bug injection fails (must fail with bugs)
  run: |
    BUG_INJECTION_ENABLED=1 pytest tests/fuzz_smoke/ -v
    if [ $? -eq 0 ]; then
      echo "ERROR: Smoke tests passed with bugs injected!"
      exit 1
    fi
  continue-on-error: false

- name: Verify normal tests pass (must pass without bugs)
  run: pytest tests/fuzz_props/ -v
```

**Test Coverage**:

1. Path traversal bypass (path_guard)
2. URL validation bypass (approved_endpoints)
3. Sanitization bypass (CSV formula injection)

**Deliverable**:

- Smoke test suite that proves property tests detect security vulnerabilities
- CI job that validates test effectiveness
- Documentation for IRAP compliance (test effectiveness evidence)

#### 2.3 CI Integration Prototype with Guardrails (4 hours)

**Objective**: Test fuzzing in CI/CD pipeline with resource protection

**Implementation**:

```yaml
# .github/workflows/fuzz.yml (Fast PR tests)
name: Property Tests (Fast)
on: [pull_request, push]

jobs:
  hypothesis-fast:
    runs-on: ubuntu-latest
    timeout-minutes: 5  # Hard limit

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ".[test]"
          pip install hypothesis pytest pytest-cov

      - name: Run fast property tests
        env:
          HYPOTHESIS_PROFILE: ci
        run: |
          pytest tests/fuzz_props/ -v -m fuzz \
            --tb=short --maxfail=3

      - name: Upload crash artifacts (on failure)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: fuzz-crashes-pr-${{ github.run_id }}
          path: .hypothesis/examples/
          retention-days: 7

# .github/workflows/fuzz-nightly.yml (Deep exploration)
name: Property Tests (Deep)
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:  # Manual trigger

jobs:
  hypothesis-explore:
    runs-on: ubuntu-latest
    timeout-minutes: 15  # Longer budget for exploration

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Run deep property exploration
        env:
          HYPOTHESIS_PROFILE: explore
        run: |
          pytest tests/fuzz_props/ -v -m fuzz \
            --hypothesis-seed=random \
            --tb=short

      - name: Upload crash artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: fuzz-crashes-nightly-${{ github.run_id }}
          path: .hypothesis/examples/
          retention-days: 7

      - name: Create issue for crashes
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '[FUZZ] Nightly fuzzing found issues',
              body: 'Fuzzing run failed. Check artifacts.',
              labels: ['security', 'fuzzing', 'needs-triage']
            })
```

**Deliverable**: Working CI workflow with resource guardrails and crash artifact collection

### Week 3: Risk Reduction & Planning (10-15 hours)

#### 3.1 Risk Mitigation Planning & Severity Taxonomy (6 hours)

**Objective**: Prepare for fuzzing challenges with clear triage procedures

**Crash Severity Classification**:

| Severity | Criteria | Examples | Triage SLA | Fix SLA |
|----------|----------|----------|-----------|---------|
| **S0 (Critical)** | Remote code execution, credential leak, arbitrary file access | Path traversal to `/etc/shadow`, `eval()` injection, password disclosure | 4 hours | 24 hours |
| **S1 (High)** | Authentication bypass, privilege escalation, SSRF | Symlink escape, URL validation bypass allowing internal network access | 24 hours | 3 days |
| **S2 (Medium)** | DoS, resource exhaustion, data corruption, formula injection | ZIP bomb, unbounded memory allocation, CSV formula injection | 3 days | 1 week |
| **S3 (Low)** | Logic error without security impact, improper error handling | Incorrect sanitization that's cosmetic, unclear error messages | 5 days | 2 weeks |
| **S4 (Info)** | Duplicate, false positive, test infrastructure issue | Test flakiness, known limitation, environment-specific failure | Best effort | Best effort |

**Triage Procedure**:

1. **Reproduce**: `HYPOTHESIS_SEED=<seed> pytest tests/fuzz_props/test_X.py -k <test_name>`
2. **Classify**: Assign severity S0-S4 based on table above
3. **Minimize**: Use Hypothesis's shrinking (automatic) or manual reduction
4. **Analyze**: Identify root cause and map to oracle violation
5. **Document**: Create GitHub issue with `[FUZZ]` prefix and severity label
6. **Regression**: Convert crash into explicit regression test in `tests/fuzz_props/seeds.py`

**GitHub Issue Template** (`.github/ISSUE_TEMPLATE/fuzz-crash.md`):

```markdown
---
name: Fuzzing Crash Report
about: Report a crash found by property-based fuzzing
labels: security, fuzzing, needs-triage
---

## Crash Details

**Severity**: [S0/S1/S2/S3/S4] (see severity table)
**Test**: `tests/fuzz_props/test_X.py::test_Y`
**Hypothesis Seed**: `<seed value>`

## Reproduction

\```bash
HYPOTHESIS_SEED=<seed> pytest tests/fuzz_props/test_X.py::test_Y -v
\```

## Oracle Violation

Which invariant was violated? (reference oracle table in fuzzing.md)
- [ ] Path escapes base_dir
- [ ] Symlink escape
- [ ] URL validation bypass
- [ ] Formula injection
- [ ] Other: ___

## Impact Assessment

[Describe security impact and exploitability]

## Minimized Example

\```python
# Minimal reproducer
\```
```

**Deliverable**: Risk mitigation checklist with severity taxonomy and triage procedures

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
- Coverage improvement (target: ≥85% branch coverage on security modules)
- Performance impact (<5 min for PR tests)
- Compliance documentation completeness

**Deliverable**: Success metrics dashboard template

---

## Phase 1: Implementation & Integration

### Timeline: 6 Weeks (60-100 hours)

### Weeks 1-2: Foundation (40-60 hours)

#### Task 1: Hypothesis Property Test Suite (10-15 hours)

**Modules to Fuzz** (Priority Order):

1. `path_guard.py` - Path traversal protection
2. `approved_endpoints.py` - URL validation
3. `sanitizers.py` - Input sanitization
4. `prompt_renderer.py` - Template injection
5. `config_parser.py` - YAML/JSON parsing

**Example Property Test with Oracle** (`tests/fuzz_props/test_path_guard_properties.py`):

```python
from hypothesis import given, strategies as st, settings
from pathlib import Path
from elspeth.core.utils.path_guard import resolve_under_base

@given(
    candidate=st.text(
        alphabet=st.characters(blacklist_categories=['Cs']),  # Valid Unicode
        min_size=1,
        max_size=200
    )
)
@settings(max_examples=100, deadline=500)
def test_resolve_under_base_never_escapes(tmp_path, candidate):
    """
    Oracle: Result must always be under base_dir.
    Maps to invariant: "Result always under base_dir" from oracle table.
    """
    try:
        result = resolve_under_base(tmp_path, candidate)

        # Oracle assertion with explicit invariant reference
        assert result.is_relative_to(tmp_path), \
            f"ORACLE VIOLATION: Path escaped base_dir\n" \
            f"  Base: {tmp_path}\n" \
            f"  Candidate: {repr(candidate)}\n" \
            f"  Result: {result}\n" \
            f"  Invariant: Result always under base_dir (see oracle table)"

    except (ValueError, SecurityError):
        # Allowed exceptions for invalid inputs (e.g., absolute paths)
        pass
```

**Property Tests per Module**:

- **path_guard.py**: 5 properties (no escape, normalization, symlink handling, absolute rejection, empty input)
- **approved_endpoints.py**: 5 properties (scheme validation, host allowlist, no credentials, IDN handling, port restrictions)
- **sanitizers.py**: 3 properties (no formula injection, Unicode preservation, hyperlink removal)
- **prompt_renderer.py**: 4 properties (no code execution, variable resolution, encoding consistency, depth limit)
- **config_parser.py**: 3 properties (round-trip identity, type consistency, required fields)

**Total**: 20 property tests across 5 modules

#### Task 2: Seed Corpus and Regression Tests (5-10 hours)

**Corpus Management** (Hypothesis-Native Approach):

Hypothesis automatically manages its corpus in `.hypothesis/examples/`. Do NOT create a separate `corpus/` directory.

**Explicit Regression Tests** (`tests/fuzz_props/seeds.py`):

```python
"""
Documented seeds for regression testing.
Each seed captures a specific bug, attack pattern, or edge case.
"""
import pytest
from elspeth.core.utils.path_guard import resolve_under_base

# Known traversal attempts (from OWASP, CVEs, production incidents)
KNOWN_TRAVERSAL_ATTEMPTS = [
    ("../../../etc/passwd", "CVE-style Unix path traversal"),
    ("..\\..\\..\\windows\\system32\\config\\sam", "Windows path traversal"),
    ("/absolute/path/escape", "Absolute path bypass attempt"),
    ("symlink/../../../etc", "Symlink + traversal combo"),
    ("file://../../etc/passwd", "URL-style file path"),
    ("\x00/../etc/passwd", "Null byte injection"),
]

@pytest.mark.parametrize("candidate,reason", KNOWN_TRAVERSAL_ATTEMPTS)
def test_known_traversal_patterns_rejected(tmp_path, candidate, reason):
    """Regression tests for documented attack patterns."""
    with pytest.raises((ValueError, SecurityError)):
        resolve_under_base(tmp_path, candidate), \
            f"Failed to reject: {reason}"
```

**Sources for Regression Seeds**:

- Existing test fixtures from test suite
- Known attack patterns (OWASP Top 10, MITRE ATT&CK)
- CVE exploit patterns (e.g., CVE-2019-XXXX path traversal)
- Bugs found by fuzzing (added after triage)

**Target**: 10-15 explicit regression tests per high-risk module

### Weeks 3-4: Integration (15-25 hours)

#### Task 4: CI/CD Pipeline Integration (Already completed in Section 2.3)

**Implementation Requirements** (See Section 2.3 for full workflow):

- Fast property tests (<5 min) on every PR using `HYPOTHESIS_PROFILE=ci`
- Deep property exploration (15 min) nightly using `HYPOTHESIS_PROFILE=explore`
- Crash artifact upload to GitHub Actions (7-day retention)
- Automated issue creation for nightly failures with `[FUZZ]` label

#### Task 3: Crash Triage Process (5-10 hours)

**Triage Workflow** (References severity taxonomy in Section 3.1):

1. **Reproduce**: `HYPOTHESIS_SEED=<seed> pytest tests/fuzz_props/test_X.py::test_Y -v`
2. **Classify**: Assign severity S0-S4 (see severity table in Section 3.1)
3. **Minimize**: Hypothesis automatic shrinking provides minimized example
4. **Analyze**: Map to oracle violation (which invariant failed?)
5. **Document**: Create GitHub issue using `[FUZZ]` template
6. **Regression**: Add to `tests/fuzz_props/seeds.py`
7. **Fix**: Implement security patch with tests
8. **Verify**: Re-run property test to confirm fix

**Reproducibility**:

```bash
# With seed from crash report
HYPOTHESIS_SEED=123456789 pytest tests/fuzz_props/test_path_guard_properties.py -k escape -v

# With saved example from .hypothesis/examples/
pytest tests/fuzz_props/ --hypothesis-seed=<seed-from-artifact>

# Manual replay with specific input
pytest tests/fuzz_props/ -k test_name --hypothesis-verbosity=verbose
```

**Documentation Requirements** (Per crash):

- GitHub issue with `[FUZZ]` prefix and severity label (S0-S4)
- Hypothesis seed for reproduction
- Oracle violation description (which invariant?)
- Impact assessment (exploitability, data at risk)
- Minimized example code
- Fix verification (regression test passing)

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

## Implementation Approach

### Recommended: Phased Rollout

**Total Investment**: 30-45 hours over 3-4 weeks

**Phase 0** (Week 1, ~8-15 hours):

- Define oracle specifications (complete table)
- Implement 3-5 property tests for highest-risk module (path_guard.py)
- Add 2-3 bug injection smoke tests
- Configure Hypothesis profiles in pyproject.toml

**Phase 1** (Weeks 2-3, ~15-25 hours):

- Expand to 15-20 property tests across 5 security modules
- Integrate with CI (PR + nightly workflows)
- Add crash triage procedures and severity taxonomy
- Document 10-15 regression seeds per module

**Phase 2** (Week 4, ~5-10 hours):

- Coverage optimization (identify untested branches)
- Performance tuning (achieve <5 min PR runtime)
- Documentation and IRAP compliance evidence
- Training materials for team

**Decision Points**:

✅ **After Phase 0**: Did we find 1+ real bugs? → Proceed to Phase 1
✅ **After Phase 1**: Are we maintaining <5% false positive rate? → Proceed to Phase 2
⚠️ **If false positives >10%**: Refine oracles before expanding

**When to Scale Back**:

- No bugs found after 200+ examples per property (may indicate low-value target)
- False positive rate >15% (oracle specifications too strict or code too dynamic)
- CI runtime exceeds 7 minutes consistently (need better mocking or reduced examples)

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

### Phase 0 Success Metrics (Discovery)

- ✅ **Oracle specifications**: Complete oracle table with invariants for 5 targets
- ✅ **Bug injection tests**: 3+ smoke tests that catch intentionally injected bugs
- ✅ **Property tests**: 3+ property tests passing with explicit oracle assertions
- ✅ **Bug discovery**: 1+ real security issue found and fixed
- ✅ **CI integration**: Fast property tests running in <5 minutes on PRs

### Phase 1 Success Metrics (Production)

**Discovery Metrics**:

- ✅ **Unique bugs found**: ≥ 2 real security issues discovered
- ✅ **Bug injection detection rate**: 100% of injected bugs caught by property tests
- ✅ **Property test coverage**: ≥ 15 property tests across 5 security modules

**Coverage Metrics** (Realistic, Not Aspirational):

- ✅ **Branch coverage on security modules**: ≥ 85% (not 95% - external review recommendation)
- ✅ **Coverage delta per property**: Each new property adds ≥ 3% coverage to target module
- ✅ **Untested critical branches**: <20 in security-critical code paths

**Performance Metrics** (CI Health):

- ✅ **PR test runtime**: ≤ 5 minutes (fast feedback, no blocking)
- ✅ **Nightly exploration runtime**: ≤ 15 minutes (deep search within budget)
- ✅ **Test failure rate**: <5% (mostly true bugs, not flakes or environmental issues)

**Maintenance Metrics** (Sustainability):

- ✅ **Crash triage time**: <24h for S0/S1, <3 days for S2 (per SLA table)
- ✅ **False positive rate**: <10% of reported crashes
- ✅ **Corpus size**: .hypothesis/examples/ < 50MB per target (pruned regularly)

**Compliance Evidence** (IRAP/Accreditation):

- ✅ **Oracle documentation**: Explicit security invariants documented for each target
- ✅ **Test effectiveness proof**: Bug injection tests demonstrate vulnerability detection
- ✅ **Continuous testing evidence**: Timestamped CI runs with crash artifacts
- ✅ **Remediation tracking**: GitHub issues linking crashes to fixes

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

### Immediate Actions (Week 1, Priority Order)

1. **Define oracle specifications** (CRITICAL) - Complete the oracle table for all 5 target modules
2. **Add Hypothesis profiles** - Configure `pyproject.toml` with ci and explore profiles
3. **Implement 2 bug injection tests** - Prove property tests can catch vulnerabilities
4. **Write 3 property tests** - Start with path_guard.py (highest risk)
5. **Run coverage analysis** - Identify untested branches in security modules

### Integration with External Review

This strategy incorporates recommendations from the external review (see `fuzzing_design_review_external.md`):

✅ **Adopted**:

- Explicit oracle table (Section 1.3) - CRITICAL addition
- Bug injection smoke tests (Section 2.2) - Proves test effectiveness
- Severity taxonomy with SLAs (Section 3.1) - Clear triage procedures
- Hypothesis profiles (Section 1.4) - ci and explore configurations
- CI guardrails (Section 2.3) - Timeout budgets and artifact collection
- Hypothesis-appropriate metrics (Success Criteria) - 85% coverage, not 95%

⚠️ **Adapted**:

- Differential testing - Only for URL validation (where applicable)
- Timeout handling - Use Hypothesis `deadline` setting, not custom utilities
- Corpus management - Use Hypothesis native `.hypothesis/examples/`

❌ **Deferred**:

- Mutation testing - Separate quality initiative, not fuzzing
- Edge-based metrics - Not applicable to Hypothesis
- Atheris/coverage-guided fuzzing - Operational complexity not justified for current risk profile

### Go/No-Go Decision Criteria

**Proceed to Phase 1 if** (after Phase 0):

- Bug injection tests catch 100% of injected vulnerabilities
- Property tests find 1+ real security issues in path_guard or URL validation
- CI integration functional with <5 min PR runtime
- Team can commit 15-25 hours for expansion

**Scale back or defer if**:

- False positive rate >15% after oracle refinement
- No bugs found in 500+ examples across 3 properties
- CI runtime consistently >7 minutes despite optimization
- Team bandwidth <10 hours over next 2 weeks

---

## Appendix A: Tool Selection Rationale

### Why Hypothesis Property-Based Testing?

**Decision**: Use Hypothesis exclusively for property-based fuzzing on Python 3.12

**Rationale**:

| Factor | Hypothesis Strengths |
|--------|---------------------|
| **Setup Complexity** | Low - pip install, works with pytest, no special infrastructure |
| **Python Compatibility** | Native Python 3.12 support, no version juggling |
| **Bug Finding** | Good for logic errors and security invariants when oracles are well-defined |
| **Debugging** | Excellent - automatic shrinking, deterministic reproduction with seeds |
| **CI Integration** | Easy - runs in standard pytest, fast feedback (<5 min) |
| **Maintenance** | Low - stdlib-like stability, minimal API churn |
| **Learning Curve** | Moderate - team already familiar with pytest |
| **Cost** | Zero - open source, no dedicated infrastructure |

**Why Not Atheris (Coverage-Guided Fuzzing)?**

While Atheris offers superior edge-case discovery through coverage guidance, it introduces operational complexity:

- **Python 3.11 requirement**: Forces version juggling (runtime on 3.12, fuzz on 3.11)
- **Infrastructure needs**: Dedicated fuzzing servers or extended CI time (hours, not minutes)
- **Higher false positive rate**: Finds crashes without semantic meaning more often
- **Maintenance burden**: More complex setup, crash reproduction harder
- **Overkill for current risk**: Property testing with explicit oracles sufficient for identified threat surfaces

**Decision Rule**: Adopt Hypothesis first. Only consider coverage-guided fuzzing (Atheris/libFuzzer) if:

1. Hypothesis finds 5+ high-severity bugs (proving ROI)
2. Code complexity increases significantly (parser expansion, new untrusted input)
3. External compliance mandate (e.g., FIPS, Common Criteria)
4. Team can commit 100+ hours to infrastructure and maintenance

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

## Conclusion and Path Forward

### Phase 1: Foundation (This Document)

Hypothesis property-based testing (30-45 hours over 3-4 weeks) provides immediate, high-value security testing with explicit oracles and low operational overhead. This phase establishes fuzzing practices, builds team expertise, and demonstrates ROI through bug discovery.

**Key to success**: Treat fuzzing as an ongoing security practice integrated into development, not a one-time activity.

### Phase 2: Advanced Coverage (When Ready)

For mission-critical systems handling classified data and PII, **Phase 2 (coverage-guided fuzzing with Atheris)** provides defense-in-depth by discovering unknown edge cases that property testing misses.

**Phase 2 is justified when**:

- ✅ Phase 1 finds ≥2 security bugs (proves fuzzing ROI)
- ✅ Atheris supports Python 3.12 (technical blocker removed)
- ✅ Threat profile warrants additional investment (classified data, nation-state actors)

**Status**: 🔶 **BLOCKED** on Atheris Python 3.12 support (est. Q2 2025+)

**Documentation**:

- **Strategy**: [fuzzing_coverage_guided.md](../archive/phase2_blocked_atheris/fuzzing_coverage_guided.md) - Complete Atheris approach
- **Roadmap**: [fuzzing_coverage_guided_plan.md](./fuzzing_coverage_guided_plan.md) - Implementation timeline
- **Tracking**: [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md) - Prerequisites and monitoring

### Defense-in-Depth Fuzzing Strategy

**Both approaches complement each other**:

- **Hypothesis (Phase 1)**: Fast oracle validation of *known* security invariants
- **Atheris (Phase 2)**: Deep exploration to discover *unknown* edge cases

**Recommended for**:

- High-assurance systems (classified, PII, mission-critical)
- IRAP/Common Criteria compliance requirements
- Systems with complex parsers (URLs, paths, templates)
- Post-incident hardening after security vulnerabilities

**Not recommended if**:

- Phase 1 finds <2 bugs (Hypothesis may be sufficient)
- Limited team capacity (<40 hours available)
- Lower-risk codebase without classified data handling
