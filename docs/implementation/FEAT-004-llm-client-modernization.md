# FEAT-004: LLM Client Modernization & Security Alignment

**Priority**: P1 (HIGH)
**Effort**: 12-18 hours (3 working days)
**Sprint**: Sprint 6 / Post-Security Audit
**Status**: PLANNED
**Completed**: N/A
**Depends On**: ADR-002, ADR-002-A, ADR-002-B, ADR-005, VULN-007, VULN-008
**Pre-1.0**: Breaking changes acceptable
**GitHub Issue**: #0

**Implementation Note**: Align LLM client implementations with the hardened plugin patterns introduced in Sprints 1-3 (immutable security policy, effective-level awareness, secure data handling).

---

## Problem Description / Context

### FEAT-004: LLM Client Modernization

**Problem Statement**:
Current LLM client implementations predate the secure plugin overhauls. They return ad-hoc dictionaries, ignore the pipeline operating level, and rely on downstream code to attach security metadata. This creates inconsistent behaviour relative to datasources/sinks and makes it difficult to audit downgrade paths.

**Motivation**:
- Enforce ADR-002/ADR-005 expectations that plugins honour the computed operating level (trusted downgrade only when allowed).
- Ensure LLM outputs are security-tagged at creation time rather than relying on downstream patch-ups (`src/elspeth/core/experiments/runner.py:1078-1080`).
- Reduce tech debt by introducing typed responses and `SecureDataFrame` integration for bulk LLM outputs (table-oriented models and retries).

**Use Case**:
```python
response = llm.generate_with_context(prompt, metadata)
assert response.security_level <= llm.get_effective_level()
secure_frame = response.to_secure_dataframe()  # Optional helper for downstream sinks
```

**Related ADRs**: ADR-002, ADR-002-A, ADR-002-B, ADR-004, ADR-005, ADR-013

**Status**: ADRs implemented, LLM clients lagging behind hardened pattern.

---

## Current State Analysis

### Existing Implementation

**What Exists**:
```python
# src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:106-135
return {
    "content": content,
    "raw": response,
    "metadata": metadata or {},
}
```

```python
# src/elspeth/core/experiments/runner.py:1078-1080
if self._active_security_level:
    record["security_level"] = self._active_security_level
```

**Problems**:
1. LLM clients never call `get_effective_level()` (confirmed by `rg get_effective_level src/elspeth/plugins/nodes/transforms/llm`), so trusted downgrade is purely contractual.
2. Responses are untyped dictionaries without embedded security metadata; downstream code patches records post hoc.
3. No helper to emit `SecureDataFrame` for multi-row LLM outputs (streaming/batch responses), unlike datasource/container model in ADR-002-A.
4. Middleware/registry coupling still uses legacy helpers (`create_llm_from_definition`) with bespoke payload munging.

### What's Missing

1. **LLMResponse object** – Typed response carrying `content`, `metadata`, `security_level`, and conversion helpers.
2. **Effective-level enforcement** – Clients must query `get_effective_level()` and adjust behaviour/logging when operating below declared clearance.
3. **SecureDataFrame utilities** – Optional helper to materialize LLM outputs into `SecureDataFrame` with uplift semantics for downstream processors.
4. **Registry simplification** – Move shared validation and `determinism_level` handling into `BasePluginFactory`, eliminate bespoke logic in `create_llm_from_definition`.

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/base/protocols.py` (UPDATE) – Introduce `LLMResponse` dataclass / protocol.
- `src/elspeth/core/experiments/runner.py` (UPDATE) – Consume typed responses, remove manual security tagging.

**Plugin Implementations** (4 files):
- `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py` (UPDATE)
- `src/elspeth/plugins/nodes/transforms/llm/openai_http.py` (UPDATE)
- `src/elspeth/plugins/nodes/transforms/llm/mock.py` (UPDATE)
- `src/elspeth/plugins/nodes/transforms/llm/static.py` (UPDATE)

**Registry & Middleware**:
- `src/elspeth/core/registries/llm.py` (UPDATE)
- `src/elspeth/plugins/nodes/transforms/llm/middleware/*.py` (UPDATE as needed for typed response access)

**Tests** (5 files):
- `tests/core/llm/test_llm_response.py` (NEW)
- `tests/core/registries/test_llm_registry.py` (UPDATE)
- `tests/plugins/llm/test_azure_openai_client.py` (NEW/UPDATE)
- `tests/plugins/llm/test_http_openai_client.py` (UPDATE)
- `tests/integration/test_experiment_runner_llm_security.py` (NEW) – ensures downgrade enforcement.

---

## Target Architecture / Design

### Design Overview

```
LLMClient.generate() -> LLMResponse
  ├─ security_level = self.get_effective_level()
  ├─ metadata.security_level recorded immediately
  └─ to_secure_dataframe() -> SecureDataFrame.with_uplifted_security_level(...)
```

**Key Design Decisions**:
1. **Typed response**: Replace bare dict with `LLMResponse` dataclass providing convenience helpers and explicit security tagging.
2. **Effective-level hook**: Clients must call `get_effective_level()` and log downgrade operations (via plugin logger or telemetry hook per ADR-013).
3. **Opt-in SecureDataFrame**: Provide helper for sinks/aggregators needing tabular outputs while respecting ADR-002-A uplift semantics.
4. **Registry cleanup**: Delegate determinism/security handling to `BasePluginFactory`, keeping registry logic declarative.

### API Design

```python
response = llm.generate(
    system_prompt=system_text,
    user_prompt=user_text,
    metadata={"row_id": row_id},
)

assert isinstance(response, LLMResponse)
assert response.security_level == llm.get_effective_level()

secure_df = response.to_secure_dataframe(columns=["content", "metrics.score"])
# secure_df.security_level == response.security_level
```

### Security Properties

| Threat | Defense Layer | Status |
|--------|---------------|--------|
| **T1: Downgrade misuse** | Mandatory `get_effective_level()` enforcement + telemetry | PLANNED |
| **T2: Unclassified outputs** | LLMResponse security metadata | PLANNED |
| **T3: Data laundering via custom clients** | Registry enforcement + typed response | PLANNED |

---

## Design Decisions

### 1. Response Typing Strategy

**Options**:
- **Option A**: Dataclass with helper methods (Chosen) – clear contract, minimal overhead.
- **Option B**: NamedTuple – immutable but less extensible.
- **Option C**: Keep dicts – perpetuates debt (Rejected).

### 2. SecureDataFrame Integration

**Decision**: Provide optional helper that constructs `SecureDataFrame` using `with_new_data()` + uplift semantics so downstream plugins opt in without forcing DataFrame usage.

### 3. Downgrade Telemetry

**Decision**: Emit plugin logger events when `self.get_effective_level() < self.get_security_level()` so audits can trace trusted downgrades.

---

## Implementation Phases (TDD)

### Phase 1.0: Core Types & Tests (4-5 hours)

- Introduce `LLMResponse` dataclass with `.content`, `.raw`, `.metadata`, `.security_level`, `.to_dict()`, `.to_secure_dataframe()`.
- Update unit tests asserting typed response and security metadata.

### Phase 2.0: Client Refactor (5-6 hours)

- Update all LLM client implementations to use `LLMResponse`.
- Ensure each client retrieves `effective_level = self.get_effective_level()` and includes downgrade telemetry via plugin logger.

### Phase 3.0: Runner & Registry Integration (3-4 hours)

- Modify `ExperimentRunner` to consume `LLMResponse`, remove manual security tagging.
- Simplify `llm_registry` factory to leverage updated `BasePluginFactory` contracts.
- Update middleware to operate on typed responses.

### Phase 4.0: Regression & Docs (1-3 hours)

- Extend integration tests for downgrade scenarios.
- Document new API usage in developer docs (LLM plugin guide).
- Run full test suite.

**Testing**: Execute targeted unit tests + `pytest tests/core tests/plugins tests/integration`.
