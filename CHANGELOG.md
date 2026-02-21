# Changelog

All notable changes to ELSPETH are documented here.

---

## [0.3.0] - 2026-02-22 (RC-3.2)

### Highlights

- **Schema Contracts** — First-row-inferred field contracts propagated through the DAG and recorded in the audit trail
- **Declarative DAG Wiring** — Every edge explicitly named and validated at construction time
- **PipelineRow** — Typed row wrapper replacing raw dicts throughout the pipeline
- **Test Suite v2** — Complete rewrite with 8,000+ tests across unit, property, integration, E2E, and performance layers
- **178-Bug Triage** — Systematic closure of 160+ bugs across 8 hardening phases

### Added

- Schema contract system: inference, propagation, sink header modes, and audit recording
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
- Frozen dataclass DTOs replacing `dict[str, Any]` at 7 audit trail boundaries
- NaN/Infinity rejection at JSON parse and schema validation boundaries
- Resume row-drop, batch adapter crash, gate-to-gate routing crash
- Telemetry DROP-mode evicting newest instead of oldest events
- AzureBlobSink multi-batch overwrite, CSVSource multiline skip_rows, JSONL multibyte decoding

### Changed

- Orchestrator, LandscapeRecorder, MCP server, and executors decomposed from monoliths into focused modules
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
