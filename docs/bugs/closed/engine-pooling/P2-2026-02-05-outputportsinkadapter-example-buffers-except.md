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
