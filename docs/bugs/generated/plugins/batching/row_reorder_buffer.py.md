# Bug Report: RowReorderBuffer deadlocks when evicting a non-head sequence

## Summary

- Evicting a sequence that is not the current `_next_release_seq` can leave a gap that the release loop never skips, causing `wait_for_next_release()` to block forever once the gap becomes the head.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unit-test style in-memory buffer scenario

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/batching/row_reorder_buffer.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `RowReorderBuffer(max_pending=10)` and submit 4 rows to get sequences 0..3.
2. Complete seq 0 and seq 1; complete seq 3; leave seq 2 incomplete.
3. Call `evict()` on the ticket for seq 2 while `_next_release_seq` is still 0 or 1.
4. Call `wait_for_next_release()` repeatedly: seq 0 and seq 1 release, then the call blocks or times out even though seq 3 is ready.

## Expected Behavior

- After evicting seq 2, the release loop should skip the missing sequence when it becomes head and allow seq 3 to release.

## Actual Behavior

- The release loop stalls once `_next_release_seq` reaches the evicted sequence, because `wait_for_next_release()` never advances past missing entries.

## Evidence

- `wait_for_next_release()` only releases when `_next_release_seq` exists in `_pending`; if it does not, it simply waits. There is no gap-skipping logic. (`/home/john/elspeth-rapid/src/elspeth/plugins/batching/row_reorder_buffer.py:248-289`)
- `evict()` only advances `_next_release_seq` if it is *currently* missing at eviction time; it does not handle gaps that become head later. (`/home/john/elspeth-rapid/src/elspeth/plugins/batching/row_reorder_buffer.py:321-323`)
- Existing eviction tests only cover head or contiguous evictions; no test covers evicting a non-head sequence that becomes a future gap. (`/home/john/elspeth-rapid/tests/plugins/batching/test_row_reorder_buffer.py:240-319`)

## Impact

- User-facing impact: Pipeline can hang with no further output even when later rows have completed.
- Data integrity / security impact: Results may never be released downstream, leading to indefinite retries/timeouts.
- Performance or cost impact: Deadlock causes idle workers, repeated timeouts, and wasted compute.

## Root Cause Hypothesis

- `evict()` advances `_next_release_seq` only when the missing sequence is at the head at eviction time; when the evicted sequence becomes the head later, `wait_for_next_release()` has no logic to skip it and waits forever.

## Proposed Fix

- Code changes (modules/files):
  - Add gap-skipping logic in `wait_for_next_release()` to advance `_next_release_seq` while it is missing and `< _next_submit_seq`, or track evicted sequences and skip them when encountered.
  - Alternatively (or additionally) record evicted sequence numbers and have `wait_for_next_release()` treat them as terminal.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a unit test in `tests/plugins/batching/test_row_reorder_buffer.py` that evicts a non-head sequence (e.g., seq 2) and verifies that seq 3 can still be released.
- Risks or migration steps:
  - Ensure skipping only occurs for sequences `< _next_submit_seq` to avoid skipping never-submitted sequences.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- `wait_for_next_release()` does not block when the next sequence has been evicted; it advances to the next available pending entry.
- New test for non-head eviction passes and reproduces the prior hang on current code.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/batching/test_row_reorder_buffer.py -k evict`
- New tests required: yes, add a non-head eviction gap test as described.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
