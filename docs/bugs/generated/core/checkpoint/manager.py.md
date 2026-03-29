## Summary

`CheckpointManager.create_checkpoint()` can record a checkpoint for `run_id` B while pointing at a `token_id` that actually belongs to `run_id` A, creating a cross-run checkpoint record that corrupts audit lineage.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/checkpoint/manager.py
- Line(s): 58-144
- Function/Method: `CheckpointManager.create_checkpoint`

## Evidence

`create_checkpoint()` validates only that the supplied `node_id` exists in the in-memory graph, then inserts the caller-supplied `run_id` and `token_id` directly:

```python
if graph is None:
    raise ValueError("graph parameter is required for checkpoint creation")
if not graph.has_node(node_id):
    raise ValueError(f"node_id '{node_id}' does not exist in graph")

with self._db.engine.begin() as conn:
    ...
    conn.execute(
        checkpoints_table.insert().values(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            token_id=token_id,
            node_id=node_id,
            ...
        )
    )
```

Source: `/home/john/elspeth/src/elspeth/core/checkpoint/manager.py:85-129`

The table definition does not enforce token/run ownership for checkpoints. It uses a single-column FK on `token_id`, unlike other audit tables that use a composite `(token_id, run_id)` FK:

```python
Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
Column("token_id", String(64), ForeignKey("tokens.token_id"), nullable=False),
...
ForeignKeyConstraint(
    ["node_id", "run_id"],
    ["nodes.node_id", "nodes.run_id"],
),
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:475-500`

By contrast, the rest of the audit layer explicitly treats token/run mismatches as Tier 1 corruption and validates them before writing:

```python
def _validate_token_run_ownership(self, token_id: str, run_id: str) -> None:
    _row_id, actual_run_id = self._resolve_token_ownership(token_id)
    if actual_run_id != run_id:
        raise AuditIntegrityError(
            f"Cross-run contamination prevented: token {token_id!r} belongs to "
            f"run {actual_run_id!r}, but caller supplied run_id={run_id!r}."
        )
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:148-167`

I verified the bug with an in-memory repro using project code: after creating `tok-a` in `run-a` and `node-b` in `run-b`, `CheckpointManager.create_checkpoint(run_id='run-b', token_id='tok-a', node_id='node-b', ...)` succeeded and persisted `('run-b', 'tok-a', 'node-b')` in `checkpoints`.

What the code does:
- Accepts any existing `token_id`
- Stores it under any caller-supplied `run_id` as long as the `node_id`/`run_id` pair is valid

What it should do:
- Crash if the token does not belong to the supplied run, exactly like other Tier 1 audit writes

## Root Cause Hypothesis

`CheckpointManager` assumes its caller always passes a token from the same run and never verifies that invariant itself. Because `checkpoints_table` also lacks a composite FK on `(token_id, run_id)`, that unchecked assumption becomes a persisted cross-run contamination bug instead of an immediate crash.

## Suggested Fix

In `create_checkpoint()`, resolve token ownership inside the transaction and raise an audit-integrity exception if the token's actual `run_id` differs from the supplied `run_id`.

Example shape:

```python
token_row = conn.execute(
    select(tokens_table.c.run_id).where(tokens_table.c.token_id == token_id)
).fetchone()
if token_row is None:
    raise CheckpointCorruptionError(
        f"Token {token_id!r} does not exist; cannot create checkpoint"
    )
if token_row.run_id != run_id:
    raise CheckpointCorruptionError(
        f"Cross-run contamination prevented: token {token_id!r} belongs to "
        f"run {token_row.run_id!r}, not {run_id!r}"
    )
```

Also add an integration test that proves mismatched `run_id`/`token_id` is rejected. Longer-term, the schema should be hardened to use a composite FK on `(token_id, run_id)` for `checkpoints`, but the primary code fix belongs in `manager.py`.

## Impact

A checkpoint can claim that run B was at token A even though token A belongs to run A. That breaks checkpoint lineage, undermines the “one run = one audit record” guarantee, and can mislead recovery/debug tooling that trusts checkpoint metadata. In audit terms, this is cross-run evidence contamination in a Tier 1 record.
