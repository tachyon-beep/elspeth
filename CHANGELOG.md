# Changelog

All notable changes to ELSPETH are documented here.

---

## [Unreleased] (RC-3.3 — Architectural Remediation)

4-phase remediation sprint driven by full architecture analysis. Focus: audit integrity hardening, layer enforcement, and elimination of defensive-pattern violations.

### T10: LLM Plugin Consolidation

Collapsed 6 LLM transform classes (~4,950 lines) into a unified `LLMTransform` with provider dispatch, eliminating ~3,300 lines of duplication. Strategy pattern: `LLMProvider` protocol handles transport (Azure SDK vs OpenRouter HTTP), two processing strategies (`SingleQueryStrategy` / `MultiQueryStrategy`) handle row logic, shared `LangfuseTracer` handles tracing.

**Phase A — Extract shared infrastructure (Tasks 1–4):**
- Extracted `LangfuseTracer` to `plugins/llm/langfuse.py` — deduplicated ~600 lines of Langfuse v3 span/generation recording across 6 transforms into factory-created `ActiveLangfuseTracer` / `NoOpLangfuseTracer`
- Extracted shared validation to `plugins/llm/validation.py` — `strip_markdown_fences()`, JSON fence detection
- Extracted prompt template system to `plugins/llm/templates.py` — `PromptTemplate` with file/inline/lookup support and Jinja2 field extraction
- Wired all 6 existing transforms to use extracted utilities (backward-compatible, no behavior change)

**Phase B — Unified transform (Tasks 5–12):**
- Created `LLMProvider` protocol (`plugins/llm/provider.py`) with `FinishReason` enum and typed DTOs
- Implemented `AzureLLMProvider` (`plugins/llm/providers/azure.py`) — wraps OpenAI SDK with Azure Monitor tracing
- Implemented `OpenRouterLLMProvider` (`plugins/llm/providers/openrouter.py`) — wraps httpx with OpenRouter HTTP API
- Relocated config models: `AzureOpenAIConfig` → `providers/azure.py`, `OpenRouterConfig` → `providers/openrouter.py`
- Created unified `LLMTransform` (`plugins/llm/transform.py`) with `_PROVIDERS` registry dispatching to `(ConfigModel, Provider)` pairs by `provider` field
- Updated plugin registration: `"llm"` registered as single transform name; old names (`azure_llm`, `openrouter_llm`, `azure_multi_query_llm`, `openrouter_multi_query_llm`) raise `ValueError` with migration guidance
- Migrated full test suite to unified LLMTransform — all test files updated to use `LLMTransform` with provider configs
- Updated 16 example YAML files: `plugin: azure_llm` → `plugin: llm` + `provider: azure` (batch plugins `azure_batch_llm` / `openrouter_batch_llm` unchanged)
- Updated 10 documentation files (tier2-tracing, configuration, user-manual, troubleshooting, keyvault runbook, ARCHITECTURE, data-trust, feature-inventory, telemetry, environment-variables)
- Deleted 5 old source files: `azure.py`, `openrouter.py`, `base_multi_query.py`, `azure_multi_query.py`, `openrouter_multi_query.py`
- Cleaned 12 stale contracts-whitelist entries and updated scan groups

### Fixed

- **Silent failure remediation (10 findings)** — Comprehensive review of LLM plugin error handling:
  - Langfuse metadata construction moved outside try blocks — our bugs crash immediately, only SDK calls wrapped
  - Missing `langfuse` package now raises `RuntimeError` with install instructions instead of silently returning NoOp tracer
  - Unrecognized tracing config types now emit structlog warning instead of silent no-op
  - Unknown LLM finish reasons now include actionable guidance in warning message
  - Azure no-choices response path now logs warning instead of silent `None` return
  - `azure-ai-inference` ImportError fallback now logs warning
  - Telemetry callback pre-start replaced `lambda: None` with warning function
  - Missing LLM output fields now return `TransformResult.error()` with field details instead of silent `None` via `.get()`
  - Null LLM content (content-filtered) now returns error with `content_filtered` reason instead of storing `None`
- **Unified LLM transform bugs** — Fixed four bugs in `LLMTransform`: limiter dispatch used wrong config attribute, `response_format` not passed to provider, declared `output_fields` not extracted from multi-query responses, NaN/Infinity values in LLM JSON responses not rejected
- **Aggregation `on_error` required** — `on_error` is now required for aggregation transforms; converted multi-query examples to unified LLM format
- **T1: Frozen audit records** — Added `frozen=True` to all 16 mutable audit record dataclasses (`Run`, `Node`, `Edge`, `Row`, `Token`, `TokenParent`, `Call`, `Artifact`, `RoutingEvent`, `Batch`, `BatchMember`, `BatchOutput`, `Checkpoint`, `RowLineage`, `ValidationErrorRecord`, `TransformErrorRecord`). All 24 dataclasses in `contracts/audit.py` are now frozen. Mutations crash at the mutation site instead of silently corrupting the Tier 1 audit trail.
- **T2: Assert removal** — Replaced 18 `assert` statements across 10 plugin files with explicit `if/raise RuntimeError` patterns. Asserts are stripped by `python -O`, silently removing safety checks. Files: `web_scrape.py` (5), `azure.py` (2), `openrouter.py` (1), `openrouter_batch.py` (2), `azure_multi_query.py` (2), `openrouter_multi_query.py` (2), `content_safety.py` (1), `pooling/executor.py` (1), `csv_sink.py` (1), `base_multi_query.py` (1).
- **T3: Truthiness checks** — Fixed 21 truthiness checks across 8 files. Python's `if x:` and `x or default` silently exclude valid zero values (`0`, `0.0`) and empty strings (`""`). All replaced with explicit `is not None` checks:
  - `reports.py`: High-variance node filter now includes 0-duration nodes
  - `spans.py`: 8 span attribute checks (`node_id`, `input_hash`, `batch_id`)
  - `node_detail.py`: 7 TUI display fallbacks preserve empty strings and zero durations
  - `processor.py`: `duration_ms` recording preserves `0.0`
  - `plugin_context.py`: `latency_ms` recording preserves `0.0`
  - `chaosllm/server.py`, `chaosweb/server.py`: `extra_delay_sec` arithmetic
  - `chaosllm_mcp/server.py`: 5 metrics aggregation values
- **T6: ExpressionParser layer violation** — Moved `ExpressionParser` from `engine/` to `core/` to resolve `core/config.py` importing from `engine/` (L1→L2 violation)
- **T7: Cross-layer contract imports** — Moved `MaxRetriesExceeded` to `contracts/errors.py` and `BufferEntry` to `contracts/engine.py` to resolve `contracts/` importing from `engine/` and `plugins/` (L0→L2 and L0→L3 violations)
- **RuntimeServiceRateLimit** — New frozen dataclass in `contracts/config/` replaces runtime import of `core.config.ServiceRateLimit` (L0→L1 violation in `RuntimeRateLimitConfig.get_service_config`)

### Changed

- Extracted `contracts/hashing.py` — primitive-only `canonical_json`, `stable_hash`, and `repr_hash` (RFC 8785 + hashlib, no pandas/numpy). Breaks mutual circular dependency between `contracts/` and `core/canonical.py`. `CANONICAL_VERSION` now lives in contracts; `core/canonical.py` imports from there.
- All imports updated across 33 files for layer violation remediation
- CI/CD tier-model allowlists and contract fingerprints updated for relocated modules

### Added

- **ADR-006**: Layer Dependency Remediation — documents the strict 4-layer model (`contracts → core → engine → plugins`) and the 10→0 violation fix strategy
- Full architecture analysis (`docs/arch-analysis-2026-02-22-0446/`) — 26 documents covering subsystem catalog, dependency matrix, C4 diagrams, architect handover brief, and per-subsystem analysis for all 13 subsystems
- Freeze audit dataclasses plan (`docs/plans/2026-02-22-freeze-audit-dataclasses.md`)
- `TestFrozenDataclassImmutability` extended to cover all 22 frozen types (6 existing + 16 newly frozen)
- 10 new truthiness regression tests across `test_reports.py`, `test_spans.py`, `test_node_detail.py`
- T17 PluginContext protocol split design doc and hierarchical implementation plan (master + 5 sub-plans)
- Backpressure modes and import hierarchy documentation in architecture docs
- `available_fields` key in `TransformErrorReason` TypedDict for LLM output field mismatch diagnostics
- 65 new tests for review-identified coverage gaps: error serialization dispatch (33), provider lifecycle (9), JSON validation (16), PluginContext record_call wrapping (5), GateExecutor error field rename (2)

### Tests

- Full suite: 10,040 tests passing, 16 skipped, 3 xfailed — mypy/ruff/contracts all clean
- T10: 10 test files updated with import path migrations from old modules to `providers/`
- T10: `test_discovery.py` updated — plugin count 17→13, assertions reference unified `llm` + batch plugins
- T10: `test_contract_validation.py` updated — 5 plugin name references migrated to `"llm"`

---

## [0.3.0] - 2026-02-22 (RC-3.2)

### Highlights

- **Schema Contracts** — First-row-inferred field contracts propagated through the DAG and recorded in the audit trail
- **Declarative DAG Wiring** — Every edge explicitly named and validated at construction time
- **PipelineRow** — Typed row wrapper replacing raw dicts throughout the pipeline
- **Strict Typing at Audit Boundaries** — Every `dict[str, Any]` crossing into the Landscape audit trail replaced with frozen dataclasses, eliminating an entire class of silent data-corruption bugs
- **Test Suite v2** — Complete rewrite with 8,000+ tests across unit, property, integration, E2E, and performance layers
- **178-Bug Triage** — Systematic closure of 160+ bugs across 8 hardening phases

### Added

- Schema contract system: inference, propagation, sink header modes, and audit recording
- `BatchCheckpointState` frozen dataclass replacing untyped checkpoint dicts in batch LLM transforms
- `WebOutcomeClassification` NamedTuple replacing positional 8-boolean tuple in ChaosWeb metrics
- `NodeStateGuard` context manager enforcing terminal-state invariants in all executors
- `detect_field_collisions()` utility preventing silent data overwrites across all transforms
- `GateEvaluationContext` and `AggregationFlushContext` typed DTOs for executor context passing
- `CallPayload` protocol with `LLMCallRequest/Response`, `HTTPCallRequest/Response` typed payloads
- `NodeStateContext`, `CoalesceMetadata`, `AggregationCheckpointState` frozen dataclasses at audit boundaries
- `TokenUsage` dataclass replacing fabricated-zero dicts in usage tracking
- Azure Key Vault secrets backend with audit trail
- SQLCipher encryption-at-rest for the Landscape database
- WebScrape transform with SSRF prevention and content fingerprinting
- ChaosWeb fake server for stress-testing HTTP transforms
- Langfuse v3 tracing for LLM plugins
- Per-branch transforms between fork and coalesce nodes
- Graceful shutdown (SIGINT/SIGTERM) for run and resume paths
- Field collision detection preventing silent data loss in transforms
- DIVERT routing for quarantine/error sink paths
- 5 new example pipelines

### Fixed

- **P0:** DNS rebinding TOCTOU in SSRF, JSON sink data loss on crash, content safety / prompt shield fail-open
- Frozen dataclass DTOs replacing `dict[str, Any]` at 10+ audit trail boundaries — eliminates runtime KeyError risk and tier-model allowlist entries
- `PluginContext.update_checkpoint()` replaced with `set_checkpoint()` (replacement semantics) — fixes P1 bug where dict merge lost checkpoint updates on restored batch state
- NaN/Infinity rejection at JSON parse and schema validation boundaries
- Resume row-drop, batch adapter crash, gate-to-gate routing crash
- Telemetry DROP-mode evicting newest instead of oldest events
- SharedBatchAdapter duplicate-emit race condition (first-result-wins preserved)
- Parallel dict consolidation in `ExecutionGraph`, `AggregationExecutor`, `_PendingCoalesce`, `SharedBatchAdapter` — each replaced with typed dataclass
- AzureBlobSink multi-batch overwrite, CSVSource multiline skip_rows, JSONL multibyte decoding

### Changed

- Orchestrator, LandscapeRecorder, MCP server, and executors decomposed from monoliths into focused modules
- Checkpoint API typed: `get_checkpoint()` returns `BatchCheckpointState | None`, `set_checkpoint()` accepts typed state
- Batch transform checkpoint data no longer serialized/deserialized through `dict` — `RowMappingEntry` promoted from module-private to contracts
- Pre-commit hooks scan full codebase (12 hooks, check-only)
- docs/ restructured from 792 files to 62 files
- All Alembic migrations deleted (pre-release, no users)

### Removed

- Gate plugin subsystem — routing is now config-driven only
- Beads (bd) issue tracker — migrated to Filigree
- V1 test suite (7,487 tests, 222K lines) — replaced by v2
- Dead plugin protocols (CoalesceProtocol, GateProtocol, PluginProtocol)
- `_RowMappingEntry` from azure_batch.py — replaced by `RowMappingEntry` in contracts
- 9 tier-model allowlist entries eliminated by typed checkpoint DTOs

---

## [0.1.0] - 2026-02-02 (RC-2)

Initial release candidate. Core SDA pipeline engine with audit trail,
plugin system, and CLI.

[0.3.0]: https://github.com/tachyon-beep/elspeth/compare/v0.1.0-phase1...main
[0.1.0]: https://github.com/tachyon-beep/elspeth/releases/tag/v0.1.0-phase1
