# Bug Report: PluginManager Silently Accepts Unknown Hook Implementations

## Summary

- `PluginManager.register()` does not validate hook implementations against known hookspecs, so a misspelled hook (e.g., `elspeth_get_tranforms`) registers without error and the plugin is silently ignored by `_refresh_caches()`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b4 (RC2.3-pipeline-row)
- OS: Unknown
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Define a plugin with a typo in the hook name (e.g., `elspeth_get_tranforms`) and decorate it with `@hookimpl`.
2. Call `PluginManager.register(plugin_instance)`.
3. Call `PluginManager.get_transforms()` or attempt to resolve the plugin by name.

## Expected Behavior

- Registration should fail immediately with a clear error about an unknown hook implementation, since plugins are system-owned and hook typos are code bugs.

## Actual Behavior

- Registration succeeds, no error is raised, and `_refresh_caches()` ignores the plugin because it only queries the known hook names.

## Evidence

- `src/elspeth/plugins/manager.py:75` registers the plugin but never validates pending/unknown hooks after `self._pm.register(plugin)`.
- `src/elspeth/plugins/manager.py:97` only calls `elspeth_get_source()` when rebuilding caches.
- `src/elspeth/plugins/manager.py:104` only calls `elspeth_get_transforms()` when rebuilding caches.
- `src/elspeth/plugins/manager.py:118` only calls `elspeth_get_sinks()` when rebuilding caches.
- `src/elspeth/plugins/hookspecs.py:45` defines the correct hook name `elspeth_get_source`.
- `src/elspeth/plugins/hookspecs.py:57` defines the correct hook name `elspeth_get_transforms`.
- `src/elspeth/plugins/hookspecs.py:77` defines the correct hook name `elspeth_get_sinks`.

## Impact

- User-facing impact: A plugin with a misspelled hook is silently ignored; the pipeline later fails with “unknown plugin” or runs without the intended plugin.
- Data integrity / security impact: Low direct impact, but silent registration failures violate the “plugin bugs must crash” principle.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `PluginManager.register()` does not call `pluggy.PluginManager.check_pending()` (or equivalent) to detect unknown hook implementations, allowing typos to pass silently.

## Proposed Fix

- Code changes (modules/files): Add a hook validation step (e.g., `self._pm.check_pending()`) in `src/elspeth/plugins/manager.py` after registration, or after `register_builtin_plugins()` completes.
- Config or schema changes: N/A
- Tests to add/update: Add a unit test that registers a plugin with a misspelled hook name and asserts registration raises a `PluginValidationError`.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:242` (plugin bugs should crash; no silent failures).
- Observed divergence: Hook typos are silently accepted and the plugin is ignored instead of crashing.
- Reason (if known): Missing hook validation step in `PluginManager.register()`.
- Alignment plan or decision needed: Enforce hook validation after registration to surface system code bugs immediately.

## Acceptance Criteria

- Registering a plugin with an unknown hook name raises a clear error at registration time.
- Registering a plugin with correct hooks continues to work and caches populate as expected.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_manager.py tests/plugins/test_hookimpl_registration.py`
- New tests required: yes, add a regression test for unknown hook name registration failure.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`, `docs/contracts/plugin-protocol.md`
