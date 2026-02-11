# Bug Report: Timeout=0 Treated As Infinite Wait In Submit/Release

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed**
- Verification summary:
  - Timeout handling now uses explicit `timeout is not None` checks, so `timeout=0.0` is treated as immediate timeout.
  - Regression tests added for both `submit()` and `wait_for_next_release()`.
- Current evidence:
  - `src/elspeth/plugins/batching/row_reorder_buffer.py`
  - `tests/unit/plugins/batching/test_row_reorder_buffer.py`

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

## Verification Status

- [x] Bug confirmed via reproduction
- [x] Root cause verified
- [x] Fix implemented
- [x] Tests added
- [x] Fix verified

## Resolution (2026-02-12)

**Fixed by:** Codex (GPT-5)

**Changes:**
- `src/elspeth/plugins/batching/row_reorder_buffer.py`: Changed deadline calculations in `submit()` and `wait_for_next_release()` from truthiness checks to explicit `timeout is not None`.
- `tests/unit/plugins/batching/test_row_reorder_buffer.py`: Added:
  - `test_submit_timeout_zero_is_immediate`
  - `test_wait_for_next_release_timeout_zero_is_immediate`

**Verification:**
- `.venv/bin/python -m pytest -q tests/unit/plugins/batching/test_row_reorder_buffer.py`
- `.venv/bin/python -m pytest -q tests/property/plugins/batching/test_reorder_buffer_properties.py`
- `.venv/bin/python -m ruff check src/elspeth/plugins/batching/row_reorder_buffer.py tests/unit/plugins/batching/test_row_reorder_buffer.py`
- `.venv/bin/python -m mypy src/elspeth/plugins/batching/row_reorder_buffer.py`
