## Summary

Time-based condition triggers can be misattributed as timeouts because `TriggerEvaluator` records the condition fire time at the moment it is first observed, not when the condition actually became true.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/triggers.py
- Line(s): 171-194
- Function/Method: TriggerEvaluator.should_trigger

## Evidence

`TriggerEvaluator.should_trigger()` correctly computes the exact fire time for timeout triggers:

```python
timeout_fire_time = self._first_accept_time + self._config.timeout_seconds
if current_time >= timeout_fire_time:
    candidates.append((timeout_fire_time, "timeout"))
```

But for a condition that becomes true only because time passed, it does this instead:

```python
result = self._condition_parser.evaluate(context)
if result:
    self._condition_fire_time = current_time
    candidates.append((self._condition_fire_time, "condition"))
```

Source: `/home/john/elspeth/src/elspeth/engine/triggers.py:156-194`

That means a condition like `row['batch_age_seconds'] >= 5` is treated as if it fired at the next poll time, not at 5 seconds after first accept. Example:

- first accept at `t=0`
- condition threshold crossed at `t=5`
- timeout threshold crossed at `t=10`
- next poll happens at `t=12`

The code records:
- timeout fire time = `10`
- condition fire time = `12`

So `"timeout"` wins, even though the condition actually became true first.

This wrong trigger type is not just internal state. The orchestrator explicitly uses the evaluator’s chosen trigger type for audit recording:

- `/home/john/elspeth/src/elspeth/engine/orchestrator/aggregation.py:191-223` checks flush status and passes `trigger_type` through for “correct audit records”.
- `/home/john/elspeth/src/elspeth/engine/processor.py:855-859` forwards that `trigger_type` into the flush executor.
- `/home/john/elspeth/src/elspeth/engine/executors/aggregation.py:321-326` persists it via `update_batch_status(..., trigger_type=trigger_type)`.

So the batch can be flushed because a condition became true first, but the audit trail records `TIMEOUT`.

Test coverage also misses this exact case. Existing tests cover:
- condition already latched before timeout: `/home/john/elspeth/tests/unit/engine/test_triggers.py:438-460`
- unlatched time-based condition with no competing timeout: `/home/john/elspeth/tests/unit/engine/test_triggers.py:462-485`

I did not find a test for “time-based condition becomes true before timeout, but both are first observed after timeout has also elapsed”.

## Root Cause Hypothesis

The implementation treats time-based conditions as edge-triggered only when polled, but the contract is “first one to fire wins.” For timeout, the code derives the true crossing time analytically. For conditions, it does not derive the crossing time and instead stores `current_time` as a placeholder. That placeholder breaks ordering when a condition threshold was crossed earlier than a timeout threshold but detected later.

## Suggested Fix

When the condition depends only on monotonic batch age and/or count, compute or preserve the actual threshold-crossing time instead of using `current_time`.

At minimum, do not claim exact “first to fire wins” semantics unless the evaluator can derive the real condition fire time. Practical fixes in this file include:

```python
if result:
    actual_fire_time = self._derive_condition_fire_time(...)
    self._condition_fire_time = actual_fire_time
```

If exact derivation is not generally possible for arbitrary expressions, the safer fix is to reject time-dependent condition expressions that cannot supply an exact fire time, or limit condition triggers to row-accept evaluation only and stop comparing them against analytically timed triggers as if their fire times were exact.

A regression test should cover:
- condition: `row['batch_age_seconds'] >= 5`
- timeout: `10`
- first accept at `t=0`
- first poll at `t=12`
- expected `which_triggered() == "condition"`

## Impact

Batch audit records can state that a flush was caused by `TIMEOUT` when the configured `CONDITION` actually fired first. That violates ELSPETH’s auditability standard because the persisted trigger reason is part of the explanatory record for why a batch executed when it did. It also makes post-incident analysis misleading for aggregation behavior that mixes timeout and time-based condition triggers.
