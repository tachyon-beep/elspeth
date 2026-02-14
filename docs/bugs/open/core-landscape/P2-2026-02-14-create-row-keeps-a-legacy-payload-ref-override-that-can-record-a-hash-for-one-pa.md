## Summary

`create_row()` keeps a legacy `payload_ref` override that can record a hash for one payload while referencing different payload bytes.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — dead parameter; no production caller passes payload_ref)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/landscape/_token_recording.py
- Line(s): 55-57, 100-112
- Function/Method: `create_row`

## Evidence

`create_row()` computes `source_data_hash` from `data`, but if `payload_ref` is passed it skips recorder-managed persistence and trusts that reference:

```python
# _token_recording.py
data_hash = stable_hash(data)
final_payload_ref = payload_ref
if self._payload_store is not None and payload_ref is None:
    payload_bytes = canonical_json(data).encode("utf-8")
    final_payload_ref = self._payload_store.store(payload_bytes)
```

`get_row_data()` later returns payload by ref only (`source_data_ref`) without checking against `source_data_hash`: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_query_methods.py:137-146`.

I verified this with `MockPayloadStore`: storing payload `{"actual":"B"}`, then calling `create_row(data={"actual":"A"}, payload_ref=<refB>)` produced:
- `source_data_hash == stable_hash({"actual":"A"})`
- retrieved row payload `{"actual":"B"}`

So hash and referenced payload can silently diverge.

## Root Cause Hypothesis

A deprecated compatibility path (`payload_ref`) remained in `create_row()`, bypassing the “Landscape owns payload persistence” invariant.

## Suggested Fix

Remove `payload_ref` override from `create_row()` and always persist from `data` when payload store is configured. If immediate removal is impossible, validate provided `payload_ref` by retrieving bytes and verifying hash equivalence before insert, then fail hard on mismatch.

## Impact

Audit evidence can become internally inconsistent (hash says one thing, stored payload says another), weakening integrity and explainability of source-row records.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_token_recording.py.md`
- Finding index in source report: 2
- Beads: pending

Triage: Downgraded P2→P3. Parameter already documented as DEPRECATED. No production code passes payload_ref. Fix is to delete the parameter per No Legacy Code policy. Cleanup task, not bug fix.
