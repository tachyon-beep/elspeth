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
---
# Bug Report: Malformed Content Safety Responses Can Crash Pipeline Due to Missing Type Validation

## Summary
- External response parsing assumes `category` is a string and `severity` is an int; malformed responses can raise `AttributeError` or `TypeError` that are not caught, crashing the pipeline instead of yielding a structured error.

## Severity
- Severity: major
- Priority: P2

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
1. Stub Azure Content Safety to return JSON where `categoriesAnalysis` items contain `{"category": null, "severity": "2"}`.
2. Run `azure_content_safety` on any row containing a string field.
3. Observe an uncaught exception during parsing or threshold checking.

## Expected Behavior
- The response should be validated at the external boundary; malformed types should result in a structured `TransformResult.error` (retryable if desired), not an uncaught exception.

## Actual Behavior
- `item["category"].lower()` can raise `AttributeError`, and `severity` values that are not ints can cause `TypeError` in threshold comparison; these crash the pipeline.

## Evidence
- `src/elspeth/plugins/transforms/azure/content_safety.py:463` iterates `data["categoriesAnalysis"]` without validating item types.
- `src/elspeth/plugins/transforms/azure/content_safety.py:464` calls `.lower()` on `item["category"]` without type checks.
- `src/elspeth/plugins/transforms/azure/content_safety.py:465` assigns `item["severity"]` without type validation.
- `src/elspeth/plugins/transforms/azure/content_safety.py:469` catches `KeyError`, `TypeError`, `ValueError` but not `AttributeError`.
- `src/elspeth/plugins/transforms/azure/content_safety.py:504` compares `severity` to `threshold` and will raise on non-numeric types.
- `CLAUDE.md:95` requires immediate validation at external call boundaries.

## Impact
- User-facing impact: Runs can fail due to provider anomalies or unexpected response shapes.
- Data integrity / security impact: External data crosses the boundary without validation; audit trail records call success but row fails due to parsing crash.
- Performance or cost impact: Reprocessing/restarts due to avoidable crashes.

## Root Cause Hypothesis
- Missing type/range validation for external response fields and incomplete exception coverage around response parsing.

## Proposed Fix
- Code changes (modules/files): Validate `data` is a dict, `categoriesAnalysis` is a list of dicts, `category` is a string in the expected set, and `severity` is an int in 0–6; on violation, raise `httpx.RequestError` (or return a structured `TransformResult.error`) instead of letting AttributeError/TypeError escape.
- Config or schema changes: None.
- Tests to add/update: Add tests for malformed response types (non-string `category`, non-int `severity`, non-list `categoriesAnalysis`) and assert the transform returns an error result instead of crashing.
- Risks or migration steps: Low risk; only tightens boundary validation.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:95`
- Observed divergence: External API responses are used without immediate structural/type validation, allowing malformed data to crash the transform.
- Reason (if known): Incomplete validation logic in `_analyze_content`.
- Alignment plan or decision needed: Implement boundary validation per CLAUDE.md and ensure malformed responses produce error results.

## Acceptance Criteria
- Malformed responses do not raise uncaught exceptions.
- Invalid response structures produce a deterministic `TransformResult.error` with a clear reason.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add malformed-response validation tests.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:95`
---
# Bug Report: Configured Fields Are Silently Skipped When Missing or Non-String (Content Bypass)

## Summary
- When a configured field is missing or not a string, the transform silently skips it and still returns success, allowing unmoderated content to pass without any audit signal.

## Severity
- Severity: major
- Priority: P2

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
1. Configure `fields: ["content"]` for `azure_content_safety`.
2. Provide a row where `content` is missing or not a string.
3. Observe the transform result.

## Expected Behavior
- Missing or wrong-typed configured fields should produce an error (or crash, per trust model) so the audit trail records the failure explicitly.

## Actual Behavior
- The field is skipped and the transform returns success with `"validated"` even though no moderation occurred.

## Evidence
- `src/elspeth/plugins/transforms/azure/content_safety.py:330` silently continues when the configured field is absent.
- `src/elspeth/plugins/transforms/azure/content_safety.py:335` silently continues when the field is not a string.
- `src/elspeth/plugins/transforms/azure/content_safety.py:377` returns success even if all configured fields were skipped.
- `CLAUDE.md:81` states transforms expect types and wrong types are upstream bugs.

## Impact
- User-facing impact: Content may bypass moderation without detection.
- Data integrity / security impact: Audit trail indicates validation success when no validation occurred for configured fields.
- Performance or cost impact: None direct, but increases compliance risk.

## Root Cause Hypothesis
- Defensive skipping of missing/non-string fields treats upstream schema violations as ignorable instead of surfacing them.

## Proposed Fix
- Code changes (modules/files): For explicit `fields` lists, require presence and string type; return `TransformResult.error` (or raise) when missing or wrong-typed fields are encountered. Keep permissive behavior only for `fields: all`.
- Config or schema changes: None.
- Tests to add/update: Add tests that set explicit fields and supply missing or non-string values, asserting an error result rather than success.
- Risks or migration steps: Moderate behavior change; users relying on silent skips will now see explicit errors.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:81`
- Observed divergence: Transform silently tolerates type/missing-field violations instead of treating them as upstream bugs.
- Reason (if known): Convenience logic to skip non-string values in mixed rows.
- Alignment plan or decision needed: Enforce explicit-field requirements or document a strict-vs-lax mode (without legacy shims).

## Acceptance Criteria
- Explicitly configured fields always result in either an API call or a recorded error.
- Missing or non-string configured fields no longer return success.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add explicit-field validation tests.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:81`
