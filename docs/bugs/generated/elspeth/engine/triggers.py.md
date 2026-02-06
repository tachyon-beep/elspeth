# Bug Report: Condition Trigger Not Latched Once Fired

## Summary

- `TriggerEvaluator` records the first time a condition becomes true, but `should_trigger()` ignores that stored fire time if the condition is false at evaluation time, allowing a previously-fired condition to be lost.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Aggregation with condition-only trigger and delayed trigger check (e.g., `row['batch_age_seconds'] < 0.5`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/engine/triggers.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a `TriggerEvaluator` with `TriggerConfig(condition="row['batch_age_seconds'] < 0.5")` and a `MockClock`.
2. Call `record_accept()` at t=0 (condition becomes true and `_condition_fire_time` is set).
3. Advance the clock to t=1.0 before calling `should_trigger()` (simulating delayed trigger check).
4. Call `should_trigger()`.

## Expected Behavior

- `should_trigger()` should return `True` because the condition fired at t=0, and `which_triggered()` should report `"condition"`.

## Actual Behavior

- `should_trigger()` returns `False` because it only considers the condition if it is true at evaluation time, ignoring the previously recorded `_condition_fire_time`.

## Evidence

- `src/elspeth/engine/triggers.py:118-134` sets `_condition_fire_time` when the condition is first true in `record_accept()`.
- `src/elspeth/engine/triggers.py:165-189` only adds the condition candidate when the condition is true at the time of `should_trigger()`, and ignores `_condition_fire_time` if the condition is currently false.

## Impact

- User-facing impact: Condition-triggered batches can fail to flush if evaluation is delayed past a time-window condition; streaming pipelines may buffer indefinitely.
- Data integrity / security impact: Buffered rows can be retained without a terminal batch flush, risking incomplete outputs and audit trail gaps.
- Performance or cost impact: Unbounded buffer growth and memory pressure in long-running streams.

## Root Cause Hypothesis

- `should_trigger()` re-evaluates the condition and only considers it if it is true “now,” instead of treating `_condition_fire_time` as a latched fire event once set.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/engine/triggers.py` so `should_trigger()` always treats a non-`None` `_condition_fire_time` as a fired trigger, and only re-evaluates the condition when `_condition_fire_time` is `None`.
- Config or schema changes: None
- Tests to add/update: Add a unit test using `MockClock` that sets a time-window condition, delays `should_trigger()`, and asserts it still fires based on stored `_condition_fire_time`.
- Risks or migration steps: None

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md#L1204-L1212` (“Multiple triggers can be combined (first one to fire wins)”).
- Observed divergence: The condition trigger can “unfire” if it is not true at evaluation time, despite having fired earlier.
- Reason (if known): Condition evaluation is gated on current truth value rather than latched fire time.
- Alignment plan or decision needed: Align `should_trigger()` with “first to fire wins” by honoring the recorded fire time once set.

## Acceptance Criteria

- `should_trigger()` returns `True` whenever `_condition_fire_time` is set, even if the condition is false at the moment of evaluation.
- Added test reproduces the delayed-check scenario and passes.
- Existing trigger tests remain green.

## Tests

- Suggested tests to run: `pytest tests/engine/test_triggers.py -k condition`
- New tests required: yes, add delayed-check condition trigger test with `MockClock`

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`
