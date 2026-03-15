# Round 5 — Final Dissent and Commitment: Pyre (Python AST Engineer)

## Commitment: I Can Build This

I commit to implementing the decided design: 5 provenance labels × 2 validation states, 7 effective states, 49-cell rule matrix, SARIF 2.1.0 output, 4-tier exit codes, 4-class governance exceptionability.

My TIER_1/TIER_2 collapse was the wrong call. The scribe's assessment is fair — my Round 4 matrix only covered 4 rules, and I missed the cells where the tiers genuinely diverge (R4 broad `except`: ERROR vs WARN; R7 `isinstance`: ERROR vs WARN). The 5-label model earns its keep on those two rules. I was optimising for implementation simplicity at the cost of semantic precision, which is exactly the mistake the tool is designed to catch in others.

## Minority Report: The INTERNAL Alias Should Exist in the API

I accept the 5-label taint engine. I register one minority position: the public API (decorator names, manifest entries, diagnostic messages) should offer `@internal_data` as an alias that resolves to TIER_2 at parse time. Not as a distinct provenance — as syntactic sugar for the common case where a developer knows data is "ours" but hasn't determined which tier.

**Rationale:** TIER_2 is the default for undeclared internal data (Sable's proposal, Round 4). Most developers writing transforms will never need TIER_1. Forcing them to choose between `@tier2_data` and `@audit_data` when they mean "this isn't external" creates friction that pushes toward UNKNOWN (no annotation at all). An `@internal_data` decorator that maps to TIER_2 captures the intent without the cognitive load.

This is a UX convenience, not a semantic objection. I can live without it. I flag it because Iris's developer experience arguments were the most compelling in the entire roundtable, and this is the same argument applied to the declaration surface.

## AST Edge Cases the Roundtable Hasn't Considered

These are implementation concerns, not design objections. The design is sound. These are the places where stdlib `ast` will fight us.

### 1. Walrus Operator in Comprehensions (`:=` Scoping)

```python
# The walrus operator leaks into enclosing scope — but comprehension
# variables don't. Taint propagation must handle this asymmetry.

result = [
    y
    for x in external_data          # x is TIER_3 — scoped to comprehension
    if (validated := validate(x))   # validated is TIER_3+S_V — leaks to ENCLOSING scope
    for y in validated.items()      # y is TIER_3+S_V — scoped to comprehension
]
# Here: `validated` is accessible and TIER_3+S_V (correct)
# But: `x` and `y` are NOT accessible (comprehension-scoped)
```

The `ast.NamedExpr` node appears inside `ast.ListComp` generators, but the variable it binds escapes to the enclosing function scope. The taint engine must treat `:=` targets differently from comprehension iteration variables (`ast.comprehension.target`). If we get this wrong, `validated` either loses its taint (false negative) or comprehension-scoped variables pollute the enclosing `TaintMap` (false positives on subsequent same-named variables).

**Mitigation:** The `TaintMap` needs scope-awareness for comprehensions. Comprehension iteration variables get a shadow scope; walrus targets write directly to the enclosing scope. This is ~20 lines of scope management, not a design change.

### 2. Decorator Detection on Methods vs. Functions

```python
class MyTransform:
    @external_boundary          # Decorates the method
    def fetch(self) -> dict:
        return requests.get(url).json()

    def process(self, row):
        data = self.fetch()     # Is this TIER_3?
```

The `ast` module sees `self.fetch()` as `ast.Attribute(value=ast.Name(id='self'), attr='fetch')`. Linking this call back to the `@external_boundary` decorator on `MyTransform.fetch` requires:

1. Resolving `self` to the enclosing class (straightforward — we're inside `MyTransform`)
2. Finding `fetch` in that class's method list (straightforward — `ast.ClassDef.body`)
3. Checking its decorators (straightforward — `ast.FunctionDef.decorator_list`)

This works for `self.method()`. It breaks for:

- **Aliased self:** `s = self; s.fetch()` — `s` is not syntactically `self`. The taint engine would need to propagate the "is-self" identity through assignments.
- **Passed-in instances:** `other_transform.fetch()` — requires cross-class resolution, which is inter-procedural analysis (out of scope for v0.1).
- **Inherited methods:** `super().fetch()` or methods defined in a parent class — `ast` doesn't resolve inheritance.

**Mitigation:** For v0.1, restrict `self.method()` resolution to direct `self` references (not aliased). Document the limitation. Aliased self is rare in ELSPETH's codebase (I checked — zero instances). Inherited decorated methods can be handled in v0.2 by scanning the class hierarchy within a single file.

### 3. Unpacking Assignments and MIXED Propagation

```python
# Tuple unpacking from a MIXED container
audit_val, external_val = combined_dict["audit"], combined_dict["external"]
```

If `combined_dict` is MIXED, what provenance do `audit_val` and `external_val` get? The AST sees `ast.Assign` with `ast.Tuple` target. The tool cannot know which element came from which tier — the string keys `"audit"` and `"external"` are semantically meaningful to humans but opaque to the AST (they're just `ast.Constant` nodes).

**More insidious — starred unpacking:**

```python
first, *rest = mixed_list  # first: MIXED? rest: MIXED? Both?
```

**The honest answer:** All unpacked variables from a MIXED container inherit MIXED. This is conservative (may produce false positives) but sound (never produces false negatives). The alternative — trying to resolve which dict key maps to which tier — requires type-level reasoning that stdlib `ast` cannot provide.

**Mitigation:** MIXED propagates through unpacking. The developer action is the same as the roundtable decided: decompose the container. The finding message should say "unpacked from MIXED container at line N — consider separating access paths by tier."

### 4. f-string Interpolation as Implicit `.format()`

```python
# f-strings don't appear as method calls in the AST
query = f"SELECT * FROM {table_name}"  # table_name is TIER_3
```

`ast.JoinedStr` contains `ast.FormattedValue` nodes. If `table_name` is TIER_3, the resulting `query` string should be MIXED (literal string + external data). But the current design focuses on `.get()`, `hasattr()`, broad `except`, and audit write paths — none of which directly involve f-string construction.

**This matters for future rules** (SQL injection, prompt injection) but not for the v0.1 rule set. The taint engine should propagate through f-strings anyway — it's cheap to implement (walk `ast.JoinedStr.values`, propagate MIXED if any `FormattedValue` references tainted variables) and positions the engine for v0.2 rules.

**Mitigation:** Implement f-string taint propagation in v0.1 as infrastructure. No rules consume it yet. Cost: ~15 lines.

### 5. `try/except/else` — The `else` Block Is Not the `try` Block

```python
try:
    response = requests.get(url)      # TIER_3
except RequestException:
    return TransformResult.error(...)
else:
    # This code runs ONLY if no exception — but the AST treats it
    # as part of the Try node, not a separate scope
    data = response.json()            # response is TIER_3 here too
```

The `ast.Try` node has `.body`, `.handlers`, `.orelse`, and `.finalbody`. Taint state from the `try` body is available in the `else` block (execution continues if no exception). This is correct for provenance propagation — `response` is still TIER_3. But for the broad `except` rule (R4), the `else` block's exception handling context is different: code in `else` is NOT wrapped by the `try`'s `except` handlers.

**Mitigation:** When evaluating R4 (broad except), track which AST subtree each variable access falls in. Accesses in `.orelse` are not covered by the `try`'s handlers. This matters for the false positive case where a developer uses broad `except` on the external call but does precise handling in `else` — the tool should not flag `else` code as "wrapped in broad except."

## Corpus Performance: 208 Samples in <5s CI

**Yes, this is trivially within budget.** The current `enforce_tier_model.py` processes ~60 files (the entire `src/elspeth/` tree) in under 2 seconds on CI. Each corpus entry is a single-file AST parse + rule evaluation. At ~10ms per file (conservative — most corpus entries will be <50 lines), 208 entries complete in ~2 seconds.

The performance risk is not the corpus. It's the taint propagation pass on large files. The current enforcer does a single AST walk per file (O(n) in AST nodes). The taint engine adds a second pass per function body for propagation. For ELSPETH's largest files (~1200 lines, ~3000 AST nodes), this is still sub-100ms per file. The <5s CI budget accommodates the full source tree + corpus with margin.

**The real performance concern is MIXED propagation in deeply nested containers.** If a function builds a dict-of-dicts-of-lists with mixed provenance, the propagation must walk the container construction tree. In pathological cases (auto-generated code with deeply nested literals), this could blow up. Practical mitigation: cap container nesting depth at 5 levels for provenance tracking. Beyond that, label as MIXED and move on. No production code in ELSPETH exceeds 3 levels.

## Summary

| Question | Answer |
|----------|--------|
| Can I commit to the 5-label model? | **Yes.** The divergence on R4 and R7 justifies the split. |
| Minority report? | `@internal_data` alias for TIER_2 as API convenience. Not blocking. |
| AST edge cases? | 5 identified: walrus scoping, method decorator resolution, MIXED unpacking, f-string propagation, try/else context. All mitigable within v0.1. |
| Corpus in <5s? | **Yes.** ~2s estimated. Performance risk is large-file propagation, not corpus size. |
| Blocking concerns? | **None.** The design is implementable in stdlib `ast`. Let's build it. |
