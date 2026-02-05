# Analysis: src/elspeth/core/landscape/formatters.py

**Lines:** 229
**Role:** Provides serialization utilities and export formatters for audit data. Contains `serialize_datetime` (recursive datetime-to-ISO-string conversion with NaN/Infinity rejection), `dataclass_to_dict` (generic dataclass-to-dict conversion), and three formatter classes: `JSONFormatter`, `LineageTextFormatter`, and `CSVFormatter`. Used by the journal (for serializing records), the exporter (indirectly via JSON dumps), the MCP server, and the orchestrator export module.
**Key dependencies:** Imports `LineageResult` (TYPE_CHECKING only) from `lineage.py`. Consumed by `journal.py` (imports `serialize_datetime`), `__init__.py` (re-exports all public symbols), `engine/orchestrator/export.py`, and `mcp/server.py`.
**Analysis depth:** FULL

## Summary

The formatters module is small and focused. The code is generally correct. There are two notable issues: (1) the `serialize_datetime` function does not handle Enum values, creating an inconsistency with `dataclass_to_dict` which does, and (2) the `dataclass_to_dict` function returns `{}` for `None` input, which is a surprising semantic that could mask bugs. The `LineageTextFormatter` correctly follows Tier 1 trust principles with direct attribute access.

## Warnings

### [71] `dataclass_to_dict` returns `{}` for `None` input instead of `None`

**What:** Line 71-72: `if obj is None: return {}`. When `None` is passed to `dataclass_to_dict`, it returns an empty dict instead of `None`. This means callers cannot distinguish between "no object" and "object with no fields."

**Why it matters:** This is a semantic mismatch. If a caller has an optional field (e.g., `outcome: TokenOutcome | None = None` in `LineageResult`), converting it with `dataclass_to_dict` would turn `None` into `{}`, which evaluates as truthy. A downstream consumer checking `if result.get("outcome"):` would treat the empty dict as present, when in fact no outcome existed. This violates the principle that `None` should remain `None` through serialization.

**Evidence:**
```python
def dataclass_to_dict(obj: Any) -> Any:
    if obj is None:
        return {}  # Surprising: None -> {} loses the None signal
```

The function docstring documents this behavior ("None (returns empty dict)"), but documentation of a problematic behavior does not eliminate the problem. Callers must know about this quirk to avoid bugs.

### [20-48] `serialize_datetime` does not handle Enum values

**What:** The `serialize_datetime` function handles `float`, `datetime`, `dict`, and `list`, but does not handle `Enum` values. If a dict contains an Enum value (common in audit records where status fields are enums), the Enum will pass through unchanged. When this dict is later passed to `json.dumps`, the Enum may or may not serialize depending on the `default` parameter.

**Why it matters:** The `JSONFormatter.format` method (line 107) uses `json.dumps(record, default=str)` which would convert enums to their string representation. But `CSVFormatter.flatten` (line 221) calls `serialize_datetime(value)` on list values and then passes to `json.dumps` -- the Enum would serialize via `default=str` here too. The issue is that `serialize_datetime` is also used by the journal (line 119-120: `safe = serialize_datetime(record)`) where the subsequent `json.dumps` also uses `default=str`. So the Enum case is "handled" by the `default=str` fallback, but this is implicit rather than explicit. If the `default=str` parameter were ever removed or changed, Enums would cause `TypeError` at serialization time.

**Evidence:**
```python
def serialize_datetime(obj: Any) -> Any:
    if isinstance(obj, float): ...
    if isinstance(obj, datetime): ...
    if isinstance(obj, dict): ...
    if isinstance(obj, list): ...
    return obj  # Enum passes through here, relying on json.dumps default=str
```

### [209-225] CSVFormatter.flatten does not handle `None` values in nested dicts

**What:** The `flatten` method recursively processes dict values. If a value is `None`, it falls through to the `else` branch (line 223: `result[full_key] = value`) and is assigned directly. This is correct behavior. However, if a value is a nested dict containing `None` values, those `None` values will also be assigned directly -- which is fine for CSV (they become empty cells). This is not a bug, but the interaction between `flatten` and `serialize_datetime` (called only for lists, line 221) means datetime values in non-list, non-dict positions are NOT converted. A datetime value directly in a dict would pass through as a `datetime` object.

**Why it matters:** If a record has a datetime value that is not nested inside a list, `CSVFormatter.flatten` would assign the raw `datetime` object as a CSV cell value. Whether this causes an error depends on the CSV writer used downstream. This is unlikely given the exporter already converts datetimes to ISO strings, but it is a gap in the formatter's own robustness.

**Evidence:**
```python
def flatten(self, record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    for key, value in record.items():
        if isinstance(value, dict):
            result.update(self.flatten(value, full_key))
        elif isinstance(value, list):
            result[full_key] = json.dumps(serialize_datetime(value))  # Lists get serialized
        else:
            result[full_key] = value  # Datetime objects pass through unconverted
```

## Observations

### [110-200] LineageTextFormatter correctly implements Tier 1 trust

**What:** The `LineageTextFormatter.format` method accesses audit data fields directly (e.g., `result.outcome.outcome.name`, `state.status.value`, `call.call_type.value`) without any defensive `getattr` or `hasattr` patterns. Comments on lines 150-153 and 163-164 explicitly note that this is intentional per Tier 1 trust.

**Why it matters:** This is the correct implementation per the Data Manifesto. The direct access pattern means any corruption in the audit data will surface as an `AttributeError` rather than being silently handled.

### [173-176] Correct handling of optional `latency_ms` in LineageTextFormatter

**What:** The formatter checks `if call.latency_ms is None` before formatting, displaying "N/A" for calls without latency data. This is correct -- latency may be absent for failed calls that never received a response.

### [94-99] ExportFormatter Protocol is minimal and clean

**What:** The `ExportFormatter` protocol defines a single `format` method returning `str | dict[str, Any]`. This is appropriate for the two implementations (JSONFormatter returns `str`, CSVFormatter returns `dict`).

### [105-107] JSONFormatter uses `default=str` as catch-all

**What:** `json.dumps(record, default=str)` will silently convert any non-serializable object to its string representation. While this prevents crashes, it means type information is lost in the JSON output.

**Why it matters:** For audit export purposes, this implicit string conversion could produce misleading data if a record accidentally contains a complex object. However, since the exporter constructs records with explicit field assignments, this is a safety net rather than a primary serialization path.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Change `dataclass_to_dict` to return `None` for `None` input instead of `{}`. This is a semantic fix that prevents callers from confusing "absent" with "empty." (2) Consider adding explicit Enum handling to `serialize_datetime` for consistency, rather than relying on the `default=str` fallback in `json.dumps`. Both are low-risk changes.
**Confidence:** HIGH -- The file is small, the logic is straightforward, and the identified issues are clear semantic concerns rather than speculative.
