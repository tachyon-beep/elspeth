## Summary

`BufferEntry` is declared `frozen=True` but leaves its generic `result` field mutable, so callers can mutate emitted buffer contents after construction and silently change what downstream code reads.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/engine.py
- Line(s): 11-43
- Function/Method: `BufferEntry.__post_init__`

## Evidence

[`/home/john/elspeth/src/elspeth/contracts/engine.py#L11`](//home/john/elspeth/src/elspeth/contracts/engine.py#L11) defines `BufferEntry` as a frozen dataclass, but [`/home/john/elspeth/src/elspeth/contracts/engine.py#L35`](//home/john/elspeth/src/elspeth/contracts/engine.py#L35) only validates numeric fields and never deep-freezes `result`.

[`/home/john/elspeth/CLAUDE.md#L333`](//home/john/elspeth/CLAUDE.md#L333) explicitly requires every frozen dataclass with container fields to enforce deep immutability in `__post_init__`.

The contract currently accepts mutable payloads. [`/home/john/elspeth/tests/unit/contracts/test_engine_contracts.py#L37`](//home/john/elspeth/tests/unit/contracts/test_engine_contracts.py#L37) constructs a `BufferEntry` with `result={"key": "value"}` and asserts it is stored as-is.

I verified the mutation hole directly:

```python
from elspeth.contracts.engine import BufferEntry
payload = {"key": {"nested": 1}}
entry = BufferEntry(0, 0, payload, 1.0, 2.0, 0.0)
payload["key"]["nested"] = 99
entry.result["added"] = True
print(entry.result)
# {'key': {'nested': 99}, 'added': True}
```

Downstream code consumes `entry.result` after buffering. [`/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L873`](//home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L873) does:

```python
entries = self.executor.execute_batch(...)
query_results = [entry.result for entry in entries]
```

So the code thinks it is handling immutable emitted results, but the contract allows post-emission mutation.

## Root Cause Hypothesis

The contract treats `frozen=True` as sufficient immutability, but `result: T` can be a mutable container and is never passed through `freeze_fields()`/`deep_freeze()`. That violates the repo’s frozen-dataclass contract and makes `BufferEntry` only shallowly immutable.

## Suggested Fix

Deep-freeze `result` in `BufferEntry.__post_init__`, or narrow the contract so `result` cannot be a mutable container.

Example fix:

```python
from elspeth.contracts.freeze import freeze_fields, require_int

def __post_init__(self) -> None:
    require_int(self.submit_index, "BufferEntry.submit_index", min_value=0)
    require_int(self.complete_index, "BufferEntry.complete_index", min_value=0)
    ...
    freeze_fields(self, "result")
```

Add a regression test that mutating the original container or `entry.result` raises / has no effect.

## Impact

Buffered outputs are not actually immutable. A caller can mutate a `BufferEntry` after construction and change the result later consumed by pooled transforms, which undermines thread-safety assumptions and can let audit-adjacent metadata drift after emission.
---
## Summary

`PendingOutcome` accepts `error_hash=""` for `QUARANTINED`/`FAILED`, which allows sink-bound failure outcomes to be recorded with a blank hash even though downstream code treats the hash as the audit key.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/engine.py
- Line(s): 46-85
- Function/Method: `PendingOutcome.__post_init__`

## Evidence

[`/home/john/elspeth/src/elspeth/contracts/engine.py#L75`](//home/john/elspeth/src/elspeth/contracts/engine.py#L75) only rejects `error_hash is None` for failure outcomes:

```python
if self.outcome in self._FAILURE_OUTCOMES and self.error_hash is None:
    raise ValueError(...)
```

A blank hash is currently accepted. I verified this:

```python
from elspeth.contracts.engine import PendingOutcome
from elspeth.contracts.enums import RowOutcome
print(PendingOutcome(RowOutcome.QUARANTINED, ""))
# PendingOutcome(..., error_hash='')
```

That value is later used as grouping and persistence metadata. [`/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L592`](//home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L592) groups pending tokens with:

```python
return (False, pending.outcome.value, pending.error_hash or "")
```

So a blank hash collapses to the same grouping key as any other falsy hash value.

Then [`/home/john/elspeth/src/elspeth/engine/executors/sink.py#L318`](//home/john/elspeth/src/elspeth/engine/executors/sink.py#L318) forwards `pending_outcome.error_hash` into `record_token_outcome()`, and [`/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L229`](//home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L229) only rejects `None`, not `""`, before persisting to [`/home/john/elspeth/src/elspeth/core/landscape/schema.py#L172`](//home/john/elspeth/src/elspeth/core/landscape/schema.py#L172).

What the code does: it treats “non-`None` string” as sufficient.
What it should do: require a real hash value for failure outcomes, because the field exists to identify the failure record.

## Root Cause Hypothesis

`PendingOutcome` validates only presence/absence, not semantic validity. Because the downstream recorder repeats the same weak check, an empty string can flow all the way into `token_outcomes.error_hash`, breaking the assumption that failure outcomes carry a usable hash reference.

## Suggested Fix

Strengthen `PendingOutcome.__post_init__` to reject blank or whitespace-only hashes for failure outcomes, and preferably validate the expected hash format used by the engine.

Example:

```python
if self.outcome in self._FAILURE_OUTCOMES:
    if self.error_hash is None or not self.error_hash.strip():
        raise ValueError(...)
```

A defense-in-depth follow-up in `DataFlowRepository._validate_outcome_fields()` would also be worthwhile, but the primary contract fix belongs here.

## Impact

A `QUARANTINED` or `FAILED` token can reach the audit trail with no usable error identifier. That weakens failure lineage, can group unrelated pending failures together, and makes the “hash of error details” field unreliable for explaining why a token terminated.
