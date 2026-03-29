## Summary

JSON and JSONL modes can upload non-standard payloads containing `NaN`/`Infinity` instead of failing fast, so the sink can persist invalid JSON while still recording a successful artifact hash.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py
- Line(s): 523-530, 535-579
- Function/Method: `_serialize_json`, `_serialize_jsonl`, `write`

## Evidence

`_serialize_json()` and `_serialize_jsonl()` call Python’s permissive JSON serializer without `allow_nan=False`:

```python
def _serialize_json(self, rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, indent=2).encode("utf-8")

def _serialize_jsonl(self, rows: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(row) for row in rows]
    return "\n".join(lines).encode("utf-8")
```

That serializer emits `NaN`/`Infinity` tokens by default instead of raising. I verified it locally against this sink: writing `{"value": float("nan")}` in `format="json"` uploaded:

```json
[
  {
    "value": NaN
  }
]
```

and still returned a normal artifact hash.

This conflicts with the repo’s documented non-finite policy:
- `CLAUDE.md` says “NaN and Infinity are strictly rejected, not silently converted.”
- [/home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py#L24](/home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py#L24) defines `FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]`.
- [/home/john/elspeth/tests/property/sinks/test_json_sink_properties.py#L22](/home/john/elspeth/tests/property/sinks/test_json_sink_properties.py#L22) only generates finite floats for JSON sink properties, so this edge case is currently untested.

The sink also does not expose the executor’s optional strict input-validation switch that neighboring sinks use:
- Azure config has no `validate_input` field in [/home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py#L78](/home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py#L78)
- `__init__` never sets `self.validate_input` in [/home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py#L308](/home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py#L308)

So there is no sink-local defense before permissive serialization runs.

## Root Cause Hypothesis

The sink assumes upstream rows are already clean Tier 2 data, but JSON serialization is one of the places where type-valid values can still be operation-invalid. Non-finite floats are a concrete example: they pass as Python floats, yet produce invalid JSON unless explicitly rejected. Because this sink uses default `json.dumps()` behavior and has no configurable input-validation path, it fails open instead of crashing.

## Suggested Fix

Reject non-finite JSON at serialization time, even if upstream validation was skipped. For example:

```python
def _serialize_json(self, rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, indent=2, allow_nan=False).encode("utf-8")

def _serialize_jsonl(self, rows: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(row, allow_nan=False) for row in rows]
    return "\n".join(lines).encode("utf-8")
```

Also add `validate_input: bool = False` to `AzureBlobSinkConfig` and wire `self.validate_input = cfg.validate_input` in `__init__`, matching the CSV/JSON/database sinks.

## Impact

Blob outputs advertised as JSON/JSONL can contain invalid JSON while the audit trail records a successful write and stable hash for that invalid payload. Downstream consumers may reject the blob, and operators get a “successful sink write” record even though the external artifact violates ELSPETH’s non-finite-value policy.
---
## Summary

`close()` leaks Azure SDK resources by nulling the cached client reference without calling the client’s `close()` method.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/azure_blob_sink.py
- Line(s): 363-381, 696-701
- Function/Method: `_get_container_client`, `close`

## Evidence

The sink lazily creates and caches a `ContainerClient`:

```python
if self._container_client is None:
    service_client = self._auth_config.create_blob_service_client()
    self._container_client = service_client.get_container_client(self._container)
```

But `close()` only drops references:

```python
def close(self) -> None:
    self._container_client = None
    self._buffered_rows = []
    self._resolved_blob_path = None
    self._has_uploaded = False
```

It never calls `self._container_client.close()`. I verified locally that:
- `azure.storage.blob.ContainerClient` does have a `close()` method
- assigning a mock client to `_container_client` and calling `sink.close()` leaves `mock.close()` uncalled

This violates the base sink lifecycle contract in [/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py#L523](/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py#L523), which defines `close()` as the place to “Release resources (file handles, connections).”

## Root Cause Hypothesis

The implementation treats Azure clients as disposable references rather than owned resources. Because `_get_container_client()` stores only the derived `ContainerClient` and discards the `BlobServiceClient`, teardown was reduced to clearing Python attributes instead of actually closing the SDK objects.

## Suggested Fix

Call `close()` on the cached Azure client during teardown, and keep/close any parent service client if needed:

```python
def close(self) -> None:
    if self._container_client is not None:
        self._container_client.close()
    self._container_client = None
    self._buffered_rows = []
    self._resolved_blob_path = None
    self._has_uploaded = False
```

If the service client owns the underlying transport session, store it on the instance and close it too.

## Impact

In long-running processes or repeated plugin instantiation, HTTP sessions and related Azure SDK resources can accumulate instead of being released at sink shutdown. That is a lifecycle/resource-management bug in the target file, and it undermines the `BaseSink.close()` contract.
