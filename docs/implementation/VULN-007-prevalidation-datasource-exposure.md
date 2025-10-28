# VULN-007: Pre-Validation Datasource Exposure

**Priority**: P0 (CRITICAL)
**Effort**: 12-16 hours (2 days)
**Sprint**: Sprint 6 / Post-Security Audit
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-002, ADR-002-A, ADR-002-B, ADR-004
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #24

**Implementation Note**: Must restore ADR-002 fail-fast guarantees by restructuring suite runner start-up order and CLI bundling path.

---

## Problem Description / Context

### VULN-007: Pre-Validation Datasource Exposure

**Finding**:
The suite execution path loads datasource content before ADR-002 start-time validation runs, allowing SECRET data to enter memory, logs, and artifact pipelines even when downstream components lack clearance.

**Impact**:
- SECRET or PROTECTED datasets can be fetched into process memory while the pipeline later fails the clearance check (`src/elspeth/core/experiments/suite_runner.py:1030-1060`).
- CLI signed-bundle generation re-reads the datasource outside the validated pipeline, bypassing operating-level enforcement (`src/elspeth/core/cli/suite.py:136-154`).
- Violates ADR-001 fail-closed and Bell-LaPadula “no read up”; attackers can exfiltrate data by pairing high-class datasources with low-clearance sinks and ignoring the validation error.

**Attack Scenario**:
```python
suite_runner = ExperimentSuiteRunner(
    suite=classified_suite,
    llm_client=UnofficialLLM(),  # clearance: UNOFFICIAL
    sinks=[CsvResultSink()],      # clearance: UNOFFICIAL
    datasource=SecretBlobDatasource(),  # clearance: SECRET
)
# SECRET data loaded here
results = suite_runner.run(df=None)
# Validation then raises SecurityValidationError, but data already in memory/logs
```

**Related ADRs**: ADR-001, ADR-002, ADR-002-A, ADR-002-B

**Status**: ADRs implemented but violated by current ordering.

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/experiments/suite_runner.py
if df is None:
    df = self.datasource.load()  # SECURITY: executes before _validate_experiment_security()
...
self._validate_experiment_security(...)
```

**Problems**:
1. Datasource load happens before clearance envelope validation.
2. Datasource and LLM plugin contexts never receive operating_level; trusted downgrade logic cannot run.
3. CLI bundle generator bypasses validation and security-level propagation.

### What's Missing

1. **Deferred load orchestration** – Need to compute operating level before fetching data.
2. **Context propagation** – Datasource/LLM must receive derived contexts with operating_level.
3. **Secure bundling path** – Bundle creation must reuse validated payload rather than reloading source data.

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/experiments/suite_runner.py` (UPDATE) – Restructure run flow, propagate operating level to datasource & LLM.
- `src/elspeth/core/base/plugin_context.py` (UPDATE) – Ensure derive paths handle datasource/LLM attachments if needed.

**CLI / Tooling** (2 files):
- `src/elspeth/core/cli/suite.py` (UPDATE)
- `src/elspeth/core/cli/single.py` (UPDATE)

**Tests** (3 new/updated):
- `tests/core/experiments/test_suite_runner_security.py` (NEW)
- `tests/core/cli/test_suite_bundle_security.py` (NEW)
- Existing suite-runner tests (UPDATE) to reflect deferred loading.

---

## Target Architecture / Design

### Design Overview

```
Suite.run()
  ├─ gather plugins ➜ compute operating_level
  ├─ propagate operating_level to datasource, llm, middlewares
  ├─ datasource.load(operating_level-aware)
  └─ runner.run(SecureDataFrame)
```

**Key Design Decisions**:
1. **Validation-first orchestration**: Instantiate datasource but defer `.load()` until after `_validate_experiment_security()` completes successfully.
2. **Context propagation**: Use `PluginContext.derive()` to inject `operating_level` into datasource and LLM contexts so `get_effective_level()` works uniformly.
3. **Bundle reuse**: Persist validated payload/metadata and reuse for signed bundle creation to prevent unvetted reloads.

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: Pre-validation data exposure** | Deferred load + fail-fast | PLANNED |
| **T2: Operating level bypass** | Context propagation | PLANNED |
| **T3: Bundle reload bypass** | Reuse validated payload | PLANNED |

---

## Design Decisions

### 1. Deferred Loading Guard

**Problem**: Need to block data fetch until security envelope validated.

**Options**:
- **Option A**: Load immediately, discard on failure – leaks possible (Rejected).
- **Option B**: Defer load using callable/closure – ensures validation first (Chosen).
- **Option C**: Precompute metadata without data fetch – infeasible for arbitrary datasources.

**Decision**: Defer load by passing datasource handle into validation, then call `load()` only after success.

**Rationale**: Meets fail-closed requirement while keeping plugin APIs stable.

### 2. Context Propagation to Datasource & LLM

**Problem**: Datasource/LLM never receive operating_level, breaking downgrade logic.

**Decision**: After computing `operating_level`, re-derive contexts for datasource and LLM before invoking `.load()` or `.generate()`.

### 3. Secure Bundle Generation

**Problem**: CLI re-reads datasource outside validation.

**Decision**: Persist run payload & metadata (including security level) for bundle construction; remove direct datasource reload.

---

## Implementation Phases (TDD)

### Phase 1.0: Regression Tests (3-4 hours)

#### Objective
Capture failing scenarios where data loads before validation and bundle bypass occurs.

#### Changes
1. Add suite-runner regression test asserting datasource `load()` is not called when validation fails.
2. Add CLI test ensuring bundle creation uses provided metadata/security level and does not touch datasource.
3. Prepare fixtures for fake datasource tracking load invocations.

### Phase 2.0: Orchestration Refactor (5-7 hours)

#### Objective
Restructure suite runner to compute operating level before loading data.

#### Changes
- Introduce deferred load closure or boolean guard in `ExperimentSuiteRunner.run()`.
- Propagate operating_level to datasource & LLM contexts via `apply_plugin_context`.
- Ensure runner metadata still records classification correctly.

### Phase 3.0: CLI Hardening (3-5 hours)

#### Objective
Disallow raw datasource reload during bundle creation and use stored metadata.

#### Changes
- Update CLI helpers to require payload metadata containing security_level.
- Fail loud if metadata missing rather than reloading datasource.

**Testing**: Re-run security regression suite, full unit tests, targeted integration tests.
