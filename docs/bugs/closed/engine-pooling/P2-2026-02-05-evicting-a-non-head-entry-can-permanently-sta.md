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
