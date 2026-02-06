# Analysis: src/elspeth/core/canonical.py

**Lines:** 277
**Role:** Two-phase deterministic JSON canonicalization for audit hash integrity. Phase 1 normalizes pandas/numpy types to JSON-safe primitives. Phase 2 serializes via `rfc8785` (RFC 8785/JCS standard). Provides `stable_hash()` for audit records, `compute_full_topology_hash()` for DAG checkpoint validation, and `repr_hash()` as a fallback for non-canonical data (quarantined rows).
**Key dependencies:** `rfc8785`, `numpy`, `pandas`, `networkx`, `hashlib`; imported by `schema_contract.py` (version_hash), `plugins/llm/templates.py` (prompt hashing), `engine/` modules (row hashing), `checkpoint/` (topology hashing)
**Analysis depth:** FULL

## Summary

This file is well-engineered for its core purpose. The NaN/Infinity rejection policy is correctly implemented, the two-phase approach cleanly separates concerns, and the bool-before-int ordering in `_normalize_value` is correct (bool is checked via `str | int | bool` on line 67, before the `np.integer` check on line 71, preventing `True` from being silently cast to `1`). However, there is one critical finding related to non-atomic write concerns in callers, one warning about unhandled types silently passing through to `rfc8785`, and a few observations worth noting.

## Critical Findings

### [116] Unhandled types fall through silently

**What:** `_normalize_value()` returns `obj` unchanged (line 116) for any type not explicitly handled. This means if a `set`, `frozenset`, `Decimal` subclass, `UUID`, `Path`, `Enum`, or any custom object reaches this function, it passes through to `rfc8785.dumps()` which will raise a `TypeError` -- but the error message will be from `rfc8785`, not from ELSPETH, making root cause analysis harder.

**Why it matters:** The docstring says "Returns: JSON-serializable primitive" and "Raises: ValueError: If value contains NaN or Infinity" -- implying that if no ValueError is raised, the return is JSON-safe. But for an unhandled type, the return is NOT JSON-safe. The `rfc8785.dumps()` call on line 166 will then fail with a cryptic `TypeError` from the third-party library. For an audit-critical system, the error should be caught and reported with ELSPETH context (which value, which type, where in the data structure).

**Evidence:**
```python
# Line 116 - silent passthrough
return obj

# Line 166 - will fail with rfc8785 TypeError
result: bytes = rfc8785.dumps(normalized)
```

If a pipeline row contains a `uuid.UUID` or `pathlib.Path` value (plausible from external sources or plugin bugs), the error trace will point to `rfc8785.dumps`, not to the normalization layer where the problem should be caught. This is not data corruption (it fails loudly), but it violates the principle of clear error attribution in an audit system.

**Severity assessment:** This is on the boundary between Critical and Warning. It cannot cause silent data corruption (it always crashes), but it can cause confusion during incident response. Elevating to Critical because for an audit system, "I don't know what happened" is the worst outcome, and a confusing stack trace during an incident approaches that.

## Warnings

### [92-96] Naive Timestamp UTC assumption is an implicit contract

**What:** Line 93-95: Naive `pd.Timestamp` objects (no timezone) are assumed to be UTC and localized accordingly. This is documented in a comment ("Naive timestamps assumed UTC (explicit policy)") but is only enforced at canonicalization time, not at source ingestion.

**Why it matters:** If a source plugin produces a naive timestamp that is actually in local time (e.g., from a CSV with no timezone column), the canonical hash will be computed assuming UTC. When the same data is re-processed on a server in a different timezone, the hash will be identical (good) but the semantic meaning may be wrong. Since this is canonicalization (not interpretation), the current behavior is defensible -- but the policy should be enforced or documented at the source layer, not just here.

**Evidence:**
```python
if obj.tz is None:
    return obj.tz_localize("UTC").isoformat()
```

### [75-88] NumPy array NaN check uses try/except TypeError for non-numeric dtypes

**What:** The NaN/Infinity check for numpy arrays catches `TypeError` from `np.isnan`/`np.isinf` on non-numeric dtypes (e.g., string arrays). The `pass` on line 88 means non-numeric arrays skip the NaN check entirely.

**Why it matters:** This is correct behavior -- string arrays cannot contain NaN. However, object-dtype arrays CAN contain a mix of types including `float('nan')`, and `np.isnan()` on an object array will raise `TypeError` for non-float elements, potentially skipping the check even when NaN values are present in the array. For example: `np.array([1.0, "text", float('nan')], dtype=object)` would raise `TypeError` on the string element, and the NaN at index 2 would slip through.

**Evidence:**
```python
try:
    if np.any(np.isnan(obj)) or np.any(np.isinf(obj)):
        raise ValueError(...)
except TypeError:
    pass  # Non-numeric arrays skip check
```

The subsequent `obj.tolist()` + `_normalize_value(x)` recursive call on line 89 WOULD catch the NaN in the individual float element, so this is not a data corruption risk -- the NaN will be caught when the individual float is processed. However, the error message would be about a scalar float, not the array, which could be confusing.

### [89] Large numpy arrays cause deep recursion and O(n) memory

**What:** `[_normalize_value(x) for x in obj.tolist()]` creates a full Python list copy of the numpy array. For very large arrays (millions of elements), this doubles memory usage and creates deep call stacks.

**Why it matters:** In typical pipeline use, row data is unlikely to contain million-element arrays. But if a source plugin loads a large binary blob or matrix as a numpy array, this could cause OOM. This is a latent issue unlikely to manifest with current usage patterns.

## Observations

### [99] pd.NaT check uses isinstance + identity

**What:** `isinstance(obj, type(pd.NaT)) and obj is pd.NaT` is used to check for NaT. This is correct and necessary because `pd.NaT` has a unique type (`NaTType`) that is not publicly exported, and `isinstance(obj, pd.NaT)` would fail.

### [67] Bool ordering is correct

**What:** `isinstance(obj, str | int | bool)` on line 67 correctly handles the `bool` subclass-of-`int` issue. Since `True` and `False` are both `bool` AND `int`, this check catches them first. The `np.integer` check on line 71 would otherwise convert `True` to `1`.

### [254-277] repr_hash is correctly scoped as fallback

**What:** `repr_hash()` is documented as non-deterministic across Python versions and only appropriate for quarantined (Tier 3) data. This is a clean design decision.

### [184-219] compute_full_topology_hash sorts deterministically

**What:** Both nodes and edges are sorted before hashing, ensuring topological hash stability regardless of graph traversal order. The `config_hash` uses `stable_hash` recursively, which correctly handles nested structures.

### [242-251] Edge data access is Tier 1 (crash on missing)

**What:** `edge_data["label"]` and `edge_data["mode"].value` on lines 249-250 use direct access without `.get()`, which is correct per CLAUDE.md Tier 1 rules -- this is our data and missing attributes indicate a bug in `ExecutionGraph.add_edge()`.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Address the unhandled type passthrough on line 116 by raising an explicit `TypeError` with ELSPETH context for types that cannot be normalized, rather than silently passing them to `rfc8785.dumps()`. The numpy object-array edge case is a minor concern that could be documented but is mitigated by recursive element processing.
**Confidence:** HIGH -- The file is straightforward, all code paths are readable, and the dependencies are well-understood. The findings are based on explicit code paths, not speculation.
