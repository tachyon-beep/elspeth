## Summary

`ResumePoint` does not enforce that its duplicated `token_id`, `node_id`, and `sequence_number` fields match the embedded `Checkpoint`, so callers can hand `Orchestrator.resume()` an internally inconsistent resume contract and make resume operate on unaudited progress data.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/checkpoint.py`
- Line(s): 43-73
- Function/Method: `ResumePoint.__post_init__`

## Evidence

`ResumePoint` stores the checkpoint and also repeats three fields from it:

```python
checkpoint: Checkpoint
token_id: str
node_id: str
sequence_number: int
```

But its validation only checks types / emptiness:

```python
if not isinstance(self.checkpoint, Checkpoint):
    raise TypeError(...)
...
require_int(self.sequence_number, "ResumePoint.sequence_number", min_value=0)
```

Source: `/home/john/elspeth/src/elspeth/contracts/checkpoint.py:43-73`

There is no invariant check that:

- `self.token_id == self.checkpoint.token_id`
- `self.node_id == self.checkpoint.node_id`
- `self.sequence_number == self.checkpoint.sequence_number`

That matters because resume code consumes the duplicated fields independently instead of always reading from `checkpoint`:

```python
self._rebase_checkpoint_sequence(resume_point.sequence_number)
...
if resume_point.aggregation_state is not None:
    restored_state[resume_point.node_id] = resume_point.aggregation_state
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2583-2599`, `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:2679-2683`

Checkpoint creation relies on `sequence_number` being a monotonic progress marker:

```python
Column("sequence_number", Integer, nullable=False),  # Monotonic progress marker
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:475-507`

and resumed runs re-use that rebased value for future checkpoints:

```python
self._sequence_number += 1
...
sequence_number=self._sequence_number,
```

Source: `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:365-394`

So a forged or buggy `ResumePoint(sequence_number=0, checkpoint.sequence_number=500, ...)` is accepted by the target file today, and the resumed run will start checkpoint numbering from the wrong place even though the audited checkpoint says otherwise.

Tests only cover type/emptiness guards for `ResumePoint`; there is no regression test for cross-field consistency. Source: `/home/john/elspeth/tests/unit/contracts/test_checkpoint.py:81-299`

## Root Cause Hypothesis

`ResumePoint` was modeled as a convenience DTO that duplicated selected checkpoint fields for easier access, but the contract never encoded the invariant that those duplicates are derived data, not independent inputs. As a result, Tier 1 checkpoint identity can diverge inside a supposedly trustworthy frozen dataclass.

## Suggested Fix

Treat the duplicated fields as integrity-checked mirrors of the embedded checkpoint.

Add explicit invariant checks in `ResumePoint.__post_init__`, for example:

```python
if self.token_id != self.checkpoint.token_id:
    raise ValueError(
        f"ResumePoint.token_id {self.token_id!r} does not match "
        f"checkpoint.token_id {self.checkpoint.token_id!r}"
    )
if self.node_id != self.checkpoint.node_id:
    raise ValueError(
        f"ResumePoint.node_id {self.node_id!r} does not match "
        f"checkpoint.node_id {self.checkpoint.node_id!r}"
    )
if self.sequence_number != self.checkpoint.sequence_number:
    raise ValueError(
        f"ResumePoint.sequence_number {self.sequence_number!r} does not match "
        f"checkpoint.sequence_number {self.checkpoint.sequence_number!r}"
    )
```

Also add unit tests covering mismatched `token_id`, `node_id`, and `sequence_number`.

A stronger alternative is to remove the duplicated fields entirely and make callers read from `resume_point.checkpoint`, but the minimal fix belongs in this file.

## Impact

Resume can proceed using progress metadata that was never recorded in the checkpoint row, which undermines checkpoint/audit integrity. The most concrete failure is incorrect checkpoint sequence rebasing after resume, causing future checkpoints to be written with misleading or non-monotonic progress markers for the same run. That weakens recovery ordering guarantees and makes post-incident reasoning about resumed runs unreliable.
