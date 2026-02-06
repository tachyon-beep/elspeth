# Analysis: src/elspeth/telemetry/exporters/console.py

**Lines:** 242
**Role:** Console exporter -- writes telemetry events to stdout or stderr in JSON or human-readable ("pretty") format. Primarily used for testing, local debugging, and development. Simplest of the four exporters with no external service dependencies.
**Key dependencies:** Imports `json`, `sys`, `structlog`, `dataclasses.asdict`, `dataclasses.fields`, `datetime`, `enum`. Imports `TelemetryExporterError` from `elspeth.telemetry.errors`. No external package dependencies beyond the standard library. Used by `TelemetryManager` via `ExporterProtocol`.
**Analysis depth:** FULL

## Summary

The console exporter is the simplest and most correct of the four exporters. It has no external dependencies, no buffering concerns, no connection management, and minimal state. The code is well-structured with thorough config validation using TypeGuard narrowing. The only notable issue is that it does not implement the full ExporterProtocol lifecycle (no `configure()` call is required before `export()` works), which is actually a reasonable default for a debugging tool. No critical or significant issues found.

## Warnings

### [158-167] JSON serialization does not handle dict or tuple types

**What:** The `_serialize_event` method handles `datetime -> isoformat()` and `Enum -> value` conversions, but unlike the OTLP and Azure Monitor exporters, it does NOT convert `dict` values or `tuple` values. Since `json.dumps()` handles dicts natively and converts tuples to lists, this works correctly by accident, but the inconsistency with sibling exporters means behavior diverges for edge cases.

**Why it matters:** This is functionally correct because `json.dumps()` natively handles `dict` and `list`/`tuple`. However, the `tuple -> list` conversion is implicit rather than explicit, and there is no handling for types that `json.dumps` cannot serialize (e.g., `bytes`, `set`, `Decimal`). If a future event type includes a non-JSON-serializable field, the OTLP/Azure Monitor exporters would handle it (or fail explicitly in their serializer), while the console exporter would crash in `json.dumps()` and the error would be caught by the outer `try/except`.

**Evidence:**
```python
# Console exporter (only handles datetime and Enum):
for key, value in data.items():
    if isinstance(value, datetime):
        data[key] = value.isoformat()
    elif isinstance(value, Enum):
        data[key] = value.value

# OTLP/Azure Monitor (handles datetime, Enum, dict, tuple, None):
for key, value in data.items():
    if value is None:
        continue
    elif isinstance(value, datetime):
        result[key] = value.isoformat()
    elif isinstance(value, Enum):
        result[key] = value.value
    elif isinstance(value, dict):
        result[key] = json.dumps(value)
    elif isinstance(value, tuple):
        result[key] = list(value)
```

### [208] getattr used in pretty-print extraction

**What:** `_extract_pretty_details` uses `getattr(event, field_name)` to access fields dynamically. The CLAUDE.md prohibits defensive `getattr` usage, but here the field names come from `dataclasses.fields(event)`, which guarantees they exist on the dataclass instance.

**Why it matters:** This is a legitimate use of `getattr` -- the field names are derived from the type's own field declarations, not from external input or guesswork. The pattern is equivalent to accessing a known attribute by a computed name. This is NOT a defensive pattern hiding a bug.

**Evidence:**
```python
event_fields = {f.name for f in fields(event)} - base_fields
for field_name in sorted(event_fields):
    value = getattr(event, field_name)
```
Since `fields(event)` returns the actual dataclass fields, every `field_name` is guaranteed to exist. This is safe.

## Observations

### [62-66] Works without configure() -- intentional design

The console exporter initializes with sensible defaults (`json` format, `stdout` output) and can export events without calling `configure()`. This is verified by the test `test_export_works_with_default_configuration`. While this technically violates the ExporterProtocol lifecycle (which specifies configure -> export -> flush -> close), it is a pragmatic choice for a debugging exporter that should "just work."

### [27-34] TypeGuard pattern is well-applied

The `_is_valid_format` and `_is_valid_output` TypeGuard functions enable mypy to narrow the type from `str` to `Literal["json", "pretty"]` or `Literal["stdout", "stderr"]` within the `if` branch. This is a clean application of TypeGuard for runtime validation that also satisfies the type checker.

### [235-241] close() is intentionally a no-op

The console exporter does not own the stdout/stderr streams, so `close()` correctly does not close them. This is documented and tested. This matches the ExporterProtocol requirement that `close()` be idempotent.

### [134] print() is used instead of stream.write()

The exporter uses `print(line, file=self._stream)` which appends a newline automatically. This is correct for JSONL (JSON Lines) format and for pretty-print output. The `print()` function handles encoding and newline correctly for the stream type.

### [161-163] Mutation of asdict result

`_serialize_event` mutates the `data` dict returned by `asdict(event)` in-place (reassigning values for datetime/enum keys and adding `event_type`). This is safe because `asdict` returns a new dict, but it is worth noting that the OTLP/Azure Monitor exporters create a separate `result` dict and leave the `data` dict untouched. The console approach is simpler and equally correct.

### Test coverage is excellent

The test file `test_console.py` has 655 lines covering configuration validation, JSON format output, pretty format output, stream selection, error handling, datetime/enum serialization, edge cases (None values, empty tuples, multiple events), and plugin registration. This is the most thoroughly tested of the four exporters.

### No None filtering in JSON mode

In JSON mode, `_serialize_event` does not skip `None` values (unlike the OTLP/Azure Monitor serializers which use `if value is None: continue`). This means `None` fields appear in JSON output as `null`. This is actually preferable for debugging (you can see all fields), while the OTLP/Azure Monitor exporters omit `None` to reduce span attribute count. The pretty format correctly omits `None` values (line 209: `if value is not None`).

## Verdict

**Status:** SOUND
**Recommended action:** Minor improvements only: (1) Consider adding explicit `tuple -> list` and `dict` handling in `_serialize_event` for consistency with sibling exporters, even though `json.dumps` handles these natively. (2) The code is clean, well-tested, and correct for its purpose.
**Confidence:** HIGH -- Full analysis with complete context from protocol, manager, factory, events, and comprehensive test file.
