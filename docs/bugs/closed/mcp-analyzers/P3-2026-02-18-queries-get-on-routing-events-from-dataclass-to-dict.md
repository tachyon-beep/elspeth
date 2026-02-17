## Summary

`explain_token_for_mcp()` in `queries.py` uses `.get("routing_events", [])` and `.get("mode")` on a dict built from `_dataclass_to_dict(result)`. Since `routing_events` and `mode` are always-present dataclass fields, this treats Tier 1 audit data as optional.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/mcp/analyzers/queries.py`
- Lines: 348, 349, 352
- Function: `explain_token_for_mcp()`

## Evidence

`result_dict` is created via `_dataclass_to_dict(result)` where `result` is an `ExplainTokenResult` dataclass. Dataclass-to-dict conversion always includes all fields. `routing_events` is always present (may be empty list). Each event's `mode` field is a `RoutingMode` enum value — always present.

## Fix Applied

Changed `.get("routing_events", [])` to `["routing_events"]` and `.get("mode")` to `["mode"]` on all three lines.

Note: `reason_hash` on line 363 was NOT changed — it is genuinely nullable in the DB schema (column has no `nullable=False` constraint, and write-side sets it to `None` when no reason exists).

## Impact

Corruption in audit data (missing routing_events or mode) now crashes instead of silently producing empty/incorrect results.
