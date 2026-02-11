# Bug Report: Legacy Sink Header Options Violate No-Legacy Policy

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- Sink config still exposes and prioritizes legacy `display_headers` and `restore_source_headers`, explicitly labeled as backwards compatibility, which violates the No Legacy Code Policy.

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

- Goal or task prompt: static analysis deep bug audit of `src/elspeth/plugins/config_base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a sink with `display_headers` or `restore_source_headers` in options (no `headers`).
2. Parse with `SinkPathConfig.from_dict(...)`.

## Expected Behavior

- Legacy header options are rejected; only `headers` is accepted.

## Actual Behavior

- Legacy options are accepted and used for header resolution.

## Evidence

- `src/elspeth/plugins/config_base.py:214-243` documents and defines legacy options as “backwards compatibility.”
- `src/elspeth/plugins/config_base.py:220-305` enforces legacy precedence and behavior (legacy fields actively used).
- `tests/plugins/test_sink_header_config.py:60-83` asserts legacy options are accepted and mapped.

## Impact

- User-facing impact: Confusing, dual configuration surface with “legacy” behavior still supported.
- Data integrity / security impact: Increases risk of configuration drift and hidden compatibility paths in an audit-focused system.
- Performance or cost impact: None known.

## Root Cause Hypothesis

- Legacy compatibility fields were kept in the base sink config despite the explicit “No Legacy Code Policy.”

## Proposed Fix

- Code changes (modules/files): Remove `display_headers` and `restore_source_headers` from `SinkPathConfig` and delete the associated precedence/validation logic in `src/elspeth/plugins/config_base.py`.
- Config or schema changes: Remove legacy options from supported config surface; enforce `headers` only.
- Tests to add/update: Update `tests/plugins/test_sink_header_config.py` and any sink tests to reflect removal of legacy options.
- Risks or migration steps: Breaking change for configs using legacy options; update examples and docs in the same change.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:841-885` (No Legacy Code Policy).
- Observed divergence: Legacy/backwards-compatibility options explicitly present and supported in sink config.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Remove legacy options and update all call sites/tests to use `headers`.

## Acceptance Criteria

- `SinkPathConfig` rejects `display_headers` and `restore_source_headers`.
- Only `headers` is supported and documented.
- Tests updated to reflect the single configuration path.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_sink_header_config.py -v`
- New tests required: yes, adjust existing tests to validate rejection of legacy options.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (No Legacy Code Policy)
