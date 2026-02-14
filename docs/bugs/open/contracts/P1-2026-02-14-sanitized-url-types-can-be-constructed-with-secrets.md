## Summary

`SanitizedDatabaseUrl` and `SanitizedWebhookUrl` can be directly instantiated with unsanitized values, letting secrets leak into artifact-safe fields.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/contracts/url.py`
- Function/Method: dataclass constructors for `SanitizedDatabaseUrl`, `SanitizedWebhookUrl`

## Evidence

- Source report: `docs/bugs/generated/contracts/url.py.md`
- Type identity is checked downstream, but constructor invariants are not enforced.

## Root Cause Hypothesis

Code assumes callers always use `from_raw_url(...)`, but direct constructors remain unrestricted.

## Suggested Fix

Add constructor invariant enforcement (or block direct construction) to ensure sanitized values only.

## Impact

Direct confidentiality and compliance risk from secret-bearing URIs in artifacts.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/url.py.md`
- Beads: elspeth-rapid-nmcc
