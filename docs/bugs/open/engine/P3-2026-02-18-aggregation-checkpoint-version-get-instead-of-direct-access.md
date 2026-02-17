## Summary

`restore_from_checkpoint()` in `aggregation.py` uses `state.get("_version")` to read the checkpoint version, returning `None` when the key is missing. This is inconsistent with the Tier 1 pattern (our checkpoint data, we always write `_version`), but may be a defensible design choice for checkpoint recovery.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/engine/executors/aggregation.py`
- Line: 736
- Function: `restore_from_checkpoint()`

## Evidence

**Write side** (line 686) always writes `_version`:
```python
state["_version"] = AGGREGATION_CHECKPOINT_VERSION
```

**Read side** (line 736) uses `.get()`:
```python
version = state.get("_version")
if version != checkpoint_version:
    slog.warning("checkpoint_version_rejected", ...)
```

When `_version` is missing, `version` is `None`, which fails the version check, causing the checkpoint to be discarded and the aggregation to start fresh.

## Design Decision Required

**Option A: Direct access (strict Tier 1)**
- `version = state["_version"]` — crashes with KeyError on missing key
- Consistent with Tier 1 enforcement
- Risk: crashes the pipeline when it could recover by discarding the checkpoint

**Option B: Keep `.get()` with explicit comment (pragmatic)**
- Keep current behavior but add comment explaining the deliberate choice
- Checkpoints are a recovery mechanism; crashing defeats their purpose
- Missing `_version` is handled the same as incompatible version (discard and start fresh)

## Root Cause

Tension between Tier 1 data integrity (crash on corruption) and checkpoint recovery pragmatism (graceful degradation when checkpoint is unusable).

## Impact

If a checkpoint is corrupted and missing `_version`, the current code silently discards it and starts fresh. With direct access, it would crash the pipeline. Both outcomes are defensible.
