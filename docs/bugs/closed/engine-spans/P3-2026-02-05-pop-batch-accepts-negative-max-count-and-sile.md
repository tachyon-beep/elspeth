# Bug Report: pop_batch Accepts Negative max_count and Silently No-Ops

## Summary

- `BoundedBuffer.pop_batch()` accepts negative `max_count` and returns an empty list without error, masking caller bugs and preventing buffer drainage.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (branch RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory TelemetryEvent

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/telemetry/buffer.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `BoundedBuffer` with any positive size.
2. Append a `TelemetryEvent`.
3. Call `pop_batch(max_count=-1)`.

## Expected Behavior

- A `ValueError` (or similar) is raised for negative `max_count`, surfacing a caller bug immediately.

## Actual Behavior

- The call returns an empty list, leaving the buffer unchanged and hiding the error.

## Evidence

- `pop_batch` has no validation for negative `max_count`: `src/elspeth/telemetry/buffer.py:89`
- The `range(min(max_count, len(self._buffer)))` no-ops for negative values, producing an empty batch: `src/elspeth/telemetry/buffer.py:101`

## Impact

- User-facing impact: Telemetry exporters can silently stop draining buffers if a batch size bug produces negative values, reducing operational visibility.
- Data integrity / security impact: Silent telemetry drop/backlog can obscure operational failures and delay detection of exporter issues.
- Performance or cost impact: Buffer fills and overflows, increasing drop counts and log noise while failing to export.

## Root Cause Hypothesis

- Missing bounds check for `max_count < 0` in `pop_batch`, allowing invalid inputs to silently no-op.

## Proposed Fix

- Code changes (modules/files): Add `if max_count < 0: raise ValueError(...)` at the start of `BoundedBuffer.pop_batch` in `src/elspeth/telemetry/buffer.py`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/unit/telemetry/test_buffer.py` asserting `pop_batch(-1)` raises `ValueError`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:972`
- Observed divergence: Internal programming errors should crash; negative `max_count` is silently ignored instead of failing fast.
- Reason (if known): Missing validation guard in `pop_batch`.
- Alignment plan or decision needed: Enforce non-negative `max_count` with explicit validation.

## Acceptance Criteria

- `pop_batch(max_count=-1)` raises `ValueError`.
- Existing buffer tests still pass; new negative-count test passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/telemetry/test_buffer.py`
- New tests required: yes, add a test for negative `max_count` raising `ValueError`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:972`
