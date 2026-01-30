# Bug Report: PluginConfig.from_dict crashes on schema: null or non-mapping configs

## Summary

- `PluginConfig.from_dict()` calls `SchemaConfig.from_dict(schema_dict)` without checking if `schema_dict` is a mapping. TypeError not caught by `except ValueError`.

## Severity

- Severity: moderate (P3 original, upgraded)
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/config_base.py:59-68` - calls `SchemaConfig.from_dict(schema_dict)` without type check
- `SchemaConfig.from_dict()` at line 280 accesses `"fields" not in config` - TypeError if None
- `except ValueError` at line 67-68 doesn't catch TypeError

## Impact

- User-facing impact: Confusing TypeError on malformed config
- Data integrity: None (fails fast)

## Proposed Fix

- Check `isinstance(schema_dict, dict)` before calling `SchemaConfig.from_dict()`

## Acceptance Criteria

- Clear error message for `schema: null` or non-dict schema values
