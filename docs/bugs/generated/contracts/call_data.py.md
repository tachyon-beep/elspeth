## Summary

`HTTPCallResponse` fails its deep-immutability and hash-stability contract for top-level JSON array responses: when an HTTP response body is a JSON list, the DTO keeps the mutable list by reference and `to_dict()` hands that same list back out.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `src/elspeth/contracts/call_data.py`
- Line(s): 240, 249-252, 264-269
- Function/Method: `HTTPCallResponse.__post_init__`, `HTTPCallResponse.to_dict`

## Evidence

`AuditedHTTPClient` can pass any valid JSON value into `HTTPCallResponse.body`:

- `src/elspeth/plugins/infrastructure/clients/http.py:165-182` parses `application/json` and returns `parsed` directly.
- JSON arrays are therefore valid production inputs here.

`HTTPCallResponse` only freezes mappings, not sequences:

```python
body: Mapping[str, Any] | str | None = None

if self.body is not None and isinstance(self.body, Mapping):
    frozen = deep_freeze(self.body)
    if frozen is not self.body:
        object.__setattr__(self, "body", frozen)
```

For a top-level JSON array like `[{"id": 1}]`, that `isinstance(..., Mapping)` check is false, so the mutable list is stored unchanged inside a `frozen=True` dataclass.

`to_dict()` then returns the same mutable object back out for non-mapping bodies:

```python
if isinstance(self.body, (MappingProxyType, dict)):
    d["body"] = deep_thaw(self.body)
else:
    d["body"] = self.body
```

So with a list body:

1. `HTTPCallResponse.body` remains mutable.
2. `HTTPCallResponse.to_dict()["body"]` aliases the DTO’s internal list.
3. Mutating the returned dict’s body mutates the supposedly immutable DTO.

This violates the file’s own contract at `src/elspeth/contracts/call_data.py:15-20`, which says all mutable containers are frozen in `__post_init__` and converted back only for wire-format stability.

There is test coverage for nested arrays inside dict bodies, but not for top-level array bodies:

- `tests/unit/plugins/clients/test_audited_http_client.py:1122-1152`
- `tests/unit/plugins/clients/test_audited_http_client.py:1340-1356`

Those tests never exercise the top-level-array case that `http.py` can produce.

## Root Cause Hypothesis

The DTO was implemented around the common HTTP cases of object JSON bodies and text bodies, and the immutability guard was narrowed to `Mapping` only. That misses another mutable JSON container shape that the HTTP client legitimately emits: top-level arrays.

## Suggested Fix

Make `HTTPCallResponse.body` accept all JSON body shapes and freeze any mutable container, not just mappings.

Example direction:

```python
body: Mapping[str, Any] | Sequence[Any] | str | int | float | bool | None = None

def __post_init__(self) -> None:
    require_int(self.status_code, "status_code", min_value=100)
    require_int(self.body_size, "body_size", optional=True, min_value=0)
    require_int(self.redirect_count, "redirect_count", min_value=0)
    if not isinstance(self.headers, MappingProxyType):
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
    if self.body is not None:
        frozen = deep_freeze(self.body)
        if frozen is not self.body:
            object.__setattr__(self, "body", frozen)

def to_dict(self) -> dict[str, Any]:
    d = {"status_code": self.status_code, "headers": dict(self.headers)}
    if self.body_size is not None:
        d["body_size"] = self.body_size
        d["body"] = deep_thaw(self.body)
    if self.redirect_count > 0:
        d["redirect_count"] = self.redirect_count
    return d
```

Add tests for:

- top-level JSON array body is frozen
- `to_dict()` returns a detached list copy
- mutating the returned list does not mutate `resp.body`

## Impact

HTTP calls returning top-level JSON arrays produce a DTO that is not actually immutable despite being part of the audit/telemetry payload path. That creates two risks:

- observability payloads can be mutated after construction, breaking the stated frozen-dataclass contract
- later serialization/hash calculations can drift if any code keeps and mutates the shared list reference

The current `AuditedHTTPClient` records immediately, so this is not a proven silent-drop or lineage-break today, but it is still a real contract violation in the target file on a valid production input shape.
