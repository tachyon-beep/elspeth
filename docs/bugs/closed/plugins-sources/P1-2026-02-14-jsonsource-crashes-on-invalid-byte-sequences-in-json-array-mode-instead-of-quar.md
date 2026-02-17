## Summary

`JSONSource` crashes on invalid byte sequences in JSON array mode instead of quarantining the parse failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py`
- Line(s): `242-246` and missing `UnicodeDecodeError` handling through `261`
- Function/Method: `_load_json_array`

## Evidence

In array mode, the file is opened with strict decoding and only JSON parse/value errors are caught:

```python
with open(self._path, encoding=self._encoding) as f:
    try:
        data = json.load(f, parse_constant=_reject_nonfinite_constant)
    except (json.JSONDecodeError, ValueError) as e:
        ...
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:242-246`

`UnicodeDecodeError` is not handled here, so undecodable external bytes can abort the source instead of producing a quarantined `SourceRow`.

By contrast, JSONL mode explicitly handles encoding failures and quarantines them:

- surrogateescape path + quarantine: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:188-201`
- explicit decode error quarantine fallback: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:226-238`

Test coverage currently verifies invalid encoding for JSONL only, not JSON array mode:

- `/home/john/elspeth-rapid/tests/unit/plugins/sources/test_json_source.py:555-660`

So this crash path is both unhandled and untested in array mode.

## Root Cause Hypothesis

Error handling in `JSONSource` was hardened for JSONL (line-by-line trust-boundary quarantine), but equivalent handling was not added to the JSON array code path, which still assumes decoding will either succeed or manifest as `JSONDecodeError`/`ValueError`.

## Suggested Fix

Handle decoding failures in `_load_json_array` as Tier-3 parse failures and route through `_record_parse_error`:

- Catch `UnicodeDecodeError` around `open/json.load` and emit quarantined row (or discard based on config), matching existing parse-error behavior.
- Optionally open with `errors="surrogateescape"` and detect surrogate bytes similarly to JSONL for better raw-byte audit payloads.
- Add tests for JSON array invalid-encoding behavior in both `quarantine` and `discard` modes.

## Impact

Malformed external JSON array files can crash pipeline execution instead of producing auditable quarantine records. This violates source trust-boundary behavior and weakens audit completeness ("record what we saw" for Tier-3 failures).
