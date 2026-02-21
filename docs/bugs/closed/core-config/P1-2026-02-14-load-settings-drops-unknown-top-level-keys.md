## Summary

`load_settings()` drops unknown top-level keys before Pydantic validation, so typos like `trnasforms` are silently ignored.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/core/config.py`
- Function/Method: `load_settings`

## Evidence

- Source report: `docs/bugs/generated/core/config.py.md`
- `ElspethSettings` uses `extra="forbid"` but `load_settings()` pre-filters keys, bypassing reject-on-unknown behavior.

## Root Cause Hypothesis

Dynaconf internal-key filtering was implemented with a broad allowlist that also removes user mistakes.

## Suggested Fix

Reject unknown user keys explicitly, while still filtering known Dynaconf internals.

## Impact

Pipelines can run with missing config sections and no explicit configuration error.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/config.py.md`
- Beads: elspeth-rapid-jkmk
