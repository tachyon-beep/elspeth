# Bug Report: CSVFormatter Skips Audit Integrity Checks for Scalar Values

**Status: CLOSED (FIXED)**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - CSV scalar values still bypass `serialize_datetime`.
  - Repro still emits scalar `float('inf')` and raw `datetime` unchanged in `CSVFormatter.format(...)`.
- Current evidence:
  - `src/elspeth/core/landscape/formatters.py:216`
  - `src/elspeth/core/landscape/formatters.py:223`

## Summary

- CSVFormatter only applies `serialize_datetime` to list values; scalar values (including datetime and NaN/Infinity floats) are passed through unvalidated, violating audit integrity requirements during CSV export.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic audit record containing datetime and NaN/Infinity

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/core/landscape/formatters.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `CSVFormatter`.
2. Call `format` with `{"timestamp": datetime(2026, 2, 4), "latency_ms": float("inf")}`.
3. Inspect returned dict; then export via `_export_csv_multifile`.

## Expected Behavior

- Scalar values should be validated through `serialize_datetime` so NaN/Infinity are rejected and datetimes are normalized to ISO strings.

## Actual Behavior

- Scalar values are emitted unchanged, allowing NaN/Infinity and non-ISO datetimes into CSV exports.

## Evidence

- `src/elspeth/core/landscape/formatters.py:209-223` shows only list values are passed through `serialize_datetime`; scalar values bypass validation.
- `src/elspeth/engine/orchestrator/export.py:130-152` shows CSVFormatter is used for post-run audit exports, so this path is live.

## Impact

- User-facing impact: CSV exports may include invalid numeric tokens or inconsistent timestamps.
- Data integrity / security impact: Violates Tier 1 audit policy by not crashing on anomalous audit data.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- CSVFormatter’s `flatten` only applies `serialize_datetime` to lists, omitting scalar values.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/landscape/formatters.py` update `flatten` to apply `serialize_datetime` to scalar values before assignment.
- Config or schema changes: None.
- Tests to add/update: Add unit tests for CSVFormatter to ensure NaN/Infinity raise and datetimes serialize to ISO strings.
- Risks or migration steps: CSV exports will now fail fast on invalid audit data, potentially revealing latent issues.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L25-L32` (Tier 1 must crash on anomalies, no coercion) and `CLAUDE.md#L631-L643` (NaN/Infinity strictly rejected).
- Observed divergence: CSVFormatter allows invalid values through without raising.
- Reason (if known): Incomplete use of `serialize_datetime` in scalar path.
- Alignment plan or decision needed: Apply `serialize_datetime` to all values in CSVFormatter.

## Acceptance Criteria

- CSVFormatter raises `ValueError` on NaN/Infinity in scalar fields.
- CSVFormatter outputs ISO-8601 strings for datetime scalar fields.
- CSV export path uses the corrected formatter behavior.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py`
- New tests required: yes, add unit tests for CSVFormatter scalar validation and datetime ISO output.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 and canonical JSON rules)


## Resolution (2026-02-12)

- Status: CLOSED (FIXED)
- Fix summary: `CSVFormatter.flatten()` now runs scalar values through `serialize_datetime`, so scalar datetimes are normalized to ISO and scalar NaN/Infinity values raise `ValueError` per Tier 1 integrity rules.
- Code updated:
  - `src/elspeth/core/landscape/formatters.py`
- Tests added/updated:
  - `tests/unit/core/landscape/test_formatters.py`
- Verification:
  - `ruff check src/elspeth/core/landscape/formatters.py tests/unit/core/landscape/test_formatters.py`
  - `pytest tests/unit/core/landscape/test_formatters.py` (`40 passed`)
  - Manual repro check confirmed scalar datetime ISO serialization and scalar Infinity rejection.
- Ticket moved from `docs/bugs/open/core-landscape/` to `docs/bugs/closed/core-landscape/`.
