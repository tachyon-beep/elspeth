# Bug Report: User-defined sink names are lowercased during config load

## Summary

- `_lowercase_schema_keys()` lowercases sink names (dict keys in `sinks` section) which can break `default_sink` references using mixed case.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/config.py:1279-1308` - `_lowercase_schema_keys()` preserves `options` contents but lowercases outer dict keys
- Sink names like `MySink` become `mysink`
- `default_sink: MySink` would then fail validation

## Impact

- User-facing impact: Mixed-case sink names break unexpectedly
- Data integrity: None

## Proposed Fix

- Preserve sink name casing or document lowercase-only requirement

## Acceptance Criteria

- Sink names preserve original casing, or validation fails early with clear message
