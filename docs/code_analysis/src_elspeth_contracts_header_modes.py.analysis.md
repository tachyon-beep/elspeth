# Analysis: src/elspeth/contracts/header_modes.py

**Lines:** 107
**Role:** Defines header output modes for sinks (NORMALIZED, ORIGINAL, CUSTOM) and provides functions to parse mode from config and resolve output headers against a SchemaContract.
**Key dependencies:**
- Imports: `SchemaContract` (TYPE_CHECKING only, from `schema_contract.py`)
- Imported by: `csv_sink.py`, `json_sink.py`, `config_base.py`, `contracts/__init__.py`
**Analysis depth:** FULL

## Summary

This file is well-structured and mostly sound. The code is clean, enum-based, and the resolution logic is straightforward. The most notable concern is a silent degradation path when ORIGINAL mode is used with a contract but `get_field()` returns `None` -- the code falls back to the normalized name without any signal, which could produce silently incorrect CSV headers in production. No critical findings. Two warnings related to silent fallback semantics and case-sensitivity on config parsing.

## Critical Findings

None.

## Warnings

### [96-97] Silent fallback to normalized name when field not found in contract in ORIGINAL mode

**What:** When `mode == HeaderMode.ORIGINAL` and a contract is provided, `contract.get_field(name)` can return `None`. In that case, line 97 falls back to `result[name] = name` (the normalized name). This means a field that should have its original header restored silently gets its Python identifier name instead.

**Why it matters:** This can produce silently incorrect CSV/JSON headers in production. If a sink is configured in ORIGINAL mode precisely because external consumers expect the original column names (e.g., "'Amount USD'" instead of "amount_usd"), silently using the normalized name breaks downstream integrations. The user explicitly chose ORIGINAL mode, so falling back without warning violates the principle of least surprise.

**Evidence:**
```python
elif mode == HeaderMode.ORIGINAL:
    if contract is not None:
        field = contract.get_field(name)
        result[name] = field.original_name if field else name  # Silent fallback
```

The field names come from `contract.fields` (line 82), so `get_field()` should always find them. However, if `field_names` were passed alongside a contract (a hypothetical future misuse), or if contract internals diverge from the iterated names, this would silently produce wrong headers.

### [53-58] Case-sensitive string comparison for mode parsing

**What:** `parse_header_mode()` compares the config string with exact lowercase matches: `"normalized"` and `"original"`. A user writing `"Normalized"` or `"ORIGINAL"` in their YAML config would get a `ValueError`.

**Why it matters:** While the Pydantic validator in `config_base.py` (line 259) also enforces valid values before this function is called through the normal config path, `parse_header_mode` is a public API in the contracts package. Direct callers could hit this case sensitivity. YAML configs often have users mixing cases. The error message helpfully says what's expected, so the user impact is low, but it is a friction point.

**Evidence:**
```python
if config == "normalized":
    return HeaderMode.NORMALIZED
if config == "original":
    return HeaderMode.ORIGINAL
raise ValueError(f"Invalid header mode '{config}'. Expected 'normalized', 'original', or mapping dict.")
```

## Observations

### [100-105] CUSTOM mode silently falls back to normalized for unmapped fields

**What:** When `mode == HeaderMode.CUSTOM` and a field is not in the custom mapping, it falls back to the normalized name. This is documented behavior and tested, but it means a partial custom mapping silently mixes naming conventions in the output.

**Why it matters:** Low severity. This is arguably the correct default behavior (better than crashing), and it is tested. However, a strict mode that rejects incomplete custom mappings could be valuable for users who want explicit control. This is a design observation, not a bug.

### [85-86] Empty dict return for no-contract-no-fields case

**What:** When both `contract` and `field_names` are `None`, the function returns an empty dict. This is a reasonable default, but callers must handle it -- writing a CSV with an empty header mapping would produce no headers at all.

**Why it matters:** Very low severity. This path is tested and callers (CSV/JSON sinks) handle it appropriately.

### [1-9] Module docstring references "Sink header mode resolution" but file also handles general header modes

**What:** The docstring says "Sink header mode resolution" but `HeaderMode` is a general-purpose enum that could in theory be used outside sinks. Currently it is only used by sinks, so this is accurate but narrowly scoped.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding a log warning in the ORIGINAL mode fallback path (line 97) when `get_field()` returns `None`. This would make silent header degradation observable without changing behavior. The case sensitivity issue is very minor given Pydantic validation upstream.
**Confidence:** HIGH -- the file is small, thoroughly tested (test_header_modes.py covers all paths), and the logic is straightforward.
