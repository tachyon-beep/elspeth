## Summary

`Runtime*Config` objects are documented as immutable, but mutable dict fields (`services` and `options`) allow in-place mutation after construction, causing runtime config drift.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — hardening issue, not an active defect; all callers are our code and no production path mutates these dicts today)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py`
- Line(s): 7-11, 295, 351, 515, 600
- Function/Method: `RuntimeRateLimitConfig.from_settings`, `ExporterConfig`, `RuntimeTelemetryConfig.from_settings`

## Evidence

`runtime.py` explicitly states runtime configs are frozen/immutable (`src/elspeth/contracts/config/runtime.py:7-11`), but:

- `RuntimeRateLimitConfig.services` is a mutable `dict` (`src/elspeth/contracts/config/runtime.py:295`)
- `from_settings` stores a normal dict (`src/elspeth/contracts/config/runtime.py:351`)
- `ExporterConfig.options` is a mutable `dict` (`src/elspeth/contracts/config/runtime.py:515`)
- telemetry conversion builds `ExporterConfig(..., options=dict(...))` (still mutable dict) (`src/elspeth/contracts/config/runtime.py:600`)

Repro (executed in workspace) shows mutation succeeds after construction:
- `rl.services['newsvc']=...` changed `RuntimeRateLimitConfig`
- `exp.options['pretty']=False` changed `ExporterConfig`
- `tele.exporter_configs[0].options['pretty']=False` changed telemetry config payload

Integration impact evidence:
- configs are passed into long-lived runtime components (`src/elspeth/cli.py:852-863`)
- rate-limit registry is explicitly concurrent/thread-safe (`src/elspeth/core/rate_limit/registry.py:56-57`), so mutable config state undermines invariants.

## Root Cause Hypothesis

`@dataclass(frozen=True)` was treated as sufficient immutability, but container fields were left as plain mutable dicts, creating shallow immutability only.

## Suggested Fix

In `runtime.py`, make container fields deeply immutable at construction:

- Use read-only mappings for `services` and `options` (e.g., `types.MappingProxyType`).
- Update type hints from `dict[...]` to `Mapping[...]`.
- Ensure `default()`/`from_settings()` wrap copies in immutable mappings.
- Add regression tests asserting in-place mutation raises `TypeError`.

## Impact

Runtime behavior can change after config creation (quota maps and exporter options), breaking deterministic configuration guarantees and risking racey, non-reproducible behavior in concurrent execution paths.
