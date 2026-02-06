# Bug Report: LLM JSON validator accepts NaN/Infinity inside objects, violating canonical JSON rules

## Summary

- `validate_json_object_response` uses default `json.loads` and does not reject non-finite constants, so LLM responses like `{"score": NaN}` or `{"score": Infinity}` are accepted as valid objects even though ELSPETH requires rejecting NaN/Infinity at the JSON boundary.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: LLM response content containing `NaN`/`Infinity` constants

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/llm/validation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `validate_json_object_response('{"score": NaN}')`.
2. Observe that the function returns `ValidationSuccess` with `data={"score": float("nan")}` instead of a validation error.

## Expected Behavior

- LLM responses containing `NaN`, `Infinity`, or `-Infinity` should be rejected at the validation boundary with `ValidationError(reason="invalid_json")`, aligning with canonical JSON rules.

## Actual Behavior

- The response parses successfully, passes the dict type check, and returns `ValidationSuccess`, letting non-finite floats into Tier 2 pipeline data.

## Evidence

- `src/elspeth/plugins/llm/validation.py:56-74` parses with `json.loads(content)` and performs only a dict type check; no rejection of non-finite constants is implemented.
- `CLAUDE.md:629-645` states “NaN and Infinity are strictly rejected,” making acceptance at the LLM boundary a spec violation.

## Impact

- User-facing impact: LLM output containing non-finite values is treated as valid, which can later surface as opaque failures or inconsistent behavior.
- Data integrity / security impact: Non-canonical values can enter the audit trail path, conflicting with canonical JSON requirements and risking audit integrity.
- Performance or cost impact: Potential downstream crashes during canonicalization or hashing, requiring reruns.

## Root Cause Hypothesis

- The validator relies on Python’s default `json.loads`, which accepts `NaN`/`Infinity` constants, and does not implement explicit non-finite rejection.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/llm/validation.py`: pass `parse_constant` to `json.loads` to reject `NaN`/`Infinity` (raise), and catch `ValueError` alongside `JSONDecodeError` to return `ValidationError(reason="invalid_json")`.
  - Optionally add a post-parse walk to detect `float("nan")`/`float("inf")` if defensive-in-depth is desired.
- Config or schema changes: None.
- Tests to add/update:
  - Add property or unit tests in `tests/property/plugins/llm/test_response_validation_properties.py` to assert `{"x": NaN}`, `{"x": Infinity}`, and `{"x": -Infinity}` are rejected with `reason="invalid_json"`.
- Risks or migration steps:
  - Behavior change: Previously accepted non-finite values will now be quarantined as invalid JSON. This aligns with spec and canonicalization requirements.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:629-645`
- Observed divergence: LLM response validator accepts NaN/Infinity instead of rejecting them at the boundary.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Update validator to reject non-finite constants and add tests to enforce.

## Acceptance Criteria

- `validate_json_object_response` returns `ValidationError(reason="invalid_json")` for any JSON content containing `NaN`, `Infinity`, or `-Infinity`.
- Tests covering these inputs pass, and no existing tests regress.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/property/plugins/llm/test_response_validation_properties.py`
- New tests required: yes, add explicit NaN/Infinity rejection cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Canonical JSON section)
