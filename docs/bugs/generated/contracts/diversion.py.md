## Summary

`SinkWriteResult` does not enforce diversion index invariants, so duplicate or out-of-range `RowDiversion.row_index` values are silently collapsed or ignored downstream, producing incorrect sink audit outcomes instead of crashing on a plugin contract violation.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/diversion.py
- Line(s): 34-40, 57-58
- Function/Method: `RowDiversion.__post_init__`, `SinkWriteResult`

## Evidence

`RowDiversion` only checks that `row_index` is a non-negative int:

```python
34     row_index: int
35     reason: str
36     row_data: Mapping[str, Any]
38     def __post_init__(self) -> None:
39         require_int(self.row_index, "row_index", min_value=0)
40         freeze_fields(self, "row_data")
```

[diversion.py](/home/john/elspeth/src/elspeth/contracts/diversion.py#L34)

`SinkWriteResult` carries the diversion collection but performs no `__post_init__` validation at all:

```python
57     artifact: ArtifactDescriptor
58     diversions: tuple[RowDiversion, ...] = ()
```

[diversion.py](/home/john/elspeth/src/elspeth/contracts/diversion.py#L57)

The executor assumes `row_index` is valid and unique. It partitions tokens by matching indices, then builds a dict keyed by `row_index`:

```python
245         diverted_indices = {d.row_index for d in diversions}
246         primary_tokens = [(token, i) for i, token in enumerate(tokens) if i not in diverted_indices]
247         diverted_tokens = [(token, i) for i, token in enumerate(tokens) if i in diverted_indices]

354             diversion_by_index = {d.row_index: d for d in diversions}
```

[sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py#L245)
[sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py#L354)

What this does:
- Duplicate `row_index` values are overwritten by the later diversion in `diversion_by_index`.
- Out-of-range `row_index` values never match any token, so they disappear from execution entirely.
- A row the sink actually rejected can therefore still be recorded as `COMPLETED` in Phase 2 because it remains in `primary_tokens` ([sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py#L251)).

The current tests only cover valid, unique indices:
- [test_diversion.py](/home/john/elspeth/tests/unit/contracts/test_diversion.py#L53)
- [test_sink_executor_diversion_properties.py](/home/john/elspeth/tests/property/engine/test_sink_executor_diversion_properties.py#L58)
- [test_sink_executor_diversion_properties.py](/home/john/elspeth/tests/property/engine/test_sink_executor_diversion_properties.py#L126)

They do not exercise duplicate or out-of-range diversion metadata.

## Root Cause Hypothesis

The contract in `diversion.py` models diversion correlation with a bare `row_index`, but it does not enforce the core invariants that make that index safe to use: uniqueness and membership in the original batch. Because ELSPETH treats plugins as system-owned code, this should be offensively validated at the contract boundary, not left for the executor to discover implicitly via set/dict behavior.

## Suggested Fix

Add contract validation in `SinkWriteResult.__post_init__` and make the contract carry enough information to validate indices.

Possible shape:
- Add a field such as `input_row_count: int`.
- In `__post_init__`, validate:
  - `diversions` is a tuple of `RowDiversion`
  - each `row_index` is `< input_row_count`
  - no duplicate `row_index` values exist
- Freeze the `diversions` field to satisfy the frozen-dataclass container rule.

Example direction:

```python
@dataclass(frozen=True, slots=True)
class SinkWriteResult:
    artifact: ArtifactDescriptor
    diversions: tuple[RowDiversion, ...] = ()
    input_row_count: int = 0

    def __post_init__(self) -> None:
        freeze_fields(self, "diversions")
        require_int(self.input_row_count, "input_row_count", min_value=0)

        seen: set[int] = set()
        for diversion in self.diversions:
            if diversion.row_index >= self.input_row_count:
                raise ValueError(...)
            if diversion.row_index in seen:
                raise ValueError(...)
            seen.add(diversion.row_index)
```

Also add unit tests for duplicate and out-of-range indices.

## Impact

A malformed diversion result can break audit correctness in exactly the area this contract is supposed to protect:
- rejected rows can be recorded as successfully written to the primary sink
- diversion reasons can be silently overwritten
- diversion metadata can disappear without any terminal state or explicit failure

That violates ELSPETH’s “no silent failures” and “every row reaches exactly one terminal state” requirements, and it does so in sink-write audit recording, which is a high-value accountability path.
