# ELSPETH Architecture Analysis: Final Report

> **Pre-remediation snapshot (2026-02-22).** This analysis was conducted at the start of the RC3.3 branch, before remediation work began. Findings described here may have been addressed by subsequent commits on this branch. See the CHANGELOG for resolved items.

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Scope:** 193 files across 45 packages (~66,000 lines)
**Analysis depth:** 15 subsystem analyses covering every file in `src/elspeth/`

---

## Executive Summary

ELSPETH's architecture is fundamentally sound. The Sense/Decide/Act pipeline model, pluggy-based extensibility, Landscape audit backbone, and three-tier trust model form a coherent foundation for auditable data processing. The codebase demonstrates genuine architectural discipline: composite primary keys are consistently applied, frozen dataclasses enforce immutability at trust boundaries, and the separation between audit trail and operational telemetry is clean.

However, the analysis identifies **three systemic patterns** that represent escalating risk as the codebase grows:

1. **God Object convergence**: `PluginContext` (17 fields, 200+ lines), `_execute_run()` (830 lines), `_process_single_token()` (375 lines), `config.py` (2,073 lines), and `ExecutionGraph` (1,452 lines) are accumulating responsibilities faster than they are being decomposed.

2. **Tier 1 audit boundary erosion**: 16 mutable dataclass records in `contracts/audit.py` can be modified after creation, and untyped `dict[str,Any]` values cross into the Landscape at multiple plugin client boundaries. The audit trail's integrity guarantee depends on immutability that is declared in policy but not enforced in code.

3. **Layer violations and dependency cycles**: 6 bidirectional dependency cycles exist between the expected L0-L4 layers. The most significant is the contracts-to-engine cycle (`contracts/` imports from `engine/expression_parser.py`), which inverts the intended dependency direction.

No P0 correctness bugs were found in the current analysis. The previously reported P0 issues (JSON sink data loss, content safety fail-open) are confirmed resolved. The findings are architectural debt that increases the cost of change and the risk of future defects.

---

## Architecture Overview

### Layer Model (Expected)

```
L0  contracts/       Type definitions, protocols, enums (leaf layer, zero internal deps)
L1  core/            Infrastructure: landscape, config, canonical, security, events
L2  engine/          Execution: orchestrator, processor, executors, retry, tokens
L3  plugins/         Domain: sources, transforms, sinks, LLM clients, batching
L4  cli/ tui/ mcp/   Presentation: CLI commands, TUI screens, MCP analysis server
```

### Layer Model (Actual)

Six bidirectional dependency cycles violate this layering:

| Cycle | Direction | Cause |
|-------|-----------|-------|
| contracts <-> engine | L0 -> L2 | `results.py` imports `MaxRetriesExceeded` from engine |
| contracts <-> plugins | L0 -> L3 | `PluginContext` references plugin types |
| core <-> engine | L1 -> L2 | `config.py` imports expression parser for gate validation |
| core <-> contracts | L1 <-> L0 | Mutual references between config and protocol types |
| engine <-> plugins | L2 <-> L3 | Executors reference plugin-specific types |
| plugins <-> core | L3 -> L1 | Plugin clients import landscape recorder directly |

The `PluginContext` dataclass is the primary coupling vector, appearing in 4 of 6 cycles because it aggregates references to components from every layer.

---

## Key Findings

### Finding 1: Mutable Audit Records at Tier 1 Boundary

**Severity:** HIGH | **Impact:** Audit integrity | **Subsystem:** contracts/audit.py

16 dataclass records that represent Landscape audit trail entries (Run, Node, Edge, Row, Token, TokenParent, Call, Artifact, RoutingEvent, Batch, BatchMember, BatchOutput, Checkpoint, RowLineage, ValidationErrorRecord, TransformErrorRecord) use `@dataclass` without `frozen=True`. Note: newer types (NodeState variants, Operation, TokenOutcome, SecretResolution) are already frozen, indicating a migration that stalled partway. These objects are created in engine code, populated incrementally, then written to the audit database.

The three-tier trust model states that Tier 1 data "must be 100% pristine at all times" and that "silently coercing bad data is evidence tampering." Mutable audit records allow post-creation modification, which means the data written to the database may not match what was originally recorded. While no current code path exploits this mutability intentionally, it is an undefended invariant.

**Evidence:** `contracts/audit.py` lines 1-500; all 16 dataclass definitions lack `frozen=True`.

**Recommendation:** Convert all 16 audit record dataclasses to `frozen=True`. Use `dataclasses.replace()` for any legitimate incremental construction patterns. This is the single highest-leverage change for audit integrity.

---

### Finding 2: Untyped Dict Boundaries at Plugin Clients

**Severity:** HIGH | **Impact:** Audit integrity, type safety | **Subsystem:** plugins/clients/, engine/executors/

Multiple plugin client boundaries pass `dict[str, Any]` where frozen dataclasses should enforce schema. The `TokenUsage` dataclass (commit dffe74a6) established the correct pattern, but it has not been applied consistently:

- `LLMClient.query()` returns response metadata as `dict[str, Any]`
- `WebScraperClient.scrape()` returns page metadata as `dict[str, Any]`
- `TransformExecutor` records `success_reason` and `error_reason` as `dict[str, Any]`
- `GateResult.row` is `dict[str, Any]` while `TransformResult` uses `PipelineRow`

Each untyped dict that reaches the Landscape recorder is a potential source of schema drift, where the audit trail records fields that no consumer expects or omits fields that consumers require.

**Evidence:** 10 open Filigree bugs (all P2/P3) track individual instances. `contracts/results.py` shows the `GateResult` vs `TransformResult` asymmetry.

**Recommendation:** Define frozen dataclasses for each boundary: `LLMResponseMeta`, `WebScrapeMeta`, `TransformOutcome`, `GateOutcome`. Wire them through to `LandscapeRecorder` methods with typed parameters.

---

### Finding 3: PluginContext God Object

**Severity:** HIGH | **Impact:** Coupling, testability, layer violations | **Subsystem:** contracts/context.py

`PluginContext` has 17 fields spanning 4 architectural layers: identifiers (run_id, row_id, token_id), runtime services (landscape, payload_store, rate_limiter), configuration (settings, plugin_config), and execution state (attempt_number, max_attempts). Every plugin receives this object, creating a dependency from L0 contracts to L1 core, L2 engine, and L3 plugin infrastructure.

This makes unit testing plugins difficult (must construct a full context), makes the dependency graph cyclic (contracts references engine types), and means any change to any service interface potentially affects every plugin.

**Evidence:** `contracts/context.py` (200+ lines); 4 of 6 dependency cycles involve PluginContext.

**Recommendation:** Split into focused protocols: `IdentityContext` (run_id, row_id, token_id), `AuditContext` (landscape, payload_store), `ExecutionContext` (attempt_number, max_attempts, rate_limiter). Plugins declare which protocols they need. This breaks 4 dependency cycles.

---

### Finding 4: Orchestrator and Processor Monoliths

**Severity:** HIGH | **Impact:** Maintainability, testability | **Subsystem:** engine/orchestrator/core.py, engine/processor.py

`_execute_run()` in orchestrator/core.py is 830 lines with 6+ nesting levels. `_process_single_token()` in processor.py is 375 lines with similar depth. Together they form the execution backbone, and their size makes reasoning about control flow, error handling, and state transitions extremely difficult.

Additionally, `_execute_run()` and `_process_resumed_rows()` share approximately 60% of their logic (work-item processing, aggregation handling, outcome recording), but this shared logic is duplicated rather than extracted.

**Evidence:** engine/orchestrator/core.py lines 1-830; engine/processor.py lines 1-375; engine/orchestrator/aggregation.py contains duplicated work-item processing helpers.

**Recommendation:** Extract phase methods from `_execute_run()`: `_process_source_rows()`, `_process_work_items()`, `_flush_aggregations()`, `_record_outcomes()`. Extract a shared `WorkItemProcessor` that both `_execute_run` and `_process_resumed_rows` delegate to. Target: no method exceeds 150 lines.

---

### Finding 5: LLM Plugin Duplication

**Severity:** HIGH | **Impact:** Consistency, correctness | **Subsystem:** plugins/llm/

Approximately 1,330 lines are duplicated across 6 LLM transform files (azure_batch, azure_multi_query, openrouter, openrouter_batch, openrouter_multi_query, plus the base). The duplication includes response validation, retry logic, NaN/Infinity rejection, and output schema construction.

Critically, this duplication has already produced inconsistencies: `openrouter_batch.py` does not reject NaN/Infinity in float fields (while Azure variants do), and `openrouter.py` uses a different output schema structure than the other transforms.

**Evidence:** plugins/llm/ directory; `BaseLLMTransform` exists but has zero production subclasses (orphaned). NaN rejection present in azure_batch.py but absent from openrouter_batch.py.

**Recommendation:** Delete `BaseLLMTransform`. Extract shared logic into composable utilities: `validate_llm_response()`, `build_llm_output_schema()`, `reject_nan_infinity()`. Each LLM transform composes these utilities rather than inheriting from a base class.

---

### Finding 6: Inverted Dependency in Config/Expression Parser

**Severity:** MEDIUM | **Impact:** Layer integrity | **Subsystem:** core/config.py, engine/expression_parser.py

`core/config.py` (L1) imports `engine/expression_parser.py` (L2) to validate gate expressions during configuration loading. This inverts the expected dependency direction (L1 should not depend on L2). The expression parser is well-designed (fail-closed, no eval(), immutable operator tables), but its location in the engine layer creates a cycle.

**Evidence:** core/config.py import of ExpressionParser; cross-cutting-dependencies.md cycle #3.

**Recommendation:** Move `ExpressionParser` to `core/expressions.py`. It has no engine dependencies and is a pure validation utility. This breaks the core-to-engine cycle.

---

### Finding 7: Landscape Mixin Anti-Pattern

**Severity:** MEDIUM | **Impact:** Maintainability, discoverability | **Subsystem:** core/landscape/

The Landscape recorder uses 8 mixins that share state through implicit attribute annotations. `LandscapeRecorder` inherits from `_RunRecordingMixin`, `_RowRecordingMixin`, `_NodeRecordingMixin`, `_CallRecordingMixin`, `_OperationRecordingMixin`, `_ExportMixin`, `_QueryMixin`, and `_LineageMixin`. Each mixin assumes access to `self._db`, `self._schema`, etc. without declaring these dependencies.

The total is 11,681 lines across 21 files. This mixin tree makes it difficult to understand which methods are available on the recorder, and impossible to use any recording capability independently.

**Evidence:** core/landscape/ directory; recorder.py assembles all mixins; each mixin file uses `self._db` without importing or declaring it.

**Recommendation:** Convert mixins to composed repositories: `RunRepository`, `RowRepository`, `NodeRepository`, etc. Each repository takes `LandscapeDB` in its constructor. `LandscapeRecorder` becomes a facade that delegates to repositories.

---

### Finding 8: Non-Functional TUI

**Severity:** MEDIUM | **Impact:** User experience, dead code | **Subsystem:** tui/

The TUI (1,134 lines) appears to implement interactive lineage exploration but is non-functional:
- `ExplainApp` renders `Static` text widgets, not interactive Textual widgets
- Token loading is deferred but never completed (always empty list)
- Node execution state requires token selection, but no selection UI exists
- `action_refresh()` does not update displayed content
- Help text mentions arrow key navigation that does not work

The `--no-tui` text output path and the MCP `explain_token` tool both provide equivalent or superior functionality.

**Evidence:** tui/explain_app.py (Static widgets); tui/screens/explain_screen.py (tokens always `[]`); tui/widgets/lineage_tree.py (token nodes never populated).

**Recommendation:** Per the no-legacy-code policy, remove the TUI. The `elspeth explain` command should support `--text` and `--json` output modes only. The MCP server provides interactive exploration via Claude. This removes 1,134 lines of non-functional code.

---

### Finding 9: Hardcoded Plugin Dispatch in Validation

**Severity:** MEDIUM | **Impact:** Extensibility, maintenance burden | **Subsystem:** plugins/validation.py

Plugin name-to-config-class dispatch is a 70-line if/elif chain in `validation.py`. Every new plugin requires updating this chain. Protocol/base class synchronization between plugin protocols and base implementations is manual with no automated parity test.

**Evidence:** plugins/validation.py dispatch chain; plugins/base/ protocol definitions.

**Recommendation:** Implement a plugin registry pattern where each plugin class declares its config class via a class attribute or decorator. The validation layer queries the registry instead of maintaining a parallel dispatch table.

---

### Finding 10: Batching and Pooling Architectural Friction

**Severity:** MEDIUM | **Impact:** Performance, complexity | **Subsystem:** plugins/batching/, plugins/pooling/

Two overlapping reorder buffer implementations exist (one in batching, one in pooling). `PooledExecutor._batch_lock` serializes all operations within a batch, eliminating row-level parallelism for multi-query transforms. `CapacityError.retryable` is dead code (accepted but never checked). `flush_batch_processing()` uses a polling loop instead of a condition variable.

**Evidence:** plugins/batching/reorder_buffer.py and plugins/pooling/ contain parallel implementations; _batch_lock in pooled_executor.py.

**Recommendation:** Unify the reorder buffer into a single implementation in `core/` or `engine/`. Replace `_batch_lock` with per-row locking or a queue-based approach. Remove `CapacityError.retryable`. Replace the polling loop with `threading.Condition`.

---

### Finding 11: Telemetry Private Symbol Sharing

**Severity:** MEDIUM | **Impact:** Maintainability | **Subsystem:** telemetry/

The OTLP and Azure Monitor exporters share private helper symbols (prefixed with `_`) across module boundaries. Event serialization is duplicated across 3 exporters. Per-exporter failures are not independently circuit-broken (one failing exporter can affect others).

**Evidence:** telemetry/exporters/ directory; shared `_serialize_event()` logic.

**Recommendation:** Extract shared serialization into `telemetry/serialization.py`. Add per-exporter circuit breakers. Make shared helpers public (drop the `_` prefix) since they are intentionally cross-module.

---

### Finding 12: Transform Safety Gaps

**Severity:** MEDIUM | **Impact:** Correctness | **Subsystem:** plugins/transforms/

Several transform-level issues:
- `BatchReplicate` quarantined rows are not audited as distinct terminal tokens (audit gap)
- `assert` statements in production code are stripped in `-O` mode (5 instances)
- Azure content safety and prompt shield transforms have ~200 lines of structural duplication
- `_get_fields_to_scan()` is triplicated across safety transforms
- `KeywordFilter` fails open on non-string configured fields

**Evidence:** plugins/transforms/batch_replicate.py; plugins/transforms/azure_content_safety.py and azure_prompt_shield.py; plugins/transforms/keyword_filter.py.

**Recommendation:** Replace `assert` with explicit `if not x: raise`. Extract `_get_fields_to_scan()` to a shared safety utility. Audit `BatchReplicate` quarantine path for token recording. Fix `KeywordFilter` to reject non-string field configurations at construction.

---

## Dependency Analysis Summary

The 6 bidirectional dependency cycles form two clusters:

**Cluster A (PluginContext-driven):** 4 cycles originate from `PluginContext` aggregating references across layers. Splitting PluginContext into focused protocols resolves these.

**Cluster B (Config/Expression):** 2 cycles originate from `config.py` importing engine-layer utilities for validation. Moving `ExpressionParser` to `core/` resolves these.

Quick wins that break cycles without architectural changes:
- Move `MaxRetriesExceeded` from `contracts/` to `engine/` (where it is thrown)
- Move `BufferEntry` from `contracts/` to `engine/` (only consumer)
- Move `ExpressionParser` from `engine/` to `core/` (pure validation utility)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Audit record mutation introduces incorrect lineage | Medium | Critical | Freeze all 16 audit dataclasses (Finding 1) |
| Untyped dict allows schema drift in audit trail | High | High | Typed dataclasses at every boundary (Finding 2) |
| Orchestrator monolith resists safe modification | High | High | Extract phase methods (Finding 4) |
| LLM inconsistency produces incorrect NaN handling | Medium | High | Shared validation utilities (Finding 5) |
| New plugin requires 3+ file changes to register | Certain | Low | Plugin registry pattern (Finding 9) |
| TUI confuses users expecting interactivity | Medium | Low | Remove or document (Finding 8) |

---

## Conclusion

ELSPETH is architecturally well-conceived. The three-tier trust model, the Landscape audit backbone, and the DAG execution model are strong foundations. The codebase's quality is above average, with consistent patterns for composite primary keys, frozen configuration, and deterministic canonicalization.

The findings in this report are architectural debt, not architectural failure. The most critical items (mutable audit records, untyped boundaries, god objects) follow a common pattern: policies that are documented in CLAUDE.md but not yet fully enforced in code. The remediation roadmap in the companion Architect Handover document provides a phased approach to closing these gaps, prioritized by risk to audit integrity.

The testing infrastructure (ChaosLLM, ChaosWeb, ChaosEngine) is notably well-isolated from the main codebase with clean one-way dependencies and proper Jinja2 sandboxing. The MCP analysis server is well-structured after its refactoring from a 2,355-line monolith to the current 4-module architecture. These are architectural successes that demonstrate the team's capability to execute the remediation work ahead.
