# XML Source Plugin Design

> **Status:** DRAFT
> **Date:** 2026-03-19
> **Author:** Claude (with John)

## Summary

Add an XML source plugin to ELSPETH that reads flat-record XML files and turns each record element into a pipeline row. Follows the same patterns as `CSVSource` and `JSONSource` — stdlib parsing, Tier 3 trust boundary handling, schema validation with coercion at the source boundary.

## Requirements

1. Read an XML file from a configured path
2. Extract repeating record elements by a configurable tag name
3. Convert each record's direct child elements and attributes into a flat row dict
4. Strip XML namespace prefixes from tag and attribute names
5. Validate rows against the configured schema (observed/fixed/flexible)
6. Quarantine invalid rows via `on_validation_failure` routing
7. Fail fast if `record_tag` matches zero elements (config error, not empty data)

## Non-Goals

- XPath-based record selection (deeply nested XML)
- Streaming/incremental parsing (`iterparse`)
- `lxml` or any third-party XML dependency
- Field normalization (`normalize_fields`, `columns`, `field_mapping`) — see **Known Limitation** below
- Namespace-aware queries (namespaces are stripped, not preserved)

### Known Limitation: Field Names

XML tag names are more constrained than CSV headers (no spaces, no parentheses), but can contain hyphens (`some-field`) and dots (`some.field`) which are not valid Python identifiers. This plugin does **not** normalize them. If your XML uses such names, configure a downstream `field_mapper` transform to rename fields.

This is consistent with `CSVSource`, where `normalize_fields` defaults to `False` — normalization is opt-in. A future enhancement could add `normalize_fields` support to this plugin by switching the config base class to `TabularSourceDataConfig`.

## Configuration

```yaml
source:
  plugin: xml
  options:
    path: data/input.xml
    record_tag: record          # Required: repeating element tag name
    encoding: utf-8             # Optional, default: utf-8
    schema:
      mode: observed            # or fixed/flexible
    on_validation_failure: quarantine_sink  # Required: sink name or "discard"
```

### Config Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | `str` | Yes | — | Path to XML file (via `PathConfig`) |
| `record_tag` | `str` | Yes | — | Tag name of repeating record elements |
| `encoding` | `str` | No | `utf-8` | File encoding |
| `schema` | `dict` | Yes | — | Schema configuration (via `DataPluginConfig`) |
| `on_validation_failure` | `str` | Yes | — | Quarantine routing (via `SourceDataConfig`) |

## Row Extraction

Given this XML:

```xml
<records>
  <record id="1" status="active">
    <name>Alice</name>
    <amount>42.50</amount>
    <notes/>
  </record>
</records>
```

With `record_tag: record`, the extracted row is:

```python
{"id": "1", "status": "active", "name": "Alice", "amount": "42.50", "notes": None}
```

Attribute-only records are also valid:

```xml
<record id="1" status="active"/>
```

Produces: `{"id": "1", "status": "active"}`

### Extraction Rules

1. **Attributes** become fields: `id="1"` → `{"id": "1"}`
2. **Direct child elements** become fields from text content: `<name>Alice</name>` → `{"name": "Alice"}`
3. **Empty/self-closing elements** → `None`: `<notes/>` → `{"notes": None}`. Whitespace-only text is also treated as absent: `<notes>  </notes>` → `{"notes": None}`. Policy: `(element.text or "").strip() or None`
4. **Name collision** (attribute and child element share a name): child element wins (closer to data body)
5. **Namespace prefixes** stripped from both element tags and attribute names: `{http://example.com}name` → `name`
6. **All values are strings** (or `None` for empty elements) — schema coercion handles type conversion, consistent with CSV source behavior
7. **Grandchild elements are ignored** — only direct children of the record element are extracted. Nested structures like `<address><street>...</street></address>` produce `{"address": None}` (the `<address>` element's own text is `None` because its content is child elements, not text)

### Namespace Stripping

ElementTree represents namespaced tags as `{uri}localname`. Stripping extracts the local name:

```python
def _strip_namespace(tag: str) -> str:
    """Strip namespace URI from an ElementTree tag or attribute name.

    ElementTree expands namespace prefixes to {uri}localname form.
    QName-style attributes (e.g., xsi:type) that ElementTree does
    not expand are returned as-is (the colon remains).
    """
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag
```

Applied to both element tags and attribute keys. For QName-style attributes like `xsi:type` that ElementTree does not expand to `{uri}` form, the name is left as-is (including the colon).

## Class Structure

### `XMLSourceConfig(SourceDataConfig)`

Extends `SourceDataConfig` directly (not `TabularSourceDataConfig`) because field normalization is a non-goal for this plugin — see **Known Limitation** above. `SourceDataConfig` provides `path` (via `PathConfig`), `schema` (via `DataPluginConfig`), and `on_validation_failure`:

- `record_tag: str` — required, validated non-empty
- `encoding: str` — default `"utf-8"`, validated via `codecs.lookup()`

### `XMLSource(BaseSource)`

- `name = "xml"`
- `plugin_version = "1.0.0"`
- `determinism = Determinism.IO_READ` (inherited default)

#### `__init__(config)`

1. Parse config via `XMLSourceConfig.from_dict(config)`
2. Store `_path`, `_record_tag`, `_encoding`, `_schema_config`, `_on_validation_failure`
3. Create schema class with `create_schema_from_config(allow_coercion=True)` (source boundary)
4. Set `self.output_schema = self._schema_class` (protocol compliance)
5. Set up schema contract:
   - Create initial contract via `create_contract_from_config(self._schema_config)`
   - **FIXED schemas**: contract is already locked → call `self.set_schema_contract(initial_contract)`, set `self._contract_builder = None`
   - **OBSERVED/FLEXIBLE schemas**: create `ContractBuilder(initial_contract)` → contract set after first valid row in `load()`

#### `load(ctx) -> Iterator[SourceRow]`

1. Check file exists → `FileNotFoundError` if not
2. Parse XML via `ET.parse(path)`:
   - Catch `ET.ParseError`: call `ctx.record_validation_error(row={"file_path": str(self._path)}, error=..., schema_mode="parse", destination=self._on_validation_failure)`. If `on_validation_failure != "discard"`: yield `SourceRow.quarantined(...)`. Return (stop processing).
   - Catch `UnicodeDecodeError`: same pattern as `ET.ParseError` above.
3. Get root, find all direct children whose namespace-stripped tag matches `record_tag`. The configured `record_tag` is a bare local name (`record`, not `{http://example.com}record`).
4. If zero matches → raise `PluginConfigError` (fail fast — config mistake, not data issue)
5. Track `first_valid_row_processed = False`
6. For each record element:
   a. Extract attributes dict (namespace-stripped keys)
   b. Extract direct child elements: namespace-stripped tag → `(element.text or "").strip() or None`
   c. Merge: start with attributes, update with child elements (child wins on collision)
   d. Attempt schema validation: `self._schema_class.model_validate(row)` → `validated.to_row()`
      - **On `ValidationError`**: call `ctx.record_validation_error(...)`. If `on_validation_failure != "discard"`: yield `SourceRow.quarantined(...)`. **Continue** to next record (skip steps e–g).
   e. On first valid row (when `_contract_builder is not None` and `not first_valid_row_processed`):
      - Identity field resolution: `{k: k for k in validated_row}`
      - Call `self._contract_builder.process_first_row(validated_row, field_resolution)`
      - Call `self.set_schema_contract(self._contract_builder.contract)`
      - Set `first_valid_row_processed = True`
   f. Validate against locked contract (type drift check) — on violation: quarantine and **continue** to next record
   g. Yield `SourceRow.valid(validated_row, contract=contract)`
7. After all records: if `not first_valid_row_processed` and `_contract_builder is not None`:
   - Call `self.set_schema_contract(self._contract_builder.contract.with_locked())`

#### `close()`

No-op (file is fully parsed in `load()`).

## Error Handling

Per the Three-Tier Trust Model. File-level parse errors follow the two-step audit pattern from `JSONSource`: always call `ctx.record_validation_error()` (audit trail), then conditionally yield `SourceRow.quarantined()` (routing). The `"discard"` path still records the error — it just doesn't yield a quarantined row.

| Failure | Tier | Response | Rationale |
|---------|------|----------|-----------|
| File not found | — | `FileNotFoundError` (crash) | Same as CSV/JSON sources |
| XML parse error (`ET.ParseError`) | Tier 3 | `ctx.record_validation_error()` + quarantine if not discard, stop | Malformed external data |
| Encoding error (`UnicodeDecodeError`) | Tier 3 | `ctx.record_validation_error()` + quarantine if not discard, stop | External file encoding issue |
| Zero `record_tag` matches | — | `PluginConfigError` (crash) | Config mistake — fail fast before processing |
| Row fails schema validation | Tier 3 | `ctx.record_validation_error()` + `SourceRow.quarantined()` | Normal source validation |
| Row fails contract validation (type drift) | Tier 3 | `ctx.record_validation_error()` + `SourceRow.quarantined()` | Inferred type mismatch |

## File Location

`src/elspeth/plugins/sources/xml_source.py`

Auto-discovered by `discover_plugins_in_directory()` scanning `plugins/sources/*.py` for `BaseSource` subclasses. No registration code needed.

## Dependencies

None — uses `xml.etree.ElementTree` from the Python standard library.

## Testing Strategy

Unit tests in `tests/unit/plugins/sources/test_xml_source.py`:

1. **Happy path**: flat records → correct row dicts
2. **Attributes only**: record with only attributes, no child elements
3. **Attributes + children**: both extracted as fields
4. **Empty elements**: self-closing, empty, and whitespace-only elements → `None`
5. **Name collision**: attribute and child element with same name → child wins
6. **Grandchild elements**: nested child element (`<address><street>...</street></address>`) ignored, parent key present with value `None`
7. **Namespace stripping**: namespaced tags/attributes → local names only
8. **QName attributes**: `xsi:type`-style attributes preserved as-is
9. **Schema validation**: fixed schema rejects extra fields, observed accepts all
10. **Quarantine routing**: invalid rows routed to `on_validation_failure` destination
11. **Quarantine discard**: `on_validation_failure="discard"` still calls `ctx.record_validation_error()` but yields nothing
12. **Contract locking (FIXED)**: contract locked at init, no builder needed
13. **Contract locking (OBSERVED)**: first valid row locks contract, type drift quarantined
14. **Config errors**: missing `record_tag`, empty `record_tag`, bad encoding
15. **Parse errors (quarantine)**: malformed XML → audit error + quarantine + stop
16. **Parse errors (discard)**: malformed XML with discard → audit error + stop, no yield
17. **Zero matches**: valid XML but wrong `record_tag` → `PluginConfigError`
18. **File not found**: raises `FileNotFoundError`
19. **Encoding errors**: non-UTF-8 file with wrong encoding config → quarantine
20. **All rows invalid**: contract locked via `with_locked()` fallback
