## Summary

`repr_hash()` produces nondeterministic hashes for unordered containers, so malformed rows/error payloads can receive different fallback hashes and row IDs across processes.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/hashing.py`
- Line(s): 96-112
- Function/Method: `repr_hash`

## Evidence

`repr_hash()` is implemented as a raw SHA-256 of `repr(obj)`:

```python
def repr_hash(obj: Any) -> str:
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()
```

Source: `/home/john/elspeth/src/elspeth/contracts/hashing.py:96-112`

That is not stable for unordered containers. In this repo, `repr_hash()` is the documented fallback when canonical hashing fails, including for “other non-serializable types”:

- `/home/john/elspeth/src/elspeth/contracts/plugin_context.py:419-432`
- `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:306-316`
- `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1284-1299`
- `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1397-1407`
- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1867-1878`

Those call sites use the fallback hash for audit-visible fields such as `row_id`, `row_hash`, and quarantined-row telemetry `content_hash`.

I verified the instability directly by hashing the same value in fresh Python processes:

```text
bed4e7addc77803e431653009352d9b209bfce9750315367632bd052bb6df6fe
317a4667b69c92647f3339a0ef99af30285069b7885479821c79c46059f8af10
317a4667b69c92647f3339a0ef99af30285069b7885479821c79c46059f8af10
f867cf97998c3a35b291865feb29ae9500ab9f00ba70510ebd686104a37681aa
88e276fcbe8428adb327c514f1c85a6bc7bb9218f1ebdb61d707a60486a6990b
```

The only input was `{'s': {'aa', 'b', 'c'}}`; the variation comes from `repr(set(...))` order changing across interpreter processes.

What the code does:
- Hashes raw `repr(obj)`.

What it should do:
- Produce a deterministic fallback hash for non-canonical data, especially for built-in unordered containers that the file itself already treats as special cases (`frozenset` is explicitly rejected at `/home/john/elspeth/src/elspeth/contracts/hashing.py:44-47`).

## Root Cause Hypothesis

The fallback path assumes `repr()` is deterministic enough “within the same Python version,” but that assumption is false for unordered containers such as `set`/`frozenset`, whose printed element order depends on hash randomization and container layout. Because `repr_hash()` is the only contracts-layer fallback for non-canonical data, that nondeterminism leaks into audit identifiers whenever malformed external data or error details contain unordered values.

## Suggested Fix

Replace raw `repr(obj)` hashing with a deterministic fallback serializer for built-in container types before hashing. For example:

- Recursively normalize `Mapping` by sorted key order.
- Normalize `set`/`frozenset` to a sorted list of stable element representations.
- Normalize `list`/`tuple` recursively in order.
- Only use plain `repr()` for opaque scalar leaves that lack a better deterministic form.

A sketch:

```python
def _stable_fallback_repr(obj: Any) -> str:
    if isinstance(obj, Mapping):
        items = [(str(k), _stable_fallback_repr(v)) for k, v in obj.items()]
        return repr(sorted(items))
    if isinstance(obj, (list, tuple)):
        return repr([_stable_fallback_repr(v) for v in obj])
    if isinstance(obj, (set, frozenset)):
        return repr(sorted(_stable_fallback_repr(v) for v in obj))
    return repr(obj)

def repr_hash(obj: Any) -> str:
    return hashlib.sha256(_stable_fallback_repr(obj).encode("utf-8")).hexdigest()
```

Add a regression test that runs the same `repr_hash()` input in multiple subprocesses and asserts identical output for data containing `set`/`frozenset`.

## Impact

Audit fallback hashes become process-dependent for some malformed inputs. That can cause:

- The same quarantined row to get different `row_id` values when `record_validation_error()` falls back in `/home/john/elspeth/src/elspeth/contracts/plugin_context.py:419-432`.
- Different `row_hash` values for equivalent malformed payloads in validation/transform error records in `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1284-1299` and `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:1397-1407`.
- Different telemetry `content_hash` values for the same quarantined payload in `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1867-1878`.

That weakens reproducibility and cross-run correlation exactly in the “record what we saw” path meant to preserve auditability for malformed external data.
