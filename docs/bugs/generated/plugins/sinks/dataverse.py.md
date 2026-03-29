## Summary

Dataverse sink records and hashes the pre-mapped pipeline rows instead of the actual PATCH requests, so the audit trail cannot prove what JSON body was sent to Dataverse.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py
- Line(s): 343-346, 372-374, 385-390, 418-421
- Function/Method: `write`

## Evidence

`write()` computes the artifact hash before it builds the outbound Dataverse payloads:

```python
# src/elspeth/plugins/sinks/dataverse.py:343-346
canonical_payload = canonical_json(rows).encode("utf-8")
content_hash = hashlib.sha256(canonical_payload).hexdigest()
```

But the actual HTTP body is produced later by `_map_row()` and can differ materially from `rows`:

```python
# src/elspeth/plugins/sinks/dataverse.py:372-374
url = self._build_upsert_url(key_value)
payload = self._map_row(row)
prepared.append((url, payload))
```

That mapped payload is not what gets persisted in the call record. The success path records only method/url/headers/field names:

```python
# src/elspeth/plugins/sinks/dataverse.py:385-390
request_data = {
    "method": "PATCH",
    "url": url,
    "headers": fingerprint_headers(response.request_headers),
    "field_names": sorted(payload.keys()),
}
```

The error path drops even more detail and still omits the JSON body:

```python
# src/elspeth/plugins/sinks/dataverse.py:418-421
request_data = {
    "method": "PATCH",
    "url": url,
    "field_names": sorted(payload.keys()),
}
```

Landscape persists exactly `request_data`; it does not magically recover the missing body later:

```python
# src/elspeth/core/landscape/execution_repository.py:534-548
request_dict = request_data.to_dict()
request_hash = stable_hash(request_dict)
if request_ref is None and self._payload_store is not None:
    request_bytes = canonical_json(request_dict).encode("utf-8")
    request_ref = self._payload_store.store(request_bytes)
```

This is a real mismatch for Dataverse because `_map_row()` renames fields, emits `@odata.bind` entries for lookups, and omits `None` lookup values:

```python
# src/elspeth/plugins/sinks/dataverse.py:303-311
if self._lookups and pipeline_field in self._lookups:
    bind_key = f"{lookup.target_field}@odata.bind"
    payload[bind_key] = f"/{lookup.target_entity}({value})"
else:
    payload[dataverse_column] = value
```

So the stored `content_hash` and request payload blobs describe the input rows, not the actual Dataverse request bodies.

## Root Cause Hypothesis

The sink treats `rows` as a sufficient proxy for the outbound write, but Dataverse writes have a second serialization/mapping step inside the sink itself. Once field renaming, lookup binding, and omission rules were added, hashing and auditing the pre-mapped rows became incorrect.

## Suggested Fix

Hash and record the actual outbound requests, not the raw pipeline rows.

A safe shape would be to build `prepared` first, then hash a canonical structure such as:

```python
requests_for_audit = [{"method": "PATCH", "url": url, "json": payload} for url, payload in prepared]
```

Use that structure for:

- `content_hash`
- success `request_data`
- error `request_data`

Include fingerprinted headers where available, but keep the JSON body in the recorded request payload so `calls.request_ref` contains the real Dataverse body.

## Impact

Auditability is weakened in exactly the place ELSPETH is supposed to be strongest: the system cannot prove the exact Dataverse mutation that occurred. Lookup writes, renamed columns, and omitted `None` bindings are especially affected. The artifact hash is also misleading, because it hashes something different from what the sink actually sent.
---
## Summary

`field_mapping` and lookup targets can collide silently, causing one source field to overwrite another in the outbound Dataverse payload with no validation error.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py
- Line(s): 80-95, 103-135, 298-311
- Function/Method: `DataverseSinkConfig`, `_map_row`

## Evidence

The config model accepts arbitrary `field_mapping` and `lookups`, but the only validators here check HTTPS and non-empty strings:

```python
# src/elspeth/plugins/sinks/dataverse.py:80-95
field_mapping: dict[str, str] = Field(...)
lookups: dict[str, LookupConfig] | None = Field(default=None, ...)
```

```python
# src/elspeth/plugins/sinks/dataverse.py:103-135
@field_validator("environment_url") ...
@field_validator("additional_domains") ...
@field_validator("entity") ...
@field_validator("alternate_key") ...
```

There is no validation that two pipeline fields do not map to the same Dataverse column, and no validation that two lookup bindings do not target the same `target_field`.

At runtime, `_map_row()` writes into a plain dict, so later entries overwrite earlier ones silently:

```python
# src/elspeth/plugins/sinks/dataverse.py:307-311
bind_key = f"{lookup.target_field}@odata.bind"
payload[bind_key] = f"/{lookup.target_entity}({value})"
...
payload[dataverse_column] = value
```

Example failure modes:

- `field_mapping={"legal_name": "fullname", "display_name": "fullname"}`: one value disappears.
- Two lookup fields with the same `target_field`: one `...@odata.bind` overwrites the other.
- A normal mapped column and a lookup bind aimed at the same Dataverse semantic field can produce contradictory payload construction with last-write-wins behavior.

Because this happens during payload construction, the sink sends a valid-looking PATCH body while silently dropping data.

## Root Cause Hypothesis

The config model validates presence but not uniqueness/consistency. The implementation then uses a mutable dict for payload assembly without collision checks, so conflicting mappings degrade into silent overwrite instead of a configuration error.

## Suggested Fix

Reject collisions during config validation, and keep a runtime assertion in `_map_row()` as a backstop.

Specifically validate that:

- `field_mapping` values are unique
- lookup `target_field` values are unique
- lookup bind keys do not conflict with any other generated outbound key

If a collision is detected, raise `PluginConfigError` with the conflicting source fields and Dataverse target key.

## Impact

This is silent data loss at the sink boundary. A row can be written with the wrong field value, or with one field entirely missing, while the pipeline still reports success. That breaks audit trust because the recorded success no longer guarantees that all configured input fields were actually represented in the Dataverse write.
