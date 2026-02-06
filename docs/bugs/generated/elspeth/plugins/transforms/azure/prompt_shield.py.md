# Bug Report: CapacityError From Rate Limits Crashes AzurePromptShield Instead of Returning a Row Error

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
---
# Bug Report: Malformed JSON Responses Can Crash AzurePromptShield

## Summary

- `_analyze_prompt()` does not catch JSON decoding errors; `response.json()` can raise `JSONDecodeError`/`ValueError`, which propagates as an uncaught exception and crashes the pipeline instead of producing a row error.

## Severity

- Severity: major
- Priority: P2

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

1. Configure `azure_prompt_shield` and run a pipeline on any row with a string field.
2. Mock the API to return HTTP 200 with invalid JSON (or invalid JSON with `Content-Type: application/json`).
3. Observe `response.json()` raising `JSONDecodeError`, which crashes the pipeline.

## Expected Behavior

- Invalid JSON from the external API should be handled at the boundary and returned as a `TransformResult.error` (non-retryable or retryable per policy), not crash the run.

## Actual Behavior

- JSON decode errors are not caught, so the exception propagates and is treated as a plugin bug.

## Evidence

- `src/elspeth/plugins/transforms/azure/prompt_shield.py:428` calls `response.json()` inside a try/except that only handles `KeyError` and `TypeError`.
- `src/elspeth/plugins/transforms/azure/prompt_shield.py:438` shows no `ValueError`/`JSONDecodeError` handling.
- `src/elspeth/plugins/transforms/azure/content_safety.py:469` shows the intended pattern includes `ValueError` handling for malformed JSON.

## Impact

- User-facing impact: pipeline aborts on malformed 200 responses instead of quarantining the row.
- Data integrity / security impact: audit trail records a call success but the run fails due to unhandled external data.
- Performance or cost impact: reruns required; potential failure amplification.

## Root Cause Hypothesis

- The JSON decode failure path is not caught in `_analyze_prompt()`; only missing keys/types are handled.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/transforms/azure/prompt_shield.py`: catch `ValueError`/`json.JSONDecodeError` alongside `KeyError` and `TypeError`, and re-raise as `httpx.RequestError` (or directly return `TransformResult.error`).
- Config or schema changes: None.
- Tests to add/update:
  - Unit test that supplies invalid JSON in the response and asserts `TransformResult.error` (no exception).
- Risks or migration steps:
  - None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:95`
- Observed divergence: external response validation is incomplete; malformed JSON is not handled at the boundary.
- Reason (if known): missing `ValueError`/`JSONDecodeError` in exception handling.
- Alignment plan or decision needed: handle JSON parse errors as boundary failures per external call rules.

## Acceptance Criteria

- Invalid JSON responses from the API result in a row error (not an exception).
- The behavior matches `azure_content_safety`’s malformed response handling.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_azure_prompt_shield.py -k invalid_json`
- New tests required: yes, add malformed JSON handling coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:95`
