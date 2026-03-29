## Summary

`CoalesceMetadata.for_failure()` and `for_merge()` leak caller-owned `branches_lost` mutations into supposedly frozen audit metadata.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py
- Line(s): 155, 195, 62-72
- Function/Method: `CoalesceMetadata.for_failure`, `CoalesceMetadata.for_merge`, `CoalesceMetadata.__post_init__`

## Evidence

`for_failure()` and `for_merge()` both build `branches_lost` with `MappingProxyType(branches_lost)`:

```python
# /home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py:151-157
return cls(
    policy=policy,
    expected_branches=tuple(expected_branches),
    branches_arrived=tuple(branches_arrived),
    branches_lost=MappingProxyType(branches_lost) if branches_lost is not None else None,
    quorum_required=quorum_required,
    timeout_seconds=timeout_seconds,
)
```

```python
# /home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py:190-197
return cls(
    policy=policy,
    merge_strategy=merge_strategy,
    expected_branches=tuple(expected_branches),
    branches_arrived=tuple(branches_arrived),
    branches_lost=MappingProxyType(branches_lost),
    arrival_order=tuple(arrival_order),
    wait_duration_ms=wait_duration_ms,
)
```

`__post_init__()` then calls `freeze_fields()` only on `branches_lost` and `union_field_collisions` ([coalesce_metadata.py](/home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py#L62)). But `deep_freeze()` preserves an existing `MappingProxyType` when its values are already immutable ([freeze.py](/home/john/elspeth/src/elspeth/contracts/freeze.py#L52)), so the proxy continues to reference the caller’s original dict instead of a detached copy.

I verified it with a runtime repro in this repo:

```python
branches_lost = {"b": "timeout"}
meta = CoalesceMetadata.for_failure(..., branches_lost=branches_lost)
branches_lost["b"] = "mutated"
branches_lost["c"] = "late"
assert dict(meta.branches_lost) == {"b": "mutated", "c": "late"}
```

That behavior violates the project’s own immutability rule in [CLAUDE.md](/home/john/elspeth/CLAUDE.md#L333), which explicitly bans `MappingProxyType(self.x)` because it is a view, not a copy ([CLAUDE.md](/home/john/elspeth/CLAUDE.md#L361)).

Existing tests only check direct raw-dict construction freezes correctly ([test_coalesce_metadata.py](/home/john/elspeth/tests/unit/contracts/test_coalesce_metadata.py#L151)); they do not cover factory aliasing.

## Root Cause Hypothesis

The factories tried to pre-freeze mappings manually with `MappingProxyType(...)`, but that is only a shallow read-only view over caller-owned state. Because `__post_init__()` relies on `freeze_fields()` idempotency, the shallow proxy is treated as “already frozen” and never detached from the original dict.

## Suggested Fix

Do not wrap caller data with `MappingProxyType(...)` in the factories. Pass the raw mapping into the dataclass and let `__post_init__()` deep-freeze it, or explicitly use `deep_freeze()` on the factory input.

Example direction:

```python
return cls(
    policy=policy,
    expected_branches=tuple(expected_branches),
    branches_arrived=tuple(branches_arrived),
    branches_lost=branches_lost,
    ...
)
```

Then add a regression test proving post-construction mutations to the caller’s `branches_lost` dict do not change `meta.branches_lost` for both `for_failure()` and `for_merge()`.

## Impact

Audit metadata can change after construction based on unrelated later mutations to the caller’s dict. In the coalesce path, that means `context_after_json` may record branch-loss reasons that were never true at merge/failure time, breaking audit integrity and the frozen-dataclass contract.
---
## Summary

Direct construction of `CoalesceMetadata` leaves sequence fields mutable, so the class does not actually enforce deep immutability.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py
- Line(s): 65-72, 79-85
- Function/Method: `CoalesceMetadata.__post_init__`

## Evidence

`__post_init__()` freezes only `branches_lost` and `union_field_collisions`:

```python
# /home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py:65-72
fields_to_freeze = []
if self.branches_lost is not None:
    fields_to_freeze.append("branches_lost")
if self.union_field_collisions is not None:
    fields_to_freeze.append("union_field_collisions")
if fields_to_freeze:
    freeze_fields(self, *fields_to_freeze)
```

But the class also contains container fields `expected_branches`, `branches_arrived`, and `arrival_order` ([coalesce_metadata.py](/home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py#L79)). The factories convert those to tuples, but direct construction does not. I verified this runtime behavior:

```python
meta = CoalesceMetadata(
    policy=CoalescePolicy.REQUIRE_ALL,
    expected_branches=["x", "y"],
    branches_arrived=["x"],
    arrival_order=[ArrivalOrderEntry(branch="x", arrival_offset_ms=0.0)],
)
meta.expected_branches.append("z")
meta.branches_arrived.append("y")
meta.arrival_order.append(...)
```

All three mutations succeed.

That contradicts the file header claim that the dataclass “enforces immutability” ([coalesce_metadata.py](/home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py#L4)) and the repo-wide rule that frozen dataclasses with `Mapping`/`Sequence` fields must deep-freeze all container fields in `__post_init__()` ([CLAUDE.md](/home/john/elspeth/CLAUDE.md#L335)).

The current tests cover only mapping freeze guards ([test_coalesce_metadata.py](/home/john/elspeth/tests/unit/contracts/test_coalesce_metadata.py#L151)) and miss these sequence fields.

## Root Cause Hypothesis

The implementation assumed callers would use factory methods, so it only protected the mapping fields that were most obviously mutable. But the class is still publicly constructible, and `frozen=True` does not protect list contents.

## Suggested Fix

Freeze all container fields in `__post_init__()`, not just mappings. That should include:

- `expected_branches`
- `branches_arrived`
- `arrival_order`
- `branches_lost`
- `union_field_collisions`

Then add regression tests showing direct construction with list inputs is normalized to tuples and becomes non-mutable.

## Impact

The contract object can be mutated after construction despite being marked frozen. That undermines the reliability of any code that treats `CoalesceMetadata` as an immutable audit DTO and makes direct-construction call sites a latent source of audit drift.
