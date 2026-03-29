## Summary

`explain()` accepts corrupted parent lineage and can return parent tokens from a different row or run because it only checks that each parent token exists, not that it belongs to the same lineage scope as the child token.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/core/landscape/lineage.py`
- Line(s): 225-236
- Function/Method: `explain`

## Evidence

`explain()` validates that the child token’s group IDs and `token_parents` links are present, then loads each parent token and appends it immediately:

```python
for parent in parents:
    parent_token = recorder.get_token(parent.parent_token_id)
    if parent_token is None:
        raise AuditIntegrityError(...)
    parent_tokens.append(parent_token)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/lineage.py:225`

There is no check here that `parent_token.run_id == token.run_id` or `parent_token.row_id == token.row_id`.

That missing check matters because the write path explicitly treats cross-run and cross-row parentage as audit corruption and rejects it before insertion:

```python
self._validate_token_run_ownership(parent_token_id, run_id)
self._validate_token_row_ownership(parent_token_id, row_id)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:461`
Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:462`
Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:670`
Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:671`
Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:567-573`

The repository’s own integrity helpers describe cross-run contamination as audit corruption and cross-row lineage as invalid:

```python
raise AuditIntegrityError(
    f"Cross-run contamination prevented: token {token_id!r} belongs to "
    f"run {actual_run_id!r}, but caller supplied run_id={run_id!r}. "
)
```

```python
raise AuditIntegrityError(
    f"Cross-row lineage corruption prevented: token {token_id!r} belongs to "
    f"row {actual_row_id!r}, but caller supplied row_id={row_id!r}. "
)
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:163-167`
Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:184-188`

Schema-level protection is weaker than the write-path checks: `token_parents` stores only `token_id` and `parent_token_id`, with no `run_id` or `row_id` constraint tying parent and child to the same lineage scope.

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:191-202`

So if the table is ever corrupted or written outside the guarded path, `explain()` will reconstruct and return impossible lineage instead of crashing.

## Root Cause Hypothesis

The module assumes that “parent exists” is sufficient because normal writers already validate lineage ownership. But `token_parents` is not schema-constrained to same-row/same-run parents, and `explain()` is the read-side audit function that should defensively verify Tier 1 invariants. That final integrity check was omitted.

## Suggested Fix

In `explain()`, after loading each `parent_token`, assert that it matches the child token’s `row_id` and `run_id` before appending it.

Example shape:

```python
if parent_token.run_id != token.run_id:
    raise AuditIntegrityError(
        f"Audit integrity violation: parent token '{parent_token.token_id}' belongs to "
        f"run '{parent_token.run_id}', but child token '{token_id}' belongs to "
        f"run '{token.run_id}'. Cross-run lineage is impossible."
    )

if parent_token.row_id != token.row_id:
    raise AuditIntegrityError(
        f"Audit integrity violation: parent token '{parent_token.token_id}' belongs to "
        f"row '{parent_token.row_id}', but child token '{token_id}' belongs to "
        f"row '{token.row_id}'. Cross-row lineage is impossible."
    )
```

A regression test should cover:
- child token with valid `fork_group_id` plus a parent token from another run
- child token with valid `join_group_id` plus a parent token from another row

## Impact

A corrupted `token_parents` row can make `explain()` present lineage that crosses rows or runs, which breaks the audit trail’s attributability guarantee. Instead of “crash on Tier 1 anomaly,” the current code can return a plausible-looking but false parent chain, undermining forensic trust in fork/coalesce/expand lineage.
