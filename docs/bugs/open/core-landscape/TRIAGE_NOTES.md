# Core Landscape Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-landscape/` (29 findings from static analysis)
**Source code reviewed:** All files in `src/elspeth/core/landscape/`

## Aggregate Summary

| Category | Count | Details |
|----------|-------|---------|
| Confirmed P1 | 4 | Genuine audit integrity issues requiring fixes |
| Confirmed P2 | 11 | Real bugs, lower impact or well-guarded by callers |
| Downgraded P1 → P2 | 7 | Real but theoretical or narrow trigger conditions |
| Downgraded P1 → P3 | 3 | Theoretical — same root cause, merge into one item |
| Downgraded P2 → P3 | 4 | Pedantic or near-zero practical risk |
| Closed (false positive / dead code) | 3 | UniqueConstraint prevents dupes; dead code; sole caller explicit |
| **Total** | **29** | 17 original P1s reduced to 4; 12 original P2s stable |

## Confirmed P1s — Must Fix

### 1. `record_transform_error` crashes on non-canonical values in `error_details`
- **File:** `_error_recording.py:168`
- **Issue:** `canonical_json(error_details)` rejects NaN/Infinity. LLM API error responses can contain non-finite floats. Escalates row-level error to pipeline crash.
- **Fix pattern exists:** `record_validation_error()` (same file) already has `try/except` fallback to `repr_hash` + `NonCanonicalMetadata`. Apply same pattern.

### 2. `get_run_contract` never cross-checks DB `schema_contract_hash` column
- **File:** `_run_recording.py:341-353`
- **Issue:** Reads `schema_contract_json`, restores contract, checks embedded hash matches reconstructed contract — but never reads the independent `schema_contract_hash` DB column. Tampered JSON with self-consistent embedded hash goes undetected.
- **Impact:** Tier 1 integrity gap. The DB column was designed as an independent check but is never used on the read path.

### 3. `LandscapeExporter` omits `token_outcomes` table entirely
- **File:** `exporter.py` (`_iter_records`)
- **Issue:** Export emits runs, nodes, edges, operations, calls, rows, tokens, token_parents, node_states, routing_events, batches, batch_members, artifacts — but NOT `token_outcomes`. Terminal state records (COMPLETED, ROUTED, FAILED, FORKED, etc.) are absent from exports.
- **Impact:** Compliance reviews cannot verify terminal states from exported data. Audit export is incomplete.

### 4. Journal circuit-breaker recovery is unreachable
- **File:** `journal.py:96-97, 118-120, 141-153`
- **Issue:** Once journal disables (5 consecutive write failures), both `_after_cursor_execute` and `_after_commit` short-circuit with `if self._disabled: return`. Recovery logic inside `_append_records` is never called because the hooks never invoke it. Dead code.
- **Impact:** Journal stays disabled forever once tripped. Emergency backup audit stream silently dies.

## Confirmed P2s — Real Bugs, Lower Urgency

| Bug | Original | Notes |
|-----|----------|-------|
| retry-batch non-idempotent | P1→P2 | Crash-during-recovery creates duplicate draft batches. Narrow window. |
| compute-grade nonexistent run | P1→P2 | Returns FULL_REPRODUCIBLE for missing run. No production caller passes bad ID. |
| csv-formatter flatten collision | P1→P2 | Silent overwrite on dotted-key collision. Only affects CSV export format, not DB. |
| explain parent-lineage truthiness | P1→P2 | Uses truthiness instead of `is not None`. Empty string scenario requires DB corruption. |
| explain-row empty source_data_ref | P1→P2 | Truthiness check; `get_row_data()` correctly uses `is not None`. Inconsistency. |
| complete-node-state invalid combos | P1→P2 | Write-then-read catches violations. Defense-in-depth gap, not active corruption. |
| landscapedb-from-url empty DB | P1→P2 | Worse error messages for read-only analysis paths. Not data corruption. |
| nodestaterepository partial invariants | P1→P2 | Silently drops cross-status fields. Requires preceding writer bug to trigger. |
| record-routing-events orphaned payload | P2 | `continue_()` path stores payload but inserts no routing_event rows. Unpurgeable blobs. |
| complete-batch non-terminal status | P2 | No validation guard. All callers pass correct values. |
| complete-run non-terminal status | P2 | No validation guard. All callers pass correct values. Note: bug report misses INTERRUPTED as valid terminal. |
| batch-lineage unbounded IN | P2 | No chunking for `state_ids` IN clause. SQLite limit ~999. |
| get-artifacts no ordering | P2 | Missing `order_by()`. Affects export signing determinism. |
| get-call-response-data no type check | P2 | `json.loads()` return not validated. `get_row_data()` does validate — inconsistency. |
| get-nodes nondeterministic | P2 | All nodes have NULL `sequence_in_pipeline`. No tiebreaker in ORDER BY. Affects export signing. |

## Downgraded to P3 — Theoretical or Pedantic

| Bug | Original | Reason |
|-----|----------|--------|
| record-transform-error wrong run_id | P1→P3 | No production caller passes mismatched IDs. Merge with schema-hardening item. |
| schema cross-run contamination | P1→P3 | Same root cause as above. All callers maintain ID consistency. |
| token-lifecycle no run_id validation | P1→P3 | Same root cause as above. Orchestrator guarantees consistency. |
| create-row legacy payload_ref | P2→P3 | Dead parameter. No caller passes it. Delete per No Legacy Code policy. |
| get-source-schema coerces with str() | P2→P3 | `str()` on already-string value is a no-op. Near-zero practical risk. |
| rowdataresult no state type validation | P2→P3 | StrEnum equality passes for raw strings. All callers use enum members. |
| tokenoutcome boolean is_terminal | P2→P3 | SQLAlchemy/SQLite returns int, never bool. Pedantic type check. |

**Note:** The three P1→P3 bugs (record-transform-error wrong run, schema cross-run, token-lifecycle) describe the **same root cause**: the `tokens` table lacks `run_id`, so downstream tables can't enforce token-to-run ownership via composite FKs. Should be tracked as **one schema-hardening item**.

## Closed — False Positives / Dead Code

| Bug | Original | Reason |
|-----|----------|--------|
| set-run-grade silently no-ops | P1 | **Dead code.** `set_run_grade()` is exported but never called from production code. Production uses `finalize_run()` → `complete_run()` which correctly validates. Delete the function. |
| get-edge-map overwrites duplicates | P1 | **False positive.** `edges` table has `UniqueConstraint("run_id", "from_node_id", "label")`. DB prevents duplicates; dict assignment is safe. |
| register-node default determinism | P2 | **False positive.** Sole production caller (`orchestrator/core.py:1113-1123`) always provides explicit `determinism=` argument. Default value is never used. |

## Cross-Cutting Observations

1. **Truthiness vs `is not None`** — Multiple bugs (#3, #4 in read-path group) stem from using truthiness checks on nullable string columns. Empty string `""` is falsy but not None. Systematic sweep recommended.

2. **Export signing determinism** — Three separate bugs (get-artifacts, get-nodes, csv-flatten) threaten export hash reproducibility. These should be fixed together since they all affect the same signing pipeline.

3. **Missing validation guards** — Complete-batch and complete-run both accept non-terminal statuses. Same two-line guard pattern applies to both. Fix together.

4. **Schema hardening (P3)** — Three bugs consolidate to one root cause: `tokens.run_id` column missing. Low priority but clean fix. Requires Alembic migration.
