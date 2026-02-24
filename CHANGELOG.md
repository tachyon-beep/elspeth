# Changelog

All notable changes to ELSPETH are documented here.

---

## [Unreleased] (RC-3.3 — Architectural Remediation)

### Fixed

- **T1:** Frozen all 16 mutable audit record dataclasses — prevents accidental mutation of Tier 1 audit data
- **T2:** Replaced 18 `assert` statements in production plugin code with explicit `raise` — asserts are stripped by `python -O`
- **T3:** Fixed 21 truthiness checks across 8 files — `if x:` and `x or default` replaced with `is not None` checks to preserve valid zero/empty-string values in performance reports, telemetry spans, TUI display, audit recording, and testing infrastructure
- Resolved 3 layer violations (T6, T7, RuntimeServiceRateLimit) — strict 4-layer dependency enforcement

### Changed

- Extracted `contracts/hashing.py` — breaks mutual circular dependency between `contracts/` and `core/canonical.py`

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
