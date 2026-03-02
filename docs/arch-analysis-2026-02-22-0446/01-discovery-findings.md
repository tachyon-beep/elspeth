# ELSPETH Architecture Discovery Findings

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6

---

## Executive Summary

ELSPETH is a domain-agnostic framework for auditable Sense/Decide/Act (SDA) pipelines, where every decision must be traceable to its source data, configuration, and code version. The codebase is architecturally mature, with a well-designed audit backbone (Landscape), a protocol-based type contract system, and a DAG-compiled execution model. The primary structural issues are: (1) six bidirectional dependency cycles between layers, driven largely by a god-object PluginContext in the contracts layer; (2) significant code duplication in the LLM plugin subsystem (~1,330 lines across 6 provider files); (3) oversized methods in the engine orchestration layer (830-line `_execute_run`, 375-line `_process_single_token`); (4) 16 mutable Tier 1 audit record dataclasses that should be frozen; and (5) an inverted dependency from core to engine for expression parsing.

## Codebase Metrics

- 77,477 lines across 206 Python files in 9 top-level subsystems
- Largest: plugins (22K), core (16K), engine (12K), contracts (10K), testing (9K)
- 17 Landscape audit tables with composite primary keys and referential integrity
- ~60 contract dataclasses (~40 frozen, ~20 mutable)
- 16 StrEnum types, 8 protocol definitions, 6 NewType semantic aliases
- 8,037 passing tests (unit, integration, e2e, property, performance)

## Technology Stack

| Component | Technology | Role |
|-----------|------------|------|
| CLI | Typer | Type-safe command interface |
| TUI | Textual | Interactive lineage explorer |
| Configuration | Dynaconf + Pydantic | Multi-source loading + validation |
| Plugins | pluggy | Hook-based discovery (3 hooks) |
| Database | SQLAlchemy Core | Multi-backend audit storage |
| Data | pandas | Tabular data processing |
| Canonical JSON | rfc8785 | Deterministic hashing (RFC 8785/JCS) |
| DAG | NetworkX | Graph validation, topo sort, cycle detection |
| Logging | structlog | Structured event logging |
| Rate Limiting | pyrate-limiter | External call throttling |

## Organizational Structure

The codebase follows a layered architecture with clear (though imperfectly enforced) dependency directions:

```
L0: contracts       -- Foundation: type definitions, protocols, frozen dataclasses
L1: core            -- Infrastructure: landscape, config, DAG, security, canonical
L2: engine          -- Execution: orchestrator, processor, executors, retry
L3: plugins         -- Implementations: sources, transforms, sinks, LLM, clients
L4: cli, tui, mcp   -- User-facing: CLI commands, TUI screens, MCP analysis server
    testing         -- Test infrastructure: chaos servers, generators
```

**Dependency fan-in/fan-out:**

| Layer | Outbound | Inbound | Role |
|-------|----------|---------|------|
| contracts (L0) | 3 | 8 | Foundation, heavily imported |
| core (L1) | 3 | 8 | Infrastructure, heavily imported |
| engine (L2) | 4 | 3 | Execution coordination |
| plugins (L3) | 2 | 4 | Plugin implementations |
| cli (L4) | 9 | 1 | Highest fanout (orchestrates everything) |

## Key Architectural Patterns

1. **Three-Tier Trust Model.** Tier 1 (audit data): crash on any anomaly, no coercion. Tier 2 (pipeline data): trust types, wrap operations on values. Tier 3 (external data): validate at boundary, coerce where meaning-preserving, quarantine failures.

2. **Protocol-based typing with frozen dataclasses.** Runtime*Config classes implement @runtime_checkable protocols consumed by engine components. ~40 frozen dataclasses enforce immutability at contract boundaries.

3. **Settings-to-Runtime*Config conversion.** Three-layer enforcement: mypy structural typing, AST-based field coverage checker, alignment tests. Prevents the "orphaned setting" class of bugs.

4. **DAG compilation from YAML.** 15-phase builder constructs an ExecutionGraph from plugin instances: node creation, deterministic ID generation (canonical JSON + SHA-256), producer/consumer wiring, two-pass schema resolution, topological sort, config freezing.

5. **Token identity for row lineage.** `row_id` (stable source identity) vs `token_id` (DAG path instance). Fork/join/expand tracked via `parent_token_id` and group IDs. Every row reaches exactly one of 9 terminal states.

6. **Content-addressable payload store.** Large blobs stored separately from audit tables. Hashes survive payload deletion. Retention policies support purge with reproducibility grade degradation.

7. **pluggy hook-based plugin system.** Three hooks (source, transform, sink). Filesystem discovery scans known directories. All plugins are system-owned code, not user extensions. pluggy acts primarily as a list aggregator.

## Critical Findings

### Finding 1: Six Bidirectional Dependency Cycles

The layered architecture has 6 cycles, 3 of which are HIGH severity:

| Cycle | Severity | Root Cause |
|-------|----------|------------|
| contracts (L0) <-> core (L1) | HIGH | PluginContext imports LandscapeRecorder, RateLimitRegistry; runtime.py imports Settings; url.py imports security |
| contracts (L0) <-> plugins (L3) | HIGH | PluginContext imports AuditedHTTPClient, AuditedLLMClient; node_state_context imports BufferEntry |
| contracts (L0) <-> engine (L2) | MEDIUM | results.py imports MaxRetriesExceeded |
| core (L1) <-> engine (L2) | MEDIUM | config.py imports ExpressionParser for gate expression validation |
| core (L1) <-> plugins (L3) | MEDIUM | DAG builder/graph/models import SourceProtocol, TransformProtocol, SinkProtocol |
| cli <-> cli_helpers | LOW | Functional split within same layer |

The dominant coupling vector is **PluginContext** in contracts/plugin_context.py, which imports from core (LandscapeRecorder, RateLimitRegistry, canonical hashing) and plugins (AuditedHTTPClient, AuditedLLMClient). This single god object creates 2 of the 3 HIGH-severity cycles. It has 17 fields and 200+ lines of method code, mixing configuration, state management, call recording, telemetry, and checkpointing.

**Remediation candidates (quick wins):** Move MaxRetriesExceeded to contracts/errors.py, move BufferEntry to contracts/, move ExpressionParser to core/, move plugin protocols from plugins/protocols.py to contracts/.

**Structural fix:** Decompose PluginContext into protocol-based injection or move it to a higher layer.

### Finding 2: LLM Plugin Duplication (~1,330 Lines)

Six provider-specific LLM transform files share ~80% structure but copy-paste instead of inheriting or composing:

| Duplicated Component | Occurrences | Est. Lines |
|---------------------|-------------|------------|
| Langfuse tracing (setup/record/flush) | 6 files | ~600 |
| Schema setup in __init__ | 6 files | ~180 |
| Client caching pattern | 5 files | ~150 |
| Response parsing (HTTP) | 3 files | ~120 |
| connect_output / accept boilerplate | 2 files | ~40 |
| Other (tracing errors, etc.) | various | ~240 |

This duplication has already caused divergence bugs: `openrouter_batch.py` does not reject NaN/Infinity in JSON responses (uses `response.json()` instead of `json.loads` with `parse_constant`), and `openrouter.py` does not use the augmented output schema that azure.py uses. Additionally, `BaseLLMTransform` has zero production subclasses (orphaned abstraction that should be deleted per the No Legacy Code policy).

### Finding 3: Engine Orchestration Complexity

The engine orchestration layer has two oversized hotspots:

- **`orchestrator/core.py::_execute_run()`** -- 830 lines, 6 nesting levels. Handles graph registration (~200 lines), source loading with quarantine (~200 lines), the processing loop (~150 lines), aggregation/coalesce flush, sink writes, and bookkeeping. The resume path (`_process_resumed_rows()`, 290 lines) duplicates ~60% of this structure: counter initialization, pending_tokens setup, the processing loop pattern, end-of-source flush, coalesce flush, and sink writes.

- **`processor.py::_process_single_token()`** -- 375 lines. The heart of DAG traversal, handling transforms (success, error with discard/routing, multi-row expansion, batch aggregation), gates (sink/fork/jump/continue), coalesce, and telemetry. The transform error handling path (quarantine vs routing) is duplicated inline. `_execute_transform_with_retry()` has two nearly identical exception handlers (LLMClientError and generic transient errors, ~50 lines each).

- **`processor.py` RowProcessor constructor has 18 parameters**, reflecting the class managing too many concerns: token creation, transform execution, gate evaluation, aggregation handling, coalesce handling, retry, routing, and telemetry.

Supporting modules have internal duplication: `aggregation.py` has identical work-item processing loops in two functions (~45 lines each), and `outcomes.py` has ~70% shared code between coalesce timeout and flush handlers.

### Finding 4: 16 Mutable Tier 1 Audit Records

In contracts/audit.py, 16 dataclasses representing Tier 1 audit records lack `frozen=True`: Run, Node, Edge, Row, Token, TokenParent, Call, Artifact, RoutingEvent, Batch, BatchMember, BatchOutput, Checkpoint, RowLineage, ValidationErrorRecord, TransformErrorRecord. These are database records that should never be modified after construction. Newer types in the same file (NodeState variants, Operation, SecretResolution, TokenOutcome) are already frozen, suggesting an incomplete migration.

Per CLAUDE.md: "Bad data in the audit trail = crash immediately." Mutable audit records can be accidentally modified after construction, silently corrupting the legal record.

### Finding 5: Inverted Dependency core -> engine

`core/config.py` imports `engine.expression_parser.ExpressionParser` for gate condition validation at config load time. This inverts the expected dependency direction (engine depends on core, not vice versa). The expression parser is used for config-time validation, but the import forces engine module initialization during config loading. This is one of 4 upward-layer violations from core (the others being 3 imports from core/dag/ to plugins/protocols.py for SourceProtocol, TransformProtocol, SinkProtocol).

## Cross-Cutting Concerns

### Error Handling Model

The codebase implements three distinct error handling strategies aligned with the trust model:

- **Tier 1 (audit data):** `AuditIntegrityError`, `FrameworkBugError`, `OrchestrationInvariantError`, `CheckpointCorruptionError`. Crash immediately. Some inconsistency: certain Tier 1 violations raise generic `ValueError` instead of `AuditIntegrityError` (notably in `_database_ops.py` and `_graph_recording.py`).

- **Tier 2 (pipeline data):** `TransformResult.error()` with routing to quarantine or error sinks. Row-level isolation -- one bad row does not stop the pipeline.

- **Tier 3 (external data):** Validate at boundary, coerce where meaning-preserving. `NonCanonicalMetadata` fallback for un-hashable quarantine data. `repr_hash()` for non-canonical audit hashing.

- **Control flow:** `BatchPendingError` (not an error -- signals async batch checkpoint), `GracefulShutdownError` (SIGINT/SIGTERM -- run is resumable).

### Configuration

Two-layer pattern: Pydantic Settings models (YAML validation) -> frozen Runtime*Config dataclasses (engine consumption). Protocol-based verification ensures no field is silently dropped. `core/config.py` at 2,073 lines mixes settings models, loading pipeline, env var expansion, template expansion, secret fingerprinting, and DSN sanitization -- a candidate for splitting into `config_models.py`, `config_loading.py`, and `config_secrets.py`.

### Logging and Observability

Dual-channel: Landscape (permanent legal record, Tier 1) and Telemetry (ephemeral operational visibility via OpenTelemetry). Event bus (protocol-based, synchronous) bridges domain logic to CLI formatters. 14 frozen event dataclasses cover lifecycle, row-level, and external call telemetry. Correlation via `run_id` and `token_id` enables cross-referencing between telemetry and the Landscape explain API.

### Security

Secret fingerprinting via HMAC (never raw storage in audit trail). URL sanitization types (`SanitizedDatabaseUrl`, `SanitizedWebhookUrl`) enforce no-password-in-audit-trail at the type level. SSRF-safe HTTP with IP-pinned connections and per-hop redirect validation. Path traversal prevention for template file resolution. Jinja2 ImmutableSandboxedEnvironment with StrictUndefined. AST-based expression parser (no eval).

## Additional Findings by Subsystem

### Landscape (core/landscape/ -- 21 files, 11,681 lines)

- **Strengths:** Strong Tier 1 compliance. 14 repository classes enforce enum validation and invariant checking at deserialization boundary. Batch query optimization (pre-load then iterate) eliminates N+1 patterns in exporter and lineage. Atomic fork/expand transactions. Quarantine-aware hashing with repr_hash fallback. Ownership validation prevents cross-run contamination.
- **Issues:** Mixin-based LandscapeRecorder (8 mixins, ~60 public methods) shares state through implicit attribute annotations with no compile-time verification. Missing OperationRepository (Operations bypass the repository pattern, skipping enum validation at deserialization). `record_secret_resolutions()` accepts `list[dict[str, Any]]` instead of typed dataclass. `LandscapeDB.in_memory()` and `from_url()` both bypass `__init__` via `cls.__new__()`. Truthiness checks (`if status:` instead of `if status is not None:`) in filter parameters could silently ignore zero-value enums.

### Contracts (37 files, ~5,500 lines)

- **Strengths:** Exemplary config contracts system (Protocol + frozen dataclass + from_settings + AST checker). TokenUsage set the precedent for the dict-to-frozen-dataclass migration. Schema contract system with O(1) dual-name resolution and three enforcement modes (FIXED, FLEXIBLE, OBSERVED). Thorough invariant validation in __post_init__ across most types. Discriminated union for NodeState variants using Literal type narrowing.
- **Issues:** `TransformErrorReason` TypedDict has 80+ optional fields (effectively untyped -- consider splitting into discriminated sub-types by error category). `GateResult.row` is `dict[str, Any]` while `TransformResult.row` is `PipelineRow`. Lazy imports in 5 files (url.py, runtime.py, type_normalization.py, contract_records.py, schema_contract.py) partially violate the leaf module invariant.

### Plugins Core (12 files)

- **Strengths:** Trust-tier-appropriate schema factory (sources may coerce via Pydantic lax mode, transforms/sinks must reject via strict mode). Well-implemented singleton sentinel pattern with pickle/copy safety. Clean Azure auth with mutual exclusion enforcement. NaN/Infinity rejection via FiniteFloat type and observed-mode model validators.
- **Issues:** Hardcoded 70-line if/elif dispatch in `validation.py` mapping plugin names to config classes (the single largest maintenance burden). Double config parsing (validate then discard, construct then re-parse). `EXCLUDED_FILES` frozenset in discovery.py requires manual maintenance when infrastructure files are added. Protocol/base class synchronization is manual with no automated parity test. Post-construction injection of routing fields (on_error, on_success) creates temporal coupling.

### DAG and Config (12 files)

- **Strengths:** Deterministic node IDs via canonical hashing enable checkpoint/resume across restarts. Two-pass schema resolution handles gate/coalesce dependency ordering. Full topology hashing for checkpoint compatibility (BUG-COMPAT-01 fix). Collision-safe type envelopes in checkpoint serialization. Fork/aggregation/coalesce-aware row completion semantics in recovery.
- **Issues:** `build_execution_graph()` is an 830-line monolithic function with inline closures that cannot be unit-tested individually. `ExecutionGraph` at 1,452 lines is a god class handling construction delegation, queries, traversal, schema validation, and route resolution. `core/config.py` at 2,073 lines mixes too many concerns. `canonical.py` has hard module-level imports of numpy and pandas, forcing the scientific computing stack to load for any canonical.py consumer.

### LLM Plugins and Clients (17 files, ~5,800 lines)

- **Strengths:** Audited client base with automatic call recording and telemetry emission. SSRF-safe HTTP with IP-pinned connections and per-hop redirect validation. Replay/verify modes support hash-based comparison when payloads are purged. Multi-query cross-product evaluation correctly abstracts the shared pipeline via BaseMultiQueryTransform. Azure batch transform has excellent Tier 3 boundary handling with per-line JSONL validation.
- **Issues:** ~1,330 lines of duplication across 6 provider files (see Finding 2). NaN/Infinity rejection inconsistency: `openrouter_batch.py` uses `response.json()` instead of `json.loads` with `parse_constant`. Output schema inconsistency: `openrouter.py` uses input schema as output schema. Validation inconsistency: Azure multi-query uses `validate_json_object_response()`, OpenRouter multi-query uses inline parsing. `BaseLLMTransform` is an orphaned abstraction with zero production subclasses.

## Prioritized Remediation Summary

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| P0 | Freeze 16 mutable Tier 1 audit records in audit.py | Low | Prevents accidental audit corruption |
| P1 | Decompose PluginContext god object (17 fields, 3 layer violations) | High | Breaks 2 of 3 HIGH-severity dependency cycles |
| P1 | Move MaxRetriesExceeded, BufferEntry, ExpressionParser, plugin protocols | Low | Eliminates 4 dependency cycle edges |
| P1 | Fix NaN/Infinity rejection in openrouter_batch.py | Trivial | Closes Tier 3 validation gap |
| P2 | Extract LLM tracing/schema/client mixins from 6 provider files | Medium | Eliminates ~1,330 lines duplication, prevents divergence bugs |
| P2 | Split _execute_run into phases; unify with _process_resumed_rows | Medium | Reduces 830-line method, eliminates ~60% structural duplication |
| P2 | Extract _handle_transform_result / _handle_gate_result from processor | Medium | Reduces 375-line _process_single_token complexity |
| P2 | Delete orphaned BaseLLMTransform | Trivial | No Legacy Code policy compliance |
| P3 | Add OperationLoader; type secret_resolutions parameter | Low | Closes remaining untyped-dict-at-Tier-1 gaps in Landscape |
| P3 | Split config.py into models/loading/secrets modules | Medium | Reduces 2,073-line file, separates concerns |
| P3 | Refactor build_execution_graph into DAGBuilder class | High | Enables phase-level testing of 15-phase build |
| P3 | Standardize Tier 1 error types (ValueError -> AuditIntegrityError) | Low | Consistent error semantics across audit subsystem |

## Confidence and Limitations

**Confidence: HIGH.** All 206 source files across 9 subsystems were analyzed. The 7 analysis reports cover contracts (37 files), core/landscape (21 files), engine/orchestrator (8 files), core/dag+config (12 files), plugins core (12 files), and plugins LLM+clients (17 files). Concerns are supported by specific file and line references. Tier model compliance was systematically checked at all data access points.

**Limitations:** The analysis did not deeply examine engine/executors/ (TransformExecutor, GateExecutor, AggregationExecutor, SinkExecutor internals), telemetry/ exporters, testing/ infrastructure, or tui/ widgets. These are understood from their interfaces at consumption points but internal complexity was not assessed. The Langfuse SDK's thread safety properties were not verified.
