# FEAT-003: Suite Operating-Level Observability & Regression Harness

**Priority**: P2 (MEDIUM)
**Effort**: 8-12 hours (1.5 days)
**Sprint**: Sprint 6 / Post-Security Audit
**Status**: PLANNED
**Completed**: N/A
**Depends On**: VULN-007, VULN-008, ADR-013
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #26

**Implementation Note**: Build observability and regression tooling around security-level propagation to prevent future drift.

---

## Problem Description / Context

### FEAT-003: Operating-Level Observability

**Problem Statement**:
Security audit highlighted blind spots around how operating levels are recorded and verified across experiments and artifact bundles. The existing implementation only exposes the last experiment’s operating level and lacks regression coverage for downgrade scenarios.

**Motivation**:
- Support IRAP evidence by proving that every experiment and suite export records the most restrictive operating level actually processed.
- Enable automated regression tests that break the build when security-level propagation regresses.
- Provide developers with telemetry hooks to audit downgrade paths taken by trusted components.

**Use Case**:
```python
tracker = OperatingLevelTracker()
tracker.record(experiment="baseline", level=SecurityLevel.SECRET)
tracker.record(experiment="followup", level=SecurityLevel.OFFICIAL)
assert tracker.suite_level == SecurityLevel.SECRET
```

**Related ADRs**: ADR-002, ADR-013 (global observability policy)

**Status**: ADR documented but observability hooks missing.

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/experiments/suite_runner.py
ctx.operating_security_level = operating_level  # overwritten per experiment
...
results["_operating_security_level"] = ctx.operating_security_level
```

**Problems**:
1. Aggregated suite level reflects only the final experiment, not the max across the run.
2. No telemetry emitted when plugins operate below their declared clearance (trusted downgrade).
3. No regression harness verifying that operating level metadata stays consistent across CLI commands.

### What's Missing

1. **OperatingLevelTracker** – Utility to accumulate per-experiment levels and emit suite-wide maximum.
2. **Telemetry hooks** – Structured logs/metrics for downgrade events and final suite classification.
3. **Regression tests & fixtures** – Cover CLI bundle metadata, JSON exports, and downgrade traces.

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/experiments/suite_runner.py` (UPDATE) – Integrate tracker.
- `src/elspeth/core/cli/suite.py` (UPDATE) – Use tracker output for artifacts.

**Observability**:
- `src/elspeth/core/utils/logging.py` (UPDATE) – Add helper for downgrade telemetry.

**Tests** (3 files):
- `tests/core/experiments/test_operating_level_tracker.py` (NEW)
- `tests/core/cli/test_suite_operating_level.py` (NEW)
- Update existing downgrade tests to assert telemetry.

---

## Target Architecture / Design

### Design Overview

```
SuiteExecutionContext
  └─ OperatingLevelTracker
        ├─ record(experiment, level)
        └─ suite_level = max(recorded_levels)
CLI bundle
  └─ uses tracker.suite_level
```

**Key Design Decisions**:
1. **Max aggregation**: Always surface the most restrictive security level across the suite.
2. **Telemetry events**: Log downgrade events with plugin name, declared level, and operating level for audit.
3. **Regression harness**: Add pytest fixtures to assert suite-level metadata across CLI pathways.

### API Design

```python
tracker = OperatingLevelTracker()
tracker.record("baseline", SecurityLevel.SECRET)
tracker.record("experiment_b", SecurityLevel.OFFICIAL)
assert tracker.suite_level == SecurityLevel.SECRET
tracker.as_dict()
# {'baseline': 'SECRET', 'experiment_b': 'OFFICIAL', 'suite': 'SECRET'}
```

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: Misreported suite classification** | Tracker aggregation | PLANNED |
| **T2: Undetected downgrade misuse** | Telemetry hooks | PLANNED |
| **T3: Regression drift** | Automated tests | PLANNED |

---

## Design Decisions

### 1. Tracker Storage Format

**Options**:
- **Option A**: Simple dict in memory – easiest, no persistence (Chosen).
- **Option B**: Persist to disk – unnecessary overhead.
- **Option C**: Use existing metrics infra – not yet integrated.

### 2. Telemetry Emission

**Decision**: Use structured plugin logger events so logs capture downgrade decisions without exposing data content.

### 3. Test Strategy

**Decision**: Create synthetic suite fixtures driving multiple operating levels and assert tracker output and CLI artifact metadata.

---

## Implementation Phases (TDD)

### Phase 1.0: Tracker & Tests (3-4 hours)

- Implement `OperatingLevelTracker` with unit tests covering aggregation and dictionary export.
- Integrate into `SuiteExecutionContext` and assert new behaviour via tests.

### Phase 2.0: CLI Integration (3-4 hours)

- Update CLI helpers to use tracker’s suite level for bundles and exports.
- Add regression tests for `cli suite` command verifying metadata in artifacts.

### Phase 3.0: Telemetry Hooks (2-4 hours)

- Emit structured log events whenever a plugin operates below its declared clearance.
- Verify via tests that downgrade events are logged with expected fields.

**Testing**: Run new regression suite, existing CLI integration tests, ensure no downgrade of current coverage.
