# Bug Report: NodeRepository Accepts Malformed `schema_fields_json` Without Crashing

## Summary

- `NodeRepository.load()` parses `schema_fields_json` but never validates it is a `list[dict]`, allowing malformed JSON types (e.g., object or `null`) to be accepted without crashing.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (1c70074ef3b71e4fe85d4f926e52afeca50197ab)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/repositories.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a `nodes` row with `schema_fields_json='{\"field\":\"x\"}'` or `schema_fields_json='null'`.
2. Load it via `NodeRepository.load()`.
3. Observe it returns a `Node` with `schema_fields` as a dict or `None` without error.

## Expected Behavior

- The repository should raise a `ValueError` if `schema_fields_json` is not a JSON array of objects.

## Actual Behavior

- The repository accepts any JSON type and forwards it into `Node.schema_fields`.

## Evidence

- `Node.schema_fields` is defined as `list[dict[str, object]] | None`. See `src/elspeth/contracts/audit.py:86-89`.
- `NodeRepository.load()` uses `json.loads()` without type validation. See `src/elspeth/core/landscape/repositories.py:90-93`.

## Impact

- User-facing impact: Schema audit metadata may be malformed without detection.
- Data integrity / security impact: Violates Tier 1 strictness by allowing invalid audit data types.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Missing type checks after `json.loads()` for `schema_fields_json`.

## Proposed Fix

- Code changes (modules/files):
- After `json.loads()`, validate `schema_fields` is a list and each element is a dict; otherwise raise `ValueError` in `src/elspeth/core/landscape/repositories.py`.
- Config or schema changes: None.
- Tests to add/update:
- Add tests that invalid `schema_fields_json` types raise, and valid list-of-dict JSON loads.
- Risks or migration steps:
- None; this is stricter validation of Tier 1 data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/audit.py:86-89`
- Observed divergence: Repository does not enforce the declared `schema_fields` type.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce type validation in the repository.

## Acceptance Criteria

- Loading `schema_fields_json` with non-list JSON raises `ValueError`.
- Loading `schema_fields_json` with list elements that are not dicts raises `ValueError`.
- Valid list-of-dict JSON loads successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add repository validation tests for malformed `schema_fields_json`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/audit.py`
