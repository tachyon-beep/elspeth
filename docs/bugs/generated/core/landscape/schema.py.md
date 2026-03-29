## Summary

`node_states` claims token/run ownership support, but its schema only foreign-keys `token_id` and `run_id` separately, so a node state can be recorded under run B while pointing at a token from run A.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/schema.py
- Line(s): 207-230
- Function/Method: `node_states_table`

## Evidence

`schema.py` says `run_id` was added for a composite relationship, but the actual table definition does not create one:

```python
Column("token_id", String(64), ForeignKey("tokens.token_id"), nullable=False),
Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),  # Added for composite FK
...
ForeignKeyConstraint(["node_id", "run_id"], ["nodes.node_id", "nodes.run_id"]),
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:211-229`

By contrast, other tables that really enforce token ownership use a composite FK:

```python
ForeignKeyConstraint(["token_id", "run_id"], ["tokens.token_id", "tokens.run_id"])
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:160-161`, `/home/john/elspeth/src/elspeth/core/landscape/schema.py:455-459`

The generated DB metadata confirms the mismatch:

- `token_outcomes`: `['token_id', 'run_id'] -> tokens ['token_id', 'run_id']`
- `node_states`: `['token_id'] -> tokens ['token_id']` and `['run_id'] -> runs ['run_id']`

Verified from an in-memory SQLite schema created from this module.

The write path trusts the caller-supplied `run_id` and inserts directly:

```python
node_states_table.insert().values(
    state_id=state.state_id,
    token_id=state.token_id,
    node_id=state.node_id,
    run_id=run_id,
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:182-193`

There is no preceding ownership validation analogous to `DataFlowRepository._validate_token_run_ownership()`.

The codebase explicitly treats cross-run contamination as an audit-integrity violation:

```python
f"Cross-run contamination prevented: token {token_id!r} belongs to "
f"run {actual_run_id!r}, but caller supplied run_id={run_id!r}."
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:148-167`

Unlike `token_outcomes` and `transform_errors`, there is no regression test asserting a composite FK for `node_states`; existing tests only cover those other tables.
Sources: `/home/john/elspeth/tests/unit/core/landscape/test_token_recording.py:1398-1457`, `/home/john/elspeth/tests/unit/core/landscape/test_error_recording.py:917-950`

## Root Cause Hypothesis

`run_id` was added to `node_states` primarily to support the composite FK to `nodes`, and the intended composite FK to `tokens` was never added. The comment was updated, but the actual constraint was not, leaving DB-level integrity weaker than the rest of the subsystem assumes.

## Suggested Fix

Change `node_states_table` to enforce token ownership the same way `token_outcomes` and `transform_errors` already do:

```python
Column("token_id", String(64), nullable=False),
Column("run_id", String(64), nullable=False),
ForeignKeyConstraint(["token_id", "run_id"], ["tokens.token_id", "tokens.run_id"]),
ForeignKeyConstraint(["node_id", "run_id"], ["nodes.node_id", "nodes.run_id"]),
```

Also add a regression test that direct insertion with `token_id` from run A and `run_id` from run B raises `IntegrityError`, mirroring the existing `token_outcomes` and `transform_errors` tests.

## Impact

A buggy caller can write a node-state record into the wrong run without the database rejecting it. That corrupts audit lineage, can misattribute calls joined through `state_id`, and violates the project’s stated rule that cross-run contamination is evidence tampering rather than recoverable bad data.
---
## Summary

`checkpoints` does not enforce that `token_id` belongs to `run_id`, so resume state can be recorded for one run while referencing a token owned by another run.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/landscape/schema.py
- Line(s): 475-500
- Function/Method: `checkpoints_table`

## Evidence

The checkpoint schema only has independent foreign keys to `runs` and `tokens`:

```python
Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
Column("token_id", String(64), ForeignKey("tokens.token_id"), nullable=False),
...
ForeignKeyConstraint(["node_id", "run_id"], ["nodes.node_id", "nodes.run_id"]),
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/schema.py:478-499`

The generated schema confirms there is no composite token/run FK:

- `checkpoints`: `['run_id'] -> runs ['run_id']`, `['token_id'] -> tokens ['token_id']`
- no `['token_id', 'run_id'] -> tokens ['token_id', 'run_id']`

Verified from an in-memory SQLite schema created from this module.

`CheckpointManager.create_checkpoint()` writes the caller-provided `run_id` and `token_id` directly, with no ownership validation:

```python
conn.execute(
    checkpoints_table.insert().values(
        checkpoint_id=checkpoint_id,
        run_id=run_id,
        token_id=token_id,
        node_id=node_id,
```

Source: `/home/john/elspeth/src/elspeth/core/checkpoint/manager.py:115-128`

Checkpoint recovery later trusts the persisted token as the resume point:

```python
return ResumePoint(
    checkpoint=checkpoint,
    token_id=checkpoint.token_id,
    node_id=checkpoint.node_id,
```

Source: `/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:179-185`

The test suite checks checkpoint columns and behavior, but there is no regression test asserting that a mismatched `(token_id, run_id)` insert is rejected at the DB layer.
Source: `/home/john/elspeth/tests/unit/core/landscape/test_schema.py:78-139`

## Root Cause Hypothesis

When `run_id` was added broadly for run isolation, `checkpoints` got the extra column and the composite FK to `nodes`, but not the corresponding composite FK to `tokens`. The schema therefore records the ownership data without enforcing it.

## Suggested Fix

Update `checkpoints_table` to use a composite FK for token ownership:

```python
Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
Column("token_id", String(64), nullable=False),
...
ForeignKeyConstraint(["token_id", "run_id"], ["tokens.token_id", "tokens.run_id"]),
ForeignKeyConstraint(["node_id", "run_id"], ["nodes.node_id", "nodes.run_id"]),
```

Add a regression test that direct insertion of a checkpoint with `token_id` from run A and `run_id` from run B raises `IntegrityError`.

## Impact

A corrupted or buggy write path can persist a checkpoint whose token belongs to a different run. Resume logic then trusts that token and may restore the wrong lineage into a run, breaking audit isolation and making recovery artifacts legally unreliable.
