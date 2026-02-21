## Summary

`CSVFormatter.flatten()` can silently overwrite fields when flattened keys collide (e.g., dotted keys vs nested keys), causing audit export data loss in CSV output.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — requires pathological dotted-key input; only affects CSV export format, not DB)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/formatters.py`
- Line(s): `214-219`
- Function/Method: `CSVFormatter.flatten`

## Evidence

`CSVFormatter.flatten()` builds dot-notation keys and merges nested dicts with `dict.update()`:

```python
# src/elspeth/core/landscape/formatters.py:214-219
for key, value in record.items():
    full_key = f"{prefix}.{key}" if prefix else key

    if isinstance(value, dict):
        result.update(self.flatten(value, full_key))
```

This has no collision detection. If two different input paths produce the same flattened key, later writes overwrite earlier ones.

Repro against current code:

- Input:
  `{"config": {"a.b": "flat", "a": {"b": "nested"}}}`
- Output:
  `{"config.a.b": "nested"}`

The `"flat"` value is dropped silently.

Why this is reachable in integration:

- Plugin `options` are intentionally preserved exactly, including user-provided key names (`src/elspeth/core/config.py:1897`).
- Export includes node config dicts (`"config": json.loads(node.config_json)`) (`src/elspeth/core/landscape/exporter.py:214`).
- CSV export uses `CSVFormatter.flatten()` for every record (`src/elspeth/engine/orchestrator/export.py:160`).

So user config keys with dots can collide with nested objects and lose data in exported CSV.

## Root Cause Hypothesis

Flattening uses dot-joined paths without an escaping scheme and merges recursively with `result.update(...)`, so key-path ambiguity is not representable and collisions are silently overwritten.

## Suggested Fix

In `CSVFormatter.flatten()`, detect key collisions and fail fast with a clear `ValueError` (preferred over silent overwrite for audit integrity). Example approach:

- Before assigning `result[full_key]`, check `if full_key in result: raise ValueError(...)`.
- When merging nested results, iterate keys and reject duplicates instead of `update(...)`.

Optionally, adopt an escaping strategy for literal `.` in source keys, but collision detection is the minimum required fix.

## Impact

CSV audit exports can omit real fields without any error, producing incomplete/misleading artifacts for compliance review. This violates traceability expectations for exported audit data and can break downstream analysis that assumes CSV export is lossless.

## Triage

Triage: Downgraded P1→P2. Requires user plugin config with literal dots in keys. Data not lost from Landscape DB — only CSV representation affected. JSON export uses JSONFormatter which doesn't flatten.
