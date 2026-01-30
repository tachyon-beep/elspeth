# Bug Report: Multi-bucket acquisition is non-atomic across processes, leaking tokens

## Summary

- `RateLimiter.try_acquire()` can consume tokens from one bucket (per-second) and then fail on a later bucket (per-minute) under cross-process concurrency, leaving leaked tokens and returning False.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: SQLite persistence with multiple processes

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a rate limiter with both `requests_per_second` and `requests_per_minute`, and set `persistence_path` to a shared SQLite file.
2. Start two separate processes that instantiate a `RateLimiter` with the same `name` and `persistence_path`.
3. Hammer `try_acquire()` concurrently from both processes.
4. Observe cases where one process returns False but still reduces the per-second capacity (subsequent per-second checks fail more often than expected).

## Expected Behavior

- Acquisition across per-second and per-minute buckets should be atomic: either all buckets consume tokens or none do.

## Actual Behavior

- Tokens are consumed from earlier buckets even when a later bucket fails, causing leaked capacity and overly strict rate limiting.

## Evidence

- Sequential acquisition without rollback in `src/elspeth/core/rate_limit/limiter.py:251-270` (pre-check then per-bucket `try_acquire`, return False on failure).
- The lock used is per-instance only (`src/elspeth/core/rate_limit/limiter.py:148, 251`), so cross-process concurrency is not synchronized despite “cross-process rate limiting” in the class docstring (`src/elspeth/core/rate_limit/limiter.py:78-83`).

## Impact

- User-facing impact: spurious rate-limit failures and increased timeouts under multi-process load.
- Data integrity / security impact: none directly.
- Performance or cost impact: reduced throughput; more retries and longer runtimes.

## Root Cause Hypothesis

- Non-atomic multi-bucket acquisition: pre-check + sequential `Limiter.try_acquire()` calls allow another process to fill a later bucket between steps, and the code does not roll back earlier bucket inserts.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/rate_limit/limiter.py`: implement atomic acquisition across all buckets. Options include wrapping all bucket inserts in a single SQLite transaction when `persistence_path` is set, or tracking successful inserts and explicitly removing them if a later limiter fails.
  - Remove or minimize reliance on `_would_all_buckets_accept()` as a guard if atomic acquisition is implemented.
- Config or schema changes: None.
- Tests to add/update:
  - Add a multiprocessing test that uses a shared SQLite `persistence_path` and asserts no leaked capacity when contention occurs across per-second and per-minute buckets.
- Risks or migration steps:
  - Ensure rollback logic works for both in-memory and SQLite buckets; validate behavior under concurrent load.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/rate_limit/limiter.py:78-83` (claims cross-process rate limiting)
- Observed divergence: cross-process contention can leak tokens across buckets, undermining the intended combined rate limit.
- Reason (if known): sequential acquisition without rollback.
- Alignment plan or decision needed: make multi-bucket acquisition atomic for SQLite-backed persistence.

## Acceptance Criteria

- Under multi-process contention, `try_acquire()` never consumes tokens unless all buckets succeed.
- No observable token leakage or unexpected throttling beyond configured limits.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k rate_limit`
- New tests required: yes, multiprocessing contention test for atomicity.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Technology Stack: pyrate-limiter usage)
---
# Bug Report: Pre-check uses bucket.count(), causing false rate-limit rejections

## Summary

- `_would_all_buckets_accept()` uses `bucket.count()` (total retained items) instead of rate-window-aware checks, which can reject requests that the underlying bucket would accept, especially because pyrate-limiter’s leak interval is 10s by default.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: In-memory limiter with per-second rate

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `RateLimiter(name="test", requests_per_second=1)` with no persistence.
2. Call `try_acquire()` once.
3. Wait ~1.5s (greater than 1s rate window but less than pyrate-limiter’s 10s leak interval).
4. Call `try_acquire()` again and observe False.

## Expected Behavior

- After the 1-second window has elapsed, a second request should be accepted (subject to the per-second limit).

## Actual Behavior

- The second request is rejected because `_would_all_buckets_accept()` sees a stale count and short-circuits before the bucket’s own window-aware logic runs.

## Evidence

- `_would_all_buckets_accept()` uses `bucket.count()` and `rate.limit` directly in `src/elspeth/core/rate_limit/limiter.py:223-239`.
- `InMemoryBucket.count()` returns `len(self.items)` without window filtering in `/home/john/elspeth-rapid/.venv/lib/python3.13/site-packages/pyrate_limiter/buckets/in_memory_bucket.py:85-86`.
- Window-aware logic is only inside `InMemoryBucket.put()` using timestamps/binary search, so it would accept once the window has moved (`.../in_memory_bucket.py:28-49`).
- Buckets are only leaked every 10 seconds by default (`pyrate_limiter/abstracts/bucket.py:221-223`), so `count()` can include expired items for up to 10s.

## Impact

- User-facing impact: rate limiting is much stricter than configured (e.g., “1/sec” effectively becomes “1/10s” under typical timings).
- Data integrity / security impact: none directly.
- Performance or cost impact: significant throughput reduction and unnecessary delays.

## Root Cause Hypothesis

- `_would_all_buckets_accept()` uses stale, non-windowed counts that depend on the leaker thread’s 10s interval, so it rejects valid requests before the bucket’s own window-aware `put()` logic can accept them.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/rate_limit/limiter.py`: remove `_would_all_buckets_accept()` or replace it with a window-aware check (e.g., attempt acquisition with rollback on failure).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that sets `requests_per_second=1`, performs a request, waits >1s but <10s, and verifies a second request succeeds after the fix.
- Risks or migration steps:
  - Removing the pre-check requires safe rollback or transactional acquisition to keep multi-bucket consistency (tie in with bug above).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: rate limiter does not honor configured per-second window due to pre-check logic.
- Reason (if known): reliance on `bucket.count()` plus long leak interval.
- Alignment plan or decision needed: use bucket’s window-aware logic or implement transactional acquisition.

## Acceptance Criteria

- A second request after the configured window passes is accepted even if the leaker thread has not yet run.
- Pre-check no longer blocks valid requests.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k rate_limit`
- New tests required: yes, a timing-based test that spans the rate window but not the leaker interval.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Technology Stack: pyrate-limiter usage)
