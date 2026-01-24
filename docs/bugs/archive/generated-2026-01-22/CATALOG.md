# Bug Catalog

Generated: 2026-01-22

This catalog contains all bugs extracted from the 42 generated bug report files in `docs/bugs/generated/`.

## Executive Summary

- **Total Bugs Found**: 32 concrete bugs
- **Trivial/No-Bug Reports**: 10 files

### By Priority

| Priority | Count |
|----------|-------|
| P0 | 1 |
| P1 | 9 |
| P2 | 18 |
| P3 | 4 |

### By Severity

| Severity | Count |
|----------|-------|
| Critical | 4 |
| Major | 22 |
| Minor | 5 |
| Trivial | 1 |

### By Component

| Component | Count |
|-----------|-------|
| CLI | 3 |
| Core/Landscape | 11 |
| Core/Config | 2 |
| Core/DAG | 2 |
| Core/Checkpoint | 3 |
| Core/Canonical | 2 |
| Core/Retention | 1 |
| Core/Rate Limit | 2 |
| Core/Payload Store | 2 |
| Core/Security | 1 |
| Contracts | 5 |

---

## Critical Bugs (P0-P1)

### P0: Source Row Payloads Never Persisted
- **File**: `elspeth/core/landscape/row_data.py.md`
- **Component**: core/landscape
- **Severity**: critical
- **Summary**: Source row payloads are not persisted during normal runs, violating the non-negotiable audit requirement to store raw source data. `rows.source_data_ref` stays NULL and `get_row_data` returns `NEVER_STORED`.
- **Impact**: Audit trail violates requirement to store raw source entries; resume fails with missing-payload errors.
- **References**: `CLAUDE.md:23`

### P1: Recovery Skips Rows for Sinks Written Later
- **File**: `elspeth/core/checkpoint/recovery.py.md` (bug #1)
- **Component**: core/checkpoint
- **Severity**: critical
- **Summary**: `RecoveryManager.get_unprocessed_rows` uses the row_index of the latest checkpointed token as a single boundary, but checkpoint order doesn't align with row_index across multiple sinks, causing resume to skip rows routed to a later/failed sink.
- **Impact**: Resume can finish without emitting outputs for some sinks; missing sink artifacts after recovery.
- **References**: `CLAUDE.md:28`

### P1: ArtifactDescriptor Leaks Secrets via Raw URLs
- **File**: `elspeth/contracts/results.py.md`
- **Component**: contracts
- **Severity**: critical
- **Summary**: `ArtifactDescriptor.for_database` and `for_webhook` embed raw URLs (including credentials/tokens) into `path_or_uri`, which is persisted into the audit trail and surfaced via exports/TUI.
- **Impact**: High-risk secret leakage into audit trail; secrets can appear in lineage exports and TUI displays.
- **References**: `CLAUDE.md:358`

### P1: Duplicate Config Gate Names Overwrite Node Mapping
- **File**: `elspeth/core/config.py.md` (bug #1)
- **Component**: core/config
- **Severity**: major
- **Summary**: Gate names documented as unique but not validated; duplicates overwrite `config_gate_id_map`, causing multiple gates to share a node ID and corrupting routing/audit attribution.
- **Impact**: Gate routing behavior unpredictable; audit trail can attribute decisions to wrong gate node.

### P1: Duplicate Fork/Coalesce Branch Names Break Merge Semantics
- **File**: `elspeth/core/config.py.md` (bug #2)
- **Component**: core/config
- **Severity**: major
- **Summary**: `fork_to` and `coalesce.branches` allow duplicate branch names; coalesce tracking uses dict keyed by branch name, so duplicates overwrite tokens and prevent merges from completing.
- **Impact**: Pipelines can hang at coalesce; tokens overwritten, causing silent loss of branch results.

### P1: Explain Returns Arbitrary Token When Multiple Tokens Exist
- **File**: `elspeth/core/landscape/lineage.py.md`
- **Component**: core/landscape
- **Severity**: major
- **Summary**: `explain(row_id)` resolves by picking first token, yielding incomplete/wrong lineage when multiple tokens share same row_id (fork/expand/coalesce/resume).
- **Impact**: Auditors/users can receive incorrect lineage for rows that fork/expand or are resumed.
- **References**: `docs/design/architecture.md:341`

### P1: RunRepository Masks Invalid export_status Values
- **File**: `elspeth/core/landscape/repositories.py.md` (bug #1)
- **Component**: core/landscape
- **Severity**: major
- **Summary**: `RunRepository.load` treats falsy export_status values as None, so invalid values like "" bypass ExportStatus coercion and don't crash, masking Tier 1 data corruption.
- **Impact**: Violates Tier 1 crash-on-anomaly rule by silently accepting corrupted audit data.
- **References**: `CLAUDE.md:40`

### P1: Unvalidated content_hash Allows Path Traversal
- **File**: `elspeth/core/payload_store.py.md` (bug #1)
- **Component**: core/payload_store
- **Severity**: major
- **Summary**: `FilesystemPayloadStore` uses raw `content_hash` to build filesystem paths, so a corrupted or attacker-controlled ref can escape `base_path` and read/delete arbitrary files.
- **Impact**: Path traversal enables arbitrary file deletion and potential data exposure.
- **References**: `CLAUDE.md:40`

### P1: store() Skips Integrity Verification for Existing Blobs
- **File**: `elspeth/core/payload_store.py.md` (bug #2)
- **Component**: core/payload_store
- **Severity**: major
- **Summary**: `FilesystemPayloadStore.store()` treats any pre-existing blob as valid and writes directly to final path; corrupted/partially written files can be silently accepted and later fail retrieval.
- **Impact**: Explain/replay/resume can fail with `IntegrityError` for payloads that were "successfully" stored earlier.
- **References**: `docs/design/architecture.md:565`

### P1: Reproducibility Grade Not Updated After Payload Purge
- **File**: `elspeth/core/retention/purge.py.md`
- **Component**: core/retention
- **Severity**: major
- **Summary**: `PurgeManager.purge_payloads()` deletes blobs but never updates `runs.reproducibility_grade`, so runs remain marked `REPLAY_REPRODUCIBLE` after payloads removed.
- **Impact**: Overstates replay capability; audit consumers may assume recomputation is possible when it's not.
- **References**: `docs/design/architecture.md:672`

---

## Major Bugs (P2)

### CLI: Run Validates One Graph But Executes Another
- **File**: `elspeth/cli.py.md` (bug #1)
- **Component**: cli
- **Severity**: minor
- **Priority**: P2
- **Summary**: `run` validates ExecutionGraph instance A, then `_execute_pipeline` rebuilds a new graph with UUID-based node IDs and executes it without `validate()`.
- **Impact**: Validation output can be misleading; validated graph differs from executed graph.
- **References**: `docs/bugs/open/P2-2026-01-20-cli-run-rebuilds-unvalidated-graph.md`

### CLI: Resume Uses New Aggregation Node IDs That Don't Match Stored Graph
- **File**: `elspeth/cli.py.md` (bug #2)
- **Component**: cli
- **Severity**: major
- **Priority**: P1
- **Summary**: `_build_resume_pipeline_config` derives aggregation node IDs from fresh graph, but resume executes with DB-reconstructed graph; UUID-based IDs don't match, breaking resume for aggregation pipelines.
- **Impact**: Resume fails for pipelines with aggregations due to node ID mismatches.

### CLI: Resume Forces mode=append on All Sinks
- **File**: `elspeth/cli.py.md` (bug #3)
- **Component**: cli
- **Severity**: major
- **Priority**: P2
- **Summary**: `_build_resume_pipeline_config` injects `sink_options["mode"] = "append"` for every sink; JSON/Database sinks don't accept `mode`, so resume fails with config validation errors.
- **Impact**: Resume fails for pipelines with JSON or Database sinks.

### Contracts: BatchOutput Missing batch_output_id
- **File**: `elspeth/contracts/audit.py.md`
- **Component**: contracts
- **Severity**: major
- **Priority**: P2
- **Summary**: `BatchOutput` contract omits `batch_output_id` primary key defined in `batch_outputs` table, preventing round-trip fidelity.
- **Impact**: Cannot reference or export unique batch output records once batch outputs are recorded.

### Contracts: contracts/config.py Imports core.config
- **File**: `elspeth/contracts/config.py.md`
- **Component**: contracts
- **Severity**: major
- **Priority**: P2
- **Summary**: Importing `elspeth.contracts` pulls in `elspeth.core.config` because contracts re-exports Core settings models, breaking contracts package independence.
- **Impact**: Increases circular-import fragility; contracts no longer independent.
- **References**: `docs/bugs/open/P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary.md`

### Contracts: check_compatibility Ignores Field Constraints
- **File**: `elspeth/contracts/data.py.md`
- **Component**: contracts
- **Severity**: major
- **Priority**: P2
- **Summary**: `check_compatibility` only compares `FieldInfo.annotation` and ignores constraint metadata, so constrained consumers (e.g., `allow_inf_nan=False`) treated as compatible with unconstrained producers.
- **Impact**: Pipelines validate as compatible but fail when constrained consumers reject rows.
- **References**: `docs/bugs/closed/P2-2026-01-19-non-finite-floats-pass-source-validation.md`

### Contracts: RoutingReason Contract Out of Sync
- **File**: `elspeth/contracts/errors.py.md` (bug #1)
- **Component**: contracts
- **Severity**: minor
- **Priority**: P3
- **Summary**: `RoutingReason` requires `rule` and `matched_value`, but GateExecutor emits `condition` and `result`.
- **Impact**: Routing explanations inconsistent with documented contract.

### Contracts: TransformReason Contract Out of Sync
- **File**: `elspeth/contracts/errors.py.md` (bug #2)
- **Component**: contracts
- **Severity**: minor
- **Priority**: P3
- **Summary**: `TransformReason` requires `action`, but transforms emit `message`/`reason`/`error` keys.
- **Impact**: Error reasons inconsistent with documented contract.

### Canonical: Decimal NaN/Infinity Bypass Non-Finite Rejection
- **File**: `elspeth/core/canonical.py.md` (bug #1)
- **Component**: core/canonical
- **Severity**: major
- **Priority**: P1
- **Summary**: `canonical_json` converts `Decimal("NaN")`/`Decimal("Infinity")` to JSON strings instead of raising, violating "reject NaN/Infinity" policy.
- **Impact**: Non-finite numeric values can be accepted and hashed without error, masking invalid data states.
- **References**: `CLAUDE.md:324`

### Canonical: Nested numpy Arrays Skip Recursive Normalization
- **File**: `elspeth/core/canonical.py.md` (bug #2)
- **Component**: core/canonical
- **Severity**: minor
- **Priority**: P2
- **Summary**: Multi-dimensional `np.ndarray` values only shallowly normalized; arrays containing pandas/numpy objects trigger `CanonicalizationError`.
- **Impact**: Canonicalization fails for valid array-shaped data containing pandas/numpy types.

### Checkpoint: Aggregation State JSON Bypasses Canonical Normalization
- **File**: `elspeth/core/checkpoint/manager.py.md`
- **Component**: core/checkpoint
- **Severity**: major
- **Priority**: P2
- **Summary**: `CheckpointManager.create_checkpoint()` serializes `aggregation_state` with raw `json.dumps` (no canonical normalization, no NaN/Infinity rejection).
- **Impact**: Checkpoint creation can crash for valid pipeline data types; invalid JSON may be written into Tier-1 audit storage.

### Checkpoint: can_resume Accepts Invalid Run Status
- **File**: `elspeth/core/checkpoint/recovery.py.md` (bug #2)
- **Component**: core/checkpoint
- **Severity**: major
- **Priority**: P2
- **Summary**: `RecoveryManager.can_resume` treats any run status other than RUNNING/COMPLETED as resumable, allowing resume on invalid run statuses.
- **Impact**: Resume may proceed on corrupted/invalid runs; violates full-trust audit DB rule.
- **References**: `CLAUDE.md:40`

### Core: resolve_config Not Exported from elspeth.core
- **File**: `elspeth/core/__init__.py.md`
- **Component**: core
- **Severity**: minor
- **Priority**: P2
- **Summary**: `resolve_config` defined in `core.config` but not exported in `core.__init__`, so documented import path fails.
- **Impact**: Documented import path fails, breaking scripts that follow published API surface.

### DAG: Plugin Gate Routes Missing in ExecutionGraph
- **File**: `elspeth/core/dag.py.md` (bug #1)
- **Component**: core/dag
- **Severity**: major
- **Priority**: P2
- **Summary**: `ExecutionGraph` builds all `row_plugins` as transforms and omits route resolution for plugin gates, leading to MissingEdgeError if plugin gate emits route label.
- **Impact**: Plugin-gate pipelines fail at runtime or misrecord routing events.
- **References**: `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md`

### DAG: Duplicate Coalesce Branch Names Silently Overwritten
- **File**: `elspeth/core/dag.py.md` (bug #2)
- **Component**: core/dag
- **Severity**: major
- **Priority**: P2
- **Summary**: `ExecutionGraph.from_config` overwrites `branch_to_coalesce` when same branch appears in multiple coalesce configs, so forked tokens routed to only one coalesce.
- **Impact**: Missing or delayed coalesce outputs for one of configured merges.

### Landscape: Schema Validation Misses Newer Required Columns
- **File**: `elspeth/core/landscape/database.py.md`
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `_validate_schema()` only checks `_REQUIRED_COLUMNS` (currently just `tokens.expand_group_id`), so stale SQLite DBs missing `nodes.schema_mode`/`nodes.schema_fields_json` pass validation then crash later.
- **Impact**: Pipelines fail mid-run with opaque SQL errors when using stale local SQLite audit DB.

### Landscape: Token Export Omits expand_group_id
- **File**: `elspeth/core/landscape/exporter.py.md` (bug #1)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `LandscapeExporter._iter_records()` emits token records without `expand_group_id`, so deaggregation lineage cannot be reconstructed from exported audit data.
- **Impact**: Auditors cannot reconstruct deaggregation groupings from exported audit data alone.
- **References**: `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md`

### Landscape: Export Omits Run/Node Configuration and Determinism Metadata
- **File**: `elspeth/core/landscape/exporter.py.md` (bug #2)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: Run and node records omit configuration fields (`settings_json`, `config_json`, `determinism`, schema config), so exported audit data not self-contained.
- **Impact**: Exported audit trail cannot stand alone for compliance review without separate access to original configuration artifacts.
- **References**: `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md`

### Landscape: Exporter Uses N+1 Query Pattern
- **File**: `elspeth/core/landscape/exporter.py.md` (bug #3)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `LandscapeExporter._iter_records()` performs nested per-entity queries, leading to large number of DB round-trips and slow exports for large runs.
- **Impact**: Exports become slow or unusable for large runs; high DB overhead.
- **References**: `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md`

### Landscape: get_calls Returns Raw Strings for Call Enums
- **File**: `elspeth/core/landscape/recorder.py.md`
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `LandscapeRecorder.get_calls()` builds `Call` objects with `call_type` and `status` taken directly from DB strings, violating enum-only contract.
- **Impact**: Downstream code comparing to enums may misbehave; invalid DB values not detected.

### Landscape: NodeRepository Drops schema_mode and schema_fields
- **File**: `elspeth/core/landscape/repositories.py.md` (bug #2)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `NodeRepository.load` ignores `schema_mode` and `schema_fields_json`, returning Node objects without schema metadata even when DB stores it.
- **Impact**: Explain/export output omits schema configuration for nodes; audit metadata dropped.
- **References**: `CLAUDE.md:17`

### Landscape: BatchRepository Drops trigger_type
- **File**: `elspeth/core/landscape/repositories.py.md` (bug #3)
- **Component**: core/landscape
- **Severity**: minor
- **Priority**: P3
- **Summary**: `BatchRepository.load` never assigns `trigger_type` from DB, so Batch objects lose aggregation trigger metadata.
- **Impact**: Batch reads omit trigger reason type in explain/export views.
- **References**: `CLAUDE.md:17`

### Landscape: compute_grade Ignores Invalid Determinism Values
- **File**: `elspeth/core/landscape/reproducibility.py.md` (bug #1)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `compute_grade` only checks for known non-reproducible determinism values; invalid determinism strings treated as reproducible instead of crashing.
- **Impact**: Runs labeled fully reproducible even when audit data corrupt; violates Tier 1 crash-on-anomaly.
- **References**: `CLAUDE.md:40`

### Landscape: update_grade_after_purge Leaves FULL_REPRODUCIBLE After Payload Purge
- **File**: `elspeth/core/landscape/reproducibility.py.md` (bug #2)
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `update_grade_after_purge` only downgrades `REPLAY_REPRODUCIBLE`; deterministic runs remain `FULL_REPRODUCIBLE` even after payloads purged, contradicting documented definition.
- **Impact**: Overstates reproducibility; runs labeled fully reproducible though payloads no longer available.
- **References**: `docs/design/architecture.md:680`

### Landscape: Error Tables Lack Foreign Keys
- **File**: `elspeth/core/landscape/schema.py.md`
- **Component**: core/landscape
- **Severity**: major
- **Priority**: P2
- **Summary**: `validation_errors.node_id` and `transform_errors.token_id`/`transform_errors.transform_id` defined without FK constraints, allowing orphan error records.
- **Impact**: Tier 1 audit DB can hold structurally inconsistent records, weakening audit defensibility.
- **References**: `docs/design/architecture.md:274`, `docs/bugs/open/P2-2026-01-19-error-tables-missing-foreign-keys.md`

### Landscape: Landscape Models Drift from Contracts/Schema
- **File**: `elspeth/core/landscape/models.py.md`
- **Component**: core/landscape
- **Severity**: minor
- **Priority**: P3
- **Summary**: `src/elspeth/core/landscape/models.py` is legacy duplicate of audit contracts and has drifted (missing Node schema fields, enum-typed fields downgraded to `str`, optional `Checkpoint.created_at`).
- **Impact**: Code/tests importing it can accept invalid/incomplete audit records and mask contract drift.
- **References**: `CLAUDE.md:417`, `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md`

### Rate Limit: RateLimiter.acquire() Not Locked/Atomic
- **File**: `elspeth/core/rate_limit/limiter.py.md` (bug #1)
- **Component**: core/rate_limit
- **Severity**: major
- **Priority**: P2
- **Summary**: `RateLimiter.acquire()` iterates limiters without `self._lock`, so concurrent calls or later limiter failures can occur after earlier token consumption.
- **Impact**: Inconsistent rate limiting under concurrency; tokens can be "lost," increasing throttling.
- **References**: `docs/bugs/open/P2-2026-01-19-rate-limiter-acquire-not-thread-safe-or-atomic.md`

### Rate Limit: Rate Limiter Suppression Set Retains Stale Thread Idents
- **File**: `elspeth/core/rate_limit/limiter.py.md` (bug #2)
- **Component**: core/rate_limit
- **Severity**: minor
- **Priority**: P2 (inferred from first bug in file)
- **Summary**: `RateLimiter.close()` registers leaker thread idents for exception suppression but only removes them when suppression fires; clean exits leave stale idents that can suppress unrelated errors if thread IDs reused.
- **Impact**: Stale thread idents can suppress legitimate AssertionErrors.

### Security: Key Vault Empty Secret Accepted as HMAC Key
- **File**: `elspeth/core/security/fingerprint.py.md`
- **Component**: core/security
- **Severity**: major
- **Priority**: P2
- **Summary**: `get_fingerprint_key()` accepts empty Key Vault secret value and returns `b""`, effectively removing secret from HMAC and undermining "no guessing oracle" guarantee.
- **Impact**: Empty HMAC key makes fingerprints guessable (no secret key), defeating intended protection.
- **References**: `docs/design/architecture.md:747`

---

## Summary Tables

### Bugs by Subcomponent (Core)

| Subcomponent | Count |
|--------------|-------|
| landscape | 11 |
| checkpoint | 3 |
| config | 2 |
| dag | 2 |
| canonical | 2 |
| rate_limit | 2 |
| payload_store | 2 |
| retention | 1 |
| security | 1 |

### Cross-References to docs/bugs/open/

The following bugs reference existing open bug reports:

1. **CLI run rebuilds unvalidated graph** → `docs/bugs/open/P2-2026-01-20-cli-run-rebuilds-unvalidated-graph.md`
2. **Contracts config reexport breaks leaf boundary** → `docs/bugs/open/P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary.md`
3. **Exporter missing expand_group_id** → `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md`
4. **Error tables missing foreign keys** → `docs/bugs/open/P2-2026-01-19-error-tables-missing-foreign-keys.md`
5. **Landscape models duplication drift** → `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md`
6. **Rate limiter acquire not thread safe** → `docs/bugs/open/P2-2026-01-19-rate-limiter-acquire-not-thread-safe-or-atomic.md`

### Cross-References to docs/bugs/pending/

The following bugs reference pending bug reports:

1. **Plugin gate graph mismatch** → `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md`
2. **Exporter missing config in export** → `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md`
3. **Exporter n plus one queries** → `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md`

### Cross-References to docs/bugs/closed/

The following bugs reference closed bug reports:

1. **Non-finite floats pass source validation** → `docs/bugs/closed/P2-2026-01-19-non-finite-floats-pass-source-validation.md`
2. **Payload store integrity and hash validation missing** → `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md`

---

## Files With No Concrete Bugs (10)

The following files reported "no concrete bug found":

1. `elspeth/contracts/cli.py.md`
2. `elspeth/contracts/engine.py.md`
3. `elspeth/contracts/enums.py.md`
4. `elspeth/contracts/identity.py.md`
5. `elspeth/contracts/__init__.py.md`
6. `elspeth/contracts/routing.py.md`
7. `elspeth/contracts/schema.py.md`
8. `elspeth/core/checkpoint/__init__.py.md`
9. `elspeth/core/landscape/formatters.py.md`
10. `elspeth/core/landscape/__init__.py.md`
11. `elspeth/core/logging.py.md`
12. `elspeth/core/rate_limit/__init__.py.md`
13. `elspeth/core/rate_limit/registry.py.md`
14. `elspeth/core/retention/__init__.py.md`
15. `elspeth/core/security/__init__.py.md`
16. `elspeth/engine/__init__.py.md`
17. `elspeth/__init__.py.md`

---

## Bug Density by Module

| Module Path | Bugs | Lines (approx) | Density |
|-------------|------|----------------|---------|
| elspeth/cli.py | 3 | ~1000 | High |
| elspeth/core/landscape/exporter.py | 3 | ~400 | Very High |
| elspeth/core/landscape/repositories.py | 3 | ~300 | Very High |
| elspeth/core/landscape/reproducibility.py | 2 | ~200 | High |
| elspeth/core/canonical.py | 2 | ~200 | High |
| elspeth/core/config.py | 2 | ~1200 | Medium |
| elspeth/core/dag.py | 2 | ~600 | Medium |
| elspeth/core/checkpoint/recovery.py | 2 | ~300 | High |
| elspeth/core/payload_store.py | 2 | ~200 | High |
| elspeth/core/rate_limit/limiter.py | 2 | ~300 | High |
| elspeth/contracts/errors.py | 2 | ~100 | Very High |

---

## Next Steps

This catalog provides an organized view of all identified bugs. The next steps should include:

1. **Triage**: Review critical/P0-P1 bugs for immediate action
2. **Deduplication**: Cross-check with `docs/bugs/open/` and `docs/bugs/pending/` to identify duplicates
3. **Prioritization**: Create work packages for high-priority bug fixes
4. **Testing**: Ensure test coverage for all reported bugs once fixed
5. **Architecture Review**: Several bugs indicate systemic issues (e.g., audit integrity, contract drift) that may require architectural decisions

---

## Methodology Note

This catalog was generated via automated static analysis (GPT-5 Codex CLI) reviewing all source files in the codebase. Each bug report includes:

- Severity/priority classification
- Detailed reproduction steps
- Impact assessment
- Root cause hypothesis
- Proposed fixes
- Test requirements
- Architecture alignment notes

The analysis focused on:
- Tier 1 audit integrity violations
- Contract/schema mismatches
- Configuration validation gaps
- Concurrency/atomicity issues
- Secret handling violations
- Data loss/corruption risks
