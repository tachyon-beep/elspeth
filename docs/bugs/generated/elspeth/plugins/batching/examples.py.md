# Bug Report: TransformOutputAdapter Example Omits `state_id` and Breaks OutputPort Contract

## Summary

- Example `TransformOutputAdapter.emit()` omits the required `state_id` parameter and never propagates it, so it will raise a `TypeError` when a batch transform emits and also breaks retry-safe routing.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (1c70074ef3b71e4fe85d4f926e52afeca50197ab)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (example-only)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/batching/examples.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement `TransformOutputAdapter` as shown in Example 4 and wire `transform_a` (batch-aware) to `transform_b`.
2. Run `transform_a.accept(...)` so the batch mixin emits to the adapter.
3. Observe a `TypeError` because the adapter’s `emit()` lacks the `state_id` parameter.

## Expected Behavior

- `TransformOutputAdapter.emit(token, result, state_id)` should accept `state_id` and propagate it into the downstream `PluginContext` for retry-safe routing.

## Actual Behavior

- The example defines `emit(self, token, result)` with no `state_id`, so it will raise a `TypeError` when called by `BatchTransformMixin`, and it drops retry-safe `state_id` tracking.

## Evidence

- `src/elspeth/plugins/batching/examples.py:173-181` shows `TransformOutputAdapter.emit(self, token, result)` without `state_id` and no `ctx.state_id` propagation.
- `src/elspeth/plugins/batching/ports.py:40-49` defines the OutputPort contract as `emit(self, token, result, state_id)`.
- `src/elspeth/plugins/batching/mixin.py:268-278` calls `self._batch_output.emit(token, result, state_id)`.

## Impact

- User-facing impact: Example code crashes when used to chain transforms.
- Data integrity / security impact: Retry-safe routing is broken; results can be misrouted or dropped if state tracking is required downstream.
- Performance or cost impact: None expected beyond the crash.

## Root Cause Hypothesis

- The Example 4 docstring was not updated after `state_id` was added to the OutputPort protocol.

## Proposed Fix

- Code changes (modules/files): Update Example 4 in `src/elspeth/plugins/batching/examples.py` so `TransformOutputAdapter.emit(self, token, result, state_id)` matches the protocol and sets `ctx.state_id = state_id` when building `PluginContext`.
- Config or schema changes: None.
- Tests to add/update: None (example-only change).
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/batching/ports.py:40-49`
- Observed divergence: Example `TransformOutputAdapter` does not implement the required `emit(..., state_id)` signature.
- Reason (if known): Example not updated after protocol change.
- Alignment plan or decision needed: Update example signature and propagation of `state_id`.

## Acceptance Criteria

- Example 4 `TransformOutputAdapter.emit()` includes `state_id` and passes it into `PluginContext`.
- Example aligns with OutputPort protocol signature.

## Tests

- Suggested tests to run: N/A (example-only change).
- New tests required: No.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/batching/ports.py`
---
# Bug Report: OutputPortSinkAdapter Example Buffers `ExceptionResult` as Normal Output

## Summary

- `OutputPortSinkAdapter` only types and buffers `TransformResult` and never handles `ExceptionResult`, so plugin bugs can be silently written to sinks instead of crashing as required.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (1c70074ef3b71e4fe85d4f926e52afeca50197ab)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (example-only)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/batching/examples.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use Example 3 to connect a batch-aware transform to `OutputPortSinkAdapter`.
2. Trigger a plugin bug so the worker thread raises; the batch mixin emits an `ExceptionResult`.
3. Observe that `OutputPortSinkAdapter` buffers the result and (if implemented) writes it to the sink without raising.

## Expected Behavior

- When an `ExceptionResult` is emitted, the adapter should crash the pipeline (or re-raise the underlying exception), per the plugin ownership rules.

## Actual Behavior

- The adapter accepts only `TransformResult` and never checks for `ExceptionResult`, so plugin bugs can be silently converted into sink writes.

## Evidence

- `src/elspeth/plugins/batching/examples.py:39-46` buffers `TransformResult` only and `emit()` accepts `TransformResult` only.
- `src/elspeth/plugins/batching/ports.py:40-49` specifies `emit()` must accept `TransformResult | ExceptionResult`.
- `src/elspeth/plugins/batching/mixin.py:288-300` emits `ExceptionResult` on output-port failures or plugin bugs.
- `CLAUDE.md:240-245` requires plugin exceptions to crash rather than be silently handled.

## Impact

- User-facing impact: Silent corruption of output if plugin bugs are treated as normal results.
- Data integrity / security impact: Violates audit integrity by hiding plugin failures.
- Performance or cost impact: Potentially wasted compute and bad downstream writes.

## Root Cause Hypothesis

- The example adapter predates `ExceptionResult` propagation and never got updated to enforce crash-on-bug behavior.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/batching/examples.py`, change buffer type to include `ExceptionResult`, update `emit()` to detect `ExceptionResult` and raise `result.exception` (or explicitly fail) before buffering.
- Config or schema changes: None.
- Tests to add/update: None (example-only change).
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:240-245` and `src/elspeth/plugins/batching/ports.py:40-49`
- Observed divergence: Example adapter accepts only `TransformResult` and never crashes on `ExceptionResult`.
- Reason (if known): Example not updated after exception propagation rules were codified.
- Alignment plan or decision needed: Update example to surface plugin bugs immediately.

## Acceptance Criteria

- Example adapter handles `ExceptionResult` by raising the underlying exception.
- Adapter typing and buffering include `ExceptionResult`.

## Tests

- Suggested tests to run: N/A (example-only change).
- New tests required: No.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Plugin Ownership section)
