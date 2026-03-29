## Summary

`resolve_field_names()` does not re-validate `field_mapping` outputs, so it can emit non-identifier final field names and break the source-boundary guarantee that all downstream field names are valid Python identifiers.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py`
- Line(s): 237-263
- Function/Method: `resolve_field_names`

## Evidence

`resolve_field_names()` documents that source field names must end up as valid identifiers, and that headerless `columns` are only safe because they are “already clean identifiers validated at config time”:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py:207-215
Field normalization is mandatory for raw headers. Source field names are
normalized to valid Python identifiers at the source boundary. When
columns are provided (headerless mode), they are used as-is since they
are already clean identifiers validated at config time.
```

But after applying `field_mapping`, the function never validates the resulting names:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/field_normalization.py:237-263
if field_mapping:
    available = set(effective_headers)
    missing = set(field_mapping.keys()) - available
    if missing:
        raise ValueError(...)

    final_headers = [
        field_mapping[h] if h in field_mapping else h
        for h in effective_headers
    ]

    check_mapping_collisions(effective_headers, final_headers, field_mapping)
else:
    final_headers = effective_headers

resolution_mapping = dict(zip(original_names, final_headers, strict=True))
return FieldResolution(...)
```

That is not just theoretical. The Dataverse source accepts `field_mapping` but does not validate its values in config, then feeds them straight into this helper:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:107-110
field_mapping: dict[str, str] | None = Field(
    default=None,
    description="Manual field name overrides",
)
```

There is no `validate_field_names(...)` call in the Dataverse validators (`/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:122-170`), unlike the tabular-source config path, which does validate mapping values:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py:191-193
if self.field_mapping is not None and self.field_mapping:
    validate_field_names(list(self.field_mapping.values()), "field_mapping values")
```

The Dataverse source then uses the unresolved value as a row key:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:425-432
mapping = self._field_resolution.resolution_mapping
result: dict[str, Any] = {}
for k, v in row.items():
    normalized_name = mapping.get(k)
    if normalized_name is None:
        normalized_name = normalize_field_name(k)
    result[normalized_name] = v
```

Minimal repro in the repo environment:

```python
from tests.integration.plugins.test_dataverse_pipeline import _make_source_config
from elspeth.plugins.sources.dataverse import DataverseSource

source = DataverseSource(_make_source_config(field_mapping={"fullname": "Full Name"}))
print(source._normalize_row_fields({"fullname": "Alice"}, is_first_row=True))
# {'Full Name': 'Alice'}
```

That output violates the target module’s own contract that source-boundary names be valid Python identifiers.

There is also no test covering this invalid post-mapping case in `/home/john/elspeth/tests/unit/plugins/sources/test_field_normalization.py` or `/home/john/elspeth/tests/property/sources/test_field_normalization_properties.py`; both suites only exercise valid mapping values.

## Root Cause Hypothesis

The module assumes all callers validate `field_mapping` values before calling `resolve_field_names()`. That assumption is only true for tabular-source configs, not universally true across source plugins. Because `resolve_field_names()` is the shared contract boundary, trusting callers here lets one integration path (Dataverse) bypass the invariant and emit non-normalized field names into Tier 2 pipeline data.

## Suggested Fix

Enforce the invariant inside `resolve_field_names()` after `field_mapping` is applied, instead of relying on callers.

A good fix is:

1. Validate `final_headers` after mapping with the same identifier/keyword/duplicate rules used elsewhere.
2. Keep `check_mapping_collisions()` for good error messages about alias collisions.
3. Add a regression test showing that `field_mapping={"fullname": "Full Name"}` raises from `resolve_field_names()`, and ideally a Dataverse integration/config test too.

Sketch:

```python
from elspeth.core.identifiers import validate_field_names

...
if field_mapping:
    ...
    check_mapping_collisions(effective_headers, final_headers, field_mapping)

validate_field_names(final_headers, "resolved field names")
```

## Impact

Pipelines using Dataverse `field_mapping` can silently cross the source boundary with invalid field names like `"Full Name"` instead of normalized identifiers. That breaks the repository’s header-normalization contract, can make downstream template/attribute-style field access fail unpredictably, and records an audit field-resolution mapping for names that were never actually normalized at the boundary.
