# ELSPETH Architecture Analysis: Architect Handover

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Purpose:** Actionable remediation roadmap derived from the architecture analysis.
**Companion:** `04-final-report.md` (findings and evidence)

---

## How to Use This Document

This document is the primary deliverable. It contains:
1. A phased remediation roadmap (4 phases)
2. A numbered task list with dependencies, effort estimates, and specific file references
3. Decision points requiring human judgment
4. Success criteria for each phase

Tasks are ordered: **security first, then correctness, then architecture, then quality.**

Effort estimates use T-shirt sizes: **S** (< 2 hours), **M** (2-8 hours), **L** (1-3 days), **XL** (3-5 days).

---

## Phase 1: Quick Wins (1-2 days total)

Low-risk changes that deliver immediate value. No architectural restructuring. Each task is independently mergeable.

### Task 1: Freeze All 16 Audit Record Dataclasses

**Priority:** P1 (correctness) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** Add `frozen=True` to all 16 mutable dataclass definitions in `src/elspeth/contracts/audit.py`: `Run`, `Node`, `Edge`, `Row`, `Token`, `TokenParent`, `Call`, `Artifact`, `RoutingEvent`, `Batch`, `BatchMember`, `BatchOutput`, `Checkpoint`, `RowLineage`, `ValidationErrorRecord`, `TransformErrorRecord`. Note: newer types (NodeState variants, Operation, TokenOutcome, SecretResolution) are already frozen — do NOT modify these.

**How:**
1. Add `frozen=True` to each `@dataclass` decorator.
2. Find all sites that mutate these objects after construction. Use: `grep -rn 'record\.\w\+ =' src/elspeth/` filtering for assignment to attributes of these types.
3. Replace mutation with `dataclasses.replace()` for legitimate incremental construction.
4. Run full test suite. Failures indicate code paths that depend on post-creation mutation -- these are the sites that need `replace()`.

**Files:** `src/elspeth/contracts/audit.py` (primary), plus any files that mutate audit records after construction.

**Verification:** `mypy src/` passes. All tests pass. `grep -rn 'frozen=True' src/elspeth/contracts/audit.py | wc -l` returns 16.

---

### Task 2: Fix assert Statements in Production Code

**Priority:** P1 (correctness) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Replace 5 `assert` statements in production code with explicit `if not x: raise` patterns. Assert statements are stripped when Python runs with `-O` flag, silently removing safety checks.

**How:** Search for `assert` in `src/elspeth/plugins/transforms/`. Replace each with an explicit conditional raise:
```python
# Before
assert isinstance(result, dict), "Expected dict"

# After
if not isinstance(result, dict):
    raise TypeError("Expected dict")
```

**Files:** `src/elspeth/plugins/transforms/batch_replicate.py`, `src/elspeth/plugins/transforms/azure_content_safety.py`, `src/elspeth/plugins/transforms/azure_prompt_shield.py` (check each for `assert` usage).

**Verification:** `grep -rn '^[[:space:]]*assert ' src/elspeth/plugins/` returns 0 results.

---

### Task 3: Fix Truthiness Checks on Numeric Values

**Priority:** P2 (correctness) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Replace truthiness checks on numeric values with explicit `is not None` comparisons. Truthiness excludes `0` and `0.0`, which are valid numeric values.

**Known locations:**
- `src/elspeth/mcp/analyzers/reports.py`: `high_variance` filter uses `if n["avg_ms"] and n["max_ms"]` -- excludes nodes with zero average duration. Change to `if n["avg_ms"] is not None and n["max_ms"] is not None`.
- `src/elspeth/engine/spans.py`: `if node_id:` should be `if node_id is not None:` (empty string node_id is unlikely but zero-like values should not be excluded).
- `src/elspeth/tui/widgets/node_detail.py`: `status or "N/A"` treats empty string as missing.

**Verification:** Targeted test cases for zero-valued inputs at each fixed location.

---

### Task 4: Fix Silent Passphrase Resolution Failure

**Priority:** P2 (correctness) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** In the `explain` CLI command, settings loading failure during passphrase resolution is silently swallowed. If `--settings` was provided and loading fails, this should be fatal. If `--settings` was not provided, the fallthrough to `passphrase = None` is correct but should log a warning.

**File:** `src/elspeth/cli.py`, in the `explain` command function. Look for `except (ValidationError, SecretLoadError)` blocks near passphrase resolution.

**How:** Add conditional error handling:
```python
if settings_path:
    # User explicitly provided settings -- failure is fatal
    raise typer.Exit(1)
else:
    # No settings provided -- warn and continue without passphrase
    logger.warning("Could not load settings for passphrase resolution", error=str(e))
```

**Verification:** Test that `elspeth explain --settings bad.yaml --database good.db` exits with error, while `elspeth explain --database good.db` works without settings.

---

### Task 5: Fix diagnose() Quarantine Count Scope

**Priority:** P3 (quality) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** `diagnose()` counts quarantined rows across ALL historical runs, making the count permanently non-zero in databases with history. Scope to recent runs (last 24 hours or last 10 runs).

**File:** `src/elspeth/mcp/analyzers/diagnostics.py`, in `diagnose()`. The quarantine count query needs a `WHERE` clause filtering by recent `run_id` values or recent timestamps.

**Verification:** Run `diagnose()` on a database with old quarantined rows and verify the count reflects only recent activity.

---

### Task 6: Move ExpressionParser to core/

**Priority:** P2 (architecture) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Move `src/elspeth/engine/expression_parser.py` to `src/elspeth/core/expression_parser.py`. The expression parser is a pure validation utility with no engine dependencies. This breaks the core-to-engine dependency cycle.

**How:**
1. Move the file.
2. Update all imports: `grep -rn 'engine.expression_parser' src/` and `grep -rn 'engine\.expression_parser' src/`.
3. Update the `__init__.py` files for both `engine/` and `core/`.

**Verification:** `mypy src/` passes. All tests pass. No import of `engine.expression_parser` remains in `core/`.

---

### Task 7: Move MaxRetriesExceeded and BufferEntry to Contracts

**Priority:** P3 (architecture) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Fix two upward layer violations from contracts (L0):
- `MaxRetriesExceeded` is defined in `engine/retry.py` (L2) but imported by `contracts/results.py` (L0) — move to `contracts/errors.py`
- `BufferEntry` is defined in `plugins/pooling/reorder_buffer.py` (L3) but imported by `contracts/node_state_context.py` (L0) — move to `contracts/`

**Files:** Move `MaxRetriesExceeded` from `src/elspeth/engine/retry.py` to `src/elspeth/contracts/errors.py`. Move `BufferEntry` from `src/elspeth/plugins/pooling/reorder_buffer.py` to `src/elspeth/contracts/`. Update all imports.

**Verification:** `mypy src/` passes. All tests pass.

---

### Task 8: Remove Dead Code

**Priority:** P3 (quality) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Remove confirmed dead code:
- `TokenManager.payload_store` field (accepted but never used) -- `src/elspeth/engine/tokens.py`
- `BaseLLMTransform` class (zero production subclasses) -- `src/elspeth/plugins/llm/base.py`
- `CapacityError.retryable` field (accepted but never checked) -- `src/elspeth/plugins/pooling/`
- `RequestRecord` in `src/elspeth/testing/chaosllm/metrics.py` (defined but never used for insertion)

**Verification:** `mypy src/` passes. All tests pass. `grep -rn 'BaseLLMTransform' src/elspeth/plugins/` returns only deletion artifacts.

---

## Phase 2: Structural Fixes (3-5 days total)

Targeted refactoring that improves type safety and reduces duplication without changing external behavior.

### Task 9: Typed Dataclasses at Plugin Client Boundaries

**Priority:** P1 (correctness) | **Effort:** L | **Risk:** Medium | **Dependencies:** Task 1

**What:** Define frozen dataclasses for the untyped dict boundaries identified in Finding 2 of the final report. Follow the `TokenUsage` pattern (commit dffe74a6).

**New types to create in `src/elspeth/contracts/`:**

```python
@dataclass(frozen=True, slots=True)
class LLMResponseMeta:
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str
    response_id: str

@dataclass(frozen=True, slots=True)
class TransformOutcome:
    action: str
    reason: str
    details: dict[str, str]  # Bounded dict with string values only

@dataclass(frozen=True, slots=True)
class GateOutcome:
    decision: str
    expression: str
    matched_path: str | None
```

**How:**
1. Define types in `contracts/`.
2. Update `LLMClient.query()` to return `LLMResponseMeta` instead of `dict`.
3. Update `TransformExecutor` to construct `TransformOutcome` instead of ad-hoc dicts.
4. Change `GateResult.row` from `dict[str,Any]` to `PipelineRow` (matching `TransformResult`).
5. Update `LandscapeRecorder` methods to accept the new types, calling `.to_dict()` at the serialization boundary.

**Files:** `src/elspeth/contracts/` (new types), `src/elspeth/plugins/clients/` (LLM client), `src/elspeth/engine/executors/` (transform/gate executors), `src/elspeth/core/landscape/` (recorder methods).

**Verification:** `mypy src/` passes with no new `# type: ignore` additions. All 10 related Filigree bugs can be closed.

---

### Task 10: Consolidate LLM Plugin Shared Logic

**Priority:** P1 (correctness) | **Effort:** L | **Risk:** Medium | **Dependencies:** Task 8 (remove BaseLLMTransform first)

**What:** Extract ~1,330 lines of duplicated logic across 6 LLM transforms into composable utility functions.

**New file:** `src/elspeth/plugins/llm/shared.py`

**Extract these functions:**
- `validate_llm_response(response: dict) -> ValidatedLLMResponse` -- JSON parsing, type checking, required field validation. Apply consistently to all 6 transforms.
- `build_llm_output_row(row: PipelineRow, classification: dict, metadata: LLMResponseMeta) -> dict` -- Standard output schema construction.
- `reject_nan_infinity(value: float, field_name: str) -> float` -- NaN/Infinity rejection. Currently missing from `openrouter_batch.py`.
- `build_llm_success_reason(action: str, model: str, tokens: int) -> TransformOutcome` -- Consistent success reason structure.

**How:**
1. Create `shared.py` with the extracted functions.
2. Refactor each LLM transform to compose these utilities.
3. Add tests for each shared function.
4. Verify that `openrouter_batch.py` now rejects NaN/Infinity (it currently does not).

**Verification:** All LLM tests pass. New test cases for NaN/Infinity rejection in OpenRouter batch. Line count of `plugins/llm/` decreases by ~800.

---

### Task 11: Extract PluginBundle Dataclass for CLI

**Priority:** P2 (type safety) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** Replace the `dict[str, Any]` return from `instantiate_plugins_from_config()` with a frozen dataclass.

**File:** `src/elspeth/cli_helpers.py`

```python
@dataclass(frozen=True, slots=True)
class PluginBundle:
    source: SourceProtocol
    source_settings: SourceSettings
    transforms: list[WiredTransform]
    sinks: dict[str, SinkProtocol]
    aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]]
```

**How:**
1. Define `PluginBundle` in `cli_helpers.py`.
2. Update `instantiate_plugins_from_config()` to return `PluginBundle`.
3. Update all callers in `cli.py` to use attribute access instead of `plugins["source"]`.

**Verification:** `mypy src/` passes. No `plugins["..."]` magic string access remains in `cli.py`.

---

### Task 12: GateExecutor NodeStateGuard Adoption

**Priority:** P2 (consistency) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** `GateExecutor` manually calls `begin()` and `complete()` on node states while all other executors use `NodeStateGuard` context manager. Adopt `NodeStateGuard` for consistency and to guarantee terminal state recording even on exceptions.

**File:** `src/elspeth/engine/executors/gate_executor.py`

**Verification:** Gate execution tests pass. NodeStateGuard is used in all executors.

---

### Task 13: Consolidate CLI Error Handling

**Priority:** P3 (quality) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** The `run`, `validate`, `resume`, and `purge` commands each have ~30-line error-handling blocks for `_load_settings_with_secrets()` that are nearly identical. Extract to a shared function.

**File:** `src/elspeth/cli.py`

**How:** Create `_load_settings_or_exit(settings_path, ...)` that handles `FileNotFoundError`, `YamlParserError`, `ValidationError`, `SecretLoadError` with consistent error formatting. Use `_format_validation_error()` (rich-formatted) uniformly across all commands.

**Verification:** All 4 commands produce identical error formatting for the same error types.

---

### Task 14: Consolidate Safety Transform Duplication

**Priority:** P3 (quality) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** `AzureContentSafety` and `AzurePromptShield` share ~200 lines of structural duplication, including `_get_fields_to_scan()` which is triplicated across safety transforms.

**How:**
1. Extract `_get_fields_to_scan()` to `src/elspeth/plugins/transforms/safety_utils.py`.
2. Extract shared Azure safety client setup and response handling to the same utility module.
3. Both transforms compose the shared utilities.

**Files:** `src/elspeth/plugins/transforms/azure_content_safety.py`, `src/elspeth/plugins/transforms/azure_prompt_shield.py`.

**Verification:** `_get_fields_to_scan` exists in exactly 1 file. Both safety transforms pass existing tests.

---

### Task 15: MCP Server Tool Dispatch Refactoring

**Priority:** P3 (quality) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** Replace the 100-line if/elif dispatch chain in `call_tool()` with a dispatch table. Unify `_TOOL_ARGS` and `list_tools()` `inputSchema` to prevent divergence.

**File:** `src/elspeth/mcp/server.py`

**How:**
1. Define a `_DISPATCH: dict[str, Callable]` table mapping tool names to handler lambdas/functions.
2. Generate `inputSchema` from `_ArgSpec` at registration time (or add a test that verifies sync).
3. New tools require updating only 1 location (the `_ArgSpec` + dispatch entry) instead of 3.

**Verification:** All 23 MCP tools function identically. Adding a test tool requires exactly 1 dict entry.

---

### Task 16: Fix KeywordFilter Fail-Open on Non-String Fields

**Priority:** P2 (correctness) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** `KeywordFilter` fails open when configured field values are not strings -- keyword matching silently passes non-string values without checking. The filter should reject non-string field configurations at construction time.

**File:** `src/elspeth/plugins/transforms/keyword_filter.py`

**How:** In `__init__()` or `validate()`, verify that all configured fields are expected to contain string values based on the source schema. At runtime, non-string field values should be treated as "no match" with a warning recorded, not silently passed.

**Verification:** Test with non-string field values confirms they are not silently passed.

---

## Phase 3: Architectural Improvements (5-8 days total)

Larger structural changes that improve long-term maintainability. These changes have wider blast radius and should be done on dedicated branches.

### Task 17: Split PluginContext into Focused Protocols

**Priority:** P1 (architecture) | **Effort:** XL | **Risk:** Medium-High | **Dependencies:** Tasks 6, 7

**What:** Decompose `PluginContext` (17 fields, 200+ lines) into focused protocol interfaces. This breaks 4 of 6 dependency cycles.

**New protocols in `src/elspeth/contracts/context.py`:**
```python
@runtime_checkable
class IdentityContext(Protocol):
    @property
    def run_id(self) -> str: ...
    @property
    def row_id(self) -> str: ...
    @property
    def token_id(self) -> str: ...

@runtime_checkable
class AuditContext(Protocol):
    @property
    def landscape(self) -> LandscapeRecorder: ...
    @property
    def payload_store(self) -> PayloadStore: ...

@runtime_checkable
class ExecutionContext(Protocol):
    @property
    def attempt_number(self) -> int: ...
    @property
    def max_attempts(self) -> int: ...
    @property
    def rate_limiter(self) -> RateLimiter | None: ...
```

**How:**
1. Define protocols in `contracts/context.py`.
2. Update each plugin's `process()` / `load()` / `write()` method signature to accept the specific protocols it needs (most need only `IdentityContext`).
3. `PluginContext` itself remains as the concrete implementation satisfying all protocols.
4. Engine code constructs `PluginContext` as before; plugins receive protocol-typed parameters.
5. This is a signature change across all plugins -- plan for a single large commit.

**Risk mitigation:** Implement incrementally by first adding the protocols without changing any signatures, verifying mypy, then updating plugins one subsystem at a time.

**Verification:** `mypy src/` passes. No plugin imports `PluginContext` directly -- all accept protocol types. Dependency cycle analysis shows 4 fewer cycles.

---

### Task 18: Extract Orchestrator Phase Methods

**Priority:** P1 (maintainability) | **Effort:** L | **Risk:** Medium | **Dependencies:** None

**What:** Decompose `_execute_run()` (830 lines) and `_process_single_token()` (375 lines) into focused phase methods. Extract shared logic between `_execute_run()` and `_process_resumed_rows()` into a `WorkItemProcessor`.

**Target structure for orchestrator/core.py:**
```
_execute_run()          -> 80 lines (orchestration only)
  _load_source()        -> ~100 lines
  _process_work_items() -> ~150 lines (shared with resume)
  _flush_aggregations() -> ~80 lines
  _record_outcomes()    -> ~100 lines
  _export_results()     -> ~80 lines
```

**Target structure for processor.py:**
```
_process_single_token() -> 80 lines (orchestration only)
  _execute_node()       -> ~100 lines
  _handle_gate_result() -> ~80 lines
  _handle_fork()        -> ~60 lines
  _record_terminal()    -> ~50 lines
```

**Files:** `src/elspeth/engine/orchestrator/core.py`, `src/elspeth/engine/orchestrator/aggregation.py`, `src/elspeth/engine/processor.py`.

**Risk mitigation:** Extract methods one at a time, running the full test suite after each extraction. Never change behavior -- only move code.

**Verification:** All tests pass. No method exceeds 150 lines. `_execute_run()` and `_process_resumed_rows()` share `_process_work_items()` with zero duplication.

---

### Task 19: Convert Landscape Mixins to Repositories

**Priority:** P2 (architecture) | **Effort:** XL | **Risk:** Medium | **Dependencies:** Task 9

**What:** Replace the 8-mixin inheritance tree in `LandscapeRecorder` with composed repository classes. Each repository owns a specific recording domain and takes `LandscapeDB` as a constructor parameter.

**New structure:**
```
core/landscape/
  recorder.py           -> Facade delegating to repositories (~200 lines)
  repositories/
    run_repository.py   -> Run lifecycle recording
    row_repository.py   -> Row/token recording
    node_repository.py  -> Node state recording
    call_repository.py  -> External call recording
    operation_repository.py -> Source/sink operation recording
    export_repository.py -> Data export
    query_repository.py -> Ad-hoc queries
    lineage_repository.py -> Lineage traversal
```

**How:**
1. Create the repository classes, moving methods from each mixin.
2. Each repository declares its dependencies explicitly in `__init__`.
3. `LandscapeRecorder.__init__` creates all repositories.
4. Public methods on `LandscapeRecorder` delegate to the appropriate repository.
5. Keep the public API of `LandscapeRecorder` identical -- this is an internal refactor.

**Risk mitigation:** Migrate one mixin at a time. Each migration is a separately testable commit.

**Verification:** All tests pass. `LandscapeRecorder` has no mixin parents. Each repository can be independently instantiated for testing.

---

### Task 20: Unify Reorder Buffer Implementations

**Priority:** P2 (architecture) | **Effort:** M | **Risk:** Medium | **Dependencies:** None

**What:** Two reorder buffer implementations exist with overlapping logic. Unify into a single `RowReorderBuffer` used by both batching and pooling subsystems.

**Files:** `src/elspeth/plugins/batching/reorder_buffer.py`, relevant pooling files. Move unified implementation to `src/elspeth/engine/reorder_buffer.py` (since both subsystems are consumers).

**Verification:** Only one reorder buffer implementation exists. Both batching and pooling tests pass.

---

### Task 21: TUI Decision and Implementation

**Priority:** P3 (quality) | **Effort:** M (removal) or XL (completion) | **Risk:** Low (removal) | **Dependencies:** None

**What:** The TUI is non-functional as an interactive tool (see Finding 8 in the final report). A decision is required.

**Option A: Remove the TUI (recommended)**
- Delete `src/elspeth/tui/` (1,134 lines)
- Update `elspeth explain` to support only `--text` and `--json` modes
- Remove `textual` from dependencies
- Effort: M

**Option B: Complete the TUI**
- Make `LineageTree` and `NodeDetailPanel` proper Textual `Widget` subclasses
- Implement token loading via `token_outcomes_table` query
- Implement node selection with keyboard navigation
- Fix `action_refresh()` to re-render widgets
- Effort: XL

**Recommendation:** Option A. The MCP server provides richer interactive exploration, the `--text` output path is functional, and the no-legacy-code policy argues against keeping non-functional scaffolding.

---

## Phase 4: Hardening (2-3 days total)

Final polish and enforcement. These tasks are lower priority but improve long-term quality.

### Task 22: Plugin Registry Pattern

**Priority:** P3 (extensibility) | **Effort:** L | **Risk:** Medium | **Dependencies:** Task 17

**What:** Replace the 70-line if/elif plugin dispatch in `validation.py` with a registry pattern.

**How:** Each plugin class declares its config class via a class attribute:
```python
class CSVSource(SourceProtocol):
    CONFIG_CLASS = CSVSourceSettings
```
The validation layer queries the registry: `plugin_cls.CONFIG_CLASS` instead of a dispatch table.

**File:** `src/elspeth/plugins/validation.py`, plus all plugin class definitions.

**Verification:** The if/elif chain is deleted. New plugins require zero changes to `validation.py`.

---

### Task 23: Config.py Decomposition

**Priority:** P3 (maintainability) | **Effort:** L | **Risk:** Medium | **Dependencies:** Task 6

**What:** Split `config.py` (2,073 lines) into focused modules. Current responsibilities: settings classes, config loading, secret resolution, template utilities, and validation.

**Target structure:**
```
core/config/
  __init__.py         -> Re-exports for backward compatibility
  settings.py         -> Pydantic Settings classes (~800 lines)
  loader.py           -> Dynaconf loading, profile resolution (~400 lines)
  secrets.py          -> Secret resolution, Key Vault integration (~300 lines)
  validation.py       -> Config validation utilities (~200 lines)
```

**Risk mitigation:** Use `__init__.py` re-exports so that `from elspeth.core.config import ElspethSettings` continues to work without updating importers.

**Verification:** All tests pass. `config.py` is replaced by `config/` package. No broken imports.

---

### Task 24: Telemetry Exporter Cleanup

**Priority:** P3 (quality) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** Extract shared event serialization into `telemetry/serialization.py`. Add per-exporter circuit breakers. Make shared helpers public.

**Files:** `src/elspeth/telemetry/exporters/` (OTLP, Azure Monitor, and any other exporter files).

**Verification:** No private symbol (`_`-prefixed) is imported across module boundaries in telemetry/. Each exporter can fail independently without affecting others.

---

### Task 25: SSRF Caller-Site Audit

**Priority:** P2 (security) | **Effort:** M | **Risk:** Low | **Dependencies:** None

**What:** The SSRF defense in `core/security/web.py` is architecturally sound (`SSRFSafeRequest` frozen dataclass with pinned IP), but a caller-site audit is needed to verify all HTTP consumers use `connection_url` + `host_header` rather than the original URL.

**How:**
1. Search for all `httpx.get()`, `httpx.post()`, `httpx.AsyncClient`, and similar HTTP call sites in `src/elspeth/`.
2. For each call site, verify it uses the SSRF-safe request pattern.
3. Document any exceptions (e.g., calls to trusted internal services that do not need SSRF protection).

**Files:** `src/elspeth/plugins/clients/`, `src/elspeth/plugins/sources/`, `src/elspeth/plugins/sinks/`, any other file making HTTP calls.

**Verification:** Written audit document listing every HTTP call site and its SSRF status. No call site bypasses SSRF protection without documented justification.

---

### Task 26: BatchReplicate Quarantine Audit Gap

**Priority:** P2 (correctness) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** `BatchReplicate` quarantined rows are not audited as distinct terminal tokens. When a row is quarantined during batch replication, the audit trail loses track of the row's terminal state.

**File:** `src/elspeth/plugins/transforms/batch_replicate.py`

**How:** Ensure quarantined rows in batch replication are recorded with `QUARANTINED` terminal state in the Landscape via the same pattern used by other transforms.

**Verification:** Test that a quarantined row in batch replication produces a `QUARANTINED` token outcome in the audit trail.

---

### Task 27: ChaosLLM MCP Bug Fix (serve() Missing)

**Priority:** P3 (testing infrastructure) | **Effort:** S | **Risk:** Low | **Dependencies:** None

**What:** `chaosllm/cli.py` calls `mcp_server.serve(database)` but `chaosllm_mcp/server.py` has no `serve()` function. The correct entry point is `asyncio.run(mcp_server.run_server(database))`. This will raise `AttributeError` at runtime.

**Files:** `src/elspeth/testing/chaosllm/cli.py`, `src/elspeth/testing/chaosllm_mcp/server.py`

**How:** Change the call in `cli.py` to `asyncio.run(mcp_server.run_server(database))`. Remove the `# type: ignore` annotations that were suppressing this error.

**Verification:** `chaosllm-mcp --database <path>` starts without `AttributeError`.

---

## Task Dependency Graph

```
Phase 1 (Quick Wins) -- all independent:
  T1  Freeze audit records
  T2  Fix assert statements
  T3  Fix truthiness checks
  T4  Fix passphrase failure
  T5  Fix diagnose scope
  T6  Move ExpressionParser
  T7  Move MaxRetriesExceeded/BufferEntry to contracts
  T8  Remove dead code

Phase 2 (Structural) -- some dependencies:
  T9  Typed boundaries        <- T1
  T10 LLM consolidation       <- T8
  T11 PluginBundle            (independent)
  T12 NodeStateGuard          (independent)
  T13 CLI error handling      (independent)
  T14 Safety consolidation    (independent)
  T15 MCP dispatch            (independent)
  T16 KeywordFilter fix       (independent)

Phase 3 (Architecture) -- dependencies on Phase 1/2:
  T17 Split PluginContext     <- T6, T7
  T18 Orchestrator phases     (independent)
  T19 Landscape repositories  <- T9
  T20 Reorder buffer unify    (independent)
  T21 TUI decision            (independent)

Phase 4 (Hardening) -- dependencies on Phase 2/3:
  T22 Plugin registry         <- T17
  T23 Config decomposition    <- T6
  T24 Telemetry cleanup       (independent)
  T25 SSRF audit              (independent)
  T26 BatchReplicate audit    (independent)
  T27 ChaosLLM MCP fix        (independent)
```

---

## Risk Mitigation

### High-Risk Tasks

**Task 17 (PluginContext split):** Widest blast radius -- touches every plugin. Mitigate by:
1. Adding protocols first without changing any signatures.
2. Verifying mypy passes with protocols defined but unused.
3. Updating plugins one subsystem at a time (sources, then transforms, then sinks).
4. Each subsystem update is a separate commit.

**Task 18 (Orchestrator decomposition):** Risk of subtle behavioral changes. Mitigate by:
1. Extract methods by pure code motion -- no logic changes.
2. Run full test suite after each individual extraction.
3. Use `git diff --stat` to verify no lines were added or removed (only moved).

**Task 19 (Landscape repositories):** Implicit mixin state dependencies may not be obvious. Mitigate by:
1. Migrate one mixin at a time.
2. Explicitly list all `self._*` attributes each mixin accesses.
3. Each repository's constructor declares these as parameters.

### Rollback Strategy

Each task targets a single concern. If a task introduces regressions:
1. Revert the task's commit(s).
2. File a Filigree bug with the regression details.
3. Continue with other independent tasks.

---

## Decision Points

These items require human judgment before proceeding:

### D1: TUI Fate (Task 21)
**Options:** Remove (M effort, recommended) vs Complete (XL effort).
**Decide before:** Phase 3 begins.
**Impact:** Removing frees 1,134 lines and a dependency (textual). Completing creates a functional interactive tool.

### D2: PluginContext Granularity (Task 17)
**Options:** 3 protocols (Identity/Audit/Execution) vs 2 (Identity/Services) vs leaving as-is with only protocol annotations.
**Decide before:** Task 17 implementation begins.
**Impact:** More protocols = more type safety but more ceremony. The 3-protocol split is recommended as the natural grouping.

### D3: Landscape Repository Granularity (Task 19)
**Options:** 8 repositories (1:1 with current mixins) vs 4 (grouped by domain: recording, querying, export, lineage) vs keep mixins with explicit dependency declarations.
**Decide before:** Task 19 implementation begins.
**Impact:** 8 repositories is the cleanest decomposition but creates the most files. 4 is a pragmatic middle ground.

### D4: Config.py Split Strategy (Task 23)
**Options:** Package with re-exports (backward compatible) vs package with updated imports (breaking).
**Decide before:** Task 23 implementation begins.
**Impact:** Re-exports add a compatibility layer (which may conflict with no-legacy-code policy). Updated imports are cleaner but require updating every `from elspeth.core.config import` statement.

---

## Success Criteria

### Phase 1 Complete When:
- All 16 audit records are `frozen=True`
- Zero `assert` statements in `src/elspeth/plugins/`
- Zero truthiness checks on numeric values at known locations
- `ExpressionParser` lives in `core/`
- All dead code items removed
- Full test suite passes
- `mypy src/` clean

### Phase 2 Complete When:
- Zero `dict[str, Any]` at plugin client -> Landscape boundaries
- LLM plugin line count reduced by ~800
- All related Filigree bugs closable
- `PluginBundle` replaces magic string access in CLI
- `NodeStateGuard` used by all executors
- Full test suite passes

### Phase 3 Complete When:
- Dependency cycle count reduced from 6 to 2 or fewer
- No method exceeds 150 lines in orchestrator or processor
- `LandscapeRecorder` has no mixin parents
- TUI decision implemented
- Full test suite passes

### Phase 4 Complete When:
- Plugin registration requires zero changes to dispatch tables
- SSRF caller-site audit documented
- All test infrastructure bugs fixed
- Full test suite passes
- `mypy src/` clean

---

## Effort Summary

| Phase | Tasks | Estimated Effort | Key Deliverable |
|-------|-------|-----------------|-----------------|
| Phase 1 | T1-T8 | 1-2 days | Frozen audit records, cycle-breaking moves, dead code removal |
| Phase 2 | T9-T16 | 3-5 days | Typed boundaries, LLM consolidation, CLI cleanup |
| Phase 3 | T17-T21 | 5-8 days | PluginContext split, orchestrator decomposition, Landscape repositories |
| Phase 4 | T22-T27 | 2-3 days | Plugin registry, config split, security audit, hardening |
| **Total** | **27 tasks** | **11-18 days** | |

Phase 1 and Phase 2 are the highest-value investment. Phase 3 delivers the largest architectural improvement but carries the highest risk. Phase 4 is polish that can be deferred if time is constrained.
