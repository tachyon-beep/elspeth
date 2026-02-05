# Bug Report: Condition-Based Aggregation Triggers Ignored in Pre-Row Flush

## Summary

- `check_aggregation_timeouts()` only flushes when `TriggerType.TIMEOUT`, so time-based `TriggerType.CONDITION` triggers are ignored between rows and the next arriving row is incorrectly included in the old batch.

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
- Data set or fixture: Aggregation with `TriggerConfig(condition="batch_age_seconds >= 5")`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/engine/orchestrator/aggregation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure an aggregation with `TriggerConfig(condition="batch_age_seconds >= 5")` (no timeout) and send two rows quickly to start a batch.
2. Wait >5 seconds with no new rows, then send a third row.

## Expected Behavior

- The condition trigger should be treated like a timeout: the existing batch should flush before buffering the new row, and the new row should start a new batch.

## Actual Behavior

- The condition trigger is ignored in `check_aggregation_timeouts()`, so the flush happens only after the new row is buffered, causing the new row to be included in the old batch.

## Evidence

- `check_aggregation_timeouts()` explicitly skips any trigger that is not `TriggerType.TIMEOUT`, so `TriggerType.CONDITION` never triggers a pre-row flush. `src/elspeth/engine/orchestrator/aggregation.py:155-166`.
- Condition triggers can become true due to time passing (`batch_age_seconds`), even without row arrivals. `src/elspeth/engine/triggers.py:165-188`.
- Aggregation flush in the normal path is checked after buffering the row, so a missed pre-row flush includes the new row. `src/elspeth/engine/processor.py:824-841`.

## Impact

- User-facing impact: Aggregation batches include rows that should belong to the next batch, violating trigger semantics.
- Data integrity / security impact: Audit trail records incorrect batch membership for condition-triggered flushes.
- Performance or cost impact: Potentially larger batches than intended, skewing downstream processing and metrics.

## Root Cause Hypothesis

- `check_aggregation_timeouts()` only recognizes `TriggerType.TIMEOUT`, ignoring `TriggerType.CONDITION` even though condition triggers can be time-based and should be evaluated between rows.

## Proposed Fix

- Code changes (modules/files):
- `src/elspeth/engine/orchestrator/aggregation.py`: treat `TriggerType.CONDITION` the same as `TIMEOUT` for pre-row flushes, and pass the actual `trigger_type` to `handle_timeout_flush()` instead of hardcoding `TriggerType.TIMEOUT`.
- Config or schema changes: None.
- Tests to add/update:
- Add a test that advances time to satisfy a condition trigger between rows and verifies the next row is not included in the flushed batch.
- Risks or migration steps:
- Low risk; change only affects condition-triggered aggregation boundaries.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Condition triggers that become true between rows are not flushed before buffering new rows.
- Reason (if known): Likely treated as count-only, but condition triggers can be time-based.
- Alignment plan or decision needed: Align condition-trigger behavior with timeout-trigger pre-row flush semantics.

## Acceptance Criteria

- Condition-based triggers that become true between rows flush before the next row is buffered.
- Batch membership and trigger_type in audit records reflect condition-triggered flushes accurately.
- New test covers time-based condition trigger behavior and passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_aggregation_timeouts.py -v`
- New tests required: yes, time-based condition trigger flush test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/engine/triggers.py` (condition trigger semantics)
