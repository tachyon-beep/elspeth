# Bug Report: CapacityError Crashes Azure Content Safety Because Pooled Executor Is Never Used

**Status: FIXED**

## Status Update (2026-02-12)

- Classification: **Fixed**
- Verification summary:
  - Implemented and verified on 2026-02-12.
  - `RowProcessor` now classifies `CapacityError` as transient/retryable in both no-retry-manager handling and retry-manager callback paths.
  - Added unit coverage for row-scoped `CapacityError` handling and retryability classification.


## Summary
- Capacity errors (HTTP 429/503/529) raise `CapacityError`, but `_executor` is never invoked; BatchTransformMixin treats the exception as a plugin bug, causing the node to fail and ignoring pool retry configuration.

## Severity
- Severity: major
- Priority: P1

## Reporter
- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment
- Commit/branch: RC2.3-pipeline-row (0282d1b441fe23c5aaee0de696917187e1ceeb9b)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)
- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/transforms/azure/content_safety.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce
1. Configure `azure_content_safety` with `pool_size: 4` and run a pipeline.
2. Simulate Azure Content Safety returning HTTP 429 for a scanned field.
3. Observe the transform execution.

## Expected Behavior
- Capacity errors should be retried with AIMD backoff via `PooledExecutor` (or converted to a retryable `TransformResult.error`), and the pipeline should not crash due to `CapacityError`.

## Actual Behavior
- `CapacityError` bubbles out of the worker thread, is wrapped as an `ExceptionResult`, and the node is marked failed; pool retry settings are ignored.

## Evidence
- `src/elspeth/plugins/transforms/azure/content_safety.py:195` constructs a `PooledExecutor` when pool config is present.
- `src/elspeth/plugins/transforms/azure/content_safety.py:339` calls `_analyze_content` inside the row processor.
- `src/elspeth/plugins/transforms/azure/content_safety.py:343` checks for capacity status codes.
- `src/elspeth/plugins/transforms/azure/content_safety.py:345` raises `CapacityError` with no local handling.
- `src/elspeth/plugins/batching/mixin.py:229` wraps any exception from the processor as an `ExceptionResult` (pipeline crash path).

## Impact
- User-facing impact: Transient capacity limits abort the run instead of retrying; pipelines fail under normal throttling.
- Data integrity / security impact: Rows never reach terminal success states, producing incomplete outputs for the run.
- Performance or cost impact: Manual restarts and repeated failures increase operational overhead; configured backoff is unused.

## Root Cause Hypothesis
- `CapacityError` was not included in engine-level transient exception classification, so exceptions raised by batch transforms were treated as fatal instead of retryable.

## Proposed Fix
- Code changes (modules/files): include `CapacityError` in `RowProcessor._execute_transform_with_retry()` transient exception handling and in the retry-manager `is_retryable` callback.
- Config or schema changes: None.
- Tests to add/update: Added unit tests for row-scoped `CapacityError` handling and retryability classification.
- Risks or migration steps: Low risk; change is localized to engine retry classification.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/pooling/executor.py:1`
- Observed divergence: `azure_content_safety` never calls `PooledExecutor` despite raising `CapacityError` for throttling.
- Reason (if known): Likely incomplete wiring during refactor.
- Alignment plan or decision needed: Route row processing through `PooledExecutor` when configured or remove pool config entirely if unsupported.

## Acceptance Criteria
- Capacity errors are treated as retryable/transient by the engine and do not cause immediate pipeline crash in this path.
- Regression coverage exists for both no-retry and retry-manager classification behavior.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add a capacity-error retry test for `azure_content_safety`.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: Unknown
