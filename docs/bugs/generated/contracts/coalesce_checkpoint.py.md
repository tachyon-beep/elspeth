## Summary

`CoalescePendingCheckpoint.from_dict()` lets malformed nested branch entries escape as raw `AttributeError` instead of raising `AuditIntegrityError`, so corrupted coalesce checkpoints fail with an unstructured exception path during resume.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py`
- Line(s): 132-164, 67-94
- Function/Method: `CoalescePendingCheckpoint.from_dict`, `CoalesceTokenCheckpoint.from_dict`

## Evidence

`CoalescePendingCheckpoint.from_dict()` validates only that `branches` is a `dict`, then blindly calls `CoalesceTokenCheckpoint.from_dict(token)` for each value:

```python
return cls(
    ...
    branches={branch: CoalesceTokenCheckpoint.from_dict(token) for branch, token in branches.items()},
    ...
)
```

[coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L158)

But `CoalesceTokenCheckpoint.from_dict()` immediately does `set(data.keys())` without first verifying `data` is actually a mapping:

```python
missing = required_fields - set(data.keys())
```

[coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L80)

I verified the failure mode directly in this repo:

```python
CoalescePendingCheckpoint.from_dict({
    "coalesce_name": "merge",
    "row_id": "row-1",
    "elapsed_age_seconds": 1.0,
    "branches": {"a": "not-a-dict"},
    "lost_branches": {},
})
```

This raises:

```text
AttributeError
'str' object has no attribute 'keys'
```

Resume paths call this DTO during checkpoint recovery:

[recovery.py](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L175)  
[recovery.py](/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py#L177)

So a corrupted checkpoint currently bypasses the contract’s intended Tier 1 corruption handling and crashes with a generic Python exception instead of an audit-integrity error. Existing tests only cover `branches`/`lost_branches` being non-dicts, not malformed nested token payloads:

[test_coalesce_checkpoint.py](/home/john/elspeth/tests/unit/contracts/test_coalesce_checkpoint.py#L246)

## Root Cause Hypothesis

The deserializer validates container shape at the top level but assumes every nested branch payload is already a `dict[str, Any]`. That assumption is unsafe for Tier 1 checkpoint reconstruction, where corruption must be detected explicitly and reported as `AuditIntegrityError`.

## Suggested Fix

Add an explicit mapping-type check before reading nested token fields, and convert bad nested payloads into `AuditIntegrityError` with branch context.

Helpful shape:

```python
if not isinstance(data, dict):
    raise AuditIntegrityError(
        f"Corrupted coalesce token checkpoint: expected dict, got {type(data).__name__}: {data!r}"
    )
```

Also wrap the branch reconstruction loop so the error names the failing branch key.

## Impact

Resume from a damaged coalesce checkpoint produces a generic `AttributeError` instead of a structured corruption failure. That weakens auditability and makes incident diagnosis harder because the system no longer clearly reports “checkpoint corruption” at the contract boundary.
---
## Summary

`CoalescePendingCheckpoint` does not validate branch-map keys or key/value consistency, so a corrupted checkpoint can restore under one branch key while the embedded token claims another branch, which lets coalesce merge the same logical branch twice.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py`
- Line(s): 104-120, 146-164
- Function/Method: `CoalescePendingCheckpoint.__post_init__`, `CoalescePendingCheckpoint.from_dict`

## Evidence

The contract stores branch arrivals as `branches: Mapping[str, CoalesceTokenCheckpoint]`, but it never enforces either of those invariants:

- keys are strings
- each key matches `token.branch_name`

[coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L104)  
[coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L117)  
[coalesce_checkpoint.py](/home/john/elspeth/src/elspeth/contracts/coalesce_checkpoint.py#L158)

I verified the DTO accepts invalid state:

```python
CoalescePendingCheckpoint(
    coalesce_name="merge",
    row_id="row-1",
    elapsed_age_seconds=1.0,
    branches={1: valid_token_with_branch_name_a},
    lost_branches={},
)
```

This constructs successfully; the stored key is `int(1)` while the token says branch `"a"`.

That matters because restore writes the corrupted mapping key into executor state:

```python
for branch_name, token_checkpoint in pending_entry.branches.items():
    token = TokenInfo(..., branch_name=token_checkpoint.branch_name, ...)
    branches[branch_name] = _BranchEntry(token=token, ...)
```

[coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L272)  
[coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L284)

Downstream coalesce logic trusts the map key, not the token’s embedded branch name, for duplicate detection and merge accounting:

```python
if token.branch_name in pending.branches:
    raise ...
```

[coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L422)

```python
arrived_count = len(pending.branches)
...
return arrived_count == expected_count
```

[coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L465)  
[coalesce_executor.py](/home/john/elspeth/src/elspeth/engine/coalesce_executor.py#L468)

I reproduced the bad behavior with repo test helpers:

- restore a checkpoint whose pending map is `{1: token(branch_name="a")}`
- then accept a live `"a"` token for the same row/coalesce

Observed result:

```text
restored keys: [1]
restored token branch_name: a
held False failure None merged True
```

So the executor merged after seeing keys `[1, "a"]`, treating them as two arrivals even though both represent branch `a`.

There are tests for preserving valid branch state after restore, but no test covering invalid branch keys or key/token mismatch:

[test_coalesce_executor.py](/home/john/elspeth/tests/unit/engine/test_coalesce_executor.py#L2058)  
[test_coalesce_executor.py](/home/john/elspeth/tests/unit/engine/test_coalesce_executor.py#L2117)

## Root Cause Hypothesis

The DTO validates only high-level shape (`branches` is a dict, overlaps with `lost_branches` are forbidden) and assumes branch identity is trustworthy. Because branch identity is encoded twice, once in the mapping key and once inside each token, the contract needs to enforce they agree. Without that, Tier 1 corruption slips into live executor state.

## Suggested Fix

Strengthen `CoalescePendingCheckpoint` validation to enforce:

- every `branches` key is a non-empty `str`
- every `branches` value is a `CoalesceTokenCheckpoint`
- `branch_key == token.branch_name`
- every `lost_branches` key/value is a non-empty `str`

Reject any mismatch with `AuditIntegrityError` in `from_dict()` and `ValueError`/`TypeError` in `__post_init__`.

## Impact

A corrupted coalesce checkpoint can silently violate row-lineage and terminal-state guarantees during resume. The executor may accept a duplicate logical branch, merge too early, and record audit metadata such as `branches_arrived` from corrupted keys rather than real branch identities. That turns checkpoint corruption into incorrect pipeline behavior instead of a clean integrity failure.
