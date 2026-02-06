# Analysis: src/elspeth/engine/expression_parser.py

**Lines:** 583
**Role:** AST-based expression parser for gate conditions and aggregation trigger expressions. Uses Python's `ast` module (NOT `eval()`) to safely parse and evaluate expressions against row data. Operates in two phases: parse-time validation (rejects forbidden constructs) and runtime evaluation (executes the validated AST). Security-sensitive component that evaluates user-defined expressions from configuration files.
**Key dependencies:**
- Imports: `ast`, `operator` (stdlib only -- no framework dependencies)
- Imported by: `engine/executors.py` (gate execution), `engine/triggers.py` (aggregation trigger evaluation), `core/config.py` (expression validation at config load time)
**Analysis depth:** FULL

## Summary

The expression parser has a sound security architecture: two-phase validation with an AST whitelist approach, no use of `eval()`, and clear separation between validation and evaluation. The primary concerns are: (1) a known open bug (P2-2026-02-05) where mutable module-level operator dicts can be tampered with at runtime, (2) the validator uses an allowlist approach but falls through to `generic_visit` for unrecognized AST nodes, meaning future Python versions that add new expression node types would silently pass validation, and (3) `ExpressionParser` is re-instantiated on every gate evaluation in the executor, re-parsing and re-validating the same static expression string per row. The parser is well-tested and the security model is defense-in-depth (plugins are trusted system code, but config expressions get restricted evaluation).

## Critical Findings

_None at the critical level. The known mutable-dicts bug (P2-2026-02-05) is already filed and tracked._

## Warnings

### [48-83] Mutable operator allowlists enable runtime tampering (known bug P2-2026-02-05)

**What:** The four operator dictionaries (`_COMPARISON_OPS`, `_BINARY_OPS`, `_UNARY_OPS`, `_BOOL_OPS`) are plain mutable `dict` objects at module scope. Any code that imports them can add entries (e.g., `_BINARY_OPS[ast.Pow] = operator.pow`) to enable operators that should be forbidden.

**Why it matters:** This undermines the core security guarantee of the restricted expression parser. If any in-process code mutates these dicts, previously forbidden operations become silently allowed. The validation and evaluation phases both use these same dicts, so a single mutation changes both what passes validation AND what executes.

**Evidence:** This is a known tracked bug: `docs/bugs/open/engine-expression-parser/P2-2026-02-05-mutable-operator-allowlists-allow-runtime-tam.md`. The fix is straightforward: use `types.MappingProxyType` to make the dicts immutable at module scope.

### [86-291] Validator uses allowlist pattern but has no catch-all for unknown AST node types

**What:** The `_ExpressionValidator` has explicit `visit_*` methods for known allowed and forbidden node types. However, `ast.NodeVisitor.generic_visit` (the default for unhandled node types) simply visits child nodes without recording any error. If a future Python version adds a new `ast.expr` subclass (e.g., a new expression type), expressions using it would pass validation silently.

**Why it matters:** This is a defense-in-depth gap. The current Python version's expression nodes are fully covered (verified: all `ast.expr` subclasses have either an allowed or forbidden handler). But Python adds new AST nodes across versions. For example, Python 3.12 added some new AST features. If ELSPETH upgrades Python and a new expression node type exists, the validator would allow it by default rather than rejecting unknown constructs.

**Evidence:** The validator inherits from `ast.NodeVisitor`, whose `generic_visit` implementation is:
```python
def generic_visit(self, node):
    for child in ast.iter_child_nodes(node):
        self.visit(child)
```
No error is appended for unrecognized node types. A `generic_visit` override that rejects unknown nodes would close this gap:
```python
def generic_visit(self, node):
    if isinstance(node, ast.expr):
        self.errors.append(f"Unrecognized expression type: {type(node).__name__}")
    super().generic_visit(node)
```

### [293-458] Evaluator returns None for unrecognized node types (silent failure)

**What:** The `_ExpressionEvaluator` also inherits from `ast.NodeVisitor`. For any node type without a `visit_*` method, the default `generic_visit` visits children and returns `None`. If validation were somehow bypassed (or a new AST node type slips through the validator gap above), the evaluator would silently return `None` instead of raising an error.

**Why it matters:** In the context of gate evaluation, `None` is falsy. An expression that should evaluate to a meaningful value would silently evaluate to `None`, causing the gate to route to the "false" path. This is a silent data routing error -- the worst kind of bug in an audit system.

**Evidence:** `ast.NodeVisitor.visit()` calls `generic_visit` for unrecognized types, which returns `None`. The evaluator has no override of `generic_visit` to raise on unknown node types. This pairs with the validator gap above: if a new node type passes validation, it would then silently evaluate to `None`.

### [837 in executors.py] ExpressionParser is re-instantiated per row in gate execution

**What:** In `engine/executors.py` line 837, `ExpressionParser(gate_config.condition)` is called inside the per-row gate evaluation loop. This re-parses the expression string with `ast.parse()`, re-creates the validator, re-visits the AST, and re-checks security for every single row processed by the gate.

**Why it matters:** For a pipeline processing N rows through a gate, this means N redundant parse + validate cycles for the same static expression string. `ast.parse()` is not free -- it involves lexing, parsing, and AST construction. The `TriggerEvaluator` in `engine/triggers.py` correctly pre-parses the expression at construction time (line 73). The gate executor should follow the same pattern.

**Evidence:**
```python
# executors.py line 837 - inside per-row loop
parser = ExpressionParser(gate_config.condition)
eval_result = parser.evaluate(token.row_data)
```
vs.
```python
# triggers.py line 71-73 - pre-parsed at construction
self._condition_parser: ExpressionParser | None = None
if config.condition is not None:
    self._condition_parser = ExpressionParser(config.condition)
```

Note: This finding is about the executor's usage pattern, not about the parser itself. The parser design correctly separates parse-time validation from evaluation, enabling pre-parsing. The executor is simply not using this capability.

## Observations

### [96-118] `_is_row_derived` and `_is_none_constant` are clean helper methods

These helpers correctly identify row-derived data for subscript restriction and None constants for `is`/`is not` validation. The recursive `_is_row_derived` handles chained access like `row['x']['y']` and `row.get('x')['y']`.

### [120-124] Name validation correctly restricts to `row`, `True`, `False`, `None`

The allowlist of valid names is tight. No access to builtins, globals, or any other name. This is a key security constraint.

### [152-174] Call validation correctly restricts to `row.get()` only

The call handler validates the exact form `row.get(key)` or `row.get(key, default)` with 1-2 positional arguments and no keyword arguments. This prevents any function calls except the specific `.get()` pattern.

### [176-190] Comparison validation correctly restricts `is`/`is not` to None checks

The `is` and `is not` operators are only allowed when one operand is a None constant. This prevents identity comparisons on arbitrary objects (which would be meaningless for row data anyway, since values are deserialized).

### [363-377] Comparison chain evaluation correctly implements Python semantics

The `visit_Compare` method correctly handles chained comparisons (e.g., `1 < x < 10`) by iterating through operators and comparators, returning `False` on first failure and advancing `left = right` for the next comparison. This matches Python's comparison chain semantics.

### [379-394] Boolean operator evaluation correctly implements short-circuit semantics

The `visit_BoolOp` method correctly returns the actual value (not just `True`/`False`), matching Python's `and`/`or` short-circuit behavior where `x and y` returns `y` if `x` is truthy, not necessarily `True`.

### [524-537] `is_boolean_expression` static analysis is correct but conservative

The method correctly identifies expressions guaranteed to return booleans. It is conservative: `row['flag']` is not classified as boolean even if the field is always boolean at runtime. This is the right approach for static analysis.

### [460-583] ExpressionParser public API is clean

The class correctly separates construction (parse + validate) from evaluation. The `_ast` attribute is stored for reuse across multiple `evaluate()` calls, enabling efficient re-evaluation against different rows. The public interface is minimal: `__init__`, `evaluate`, `is_boolean_expression`, `expression` property.

### [244-290] Forbidden construct handlers correctly block dangerous operations

Lambda, comprehensions, yield, await, assignment expressions, f-strings, and starred expressions are all explicitly forbidden. The handlers append errors rather than raising, allowing multiple security violations to be reported at once.

### Thread safety note

The `_ExpressionValidator` uses an instance variable `_in_call_func` as a flag during tree traversal. This is safe because validators are instantiated per parse (line 512) and never shared across threads. Similarly, `_ExpressionEvaluator` is instantiated per evaluation (line 579). The `ExpressionParser` instance itself stores only immutable state (`_expression` string and `_ast` tree), making it safe to share across threads for evaluation.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. Fix the mutable operator allowlists (known P2 bug) -- use `types.MappingProxyType` wrapping.
2. Add a `generic_visit` override to `_ExpressionValidator` that rejects unknown `ast.expr` node types, closing the future-Python-version gap.
3. Add a `generic_visit` override to `_ExpressionEvaluator` that raises `ExpressionSecurityError` for unrecognized node types, preventing silent `None` evaluation.
4. Pre-parse gate expressions in the executor rather than re-parsing per row (performance improvement, pattern already exists in `TriggerEvaluator`).
**Confidence:** HIGH -- Full code read, complete understanding of the AST visitor pattern, verified coverage of all current Python AST expression types, cross-referenced with executor and trigger usage patterns.
