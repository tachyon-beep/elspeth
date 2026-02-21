# Core DAG Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-dag/` (4 findings from static analysis)
**Source code reviewed:** `src/elspeth/core/dag/builder.py` (920 lines), `src/elspeth/core/dag/graph.py` (1456 lines)
**Subagent investigations:** 2 (post-freeze mutation search, branch trace failure analysis)

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | `P1-...-build-execution-graph-shares-mutable-schema-dicts-across-nodes.md` | P1 | **P2 downgrade** | Real aliasing, but exhaustive search confirms no post-construction mutation exists |
| 2 | `P1-...-get-effective-producer-schema-suppresses-graphvalidationerror...md` | P1 | **P1 confirmed** | Textbook "fails open" — suppresses Tier 1 graph construction bug, skips validation |
| 3 | `P2-...-executiongraph-get-schema-config-from-node-silently-treats-malformed...md` | P2 | **P2 confirmed** | Valid but low-risk — all schema values are builder-produced dicts in practice |
| 4 | `P2-...-field-required-coerces-non-bool-required-values...md` | P2 | **P3 downgrade** | Real `bool()` coercion violation, but input path never produces non-bool values |

## Detailed Assessment

### Finding 1: Mutable schema dicts shared across nodes — DOWNGRADED to P2

**Verdict: Real invariant violation, but latent — no active corruption. Downgraded P1 to P2.**

The aliasing is confirmed: `_best_schema_dict()` at `builder.py:160` returns the original
dict reference (not a copy) when `output_schema_config` is None. This gets assigned into
gate configs at lines 578 and 898, creating shared references. The freeze at lines 911-914
uses only top-level `MappingProxyType` — nested dicts/lists remain mutable.

**However, exhaustive subagent search (48 tool calls, all relevant subsystems) found:**

- **Zero** post-construction mutations of schema dicts
- All runtime access is read-only: `SchemaConfig.from_dict()` (parser), `canonical_json()` (serializer), `stable_hash()` (hasher)
- No `.append()`, `.update()`, `[key] = value`, or any other mutation pattern on nested schema objects
- 95% confidence (small gap for dynamic access patterns)

**Why P2, not P1:**
- The invariant IS broken (shallow freeze != deep freeze), but nothing exploits it
- No data corruption, no incorrect validation, no audit integrity violation
- This is a "broken lock on a door nobody opens" — fix is important for correctness but not urgent
- Future code changes could accidentally trigger it, but the MappingProxyType at least prevents the most obvious mutations

**Fix is still important:** Deep copy in `_best_schema_dict()` or recursive freeze
(dict → MappingProxyType, list → tuple) at construction end. Trivial, low-risk change.

### Finding 2: `GraphValidationError` suppression in `get_effective_producer_schema` — CONFIRMED P1

**Verdict: Textbook Tier 1 "fails open" violation. P1 confirmed.**

At `graph.py:1088-1092`:
```python
try:
    _first, last = self._trace_branch_endpoints(NodeID(node_id), select_branch)
    return self.get_effective_producer_schema(last)
except GraphValidationError:
    pass  # Fall through to None if trace fails
```

Subagent investigation (42 tool calls) confirmed:

1. **`_trace_branch_endpoints` can ONLY fail due to graph construction bugs** — the builder
   always creates either complete MOVE chains (transform branches) or COPY edges (identity
   branches). A trace failure means broken edge structure.

2. **No valid configuration produces an un-traceable branch chain.** The builder at
   `builder.py:390-609` guarantees the MOVE edge structure that `_trace_branch_endpoints` expects.

3. **No tests exercise the exception path.** The suppression is untested dead code that
   hides bugs.

4. **The suppressed error message itself says "this indicates a graph construction bug"**
   (`graph.py:746-750`) — and then the caller silences it.

**Impact chain:**
- `_trace_branch_endpoints` fails → `GraphValidationError` caught → returns `None`
- `None` producer schema → `_validate_single_edge` skips validation (`graph.py:1027`)
- Type mismatches pass through silently → runtime failures far from root cause

**Fix:** Remove the try/except block entirely. Let `GraphValidationError` propagate.
This is a one-line deletion.

### Finding 3: `get_schema_config_from_node` treats malformed schema as "no schema" — CONFIRMED P2

**Verdict: Valid analysis. P2 confirmed.**

At `graph.py:1320-1323`, a non-dict `schema` value falls through to `return None`,
which means "no schema" — silently disabling contract validation.

The correct behavior per Tier 1 trust model:
- `"schema"` key absent → return None (legitimate: not all nodes have schemas)
- `"schema"` key present, value is dict → parse it
- `"schema"` key present, value is NOT dict → crash (our data is malformed)

**Risk assessment:** Low. All schema values are builder-produced dicts. The non-dict path
can only be triggered by a bug in builder.py or manual node construction (tests only).
P2 is appropriate — correct to fix but not urgent.

**Fix:** Add `else: raise GraphValidationError(f"Node '{node_id}' has malformed schema config: expected dict, got {type(schema_dict).__name__}")`.

### Finding 4: `_field_required` coerces non-bool `required` values — DOWNGRADED to P3

**Verdict: Real `bool()` coercion violation, but unreachable in practice. Downgraded P2 to P3.**

At `builder.py:83`, `bool(field_spec["required"])` coerces non-bool values instead of
crashing. The report correctly shows that `'false'` → `True` and `'0'` → `True` (string
truthiness), which would produce incorrect merged field optionality.

**However, the input path never produces non-bool `required` values:**

- `SchemaConfig.to_dict()` always produces proper bools (Pydantic-validated)
- Plugin configs are Pydantic-validated before reaching the builder
- The builder's own coalesce schema construction (line 853) uses string format
  (`"name: type?"`) not dict format, so `_field_required` takes the string path instead

The `bool()` coercion violates CLAUDE.md's fail-fast principle for Tier 1 data, but no
realistic code path feeds non-bool values into it. P3 is appropriate — fix when convenient.

**Fix:** Replace `return bool(field_spec["required"])` with:
```python
val = field_spec["required"]
if type(val) is not bool:
    raise GraphValidationError(f"Schema field spec 'required' must be bool, got {type(val).__name__}: {val!r}")
return val
```

## Actions Taken

1. **Finding 1:** Downgraded from P1 → P2 (updated in bug file)
2. **Finding 2:** Confirmed P1, no changes needed (analysis is accurate)
3. **Finding 3:** Confirmed P2, no changes needed
4. **Finding 4:** Downgraded from P2 → P3 (updated in bug file)
