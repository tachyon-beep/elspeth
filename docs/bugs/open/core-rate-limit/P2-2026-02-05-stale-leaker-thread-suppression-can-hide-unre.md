# Bug Report: Stale leaker-thread suppression can hide unrelated AssertionErrors

## Summary

- RateLimiter’s exception suppression registry is keyed only by thread ident and is not cleaned up when the leaker thread exits after the 50ms join timeout, which can later suppress AssertionErrors from unrelated threads that reuse the same ident.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/rate_limit/limiter.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `RateLimiter`, then call `close()` quickly in a loop so the leaker thread is still alive when `close()` runs.
2. After `close()` returns (join timeout elapsed), spawn many short-lived threads that intentionally raise `AssertionError` to increase chances of thread ident reuse.
3. Observe that some AssertionErrors from unrelated threads are suppressed and logged as “Suppressed expected pyrate-limiter cleanup exception” instead of reaching the original excepthook (intermittent; depends on ident reuse timing).

## Expected Behavior

- Only the known pyrate-limiter leaker thread AssertionError during cleanup is suppressed; unrelated threads should always reach the original `threading.excepthook`.

## Actual Behavior

- If the leaker thread exits after the 50ms join timeout without raising, its ident remains in the suppression set, so a later thread that reuses the same ident can have its `AssertionError` silently suppressed.

## Evidence

- Suppression registry keyed only by thread ident (`src/elspeth/core/rate_limit/limiter.py:30`).
- Suppression decision checks only `thread_ident` and `exc_type` (`src/elspeth/core/rate_limit/limiter.py:58`).
- Leaker thread ident added to suppression set on close (`src/elspeth/core/rate_limit/limiter.py:235`).
- Cleanup only happens after a 50ms join timeout (`src/elspeth/core/rate_limit/limiter.py:248`).
- Suppression entry removed only in hook or immediately after join, with no path if join times out and thread exits later (`src/elspeth/core/rate_limit/limiter.py:252`).

## Impact

- User-facing impact: Intermittent loss of visible AssertionError in unrelated threads, making failures harder to detect and debug.
- Data integrity / security impact: Potential to hide internal failures that should crash, weakening error visibility.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- Suppression is keyed solely by thread ident and removal depends on a short join; if the leaker thread exits after the timeout (without raising), the ident stays in the global suppression set and can match unrelated threads when idents are reused.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/core/rate_limit/limiter.py`, track suppression by thread object (or weakref) instead of ident-only, and add a cleanup path when join times out (e.g., background join + removal or weakref finalizer). Also verify `args.thread` identity in `_custom_excepthook` before suppressing.
- Config or schema changes: None.
- Tests to add/update: Add unit tests validating that suppression only occurs for the exact leaker thread object and that suppression entries are cleaned even when join times out.
- Risks or migration steps: Minor behavior change in logging/suppression; ensure no regression in suppressing the known pyrate-limiter cleanup AssertionError.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918` (No Bug-Hiding Patterns / no silent exception handling).
- Observed divergence: Stale ident-based suppression can hide unrelated AssertionErrors, violating the “no silent exception handling” principle when it suppresses non-benign errors.
- Reason (if known): Cleanup is tied to a short join timeout and uses ident-only tracking.
- Alignment plan or decision needed: Track the actual thread object and guarantee cleanup after thread exit to avoid suppressing unrelated failures.

## Acceptance Criteria

- Suppression only triggers for the exact leaker thread object tied to `RateLimiter.close()`.
- No suppression entries remain after the leaker thread exits, even if it exits after the join timeout.
- Unrelated thread AssertionErrors always reach the original excepthook.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_rate_limit_limiter.py -k suppression`
- New tests required: yes, add coverage for suppression cleanup and thread identity matching.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
