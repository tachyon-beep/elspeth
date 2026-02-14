## Summary

`TriggerEvaluator.restore_from_checkpoint()` accepts impossible “empty batch with elapsed age” state, which causes the next real row to inherit stale timeout age and flush immediately.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/triggers.py
- Line(s): 279, 283, 286-294, 111-113, 156-159
- Function/Method: `TriggerEvaluator.restore_from_checkpoint` (impact manifests in `record_accept` and `should_trigger`)

## Evidence

`restore_from_checkpoint()` unconditionally restores a timer even when `batch_count` is zero:

```python
# src/elspeth/engine/triggers.py
self._batch_count = batch_count                          # line 279
self._first_accept_time = current_time - elapsed_age_seconds  # line 283
```

Then later, first real row does not reset timer because `_first_accept_time` is already set:

```python
# src/elspeth/engine/triggers.py
if self._first_accept_time is None:                      # line 111
    self._first_accept_time = current_time               # line 112
```

Timeout check uses stale restored time:

```python
# src/elspeth/engine/triggers.py
timeout_fire_time = self._first_accept_time + self._config.timeout_seconds  # line 157
if current_time >= timeout_fire_time:                    # line 158
```

Integration path currently permits this bad input shape:
- `/home/john/elspeth-rapid/src/elspeth/engine/executors/aggregation.py:731-734` validates only that `tokens` is a list, not non-empty.
- `/home/john/elspeth-rapid/src/elspeth/engine/executors/aggregation.py:829-834` passes `batch_count=len(reconstructed_tokens)` directly to `restore_from_checkpoint`.

Observed repro (with current code): restoring `batch_count=0, elapsed_age_seconds=50` then accepting one row yields immediate timeout trigger (`should_trigger=True`, `which_triggered='timeout'`), even though that row is brand new.

## Root Cause Hypothesis

`restore_from_checkpoint()` assumes callers always pass semantically valid active-batch state and does not enforce Tier-1 invariants. That allows logically inconsistent checkpoint restore state to survive and alter runtime behavior instead of crashing.

## Suggested Fix

In `/home/john/elspeth-rapid/src/elspeth/engine/triggers.py` inside `restore_from_checkpoint()`:

- Reject invalid restore states with `ValueError`:
1. `batch_count <= 0`
2. `elapsed_age_seconds < 0` or non-finite
3. negative offsets
4. offsets greater than `elapsed_age_seconds`

- Clear stale trigger metadata on restore:
1. set `self._last_triggered = None`

Minimal direction:

```python
if batch_count <= 0:
    raise ValueError("restore_from_checkpoint requires batch_count > 0")
if not math.isfinite(elapsed_age_seconds) or elapsed_age_seconds < 0:
    raise ValueError(...)
...
self._last_triggered = None
```

## Impact

- Premature timeout flushes after resume.
- Incorrect `trigger_type` attribution in batch audit records.
- Violates Tier-1 “crash on anomaly” policy for checkpoint/audit data.
- Can distort batching behavior and traceability for resumed runs.

## Triage

- Status: closed (false positive)
- Reason: `get_checkpoint_state()` explicitly excludes empty buffers with `if not tokens: continue`, so `batch_count=0` can never reach `restore_from_checkpoint()` through normal code paths. The claimed failure path is unreachable.
- Source report: `docs/bugs/generated/engine/triggers.py.md`
