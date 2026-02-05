# Bug Report: Evicting A Non-Head Entry Can Permanently Stall FIFO Releases

## Summary

- Evicting a sequence that is not the current `next_release_seq` creates an unrecoverable gap, causing `wait_for_next_release()` to block forever once it reaches the missing sequence, even if later entries are complete.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `RC2.3-pipeline-row` @ `1c70074ef3b71e4fe85d4f926e52afeca50197ab`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic in-memory buffer

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/batching/row_reorder_buffer.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `RowReorderBuffer(max_pending=10)`.
2. Submit three rows `t0`, `t1`, `t2` (sequences 0,1,2).
3. Evict `t1` while `t0` is still pending (non-head eviction).
4. Complete `t0` and `t2`.
5. Call `wait_for_next_release()` twice; the first returns `t0`, the second times out even though `t2` is complete.

## Expected Behavior

- Evicting any sequence should ensure the release loop can skip it later, so `t2` should be released after `t0`.

## Actual Behavior

- The release loop stalls at the missing sequence `1` and never advances to `2`, causing timeouts and blocking downstream.

## Evidence

- `row_reorder_buffer.py:291-323` evicts only advances `self._next_release_seq` at eviction time, not when a future gap is reached.
- `row_reorder_buffer.py:248-289` `wait_for_next_release()` only checks `self._next_release_seq in self._pending` and never skips missing sequences.

## Impact

- User-facing impact: Rows can hang indefinitely, causing pipeline stalls and timeouts.
- Data integrity / security impact: Indirect; completed results may never be emitted.
- Performance or cost impact: Threads blocked waiting, wasted compute on completed work that never flows.

## Root Cause Hypothesis

- The eviction logic only skips gaps if the gap is at the current `next_release_seq` when eviction happens; it does not record evicted sequence numbers for future skipping.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/batching/row_reorder_buffer.py`, either track an `evicted_seqs` set and advance past evicted sequences in `wait_for_next_release()`, or add a skip loop in `wait_for_next_release()` to advance while `next_release_seq` is not in `_pending` and `< _next_submit_seq`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that evicts a non-head entry and confirms later sequences are released (new test in `tests/plugins/batching/test_row_reorder_buffer.py`).
- Risks or migration steps: Low risk; behavior becomes consistent with documented eviction semantics.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/batching/row_reorder_buffer.py` docstring states “The release loop will skip this sequence number.”
- Observed divergence: Skipping only occurs if the evicted sequence is at the head at eviction time; later gaps stall the release loop.
- Reason (if known): Eviction does not persist gap information for future release iterations.
- Alignment plan or decision needed: Implement gap tracking or skip logic in `wait_for_next_release()`.

## Acceptance Criteria

- Evicting any sequence (head or non-head) never causes a permanent stall; later completed entries are released in FIFO order with gaps skipped.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/batching/test_row_reorder_buffer.py -k evict`
- New tests required: yes, “evict non-head entry does not block later release”

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/batching/row_reorder_buffer.py` docstring on eviction semantics
---
# Bug Report: Timeout=0 Treated As Infinite Wait In Submit/Release

## Summary

- `submit(timeout=0.0)` and `wait_for_next_release(timeout=0.0)` are treated as infinite waits because `timeout` is checked with a truthiness test instead of `is not None`.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `RC2.3-pipeline-row` @ `1c70074ef3b71e4fe85d4f926e52afeca50197ab`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic in-memory buffer

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/batching/row_reorder_buffer.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `RowReorderBuffer(max_pending=1)`.
2. Submit one row to fill the buffer.
3. Call `submit("row-2", timeout=0.0)` expecting an immediate `TimeoutError`.
4. Observe the call blocks indefinitely.

## Expected Behavior

- A timeout of `0.0` should mean “do not wait” and immediately raise `TimeoutError`.

## Actual Behavior

- `timeout=0.0` is treated as `None` (infinite wait) and blocks.

## Evidence

- `row_reorder_buffer.py:157` uses `deadline = time.monotonic() + timeout if timeout else None`, so `timeout=0.0` is treated as false and becomes `None`.
- `row_reorder_buffer.py:240` uses the same pattern in `wait_for_next_release()`.

## Impact

- User-facing impact: Non-blocking or polling callers cannot use zero-timeout; may hang unexpectedly.
- Data integrity / security impact: None.
- Performance or cost impact: Threads can block indefinitely when a caller intended a non-blocking check.

## Root Cause Hypothesis

- Truthiness check (`if timeout`) incorrectly treats `0.0` as “no timeout.”

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/batching/row_reorder_buffer.py`, change timeout handling to `if timeout is not None`.
- Config or schema changes: None.
- Tests to add/update: Add tests that `timeout=0.0` raises immediately for `submit()` and `wait_for_next_release()`.
- Risks or migration steps: Low risk; aligns behavior with documented “None = forever.”

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Method docstrings state “None = forever,” implying numeric timeouts (including 0) should be honored.
- Observed divergence: `0.0` is treated as `None` (forever).
- Reason (if known): Truthiness check for timeout.
- Alignment plan or decision needed: Replace with explicit `is not None` checks.

## Acceptance Criteria

- `submit(timeout=0.0)` and `wait_for_next_release(timeout=0.0)` raise `TimeoutError` immediately when the operation would otherwise block.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/batching/test_row_reorder_buffer.py -k timeout`
- New tests required: yes, “timeout zero behaves as immediate timeout”

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/batching/row_reorder_buffer.py` docstrings for timeout semantics
