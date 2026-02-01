# Bug Report: RateLimitRegistry not closed when resume fails

## Summary

- `_execute_resume_with_instances()` closes `RateLimitRegistry` only on success; if `orchestrator.resume()` raises, rate limiters are never closed.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/cli.py:1459-1485` - `rate_limit_registry.close()` after `orchestrator.resume()` with no try/finally

## Proposed Fix

- Wrap in try/finally to always close registry

## Acceptance Criteria

- RateLimitRegistry.close() called on both success and failure

## Verification (2026-02-01)

**Status: STILL VALID**

- `_execute_resume_with_instances()` still calls `rate_limit_registry.close()` only after `orchestrator.resume()` returns (no try/finally). (`src/elspeth/cli.py:1521-1534`)
