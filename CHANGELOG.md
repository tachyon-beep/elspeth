# Changelog

All notable changes to ELSPETH are documented here.

---

## [0.3.4] (RC-3.4 — Systematic Hardening)

Systematic hardening sprint driven by 191-bug triage, mutation testing, and code quality sweep. Focus: audit integrity, deep immutability, construction-time validation, exception hygiene, and elimination of defensive anti-patterns. No new features — pure correctness and reliability work.

### Fixed

#### Audit Integrity & Tier 1 Hardening

- **PayloadNotFoundError domain exception** — `PayloadStore` protocol, `FilesystemPayloadStore`, and `MockPayloadStore` now raise `PayloadNotFoundError` instead of generic `KeyError`, preventing accidental catch by `except KeyError:` dict-lookup handlers. All five caller sites updated. PURGED paths now emit debug logs with `content_hash` for operational visibility.
- **PayloadIntegrityError → AuditIntegrityError** — `get_call_response_data` now catches `PayloadIntegrityError` and translates to `AuditIntegrityError` with run/call context, instead of letting raw integrity errors escape the landscape layer.
- **AuditIntegrityError for Tier 1 corruption** — Lineage queries, edge lookups, and purge grade updates now raise `AuditIntegrityError` instead of generic `ValueError` when encountering corrupt audit data.
- **Silent default=str fallback removed** — Journal serialization no longer silently coerces unserializable types via `default=str`. Non-serializable data now crashes immediately, exposing the upstream bug.
- **BatchCheckpointState tuple restoration** — `from_dict()` now restores tuple types after JSON round-trip instead of leaving them as lists, preserving Tier 1 checkpoint invariants.
- **Null-content LLM responses recorded** — Null-content responses are now recorded in the audit trail before raising, closing an audit gap where failed LLM calls left no trace.
- **Exception type hygiene** — `ValueError` replaced with `AuditIntegrityError` or `OrchestrationInvariantError` at 12 sites where the generic type misrepresented the failure category.
- **Tier 1 invariants in graph.py** — DAG graph now crashes on invalid source count, missing route labels, and defensive `.get()` patterns that masked corruption.
- **Programming-error guards in exporters** — Exporters and journal now raise `AuditIntegrityError` or `FrameworkBugError` instead of silently continuing on corrupt state.
- **Dead `ExecutionError.from_dict()` deleted** — Removed dead deserialization method; `TokenUsage.from_dict()` now rejects bool values that would silently coerce to int.

#### Deep Immutability & Frozen Dataclass Hardening

- **Central freeze/thaw utilities** — New `deep_freeze()` and `deep_thaw()` functions standardize immutability across all frozen dataclasses, replacing ad-hoc `deepcopy` calls.
- **deep_freeze recursion** — Now recurses into tuples, frozensets, and `MappingProxyType` contents, closing gaps where nested mutable containers survived freezing.
- **Mutable dict fields frozen** — All frozen checkpoint dataclasses now freeze mutable dict fields at construction, preventing post-construction mutation of Tier 1 data.
- **Category A mutable-frozen bugs** — Enforced deep immutability on 5 frozen dataclasses where mutable fields were exposed.
- **Category B mutable-frozen bugs** — Froze 5 additional DTOs with mutable internal state.
- **`slots=True` on all frozen dataclasses** — Added `slots=True` to `ResumeCheck`, `ResumePoint`, `RowDataResult`, `_GateEntry`, and all remaining frozen dataclasses that lacked it.
- **Contracts layer hardened** — Frozen sets, `deep_freeze` over `deepcopy`, `AuditIntegrityError` for checkpoint corruption.
- **HTTP DTO headers copied before freezing** — Prevents shared mutable header dicts from being modified after DTO construction.
- **Frozen constants and LineageResult** — Immutability hardened across engine constants and lineage query results.
- **Frozen/shared data structure enforcement** — Cleared `cluster:mutable-frozen` bug cluster.

#### Construction-Time Validation (`__post_init__`)

- **12 frozen dataclass types validated** — Added `__post_init__` validation enforcing invariants at construction time across contracts and engine types.
- **Remaining `cluster:missing-post-init` types** — Completed validation coverage for all frozen dataclasses that lacked construction-time checks.
- **NaN bypass and generator truthiness** — Fixed `__post_init__` validators that failed to detect NaN values and generators that evaluated truthy regardless of content.
- **Coalesce checkpoint DTO validation** — `CoalesceTokenCheckpoint` and `CoalescePendingCheckpoint` now enforce non-empty identifiers, non-negative timing, dict types, and disjoint branch keys.
- **Config-time validation** — Added validation for free-string fields, encoding, delimiters, and cross-field invariants at settings load time, clearing `cluster:config-validation`.

#### Exception Handling Hygiene

- **Exception chains preserved** — Replaced `from None` with `from exc` across 16 files, preserving diagnostic context in exception chains.
- **5 broken exception chains repaired** — Fixed `raise X from None` patterns in engine, plugins, and CLI that destroyed root-cause information.
- **22 broad `except Exception` catches narrowed** — Replaced overly broad catches with specific exception types, clearing `cluster:broad-except`.
- **Missing programming-error re-raises** — Added `FrameworkBugError`/`AuditIntegrityError` re-raise guards to telemetry `except` blocks that swallowed system errors.
- **Generic exceptions replaced** — Domain-specific error types (`AuditIntegrityError`, `GraphValidationError`, `OrchestrationInvariantError`) replace generic `ValueError`/`RuntimeError`, clearing `cluster:wrong-exception-type`.
- **Silent skips → explicit crashes** — 6 audit-gap bugs where code silently returned on invalid state now crash with invariant violation messages.

#### Defensive Pattern Removal

- **`hasattr()` banned unconditionally** — All 3 occurrences replaced with type-safe alternatives. `hasattr` is no longer allowlistable in the tier model enforcer.
- **Defensive `.get()` → required-fields validation** — `AggregationNodeCheckpoint.from_dict()` and other Tier 1 deserializers now validate required fields explicitly instead of using `.get()` with defaults.
- **Defensive access patterns removed** — Two passes across typed and Tier 1 data, replacing `.get(key, default)` with direct access on data we own.
- **CUSTOM header mode fail-closed** — Sink header mode `CUSTOM` now raises on unmapped fields instead of silently falling back to normalized names.

#### Data Fabrication Elimination

- **10 `cluster:fabrication` bugs fixed** — Replaced fabricated defaults (`None` → `0`, missing → empty string) with explicit validation or propagation of absence.
- **LLM batch, DB sink, and coalesce fabrication** — Eliminated silent default injection in three additional paths where missing data was replaced with invented values.

#### Audit-Gap Bug Fixes

- **4 TOCTOU races, silent blank rows, checkpoint invariant** — Fixed race conditions in concurrent audit writes and checkpoint state transitions.
- **3 credential leak, buffer corruption, record ordering** — Closed credential exposure in error messages, buffer mutation after read, and out-of-order audit record insertion.
- **2 rowcount validation, dict mutation** — Added rowcount assertions for fork/coalesce/expand writes; fixed in-place dict mutation in sequential multi-query.
- **4 row_data serialization, replayer Tier 1 reads** — Protected row_data from mutation during serialization; hardened replayer reads to crash on corruption.
- **Audit-gap silent failures recorded** — Error file download, malformed JSONL, and batch quarantine now record failures instead of silently dropping them.

#### Plugin & Engine Fixes

- **`_prepare_call_payloads` extracted** — Deduplicates payload preparation between `record_call` and `record_operation_call`.
- **`_make_checkpoint_after_sink_factory` extracted** — Deduplicates checkpoint-after-sink closure across orchestrator paths.
- **`dataclass_to_dict` tuple handling** — Now handles tuples correctly; fixed `has_retries` off-by-one comparison.
- **Azure client close-before-null** — `CallDataResult` discriminated type replaces ambiguous `None` return from Azure client operations.
- **Missing fingerprint key crashes** — Auth header fingerprinting now crashes on missing key instead of silently skipping; non-finite row indices recorded in batch stats.
- **Broken output port and shutdown timeout** — Batch mixin now crashes on broken output ports and respects shutdown timeout instead of silently continuing.
- **Purge grade updates wrapped individually** — Prevents stale grades after partial payload deletion.
- **Absent finish_reason accepted** — LLM responses with no `finish_reason` field (distinct from non-STOP values) are now accepted; Azure batch file ID guards added.
- **Per-query templates pre-compiled at init** — Separates structural errors (config, caught at startup) from operational errors (per-row, caught at render).
- **Coalesce `_completed_keys` for late arrivals** — Late-arriving tokens after resume are now correctly detected via completed-keys tracking.
- **Route-label enforcement at construction** — Moved from runtime lookup to DAG construction time; `get_route_label()` simplified.
- **`select_branch` KeyError wrapped** — Now raises `GraphValidationError` with context instead of bare `KeyError`.
- **`_get_node()` extracted in AggregationExecutor** — Unifies node validation, removes dead code.

#### Type Design

- **22 type-design bugs fixed** — 14 across engine, contracts, and plugins; 8 across engine, landscape, plugins, and verifier. Tightened field types, added missing validation, removed dead fields.
- **Checkpoint and call_data contracts hardened** — Type design improvements in checkpoint and call_data contract types.

#### Logging & Telemetry

- **stdlib logging → structlog** — Replaced in batch mixin, multi_query, azure_blob_source, and azure_batch.
- **Telemetry emitted before null-content raise** — Telemetry events are now emitted before raising on null-content LLM responses, closing an observability gap.
- **Journal payload load errors caught** — Journal now catches and translates `PayloadNotFoundError` and `OSError` from payload store with diagnostic context.
- **LLM finish-reason fail-closed** — Restructured `_finish_reason_error` from blocklist to allowlist (accept only `STOP` and absent). Unknown finish reasons now rejected as non-retryable errors.
- **Shutdown checkpoint skip logging** — `_checkpoint_interrupted_progress` emits structured `shutdown_checkpoint_skipped` warning with diagnostic context instead of silently returning.
- **Schema epoch directional guard** — `_sync_sqlite_schema_epoch` raises `SchemaCompatibilityError` on future epochs instead of silently downgrading.
- **Checkpoint recovery type annotation** — `_get_buffered_checkpoint_token_ids` parameter typed as `Checkpoint` instead of `Any`.
- **SQLite read-only audit inspection** — `LandscapeDB.from_url(..., create_tables=False)` no longer stamps `PRAGMA user_version`, preserving forensic access.

#### Test Infrastructure (ChaosLLM/ChaosWeb)

- **Malformed header overrides** — ChaosLLM and ChaosWeb now handle malformed header overrides gracefully instead of crashing the test server.
- **ChaosLLM template pre-compilation** — Templates pre-compiled at init for faster test execution.
- **Flaky purge test fixed** — `test_grade_update_failures_logged` used `capsys` which is unreliable when prior tests reconfigure structlog; switched to `structlog.testing.capture_logs()`.

### Changed

- `isinstance` allowlist compacted from flat entries into per-file rules with `max_hits` caps
- Code review findings remediated — frozen field access, `deep_thaw` frozenset, DTO validation

### Added

- **Agentic code threat model discussion paper** — Comprehensive research paper covering forward analysis for agentic security, control strength hierarchy, incentive misalignment analysis, ISM control citations, and ACF framework. Multiple revisions through v0.3 with LaTeX build pipeline and DTA brand guidelines.
- **`PayloadNotFoundError`** — Domain exception in `PayloadStore` protocol, replacing generic `KeyError` for missing payload lookups.
- **`CallDataResult` discriminated type** — Replaces ambiguous `None` returns from Azure client data operations.
- DAG validation tests for route-label and sink-map invariants
- Coalesce checkpoint unit tests for `_get_buffered_checkpoint_token_ids` and `restore_from_checkpoint` rejection paths

### Removed

- Dead lifecycle hooks, stale comments, unused imports across engine and plugins
- Dead code and process-tracking comments in ChaosLLM and ChaosWeb
- Dead code, tombstone comments, and process-tracking prefixes across codebase

### Tests

- 6 P0 mutation survivors killed across canonical, lineage, tokens, triggers, and coalesce
- 15 P1 mutation survivors killed across topology, lineage, tokens, triggers, coalesce, payload, exporter, executors, and outcomes
- 9 test-gap bugs closed with 25 new tests across executors, coalesce, DAG, sinks, and plugins
- 2 remaining test-gap bugs closed — purge command and MCP analyzer queries

---

## [0.3.3] (RC-3.3 — Architectural Remediation)

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

- **Pending coalesce resume gaps** — Added typed coalesce checkpoint DTOs, persisted pending coalesce state in checkpoint records, restored coalesce barriers on resume, and taught recovery to exclude buffered coalesce tokens from replay. Graceful shutdown can now resume fork/join pipelines without losing pending joins or replaying already-buffered rows.
- **Interrupted resume checkpoint ordering** — Resumed runs now rebase checkpoint sequence numbers from the previous resume point before writing fresh checkpoints, so a second interrupted resume continues from the newest durable progress marker instead of falling back to an older checkpoint.
- **SQLite schema compatibility posture** — Replaced the ad hoc `checkpoints.coalesce_state_json` required-column gate with an explicit SQLite schema epoch stamp via `PRAGMA user_version`, preserving intentional pre-1.0 schema breaks while keeping a clear future migration seam.
- **Buffered-only resume shutdown semantics** — Resume now honors a pre-set shutdown signal before any end-of-source aggregation/coalesce flushes, so buffered-only checkpoints are re-checkpointed for another resume instead of being flushed to sinks.
- **Frozen audit records** — Added `frozen=True, slots=True` to all 16 mutable audit record dataclasses in `contracts/audit.py`. Mutations now crash at the mutation site instead of silently corrupting the Tier 1 audit trail.
- **FrameworkBugError/AuditIntegrityError re-raise** — Added explicit re-raise before all broad `except Exception` handlers (13 sites across 7 files). System-level errors now always propagate. Structural AST test enforces bare `raise` pattern at all 17 guard sites.
- **Silent failure remediation** — Comprehensive review of error handling across LLM plugins and plugin infrastructure. Silent fallbacks converted to proper exceptions or `TransformResult.error()` with diagnostic context. Missing optional packages now raise `RuntimeError` with install instructions instead of silently degrading.
- **azure_batch silent passthrough** — `_process_single` else branch now raises `RuntimeError` instead of silently passing through unprocessed rows as "processed", matching the hardened pattern in `openrouter_batch`.
- **Assert removal** — Replaced 18 `assert` statements across 10 plugin files with explicit `if/raise RuntimeError`. Asserts are stripped by `python -O`, silently removing safety checks.
- **Truthiness checks** — Fixed 21 `if x:` / `x or default` patterns across 8 files that silently excluded valid zero values and empty strings. All replaced with explicit `is not None` checks.
- **LLM transform bugs** — Fixed limiter dispatch using wrong config attribute, `response_format` not passed to provider, `output_fields` not extracted from multi-query responses, NaN/Infinity not rejected in LLM JSON responses
- **Layer violations resolved** — Moved `ExpressionParser` from `engine/` to `core/`, `MaxRetriesExceeded` and `BufferEntry` to `contracts/`, created `RuntimeServiceRateLimit` in `contracts/config/`. 10 upward import violations → 0.
- **OpenRouter parallel query client race** — Parallel multi-query runs shared a cached `AuditedHTTPClient` by `state_id`; first query to finish destroyed the transport for siblings. Added reference counting so client closes only when last query releases it.
- **Aggregation BUFFERED lifecycle gap** — Triggering token on count-threshold flush skipped `BUFFERED` and went directly to terminal. Moved `BUFFERED` recording before `should_flush()` check so every aggregation token follows `BUFFERED` → terminal.
- **BatchReplicate quarantine audit gap** — Buffer-time recording changed from `CONSUMED_IN_BATCH` (terminal) to `BUFFERED` (non-terminal) for transform-mode aggregation, enabling per-token `QUARANTINED` recording when batch transforms quarantine individual rows.
- **KeywordFilter fail-closed on non-string values** — Security transform was silently passing non-string values in explicitly configured fields (fail-open). Now returns error with `reason='non_string_field'`.
- **Multi-query regressions from T10** — Restored field type validation against declared `output_fields` type/enum constraints; restored pooled execution with AIMD capacity backoff; fixed Pydantic schema missing `output_fields`; fixed `_output_schema_config` using unprefixed single-query fields.
- **LLM empty/whitespace content detection** — Azure and OpenRouter providers now raise `ContentPolicyError` for empty or whitespace-only content before `LLMQueryResult` construction.
- **LLM content-filter finish reason fail-open** — Unified single-query and multi-query `LLMTransform` paths now treat `finish_reason=content_filter` as `reason='content_filtered'` instead of recording provider-filtered fallback text as successful output.
- **Telemetry/Landscape hash divergence** — Telemetry hashes now read from recorded `Call` object instead of recomputing independently, eliminating divergence for datetime/Decimal/bytes/numpy payloads.
- **URL password fingerprint encoding** — Fingerprinting now decodes percent-encoding before HMAC, so fingerprint represents the actual secret, not the URL-encoded form.
- **TUI coalesce error crash on older records** — `_validate_coalesce_error` crashed with `KeyError` on pre-RC3.3 records. Added schema shape detection; older records render with degraded-format note.
- **Graceful shutdown end-of-source synthesis** — Interrupted runs no longer force `END_OF_SOURCE` aggregation flushes or resolve pending coalesces just because shutdown arrived after the current row.
- **Graceful shutdown resumability for buffered pipelines** — Interrupted aggregation/coalesce runs now persist a shutdown checkpoint before raising, so buffered state remains resumable even when no sink token was written yet.
- **CLI explain passphrase silently swallowed** (T4) — YAML parse errors when `--settings` was explicitly provided now exit with code 1 and clear error message.
- **MCP `diagnose()` quarantine count unscoped** (T5) — Was counting all historical runs; now scoped to last 24 hours, matching "what's broken right now?" purpose.
- **ChaosLLM MCP CLI broken** (T27) — Called nonexistent `serve()` instead of `run_server()`, masked by `# type: ignore` comments.
- **Azure AI tracing silent no-op** — Wired `_configure_azure_monitor()` into `LLMTransform.on_start()` with provider compatibility validation (Azure-only); replaced broad `except TypeError` with explicit `None` check so real SDK errors propagate.
- **Contract-level fixes** — `Token.run_id` false optional removed; `CoalesceFailureReason` TypedDict replaced with frozen dataclass (3 dead fields deleted, 4 fields made required); dead `version` parameter removed from `stable_hash()`; Call XOR invariant (`state_id` vs `operation_id`) now enforced at construction; `RawCallPayload.to_dict()` returns shallow copy per immutability contract; `SanitizedDatabaseUrl` rewrote DSN handling to use `urllib.parse` (keeping `contracts/` a leaf layer).
- **Code review remediation** — 4 critical (provider key validation split, `REPR_FALLBACK` row data state, `AuditIntegrityError` in `ExecutionError.from_dict()`, type-narrow `_convert_retryable_to_error_result`), 8 important, 6 suggestion fixes.
- **CI/CD failures resolved** — ruff lint/format, mypy stale `type: ignore`, contracts allowlist, tier model (31 stale fingerprints refreshed).

### Changed

- Extracted `contracts/hashing.py` — primitive-only `canonical_json`, `stable_hash`, and `repr_hash` (RFC 8785 + hashlib, no pandas/numpy). Breaks circular dependency between `contracts/` and `core/canonical.py`.
- Aggregation `on_error` is now required for aggregation transforms
- DTO mapper classes renamed from `*Repository` to `*Loader` to avoid confusion with new domain repositories
- **Test infrastructure overhaul (P0.5a–P4)** — 6-phase systematic hardening of the test suite, eliminating brittle coupling to internal constructors:
  - P0.5a–b: New factories (`make_recorder_with_run()`, `register_test_node()`, etc.) and refactored existing factories to delegate through them
  - P1: Replaced ~350 direct `PluginContext(...)` constructions across 53 files with centralized `make_context()` factory
  - P2: Replaced ~452 inline `LandscapeDB.in_memory()`/`LandscapeRecorder(...)` constructions across 76 files with factory calls. Net −715 lines
  - P3: Replaced ~529 lines of duplicated inline test plugin classes across 10 files with shared `tests.fixtures.plugins` imports
  - P4: Re-raise guards in telemetry/orchestrator/operation tracking, frozen evidence types (`ExceptionResult`, `FailureInfo`), aggregation DRY via `accumulate_row_outcomes()` + `ExecutionCounters`
- Resolved all 401 mypy errors across test suite — removed ~74 stale `# type: ignore` comments, added union-type narrowing guards, fixed module re-exports, wrapped `NewType` constructors, fixed protocol signatures (103 files)
- `PluginBundle` frozen dataclass replaces `dict[str, Any]` return from `instantiate_plugins_from_config()`, enabling mypy checking on all access sites
- Fingerprint primitives (`get_fingerprint_key()`, `secret_fingerprint()`) moved to `contracts/security.py` as stdlib-only implementations
- Redundant `.value` on `StrEnum` usage removed across checkpoint, landscape repositories, MCP, and tests
- Removed file-path header comments from 128 source files
- Azure safety transform consolidation (T14) — extracted shared batch infrastructure into `BaseAzureSafetyTransform` and `safety_utils.py`

### Added

- Typed coalesce checkpoint contracts (`CoalesceCheckpointState`, `CoalescePendingCheckpoint`, `CoalesceTokenCheckpoint`) plus CLI resume visibility for whether a checkpoint carries coalesce state
- **ADR-006**: Layer Dependency Remediation — documents the strict 4-layer model and CI enforcement strategy
- Full architecture analysis (23 documents covering all 13 subsystems)
- **Security posture brief** — Comprehensive document covering threat model, security controls, assurance evidence, and residual risk for ELSPETH v0.3.0
- **TYPE_CHECKING layer import detection** — `enforce_tier_model.py` CI gate now detects `TYPE_CHECKING` imports crossing layer boundaries as allowlistable findings
- **MCP server `_ToolDef` registry** replacing if/elif dispatch chain (T15)
- ~150 new tests across hardening, code review, and infrastructure phases

### Removed

- Dead code: `BaseLLMTransform` (3,473 lines, zero subclasses), `RequestRecord` dataclass, `TokenManager.payload_store` parameter, `populate_run()` (raw SQL bypass of `LandscapeRecorder`), LLM validation utilities (`render_template_safe`, `check_truncation`)
- ~21 low-value tests (vacuous assertions, mock-testing, implementation coupling)
- Superseded aggregation helpers replaced by shared `accumulate_row_outcomes()`

### Tests

- Full suite: approximately 10,500 tests — mypy/ruff/contracts all clean
- P0.5a–P4 test infrastructure overhaul: centralized factories, shared fixtures, eliminated ~1,700 lines of duplicated test boilerplate

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

## Historical Changelogs

- [RC-1 Changelog](CHANGELOG-RC1.md) — Initial framework build and hardening (Jan 12 – Feb 2, 2026)
- [RC-2 Changelog](CHANGELOG-RC2.md) — Sub-releases RC2 through RC2.5 (Feb 2 – Feb 12, 2026)

[0.3.4]: https://github.com/tachyon-beep/elspeth/compare/v0.3.3-rc3.3...main
[0.3.3]: https://github.com/tachyon-beep/elspeth/compare/v0.3.0-rc3.2...v0.3.3-rc3.3
[0.3.0]: https://github.com/tachyon-beep/elspeth/compare/v0.1.0-phase1...v0.3.0-rc3.2
[0.1.0]: https://github.com/tachyon-beep/elspeth/releases/tag/v0.1.0-phase1
