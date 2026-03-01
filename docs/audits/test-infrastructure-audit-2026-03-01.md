# Test Infrastructure Audit — 2026-03-01

## Executive Summary

**Problem:** Tests create their own mocks, landscape databases, plugin contexts, and plugin classes instead of using the existing factory/fixture infrastructure. This causes tests to break whenever production code changes, because each test has its own brittle coupling to internal APIs.

**Scale:** ~900+ violations across ~120+ files out of 499 total test files.

**Root cause:** The factory infrastructure (`make_context()`, `make_operation_context()`, `ListSource`, `CollectSink`, etc.) exists and is well-designed, but was not adopted consistently during the test suite v2 migration.

**Triggering incident:** `test_resume_validate_then_write_succeeds` was constructing `PluginContext(...)` directly with a fabricated `operation_id`, bypassing the FK chain required by the Landscape database. A single production change to enforce FK constraints broke it. Using `make_operation_context()` would have prevented this entirely.

---

## Available Infrastructure (What Tests SHOULD Use)

| Factory/Fixture | Location | Purpose |
|---|---|---|
| `make_context()` | `tests/fixtures/factories.py` | PluginContext with Mock landscape (most common need) |
| `make_source_context()` | `tests/fixtures/factories.py` | PluginContext with real landscape + FK chain (run→node) |
| `make_operation_context()` | `tests/fixtures/factories.py` | Full FK chain (run→node→operation) for `record_call()` |
| `make_landscape_db()` | `tests/fixtures/landscape.py` | `LandscapeDB.in_memory()` wrapper |
| `make_recorder()` | `tests/fixtures/landscape.py` | `LandscapeRecorder` factory |
| `landscape_db` fixture | `tests/fixtures/landscape.py` | Pytest fixture for LandscapeDB |
| `recorder` fixture | `tests/fixtures/landscape.py` | Pytest fixture for LandscapeRecorder |
| `MockPayloadStore` | `tests/fixtures/stores.py` | In-memory PayloadStore |
| `MockClock` | `tests/fixtures/stores.py` | Deterministic clock |
| `ListSource` | `tests/fixtures/plugins.py` | Source from list |
| `CollectSink` | `tests/fixtures/plugins.py` | Sink that collects results |
| `PassTransform` | `tests/fixtures/plugins.py` | Identity transform |
| `FailTransform` | `tests/fixtures/plugins.py` | Always-error transform |
| `ConditionalErrorTransform` | `tests/fixtures/plugins.py` | Error on truthy `fail` key |
| `CountingTransform` | `tests/fixtures/plugins.py` | Counts invocations |
| `ErrorOnNthTransform` | `tests/fixtures/plugins.py` | Error on Nth call |
| `build_linear_pipeline()` | `tests/fixtures/pipeline.py` | Production-path pipeline builder |
| `build_fork_pipeline()` | `tests/fixtures/pipeline.py` | Fork/join pipeline builder |
| `wire_transforms()` | `tests/fixtures/factories.py` | WiredTransform list builder |
| `create_observed_contract()` | `tests/fixtures/base_classes.py` | SchemaContract from row dict |

---

## Findings by Category

### Category A: Direct `PluginContext(...)` Construction (359 occurrences across 60 files)

Tests that call `PluginContext(run_id=..., config={}, landscape=...)` directly instead of `make_context()`, `make_source_context()`, or `make_operation_context()`.

**Severity: HIGH** — This is the exact pattern that caused the triggering incident.

| Directory | Files | Occurrences | Key Offenders |
|---|---|---|---|
| `unit/plugins/` | 25+ files | ~160 | `test_openrouter.py` (54), `test_azure.py` (21), `test_batching/test_batch_transform_mixin.py` (14), `test_azure_multi_query.py` (13), `test_sink_display_headers.py` (10), `test_azure_multi_query_retry.py` (10) |
| `unit/engine/` | 5 files | ~65 | `test_processor.py` (52 alone), `test_batch_token_identity.py` (3) |
| `unit/core/` | 1 file | 10 | `test_validation_error_noncanonical.py` |
| `unit/contracts/` | 7 files | ~30 | `test_csv_sink_contract.py` (11), `test_csv_source_contract.py` (7) |
| `unit/regression/` | 1 file | 5 | `test_phase8_sweep_d_validation.py` |
| `integration/` | 8 files | ~30 | `test_error_persistence.py` (7), `test_retry.py` (3), `test_fixes.py` (2), `test_rate_limit/test_integration.py` (3) |
| `performance/` | 2 files | ~23 | `test_llm_retry.py` (22), `conftest.py` (1) |
| `property/` | 2 files | ~22 | `test_operations_properties.py` (20), `test_csv_sink_properties.py` (2) |

**Legitimate exclusions (tests that test PluginContext itself):**

- `tests/unit/plugins/test_context.py` (35 occurrences) — tests PluginContext behavior directly
- `tests/unit/contracts/test_context_protocols.py` (2 occurrences) — tests protocol compliance
- `tests/fixtures/factories.py` (3 occurrences) — factory implementations

These files should NOT be refactored to use factories — direct construction is the system under test or the factory itself.

#### PluginContext Field Usage Analysis

Before bulk-replacing `PluginContext(...)` with `make_context()`, we must verify that `make_context()` exposes all fields tests actually need. Analysis of the 8 highest-volume files:

| Field | make_context() has it? | Files using it | Occurrences |
|---|---|---|---|
| `run_id` | Yes | 7 | 173 |
| `config` | Yes | 7 | 173 |
| `landscape` | Yes | 7 | 172 |
| `state_id` | Yes | 2 | 30 |
| `token` | Yes | 2 | 29 |
| **`node_id`** | **No** | 1 | 10 |
| **`operation_id`** | **No** (but `make_operation_context()` covers this) | 1 | 8 |

**Finding:** `make_context()` covers ~95% of violations as-is. The remaining ~5% need `node_id` support. The fix is to extend `make_context()` with `node_id: str | None = None` (see Prerequisite P0.5 below), not to create a new factory.

**Fix:** Replace with `make_context()` (mock landscape) or `make_context(landscape=recorder)` (real recorder). For tests needing `node_id`, use the extended `make_context(node_id="source")`.

### Category B: Inline `LandscapeDB.in_memory()` + `LandscapeRecorder(...)` (550 occurrences across 105 files)

Tests that construct the landscape stack inline instead of using `make_landscape_db()`, `make_recorder()`, or the shared pytest fixtures. This category covers both `LandscapeDB.in_memory()` (550 occurrences across 105 files, excluding `tests/fixtures/`) and companion `LandscapeRecorder(db)` calls (478 across 98 files, excluding `tests/fixtures/`), which are nearly always co-located.

**Severity: MEDIUM-HIGH** — Duplicates 3-4 lines of setup that break if LandscapeDB/LandscapeRecorder constructors change.

| Directory | Files | `in_memory()` | `Recorder(...)` | Notes |
|---|---|---|---|---|
| `unit/plugins/` | 22 files | ~45 | ~45 | Co-located with Category A violations |
| `unit/engine/` | 7 files | ~35 | ~30 | `test_tokens.py` (21 alone!) |
| `unit/core/landscape/` | 13 files | ~65 | ~65 | Landscape subsystem tests |
| `unit/core/` (other) | 3 files | 6 | — | `test_token_outcomes.py`, `test_explicit_sink_routing_safeguards.py`, `test_config_alignment.py` |
| `unit/contracts/` | 4 files | ~20 | ~20 | `test_csv_sink_contract.py` (11), `test_csv_source_contract.py` (7) |
| `unit/mcp/` | 1 file | 6 | 6 | `test_diagnostics.py` |
| `integration/audit/` | 16 files | ~152 | ~152 | **Worst cluster** — every `test_recorder_*.py` file (tokens: 23, contracts: 18, runs: 14, nodes: 14, node_states: 14, batches: 12). **Note:** requires scoping pass before migration (see P2 prerequisite) |
| `integration/pipeline/` | 10+ files | ~55 | ~20 | `test_quarantine_routing.py` (13), `test_t18_characterization.py` (11), orchestrator tests |
| `e2e/` | 8 files | ~15 | ~15 | Pipeline + recovery tests |
| `performance/` | 8 files | ~16 | ~6 | Benchmarks + scalability |
| `property/` | 12 files | ~108 | ~58 | Hypothesis `@given` (see note below) |

**Tier-level breakdown:**

| Tier | `in_memory()` occurrences | Files |
|---|---|---|
| `tests/unit/` | 206 | 55 |
| `tests/integration/` | 220 | 28 |
| `tests/property/` | 108 | 13 |
| `tests/performance/` | 16 | 9 |

#### Common Setup Pattern (80%+ of violations)

Analysis of 451 `begin_run()` and 500 `register_node()` calls reveals a dominant pattern:

```python
# The 80% pattern — identical across most tests
db = LandscapeDB.in_memory()
recorder = LandscapeRecorder(db)
run = recorder.begin_run(config={}, canonical_version="v1")
source = recorder.register_node(
    run_id=run.run_id,
    plugin_name="source",
    node_type=NodeType.SOURCE,
    plugin_version="1.0",
    config={},
    schema_config=DYNAMIC_SCHEMA,
)
# Tests then use: db, recorder, run.run_id, source.node_id
```

Parameters are effectively constant: `config={}`, `canonical_version="v1"`, `plugin_version="1.0"`, `schema_config=DYNAMIC_SCHEMA`. The only variation is `plugin_name` and whether `node_id` is explicit (for deterministic tests) or auto-generated.

**Variant patterns (the 20%):**
- **Multi-node:** Register 2-5 additional nodes (aggregation, transform, coalesce, sink) — same `run_id`
- **With rows/tokens:** After register_node, call `create_row()` + `create_token()` — mainly integration/audit tests
- **Helper factories:** `_make_recorder()` in `test_processor.py`, `_setup()` in 8 landscape test files

**Fix for integration/unit:** Use `landscape_db`/`recorder` fixtures or `make_landscape_db()`/`make_recorder()` for simple cases. Use the new `make_recorder_with_run()` factory (see F5 below) for the 80% pattern that needs run + source node.

**Fix for property:** While `@given` tests cannot receive pytest fixtures as parameters, they CAN call factory functions inside the test body:

```python
@given(st.integers())
def test_something(n):
    db = make_landscape_db()       # Works inside @given
    recorder = make_recorder(db)   # Works inside @given
```

Property tests should use `make_landscape_db()` / `make_recorder()` rather than inline `LandscapeDB.in_memory()` / `LandscapeRecorder(db)`. This doesn't reduce line count, but routes all construction through factories so constructor changes propagate automatically. Lower priority than unit/integration fixes.

### Category C: Inline Plugin Class Definitions (20 duplicate classes across 12 files)

Tests defining their own Source/Sink/Transform classes when `ListSource`, `CollectSink`, `PassTransform`, etc. would suffice.

**Severity: MEDIUM** — Creates drift between test infrastructure and production plugin protocols.

**Verified duplicates (behavioral equivalence confirmed):**

#### PassTransform duplicates (8 classes → 0 after fix)

| Inline Class | File | Lines | Differences from `PassTransform` |
|---|---|---|---|
| `IdentityTransform` | `test_orchestrator_core.py` | 82 | None — identical logic |
| `IdentityTransform` (×4) | `test_orchestrator_checkpointing.py` | 82, 137, 183, 415 | None — repeated 4 times |
| `PassthroughTransform` | `test_orchestrator_checkpointing.py` | 231 | None — identical logic, different name |
| `PassthroughTransform` (×3) | `test_completed_outcome_timing.py` | 133, 227, 306 | None — identical logic |
| `PassthroughTransform` | `test_telemetry_contracts.py` | 107 | Minor: PipelineRow type handling |
| `SimpleTransform` | `test_wiring.py` (telemetry) | 80 | None — identical logic |
| `IdentityTransform` | `test_explicit_sink_routing.py` | 40 | None — identical logic |

#### ListSource duplicates (3 replaceable, 1 special case)

| Inline Class | File | Lines | Differences from `ListSource` |
|---|---|---|---|
| `SimpleSource` | `test_concurrency.py` | 231 | None — identical interface |
| `SimpleSource` | `test_wiring.py` (telemetry) | 64 | None — identical |
| `SimpleSource` | `test_telemetry_contracts.py` | 73 | None — identical |
| `ListSource` | `test_base.py` | 260 | **Different:** reads from `config["data"]` — keep as-is |

#### CollectSink duplicates (5 replaceable)

| Inline Class | File | Lines | Differences from `CollectSink` |
|---|---|---|---|
| `SimpleSink` | `test_concurrency.py` | 244 | Attribute named `written` instead of `results` |
| `SimpleSink` | `test_wiring.py` (telemetry) | 93 | None — identical |
| `SimpleSink` | `test_telemetry_contracts.py` | 89 | None — identical |
| `CollectingSink` | `test_aggregation_checkpoint_bug.py` | 91 | None — identical |
| `MemorySink` | `test_integration.py` | 69 | Attribute named `rows` instead of `results` |

#### Classes needing new fixtures (no existing equivalent)

| Inline Class | File | Lines | Behavior | Proposed Fixture |
|---|---|---|---|---|
| `FailingSink` (×3) | `test_completed_outcome_timing.py` | — | `write()` raises RuntimeError | F2 |
| `FailingSource` | `test_orchestrator_cleanup.py`, `test_export_partial_semantics.py` | — | `load()` raises RuntimeError | F3 |
| `FlakyTransform` | `test_retry.py` | 51 | Fails N times then succeeds | DEFERRED (1 occurrence, below threshold) |

**Excluded from count (legitimate test infrastructure, NOT duplicates):**
- Schema classes (`PluginSchema` subclasses like `SourceOutput`, `SinkInput`) — test schema validation
- Protocol test base classes (`SourceContractTestBase`, `SinkContractTestBase`) — test infrastructure
- Plugin discovery classes (`SourceOne`, `SourceTwo`) — test pluggy registration
- Behavioral test transforms (`DoubleTransform`, `AddOneTransform`, `ExpandingTransform`) — test-specific logic that fixtures cannot generalize

### Category D: Local Mock Context Helpers (6 definitions, 20+ downstream calls)

Tests defining their own `make_mock_context()` / `make_plugin_context()` helper instead of importing `make_context()` from `tests/fixtures/factories.py`.

**Severity: LOW-MEDIUM** — The `make_context()` factory already does exactly what these helpers do.

**Helper definitions found:**

| File | Function | Downstream Calls | Notes |
|---|---|---|---|
| `tests/unit/plugins/llm/conftest.py` | `make_plugin_context()` | Imported by LLM tests | **Functionally identical to `make_context()`** |
| `tests/performance/stress/conftest.py` | `make_plugin_context()` | Imported by stress tests | Same pattern |
| `tests/unit/plugins/transforms/test_keyword_filter.py` | `make_mock_context()` | 20 calls within file | Same pattern |
| `tests/unit/plugins/transforms/azure/test_content_safety.py` | `make_mock_context()` | Within file | Same pattern |
| `tests/unit/plugins/transforms/azure/test_prompt_shield.py` | `make_mock_context()` | Within file | Duplicate of content_safety |
| `tests/unit/plugins/llm/test_openrouter_multi_query.py` | Local helper | Within file | Duplicate of conftest |

**Why these are redundant:** The conftest `make_plugin_context()` (lines 39-53) constructs `PluginContext(run_id="run-123", landscape=mock, state_id=state_id, config={}, token=token)` — identical to `make_context(state_id=state_id, token=token)`.

**Fix:** Delete all 6 helper definitions. Replace calls with `from tests.fixtures.factories import make_context`.

### Category E: Manual `ExecutionGraph()` in Integration/E2E (HIGH SEVERITY) - FIXED

Tests that bypass `ExecutionGraph.from_plugin_instances()` — the BUG-LINEAGE-01 prevention rule. These have been fixed.

**Non-exempt violations (must fix):**

1. `tests/integration/pipeline/orchestrator/test_graceful_shutdown.py:406-413` — `_setup_failed_run()` - FIXED
2. `tests/integration/plugins/sources/test_payload_storage.py:47-68` — `_build_simple_graph()` - FIXED
3. `tests/integration/pipeline/test_concurrency.py` — synthetic `DAGTraversalContext` - FIXED

**Documented exemptions (acceptable):**

- `test_topology_validation.py` — testing hashing algorithms specifically
- `test_recovery.py` — checkpoint tests need stable node IDs
- `test_aggregation_contracts.py` — testing DAG edge validation logic
- `test_resume_comprehensive.py` — checkpoint node ID matching
- Various e2e recovery tests — all carry inline documentation

---

## New Factories Needed

Based on repeated boilerplate (3+ occurrences), these new factories should be added.

**Note:** F1 from the original audit (`make_process_context`) has been **removed** — `make_context()` already accepts the same parameters (`state_id`, `token`, `landscape`, `run_id`, `config`). Instead, `make_context()` should be extended with `node_id` support (see below).

### Prerequisite: Extend `make_context()` with `node_id`

**Before any Category A remediation**, add `node_id` to `make_context()`:

```python
def make_context(
    *,
    run_id: str = "test-run",
    state_id: str = "state-123",
    token: Any | None = None,
    config: dict[str, Any] | None = None,
    landscape: Any | None = None,
    node_id: str | None = None,           # NEW — needed by 10 tests
) -> PluginContext:
```

This is a non-breaking additive change — all existing callers are unaffected.

### F2: `FailingSink` — Add to `tests/fixtures/plugins.py`

**Pattern:** Sink whose `write()` always raises `RuntimeError`.
**Currently duplicated in:** `test_completed_outcome_timing.py` (×3), `test_orchestrator_checkpointing.py`.
**Proposed:**

```python
class FailingSink(_TestSinkBase):
    name = "failing_sink"
    def write(self, rows, ctx):
        raise RuntimeError("Sink write failed")
```

### F3: `FailingSource` — Add to `tests/fixtures/plugins.py`

**Pattern:** Source whose `load()` always raises.
**Currently duplicated in:** `test_orchestrator_cleanup.py`, `test_export_partial_semantics.py`.
**Proposed:**

```python
class FailingSource(ListSource):
    name = "failing_source"
    def load(self, ctx):
        raise RuntimeError("Source failed intentionally")
```

### ~~F4: `FlakyTransform`~~ — DEFERRED

**Deferred from P0.5 scope.** Only 1 occurrence (`tests/integration/pipeline/test_retry.py`), which is below the 3+ duplication threshold for new fixtures. `ErrorOnNthTransform` already exists in `tests/fixtures/plugins.py` with similar semantics (errors on exactly call N). The semantic difference — `ErrorOnNthTransform` errors on exactly call N while `FlakyTransform` errors on calls 1 through N — is genuine but does not justify a new fixture with only 1 consumer. If retry testing creates more demand in future, revisit.

### F5: `make_recorder_with_run()` — Add to `tests/fixtures/landscape.py`

**Pattern:** `LandscapeDB.in_memory()` + `LandscapeRecorder(db)` + `begin_run()` + `register_node()`.
**Currently duplicated in:** `test_processor.py` (`_make_recorder()`), `test_tokens.py` (21 inline), `test_batch_token_identity.py` (3 inline), `test_plugin_detection.py`, and 8+ landscape test files with `_setup()` helpers. Covers the 80% setup pattern identified across 451 `begin_run()` calls.

**Distinction from `make_source_context()` / `make_operation_context()`:** Those factories return a `PluginContext` — the recorder and DB are internal and not accessible. `make_recorder_with_run()` returns a named result for tests that need to query the DB directly or call recorder methods beyond what PluginContext exposes.

**Proposed:**

```python
@dataclass(frozen=True, slots=True)
class RecorderSetup:
    db: LandscapeDB
    recorder: LandscapeRecorder
    run_id: str
    source_node_id: str


def make_recorder_with_run(
    *,
    run_id: str | None = None,
    source_node_id: str | None = None,
    source_plugin_name: str = "source",
) -> RecorderSetup:
    """Create LandscapeDB + Recorder + run + source node in one call.

    Covers the 80% setup pattern: db → recorder → begin_run → register_node(SOURCE).
    Tests needing additional nodes (transforms, sinks, aggregations) can call
    recorder.register_node() on the returned recorder.

    Args:
        run_id: Explicit run ID for deterministic tests. Auto-generated if None.
        source_node_id: Explicit source node ID. Auto-generated if None.
        source_plugin_name: Plugin name for the source node (default "source").
    """
```

**Design rationale:** The factory covers the common 4-step boilerplate but does NOT register transforms/gates/sinks — those are test-specific. Tests needing multi-node setups call `recorder.register_node()` on the returned recorder with the same `run_id`.

**Internal deduplication:** After `make_recorder_with_run()` is implemented, `make_source_context()` and `make_operation_context()` in `tests/fixtures/factories.py` should be refactored to delegate to it internally. Both currently duplicate the same 4-step boilerplate. Without this consolidation, a change to `begin_run()` or `register_node()` signatures would need updating in three factories independently — the exact class of breakage this audit exists to prevent.

**Companion helper for multi-node setup (the 20% pattern):**

```python
def register_test_node(
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str,
    *,
    node_type: NodeType = NodeType.TRANSFORM,
    plugin_name: str = "transform",
) -> str:
    """Register an additional test node with sensible defaults.

    Defaults plugin_version="1.0", config={}, schema_config=DYNAMIC_SCHEMA.
    Returns the node_id for convenience.
    """
```

This completes the solution for the 20% variant pattern where tests need 2-5 additional nodes after `make_recorder_with_run()` creates the source.

### F6: `run_audit_pipeline()` — Add to `tests/fixtures/pipeline.py`

**Pattern:** Full pipeline execution with file-based SQLite + payload store, returning named fields for audit verification.
**Currently duplicated in:** 4 e2e audit test files (`test_full_lineage.py`, `test_attributability.py`, `test_export_reimport.py`, `test_purge_integrity.py`). All 4 share an identical `_run_pipeline()` helper returning `tuple[str, LandscapeDB, FilesystemPayloadStore, CollectSink]`.

**Distinction from `make_recorder_with_run()` (F5):** F5 creates an in-memory DB for unit/integration tests. F6 creates a file-based SQLite DB at `tmp_path/audit.db` with a real `FilesystemPayloadStore`, then actually executes the pipeline via `Orchestrator.run()`. F6 is the e2e audit factory; F5 is the unit/integration setup factory.

**Proposed:**

```python
@dataclass(frozen=True, slots=True)
class AuditPipelineResult:
    """Result from run_audit_pipeline() for e2e audit verification."""

    run_id: str
    db: LandscapeDB
    payload_store: FilesystemPayloadStore
    sink: CollectSink


def run_audit_pipeline(
    tmp_path: Path,
    source_data: list[dict[str, Any]],
    transforms: list[Any] | None = None,
) -> AuditPipelineResult:
    """Execute a linear pipeline with file-based audit trail for e2e verification.

    Creates a file-based SQLite DB (not in-memory) and FilesystemPayloadStore,
    builds a production-path pipeline via build_linear_pipeline(), runs it via
    Orchestrator.run(), and asserts RunStatus.COMPLETED.

    For tests that need the pipeline to fail, call build_linear_pipeline() and
    Orchestrator directly — this factory is for the success path only.

    Args:
        tmp_path: Pytest tmp_path fixture for DB and payload files.
        source_data: Rows to feed through the pipeline.
        transforms: Optional transforms (default: [PassTransform()]).

    Returns:
        AuditPipelineResult with run_id, db, payload_store, and sink.
    """
```

**Design rationale:** The 4 existing `_run_pipeline()` helpers are functionally identical: create file-based DB, create payload store, call `build_linear_pipeline()`, build `PipelineConfig`, run via `Orchestrator`, assert completion, return the 4-tuple. The factory eliminates the bare tuple return (which requires positional indexing) in favor of named fields via `AuditPipelineResult`.

### F7: `create_observed_contract()` — Already exists but underused

**Pattern:** `SchemaContract(mode="OBSERVED", fields=(...), locked=True)` from a row dict.
**Already in:** `tests/fixtures/base_classes.py` as `create_observed_contract(row)`.
**Duplicated in:** `test_aggregation_recovery.py`, `test_durability.py` (both define their own `_make_contract()`). Note: `test_payload_storage.py` was previously duplicated but has already been fixed to import from `tests.fixtures.base_classes`.

---

## Priority Order for Remediation

### P0 — Critical (BUG-LINEAGE-01 violations) — DONE

3 non-exempt `ExecutionGraph()` manual constructions in integration tests. All fixed.

### P0.5 — Prerequisite (Create factories before bulk remediation)

Create all new factories (F2, F3, F5–F7), extend `make_context()` with `node_id`, add factory smoke tests, and refactor existing factories to delegate to `make_recorder_with_run()`. This is a small PR (~200 lines of new factory code + ~50 lines of factory tests) that unblocks all downstream work.

Without this step, P1 remediation will stall on the ~10 tests that need `node_id` and the Category C deduplication will have nowhere to point.

**Scope:**
1. Extend `make_context()` with `node_id` parameter
2. Add `FailingSink`, `FailingSource` to `tests/fixtures/plugins.py`
3. Add `RecorderSetup` dataclass (frozen), `make_recorder_with_run()`, and `register_test_node()` to `tests/fixtures/landscape.py`
4. Add `AuditPipelineResult` dataclass and `run_audit_pipeline()` to `tests/fixtures/pipeline.py`
5. Refactor `make_source_context()` and `make_operation_context()` to delegate to `make_recorder_with_run()` internally
6. Add `tests/fixtures/test_factories.py` — smoke tests for every new factory (see Factory Testing below)

**Factory Testing (`tests/fixtures/test_factories.py`):**

Factory smoke tests MUST be created before any migration begins. A bug in a centralized factory would silently corrupt every downstream test, producing hundreds of failures with no signal about the root cause. Each factory needs:

- `make_context(node_id="x")` — verify `node_id` passes through to PluginContext
- `make_recorder_with_run()` — verify: (a) returned `run_id` matches what's in the DB, (b) `source_node_id` is registered in the DB, (c) calling `recorder.register_node()` on the returned recorder succeeds
- `register_test_node()` — verify registered node exists in DB
- `FailingSink.write()` — verify it raises `RuntimeError`
- `FailingSource.load()` — verify it raises `RuntimeError`
- `run_audit_pipeline()` — verify it returns a completed run with rows in the sink

### P1 — High (FK chain violations like the triggering incident)

359 direct `PluginContext(...)` constructions across 60 files. Any of these could break on the next production change to PluginContext, LandscapeRecorder, or the FK schema.

**Also includes Category D:** Delete 6 local `make_mock_context()`/`make_plugin_context()` helpers and replace all call sites with `make_context()`.

### P2 — Medium-High (Inline landscape setup in non-property tests)

~442 inline `LandscapeDB.in_memory()` + `LandscapeRecorder(...)` constructions across ~92 non-property files (550 total minus ~108 property occurrences).

**Prerequisite — `integration/audit/` scoping pass:** Before migrating the `integration/audit/test_recorder_*.py` cluster (~152 occurrences across 16 files), audit each file and split into:

- **(a) Tests where inline construction is the subject under test (EXEMPT).** In recorder tests like `test_recorder_tokens.py`, the explicit `db = LandscapeDB.in_memory(); recorder = LandscapeRecorder(db)` construction IS the test setup for testing recorder behavior. Replacing it with `make_recorder_with_run()` would obscure what the test is testing and mask recorder bugs. These should remain verbose and be added to the CI enforcement allowlist with justification.
- **(b) Tests where it is pure boilerplate (MIGRATE).** Recorder tests where the setup is incidental (e.g., creating a recorder just to have a landscape for an unrelated assertion) should use the factory.

This distinction does not apply to other P2 clusters (`unit/plugins/`, `unit/engine/`, etc.) where the landscape is always a dependency, never the system under test.

### P3 — Medium (Inline plugin class deduplication)

Mechanically replace inline plugin class definitions with imports from `tests/fixtures/plugins.py`:
- 8 PassTransform duplicates → `from tests.fixtures.plugins import PassTransform`
- 3 ListSource duplicates → `from tests.fixtures.plugins import ListSource`
- 5 CollectSink duplicates → `from tests.fixtures.plugins import CollectSink`
- 2 classes using new fixtures (FailingSink, FailingSource)

### P4 — Low (Property test `@given` setup)

~108 `LandscapeDB.in_memory()` + ~58 `LandscapeRecorder(...)` constructions in property tests (13 files). Use `make_landscape_db()` / `make_recorder()` factory calls instead of direct construction. Lower priority because these are less likely to break (simpler setup patterns) and the fix is purely routing through factories, not reducing code.

---

## Migration Strategy

### Recommended Approach: Directory-at-a-Time

For ~900 violations, manual file-by-file editing is impractical. The recommended approach:

1. **Phase by directory, starting with highest-density clusters:**
   - `unit/plugins/llm/` (54 + 21 + 14 + 13 + 10 = 112 occurrences) — do first
   - `unit/engine/test_processor.py` (52 occurrences, single file) — second
   - `integration/audit/test_recorder_*.py` (~152 occurrences, 16 files) — third, **after** the scoping pass (see P2 prerequisite)
   - Remaining directories in descending occurrence count

2. **Each directory is one PR** to keep diffs reviewable (typically 200–800 lines of diff per directory). PRs must be sequential, not parallel — conftest files span directories and concurrent modification causes merge conflicts.

3. **Mechanical replacement pattern** for ~80% of violations:

   ```python
   # BEFORE (Category A)
   ctx = PluginContext(run_id="test-run", config={}, landscape=Mock())

   # AFTER
   ctx = make_context()
   ```

   ```python
   # BEFORE (Category B)
   db = LandscapeDB.in_memory()
   recorder = LandscapeRecorder(db)
   run = recorder.begin_run(config={}, canonical_version="v1")

   # AFTER
   setup = make_recorder_with_run()
   db, recorder, run_id = setup.db, setup.recorder, setup.run_id
   ```

4. **Validate each PR** before merging:
   - `.venv/bin/python -m pytest tests/` — 0 failures (xfails allowed)
   - `.venv/bin/python -m mypy src/` — no new errors
   - `.venv/bin/python -m ruff check src/` — clean

### What NOT to Automate

- Tests where `PluginContext` is constructed with unusual field combinations (manual review needed — see decision checklist below)
- Tests where the inline plugin class has behavioral differences from the fixture (noted in Category C tables)
- Category D helpers in conftest files (deletion requires verifying all importers)
- Performance tests (`tests/performance/`) that use `Mock()` landscape — these intentionally avoid real DB overhead to measure plugin/transform speed. Migrating to `make_recorder_with_run()` would introduce SQLite I/O into benchmarks, changing what they measure. These should be added to the CI enforcement allowlist.

**Category D atomic PR constraint:** The deletion of a conftest helper and ALL of its call-site replacements MUST be in a single PR. `tests/unit/plugins/llm/conftest.py:make_plugin_context()` is imported by files across `tests/unit/plugins/llm/` — deleting the definition before all importers are updated breaks test collection for the entire LLM test cluster.

**Decision checklist for Category A manual review:**

When migrating a `PluginContext(...)` call, check:
1. Does the test assert on a specific `run_id` value (e.g., `assert ctx.run_id == "specific-id"`)? → Keep explicit `run_id` via `make_context(run_id="specific-id")`
2. Does the test pass `ctx` to production code that reads `ctx.node_id`? → Use `make_context(node_id="...")`
3. Does the test assert on error messages containing `ctx.run_id`? → Keep explicit `run_id` to avoid breaking message assertions
4. Does the test use `ctx.landscape` for direct DB queries after pipeline execution? → Use `make_source_context()` or `make_operation_context()` (real recorder, not mock)

---

## Regression Prevention

After remediation, new violations must be prevented from being introduced. The following measures should be added:

1. **AST-based CI enforcement.** Add a lightweight Python script at `scripts/cicd/enforce_test_factories.py`, modeled on the existing `enforce_tier_model.py`. The script should:
   - Walk `tests/**/*.py` with Python `ast`
   - Detect `PluginContext(` call nodes (not string/comment matches — grep has false positives)
   - Detect `LandscapeDB.in_memory()` and `LandscapeRecorder(` call nodes outside `tests/fixtures/`
   - Detect inline plugin class definitions that duplicate existing fixtures (Category C)
   - Support an explicit allowlist of `(file, function/class)` pairs for legitimate direct construction
   - Fail if any non-allowlisted match is found

   **Why AST over grep:** The project already uses AST-based enforcement for the tier model (`enforce_tier_model.py`). Grep-based checks have known failure modes: false positives from comments/strings/docstrings, no per-site allowlist mechanism (only whole-file exclusion), and false negatives via import aliasing (`from ... import PluginContext as PC`). An AST walker is ~100-150 lines and provides the same allowlist expressiveness as `enforce_tier_model.py`.

   **Initial allowlist entries:**
   - `tests/unit/plugins/test_context.py` — tests PluginContext behavior directly
   - `tests/unit/contracts/test_context_protocols.py` — tests protocol compliance
   - `tests/fixtures/factories.py` — factory implementations
   - `tests/fixtures/landscape.py` — factory implementations
   - `tests/fixtures/test_factories.py` — factory smoke tests
   - `tests/performance/` — benchmark tests that intentionally use Mock landscape
   - Exempt `integration/audit/test_recorder_*.py` entries identified during P2 scoping pass

2. **Convention documentation.** Add a `tests/fixtures/README.md` documenting which factory to use for each scenario:
   - "I need a PluginContext for a transform test" → `make_context()`
   - "I need a PluginContext that can record calls" → `make_operation_context()`
   - "I need a PluginContext for a source with validation errors" → `make_source_context()`
   - "I need a recorder + DB to query directly" → `make_recorder_with_run()`
   - "I need additional nodes after `make_recorder_with_run()`" → `register_test_node()`
   - "I need a full e2e pipeline with audit trail" → `run_audit_pipeline()`
   - "I need a test source/sink/transform" → use `tests/fixtures/plugins.py`

3. **Enforcement rollout timing.** The enforcement script should be deployed in two phases:
   - **During P1-P2 remediation:** Run in "audit mode" (`--audit`) — reports violations but does not fail CI. This allows migration PRs to land without fighting the ratchet.
   - **After P2 completes:** Switch to "enforce mode" (`--enforce`) — fails CI on any non-allowlisted violation. The switch must happen in the same PR as the final P2 remediation to prevent a gap where violations can be reintroduced.
   - This mirrors the rollout pattern used for `enforce_tier_model.py`.

---

## Metrics

| Metric | Count |
|---|---|
| Total test files audited | 499 |
| Files with violations | ~120+ |
| Category A (direct PluginContext) | 359 occurrences across 60 files |
| Category B (inline `in_memory()`, excl. fixtures) | 550 occurrences across 105 files |
| Category B (inline `Recorder(...)`, excl. fixtures) | 478 occurrences across 98 files |
| Category B — unit tier | 206 `in_memory()` / 193 `Recorder()` across 55/53 files |
| Category B — integration tier | 220 `in_memory()` / 204 `Recorder()` across 28/36 files |
| Category B — property tier | 108 `in_memory()` / 58 `Recorder()` across 13/6 files |
| Category B — performance tier | 16 `in_memory()` / 6 `Recorder()` across 9/3 files |
| Category C (inline plugin classes) | 20 verified duplicates across 12 files |
| Category D (local mock context helpers) | 6 definitions, 20+ downstream calls |
| Category E (manual ExecutionGraph) | 3 non-exempt (FIXED) |
| New factories to create | 5 (F2, F3, F5–F7) + `register_test_node()` + 1 `make_context()` extension |
| Factory smoke tests | `tests/fixtures/test_factories.py` — smoke tests for all new factories |
| Internal factory refactor | `make_source_context()` + `make_operation_context()` delegate to `make_recorder_with_run()` |
| Estimated lines of churn | 1,800–2,700 (replaced by factory calls) |

---

## Review Log

**2026-03-01 — 4-agent review (Reality, Architecture, Quality, Systems)**

Verdict: APPROVE WITH CONDITIONS. All conditions resolved in-document.

Changes made from review:

| # | Change | Source |
|---|--------|--------|
| B1 | F6 (`run_audit_pipeline`) fully specified: `AuditPipelineResult` dataclass, complete function signature, design rationale | Architecture + Quality |
| B2 | Factory smoke tests (`tests/fixtures/test_factories.py`) added to P0.5 scope | Quality + Systems |
| B3 | `RecorderSetup` changed to `@dataclass(frozen=True, slots=True)` | Architecture |
| B4 | CI enforcement rollout timing specified: audit mode during P1-P2, enforce mode after P2 | Systems + Quality |
| B5 | `integration/audit/` scoping pass added as P2 prerequisite — split exempt vs. migrate | Systems |
| W1 | CI grep checks replaced with AST-based enforcement (`enforce_test_factories.py`) | Architecture |
| W2 | F4 (`FlakyTransform`) deferred from P0.5 — below 3+ threshold, `ErrorOnNthTransform` may suffice | Architecture |
| W3 | Internal factory deduplication: `make_source_context`/`make_operation_context` delegate to `make_recorder_with_run` | Architecture |
| W4 | Performance tests exempted from landscape factory migration | Systems |
| W5 | `register_test_node()` helper added for 20% multi-node pattern | Architecture |
| W6 | Validation criteria specified: pytest + mypy + ruff per PR | Quality |
| I1 | `unit/core/landscape/` count corrected: ~65 across 13 files (was ~55 across 14) | Reality |
| I2 | `integration/audit/` count corrected: ~152 across 16 files (was ~165 across 15+) | Reality |
| I3 | F7 stale claim removed: `test_payload_storage.py` already imports from fixtures | Reality |
| — | Category D atomic PR constraint documented | Systems |
| — | Decision checklist for Category A manual review added | Quality |
| — | Migration ordering updated: `unit/plugins/llm/` first, `integration/audit/` third (after scoping) | Systems |
| — | PRs must be sequential (conftest conflict risk documented) | Architecture |

**2026-03-01 — Post-review: `populate_run()` deletion (Architecture finding)**

The 4-agent review identified `populate_run()` in `tests/fixtures/factories.py` as a BUG-LINEAGE-01-class violation: it bypassed `LandscapeRecorder` entirely, inserting directly into `runs_table`, `nodes_table`, `rows_table`, `tokens_table`, and `token_outcomes_table` via raw SQL. This is the same architectural anti-pattern (bypassing production code paths in test infrastructure) that this audit exists to prevent.

Investigation found `populate_run()` was **dead code** — zero callers across the entire test suite. The documentation (`docs/guides/test-system.md`) incorrectly claimed it had "many" users and listed it in `fixtures/landscape.py` (it was actually in `fixtures/factories.py`). The docs also referenced two non-existent companion functions (`populate_fork_run()`, `assert_lineage_complete()`).

**Actions taken:**

| # | Action | Files |
|---|--------|-------|
| 1 | Deleted `populate_run()` (119 lines of dead code with raw SQL inserts) | `tests/fixtures/factories.py` |
| 2 | Removed `populate_run()` definition from docs (92 lines), replaced with 2-line removal note | `docs/guides/test-system.md` |
| 3 | Removed references to non-existent `populate_fork_run()` and `assert_lineage_complete()` | `docs/guides/test-system.md` |
| 4 | Updated 3 remaining doc references (table row, tree diagram, description list) | `docs/guides/test-system.md` |
