# Bug Report: Partial Service Principal Fields Are Ignored When Another Auth Method Is Set

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed and verified**
- Resolution summary:
  - Updated `AzureAuthConfig.validate_auth_method()` to reject partial Service Principal fields regardless of whether another auth method is configured.
  - This restores the documented mutually-exclusive auth contract and prevents silent fallback to another method when SP credentials are partially present.
  - Added regression coverage for `connection_string` + partial Service Principal fields.
- Verification:
  - `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_auth.py -q` (29 passed)
  - `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure -q` (216 passed)
  - `.venv/bin/ruff check src/elspeth/plugins/azure/auth.py tests/unit/plugins/transforms/azure/test_auth.py` (passed)

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- Partial Service Principal credentials are silently ignored if another auth method (e.g., `connection_string`) is fully configured, violating the "mutually exclusive" contract and masking misconfiguration.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/azure/auth.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `AzureAuthConfig` with a valid `connection_string` and only one Service Principal field set (e.g., `tenant_id="t"`).
2. Observe that no validation error is raised and the config resolves to `connection_string` auth, ignoring the partial Service Principal fields.

## Expected Behavior

- Any partial Service Principal configuration should raise a validation error regardless of other configured auth methods, preserving mutual exclusivity and preventing misconfiguration.

## Actual Behavior

- Partial Service Principal fields are ignored when another auth method is active, so validation succeeds and the selected method silently falls back to the other configured method.

## Evidence

- `src/elspeth/plugins/azure/auth.py#L28-L33`: Declares methods are mutually exclusive.
- `src/elspeth/plugins/azure/auth.py#L127-L129`: Partial Service Principal validation only runs when no other method is active (`and not has_conn_string and not has_sas_token and not has_managed_identity`), so partial SP fields are ignored whenever another method is configured.

## Impact

- User-facing impact: Misconfiguration is accepted without error; the system may authenticate using an unintended method.
- Data integrity / security impact: Risk of reading from or writing to the wrong storage account, undermining audit expectations and potentially exposing or contaminating data.
- Performance or cost impact: Potentially wasted runs or retries against the wrong account.

## Root Cause Hypothesis

- Partial Service Principal validation is gated on “no other method active,” so incomplete SP fields are not rejected when another method is configured.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/azure/auth.py` to treat any non-empty SP field as an attempted method and require all SP fields plus `account_url`, regardless of other configured methods; alternatively, enforce that non-selected method fields must be empty.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/azure/test_auth.py` asserting that `connection_string` + partial SP fields raises `ValidationError`.
- Risks or migration steps: Tightened validation could reject previously accepted but misconfigured settings; this is aligned with “mutually exclusive” contract.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/azure/auth.py#L28-L33`
- Observed divergence: The implementation allows partial SP fields alongside another auth method, contradicting mutual exclusivity.
- Reason (if known): Validation gate only runs when no other method is active.
- Alignment plan or decision needed: Enforce exclusivity by rejecting any non-empty fields from non-selected methods.

## Acceptance Criteria

- A config with `connection_string` plus any partial Service Principal fields raises `ValidationError`.
- Tests in `tests/plugins/azure/test_auth.py` cover this scenario and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_auth.py`
- New tests required: yes, add a case for `connection_string` + partial SP fields raising `ValidationError`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/azure/auth.py`
