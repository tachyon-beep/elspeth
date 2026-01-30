# Bug Report: Checkpoint aggregation_state_json allows NaN/Infinity (non‑canonical JSON)

## Summary

- `CheckpointManager.create_checkpoint()` serializes `aggregation_state` with default `json.dumps`, which permits NaN/Infinity and stores invalid JSON in the audit DB.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Minimal in-memory SQLite run + token setup

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run, node, row, and token in the Landscape DB.
2. Call `CheckpointManager.create_checkpoint(..., aggregation_state={"metric": float("nan")}, graph=...)`.
3. Inspect `checkpoints.aggregation_state_json` or call `get_latest_checkpoint()` and `json.loads()`.

## Expected Behavior

- Checkpoint creation should reject NaN/Infinity (raise a clear error) so invalid JSON is never stored in audit data.

## Actual Behavior

- `json.dumps` serializes NaN/Infinity to non‑standard tokens (`NaN`, `Infinity`), storing invalid JSON in `aggregation_state_json`.

## Evidence

- `src/elspeth/core/checkpoint/manager.py:81-82` uses `json.dumps(aggregation_state)` with default settings (allows NaN/Infinity).
- CLAUDE.md “Canonical JSON” policy requires NaN/Infinity rejection for audit integrity (Canonical JSON section).

## Impact

- User-facing impact: Resume or exports can fail in strict JSON environments; cross‑language consumers may reject the checkpoint payload.
- Data integrity / security impact: Audit trail can contain non‑canonical JSON, violating auditability guarantees.
- Performance or cost impact: Minimal, but can trigger retries/duplicate work if checkpointing fails downstream.

## Root Cause Hypothesis

- The checkpoint serialization path does not enforce the canonical JSON NaN/Infinity rejection policy.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/checkpoint/manager.py`: use `json.dumps(..., allow_nan=False)` and raise a contextual error if serialization fails.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/core/checkpoint/test_manager.py` asserting `create_checkpoint` raises on NaN/Infinity in `aggregation_state`.
- Risks or migration steps:
  - Pipelines currently emitting NaN/Infinity in aggregation state will now fail checkpoint creation (intended per policy).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` → Canonical JSON (NaN/Infinity must be rejected).
- Observed divergence: Checkpoint serialization accepts NaN/Infinity.
- Reason (if known): Uses default `json.dumps` without `allow_nan=False`.
- Alignment plan or decision needed: Enforce canonical JSON rejection for checkpoint payloads.

## Acceptance Criteria

- Creating a checkpoint with NaN/Infinity in `aggregation_state` raises a clear error and does not persist a row.
- Aggregation state serialization still succeeds for valid JSON‑safe values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_manager.py -k nan`
- New tests required: yes, reject NaN/Infinity in aggregation_state serialization

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Canonical JSON policy)
---
# Bug Report: Legacy compatibility fallback violates no‑legacy policy and masks missing format_version

## Summary

- `_validate_checkpoint_compatibility()` accepts checkpoints with `format_version=None` when `created_at >= 2026-01-24`, which is backwards‑compatibility code prohibited by CLAUDE.md and allows Tier‑1 audit anomalies to pass.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Minimal in-memory SQLite run + token setup

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a checkpoint row with `format_version = NULL` and `created_at >= 2026-01-24`.
2. Call `CheckpointManager.get_latest_checkpoint(run_id)`.

## Expected Behavior

- Checkpoints missing `format_version` should be rejected outright (Tier‑1 audit data must be complete; no legacy compatibility shims).

## Actual Behavior

- The checkpoint is accepted because the code falls back to a date check and treats it as compatible.

## Evidence

- `src/elspeth/core/checkpoint/manager.py:234-243` implements the date-based legacy fallback for `format_version=None`.
- `tests/core/checkpoint/test_manager.py:336-367` explicitly asserts acceptance of a `format_version=None` checkpoint created on the cutoff date.

## Impact

- User-facing impact: Ambiguous compatibility behavior; allows resumption from checkpoints missing required metadata.
- Data integrity / security impact: Masks Tier‑1 anomalies (missing `format_version`) and violates the “no legacy code” rule.
- Performance or cost impact: None directly.

## Root Cause Hypothesis

- A legacy compatibility path was retained after format versioning was introduced.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/checkpoint/manager.py`: remove the date-based fallback; if `format_version is None`, raise `IncompatibleCheckpointError`.
- Config or schema changes: None.
- Tests to add/update:
  - Update `tests/core/checkpoint/test_manager.py` to expect rejection when `format_version` is NULL regardless of `created_at`.
- Risks or migration steps:
  - Existing legacy checkpoints will become non‑resumable (aligned with no‑legacy policy).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` → No Legacy Code Policy.
- Observed divergence: Explicit backwards‑compatibility shim based on date cutoff.
- Reason (if known): Support for pre-versioned checkpoints.
- Alignment plan or decision needed: Remove compatibility logic; treat all NULL format_version checkpoints as incompatible.

## Acceptance Criteria

- Any checkpoint missing `format_version` raises `IncompatibleCheckpointError`.
- Tests reflect the removal of legacy support.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_manager.py -k format_version`
- New tests required: yes, add/update tests to enforce NULL format_version rejection

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (No Legacy Code Policy)
