# Analysis: src/elspeth/contracts/schema.py

**Lines:** 471
**Role:** Schema configuration types for config-driven plugin schemas. Defines `FieldDefinition`, `SchemaConfig`, and field parsing/validation logic. This is the user-facing configuration layer -- it parses YAML schema declarations into validated config objects that later get converted to runtime `SchemaContract` objects.
**Key dependencies:** No internal imports (pure standard library: `re`, `dataclasses`, `typing`). Imported by `schema_contract_factory.py`, `plugins/config_base.py`, `plugins/schema_factory.py`, `plugins/validation.py`, and many test files. This is a foundational config module.
**Analysis depth:** FULL

## Summary

This file is well-structured and defensively coded. The field parsing logic is thorough with good error messages. The `SchemaConfig.from_dict()` factory method handles the three schema modes correctly with appropriate validation. One notable concern is a semantic gap between `_parse_field_names_list` treating empty lists as `None` (lines 150-151), which could mask user intent in edge cases. Overall, this is sound code with minor observations.

## Critical Findings

None.

## Warnings

### [41] FIELD_PATTERN allows `\w+` which includes Unicode characters

**What:** The regex `FIELD_PATTERN = re.compile(r"^(\w+):\s*(str|int|float|bool|any)(\?)?$")` uses `\w+` which in Python 3 matches Unicode letters (accented characters, CJK, etc.), not just ASCII. The subsequent `name.isidentifier()` check (line 102) also accepts Unicode identifiers. This means field names like `preis`, `nombre`, or `montant` are valid, but more exotic Unicode identifiers could also pass.

**Why it matters:** Field names flow into dict keys, JSON serialization (canonical JSON via RFC 8785), database column references, and Jinja2 templates. While Python technically supports Unicode identifiers, downstream consumers (SQL databases, JSON canonical form, CSV headers) may not handle them consistently. This could cause silent serialization divergence in the canonical hash if the same Unicode character has multiple normalization forms (NFC vs NFD).

**Evidence:**
```python
FIELD_PATTERN = re.compile(r"^(\w+):\s*(str|int|float|bool|any)(\?)?$")
# ...
if not name.isidentifier():  # Also Unicode-aware in Python 3
```

### [150-151] Empty list treated as None silently discards user intent

**What:** `_parse_field_names_list` returns `None` when the input is an empty list (`[]`), treating it the same as not specifying the field at all.

**Why it matters:** A user who explicitly writes `guaranteed_fields: []` in YAML is expressing "I guarantee zero fields" which is semantically different from omitting `guaranteed_fields` entirely (which means "I haven't stated what I guarantee"). For observed schemas, this distinction could matter. The empty list is silently upgraded to `None` (unspecified), potentially masking a user's explicit choice to declare empty guarantees.

**Evidence:**
```python
if len(value) == 0:
    return None  # Empty list is treated as unspecified
```

### [330] Observed schema field validation is asymmetric

**What:** For `mode: observed`, the code checks `if fields_value is not None and isinstance(fields_value, list) and len(fields_value) > 0` to reject explicit field definitions. However, if `fields_value` is a non-list truthy value (e.g., a string or a number), the check silently passes because `isinstance(fields_value, list)` is False, meaning the invalid `fields` value is just ignored.

**Why it matters:** If a user accidentally writes `fields: true` or `fields: "auto"` under an observed schema, the invalid value is silently ignored instead of producing an error. This is a minor robustness gap -- the value is effectively swallowed.

**Evidence:**
```python
if fields_value is not None and isinstance(fields_value, list) and len(fields_value) > 0:
    raise ValueError(
        "Observed schemas (mode: observed) cannot have explicit field definitions. "
    )
# Non-list truthy values fall through silently here
```

## Observations

### [77-94] Excellent error messages in field parsing

The parse error diagnostics are a strength -- the code differentiates between "wrong type" and "wrong field name format" and even suggests corrections (e.g., replacing hyphens with underscores). This is the kind of user-facing validation that reduces support burden.

### [131-173] `_parse_field_names_list` has O(n^2) duplicate detection

The duplicate detection at line 170 uses `result.count(n)` inside a set comprehension, which is O(n^2). For field name lists this is inconsequential (typically <100 fields), but it is technically quadratic. A Counter-based approach would be O(n).

### [207-245] `_normalize_field_spec` handles YAML dict-vs-string ambiguity

Good defensive handling of the YAML parsing ambiguity where `- id: int` becomes `{"id": "int"}` while `- "id: int"` stays a string. Both paths are supported with clear error messages.

### [431-471] `get_effective_guaranteed_fields` and `get_effective_required_fields` are near-identical

These two methods have almost identical structure -- they both union explicit fields with declared required fields from the schema. This is minor duplication but is justified by their different semantic meanings (producer guarantee vs consumer requirement).

## Verdict

**Status:** SOUND
**Recommended action:** No immediate changes required. Consider tightening the empty-list handling in `_parse_field_names_list` and adding a guard for non-list `fields` values in observed mode. The Unicode field name acceptance is worth documenting as a known behavior.
**Confidence:** HIGH -- this is a pure parsing/validation module with no I/O, no concurrency, and no external dependencies. The logic is straightforward and well-tested based on the test file count.
