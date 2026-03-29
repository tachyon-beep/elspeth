## Summary

`parse_json_strict()` silently accepts duplicate object keys, so external JSON like `{"a": 1, "a": 2}` is recorded and processed as `{"a": 2}` instead of being rejected at the Tier 3 boundary.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py
- Line(s): 59-68
- Function/Method: `parse_json_strict`

## Evidence

`parse_json_strict()` delegates straight to `json.loads(text)` and only post-validates for non-finite floats:

```python
try:
    parsed = json.loads(text)
except JSONDecodeError as e:
    return None, str(e)

if contains_non_finite(parsed):
    return None, "JSON contains non-finite values (NaN or Infinity)"

return parsed, None
```

Source: [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py:59](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py#L59)

That parser is the shared Tier 3 boundary for both main callers:

- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:165](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L165)
- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py:486](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py#L486)

The project rule at the external boundary is “validate at the boundary” and “record what we got,” especially for unexpected JSON structures:

- [/home/john/elspeth/CLAUDE.md:50](/home/john/elspeth/CLAUDE.md#L50)
- [/home/john/elspeth/CLAUDE.md:51](/home/john/elspeth/CLAUDE.md#L51)

But Python’s stdlib parser collapses duplicate keys before ELSPETH sees them. I verified locally in this workspace that:

```python
parse_json_strict('{"a": 1, "a": 2}') == ({"a": 2}, None)
```

So the first `a` is silently discarded. For `AuditedHTTPClient`, that mutated body is then persisted in the audited DTO path:

- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:339](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L339)
- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:345](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L345)

There is test coverage for NaN/Infinity and malformed JSON, but none for duplicate-key rejection:

- [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py:101](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py#L101)
- [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py:114](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py#L114)

## Root Cause Hypothesis

The helper treats `json.loads()` as a fully trustworthy structural validator, but stdlib JSON parsing is lossy for duplicate object keys. Because duplicate-key detection is not performed during parsing, malformed external payloads are normalized into valid-looking Tier 2 data, violating the boundary-validation rule.

## Suggested Fix

Parse objects with an `object_pairs_hook` that rejects repeated keys before constructing the dict. Keep the NaN/Infinity rejection, but make duplicate keys a parse error too.

Example shape:

```python
def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result

parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
```

Then convert that `ValueError` into the existing `(None, error_message)` failure path.

## Impact

External responses can lose data before audit recording or row extraction. The audit trail can then contain a confident but incomplete version of what the remote system sent, which breaks ELSPETH’s “record what we got” guarantee and can misroute downstream logic that depends on the overwritten field.
---
## Summary

`parse_json_strict()` can raise `RecursionError` on deeply nested JSON because `contains_non_finite()` walks the parsed structure recursively, causing malformed external payloads to escape the intended parse-failure path.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py
- Line(s): 21-41, 64-66
- Function/Method: `contains_non_finite`, `parse_json_strict`

## Evidence

The non-finite scan is fully recursive:

```python
if isinstance(obj, dict):
    return any(contains_non_finite(v) for v in obj.values())
if isinstance(obj, list):
    return any(contains_non_finite(v) for v in obj)
```

Source: [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py:37](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py#L37)

`parse_json_strict()` does not catch anything from that scan except the earlier `JSONDecodeError` from `json.loads()`:

```python
try:
    parsed = json.loads(text)
except JSONDecodeError as e:
    return None, str(e)

if contains_non_finite(parsed):
    return None, "JSON contains non-finite values (NaN or Infinity)"
```

Source: [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py:59](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/json_utils.py#L59)

I verified locally that a deeply nested but valid JSON array parses with `json.loads()`, then `parse_json_strict()` crashes with:

```python
RecursionError: maximum recursion depth exceeded
```

For the Dataverse path, that exception is especially bad because `_execute_request()` only wraps `httpx.*` errors; JSON parsing happens afterward with no generic conversion to `DataverseClientError`:

- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py:420](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py#L420)
- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py:486](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py#L486)

And the source only audits failures inside `except DataverseClientError`:

- [/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:686](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L686)

So a deep-nesting `RecursionError` can bypass the intended Dataverse error classification and miss the normal audited error-recording path entirely.

For `AuditedHTTPClient`, the generic `except Exception` does record an error, but it loses the intended parse-failure body context (`_json_parse_failed`, raw text preview) and treats a Tier 3 validation problem as an internal exception:

- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:377](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L377)
- [/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:382](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L382)

The current tests cover malformed JSON and NaN/Infinity, but not deep nesting:

- [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py:101](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py#L101)
- [/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py:125](/home/john/elspeth/tests/unit/plugins/infrastructure/clients/test_json_utils.py#L125)

## Root Cause Hypothesis

The helper validates after parsing by recursively traversing arbitrary attacker-controlled nesting depth. That makes the validator itself vulnerable to stack exhaustion, and because only `JSONDecodeError` is normalized into the tuple return contract, the recursion failure escapes as a raw exception.

## Suggested Fix

Make non-finite detection non-recursive or reject constants during parsing so no second full recursive walk is needed.

Safer options:

```python
def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"JSON contains non-finite value: {token}")

parsed = json.loads(text, parse_constant=_reject_non_finite)
```

If a post-parse walk is still needed, use an explicit stack/queue instead of recursion and catch `ValueError` from parser hooks in `parse_json_strict()` so all Tier 3 validation failures return `(None, error_message)`.

## Impact

A single deeply nested external response can escape the normal boundary-validation path. In Dataverse, that can bypass `DataverseClientError` classification and the source’s audited error-recording flow; in the generic HTTP client, it downgrades a parse failure into a generic exception path that loses the raw-body parse-failure context.
