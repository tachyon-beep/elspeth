# Bug Report: JSONFormatter Silently Coerces Unsupported Types and Allows NaN/Infinity in Audit Exports

## Summary

- JSONFormatter uses `json.dumps(..., default=str)` with `allow_nan=True` (default), so non-JSON types are silently coerced and NaN/Infinity are emitted instead of raising, violating audit integrity rules.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9 (fix/P2-aggregation-metadata-hardcoded)
- OS: Linux
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: Synthetic record with NaN/unsupported types

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/landscape/formatters.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a REPL, run:
   - `from elspeth.core.landscape.formatters import JSONFormatter`
2. Call:
   - `JSONFormatter().format({"value": float("nan")})` or `JSONFormatter().format({"value": object()})`

## Expected Behavior

- NaN/Infinity should raise (per canonical JSON/audit integrity rules), and unsupported types should raise TypeError to surface audit corruption.

## Actual Behavior

- NaN/Infinity are serialized as `NaN` and unsupported types are stringified, silently masking invalid audit data.

## Evidence

- `src/elspeth/core/landscape/formatters.py:102-107` shows `json.dumps(record, default=str)` without `allow_nan=False`.

## Impact

- User-facing impact: Exported audit JSON can contain invalid/non-canonical values and misleading stringified fields.
- Data integrity / security impact: Violates “no coercion” and NaN/Infinity rejection standards, undermining audit trail integrity.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- JSONFormatter uses `default=str` (broad coercion) and relies on default `allow_nan=True`, bypassing audit integrity checks.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/landscape/formatters.py`: replace `default=str` with explicit serialization (e.g., `serialize_datetime` or a strict default that only handles datetime/Enum) and set `allow_nan=False`.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests asserting JSONFormatter raises on NaN/Infinity and unsupported types.
  - Update existing JSONFormatter tests to expect strict failures where appropriate.
- Risks or migration steps:
  - Downstream callers relying on implicit coercion will now get explicit errors; update call sites if needed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` “Auditability Standard” and “Canonical JSON - NaN and Infinity are strictly rejected”.
- Observed divergence: Formatter serializes invalid values and coerces types instead of crashing.
- Reason (if known): Convenience default for datetime handling broadened to all types.
- Alignment plan or decision needed: Enforce strict serialization consistent with audit integrity rules.

## Acceptance Criteria

- JSONFormatter raises on NaN/Infinity and unsupported types.
- JSONFormatter still serializes datetime and enums deterministically (without broad coercion).
- Tests cover strict failure cases.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py -k JSONFormatter`
- New tests required: yes, strict NaN/Infinity and unsupported-type cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard; Canonical JSON)
---
# Bug Report: CSVFormatter Allows NaN/Infinity in List Serialization

## Summary

- CSVFormatter serializes list values with `json.dumps` defaults, allowing NaN/Infinity to pass through as `NaN`/`Infinity` tokens instead of raising.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9 (fix/P2-aggregation-metadata-hardcoded)
- OS: Linux
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: Synthetic record with NaN list values

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/landscape/formatters.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a REPL, run:
   - `from elspeth.core.landscape.formatters import CSVFormatter`
2. Call:
   - `CSVFormatter().flatten({"vals": [float("nan")]})`

## Expected Behavior

- NaN/Infinity should raise to prevent invalid, non-canonical values from appearing in audit exports.

## Actual Behavior

- List values are JSON-encoded with `NaN` tokens, silently masking invalid values.

## Evidence

- `src/elspeth/core/landscape/formatters.py:215-217` uses `json.dumps(value)` without `allow_nan=False` or pre-validation.

## Impact

- User-facing impact: CSV exports can include invalid JSON fragments inside list fields.
- Data integrity / security impact: Violates NaN/Infinity rejection requirements for audit outputs.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- CSVFormatter uses bare `json.dumps` for lists without enforcing canonical JSON constraints.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/landscape/formatters.py`: validate list contents via `serialize_datetime` (which rejects NaN/Infinity) and call `json.dumps(..., allow_nan=False)`.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests ensuring CSVFormatter raises on NaN/Infinity in list values.
- Risks or migration steps:
  - Export of previously tolerated invalid data will now fail, surfacing upstream audit corruption.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` “Canonical JSON - NaN and Infinity are strictly rejected”.
- Observed divergence: List serialization emits NaN/Infinity rather than crashing.
- Reason (if known): Default `json.dumps` behavior.
- Alignment plan or decision needed: Enforce strict JSON rules during list serialization.

## Acceptance Criteria

- CSVFormatter raises when list values contain NaN/Infinity.
- Valid list values serialize correctly to JSON strings.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py -k CSVFormatter`
- New tests required: yes, NaN/Infinity list cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Canonical JSON rules)
---
# Bug Report: LineageTextFormatter Fabricates 0.0ms Latency When Missing

## Summary

- LineageTextFormatter prints `0.0ms` when `call.latency_ms` is None, implying a measured latency that was never recorded.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9 (fix/P2-aggregation-metadata-hardcoded)
- OS: Linux
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: LineageResult with Call.latency_ms = None

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/landscape/formatters.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct a LineageResult with a Call where `latency_ms=None`.
2. Format via `LineageTextFormatter().format(result)`.

## Expected Behavior

- Output should indicate missing latency (e.g., `N/A`) or omit latency to avoid fabricating values.

## Actual Behavior

- Output shows `(0.0ms)` even when latency is not recorded.

## Evidence

- `src/elspeth/core/landscape/formatters.py:171-174` defaults `latency` to `0.0` when None.
- `src/elspeth/contracts/audit.py:271` defines `latency_ms` as `float | None` (None is valid).

## Impact

- User-facing impact: Operators/auditors are misled into thinking latency was zero.
- Data integrity / security impact: Violates “no inference” audit principles in CLI output.
- Performance or cost impact: Minimal.

## Root Cause Hypothesis

- Formatter replaces missing latency with a numeric default rather than preserving unknown state.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/landscape/formatters.py`: render missing latency as `N/A` or omit the latency suffix entirely.
- Config or schema changes: None.
- Tests to add/update:
  - Update LineageTextFormatter tests to cover `latency_ms=None` rendering.
- Risks or migration steps:
  - None; output becomes more accurate.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` “Auditability Standard” (“No inference - if it's not recorded, it didn't happen”).
- Observed divergence: Formatter fabricates a latency value.
- Reason (if known): Convenience fallback.
- Alignment plan or decision needed: Use explicit “unknown” representation.

## Acceptance Criteria

- `latency_ms=None` renders as “N/A” (or omitted) rather than `0.0ms`.
- Existing output for non-None latency remains unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_formatters.py -k LineageTextFormatter`
- New tests required: yes, `latency_ms=None` case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard)
