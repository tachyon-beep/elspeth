# Bug Report: TransformCompleted telemetry requires output_hash even when no output exists

## Summary

- TransformCompleted in `contracts/events.py` requires `output_hash: str`, but failed transforms legitimately have `output_hash = None`, forcing the emitter to coerce to an empty string and producing misleading telemetry.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1f10763eed654bee9c12cd7f935428db1280e13c (branch: fix/P2-aggregation-metadata-hardcoded)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/events.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with a transform that returns `TransformResult.error(...)` (e.g., `FailingTransform`).
2. Run the pipeline with telemetry enabled and capture emitted `TransformCompleted` events.

## Expected Behavior

- For failed transforms, telemetry should include `output_hash=None` (or omit it), reflecting that no output hash exists.

## Actual Behavior

- `TransformCompleted.output_hash` is forced to an empty string (`""`), making it appear as a present hash value even when no output exists.

## Evidence

- `TransformCompleted` contract requires `output_hash: str`, disallowing `None` even though failures have no output. `src/elspeth/contracts/events.py:156-167`
- Transform executor sets `output_hash = None` when no output data exists. `src/elspeth/engine/executors.py:324-332`
- Emitter coerces missing hashes to empty strings. `src/elspeth/engine/processor.py:207-218`
- `TransformResult.output_hash` is explicitly optional. `src/elspeth/contracts/results.py:102-105`

## Impact

- User-facing impact: Telemetry consumers see an “output_hash” value even for failed transforms, which is misleading.
- Data integrity / security impact: Observability data is inconsistent with audit semantics; can mask “no output” conditions.
- Performance or cost impact: None directly; potential downstream confusion or incorrect alerting.

## Root Cause Hypothesis

- The telemetry contract in `events.py` requires `output_hash: str`, but transform failures legitimately produce `output_hash=None`. The emitter compensates by coercing to `""`, introducing schema drift and misleading telemetry.

## Proposed Fix

- Code changes (modules/files):
  - Update `TransformCompleted.output_hash` to `str | None` in `src/elspeth/contracts/events.py`.
  - Update `_emit_transform_completed` to pass through `None` (remove `or ""`) in `src/elspeth/engine/processor.py`.
- Config or schema changes: None.
- Tests to add/update:
  - Extend `tests/engine/test_processor_telemetry.py` to assert `output_hash is None` for failed transforms.
- Risks or migration steps:
  - Ensure exporters handle `None` (most already skip `None`); verify console JSON output remains acceptable.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- TransformCompleted events for failed transforms carry `output_hash=None` (or omit it) instead of empty string.
- Telemetry exporters continue to serialize events without errors.
- Updated telemetry tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_processor_telemetry.py -k "TransformCompleted"`
- New tests required: yes, assert `output_hash is None` for failed transforms.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
