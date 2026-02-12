# Bug Report: CapacityError From Rate Limits Crashes AzurePromptShield Instead of Returning a Row Error

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- HTTP 429/503/529 responses raise `CapacityError` that is never handled in this transform, so BatchTransformMixin treats it as a plugin bug and the pipeline crashes instead of retrying or returning `TransformResult.error`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (branch `RC2.3-pipeline-row`)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `src/elspeth/plugins/transforms/azure/prompt_shield.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_prompt_shield` and run a pipeline on any row containing a string field.
2. Mock the API to return HTTP 429/503/529 (e.g., have `AuditedHTTPClient.post()` raise `httpx.HTTPStatusError` with status 429).
3. Observe the worker raising `CapacityError` and the pipeline failing with an uncaught exception.

## Expected Behavior

- Capacity errors should be retried via `PooledExecutor` or converted into a `TransformResult.error` (retryable) without crashing the run.

## Actual Behavior

- `CapacityError` propagates out of `_process_single_with_state` and is wrapped as `ExceptionResult`, causing the orchestrator to re-raise and abort the pipeline.

## Evidence

- `src/elspeth/plugins/transforms/azure/prompt_shield.py:311` raises `CapacityError` on capacity HTTP status.
- `src/elspeth/plugins/transforms/azure/prompt_shield.py:172` creates a `PooledExecutor`, but the transform never uses it to handle retries.
- `src/elspeth/plugins/batching/mixin.py:214` documents that uncaught exceptions are treated as plugin bugs and re-raised.

## Impact

- User-facing impact: pipelines abort on transient rate limits instead of quarantining/retrying the row.
- Data integrity / security impact: run ends in `FAILED` rather than cleanly recorded row error outcomes.
- Performance or cost impact: reruns required after transient capacity events; no backoff or retry applied.

## Root Cause Hypothesis

- The transform raises `CapacityError` but does not route work through `PooledExecutor` or handle the exception locally, so it is treated as a plugin bug.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/transforms/azure/prompt_shield.py`: either wire `_process_single_with_state` through `PooledExecutor` when `pool_config` is set, or catch `CapacityError` and return `TransformResult.error` in the sequential path (mirroring `azure_multi_query`’s sequential handling).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that simulates HTTP 429 and asserts a `TransformResult.error` (no exception).
  - If pooled mode is implemented, add a test validating retries/backoff behavior.
- Risks or migration steps:
  - Ensure existing configs using `pool_size` now behave predictably; document whether pooling is active or removed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:95`
- Observed divergence: external call failures should be converted to `TransformResult.error` at the boundary, but capacity errors currently crash the pipeline.
- Reason (if known): missing CapacityError handling and unused `PooledExecutor`.
- Alignment plan or decision needed: implement pooled retries or explicit `CapacityError` handling consistent with boundary rules.

## Acceptance Criteria

- A 429/503/529 response results in a retry (pooled mode) or a `TransformResult.error` (sequential mode) without pipeline crash.
- `pool_size` has defined behavior or is removed.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_azure_prompt_shield.py -k rate_limit`
- New tests required: yes, add rate-limit handling coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:95`

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `129c08d2`
- Fix summary: Handle PromptShield capacity errors as row-level retryable results
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.

