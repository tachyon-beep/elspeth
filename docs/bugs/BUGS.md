# Bug Tracking

## Closed Bugs

### P0-2026-01-24-schema-validation-non-functional ✅
- **Status:** Resolved in RC-2
- **Fix:** Architectural refactor - plugin instantiation before graph construction
- **Resolution Date:** 2026-01-24

### P2-2026-01-24-aggregation-nodes-lack-schema-validation ✅
- **Status:** Resolved (symptom of P0 bug)
- **Fix:** Included in P0 architectural refactor
- **Resolution Date:** 2026-01-24

### P3-2026-01-24-coalesce-nodes-lack-schema-validation ✅
- **Status:** Resolved (symptom of P0 bug)
- **Fix:** Included in P0 architectural refactor
- **Resolution Date:** 2026-01-24

---

# Bug Report Template

## Summary

- What is broken, where it happens, and why it matters.

## Severity

- Severity: <blocker|critical|major|minor|trivial>
- Priority: <P0|P1|P2|P3>

## Reporter

- Name or handle:
- Date:
- Related run/issue ID:

## Environment

- Commit/branch:
- OS:
- Python version:
- Config profile / env vars:
- Data set or fixture:

## Agent Context (if relevant)

- Goal or task prompt:
- Model/version:
- Tooling and permissions (sandbox/approvals):
- Determinism details (seed, run ID):
- Notable tool calls or steps:

## Steps To Reproduce

1.
2.
3.

## Expected Behavior

-

## Actual Behavior

-

## Evidence

- Logs or stack traces:
- Artifacts (paths, IDs, screenshots):
- Minimal repro input (attach or link):

## Impact

- User-facing impact:
- Data integrity / security impact:
- Performance or cost impact:

## Root Cause Hypothesis

-

## Proposed Fix

- Code changes (modules/files):
- Config or schema changes:
- Tests to add/update:
- Risks or migration steps:

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...):
- Observed divergence:
- Reason (if known):
- Alignment plan or decision needed:

## Acceptance Criteria

-

## Tests

- Suggested tests to run:
- New tests required:

## Notes / Links

- Related issues/PRs:
- Related design docs:
