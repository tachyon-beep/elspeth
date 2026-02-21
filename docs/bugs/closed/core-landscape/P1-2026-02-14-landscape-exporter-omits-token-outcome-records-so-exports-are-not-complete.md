## Summary

`LandscapeExporter` omits `token_outcome` records, so exports are not actually complete for terminal-state audit lineage.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/core/landscape/exporter.py`
- Line(s): 32-46, 153-525
- Function/Method: `LandscapeExporter._iter_records`

## Evidence

`exporter.py` declares/exports many record types, but never includes token outcomes:

```python
# src/elspeth/core/landscape/exporter.py:32-46
# Record types:
# - run
# - secret_resolution
# - node
# - edge
# - operation
# - row
# - token
# - token_parent
# - node_state
# - routing_event
# - call
# - batch
# - batch_member
# - artifact
```

And `_iter_records()` emits rows/tokens/states/routing/calls/batches/artifacts only (`src/elspeth/core/landscape/exporter.py:153-525`), with no call to any token outcome query.

But terminal outcomes are explicitly recorded and contract-critical:

- `token_outcomes` is a first-class audit table (`src/elspeth/core/landscape/schema.py:144-177`).
- Recorder writes every outcome via `record_token_outcome()` (`src/elspeth/core/landscape/_token_recording.py:506-569`).
- Contract states: `token_outcomes` is the authoritative terminal-state record, and `node_states` do not replace it (`docs/contracts/token-outcomes/00-token-outcome-contract.md:53-56`).
- Project audit standard requires explicit terminal states/no silent drops (`CLAUDE.md:554-567`).

So exporter behavior is incomplete versus the audit model it is supposed to export.

## Root Cause Hypothesis

`LandscapeExporter` was expanded for batches/calls but not updated after AUD-001 introduced explicit `token_outcomes` as authoritative terminal-state records.

## Suggested Fix

Add `token_outcome` export support in `src/elspeth/core/landscape/exporter.py`:

1. Include `token_outcome` in documented record types.
2. Emit `token_outcome` records in `_iter_records()` with fields from `TokenOutcome`:
   - `outcome_id`, `run_id`, `token_id`, `outcome`, `is_terminal`, `recorded_at`,
   - `sink_name`, `batch_id`, `fork_group_id`, `join_group_id`, `expand_group_id`,
   - `error_hash`, `context_json`, `expected_branches_json`.
3. Keep deterministic ordering (prefer batch preload/grouping by token or row).
4. Update exporter tests to assert `token_outcome` presence/counts.

## Impact

Audit exports currently lose authoritative terminal-state evidence. For compliance/review exports, this breaks full lineage proof for outcomes like `FORKED`, `COALESCED`, `CONSUMED_IN_BATCH`, `EXPANDED`, and `BUFFERED→terminal` transitions, weakening "no silent drops" guarantees even though data exists in the DB.
