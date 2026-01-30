# Bug Report: Discovery silently skips plugins missing required name attribute

## Summary

- Plugin discovery uses a defensive getattr and logs a warning instead of crashing when a plugin subclass lacks a `name` attribute, hiding system-owned plugin bugs and allowing silent omission from registration.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/discovery.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Add a plugin class in a scanned directory (e.g., `src/elspeth/plugins/sources/bad_source.py`) that subclasses `BaseSource` but omits the `name` attribute.
2. Run plugin discovery (e.g., `discover_plugins_in_directory()` or `discover_all_plugins()`).

## Expected Behavior

- Discovery should crash immediately (raise) because a system-owned plugin violates the required interface contract.

## Actual Behavior

- Discovery logs a warning and silently skips the plugin, allowing the pipeline to continue without that plugin being registered.

## Evidence

- `src/elspeth/plugins/discovery.py:131-143` uses `getattr(obj, "name", None)` and logs a warning before `continue`, instead of failing fast on a missing required attribute.
- `CLAUDE.md:251-256` states that missing expected attributes in plugins must crash, and explicitly calls out `getattr(..., default)` as the wrong response.
- `CLAUDE.md:862-864` prohibits defensive patterns like `getattr` that hide bugs in system-owned code.

## Impact

- User-facing impact: Plugins with missing `name` are silently absent from discovery, leading to confusing “unknown plugin” errors later or missing functionality without a hard failure at the root cause.
- Data integrity / security impact: Hides system code defects, violating auditability principles that require immediate failure on internal contract violations.
- Performance or cost impact: Minimal directly, but increased debugging time due to delayed error surfacing.

## Root Cause Hypothesis

- `_discover_in_file` treats the `name` attribute as optional via a defensive `getattr` and warning-based skip, contrary to the system-owned plugin contract.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/discovery.py`: Replace `getattr(obj, "name", None)` with direct `obj.name` access and raise `ValueError` if empty.
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test in `tests/plugins/test_discovery.py` that creates a plugin subclass without `name` and asserts discovery raises (not skips).
- Risks or migration steps:
  - None; this enforces the existing contract and surfaces bugs earlier.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:216-256` (Plugin Ownership; missing expected attribute must crash) and `CLAUDE.md:862-864` (prohibition on defensive `getattr` in system-owned code).
- Observed divergence: Discovery uses defensive `getattr` and skip behavior for missing `name` rather than crashing.
- Reason (if known): Likely intended to tolerate arbitrary files, but conflicts with system-owned plugin policy.
- Alignment plan or decision needed: Enforce hard failure on missing/empty `name` in discovery.

## Acceptance Criteria

- Discovery raises an exception when a subclass of `BaseSource`, `BaseTransform`, or `BaseSink` lacks a non-empty `name`.
- Added test fails on missing `name` and passes when fixed.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_discovery.py`
- New tests required: yes, add a test asserting discovery raises on missing `name`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Plugin Ownership; defensive programming prohibition)
