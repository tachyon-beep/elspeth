# Bug Report: JSONFormatter Silently Coerces Audit Data and Allows NaN/Infinity

## Summary

- JSONFormatter uses `json.dumps(..., default=str)` without `serialize_datetime`, allowing NaN/Infinity and silently coercing unexpected types instead of failing fast.

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
- Data set or fixture: Synthetic audit record containing NaN/Infinity or datetime

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/core/landscape/formatters.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `JSONFormatter`.
2. Call `format` with `{"latency_ms": float("nan")}` or `{"timestamp": datetime(2026, 2, 4)}`.
3. Observe the returned JSON string.

## Expected Behavior

- NaN/Infinity should be rejected (raise `ValueError`) per audit integrity rules.
- Datetimes should be serialized to ISO-8601 using `serialize_datetime`.
- Unknown types should crash rather than being coerced.

## Actual Behavior

- NaN/Infinity are serialized as `NaN`/`Infinity` (invalid JSON).
- Datetimes are serialized via `str()` (non-ISO format).
- Unknown objects are silently coerced to strings.

## Evidence

- `src/elspeth/core/landscape/formatters.py:20-48` shows `serialize_datetime` explicitly rejects NaN/Infinity and converts datetimes to ISO strings.
- `src/elspeth/core/landscape/formatters.py:102-107` shows `JSONFormatter.format` calls `json.dumps(record, default=str)` without `serialize_datetime`, bypassing those checks.

## Impact

- User-facing impact: JSON exports can include invalid JSON tokens (`NaN`, `Infinity`) and inconsistent timestamp formats.
- Data integrity / security impact: Violates Tier 1 audit rules by coercing/normalizing data instead of crashing on anomalies.
- Performance or cost impact: Minimal; main risk is silent corruption rather than performance.

## Root Cause Hypothesis

- JSONFormatter was implemented with `default=str` for convenience and never wired to `serialize_datetime`, so audit integrity checks are skipped.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/landscape/formatters.py` update `JSONFormatter.format` to call `serialize_datetime(record)` and then `json.dumps(..., allow_nan=False)` without `default=str`.
- Config or schema changes: None.
- Tests to add/update: Add unit tests asserting NaN/Infinity raise `ValueError` and datetimes are ISO-8601 in JSONFormatter output.
- Risks or migration steps: JSON export will now raise if audit records contain non-serializable types or NaN/Infinity, surfacing latent data bugs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L25-L32` (Tier 1 must crash on anomalies, no coercion) and `CLAUDE.md#L631-L643` (NaN/Infinity strictly rejected).
- Observed divergence: JSONFormatter coerces unknown types and allows NaN/Infinity instead of crashing.
- Reason (if known): Convenience `default=str` implementation.
- Alignment plan or decision needed: Enforce `serialize_datetime` + `allow_nan=False` and remove `default=str`.

## Acceptance Criteria

- JSONFormatter raises `ValueError` on NaN/Infinity.
- JSONFormatter outputs ISO-8601 strings for datetimes.
- JSONFormatter no longer coerces unknown types.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py`
- New tests required: yes, add unit tests for JSONFormatter NaN/Infinity rejection and datetime ISO formatting.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 and canonical JSON rules)
---
# Bug Report: CSVFormatter Skips Audit Integrity Checks for Scalar Values

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
