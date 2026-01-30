# Bug Report: Batching examples implement OutputPort with outdated emit signature (missing state_id and ExceptionResult handling)

## Summary

- The batching examples define OutputPort adapters with `emit(self, token, result)` instead of the required `emit(self, token, result, state_id)`, and they only accept `TransformResult`, not `ExceptionResult`, making the examples incompatible with the current OutputPort protocol and retry-safe batch routing.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/RC1-RC2-bridge @ 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/batching/examples.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Wire `BatchTransformMixin` to `OutputPortSinkAdapter` as shown in the examples.
2. Run a batched transform so `_release_loop()` calls `output.emit(token, result, state_id)`.

## Expected Behavior

- OutputPort adapters in the examples accept `(token, result, state_id)` and handle `ExceptionResult` to preserve retry safety and crash propagation semantics.

## Actual Behavior

- `OutputPortSinkAdapter.emit()` and the `TransformOutputAdapter` example accept only `(token, result)`. When used with `BatchTransformMixin`, this raises `TypeError` due to the missing `state_id` argument and does not account for `ExceptionResult`.

## Evidence

- `src/elspeth/plugins/batching/examples.py:25-46` defines `OutputPortSinkAdapter.emit(self, token, result)` without `state_id`.
- `src/elspeth/plugins/batching/examples.py:167-175` defines `TransformOutputAdapter.emit(self, token, result)` without `state_id`.
- `src/elspeth/plugins/batching/ports.py:27-52` specifies the OutputPort protocol `emit(self, token, result: TransformResult | ExceptionResult, state_id: str | None)`.

## Impact

- User-facing impact: Developers following the examples will hit a `TypeError` when batching emits results with `state_id`, preventing pipelines from running.
- Data integrity / security impact: Exception results (plugin bugs) are not handled or propagated as required, risking incorrect behavior or silent misrouting if developers adapt the examples.
- Performance or cost impact: N/A.

## Root Cause Hypothesis

- The examples were not updated after the OutputPort protocol added the `state_id` parameter and `ExceptionResult` handling for retry safety.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/batching/examples.py` to define `emit(self, token, result, state_id)` in both adapters.
  - Update example buffering to include `state_id` and accept `TransformResult | ExceptionResult`.
  - Show proper handling of `ExceptionResult` (e.g., raise to crash or propagate explicitly).
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a small typing/runtime check (e.g., `isinstance(adapter, OutputPort)` or a signature test) to keep examples aligned with the protocol.
- Risks or migration steps:
  - Minimal; update documentation/example code only.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/batching/ports.py:27-52` (OutputPort protocol with state_id and ExceptionResult)
- Observed divergence: Examples omit `state_id` and `ExceptionResult` handling in OutputPort adapters.
- Reason (if known): Examples not updated after protocol change.
- Alignment plan or decision needed: Update examples to match the current OutputPort protocol.

## Acceptance Criteria

- Example adapters in `src/elspeth/plugins/batching/examples.py` match the OutputPort signature and illustrate correct handling of `state_id` and `ExceptionResult`.
- Copy/pasting example adapters no longer produces a `TypeError` when used with `BatchTransformMixin`.

## Tests

- Suggested tests to run: Unknown
- New tests required: yes, simple adapter protocol conformance test or signature check.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/batching/ports.py`
