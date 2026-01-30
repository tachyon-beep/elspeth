# Bug Report: Checkpoint ID truncation risks collisions under high checkpoint volume

## Summary

- `create_checkpoint` truncates UUID4 to 12 hex chars (48 bits), which materially increases collision probability; duplicate `checkpoint_id` causes primary-key insert failure and can crash long, high-frequency checkpoint runs.

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
- Data set or fixture: Large run with frequent checkpoints (e.g., every_row)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Monkeypatch `uuid.uuid4()` to return two values with the same first 12 hex characters.
2. Call `CheckpointManager.create_checkpoint(...)` twice for the same or different runs.
3. Observe the second insert fails with a primary-key collision.

## Expected Behavior

- Every checkpoint creation yields a collision-resistant unique ID; no primary-key failures even under large checkpoint counts.

## Actual Behavior

- The ID space is only 48 bits, so collisions become plausible at high volume; duplicates trigger insert failure and can abort the run.

## Evidence

- Checkpoint IDs are truncated to 12 hex chars: `checkpoint_id = f"cp-{uuid.uuid4().hex[:12]}"` in `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py:78`.
- `checkpoint_id` is the primary key, so collisions are fatal: `checkpoints_table` defines `checkpoint_id` as primary key in `/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py:382-401`.

## Impact

- User-facing impact: Large runs with frequent checkpoints can fail unpredictably due to `IntegrityError`, interrupting pipelines.
- Data integrity / security impact: Checkpoint creation failure can prevent reliable crash recovery and may require manual intervention.
- Performance or cost impact: Retry/rollback costs increase; reruns are more likely.

## Root Cause Hypothesis

- Truncating UUID4 to 12 hex characters reduces entropy to 48 bits, making collisions statistically plausible at scale.

## Proposed Fix

- Code changes (modules/files):
  - Use full UUID hex or standard helper (e.g., `generate_id()` + prefix) instead of truncation in `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py`.
- Config or schema changes: None
- Tests to add/update:
  - Unit test asserting checkpoint IDs use full UUID length (or helper) and are not truncated.
  - Optional deterministic collision test by patching `uuid.uuid4()` to produce identical prefixes and verifying no truncation occurs.
- Risks or migration steps:
  - None; IDs are opaque strings and length stays within existing `String(64)` column.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Checkpoint IDs are generated with full UUID entropy (no truncation).
- Large runs with frequent checkpoints do not encounter `checkpoint_id` collision errors.

## Tests

- Suggested tests to run: Unknown
- New tests required: yes, add ID generation test for checkpoints.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
