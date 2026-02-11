# Bug Report: Quarantined row telemetry hash can crash on malformed data

## Summary

- Quarantined rows compute `stable_hash(source_item.row)` for telemetry, which can raise on non‑canonical data (NaN/Infinity or non‑serializable), crashing the run instead of quarantining the row.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Source that yields `SourceRow.quarantined(row={"bad": float("nan")}, ...)`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/engine/orchestrator/core.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a source that yields `SourceRow.quarantined` with `row` containing `float("nan")` or another non‑canonical value.
2. Run a pipeline that reads from that source.
3. Observe the run fails during telemetry hashing before the row is routed to the quarantine sink.

## Expected Behavior

- Quarantined rows should never crash the pipeline; telemetry should tolerate non‑canonical external data (use `repr_hash` or skip hash).

## Actual Behavior

- `stable_hash` throws, aborting the run on malformed external data even though it was already marked quarantined.

## Evidence

- `src/elspeth/engine/orchestrator/core.py:1115` computes `stable_hash(source_item.row)` for quarantined rows.
- `src/elspeth/core/canonical.py:9` states NaN/Infinity are strictly rejected.
- `src/elspeth/core/canonical.py:12` instructs using `repr_hash()` for non‑canonical Tier‑3 data.

## Impact

- User-facing impact: Pipelines crash on bad input that should be quarantined.
- Data integrity / security impact: Audit trail loses expected quarantine records for malformed rows.
- Performance or cost impact: None beyond the crash.

## Root Cause Hypothesis

- Telemetry hashing reused strict canonical hashing on Tier‑3 data without fallback.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/engine/orchestrator/core.py:1115`, wrap `stable_hash` with a fallback to `repr_hash` on `ValueError` or `TypeError`, or use `repr_hash` directly for quarantined rows.
- Config or schema changes: None.
- Tests to add/update: Add a quarantine‑row test that includes NaN and asserts the run continues and routes to quarantine sink.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59` (Tier‑3 data should be quarantined, not crash) and `src/elspeth/core/canonical.py:12` (repr_hash for non‑canonical external data).
- Observed divergence: Quarantined rows still use strict canonical hashing.
- Reason (if known): Telemetry hash reuse without Tier‑3 fallback.
- Alignment plan or decision needed: Use `repr_hash` or guarded hashing for quarantined data.

## Acceptance Criteria

- A quarantined row containing NaN or other non‑canonical values does not crash the run.
- The row reaches the quarantine sink and is recorded in the audit trail.
- Telemetry hashing uses a safe fallback.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine -k quarantine`
- New tests required: yes, quarantined row with NaN or non‑serializable payload.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`

## Closure Update (2026-02-11)

- Status: Closed after re-verification against current code.
- Verification summary: quarantined-row telemetry hashing now guards canonical hashing and falls back to `repr_hash` for non-canonical data.
- Evidence:
  - `src/elspeth/engine/orchestrator/core.py:1354` computes `stable_hash(...)` in a `try`.
  - `src/elspeth/engine/orchestrator/core.py:1357` falls back to `repr_hash(...)` on `ValueError`/`TypeError`.
  - `tests/integration/pipeline/orchestrator/test_quarantine_routing.py` passes with non-canonical quarantine coverage.
