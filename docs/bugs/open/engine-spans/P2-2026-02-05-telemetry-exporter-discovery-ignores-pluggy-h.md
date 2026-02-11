# Bug Report: Telemetry Exporter Discovery Ignores Pluggy Hooks

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Telemetry factory still resolves exporters from static `_EXPORTER_REGISTRY` only.
  - Telemetry hook specs and built-in hook implementation exist, but factory still does not call the pluggy discovery path.
- Current evidence:
  - `src/elspeth/telemetry/factory.py:37`
  - `src/elspeth/telemetry/factory.py:69`
  - `src/elspeth/telemetry/hookspecs.py:38`
  - `src/elspeth/telemetry/exporters/__init__.py:32`

## Summary

- `create_telemetry_manager()` only consults a hardcoded registry and never calls the telemetry pluggy hooks, so any exporter registered via `elspeth_get_exporters` is invisible and fails with `TelemetryExporterError`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b4
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/telemetry/factory.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a custom exporter plugin using `@hookimpl` with `elspeth_get_exporters()` returning a new exporter class.
2. Register the plugin in a pluggy `PluginManager` as the hookspecs describe.
3. Configure telemetry with `exporters: - name: <custom_exporter_name>` and call `create_telemetry_manager()`.

## Expected Behavior

- The custom exporter class is discovered via the telemetry hook and instantiated when its name appears in config.

## Actual Behavior

- `create_telemetry_manager()` only checks the static `_EXPORTER_REGISTRY`, so the custom exporter name is “unknown” and raises `TelemetryExporterError`.

## Evidence

- Hardcoded registry only: `src/elspeth/telemetry/factory.py:36-75`
- Hook spec promises discovery via pluggy: `src/elspeth/telemetry/hookspecs.py:4-43`
- Built-in exporter plugin registration via hook exists but is never used: `src/elspeth/telemetry/exporters/__init__.py:4-34`

## Impact

- User-facing impact: Custom telemetry exporters cannot be used; configuration for them always fails.
- Data integrity / security impact: None direct, but telemetry integrations beyond built-ins are blocked.
- Performance or cost impact: None direct.

## Root Cause Hypothesis

- The factory bypasses the pluggy hooks entirely and uses a static registry, so exporter discovery never considers registered plugins.

## Proposed Fix

- Code changes (modules/files): Replace `_EXPORTER_REGISTRY` usage with a pluggy discovery step in `src/elspeth/telemetry/factory.py` that registers `BuiltinExportersPlugin` and collects `elspeth_get_exporters()` results into a registry with duplicate detection.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that registers a custom exporter via hook and asserts `create_telemetry_manager()` resolves it; add a test for duplicate exporter names across hooks.
- Risks or migration steps: Ensure built-in exporters are still discoverable; remove or deprecate the static registry to avoid drift.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/telemetry/hookspecs.py:4-43`, `src/elspeth/telemetry/exporters/__init__.py:4-34`
- Observed divergence: Factory ignores hook-based discovery and uses a hardcoded registry.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Decide whether telemetry exporters are truly pluggy-based; if yes, implement discovery in the factory and eliminate the static registry.

## Acceptance Criteria

- `create_telemetry_manager()` discovers exporters registered via `elspeth_get_exporters()` and can instantiate a custom exporter by name.
- Built-in exporters remain available without manual registry updates.
- Duplicate exporter names across hooks are detected and raise a clear error.

## Tests

- Suggested tests to run: ` .venv/bin/python -m pytest tests/telemetry/test_factory.py`
- New tests required: yes, add tests for hook-based discovery and duplicate name detection.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/telemetry/hookspecs.py`, `src/elspeth/telemetry/exporters/__init__.py`
