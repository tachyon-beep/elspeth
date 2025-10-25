# ADR 011 – Testing Strategy & Quality Gates

## Status

**DRAFT** (2025-10-26)

**Priority**: P1 (Next Sprint)

## Context

Elspeth is a security-critical platform handling classified data with stringent regulatory requirements (government, healthcare, finance). Quality is non-negotiable per ADR-001 priority #2 (Data Integrity). The codebase has comprehensive test coverage with clear patterns documented in `docs/development/testing-overview.md`, but testing requirements are **not formalized as an ADR**.

### Current State

**Implemented and Working**:
- ✅ Test markers (`@pytest.mark.integration`, `@pytest.mark.slow`)
- ✅ Coverage gates via SonarQube integration
- ✅ Mutation testing used in refactoring methodology (Phase 0)
- ✅ Characterization tests required before refactoring
- ✅ Comprehensive test suite (configuration, datasources, middleware, LLM, sanitization, signing, pipeline)

**Problems**:
1. **No Formal Requirements**: Coverage targets exist but not mandated
2. **Inconsistent Standards**: Security-critical code vs general code not differentiated
3. **No Quality Gates**: What MUST pass for merge? Unclear.
4. **Contributor Confusion**: New contributors unsure of test expectations
5. **Refactoring Dependency**: Methodology requires 80%+ coverage but not architecturally required

### Quality as Core Principle

**ADR-001 Priority #2**: Data Integrity

> "Ensure results, artifacts, and provenance are trustworthy and reproducible; maintain tamper-evident audit trails."

**Refactoring Methodology Dependency**:
- Phase 0 requires **80%+ coverage** on target function
- Mutation testing to verify test quality (≤10% survivors)
- Without coverage, refactoring unsafe (risk of behavioral changes)

**Need**: Formalize testing requirements to support quality and refactoring discipline.

## Decision

We will establish formal **testing strategy** with **component-specific coverage requirements** and **quality gates** that must pass before merge.

---

## Part 1: Coverage Requirements by Component Type

### Coverage Targets

#### 1. Security-Critical Components (>90% coverage)

**Definition**: Components enforcing security controls (ADR-001 priority #1)

**Components**:
- `src/elspeth/core/security/` – Security enforcement, signing, audit logging
- `src/elspeth/core/base/plugin.py` – BasePlugin security bones (ADR-004)
- `src/elspeth/core/data/classified_data.py` – ClassifiedDataFrame (ADR-002-A)
- `src/elspeth/core/pipeline/artifact_pipeline.py` – Security-aware artifact flow
- Middleware: Content safety, prompt shielding

**Coverage Target**: **>90%** line coverage

**Additional Requirements**:
- ✅ Mutation testing (≤10% survivors)
- ✅ Property-based testing (where applicable)
- ✅ Security-specific test cases (boundary conditions, privilege escalation attempts)

**Rationale**: Security cannot be compromised. High coverage + mutation testing ensures security controls work.

**Enforcement**: The `ci-quality-gate` GitHub Actions workflow runs `pytest --cov`
and `mutmut` for the security-critical packages. The job fails if coverage drops
below 90% or if more than 10% of mutations survive, and posts a status comment on
pull requests for reviewer visibility.

---

#### 2. Core Orchestration (>80% coverage)

**Definition**: Components managing pipeline execution and coordination

**Components**:
- `src/elspeth/core/experiments/` – Suite runner, experiment runner, orchestrator
- `src/elspeth/core/pipeline/` – ArtifactPipeline, dependency resolution
- `src/elspeth/core/registries/` – Plugin registries (ADR-007)
- `src/elspeth/core/config.py` – Configuration merge (ADR-008)
- `src/elspeth/core/validation/` – Schema validation, settings validation

**Coverage Target**: **>80%** line coverage

**Additional Requirements**:
- ✅ Integration tests (component interaction)
- ✅ Error path coverage (failure scenarios)
- ✅ Characterization tests before refactoring (per methodology)

**Rationale**: Orchestration bugs cause cascading failures. High coverage ensures reliability.

---

#### 3. Plugin Implementations (>70% coverage)

**Definition**: Datasources, transforms, sinks, middleware

**Components**:
- `src/elspeth/plugins/nodes/sources/` – Datasources
- `src/elspeth/plugins/nodes/transforms/llm/` – LLM clients, middleware
- `src/elspeth/plugins/nodes/sinks/` – Result sinks
- `src/elspeth/plugins/experiments/` – Baseline, aggregators, early stop

**Coverage Target**: **>70%** line coverage

**Additional Requirements**:
- ✅ Happy path tests (normal operation)
- ✅ Error handling tests (`on_error` policies)
- ✅ Security level validation tests

**Rationale**: Plugins are user-extensible, test coverage ensures base quality. Lower target acknowledges variation.

---

#### 4. Configuration & Validation (>85% coverage)

**Definition**: Configuration loading, merging, validation

**Components**:
- `src/elspeth/core/config.py` – Configuration merge logic
- `src/elspeth/core/validation/` – Validation pipeline
- Configuration loading (YAML parsing, schema validation)

**Coverage Target**: **>85%** line coverage

**Additional Requirements**:
- ✅ All merge paths tested (suite defaults, prompt packs, experiments)
- ✅ All validation failures tested (syntax, structure, schema)
- ✅ Edge cases (null handling, `__delete__` markers)

**Rationale**: Configuration errors are #1 user pain point. High coverage prevents silent failures.

---

### Coverage Summary Table

| Component Type | Coverage Target | Mutation Testing | Integration Tests |
|----------------|----------------|------------------|-------------------|
| **Security-Critical** | **>90%** | ✅ Required | ✅ Required |
| **Core Orchestration** | **>80%** | ⚠️ Recommended | ✅ Required |
| **Plugin Implementations** | **>70%** | ❌ Not required | ⚠️ Recommended |
| **Configuration** | **>85%** | ⚠️ Recommended | ✅ Required |

Coverage is enforced automatically in CI via the `ci-quality-gate` workflow and
SonarQube. A merge is blocked if any component type falls below its target.

---

## Part 2: Test Pyramid

### Test Distribution

**Pyramid Structure** (relative proportion):
```
       ┌─────────────────┐
       │  E2E Tests (5%) │  Full pipeline, slow
       ├─────────────────┤
       │ Integration (25%)│  Component interaction
       ├─────────────────┤
       │  Unit Tests (70%)│  Fast, isolated
       └─────────────────┘
```

**Rationale**: Broad base of fast unit tests, fewer slow integration/E2E tests.

---

### Test Type 1: Unit Tests (70%)

**Purpose**: Test individual functions/classes in isolation

**Characteristics**:
- Fast (<10ms per test)
- No external dependencies (mocked)
- High volume (100s of tests)

**Example**:
```python
def test_security_level_comparison():
    """Unit test: Security level ordering."""
    assert SecurityLevel.SECRET > SecurityLevel.CONFIDENTIAL
    assert SecurityLevel.CONFIDENTIAL > SecurityLevel.OFFICIAL
    assert SecurityLevel.OFFICIAL > SecurityLevel.UNOFFICIAL
```

**Coverage Target**: 70% of total test suite

---

### Test Type 2: Integration Tests (25%)

**Purpose**: Test component interaction (datasource + transform, transform + sink)

**Characteristics**:
- Medium speed (100ms-1s per test)
- Multiple components
- Real dependencies (test databases, file systems)

**Marker**: `@pytest.mark.integration`

**Example**:
```python
@pytest.mark.integration
def test_datasource_to_transform_pipeline():
    """Integration test: Datasource → LLM transform."""
    datasource = CsvLocalDataSource(file_path="test_data.csv")
    llm = MockLLMClient()

    results = []
    for row in datasource.load_data():
        result = llm.transform(row)
        results.append(result)

    assert len(results) == len(datasource.load_data())
    # Verify transform behavior
```

**Coverage Target**: 25% of total test suite

---

### Test Type 3: End-to-End Tests (5%)

**Purpose**: Test full pipeline (datasource → transform → sink)

**Characteristics**:
- Slow (1-10s per test)
- Full pipeline execution
- Real file I/O, external services (mocked LLMs)

**Marker**: `@pytest.mark.slow`

**Example**:
```python
@pytest.mark.slow
def test_full_experiment_pipeline():
    """E2E test: Full experiment execution."""
    suite_runner = ExperimentSuiteRunner(
        settings_path="test_suite/settings.yaml",
        suite_root="test_suite/",
    )

    suite_runner.run()

    # Verify outputs exist
    assert Path("outputs/results.csv").exists()
    assert Path("outputs/report.md").exists()
    # Verify correctness
```

**Coverage Target**: 5% of total test suite

---

## Part 3: Test Type Requirements

### Test Type 1: Characterization Tests

**Purpose**: Capture existing behavior before refactoring (per refactoring methodology Phase 0)

**When Required**: Before refactoring functions with complexity ≥25

**Characteristics**:
- 6+ integration tests capturing complete workflows
- Cover all entry points to target function
- Capture side effects (file I/O, logging, state changes)

**Example** (from refactoring methodology):
```python
# Characterization test: Capture suite runner behavior
def test_suite_runner_baseline_comparison():
    """Characterize baseline comparison workflow."""
    # Setup
    suite = create_test_suite_with_baseline()

    # Execute
    results = suite_runner.run()

    # Characterize outputs
    assert "baseline_results" in results
    assert "variant_results" in results
    assert "comparison_report" in results
    # Verify side effects
    assert Path("outputs/baseline.csv").exists()
```

**Coverage Requirement**: 80%+ on target function before refactoring

**Validation**: Mutation testing (≤10% survivors)

---

### Test Type 2: Mutation Tests

**Purpose**: Verify test quality (do tests catch bugs?)

**When Required**: Security-critical components (>90% coverage target)

**Tool**: `mutmut` (Python mutation testing)

**Process**:
1. Run mutation testing: `mutmut run --paths-to-mutate src/path/target.py`
2. Check survivors: `mutmut results`
3. Target: ≤10% survivors (90%+ mutations caught)

**Example Mutations**:
- Change `>` to `>=` (boundary condition)
- Change `and` to `or` (boolean logic)
- Remove `return` statement
- Change constant values

**Interpretation**:
- High survivors = weak tests (don't catch bugs)
- Low survivors = strong tests (catch most bugs)

**Requirement**: Security-critical components MUST have ≤10% survivors

---

### Test Type 3: Property-Based Tests

**Purpose**: Test invariants across wide input space

**When Recommended**: Validation logic, parsers, security checks

**Tool**: `hypothesis` (Python property-based testing)

**Example**:
```python
from hypothesis import given, strategies as st

@given(st.text(), st.text())
def test_deep_merge_commutative_for_disjoint_keys(dict1, dict2):
    """Property: Deep merge is commutative for disjoint keys."""
    # Assume disjoint keys
    assume(set(dict1.keys()).isdisjoint(set(dict2.keys())))

    # Property: Order doesn't matter
    result1 = deep_merge(dict1, dict2)
    result2 = deep_merge(dict2, dict1)

    assert result1 == result2
```

**Requirement**: Recommended (not mandatory) for validation logic

---

## Part 4: Quality Gates

### Pre-Merge Requirements (ALL MUST PASS)

#### Gate 1: All Tests Pass

**Requirement**: 100% test pass rate

**Command**: `python -m pytest`

**Failure**: Merge blocked until tests pass

**Exception**: None (no exceptions)

---

#### Gate 2: Coverage Targets Met

**Requirement**: Coverage targets per component type (see Part 1)

**Command**: `python -m pytest --cov=elspeth --cov-report=term-missing`

**Targets**:
- Security-critical: >90%
- Core orchestration: >80%
- Plugin implementations: >70%
- Configuration: >85%

**Failure**: Merge blocked if coverage below target

**Exception**: New code only (existing code grandfathered)

---

#### Gate 3: MyPy Clean (Type Checking)

**Requirement**: No type errors

**Command**: `python -m mypy src/elspeth`

**Configuration**: `pyproject.toml` lines 177-199

**Failure**: Merge blocked on type errors

**Exception**: `# type: ignore` with justification comment

---

#### Gate 4: Ruff Clean (Linting)

**Requirement**: No linting errors

**Command**: `python -m ruff check src tests`

**Configuration**: `pyproject.toml` (Ruff section)

**Failure**: Merge blocked on errors (warnings allowed)

**Exception**: `# noqa` with justification comment

---

#### Gate 5: Mutation Testing (Security-Critical Only)

**Requirement**: ≤10% survivors for security-critical components

**Command**: `mutmut run --paths-to-mutate src/elspeth/core/security/`

**Frequency**: Required for security-critical code changes

**Failure**: Merge blocked if >10% survivors

**Exception**: Justification required for unKillable mutants

---

### Quality Gate Summary

| Gate | Requirement | Command | Exception |
|------|-------------|---------|-----------|
| **All Tests Pass** | 100% pass | `pytest` | None |
| **Coverage Targets** | Component-specific | `pytest --cov` | New code only |
| **MyPy Clean** | No type errors | `mypy src/elspeth` | `# type: ignore` + comment |
| **Ruff Clean** | No lint errors | `ruff check` | `# noqa` + comment |
| **Mutation Testing** | ≤10% survivors | `mutmut run` | Security-critical only |

---

## Consequences

### Benefits

1. **Quality Assurance**: Clear expectations for all contributors
2. **Security Confidence**: High coverage + mutation testing for critical code
3. **Refactoring Safety**: 80%+ coverage enables safe refactoring (per methodology)
4. **Predictable Merges**: Quality gates prevent low-quality code
5. **Documentation**: Formalized testing requirements (not ad-hoc)

### Limitations / Trade-offs

1. **Higher Bar**: More tests required, may slow development velocity
   - *Mitigation*: Quality > speed (ADR-001 priority #2)

2. **CI Latency**: Mutation testing slow (~5-10 minutes)
   - *Mitigation*: Run only on security-critical changes

3. **Coverage Gaming**: Developers may write shallow tests for coverage
   - *Mitigation*: Mutation testing catches weak tests

4. **Strict Gates**: May block urgent fixes
   - *Mitigation*: Exception process with justification (security review)

5. **Test Maintenance**: More tests = more maintenance burden
   - *Mitigation*: Test pyramid (70% fast unit tests)

### Future Enhancements (Post-1.0)

1. **Coverage Ratchet**: Prevent coverage regression (only increase allowed)
2. **Differential Coverage**: Require 100% coverage on changed lines
3. **Performance Regression Tests**: Benchmark critical paths
4. **Fuzz Testing**: Security-critical parsers (YAML, JSON)
5. **Visual Regression Tests**: Report generation (screenshot comparison)

### Implementation Checklist

**Phase 1: Documentation** (P1, 1 hour):
- [x] Testing strategy documented (`docs/development/testing-overview.md`)
- [ ] Formalize as ADR (this document)
- [ ] Update contributor guide with quality gates

**Phase 2: CI Integration** (P1, 1-2 hours):
- [ ] Add coverage gates to CI (fail if below target)
- [ ] Add MyPy to CI (fail on type errors)
- [ ] Add Ruff to CI (fail on lint errors)
- [ ] Add mutation testing for security-critical PRs

**Phase 3: Tooling** (P2, post-1.0):
- [ ] Coverage ratchet (prevent regression)
- [ ] Differential coverage reporting
- [ ] Performance benchmarking

### Related ADRs

- **ADR-001**: Design Philosophy – Quality is priority #2 (Data Integrity)
- **ADR-004**: Mandatory BasePlugin – Security-critical component (>90% coverage required)
- **Refactoring Methodology**: Depends on 80%+ coverage (Phase 0)

### Implementation References

- `docs/development/testing-overview.md` – Current testing guide
- `docs/refactoring/METHODOLOGY.md` – Phase 0 coverage requirements
- `pyproject.toml` lines 177-199 – MyPy configuration
- `pyproject.toml` (Ruff section) – Linting configuration
- `.github/workflows/` – CI integration (to be updated)

---

**Document Status**: DRAFT – Requires review and acceptance
**Next Steps**:
1. Review with team (coverage targets approval)
2. Add coverage gates to CI
3. Update contributor guide
4. Run mutation testing on security-critical components
