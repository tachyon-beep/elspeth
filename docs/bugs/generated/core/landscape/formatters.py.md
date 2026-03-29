## Summary

`CSVFormatter.flatten()` silently drops empty nested objects, so CSV audit exports lose the fact that a field was present-but-empty.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [formatters.py](/home/john/elspeth/src/elspeth/core/landscape/formatters.py)
- Line(s): 243-251
- Function/Method: `CSVFormatter.flatten`

## Evidence

`CSVFormatter.flatten()` only emits keys for nested dict members:

```python
if isinstance(value, dict):
    nested = self.flatten(value, full_key)
    for nested_key, nested_val in nested.items():
        ...
        result[nested_key] = nested_val
```

When `value == {}`, `nested.items()` is empty, so `full_key` disappears entirely. The current unit test codifies that behavior:

- [tests/unit/core/landscape/test_formatters.py:279](/home/john/elspeth/tests/unit/core/landscape/test_formatters.py#L279) through [tests/unit/core/landscape/test_formatters.py:293](/home/john/elspeth/tests/unit/core/landscape/test_formatters.py#L293) expects `"empty"` not to appear in the flattened output.

That omission is not isolated to a toy helper. The CSV export path uses this formatter for every exported audit record:

- [export.py:156](/home/john/elspeth/src/elspeth/engine/orchestrator/export.py#L156) through [export.py:169](/home/john/elspeth/src/elspeth/engine/orchestrator/export.py#L169)

And exported records do carry structured config/settings payloads where `{}` is a valid, meaningful value:

- [export_records.py:21](/home/john/elspeth/src/elspeth/contracts/export_records.py#L21) `settings: Any`
- [export_records.py:47](/home/john/elspeth/src/elspeth/contracts/export_records.py#L47) `config: Any`
- [exporter.py:227](/home/john/elspeth/src/elspeth/core/landscape/exporter.py#L227) populates `settings` from stored JSON
- [exporter.py:260](/home/john/elspeth/src/elspeth/core/landscape/exporter.py#L260) populates `config` from stored JSON

What the code does: turns `{}` into “field absent”.

What it should do: preserve the distinction between “present and empty” and “not present”, because ELSPETH’s audit rules treat absence vs empty as materially different facts.

## Root Cause Hypothesis

The flattener treats nested dicts only as containers to recurse into, with no representation for the container itself when it has zero children. That is convenient for CSV shape generation, but it violates the project’s “record what happened exactly” rule by collapsing an explicit empty object into non-existence.

## Suggested Fix

Preserve empty dicts explicitly instead of dropping them. A straightforward fix in `CSVFormatter.flatten()` is to special-case empty dicts and serialize them as JSON:

```python
if isinstance(value, dict):
    if not value:
        if full_key in result:
            raise ValueError(...)
        result[full_key] = "{}"
        continue
    nested = self.flatten(value, full_key)
    ...
```

Add export-level tests proving that CSV output retains empty `settings`/`config` fields rather than omitting them.

## Impact

CSV audit exports can silently lose probative data. An auditor reading the export cannot distinguish:

- a node config that was explicitly `{}`, from
- a config field that was never present

That is silent data loss in an artifact explicitly meant for compliance review and legal inquiry.
---
## Summary

`LineageTextFormatter` omits `routing_events` entirely, so `elspeth explain --no-tui` hides the actual routing/divert decisions for a token.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: [formatters.py](/home/john/elspeth/src/elspeth/core/landscape/formatters.py)
- Line(s): 181-220
- Function/Method: `LineageTextFormatter.format`

## Evidence

`LineageResult` explicitly contains routing history:

- [lineage.py:44](/home/john/elspeth/src/elspeth/core/landscape/lineage.py#L44) through [lineage.py:45](/home/john/elspeth/src/elspeth/core/landscape/lineage.py#L45) define `routing_events: tuple[RoutingEvent, ...]`

But `LineageTextFormatter.format()` never renders that field. After outcome it prints node states, calls, errors, and parent tokens:

- [formatters.py:181](/home/john/elspeth/src/elspeth/core/landscape/formatters.py#L181) through [formatters.py:220](/home/john/elspeth/src/elspeth/core/landscape/formatters.py#L220)

There is no `--- Routing Events ---` section and no iteration over `result.routing_events`.

This matters because the CLI’s non-TUI explain path uses this formatter directly:

- [cli.py:784](/home/john/elspeth/src/elspeth/cli.py#L784) through [cli.py:786](/home/john/elspeth/src/elspeth/cli.py#L786)

So a token can have recorded routing history, including divert/quarantine edges and reason hashes, yet the human-readable explain output never shows it.

What the code does: prints a lineage report without routing decisions.

What it should do: include routing events, because those events are part of the token’s recorded lineage and often explain why the token reached a sink or quarantine path.

## Root Cause Hypothesis

`LineageTextFormatter` appears to have been built around source row, outcome, states, and calls, but never updated when `LineageResult` gained first-class `routing_events`. The data is queried and returned correctly; the formatter just drops it from the text view.

## Suggested Fix

Add a routing section to `LineageTextFormatter.format()` that prints at least:

- routing mode
- edge id
- ordinal
- routing group id
- reason hash when present

Example shape:

```python
if result.routing_events:
    lines.append("--- Routing Events ---")
    for event in result.routing_events:
        lines.append(
            f"  [{event.ordinal}] {event.mode.value} edge={event.edge_id} reason_hash={event.reason_hash}"
        )
    lines.append("")
```

Add formatter tests with non-empty `routing_events` to lock this in.

## Impact

`elspeth explain --no-tui` can produce an incomplete lineage narrative for routed or diverted tokens. The audit data still exists in Landscape, but the primary text investigation path hides the exact routing decisions, which slows incident analysis and can mislead operators about why a row ended up in a given sink or quarantine path.
