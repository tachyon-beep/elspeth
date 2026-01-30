# Bug Report: User-defined sink names are lowercased during config load, breaking default_sink and routing

## Summary

- `_lowercase_schema_keys` lowercases all dict keys except those under `options`, which mutates user-defined sink names (dict keys in `sinks`) and can make `default_sink` and gate routing references fail even when the YAML is valid.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: de0ca01 / fix/P2-aggregation-metadata-hardcoded
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Minimal settings.yaml with mixed-case sink name

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/config.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a settings file with a mixed-case sink key, e.g.:
   ```yaml
   source:
     plugin: csv
     options:
       path: input.csv
       schema:
         fields: dynamic
   sinks:
     MySink:
       plugin: csv
       options:
         path: output.csv
         schema:
           fields: dynamic
   default_sink: MySink
   ```
2. Call `load_settings(Path("settings.yaml"))`.

## Expected Behavior

- Settings load successfully, and `default_sink` resolves to the user-defined sink key `MySink` without case changes.

## Actual Behavior

- `load_settings` lowercases sink keys to `mysink`, so validation fails with `default_sink 'MySink' not found in sinks`, even though the YAML is consistent.

## Evidence

- `_lowercase_schema_keys` lowercases dict keys by default (src/elspeth/core/config.py:1279, src/elspeth/core/config.py:1301).
- `load_settings` applies `_lowercase_schema_keys` to the full config dict (src/elspeth/core/config.py:1351).
- `default_sink` validation compares the string value against dict keys without case normalization (src/elspeth/core/config.py:799, src/elspeth/core/config.py:801).
- Gate route destinations are documented as any dict key sink name, implying case should be preserved (src/elspeth/core/config.py:224, src/elspeth/core/config.py:225).

## Impact

- User-facing impact: Valid configs using mixed-case sink names fail to load with a misleading “sink not found” error.
- Data integrity / security impact: None directly; pipelines fail before execution.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `_lowercase_schema_keys` is designed to normalize schema keys but lacks path-awareness, so it lowercases user-defined dict keys (like `sinks` and `routes`) that should be preserved verbatim.

## Proposed Fix

- Code changes (modules/files):
  - Adjust `_lowercase_schema_keys` in `src/elspeth/core/config.py` to preserve dict keys for user-defined name maps (at least `sinks` and `gates[*].routes`), while still lowercasing schema keys inside each mapped value.
  - Example approach: pass parent-key context and only lowercase keys when they are schema fields, not user-defined identifiers.
- Config or schema changes: None.
- Tests to add/update:
  - Add a config-loading test that uses mixed-case sink names and verifies `default_sink` and gate destinations resolve correctly after `load_settings`.
  - Add a test that verifies route labels in `gates[].routes` are preserved.
- Risks or migration steps:
  - Minimal; behavior becomes more permissive and aligns with documented flexibility for sink keys.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): src/elspeth/core/config.py:1280 (docstring promises “user data preserved”), src/elspeth/core/config.py:224 (sink names can be any dict key).
- Observed divergence: User-defined dict keys (sink names, route labels) are lowercased during load, violating the stated preservation of user data.
- Reason (if known): Overly broad lowercasing intended to normalize Dynaconf schema keys.
- Alignment plan or decision needed: Make lowercasing path-aware to preserve user-defined identifiers while still normalizing schema fields.

## Acceptance Criteria

- `load_settings` preserves sink key case and `default_sink` validation succeeds for mixed-case sink names.
- Gate route labels and sink destinations remain unchanged after load.
- Added tests pass and prevent regression.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/`
- New tests required: yes, config-loading unit tests covering case preservation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/reference/configuration.md`
