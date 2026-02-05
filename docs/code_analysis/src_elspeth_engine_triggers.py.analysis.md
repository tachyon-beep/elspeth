# Analysis: src/elspeth/engine/triggers.py

**Lines:** 301
**Role:** Evaluates trigger conditions for aggregation batches. Determines when aggregation buffers should flush based on count thresholds, timeout durations, and custom expression-based conditions. Supports checkpoint/restore for resume correctness. Uses "first to fire wins" semantics when multiple triggers are configured (OR logic).
**Key dependencies:**
- Imports: `TriggerType` (contracts.enums), `TriggerConfig` (core.config), `DEFAULT_CLOCK`/`Clock` (engine.clock), `ExpressionParser` (engine.expression_parser)
- Imported by: `engine/executors.py` (AggregationExecutor creates TriggerEvaluator instances)
**Analysis depth:** FULL

## Summary

TriggerEvaluator is carefully implemented with good attention to "first to fire wins" ordering semantics and checkpoint/restore correctness. The most significant concern is a subtle timing issue where the condition expression is evaluated in both `record_accept()` and `should_trigger()`, but with potentially different `batch_age_seconds` values, leading to duplicate evaluation work and a minor inconsistency window. There is also a potential for `should_trigger()` to append `_condition_fire_time` to candidates when that value is `None` (already set from a race path), though this is prevented by the conditional structure. Overall the file is sound with one notable warning about condition evaluation duplication.

## Warnings

### [119-133, 165-189] Condition expression evaluated redundantly in both record_accept() and should_trigger()

**What:** The condition expression is evaluated in `record_accept()` (lines 119-133) to track when the condition first fires, and then re-evaluated in `should_trigger()` (lines 165-189) because "time-dependent conditions may have become true after time passed." This creates two evaluation paths with different `batch_age_seconds` values -- `record_accept()` uses `current_time - self._first_accept_time` at accept time, while `should_trigger()` uses a later `current_time`.

**Why it matters:** This dual evaluation means:
1. Extra computation per row (expressions parsed and evaluated twice per accept+trigger cycle).
2. A subtle ordering inconsistency: if the condition first becomes true in `should_trigger()` (time elapsed since last accept), `_condition_fire_time` is set to `current_time` of the `should_trigger()` call, not the actual moment the condition became true. The code acknowledges this: "we use current_time as a conservative estimate" (line 187). This means the "first to fire wins" ordering between condition and timeout is approximate for time-dependent conditions, not exact.

**Evidence:**
```python
# In record_accept() - evaluates at accept time
if self._condition_fire_time is None and self._condition_parser is not None:
    context = {
        "batch_count": self._batch_count,
        "batch_age_seconds": current_time - self._first_accept_time,
    }
    result = self._condition_parser.evaluate(context)
    ...

# In should_trigger() - re-evaluates at trigger check time
if self._condition_parser is not None and self._first_accept_time is not None:
    batch_age = current_time - self._first_accept_time
    context = {
        "batch_count": self._batch_count,
        "batch_age_seconds": batch_age,
    }
    result = self._condition_parser.evaluate(context)
```
The duplication is intentional (documented) but the "conservative estimate" for condition fire time means that in edge cases, the condition could appear to have fired after a timeout even though it actually became true earlier (between accepts).

### [156-159] Timeout fire time computed from first_accept_time assumes no clock drift

**What:** The timeout fire time is calculated as `self._first_accept_time + self._config.timeout_seconds` (line 157). This is compared against `current_time` from `self._clock.monotonic()`. The calculation is mathematically sound for monotonic clocks, but during checkpoint/restore, `_first_accept_time` is synthetically reconstructed as `current_time - elapsed_age_seconds` (line 279 in `restore_from_checkpoint`).

**Why it matters:** After restore, the synthetic `_first_accept_time` is based on the restore-time clock value. If the checkpoint captured `elapsed_age_seconds` inaccurately (e.g., due to process suspension between checkpoint write and actual pause), the timeout calculation post-restore could fire earlier or later than expected. This is inherent to the checkpoint design and documented, but worth noting as a known imprecision.

**Evidence:**
```python
# restore_from_checkpoint line 279
self._first_accept_time = current_time - elapsed_age_seconds

# should_trigger line 157
timeout_fire_time = self._first_accept_time + self._config.timeout_seconds
```
The restored `first_accept_time` is a synthetic value. If `elapsed_age_seconds` was 50.0 and the actual wall clock advanced 52.0 seconds between checkpoint and restore, the timeout fires 2 seconds earlier than it should relative to the original batch timing.

### [51-60] No validation that TriggerConfig has at least one trigger configured

**What:** The constructor accepts a `TriggerConfig` without verifying that at least one of `count`, `timeout_seconds`, or `condition` is set. If all are `None`, `should_trigger()` will always return `False`, and the aggregation will never flush until end-of-source.

**Why it matters:** This is probably intentional (end-of-source is the implicit flush trigger, documented in the module docstring), but if a misconfigured TriggerConfig with no triggers is provided, the aggregation silently buffers all rows until source exhaustion. For large sources, this could mean unbounded memory growth in the aggregation buffer. A warning or validation at construction could catch this configuration error early.

**Evidence:**
```python
# Constructor accepts all-None config without complaint
self._config = config  # Could have count=None, timeout_seconds=None, condition=None
```
The `TriggerConfig` Pydantic model allows all fields to be `None` (they all have `default=None`).

## Observations

### [125-131, 174-180] Defense-in-depth type checking on condition results is appropriate

**What:** Both `record_accept()` and `should_trigger()` check `isinstance(result, bool)` and raise `TypeError` if the condition expression returns a non-boolean. This is consistent with the config-level validation in `TriggerConfig.validate_condition_expression()` which uses `parser.is_boolean_expression()` for static checking.

**Why it matters:** Positive observation -- the runtime check catches cases where the static analysis in `is_boolean_expression()` might miss (e.g., a comparison expression that involves row data types producing non-boolean via Python's short-circuit behavior in `and`/`or`). The dual check (static at config time, dynamic at runtime) is appropriate defense-in-depth.

### [225-291] Checkpoint/restore API is well-designed

**What:** The checkpoint/restore API preserves trigger fire offsets relative to `first_accept_time`, not absolute timestamps. This correctly handles the fact that monotonic clock values are not meaningful across process restarts.

**Why it matters:** Positive observation -- storing offsets instead of absolute times means "first to fire wins" ordering is preserved across checkpoint/restore cycles. The implementation at lines 282-290 correctly reconstructs absolute fire times from the restored `first_accept_time` base.

### [292-301] Reset method is complete

**What:** The `reset()` method clears all mutable state including fire times and last triggered marker. This prevents stale state from leaking between batches.

**Why it matters:** Positive observation -- all five mutable fields are reset. No state leakage between batches.

### [87-97] get_age_seconds is a simple alias

**What:** `get_age_seconds()` is documented as existing "for clarity when checkpointing" but is just `return self.batch_age_seconds`. The property and method return the same value.

**Why it matters:** Minor API surface redundancy. Not harmful but adds a second way to get the same value.

## Verdict

**Status:** SOUND
**Recommended action:** The condition evaluation duplication between `record_accept()` and `should_trigger()` is the most notable concern but is intentional and documented. Consider whether the all-None trigger config case should produce a warning at construction time, since it leads to unbounded buffering. No critical fixes required.
**Confidence:** HIGH -- Complete analysis of all code paths including checkpoint/restore. Cross-referenced with TriggerConfig validation, ExpressionParser behavior, and AggregationExecutor usage in executors.py.
