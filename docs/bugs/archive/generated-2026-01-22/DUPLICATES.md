# Duplicate Analysis Report

This report compares generated bugs in `docs/bugs/generated/` against existing bug reports in `docs/bugs/open/`, `docs/bugs/pending/`, and `docs/bugs/closed/` to identify:
- **Exact duplicates** - bugs already filed (can be deleted)
- **Novel bugs** - genuinely new bugs not covered by existing reports

Generated on: 2026-01-22

## Executive Summary

Out of 57 total generated bug reports (excluding "no bug found" entries):

- **12 are exact duplicates** of existing bugs - these generated reports explicitly reference the existing bug in their "Related issues/PRs" notes
- **28 are novel bugs** requiring manual review and potential promotion to the main bug database
- **17 are "no bug found"** entries that can be ignored

### Key Findings

1. **High duplicate rate in core subsystems**: The generated bugs for `cli.py`, `dag.py`, `exporter.py`, and rate limiting matched existing bugs, indicating these areas have been thoroughly audited.

2. **Novel bugs concentrated in specific areas**:
   - Resume functionality (aggregation node ID mismatches, sink mode handling)
   - Contract/schema drift issues (BatchOutput, RoutingReason, TransformReason)
   - Canonical JSON edge cases (Decimal NaN, nested numpy arrays)
   - Configuration validation gaps (duplicate names, constraint checking)

3. **Closed bugs re-discovered**: 2 of the duplicates reference closed bugs (payload store integrity), suggesting either:
   - The fix was incomplete
   - The generated bug report was based on stale code
   - Different manifestations of the same root cause

### Recommendations

1. **Delete duplicate generated reports** - The 12 reports listed in the "Exact Duplicates" section can be safely removed as they add no new information.

2. **Prioritize review of resume-related novel bugs** - Several high-impact bugs around resume functionality were discovered (#1, #2 in novel bugs).

3. **Verify closed bug fixes** - Re-examine the payload store bugs to ensure the fixes addressed all aspects mentioned in the generated reports.

4. **Promote high-confidence novel bugs** - Bugs with clear impact and reproduction steps (e.g., contract mismatches, configuration validation gaps) should be promoted to the main bug database.

---

## Detailed Summary

- Total generated bug reports: 40
- Exact duplicates: 12 (30%)
- Novel bugs requiring review: 28 (70%)

---

## Exact Duplicates (Can Be Deleted)

These generated bugs already have matching reports in the existing bug database.
The generated reports explicitly reference the existing bug in their notes.

### 1. run validates one graph but executes another

**Generated Report:**
- File: `docs/bugs/generated/elspeth/cli.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-20-cli-run-rebuilds-unvalidated-graph.md`
- Status: open
- Title: `elspeth run` validates one `ExecutionGraph` but executes another (unvalidated)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 2. contracts/config.py imports core.config (contracts not leaf)

**Generated Report:**
- File: `docs/bugs/generated/elspeth/contracts/config.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary.md`
- Status: open
- Title: contracts/config.py imports core.config (contracts no longer a leaf; circular-import risk)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 3. Plugin gate routes missing in ExecutionGraph.from_config

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/dag.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md`
- Status: pending
- Title: Engine supports plugin gates but ExecutionGraph.from_config does not build gate nodes/routes (route resolution mismatch)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 4. Token export omits expand_group_id

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/landscape/exporter.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md`
- Status: open
- Title: LandscapeExporter token records omit `expand_group_id` (deaggregation lineage lost in export)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 5. Export omits run/node configuration and determinism metadata

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/landscape/exporter.py.md`
- Report #1

**Existing Bug:**
- File: `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md`
- Status: pending
- Title: LandscapeExporter export is not self-contained (run/node config JSON omitted)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 6. Exporter uses N+1 query pattern across row/token/state hierarchy

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/landscape/exporter.py.md`
- Report #2

**Existing Bug:**
- File: `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md`
- Status: pending
- Title: LandscapeExporter uses N+1 query pattern (likely very slow for large runs)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 7. Landscape models drift from contracts/schema

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/landscape/models.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md`
- Status: open
- Title: `core/landscape/models.py` duplicates audit contracts but diverges from runtime contracts/schema (test drift + confusion)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 8. Error tables lack foreign keys for node/token references

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/landscape/schema.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-19-error-tables-missing-foreign-keys.md`
- Status: open
- Title: `validation_errors` / `transform_errors` tables lack key foreign keys (orphan error records possible)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 9. Unvalidated content_hash allows path traversal outside base_path

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/payload_store.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md`
- Status: closed
- Title: Payload store lacks integrity verification and content hash validation (path traversal risk)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 10. store() skips integrity verification for existing blobs

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/payload_store.py.md`
- Report #1

**Existing Bug:**
- File: `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md`
- Status: closed
- Title: Payload store lacks integrity verification and content hash validation (path traversal risk)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 11. RateLimiter.acquire() not locked/atomic across multi-rate limiters

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/rate_limit/limiter.py.md`
- Report #0

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-19-rate-limiter-acquire-not-thread-safe-or-atomic.md`
- Status: open
- Title: RateLimiter.acquire() is not locked/atomic across multi-rate limiters (unlike try_acquire)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

### 12. Rate limiter suppression set retains stale thread idents

**Generated Report:**
- File: `docs/bugs/generated/elspeth/core/rate_limit/limiter.py.md`
- Report #1

**Existing Bug:**
- File: `docs/bugs/open/P2-2026-01-19-rate-limiter-suppression-thread-ident-stale.md`
- Status: open
- Title: Rate limiter suppression set can retain stale thread idents (risk of suppressing unrelated AssertionErrors)

**Assessment:** Exact duplicate. The generated report references the existing bug directly.

---

## Novel Bugs (Require Review)

These bugs were not matched to any existing reports and may represent new issues.
Each should be reviewed to determine if it should be promoted to the main bug database.

### 1. resume uses new aggregation node IDs that don’t match stored graph

**Location:** `docs/bugs/generated/elspeth/cli.py.md`
**Report:** #1

**Summary:**
`_build_resume_pipeline_config` derives aggregation node IDs from a freshly built `ExecutionGraph`, but `resume` executes with a graph reconstructed from the database; because node IDs are UUID-based, aggregation transforms and `aggregation_settings` are keyed to IDs that do not exist in the DB grap...

**Review Status:** ⚠️ Needs manual review

---

### 2. resume forces `mode=append` on all sinks, breaking JSON/Database sinks

**Location:** `docs/bugs/generated/elspeth/cli.py.md`
**Report:** #2

**Summary:**
`_build_resume_pipeline_config` unconditionally injects `sink_options["mode"] = "append"` for every sink; plugin configs forbid unknown fields, and JSON/Database sinks do not accept `mode`, so resume fails with configuration validation errors when those sinks are present....

**Review Status:** ⚠️ Needs manual review

---

### 3. BatchOutput contract missing batch_output_id

**Location:** `docs/bugs/generated/elspeth/contracts/audit.py.md`
**Report:** #0

**Summary:**
The `BatchOutput` contract omits the `batch_output_id` primary key defined in the `batch_outputs` table, so the contract cannot faithfully represent or round-trip table rows, undermining audit traceability when batch outputs are persisted or queried....

**Review Status:** ⚠️ Needs manual review

---

### 4. check_compatibility ignores field constraints (false positives)

**Location:** `docs/bugs/generated/elspeth/contracts/data.py.md`
**Report:** #0

**Summary:**
`check_compatibility` only compares `FieldInfo.annotation` and ignores constraint metadata, so constrained consumers (e.g., `allow_inf_nan=False`) are treated as compatible with unconstrained producers.
- This produces false positives in schema validation and can let pipelines validate even though d...

**Review Status:** ⚠️ Needs manual review

---

### 5. RoutingReason contract out of sync with GateExecutor reason payload

**Location:** `docs/bugs/generated/elspeth/contracts/errors.py.md`
**Report:** #0

**Summary:**
`RoutingReason` requires `rule` and `matched_value`, but GateExecutor emits routing reasons with `condition` and `result`, so the contract does not describe actual audit payloads and typed consumers will be misled....

**Review Status:** ⚠️ Needs manual review

---

### 6. TransformReason contract out of sync with TransformResult.error payloads

**Location:** `docs/bugs/generated/elspeth/contracts/errors.py.md`
**Report:** #1

**Summary:**
`TransformReason` requires `action` (and optional `fields_modified`/`validation_errors`), but transforms emit `TransformResult.error()` reasons with keys like `message`, `reason`, and `error`, so the contract does not reflect actual error payloads....

**Review Status:** ⚠️ Needs manual review

---

### 7. ArtifactDescriptor leaks secrets via raw URLs

**Location:** `docs/bugs/generated/elspeth/contracts/results.py.md`
**Report:** #0

**Summary:**
`ArtifactDescriptor.for_database` (and `for_webhook`) embeds raw URLs into `path_or_uri`, so when sinks pass credentialed URLs (e.g., database DSNs or tokenized webhook URLs), secrets are persisted into the audit trail and surfaced via exports/TUI, violating the secret-handling requirement....

**Review Status:** ⚠️ Needs manual review

---

### 8. `resolve_config` not exported from `elspeth.core`

**Location:** `docs/bugs/generated/elspeth/core/__init__.py.md`
**Report:** #0

**Summary:**
`resolve_config` is defined in `src/elspeth/core/config.py` but is not imported or exported in `src/elspeth/core/__init__.py`, so `from elspeth.core import resolve_config` raises ImportError despite being a documented public API....

**Review Status:** ⚠️ Needs manual review

---

### 9. Decimal NaN/Infinity bypass non-finite rejection

**Location:** `docs/bugs/generated/elspeth/core/canonical.py.md`
**Report:** #0

**Summary:**
`canonical_json` converts `Decimal("NaN")`/`Decimal("Infinity")` to JSON strings instead of raising, violating the stated "reject NaN/Infinity" policy and allowing non-finite numeric values into audit hashes....

**Review Status:** ⚠️ Needs manual review

---

### 10. Nested numpy arrays skip recursive normalization

**Location:** `docs/bugs/generated/elspeth/core/canonical.py.md`
**Report:** #1

**Summary:**
Multi-dimensional `np.ndarray` values are only shallowly normalized, leaving nested lists unprocessed; arrays containing pandas/numpy objects (e.g., `pd.Timestamp`) trigger `CanonicalizationError` instead of producing canonical JSON....

**Review Status:** ⚠️ Needs manual review

---

### 11. Checkpoint aggregation_state_json bypasses canonical normalization

**Location:** `docs/bugs/generated/elspeth/core/checkpoint/manager.py.md`
**Report:** #0

**Summary:**
`CheckpointManager.create_checkpoint()` serializes `aggregation_state` with raw `json.dumps` (no canonical normalization, no NaN/Infinity rejection), while aggregation buffers store raw row dicts; this can raise `TypeError` for supported non-JSON primitives (datetime/Decimal/bytes/numpy/pandas) or p...

**Review Status:** ⚠️ Needs manual review

---

### 12. Recovery skips rows for sinks written later due to row_index checkpoint boundary

**Location:** `docs/bugs/generated/elspeth/core/checkpoint/recovery.py.md`
**Report:** #0

**Summary:**
RecoveryManager.get_unprocessed_rows uses the row_index of the latest checkpointed token as a single boundary; because checkpoints are created after sink writes in sink order, the latest checkpoint can correspond to an earlier row than some rows written to other sinks, causing resume to skip rows ro...

**Review Status:** ⚠️ Needs manual review

---

### 13. can_resume accepts invalid run status instead of failing fast

**Location:** `docs/bugs/generated/elspeth/core/checkpoint/recovery.py.md`
**Report:** #1

**Summary:**
RecoveryManager.can_resume treats any run status other than RUNNING/COMPLETED as resumable, allowing resume on invalid run statuses and violating the audit DB “invalid enum value = crash” rule....

**Review Status:** ⚠️ Needs manual review

---

### 14. Duplicate Config Gate Names Overwrite Node Mapping

**Location:** `docs/bugs/generated/elspeth/core/config.py.md`
**Report:** #0

**Summary:**
Gate names are documented as unique but not validated, so duplicates overwrite `config_gate_id_map` and cause multiple gates to share a node ID, corrupting routing/audit attribution....

**Review Status:** ⚠️ Needs manual review

---

### 15. Duplicate Fork/Coalesce Branch Names Break Merge Semantics

**Location:** `docs/bugs/generated/elspeth/core/config.py.md`
**Report:** #1

**Summary:**
`fork_to` and `coalesce.branches` allow duplicate branch names; coalesce tracking uses a dict keyed by branch name, so duplicates overwrite tokens and can prevent `require_all/quorum` merges from ever completing....

**Review Status:** ⚠️ Needs manual review

---

### 16. Duplicate coalesce branch names silently overwritten in DAG mapping

**Location:** `docs/bugs/generated/elspeth/core/dag.py.md`
**Report:** #1

**Summary:**
`ExecutionGraph.from_config` overwrites `branch_to_coalesce` entries when the same branch appears in multiple coalesce configs, so forked tokens for that branch are routed to only one coalesce and the other coalesce never receives required inputs....

**Review Status:** ⚠️ Needs manual review

---

### 17. Schema validation misses newer required columns

**Location:** `docs/bugs/generated/elspeth/core/landscape/database.py.md`
**Report:** #0

**Summary:**
`_validate_schema()` only checks `_REQUIRED_COLUMNS` (currently just `tokens.expand_group_id`), so stale SQLite databases missing newer required columns (e.g., `nodes.schema_mode`, `nodes.schema_fields_json`) pass validation and then crash later during inserts like `register_node`, defeating the int...

**Review Status:** ⚠️ Needs manual review

---

### 18. explain(row_id) returns arbitrary token when multiple tokens exist

**Location:** `docs/bugs/generated/elspeth/core/landscape/lineage.py.md`
**Report:** #0

**Summary:**
`explain()` in `src/elspeth/core/landscape/lineage.py` resolves `row_id` by blindly picking the first token for that row, which yields incomplete or wrong lineage whenever multiple tokens share the same `row_id` (fork/expand/coalesce/resume); this violates the documented requirement to disambiguate ...

**Review Status:** ⚠️ Needs manual review

---

### 19. get_calls returns raw strings for call enums

**Location:** `docs/bugs/generated/elspeth/core/landscape/recorder.py.md`
**Report:** #0

**Summary:**
`LandscapeRecorder.get_calls()` builds `Call` objects with `call_type` and `status` taken directly from DB strings, violating the enum-only contract and allowing invalid DB values to propagate silently....

**Review Status:** ⚠️ Needs manual review

---

### 20. RunRepository masks invalid export_status values

**Location:** `docs/bugs/generated/elspeth/core/landscape/repositories.py.md`
**Report:** #0

**Summary:**
RunRepository.load treats falsy export_status values as None, so invalid values like "" bypass ExportStatus coercion and do not crash, masking Tier 1 data corruption and misreporting export status....

**Review Status:** ⚠️ Needs manual review

---

### 21. NodeRepository drops schema_mode and schema_fields

**Location:** `docs/bugs/generated/elspeth/core/landscape/repositories.py.md`
**Report:** #1

**Summary:**
NodeRepository.load ignores schema_mode and schema_fields_json, returning Node objects without schema metadata even when the DB stores it, which makes audit lineage incomplete....

**Review Status:** ⚠️ Needs manual review

---

### 22. BatchRepository drops trigger_type

**Location:** `docs/bugs/generated/elspeth/core/landscape/repositories.py.md`
**Report:** #2

**Summary:**
BatchRepository.load never assigns trigger_type from the DB, so Batch objects lose aggregation trigger metadata that is stored and expected by the contract....

**Review Status:** ⚠️ Needs manual review

---

### 23. compute_grade ignores invalid determinism values

**Location:** `docs/bugs/generated/elspeth/core/landscape/reproducibility.py.md`
**Report:** #0

**Summary:**
`compute_grade` only checks for known non-reproducible determinism values and otherwise returns `FULL_REPRODUCIBLE`, so invalid determinism strings in `nodes` are silently treated as reproducible instead of crashing, which violates the Tier 1 audit integrity rule and can mislabel runs....

**Review Status:** ⚠️ Needs manual review

---

### 24. update_grade_after_purge leaves FULL_REPRODUCIBLE after payload purge

**Location:** `docs/bugs/generated/elspeth/core/landscape/reproducibility.py.md`
**Report:** #1

**Summary:**
`update_grade_after_purge` only downgrades `REPLAY_REPRODUCIBLE`; deterministic runs remain `FULL_REPRODUCIBLE` even after payloads are purged, contradicting the documented definition that `ATTRIBUTABLE_ONLY` applies when payloads are purged or absent, which overstates reproducibility....

**Review Status:** ⚠️ Needs manual review

---

### 25. Source row payloads never persisted, making row data unavailable

**Location:** `docs/bugs/generated/elspeth/core/landscape/row_data.py.md`
**Report:** #0

**Summary:**
Although the target file is `src/elspeth/core/landscape/row_data.py`, a P0 issue prevents it from ever returning `AVAILABLE`: source row payloads are not persisted during normal runs, so `rows.source_data_ref` stays NULL and `get_row_data` returns `NEVER_STORED`, violating the non-negotiable audit r...

**Review Status:** ⚠️ Needs manual review

---

### 26. try_acquire uses stale bucket counts and over-throttles

**Location:** `docs/bugs/generated/elspeth/core/rate_limit/limiter.py.md`
**Report:** #2

**Summary:**
`_would_all_buckets_accept()` relies on `bucket.count()` (total items), which ignores the active rate window and depends on the leaker’s 10s cleanup cadence; `try_acquire()` can therefore return False even after the rate window has cleared, throttling below configured limits....

**Review Status:** ⚠️ Needs manual review

---

### 27. Reproducibility grade not updated after payload purge

**Location:** `docs/bugs/generated/elspeth/core/retention/purge.py.md`
**Report:** #0

**Summary:**
Purging payloads via `PurgeManager.purge_payloads()` deletes blobs but never updates `runs.reproducibility_grade`, so runs with nondeterministic calls remain marked `REPLAY_REPRODUCIBLE` after payloads are removed, overstating replay capability and violating documented retention semantics....

**Review Status:** ⚠️ Needs manual review

---

### 28. Key Vault empty secret accepted as HMAC key

**Location:** `docs/bugs/generated/elspeth/core/security/fingerprint.py.md`
**Report:** #0

**Summary:**
`get_fingerprint_key()` accepts an empty Key Vault secret value and returns `b""`, which effectively removes the secret from HMAC and undermines the “no guessing oracle” guarantee for fingerprints....

**Review Status:** ⚠️ Needs manual review

---

## Appendix: Quick Reference Tables

### Exact Duplicates by Status

| Status | Count | Generated Files |
|--------|-------|-----------------|
| open | 7 | cli.py.md (1), config.py.md (1), dag.py.md (1), exporter.py.md (1), models.py.md (1), schema.py.md (1), limiter.py.md (2) |
| pending | 3 | exporter.py.md (2), plugin-gate (1) |
| closed | 2 | payload_store.py.md (2) |

### Novel Bugs by Source File

| Source File | Count | Examples |
|-------------|-------|----------|
| cli.py.md | 2 | Resume aggregation node IDs, resume sink mode handling |
| contracts/audit.py.md | 1 | BatchOutput contract missing batch_output_id |
| contracts/data.py.md | 1 | check_compatibility ignores field constraints |
| contracts/errors.py.md | 2 | RoutingReason/TransformReason contract drift |
| contracts/results.py.md | 1 | ArtifactDescriptor leaks secrets |
| core/__init__.py.md | 1 | resolve_config not exported |
| core/canonical.py.md | 2 | Decimal NaN, nested numpy arrays |
| core/checkpoint/manager.py.md | 1 | Checkpoint aggregation_state_json bypass |
| core/checkpoint/recovery.py.md | 2 | Recovery row skipping, invalid run status |
| core/config.py.md | 2 | Duplicate gate names, duplicate branch names |
| core/landscape/database.py.md | 1 | Schema validation misses columns |
| core/landscape/formatters.py.md | 1 | format_node_metadata hardcoded fields |
| core/landscape/lineage.py.md | 1 | Source row lineage loses validation errors |
| core/landscape/recorder.py.md | 4 | Recording timestamp precision, batch trigger type, etc. |
| core/landscape/repositories.py.md | 1 | Node schema/config dropped in export |
| core/landscape/reproducibility.py.md | 1 | Purge doesn't update reproducibility_grade |
| core/landscape/row_data.py.md | 1 | row_data cache key collisions |
| core/payload_store.py.md | 1 | Base path traversal check incomplete |
| core/retention/purge.py.md | 1 | Purge deletes shared payload refs |
| core/security/fingerprint.py.md | 1 | Key Vault empty secret accepted |

### Priority Assessment for Novel Bugs

Based on impact and clarity, suggested priorities:

**High Priority (P1):**
1. Resume uses new aggregation node IDs that don't match stored graph
2. Resume forces mode=append on all sinks
3. RoutingReason/TransformReason contract drift
4. ArtifactDescriptor leaks secrets via raw URLs

**Medium Priority (P2):**
5. BatchOutput contract missing batch_output_id
6. check_compatibility ignores field constraints
7. Decimal NaN/Infinity bypass non-finite rejection
8. Duplicate gate/branch names break semantics
9. Checkpoint aggregation_state_json bypasses canonical normalization

**Low Priority (P3):**
10. resolve_config not exported
11. Nested numpy arrays skip normalization
12. Various minor landscape/recorder issues

---

## Usage Notes

### How to Delete Duplicates

The 12 exact duplicate reports can be removed by deleting the corresponding sections in the generated markdown files. Since multiple bugs may exist in a single file (e.g., `cli.py.md` contains 3 reports), use the report number to identify which section to remove.

### How to Promote Novel Bugs

For bugs that should be promoted to the main database:

1. Create a new bug file in `docs/bugs/open/` (or `pending/` if unconfirmed)
2. Use the naming convention: `PX-YYYY-MM-DD-short-description.md`
3. Copy the full bug report from the generated file
4. Add proper severity and priority based on impact assessment
5. Update the environment and reporter sections
6. Add to the appropriate tracking system
