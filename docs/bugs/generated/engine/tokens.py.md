## Summary

`create_quarantine_token()` crashes on quarantined rows whose payload is a `dict` subclass or other mapping-like object, so malformed external data that should be quarantined can instead abort the run.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/tokens.py
- Line(s): 150-165
- Function/Method: `TokenManager.create_quarantine_token`

## Evidence

`create_quarantine_token()` currently treats any `isinstance(..., dict)` payload as ready for `PipelineRow`:

```python
# /home/john/elspeth/src/elspeth/engine/tokens.py:150-165
row_data: dict[str, Any] = source_row.row if isinstance(source_row.row, dict) else {"_raw": source_row.row}
pipeline_row = PipelineRow(row_data, quarantine_contract)
```

But `PipelineRow` rejects anything that is not an exact builtin `dict`:

```python
# /home/john/elspeth/src/elspeth/contracts/schema_contract.py:541-545
if type(data) is not dict:
    raise TypeError(
        f"PipelineRow requires exactly dict, got {type(data).__name__}. "
    )
```

Quarantined source rows are explicitly allowed to carry arbitrary external payloads:

```python
# /home/john/elspeth/src/elspeth/contracts/results.py:503-568
row: Any
...
@classmethod
def quarantined(cls, row: Any, error: str, destination: str) -> SourceRow:
```

So a quarantined payload like `OrderedDict(...)` or another mapping subtype passes the `isinstance(..., dict)` check in `tokens.py`, then immediately fails in `PipelineRow(...)` with `TypeError` instead of being routed to quarantine.

The existing tests only cover:
- plain `dict` payloads: `/home/john/elspeth/tests/unit/engine/test_tokens.py:852-869`
- clearly non-dict payloads like `list`: `/home/john/elspeth/tests/unit/engine/test_tokens.py:871-887`

There is no coverage for the middle case of dict subclasses / mapping-like quarantine payloads.

## Root Cause Hypothesis

The quarantine path mixes two incompatible assumptions:

- `tokens.py` uses `isinstance(source_row.row, dict)` as if any dict-like mapping is acceptable.
- `PipelineRow` enforces a stricter Tier-1 invariant: only an exact builtin `dict` is allowed.

That mismatch is harmless for plain dicts and obvious non-dicts, but it breaks on mapping subtypes that are valid external payload containers.

## Suggested Fix

Normalize quarantined mapping payloads to a plain builtin `dict` before constructing `PipelineRow`.

Example shape:

```python
from collections.abc import Mapping

raw_row = source_row.row
if type(raw_row) is dict:
    row_data = raw_row
elif isinstance(raw_row, Mapping):
    row_data = dict(raw_row)
else:
    row_data = {"_raw": raw_row}
```

Also add a regression test where `SourceRow.quarantined()` receives an `OrderedDict` or custom `Mapping`, and assert that `create_quarantine_token()` succeeds and preserves the payload content.

## Impact

A source plugin can correctly identify a bad external row and emit `SourceRow.quarantined(...)`, yet the engine still crashes before recording the quarantine token if the raw payload is a mapping subtype instead of a plain `dict`.

That breaks the Tier-3 boundary contract from `CLAUDE.md`: bad external data should be quarantined and recorded, not take down the run. In practice this causes:
- loss of the expected `QUARANTINED` terminal outcome for that row
- interruption of processing for subsequent rows
- incomplete audit trail for a row that should have had a traceable quarantine path
