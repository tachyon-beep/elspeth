# Bug Report: Configured Fields Are Silently Skipped When Missing or Non-String (Content Bypass)

## Summary
- When a configured field is missing or not a string, the transform silently skips it and still returns success, allowing unmoderated content to pass without any audit signal.

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
1. Configure `fields: ["content"]` for `azure_content_safety`.
2. Provide a row where `content` is missing or not a string.
3. Observe the transform result.

## Expected Behavior
- Missing or wrong-typed configured fields should produce an error (or crash, per trust model) so the audit trail records the failure explicitly.

## Actual Behavior
- The field is skipped and the transform returns success with `"validated"` even though no moderation occurred.

## Evidence
- `src/elspeth/plugins/transforms/azure/content_safety.py:330` silently continues when the configured field is absent.
- `src/elspeth/plugins/transforms/azure/content_safety.py:335` silently continues when the field is not a string.
- `src/elspeth/plugins/transforms/azure/content_safety.py:377` returns success even if all configured fields were skipped.
- `CLAUDE.md:81` states transforms expect types and wrong types are upstream bugs.

## Impact
- User-facing impact: Content may bypass moderation without detection.
- Data integrity / security impact: Audit trail indicates validation success when no validation occurred for configured fields.
- Performance or cost impact: None direct, but increases compliance risk.

## Root Cause Hypothesis
- Defensive skipping of missing/non-string fields treats upstream schema violations as ignorable instead of surfacing them.

## Proposed Fix
- Code changes (modules/files): For explicit `fields` lists, require presence and string type; return `TransformResult.error` (or raise) when missing or wrong-typed fields are encountered. Keep permissive behavior only for `fields: all`.
- Config or schema changes: None.
- Tests to add/update: Add tests that set explicit fields and supply missing or non-string values, asserting an error result rather than success.
- Risks or migration steps: Moderate behavior change; users relying on silent skips will now see explicit errors.

## Architectural Deviations
- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:81`
- Observed divergence: Transform silently tolerates type/missing-field violations instead of treating them as upstream bugs.
- Reason (if known): Convenience logic to skip non-string values in mixed rows.
- Alignment plan or decision needed: Enforce explicit-field requirements or document a strict-vs-lax mode (without legacy shims).

## Acceptance Criteria
- Explicitly configured fields always result in either an API call or a recorded error.
- Missing or non-string configured fields no longer return success.

## Tests
- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k content_safety`
- New tests required: yes, add explicit-field validation tests.

## Notes / Links
- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:81`
