# Analysis: src/elspeth/core/templates.py

**Lines:** 233
**Role:** Development-time helper for extracting field names from Jinja2 templates via AST walking. Used to discover template dependencies so developers can declare `required_input_fields` in plugin config. NOT used for runtime template rendering (that is handled by `plugins/llm/templates.py` using `SandboxedEnvironment`).
**Key dependencies:** `jinja2.Environment`, `jinja2.nodes` (AST node types); imports `SchemaContract` for type-checking only; imported by `plugins/llm/base.py`, test files, and `extract_jinja2_fields_with_names` used by integration tests
**Analysis depth:** FULL

## Summary

This module is well-designed for its purpose as a development helper. The AST walking is correct and the three extraction functions provide increasing levels of detail. The use of unsandboxed `jinja2.Environment()` for parsing is a notable design choice -- it is safe because only `env.parse()` is called (AST generation), not `template.render()` (execution). There are no critical findings. Warnings relate to the unsandboxed environment choice and potential confusion about the module's role versus `plugins/llm/templates.py`.

## Warnings

### [84, 138] Uses unsandboxed Environment for AST parsing

**What:** `Environment()` on lines 84 and 138 creates a standard (unsandboxed) Jinja2 environment. In contrast, `plugins/llm/templates.py` (line 111) uses `SandboxedEnvironment` for actual template rendering.

**Why it matters:** This is **safe for the current use case** because `env.parse()` only generates an AST -- it does not execute any template code. There is no `template.render()` call anywhere in this module. However, a future developer might see `Environment()` and add rendering functionality, unknowingly creating an injection vector. The `plugins/llm/templates.py` module already handles rendering correctly with sandboxing.

**Risk assessment:** LOW. The module docstring clearly states this is a "development helper" for field extraction. No rendering occurs. But the asymmetry with `plugins/llm/templates.py` could cause confusion during code review.

### [84] TemplateSyntaxError propagation is documented but could leak template content

**What:** The docstring on line 66 documents that `jinja2.TemplateSyntaxError` is raised for malformed templates. This exception includes the template source in its message. If templates contain sensitive data (API keys embedded in prompts, PII in lookup references), the error message could leak that data to logs or error handlers.

**Why it matters:** Since this is a development helper (not runtime), the risk is limited to developer environments. But if it is ever called with production templates during debugging, sensitive content could appear in logs.

### [100-101, 104-111] AST walking does not handle nested namespace access

**What:** The walker checks for `row.field` (Getattr) and `row["field"]` (Getitem) patterns, but only one level deep. It would NOT detect:
- `row.nested.field` (chained attribute access)
- `row["dict"]["key"]` (chained item access)
- `row.items()` or `row.keys()` (method calls on the namespace)

**Why it matters:** These patterns are unlikely in typical LLM prompt templates (which tend to be flat field references), but a template like `{{ row.address.city }}` would only extract `address`, not `city`. The developer would then declare `required_input_fields: [address]` which is correct (the row needs an `address` field), but would miss that `address` must be a dict with a `city` key.

**Evidence:**
```python
# Only handles: row.field
if isinstance(node, Getattr) and isinstance(node.node, Name) and node.node.name == namespace:
    fields.add(node.attr)

# Only handles: row["field"]
if isinstance(node, Getitem) and isinstance(node.node, Name) and node.node.name == namespace:
    # ...
```

The docstring correctly documents this limitation: "Cannot analyze dynamic keys (row[variable] is ignored)." But the nested access limitation is not explicitly documented.

## Observations

### [48-88] extract_jinja2_fields is clean and correct

**What:** The function correctly uses Jinja2's built-in `env.parse()` for AST generation rather than regex-based extraction. This handles all Jinja2 syntax including conditionals, loops, and nested blocks. The frozenset return type prevents mutation and signals immutability.

### [118-159] extract_jinja2_fields_with_details provides useful debugging info

**What:** Returns access type ("attr" vs "item") per field, which is useful for understanding how templates reference data. The `setdefault` pattern correctly handles fields accessed both ways.

### [162-233] extract_jinja2_fields_with_names integrates with SchemaContract

**What:** This function resolves field names through the `SchemaContract.resolve_name()` method, enabling developers to see both original and normalized names. The `try/except KeyError` on line 218 correctly handles fields not in the contract (reporting them as-is with `resolved: False`).

### [91-115] Recursive AST walk is straightforward

**What:** The `_walk_ast` function uses `node.iter_child_nodes()` for traversal, which is the idiomatic Jinja2 AST walking pattern. Recursion depth is bounded by template nesting depth, which is practically limited (templates rarely nest more than 10-20 levels).

### Module boundary is clean

**What:** This module is purely analytical (reads template AST, returns data). It has no side effects, no state, and no I/O. The separation from `plugins/llm/templates.py` (which handles rendering) is a good architectural boundary.

### [41-45] __all__ correctly limits public API

**What:** Only the three extraction functions are exported. Internal helpers (`_walk_ast`) are correctly excluded.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. Consider adding a comment about the unsandboxed Environment choice (explaining that parse-only is safe) to prevent future confusion. The nested access limitation could be documented more explicitly in the docstring.
**Confidence:** HIGH -- The module is small, pure-functional, and has no side effects. The Jinja2 AST walking is a well-understood pattern. The relationship with `plugins/llm/templates.py` is clearly separated.
