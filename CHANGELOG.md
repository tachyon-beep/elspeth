# Changelog

All notable changes to ELSPETH are documented here.

---

## [Unreleased] (RC-3.3 — Architectural Remediation)

4-phase remediation sprint driven by full architecture analysis. Focus: audit integrity hardening, layer enforcement, and elimination of defensive-pattern violations.

### T10: LLM Plugin Consolidation

Collapsed 6 LLM transform classes (~4,950 lines) into a unified `LLMTransform` with provider dispatch, eliminating ~3,300 lines of duplication. Strategy pattern: `LLMProvider` protocol handles transport (Azure SDK vs OpenRouter HTTP), two processing strategies (`SingleQueryStrategy` / `MultiQueryStrategy`) handle row logic, shared `LangfuseTracer` handles tracing.

- Extracted shared infrastructure: `LangfuseTracer` (~600 lines deduplicated), `PromptTemplate` system, validation utilities
- Created `LLMProvider` protocol with `AzureLLMProvider` and `OpenRouterLLMProvider` implementations
- Single plugin registration: `plugin: llm` + `provider: azure|openrouter`; old names raise `ValueError` with migration guidance
- Deleted 5 old source files, updated 16 example YAMLs and 10 documentation files

### T17: PluginContext Protocol Split

Decomposed the god-object `PluginContext` (20+ fields) into 4 phase-based protocols in `contracts/contexts.py` — `SourceContext`, `TransformContext`, `SinkContext`, `LifecycleContext` — narrowing each plugin method signature to only the fields that pipeline phase actually needs. Concrete `PluginContext` structurally satisfies all 4 protocols; engine executors mutate concrete fields between steps while plugins see read-only views via protocol typing. 23 plugin files updated.

### T18: Orchestrator/Processor Decomposition

Pure extract-method refactoring of the two largest engine files, reducing maximum method size to ≤150 lines with no behavior change. Extracted 7 methods from `orchestrator/core.py` and 3 from `processor.py`. Introduced typed parameter bundles (`GraphArtifacts`, `RunContext`, `LoopContext`) and discriminated union types for transform/gate outcomes.

### T19: Landscape Repository Pattern

Refactored `LandscapeRecorder` from 8 mixins into 4 composed domain repositories — `RunLifecycleRepository`, `ExecutionRepository`, `DataFlowRepository`, `QueryRepository` — split by pipeline-phase domain. `LandscapeRecorder` is now a pure delegation facade (~91 public methods, zero logic).

### Plugins Restructure (SDA Alignment)

Reorganized the flat `plugins/` directory into 4 SDA-aligned subfolders: `infrastructure/` (shared base classes, clients, batching, pooling), `sources/`, `transforms/`, `sinks/`. 247 files changed, ~200 imports rewritten.

### Protocol Relocation (L3→L0)

Moved `SourceProtocol`, `TransformProtocol`, `SinkProtocol`, `BatchTransformProtocol`, and `GateResult` from `plugins/infrastructure/` (L3) to `contracts/` (L0). Eliminates the engine→plugins layer violation that forced L2 code to import from L3.

### Fixed

- **Frozen audit records** — Added `frozen=True, slots=True` to all 16 mutable audit record dataclasses in `contracts/audit.py`. Mutations now crash at the mutation site instead of silently corrupting the Tier 1 audit trail.
- **FrameworkBugError/AuditIntegrityError re-raise** — Added explicit re-raise before all broad `except Exception` handlers (13 sites across 7 files). System-level errors now always propagate.
- **Silent failure remediation** — Comprehensive review of error handling across LLM plugins and plugin infrastructure. Silent fallbacks converted to proper exceptions or `TransformResult.error()` with diagnostic context. Missing optional packages now raise `RuntimeError` with install instructions instead of silently degrading.
- **azure_batch silent passthrough** — `_process_single` else branch now raises `RuntimeError` instead of silently passing through unprocessed rows as "processed", matching the hardened pattern in `openrouter_batch`.
- **Assert removal** — Replaced 18 `assert` statements across 10 plugin files with explicit `if/raise RuntimeError`. Asserts are stripped by `python -O`, silently removing safety checks.
- **Truthiness checks** — Fixed 21 `if x:` / `x or default` patterns across 8 files that silently excluded valid zero values and empty strings. All replaced with explicit `is not None` checks.
- **LLM transform bugs** — Fixed limiter dispatch using wrong config attribute, `response_format` not passed to provider, `output_fields` not extracted from multi-query responses, NaN/Infinity not rejected in LLM JSON responses
- **Layer violations resolved** — Moved `ExpressionParser` from `engine/` to `core/`, `MaxRetriesExceeded` and `BufferEntry` to `contracts/`, created `RuntimeServiceRateLimit` in `contracts/config/`. 10 upward import violations → 0.

### Changed

- Extracted `contracts/hashing.py` — primitive-only `canonical_json`, `stable_hash`, and `repr_hash` (RFC 8785 + hashlib, no pandas/numpy). Breaks circular dependency between `contracts/` and `core/canonical.py`.
- Aggregation `on_error` is now required for aggregation transforms
- DTO mapper classes renamed from `*Repository` to `*Loader` to avoid confusion with new domain repositories

### Added

- **ADR-006**: Layer Dependency Remediation — documents the strict 4-layer model and CI enforcement strategy
- Full architecture analysis (23 documents covering all 13 subsystems)
- ~75 new tests for hardening coverage (frozen dataclass immutability, truthiness regressions, error serialization, provider lifecycle, JSON validation)

### Tests

- Full suite: 10,482 tests collected, 16 skipped, 3 xfailed — mypy/ruff/contracts all clean

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
- Typed DTOs at audit boundaries: `BatchCheckpointState`, `WebOutcomeClassification`, `NodeStateContext`, `CoalesceMetadata`, `AggregationCheckpointState`, `TokenUsage`, `GateEvaluationContext`, `AggregationFlushContext`, `CallPayload` protocol with typed request/response pairs
- `NodeStateGuard` context manager enforcing terminal-state invariants in all executors
- `detect_field_collisions()` utility preventing silent data overwrites across all transforms
- Azure Key Vault secrets backend with audit trail
- SQLCipher encryption-at-rest for the Landscape database
- WebScrape transform with SSRF prevention and content fingerprinting
- ChaosWeb fake server for stress-testing HTTP transforms
- Langfuse v3 tracing for LLM plugins
- Per-branch transforms between fork and coalesce nodes
- Graceful shutdown (SIGINT/SIGTERM) for run and resume paths
- DIVERT routing for quarantine/error sink paths

### Fixed

- **P0:** DNS rebinding TOCTOU in SSRF, JSON sink data loss on crash, content safety / prompt shield fail-open
- Frozen dataclass DTOs replacing `dict[str, Any]` at 10+ audit trail boundaries — eliminates runtime KeyError risk and tier-model allowlist entries
- `PluginContext.update_checkpoint()` replaced with `set_checkpoint()` (replacement semantics) — fixes P1 bug where dict merge lost checkpoint updates on restored batch state
- NaN/Infinity rejection at JSON parse and schema validation boundaries
- Resume row-drop, batch adapter crash, gate-to-gate routing crash
- Telemetry DROP-mode evicting newest instead of oldest events
- SharedBatchAdapter duplicate-emit race condition (first-result-wins preserved)
- AzureBlobSink multi-batch overwrite, CSVSource multiline skip_rows, JSONL multibyte decoding

### Changed

- Orchestrator, LandscapeRecorder, MCP server, and executors decomposed from monoliths into focused modules
- Checkpoint API typed: `get_checkpoint()` returns `BatchCheckpointState | None`, `set_checkpoint()` accepts typed state
- Pre-commit hooks scan full codebase (12 hooks, check-only)
- docs/ restructured from 792 files to 62 files
- All Alembic migrations deleted (pre-release, no users)

### Removed

- Gate plugin subsystem — routing is now config-driven only
- Beads (bd) issue tracker — migrated to Filigree
- V1 test suite (7,487 tests, 222K lines) — replaced by v2
- Dead plugin protocols (CoalesceProtocol, GateProtocol, PluginProtocol)

---

## [0.1.0] - 2026-02-02 (RC-2)

Initial release candidate. Core SDA pipeline engine with audit trail,
plugin system, and CLI.

[0.3.0]: https://github.com/tachyon-beep/elspeth/compare/v0.1.0-phase1...main
[0.1.0]: https://github.com/tachyon-beep/elspeth/releases/tag/v0.1.0-phase1
