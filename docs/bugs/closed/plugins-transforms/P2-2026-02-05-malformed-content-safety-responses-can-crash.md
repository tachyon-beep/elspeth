# Bug Report: Malformed Content Safety Responses Can Crash Pipeline Due to Missing Type Validation

**Status: FIXED**

## Status Update (2026-02-11)

- Classification: **Fixed**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the originally reported behavior is no longer present.


## Summary
- External response parsing assumes `category` is a string and `severity` is an int; malformed responses can raise `AttributeError` or `TypeError` that are not caught, crashing the pipeline instead of yielding a structured error.

## Severity
- Severity: major
- Priority: P2

## Reporter
- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment
- Commit/branch: RC2.3-pipeline-row (0282d1b441fe23c5aaee0de696917187e1ceeb9b)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)
- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/transforms/azure/content_safety.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce
1. Stub Azure Content Safety to return JSON where `categoriesAnalysis` items contain `{"category": null, "severity": "2"}`.
2. Run `azure_content_safety` on any row containing a string field.
3. Observe an uncaught exception during parsing or threshold checking.

## Expected Behavior
- The response should be validated at the external boundary; malformed types should result in a structured `TransformResult.error` (retryable if desired), not an uncaught exception.

## Actual Behavior
- `item["category"].lower()` can raise `AttributeError`, and `severity` values that are not ints can cause `TypeError` in threshold comparison; these crash the pipeline.

## Evidence
- `src/elspeth/plugins/transforms/azure/content_safety.py:463` iterates `data["categoriesAnalysis"]` without validating item types.
- `src/elspeth/plugins/transforms/azure/content_safety.py:464` calls `.lower()` on `item["category"]` without type checks.
- `src/elspeth/plugins/transforms/azure/content_safety.py:465` assigns `item["severity"]` without type validation.
- `src/elspeth/plugins/transforms/azure/content_safety.py:469` catches `KeyError`, `TypeError`, `ValueError` but not `AttributeError`.
- `src/elspeth/plugins/transforms/azure/content_safety.py:504` compares `severity` to `threshold` and will raise on non-numeric types.
- `CLAUDE.md:95` requires immediate validation at external call boundaries.

## Impact
- User-facing impact: Runs can fail due to provider anomalies or unexpected response shapes.
- Data integrity / security impact: External data crosses the boundary without validation; audit trail records call success but row fails due to parsing crash.
- Performance or cost impact: Reprocessing/restarts due to avoidable crashes.

## Root Cause Hypothesis
- Missing type/range validation for external response fields and incomplete exception coverage around response parsing.

## Proposed Fix
- Code changes (modules/files): Validate `data` is a dict, `categoriesAnalysis` is a list of dicts, `category` is a string in the expected set, and `severity` is an int in 0–6; on violation, raise `httpx.RequestError` (or return a structured `TransformResult.error`) instead of letting AttributeError/TypeError escape.
- Config or schema changes: None.
- Tests to add/update: Add tests for malformed response types (non-string `category`, non-int `severity`, non-list `categoriesAnalysis`) and assert the transform returns an error result instead of crashing.
- Risks or migration steps: Low risk; only tightens boundary validation.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:95`
- Observed divergence: External API responses are used without immediate structural/type validation, allowing malformed data to crash the transform.
- Reason (if known): Incomplete validation logic in `_analyze_content`.
- Alignment plan or decision needed: Implement boundary validation per CLAUDE.md and ensure malformed responses produce error results.

## Acceptance Criteria
- Malformed responses do not raise uncaught exceptions.
- Invalid response structures produce a deterministic `TransformResult.error` with a clear reason.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add malformed-response validation tests.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:95`
