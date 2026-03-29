## Summary

`coalesce_tokens()` accepts an empty `parent_token_ids` list and creates a merged token with `join_group_id` but no `token_parents` rows, manufacturing audit-corrupt lineage.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py
- Line(s): 565-623
- Function/Method: `coalesce_tokens`

## Evidence

`coalesce_tokens()` never rejects an empty parent list. When `parent_token_ids` is empty, the validation loop is skipped, `run_id` is derived from the row, and the method still inserts a merged token:

```python
run_id: str | None = None
for parent_id in parent_token_ids:
    ...
if run_id is None:
    run_id = self._resolve_run_id_for_row(row_id)

...
conn.execute(
    tokens_table.insert().values(
        token_id=token_id,
        row_id=row_id,
        run_id=run_id,
        join_group_id=join_group_id,
        ...
    )
)
```

Source: [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L565)

That produces a token with `join_group_id` but zero parent links. The lineage layer treats exactly that shape as audit corruption and raises:

```python
if set_groups and not parents:
    ...
    raise AuditIntegrityError(
        ... "has {group_type}_group_id=... but no parent relationships ..."
    )
```

Source: [lineage.py](/home/john/elspeth/src/elspeth/core/landscape/lineage.py#L208)

The invariant is also tested explicitly for grouped tokens without parents:

```python
"""Token with fork_group_id but no parents is audit corruption."""
with pytest.raises(AuditIntegrityError, match="Audit integrity violation"):
    explain(...)
```

Source: [test_lineage.py](/home/john/elspeth/tests/unit/core/landscape/test_lineage.py#L280)

By contrast, the engine-facing `TokenManager.coalesce_tokens()` already rejects empty parents before calling the recorder:

```python
if not parents:
    raise OrchestrationInvariantError("coalesce_tokens requires at least one parent token")
```

Source: [tokens.py](/home/john/elspeth/src/elspeth/engine/tokens.py#L282)

So the repository currently relies on an upstream caller guard instead of enforcing its own audit invariant.

## Root Cause Hypothesis

The repository assumes all callers come through `TokenManager`, which already validates non-empty parents. But `LandscapeRecorder.coalesce_tokens()` delegates directly to this repository, so the repository method remains publicly callable with `[]` and can write an impossible audit state.

## Suggested Fix

Reject empty parent lists inside `DataFlowRepository.coalesce_tokens()` before any writes, similar to `fork_token()` and `expand_token()`:

```python
if not parent_token_ids:
    raise ValueError("coalesce_tokens requires at least one parent token")
```

A regression test should call `recorder.coalesce_tokens(parent_token_ids=[], row_id=...)` and assert that no token is inserted.

## Impact

A caller can persist a coalesced token that cannot be explained, breaking the “complete lineage back to source” guarantee in CLAUDE.md. The token looks valid in `tokens` but is unusable in `explain()`, which is silent data corruption of the audit graph rather than a clean crash at the write boundary.
---
## Summary

`create_token()` allows callers to persist impossible lineage metadata combinations such as both `fork_group_id` and `join_group_id`, creating tokens that the audit reader later classifies as corruption.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py
- Line(s): 365-421
- Function/Method: `create_token`

## Evidence

`create_token()` accepts independent `branch_name`, `fork_group_id`, and `join_group_id` parameters, then inserts them without any invariant checks:

```python
def create_token(
    self,
    row_id: str,
    *,
    token_id: str | None = None,
    branch_name: str | None = None,
    fork_group_id: str | None = None,
    join_group_id: str | None = None,
) -> Token:
    ...
    token = Token(
        token_id=token_id,
        row_id=row_id,
        fork_group_id=fork_group_id,
        join_group_id=join_group_id,
        branch_name=branch_name,
        ...
    )
```

Source: [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L365)

The `Token` dataclass itself only validates `step_in_pipeline`; it does not reject conflicting lineage fields:

```python
@dataclass(frozen=True, slots=True)
class Token:
    ...
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None
```

Source: [audit.py](/home/john/elspeth/src/elspeth/contracts/audit.py#L142)

But the lineage reader requires XOR semantics across group IDs and crashes if more than one is set:

```python
set_groups = [k for k, v in group_ids.items() if v is not None]
if len(set_groups) > 1:
    raise AuditIntegrityError(
        ... "has multiple group IDs set" ...
    )
```

Source: [lineage.py](/home/john/elspeth/src/elspeth/core/landscape/lineage.py#L201)

That invariant is covered by a unit test:

```python
token = _make_token(fork_group_id="fg-1", join_group_id="jg-1")
with pytest.raises(AuditIntegrityError, match=r"multiple group IDs"):
    explain(...)
```

Source: [test_lineage.py](/home/john/elspeth/tests/unit/core/landscape/test_lineage.py#L391)

So `create_token()` can write a token shape that the read path already defines as invalid Tier 1 data.

## Root Cause Hypothesis

The repository exposes low-level lineage fields for flexibility but does not enforce the same invariants the query side assumes. That leaves write-time validation weaker than read-time validation, so impossible token states can be committed and only discovered later during explanation.

## Suggested Fix

Validate lineage metadata in `create_token()` before insertion.

At minimum:
- Reject more than one of `fork_group_id`, `join_group_id`, `expand_group_id`
- Reject `branch_name` without `fork_group_id`
- Reject empty-string group IDs

A small private helper used by `create_token()`, `fork_token()`, `coalesce_tokens()`, and `expand_token()` would keep the invariant centralized.

## Impact

This permits self-inflicted Tier 1 corruption in the audit database. Any token written with conflicting group metadata becomes non-explainable and undermines the audit trail’s trust model, because the repository records states that later code treats as impossible.
