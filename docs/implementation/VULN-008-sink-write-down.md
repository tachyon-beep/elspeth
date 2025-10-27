# VULN-008: Sink Write-Down Due to Missing Payload Clearance Checks

**Priority**: P0 (CRITICAL)
**Effort**: 10-14 hours (2 days)
**Sprint**: Sprint 6 / Post-Security Audit
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-002, ADR-002-B, ADR-005, VULN-007
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #25

**Implementation Note**: Enforce Bell-LaPadula “no write down” rules inside ArtifactPipeline and sink implementations.

---

## Problem Description / Context

### VULN-008: Sink Write-Down Due to Missing Payload Clearance Checks

**Finding**:
Artifact dispatch hands the entire experiment payload and metadata to each sink without verifying the sink’s clearance, enabling UNOFFICIAL sinks to persist SECRET content despite ADR-002 and SecureDataFrame policies.

**Impact**:
- Any sink implementing `write()` can capture high-classification payloads regardless of its declared clearance (`src/elspeth/core/pipeline/artifact_pipeline.py:360-399`).
- Metadata tagging happens after the write, so audit trails show correct classification while the sink already stored the data, defeating compliance.
- Breaks IRAP/ISM requirements around segregation of security domains and invalidates “trusted downgrade” assumptions.

**Attack Scenario**:
```python
sink = CsvResultSink(path="outputs/leak.csv")  # security_level = UNOFFICIAL
binding = SinkBinding(id="csv", sink=sink, security_level=SecurityLevel.UNOFFICIAL, ...)
pipeline.execute(payload={"metadata": {"security_level": SecurityLevel.SECRET}, ...})
# No check before sink.write; UNOFFICIAL sink persists SECRET content
```

**Related ADRs**: ADR-002, ADR-002-B, ADR-005, ADR-007

**Status**: ADRs implemented but enforcement missing along sink path.

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/core/pipeline/artifact_pipeline.py
binding.sink.write(payload, metadata=metadata_dict)
# No verification that binding.security_level >= metadata.security_level
```

**Problems**:
1. Pipeline only checks artifacts retrieved via descriptors; the main payload bypasses clearance checks.
2. Sink implementations (e.g., `CsvResultSink`) assume pre-validated payloads and do not self-verify.
3. No regression tests asserting “no write down” behaviour for sinks.

### What's Missing

1. **Payload clearance gate** – Compare payload/metadata security level to sink clearance before invoking `write()`.
2. **Sink self-checks** – Provide helper API or base mixin for sinks to validate incoming payloads.
3. **Regression tests** – Ensure future refactors cannot remove clearance enforcement silently.

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/pipeline/artifact_pipeline.py` (UPDATE) – Enforce clearance check for payload.
- `src/elspeth/core/base/protocols.py` (UPDATE) – Document expected behaviour for sinks.

**Sink Implementations** (2 files):
- `src/elspeth/plugins/nodes/sinks/csv_file.py` (UPDATE)
- `src/elspeth/plugins/nodes/sinks/zip_bundle.py` (UPDATE)

**Tests** (3 files):
- `tests/core/pipeline/test_artifact_pipeline_security.py` (NEW)
- `tests/plugins/sinks/test_csv_sink_security.py` (NEW)
- Update existing bundle tests to cover clearance enforcement.

---

## Target Architecture / Design

### Design Overview

```
ArtifactPipeline.execute()
  ├─ determine payload_level = metadata.security_level
  ├─ if payload_level > sink.security_level: raise SecurityValidationError
  ├─ sink.write(payload)
  └─ register artifacts (existing behaviour)
```

**Key Design Decisions**:
1. **Central enforcement**: Perform clearance checks inside ArtifactPipeline before any sink-specific logic runs.
2. **Fail-loud**: Raise `SecurityValidationError` with clear diagnostics when violation occurs.
3. **Best-effort sinks**: Provide helper utility to enforce intra-sink checks for sinks that create derivative artifacts.

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: Write-down leakage** | Pipeline clearance gate | PLANNED |
| **T2: Sink bypass via custom logic** | Sink helper/mixin | PLANNED |
| **T3: Regression** | Dedicated tests | PLANNED |

---

## Design Decisions

### 1. Clearance Computation

**Problem**: Need a consistent payload security level to compare against sink clearance.

**Decision**: Use `metadata.get("security_level")`; if absent, fall back to runner’s `_active_security_level` or raise error to maintain fail-closed semantics.

### 2. Failure Handling Strategy

**Options**:
- **Option A**: Log and continue – violates fail-loud (Rejected).
- **Option B**: Raise `PermissionError` – misleading for security policy.
- **Option C**: Raise `SecurityValidationError` – aligns with existing controls (Chosen).

### 3. Sink Helper API

**Decision**: Add optional mixin or utility for sinks to call `ensure_security_level(payload_level, self.security_level)` to simplify compliance.

---

## Implementation Phases (TDD)

### Phase 1.0: Tests First (3-4 hours)

- Add pipeline test verifying SECRET payload routed to UNOFFICIAL sink raises `SecurityValidationError`.
- Add sink-specific regression test ensuring `CsvResultSink` rejects mismatched metadata when invoked directly.

### Phase 2.0: Enforcement Logic (4-5 hours)

- Compute payload security level in `ArtifactPipeline.execute()` and enforce clearance gate.
- Ensure metadata is present; otherwise raise fail-loud error instructing caller to supply classification.

### Phase 3.0: Sink Updates & Docs (3-5 hours)

- Update sinks to use helper API and propagate security level to produced artifacts.
- Document behaviour in protocols and developer docs.
- Run full test suite.
