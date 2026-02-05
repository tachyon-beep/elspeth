# Bug Report: CapacityError Crashes Azure Content Safety Because Pooled Executor Is Never Used

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
- The transform constructs a `PooledExecutor` but never routes work through it, so `CapacityError` is treated as a plugin exception rather than a retryable capacity event.

## Proposed Fix
- Code changes (modules/files): Use `self._executor.execute_batch()` (or a single-item wrapper) when `pool_size > 1`, or catch `CapacityError` in `_process_row` and return a retryable `TransformResult.error`; ensure pool stats (if any) are propagated via `context_after`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that stubs `http_client.post()` to return 429 and asserts no exception is raised, and that the result is retryable or retried until timeout.
- Risks or migration steps: Low risk; changes are local to `azure_content_safety` execution flow.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/pooling/executor.py:1`
- Observed divergence: `azure_content_safety` never calls `PooledExecutor` despite raising `CapacityError` for throttling.
- Reason (if known): Likely incomplete wiring during refactor.
- Alignment plan or decision needed: Route row processing through `PooledExecutor` when configured or remove pool config entirely if unsupported.

## Acceptance Criteria
- Capacity errors trigger retry/backoff (or return a retryable error) and do not crash the pipeline.
- `pool_size` and `max_capacity_retry_seconds` have observable effect on behavior.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add a capacity-error retry test for `azure_content_safety`.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: Unknown
