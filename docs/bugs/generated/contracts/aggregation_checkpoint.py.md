## Summary

Aggregation checkpoint deserialization does not enforce Tier 1 scalar/container types, so corrupted checkpoint JSON can deserialize as a “valid” `AggregationCheckpointState` and only fail later with misleading exceptions or wrong-typed token identities.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py
- Line(s): 54-63, 79-112, 135-150, 163-209, 232-237, 249-268
- Function/Method: `AggregationTokenCheckpoint.__post_init__`, `AggregationTokenCheckpoint.from_dict`, `AggregationNodeCheckpoint.__post_init__`, `AggregationNodeCheckpoint.from_dict`, `AggregationCheckpointState.__post_init__`, `AggregationCheckpointState.from_dict`

## Evidence

`AggregationTokenCheckpoint.__post_init__` and the sibling node/state validators check truthiness, not exact types:

```python
if not self.token_id:
    raise ValueError(...)
if not self.row_id:
    raise ValueError(...)
if not self.contract_version:
    raise ValueError(...)
```

and:

```python
if not self.batch_id:
    raise ValueError(...)
...
if not self.version:
    raise ValueError(...)
```

in [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L54) and [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L135) and [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L232).

That means values like `42`, `True`, or `["3.0"]` are accepted if they are truthy. `from_dict()` mostly forwards raw values unchanged instead of rejecting corruption at the DTO boundary, for example in [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L103) and [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L202) and [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L263).

This contract is the recovery boundary: [recovery.py](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L168) calls `AggregationCheckpointState.from_dict(raw)` before building a `ResumePoint`. But sibling Tier 1 contracts are strict:

- [checkpoint.py](/home/john/elspeth/src/elspeth/contracts/checkpoint.py#L57) rejects non-string `token_id`/`node_id`.
- [batch_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/batch_checkpoint.py#L136) explicitly rejects wrong container types in `from_dict()`.
- [coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L185) enforces `version` is a non-empty string.

So this file’s behavior is inconsistent with the repo’s Tier 1 pattern: corrupted checkpoint data is supposed to be rejected immediately as corruption, not accepted and reinterpreted later. For example, a wrong-typed `version` currently reaches [aggregation.py](/home/john/elspeth/src/elspeth/engine/executors/aggregation.py#L709) and is reported as an “incompatible checkpoint version” instead of corrupt checkpoint structure.

## Root Cause Hypothesis

The module was upgraded from raw dicts to frozen dataclasses, but its validation stayed at “non-empty” checks rather than full Tier 1 type guards. The `from_dict()` methods also assume nested objects are already the right shape and do not normalize constructor failures into `AuditIntegrityError`, unlike the batch/coalesce checkpoint contracts.

## Suggested Fix

Add strict type validation for all Tier 1 scalar/container fields in this file, and make `from_dict()` reject malformed shapes with `AuditIntegrityError` before constructing objects.

Helpful changes:
```python
if not isinstance(self.token_id, str):
    raise TypeError(...)
if not isinstance(self.row_id, str):
    raise TypeError(...)
if not isinstance(self.contract_version, str):
    raise TypeError(...)
if not isinstance(self.batch_id, str):
    raise TypeError(...)
if not isinstance(self.version, str):
    raise TypeError(...)
```

Also validate `data`/nested entries are `dict` in each `from_dict()`, and wrap constructor `TypeError`/`ValueError` as `AuditIntegrityError` so corruption is classified consistently.

## Impact

Tier 1 checkpoint corruption is not reliably caught at the contract boundary. A malformed aggregation checkpoint can be:
- misclassified as “version incompatibility” instead of corruption,
- restored with wrong-typed `token_id`/`row_id` values,
- or crash later with generic exceptions outside the checkpoint-corruption path.

That weakens the recovery contract and makes audit/debug outcomes less trustworthy precisely where the code claims to enforce “crash on corruption.”
---
## Summary

`AggregationNodeCheckpoint` is declared `frozen=True` but leaves `tokens` mutable and unvalidated, so callers can construct a “frozen” checkpoint object backed by a mutable list and mutate the buffered-token snapshot after creation.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py
- Line(s): 128-150
- Function/Method: `AggregationNodeCheckpoint.__post_init__`

## Evidence

The dataclass has a container field:

```python
tokens: tuple[AggregationTokenCheckpoint, ...]
```

but `__post_init__` never freezes or coerces it:

```python
def __post_init__(self) -> None:
    ...
    if not isinstance(self.contract, (dict, MappingProxyType)):
        raise TypeError(...)
    freeze_fields(self, "contract")
```

from [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L128).

The project standard explicitly says every frozen dataclass with container fields must deep-freeze them in `__post_init__`; see [CLAUDE.md](/home/john/elspeth/CLAUDE.md#L333). This file freezes `row_data`, `contract`, and `nodes`, but not `tokens`.

That matters because checkpoint persistence serializes the current object graph directly:
- [aggregation_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/aggregation_checkpoint.py#L155) iterates `self.tokens`
- [manager.py](/home/john/elspeth/src/elspeth/core/checkpoint/manager.py#L103) persists `aggregation_state.to_dict()`

So if a caller constructs `AggregationNodeCheckpoint(tokens=[...], ...)`, the list remains mutable even though the dataclass is “frozen”.

## Root Cause Hypothesis

The refactor focused on freezing mapping fields and overlooked that `tokens` is also a container field. Because normal production construction uses tuples, the gap stayed hidden, but the contract itself still violates the repo’s frozen-dataclass rule.

## Suggested Fix

Freeze and validate `tokens` in `AggregationNodeCheckpoint.__post_init__`.

For example:
```python
object.__setattr__(self, "tokens", tuple(self.tokens))
for i, token in enumerate(self.tokens):
    if not isinstance(token, AggregationTokenCheckpoint):
        raise TypeError(...)
```

If preferred, use `freeze_fields(self, "tokens", "contract")` after converting/validating element types.

## Impact

The checkpoint DTO is not actually immutable. A caller can mutate buffered tokens after constructing the checkpoint object, changing what gets serialized and persisted. That undermines the idea that checkpoint state is a stable audit snapshot and makes tests or helper code prone to accidental state drift.
