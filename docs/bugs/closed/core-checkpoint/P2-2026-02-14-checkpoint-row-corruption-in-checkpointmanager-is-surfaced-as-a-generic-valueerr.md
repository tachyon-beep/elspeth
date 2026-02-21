## Summary

Checkpoint row corruption in `CheckpointManager` is surfaced as a generic `ValueError` instead of `CheckpointCorruptionError`, causing loss of corruption context and inconsistent resume error handling.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 during triage — crash behavior is correct per Tier 1 trust model; this is a diagnostic quality improvement only)

## Location

- File: `src/elspeth/core/checkpoint/manager.py`
- Line(s): 25-32, 160-171, 192-205
- Function/Method: `CheckpointManager.get_latest_checkpoint`, `CheckpointManager.get_checkpoints`

## Evidence

`CheckpointCorruptionError` is defined as the corruption-specific exception, but never raised in this file:

- `src/elspeth/core/checkpoint/manager.py:25` defines `CheckpointCorruptionError`.
- `src/elspeth/core/checkpoint/manager.py:160` and `src/elspeth/core/checkpoint/manager.py:193` directly instantiate `Checkpoint(...)` from DB rows without exception translation.

`Checkpoint` validation raises bare `ValueError` on corrupt Tier-1 fields:

- `src/elspeth/contracts/audit.py:402`
- `src/elspeth/contracts/audit.py:408`
- `src/elspeth/contracts/audit.py:410`

`RecoveryManager.can_resume()` only catches `IncompatibleCheckpointError`, so this bare `ValueError` escapes unexpectedly:

- `src/elspeth/core/checkpoint/recovery.py:106`
- `src/elspeth/core/checkpoint/recovery.py:108`

Verified behavior with an in-memory repro: inserting a checkpoint row with `upstream_topology_hash=''` causes:
`ValueError upstream_topology_hash is required and cannot be empty`
instead of `CheckpointCorruptionError`.

## Root Cause Hypothesis

`CheckpointManager` lacks a deserialization/validation error translation layer when reconstructing `Checkpoint` from database rows. Corruption is detected by `Checkpoint.__post_init__`, but manager methods let the raw `ValueError` propagate rather than raising the domain-specific corruption exception they define.

## Suggested Fix

Wrap `Checkpoint(...)` reconstruction in `try/except ValueError` in both `get_latest_checkpoint()` and `get_checkpoints()`, then raise `CheckpointCorruptionError` with run/checkpoint context and chained exception.

Example shape:

```python
try:
    checkpoint = Checkpoint(...)
except ValueError as e:
    raise CheckpointCorruptionError(
        f"Checkpoint corruption detected for run '{run_id}', checkpoint '{result.checkpoint_id}': {e}"
    ) from e
```

Apply equivalent wrapping in list reconstruction path (`get_checkpoints`) per row.

## Impact

Corrupted checkpoint data currently produces low-context generic errors, which:

- Makes corruption triage harder (missing run/checkpoint attribution in exception type/message).
- Breaks exception contract consistency for resume workflows (corruption is not typed as corruption).
- Risks generic CLI/API error handling paths instead of explicit Tier-1 corruption handling semantics.

## Triage

- Status: open (downgraded P2 → P3)
- Source report: `docs/bugs/generated/core/checkpoint/manager.py.md`
- Finding index in source report: 1
- Beads: pending
- Triage note: Current crash-on-corruption behavior is correct per CLAUDE.md Tier 1 trust model. The improvement is better exception typing and diagnostic context, not a behavioral fix. Requires actual database corruption to trigger.
