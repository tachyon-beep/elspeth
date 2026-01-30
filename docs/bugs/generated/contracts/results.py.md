# Bug Report: RowResult exposes legacy token_id/row_id accessors (backwards compatibility shim)

## Summary

- RowResult defines token_id and row_id properties explicitly labeled “backwards compatibility,” which violates the No Legacy Code Policy and keeps deprecated access paths alive.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: Unknown

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/results.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct a `RowResult` with a `TokenInfo` instance.
2. Access `row_result.token_id` or `row_result.row_id`.
3. Observe that the compatibility accessors exist and are documented as such.

## Expected Behavior

- `RowResult` should expose only `token` (and other current fields). Legacy accessors should not exist; callers should use `row_result.token.token_id` and `row_result.token.row_id`.

## Actual Behavior

- `RowResult` provides explicit compatibility accessors `token_id` and `row_id`.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:199-207` defines `token_id` and `row_id` properties with docstrings “backwards compatibility.”
- `/home/john/elspeth-rapid/CLAUDE.md:797-841` explicitly forbids backwards compatibility code and requires removal of legacy shims.

## Impact

- User-facing impact: Encourages continued use of deprecated access patterns, slowing cleanup of legacy interfaces.
- Data integrity / security impact: Low direct impact, but undermines architectural policy enforcement.
- Performance or cost impact: Negligible.

## Root Cause Hypothesis

- Legacy accessors were retained after an API refactor and never removed.

## Proposed Fix

- Code changes (modules/files):
  - Remove `token_id` and `row_id` properties from `src/elspeth/contracts/results.py`.
  - Update any call sites to use `row_result.token.token_id` and `row_result.token.row_id`.
- Config or schema changes: None.
- Tests to add/update:
  - Update any tests or type checks that reference `row_result.token_id` / `row_result.row_id`.
- Risks or migration steps:
  - This is a breaking change for any external callers using the deprecated properties; update all internal usage in the same commit.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/CLAUDE.md:797-841` (No Legacy Code Policy)
- Observed divergence: Backwards compatibility properties remain in `RowResult`.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Remove compatibility accessors and update all usages.

## Acceptance Criteria

- `RowResult` no longer exposes `token_id` or `row_id` properties.
- All internal references use `row_result.token.*`.
- Test suite passes without legacy accessors.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: no (unless current tests hard-code legacy accessors)

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `/home/john/elspeth-rapid/CLAUDE.md` (No Legacy Code Policy)
---
# Bug Report: ArtifactDescriptor accepts duck-typed “sanitized” URLs and uses prohibited hasattr checks

## Summary

- `ArtifactDescriptor.for_database` and `.for_webhook` only check `hasattr(url, "sanitized_url")` / `"fingerprint"`, allowing any duck-typed object to pass and enabling unsanitized URLs (with secrets) to be recorded in the audit trail; also violates the prohibition on defensive patterns (`hasattr`) in system-owned code.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: Unknown

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/contracts/results.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a dummy object with `sanitized_url="postgresql://user:secret@host/db"` and `fingerprint=None`.
2. Call `ArtifactDescriptor.for_database(dummy, table="t", content_hash="...", payload_size=1, row_count=1)`.
3. Observe that it succeeds and embeds the raw URL with credentials into `path_or_uri`.

## Expected Behavior

- The factory should only accept a verified `SanitizedDatabaseUrl` / `SanitizedWebhookUrl` (or explicitly validate that `sanitized_url` contains no secrets) and should crash if the object is not guaranteed sanitized.

## Actual Behavior

- Any object with `sanitized_url` and `fingerprint` attributes is accepted, and the value is used verbatim in `path_or_uri`.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:254-271` and `/home/john/elspeth-rapid/src/elspeth/contracts/results.py:285-301` use `hasattr(...)` checks and then interpolate `url.sanitized_url` directly into `path_or_uri`.
- `/home/john/elspeth-rapid/CLAUDE.md:862-865` forbids defensive patterns like `hasattr` for system-owned data.
- `/home/john/elspeth-rapid/CLAUDE.md:678-684` requires secrets never be stored; only HMAC fingerprints should be recorded.

## Impact

- User-facing impact: Potentially leaks secrets into the audit trail if a non-sanitized object is passed.
- Data integrity / security impact: High—audit trail may contain credentials/tokens, violating auditability and secret-handling requirements.
- Performance or cost impact: Negligible.

## Root Cause Hypothesis

- Duck-typing via `hasattr` was used to avoid importing the Sanitized* types, but it weakens the contract and bypasses guaranteed sanitization.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/contracts/results.py`, replace `hasattr` checks with strict type enforcement for `SanitizedDatabaseUrl` / `SanitizedWebhookUrl`, or validate `sanitized_url` content before use (e.g., reject URLs containing credentials or sensitive query params).
- Config or schema changes: None.
- Tests to add/update:
  - Add unit tests to ensure `for_database` / `for_webhook` reject non-sanitized or non-`Sanitized*` inputs.
- Risks or migration steps:
  - Ensure all call sites construct URLs via `SanitizedDatabaseUrl.from_raw_url()` / `SanitizedWebhookUrl.from_raw_url()`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/CLAUDE.md:862-865` (Defensive programming prohibition), `/home/john/elspeth-rapid/CLAUDE.md:678-684` (Secret handling)
- Observed divergence: `hasattr`-based checks and duck-typing allow unsanitized URLs to pass.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce strict Sanitized* types or validate sanitized URL content before building `path_or_uri`.

## Acceptance Criteria

- `for_database` and `for_webhook` reject inputs that are not verified sanitized URL types (or fail validation).
- No code path allows raw credentials or tokens to appear in `path_or_uri`.
- Tests cover rejection of unsanitized/duck-typed inputs.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add targeted unit tests for `ArtifactDescriptor` factories

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `/home/john/elspeth-rapid/CLAUDE.md` (Secret handling, defensive programming prohibition)
