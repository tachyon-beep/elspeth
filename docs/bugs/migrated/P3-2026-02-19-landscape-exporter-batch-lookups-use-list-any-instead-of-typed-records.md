## Summary

The Landscape exporter pre-loads batch data into four `dict[str, list[Any]]` structures for export optimization. The `list[Any]` values are actually typed database records (node states, routing events, calls, token outcomes), but this is not expressed in the type system.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/core/landscape/exporter.py` — Lines 302-323

## Evidence

```python
# exporter.py — batch loading
states_by_token: dict[str, list[Any]] = {}      # Line 302 — actually list[NodeState]
events_by_state: dict[str, list[Any]] = {}      # Line 308 — actually list[RoutingEvent]
calls_by_state: dict[str, list[Any]] = {}       # Line 314 — actually list[Call]
outcomes_by_token: dict[str, list[Any]] = {}     # Line 321 — actually list[TokenOutcome]
```

The `Any` types lose all type information from the database query results, preventing IDE autocomplete and type checking when accessing record fields during export formatting.

## Proposed Fix

Replace `list[Any]` with the actual SQLAlchemy row types or create typed wrappers:

```python
states_by_token: dict[str, list[NodeStateRow]] = {}
events_by_state: dict[str, list[RoutingEventRow]] = {}
calls_by_state: dict[str, list[CallRow]] = {}
outcomes_by_token: dict[str, list[TokenOutcomeRow]] = {}
```

The specific row types depend on whether SQLAlchemy `Row` objects are used directly or wrapped in dataclasses.

## Affected Subsystems

- `core/landscape/exporter.py` — batch loading and export formatting
