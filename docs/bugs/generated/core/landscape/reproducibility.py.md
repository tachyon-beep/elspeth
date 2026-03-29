## Summary

`update_grade_after_purge()` downgrades an entire run to `ATTRIBUTABLE_ONLY` after any payload deletion in that run, even when the purged payload type is not required for replay.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/reproducibility.py
- Line(s): 95-138
- Function/Method: `update_grade_after_purge`

## Evidence

`update_grade_after_purge()` has no visibility into what was purged. It validates the current grade, then unconditionally performs `REPLAY_REPRODUCIBLE -> ATTRIBUTABLE_ONLY` for the run:

```python
conn.execute(
    runs_table.update()
    .where(runs_table.c.run_id == run_id)
    .where(runs_table.c.reproducibility_grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE)
    .values(reproducibility_grade=ReproducibilityGrade.ATTRIBUTABLE_ONLY)
)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/reproducibility.py:131-137`

The caller marks a run as “affected” if **any** deleted ref belonged to that run, across many payload classes:

- `rows.source_data_ref`
- `operations.input_data_ref`
- `operations.output_data_ref`
- `calls.request_ref`
- `calls.response_ref`
- `routing_events.reason_ref`

Source: `/home/john/elspeth/src/elspeth/core/retention/purge.py:100-125`, `/home/john/elspeth/src/elspeth/core/retention/purge.py:268-312`, `/home/john/elspeth/src/elspeth/core/retention/purge.py:388-401`

But the replay path shown in the codebase only requires recorded **call response** payloads. `CallReplayer.replay()` looks up a call by `request_hash`, then fetches `get_call_response_data(call.call_id)`, and fails specifically when the response payload is unavailable:

```python
call = self._recorder.find_call_by_request_hash(...)
call_data = self._recorder.get_call_response_data(call.call_id)

if call_data.state == CallDataState.AVAILABLE:
    ...
elif call_data.state == CallDataState.HASH_ONLY:
    raise ReplayPayloadMissingError(...)
...
else:
    raise ReplayPayloadMissingError(...)
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py:207-249`

`get_call_response_data()` likewise only consults `response_ref` / `response_hash`; request payloads, row payloads, operation payloads, and routing-reason payloads are not part of this replay read path:

```python
if row.response_ref is None:
    if row.response_hash is not None:
        return CallDataResult(state=CallDataState.HASH_ONLY, data=None)
...
payload_bytes = self._payload_store.retrieve(row.response_ref)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:994-1010`

There is already an end-to-end test demonstrating partial purge of only source row payloads, with non-purged payloads remaining available, but no corresponding grade assertion:

Source: `/home/john/elspeth/tests/e2e/audit/test_purge_integrity.py:158-187`

What the code does:
- Treats “some payload in this run was deleted” as equivalent to “this run can no longer be replayed.”

What it should do:
- Downgrade only when purge removed replay-critical payloads for that run.

## Root Cause Hypothesis

This module encodes an over-broad state transition: it equates payload retention loss in general with replay impossibility. That assumption is stronger than the actual replay contract implemented elsewhere in the codebase, which is response-payload-specific. As a result, `reproducibility_grade` can become a false statement about replayability.

## Suggested Fix

Make `update_grade_after_purge()` decide based on replay-critical payload loss, not merely on run membership.

A practical fix would be:

```python
def update_grade_after_purge(db: LandscapeDB, run_id: str, purged_refs: Collection[str]) -> None:
    ...
    # Only degrade if a purged ref matches replay-critical refs for this run.
```

Then have it query only the refs that matter for replay, for example `calls.response_ref` for nondeterministic/external-call replay, and only downgrade if one of those refs was actually deleted. If other payload classes are also truly replay-critical for `IO_READ`/`IO_WRITE`, encode that explicitly here rather than degrading on every payload category.

Also add a regression test covering:
- `REPLAY_REPRODUCIBLE` run
- purge only `rows.source_data_ref` or `calls.request_ref`
- grade must remain `REPLAY_REPRODUCIBLE`
- purge `calls.response_ref`
- grade must become `ATTRIBUTABLE_ONLY`

## Impact

The audit trail can record a run as `ATTRIBUTABLE_ONLY` even though replay still works. That is an audit-state integrity bug: operators and downstream tooling will believe replay is impossible when the implementation can still replay the run. This degrades observability and can cause incorrect retention/replay decisions.
