# Bug Report: RowLineage source_data contract rejects non-dict quarantined rows

## Summary

- RowLineage.source_data is typed as a dict even though quarantined SourceRow payloads can be non-dict and are still persisted, so explain_row can surface primitives/lists that violate the contract and downstream assumptions.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: JSON array with primitive rows routed to quarantine sink

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run a JSON source with schema expecting object rows and input like `[1]` so the row is quarantined.
2. Configure `on_validation_failure` to a quarantine sink so a token/row is created for the quarantined item.
3. Call `LandscapeRecorder.explain_row(run_id, row_id)` for the quarantined row and inspect `RowLineage.source_data`.

## Expected Behavior

- RowLineage should accept and represent non-dict payloads for quarantined rows without violating its own contract.

## Actual Behavior

- RowLineage declares `source_data` as `dict[str, object] | None`, but quarantined rows can be primitives/lists, so explain_row can return values that contradict the contract and can crash consumers that assume dict.

## Evidence

- `src/elspeth/contracts/audit.py:359` (RowLineage.source_data typed as dict)
- `src/elspeth/contracts/results.py:316` (SourceRow row is Any; quarantined rows may be non-dict)
- `src/elspeth/engine/orchestrator.py:902` (quarantined rows are still persisted via create_initial_token with row_data=source_item.row)

## Impact

- User-facing impact: explain/TUI consumers can crash or misrender when they assume dict fields on a primitive payload.
- Data integrity / security impact: lineage payloads for quarantined rows can be misinterpreted or silently dropped.
- Performance or cost impact: minimal.

## Root Cause Hypothesis

- RowLineage contract assumes all row payloads are dicts, but SourceRow explicitly allows non-dict quarantined data and those rows are persisted.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/audit.py`: widen `RowLineage.source_data` to `Any | None` (or `object | None`) and update docstring to allow non-dict quarantined payloads.
- Config or schema changes: None.
- Tests to add/update:
  - Add a lineage test where a quarantined primitive row is persisted and `explain_row` returns the primitive without type assumptions.
- Risks or migration steps:
  - Low; typing change only, but update any consumers that assume dict.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- RowLineage accepts non-dict payloads and explain_row returns them without contract violations.
- A test covers quarantined primitive payloads in explain output.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/cli/test_explain_command.py`
- New tests required: yes, add a lineage/explain test for quarantined primitive payloads.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
---
# Bug Report: Checkpoint contract allows NULL topology hashes, masking audit DB corruption

## Summary

- Checkpoint in audit.py marks `upstream_topology_hash` and `checkpoint_node_config_hash` as optional despite the schema requiring NOT NULL, enabling NULLs to be treated as “legacy” rather than triggering a Tier‑1 crash.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: checkpoint row with NULL topology hashes (legacy or corrupted DB)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create or migrate a checkpoint row with NULL `upstream_topology_hash`/`checkpoint_node_config_hash`.
2. Load it via `CheckpointManager.get_latest_checkpoint` and run `CheckpointCompatibilityValidator.validate`.
3. Observe the validator treats it as “legacy” instead of raising an integrity error.

## Expected Behavior

- Tier‑1 audit data with NULL in required fields should trigger a hard failure, not a legacy/compatibility path.

## Actual Behavior

- The audit contract permits NULLs for required topology hashes and the validator treats missing hashes as legacy, masking audit DB corruption.

## Evidence

- `src/elspeth/contracts/audit.py:335` (Checkpoint fields are optional)
- `src/elspeth/core/landscape/schema.py:353` (checkpoint topology hash columns are NOT NULL)
- `src/elspeth/core/checkpoint/compatibility.py:50` (None routes to legacy handling)

## Impact

- User-facing impact: resume failures report “legacy checkpoint” instead of surfacing audit DB corruption.
- Data integrity / security impact: violates Tier‑1 “crash on anomaly” rule; corrupted audit data may be handled softly.
- Performance or cost impact: minimal.

## Root Cause Hypothesis

- The Checkpoint contract permits NULLs for required topology fields, enabling downstream code to treat missing data as legacy rather than as integrity violations.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/audit.py`: make `upstream_topology_hash` and `checkpoint_node_config_hash` non-optional; add `__post_init__` assertions if runtime enforcement is needed.
  - `src/elspeth/core/checkpoint/compatibility.py`: remove or hard-fail the legacy path for missing topology hashes to align with Tier‑1 rules.
- Config or schema changes: None.
- Tests to add/update:
  - Update checkpoint compatibility tests to assert NULL topology hashes raise/abort rather than returning a legacy ResumeCheck.
- Risks or migration steps:
  - Legacy checkpoints will become hard failures; communicate as breaking and require reruns.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:36`
- Observed divergence: Tier‑1 “NULL where unexpected = crash” is bypassed for checkpoints with missing topology hashes.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce non-null checkpoint topology fields and remove legacy handling to comply with Tier‑1 trust model.

## Acceptance Criteria

- Checkpoint objects cannot be constructed with NULL topology hashes.
- Compatibility validation fails fast on missing topology hashes.
- Tests cover NULL-hash checkpoints as integrity violations.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/core/checkpoint/test_compatibility_validator.py`
- New tests required: yes, add a case for NULL topology hashes.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
