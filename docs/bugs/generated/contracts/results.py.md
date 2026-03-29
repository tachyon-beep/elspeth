## Summary

`TransformResult` accepts a "success" object with both `row` and `rows` populated, and the engine then silently treats it as single-row output, dropping the multi-row payload.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/results.py
- Line(s): 136-165
- Function/Method: `TransformResult.__post_init__`

## Evidence

`TransformResult.__post_init__` enforces "success must have some output" but never enforces the single-row and multi-row shapes are mutually exclusive:

```python
if self.status == "success" and self.row is None and self.rows is None:
    raise ValueError(...)
```

There is no corresponding guard for `self.row is not None and self.rows is not None` in [`/home/john/elspeth/src/elspeth/contracts/results.py`](\/home/john/elspeth/src/elspeth/contracts/results.py#L136).

Downstream, the executor and processor both privilege `row` over `rows`:

```python
if result.row is not None:
    result.output_hash = stable_hash(result.row)
elif result.rows is not None:
    result.output_hash = stable_hash(result.rows)
```

in [`/home/john/elspeth/src/elspeth/engine/executors/transform.py`](\/home/john/elspeth/src/elspeth/engine/executors/transform.py#L343)

and:

```python
if result.row is not None:
    output_data = result.row.to_dict()
else:
    output_data = [r.to_dict() for r in result.rows]
```

in [`/home/john/elspeth/src/elspeth/engine/executors/transform.py`](\/home/john/elspeth/src/elspeth/engine/executors/transform.py#L369)

Then deaggregation only happens when `is_multi_row` is true, which is defined as `self.rows is not None` in the target file, but the executor has already updated the token with `row` when `row is not None`:

```python
if result.row is not None:
    updated_token = token.with_updated_data(result.row)
else:
    updated_token = token.with_updated_data(token.row_data)
```

in [`/home/john/elspeth/src/elspeth/engine/executors/transform.py`](\/home/john/elspeth/src/elspeth/engine/executors/transform.py#L408)

and the processor expands child tokens from `transform_result.rows` only later if `is_multi_row` is true:

```python
if transform_result.is_multi_row:
    expanded_rows=[r.to_dict() for r in transform_result.rows]
```

in [`/home/john/elspeth/src/elspeth/engine/processor.py`](\/home/john/elspeth/src/elspeth/engine/processor.py#L1608).

So a malformed success result with both fields set produces contradictory audit behavior: node-state output and token update follow `row`, while expansion follows `rows`.

## Root Cause Hypothesis

The target contract validates presence but not exclusivity. That leaves an impossible state constructible through direct dataclass use, and downstream code resolves the ambiguity inconsistently by checking `row` first in some places and `rows` in others.

## Suggested Fix

Add an XOR invariant for success results in `TransformResult.__post_init__`:

```python
if self.status == "success" and (self.row is not None) == (self.rows is not None):
    raise ValueError(
        "TransformResult with status='success' MUST provide exactly one of row or rows."
    )
```

Also add a regression test that direct construction with both fields set raises.

## Impact

This can cause silent data loss or contradictory lineage for multi-row transforms: the audit trail can record one output shape while downstream token expansion uses another. That violates the "no silent drops" and complete-lineage requirements for row processing.
---
## Summary

`SourceRow.valid()` allows creation of a non-quarantined row with `contract=None`, even though the engine requires every valid source row to have a contract and crashes later when tokenization begins.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/results.py
- Line(s): 512-545
- Function/Method: `SourceRow.__post_init__` / `SourceRow.valid`

## Evidence

The target file explicitly permits this shape:

```python
@classmethod
def valid(
    cls,
    row: dict[str, Any],
    contract: SchemaContract | None = None,
) -> SourceRow:
    return cls(row=row, is_quarantined=False, contract=contract)
```

in [`/home/john/elspeth/src/elspeth/contracts/results.py`](\/home/john/elspeth/src/elspeth/contracts/results.py#L530)

and `__post_init__` checks only quarantine metadata, not the valid-row contract invariant:

```python
if self.is_quarantined:
    ...
else:
    if self.quarantine_error is not None: ...
    if self.quarantine_destination is not None: ...
```

in [`/home/john/elspeth/src/elspeth/contracts/results.py`](\/home/john/elspeth/src/elspeth/contracts/results.py#L512)

But the engine refuses to process such a row:

```python
if source_row.contract is None:
    raise OrchestrationInvariantError(
        "SourceRow must have contract to create token. Source plugins must set contract on all valid rows."
    )
```

in [`/home/john/elspeth/src/elspeth/engine/tokens.py`](\/home/john/elspeth/src/elspeth/engine/tokens.py#L93)

and `SourceRow.to_pipeline_row()` also fails:

```python
if self.contract is None:
    raise FrameworkBugError("SourceRow has no contract ...")
```

in [`/home/john/elspeth/src/elspeth/contracts/results.py`](\/home/john/elspeth/src/elspeth/contracts/results.py#L584)

The public protocol example even advertises the invalid construction:

```python
for row in reader:
    yield SourceRow.valid(row)
```

in [`/home/john/elspeth/src/elspeth/contracts/plugin_protocols.py`](\/home/john/elspeth/src/elspeth/contracts/plugin_protocols.py#L52)

So the contract object accepts a state the engine rejects, and the published example points plugin authors toward it.

## Root Cause Hypothesis

`SourceRow` currently models "valid vs quarantined" but does not encode the stronger invariant that valid rows are already paired with a schema contract before entering Tier 2 pipeline processing. The constructor and docs lag behind the engine’s actual requirement.

## Suggested Fix

Make contract mandatory for non-quarantined rows in the target file. Either:

```python
if not self.is_quarantined and self.contract is None:
    raise ValueError("Valid SourceRow must have contract")
```

in `__post_init__`, or remove the optional default from `SourceRow.valid()`.

Update the source protocol/example text to show `SourceRow.valid(row, contract=contract)`.

## Impact

This is a contract/API bug that turns a seemingly valid `SourceRow` into a runtime crash during token creation. It does not silently corrupt audit data, but it creates a misleading public contract in the target file and can break source plugins at first-row processing time.
