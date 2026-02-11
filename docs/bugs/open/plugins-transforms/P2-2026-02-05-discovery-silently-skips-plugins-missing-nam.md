# Bug Report: Discovery Silently Skips Plugins Missing `name` Attribute

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- Plugin discovery uses a defensive `getattr` + warning to skip system-owned plugin classes without a `name`, masking protocol violations instead of failing fast.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ `1c70074ef3b71e4fe85d4f926e52afeca50197ab`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/discovery.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Add or modify a plugin class in `src/elspeth/plugins/transforms/` to subclass `BaseTransform` but omit the `name` attribute.
2. Call `PluginManager.register_builtin_plugins()` (or `discover_all_plugins()`).
3. Observe a warning and that the plugin is skipped, rather than a hard failure.

## Expected Behavior

- Discovery should raise a clear error when a system-owned plugin class violates the required `name` contract.

## Actual Behavior

- Discovery logs a warning and silently skips the plugin.

## Evidence

- `src/elspeth/plugins/discovery.py:131-143` uses `getattr(obj, "name", None)` and logs a warning, then skips the class.
- `src/elspeth/plugins/protocols.py:31-40` defines `name: str` as a required plugin protocol attribute.
- `docs/contracts/plugin-protocol.md:202-210` lists `name: str` under required attributes for plugins.
- `CLAUDE.md:918-920` explicitly prohibits defensive patterns like `getattr` that hide system-code bugs.

## Impact

- User-facing impact: Missing plugins are silently excluded from discovery; pipelines may fail later with “unknown plugin” errors that obscure the true cause.
- Data integrity / security impact: Hides system-code contract violations, weakening auditability and traceability of plugin availability.
- Performance or cost impact: None direct.

## Root Cause Hypothesis

- Discovery treats system-owned plugin metadata as optional by using `getattr` and warning-based skipping, contrary to the required protocol and “no defensive programming” policy.

## Proposed Fix

- Code changes (modules/files): Replace the `getattr` + warning path in `src/elspeth/plugins/discovery.py` with a hard failure (e.g., direct attribute access or an explicit `raise ValueError` when `name` is missing/empty).
- Config or schema changes: None.
- Tests to add/update: Add a discovery test that asserts a missing `name` attribute raises (e.g., new test in `tests/plugins/test_discovery.py`).
- Risks or migration steps: None; this is a strict enforcement of existing contract.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md:202-210` and `CLAUDE.md:918-920`
- Observed divergence: Discovery skips non-compliant plugin classes instead of failing fast on required attributes.
- Reason (if known): Likely intended to be permissive for “arbitrary Python files,” but conflicts with system-owned plugin guarantees.
- Alignment plan or decision needed: Enforce hard failure on missing `name` to match protocol and defensive-programming prohibition.

## Acceptance Criteria

- Discovery raises a clear exception when a plugin class lacks a `name`.
- A unit test asserts this failure mode.
- No warnings-only skip path remains for system-owned plugin contract violations.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_discovery.py -k "missing_name"`
- New tests required: yes, add a test for missing `name` enforcement.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`, `CLAUDE.md`
