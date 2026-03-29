## Summary

`complete_node_state()` can commit terminal rows that violate the `NodeState` status contract, then only discover the corruption after the transaction has already committed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/execution_repository.py
- Line(s): 263-317
- Function/Method: `complete_node_state`

## Evidence

`complete_node_state()` only validates two positive requirements before writing:

```python
if status == NodeStateStatus.COMPLETED and output_data is None:
    raise ValueError(...)
if status == NodeStateStatus.FAILED and error is None:
    raise ValueError(...)
...
output_hash = stable_hash(output_data) if output_data is not None else None
...
error_json = canonical_json(error_data) if error is not None else None
success_reason_json = canonical_json(success_reason) if success_reason is not None else None
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:269](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L269), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:276](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L276), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:279](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L279), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:286](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L286)

That means these invalid combinations are accepted and written:
- `PENDING` with `output_data`
- `PENDING` with `error`
- `PENDING` with `success_reason`
- `COMPLETED` with `error`
- `FAILED` with `success_reason`

The write commits before loader validation runs:

```python
with self._db.connection() as conn:
    conn.execute(update ...)
    row = conn.execute(select(...)).fetchone()

result = self._node_state_loader.load(row)
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:290](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L290), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:313](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L313)

`LandscapeDB.connection()` uses `engine.begin()`, which auto-commits when the `with` block exits successfully:

Source: [/home/john/elspeth/src/elspeth/core/landscape/database.py:570-583](/home/john/elspeth/src/elspeth/core/landscape/database.py#L570)

The loader explicitly rejects those same states as audit corruption:

- `PENDING` must have `output_hash is NULL`, `error_json is NULL`, `success_reason_json is NULL`
- `COMPLETED` must have `error_json is NULL`
- `FAILED` must have `success_reason_json is NULL`

Source: [/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py:315-327](/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py#L315), [/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py:344-354](/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py#L344), [/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py:372-380](/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py#L372)

So the method can persist an invalid row and only then raise.

## Root Cause Hypothesis

The repository validates only required fields, not forbidden fields, and it performs Tier-1 invariant checking after the transaction has committed instead of before commit.

## Suggested Fix

Add explicit status-dependent guards before any write:
- `PENDING`: require `output_data is None`, `error is None`, `success_reason is None`
- `COMPLETED`: require `error is None`
- `FAILED`: require `success_reason is None`

Also keep validation inside the transaction boundary, either by:
- constructing/loading the expected typed result before leaving the `with self._db.connection()` block, or
- computing the exact column set per status so invalid combinations can never be written.

## Impact

A bad internal call can permanently corrupt `node_states`, which is Tier-1 audit data. After that, later reads, exporters, or explain flows can fail on a row that this repository itself wrote, violating the “audit trail is pristine” guarantee.
---
## Summary

`complete_operation()` can persist impossible operation lifecycle states that violate the `Operation` contract, and it never validates them before returning.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/execution_repository.py
- Line(s): 691-748
- Function/Method: `complete_operation`

## Evidence

`complete_operation()` accepts any combination of `status`, `error`, `duration_ms`, and `output_data` and writes it directly:

```python
stmt = (
    operations_table.update()
    .where((operations_table.c.operation_id == operation_id) & (operations_table.c.status == "open"))
    .values(
        completed_at=timestamp,
        status=status,
        error_message=error,
        duration_ms=duration_ms,
        output_data_hash=output_hash,
    )
)
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:718-727](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L718)

But the `Operation` contract requires:
- `completed` -> `completed_at` and `duration_ms` present, `error_message` must be `None`
- `failed` -> `completed_at`, `duration_ms`, and `error_message` all required
- `pending` -> `completed_at` and `duration_ms` required

Source: [/home/john/elspeth/src/elspeth/contracts/audit.py:711-739](/home/john/elspeth/src/elspeth/contracts/audit.py#L711)

`OperationLoader` enforces those invariants only when someone later reads the row:

Source: [/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py:578-600](/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py#L578)

Unlike `complete_node_state()`, `complete_operation()` does not reload the row at all, so invalid audit rows can be written silently. The tests around this method cover only valid paths and duplicate/nonexistent IDs, not invalid status-field combinations.

Source: [/home/john/elspeth/tests/unit/core/landscape/test_call_recording.py:319-401](/home/john/elspeth/tests/unit/core/landscape/test_call_recording.py#L319), [/home/john/elspeth/tests/unit/core/landscape/test_execution_repository.py:432-488](/home/john/elspeth/tests/unit/core/landscape/test_execution_repository.py#L432)

## Root Cause Hypothesis

The method treats `operations` as a simple status update path and relies on downstream dataclass validation to catch impossible states, but that validation is not part of the write path.

## Suggested Fix

Validate status-dependent invariants before updating:
- reject `status="completed"` when `error` is provided
- reject `status="failed"` when `error` is missing
- reject terminal statuses when `duration_ms` is missing

Optionally load/validate the updated row before commit, matching the stricter pattern intended for Tier-1 audit data.

## Impact

Source and sink operation records can claim impossible states like “completed with an error message” or “failed with no error”. That corrupts the audit trail for source/sink I/O and can break later readers unpredictably.
---
## Summary

Payload blobs are persisted before their referencing SQL rows are inserted, so any later insert failure leaks unreferenced payloads that retention can never find.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/execution_repository.py
- Line(s): 368-370, 429-431, 541-548, 598-622, 672-688, 816-840
- Function/Method: `record_routing_event`, `record_routing_events`, `_prepare_call_payloads`, `record_call`, `begin_operation`, `record_operation_call`

## Evidence

These methods store payloads before the DB insert that references them:

```python
reason_ref = self._payload_store.store(reason_bytes)
...
self._ops.execute_insert(routing_events_table.insert().values(...))
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:368-370](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L368), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:384-396](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L384)

```python
request_ref = self._payload_store.store(request_bytes)
response_ref = self._payload_store.store(response_bytes)
...
self._ops.execute_insert(calls_table.insert().values(**values))
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:541-548](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L541), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:622](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L622), [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:840](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L840)

```python
input_ref = self._payload_store.store(input_bytes)
...
self._ops.execute_insert(operations_table.insert().values(**operation.to_dict()))
```

Source: [/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:672-688](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L672)

There are already tested insert-failure paths for calls:
- duplicate `(state_id, call_index)` raises `IntegrityError`
- invalid `state_id` raises `IntegrityError`

Source: [/home/john/elspeth/tests/integration/audit/test_recorder_calls.py:228-268](/home/john/elspeth/tests/integration/audit/test_recorder_calls.py#L228)

Retention only discovers payload refs by scanning DB tables and joins; it has no way to find blobs that were stored but never referenced:

Source: [/home/john/elspeth/src/elspeth/core/retention/purge.py:100-128](/home/john/elspeth/src/elspeth/core/retention/purge.py#L100)

So a failed insert leaves a blob on disk forever.

## Root Cause Hypothesis

The payload store is being used as a pre-insert side effect, but garbage collection is entirely DB-reference-driven. That makes insert failures leak unreachable content-addressed blobs.

## Suggested Fix

Rework these paths to avoid storing payloads before the relational row exists. A safer pattern is:
1. insert the audit row with hashes and `*_ref=NULL`
2. store the payload
3. update the row with the ref inside the same DB transaction window where possible

At minimum, wrap the insert path so that any `IntegrityError` after `store()` triggers best-effort deletion of the just-created blob.

## Impact

This does not falsify row lineage directly, but it causes permanent payload-store leaks outside retention accounting. Over time, repeated invalid/duplicate writes can grow disk usage with blobs that are invisible to the purge system.
