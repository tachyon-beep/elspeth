## Summary

`display_headers.py` silently falls back to normalized field names in `headers: {mapping}` mode when the mapping is empty or incomplete, violating the sink header contract and emitting externally visible column names the user did not configure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py`
- Line(s): 85-86, 219-230
- Function/Method: `get_effective_display_headers`, `apply_display_headers`

## Evidence

`get_effective_display_headers()` returns the raw custom mapping without validating it:

```python
if sink._headers_mode == HeaderMode.CUSTOM:
    return sink._headers_custom_mapping
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:85-86`

Then `apply_display_headers()` silently preserves unmapped keys instead of failing:

```python
display_key = display_map[k] if k in display_map else k
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:228-229`

That behavior contradicts the repository’s canonical header contract. `resolve_headers()` explicitly requires CUSTOM mappings to be complete and non-empty:

```python
if mode == HeaderMode.CUSTOM and not custom_mapping:
    raise ValueError(...)
...
if name not in custom_mapping:
    raise ValueError(
        f"CUSTOM header mode has no mapping for field '{name}'. "
        f"All fields must be explicitly mapped — silent fallback to normalized "
        f"names risks data corruption in external system handover."
    )
```

Source: `/home/john/elspeth/src/elspeth/contracts/header_modes.py:90-119`

The contract is also codified in tests:

- `/home/john/elspeth/tests/unit/contracts/test_header_modes.py:121-130` says partial CUSTOM mapping must raise because “silent fallback is data corruption”.
- `/home/john/elspeth/tests/unit/contracts/test_header_modes.py:164-170` says `None` mapping in CUSTOM mode must raise.

But the target file’s own tests currently assert the opposite behavior:

- `/home/john/elspeth/tests/unit/plugins/infrastructure/test_display_headers.py:296-304` expects unmapped keys to pass through.
- `/home/john/elspeth/tests/unit/plugins/infrastructure/test_display_headers.py:333-342` expects an empty mapping to pass through unchanged.

This bug is not isolated to helper internals. CSV header generation also consumes this permissive map and falls back per field:

```python
display_fields = [display_map.get(field, field) for field in data_fields]
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:475-483`

So a sink configured with `headers: {"amount_usd": "AMOUNT"}` can emit a mixed header set like `AMOUNT,customer_id`, even though the declared contract says that should fail.

## Root Cause Hypothesis

`display_headers.py` implements a second, looser CUSTOM-mode policy than `contracts/header_modes.py`. The helper treats CUSTOM mode as “best-effort rename whatever is mapped,” while the contract layer defines CUSTOM mode as “explicit external handover mapping for every field.” That split likely happened to accommodate transform-added fields, but it bypasses the repository’s stated rule that silent fallback in CUSTOM mode is unsafe.

## Suggested Fix

Make `display_headers.py` enforce CUSTOM-mode completeness instead of returning raw mappings and per-key fallbacks.

A safe approach:

- In `get_effective_display_headers()`, stop returning `_headers_custom_mapping` directly for `HeaderMode.CUSTOM`.
- In `apply_display_headers()`, when `HeaderMode.CUSTOM` is active, validate the current row fields with `resolve_headers(contract=None, mode=HeaderMode.CUSTOM, custom_mapping=..., field_names=list(row.keys()))` and use the returned mapping.
- Do the same for CSV header generation so `_get_field_names_and_display()` cannot emit partially mapped headers.
- Update the permissive tests in `tests/unit/plugins/infrastructure/test_display_headers.py` to expect `ValueError` for empty/incomplete mappings.

## Impact

Sinks can silently emit wrong output schemas in CUSTOM mode, especially for external system handoff. That breaks the documented plugin contract, can produce mixed normalized/custom headers in CSV/JSON/JSONL/blob outputs, and violates ELSPETH’s auditability standard by recording a configured handoff that did not actually occur as specified.
