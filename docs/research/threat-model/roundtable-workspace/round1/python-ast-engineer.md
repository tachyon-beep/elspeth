# Round 1 — Opening Position: Pyre (Python AST Engineer)

## Summary Position

Python's `ast` module gives us a complete, faithful parse tree with full positional information — enough for robust intra-function taint analysis and structural verification of validator decorators. The hard limit is not parsing but *resolution*: without type information, we cannot distinguish `response.get("key")` (Tier 3, legitimate) from `config.get("key")` (Tier 1, violation) by AST alone. The design must embrace this limit explicitly through a declaration-plus-heuristic model rather than pretending we can infer provenance from syntax.

## Detailed Analysis

### 1. AST Capabilities and Limits

**What `ast.parse()` gives us (Python 3.12+):**

Every syntactic construct becomes a typed node with precise `lineno`, `col_offset`, `end_lineno`, `end_col_offset`. For our purposes, the critical node types are:

| Need | AST Nodes | Reliability |
|------|-----------|-------------|
| Function boundaries | `FunctionDef`, `AsyncFunctionDef` | Perfect — 1:1 with source |
| Decorator detection | `node.decorator_list` → list of `Name`/`Attribute`/`Call` | Perfect — decorators are syntactic |
| Method calls (`.get()`, `.loads()`) | `Call(func=Attribute(value=..., attr="get"))` | Perfect syntax, zero type info |
| Import tracking | `Import`, `ImportFrom` | Perfect for static imports |
| Assignment targets | `Assign`, `AnnAssign`, `AugAssign`, `NamedExpr` | Complete |
| Control flow | `If`, `Try`, `ExceptHandler`, `Raise`, `Return`, `Assert` | Complete |
| Comprehensions | `ListComp`, `SetComp`, `DictComp`, `GeneratorExp` | Complete, including nested `if` clauses |
| f-strings | `JoinedStr` with `FormattedValue` children | Complete since 3.12 |

**What `ast.parse()` does NOT give us:**

1. **Type information.** `x.get("key")` — is `x` a dict? An `os.environ`? A `requests.Response`? A custom class with a `.get()` method? The AST knows only that something named `x` had `.get()` called on it. This is the fundamental reason the current enforcer fires on *every* `.get()` call and relies on allowlisting.

2. **Runtime name resolution.** After `from module import thing`, we know the *string* `"module"` but not what `thing` actually is at runtime. Dynamic imports (`importlib.import_module`), conditional imports (`if sys.platform == ...`), and re-exports all break static resolution.

3. **Call graph / return types.** Given `result = some_function(x)`, we cannot know what `some_function` returns without analyzing its definition — and that definition may be in another file, in a C extension, or generated dynamically.

4. **Metaclass effects.** `__init_subclass__`, `__set_name__`, descriptor protocols, and metaclass `__new__` can all create or modify attributes that the AST cannot see.

5. **Decorator side effects.** `@dataclass` adds `__init__`, `__eq__`, etc. `@property` creates descriptors. The AST sees the decorator *name* but not its runtime effects on the class/function.

6. **Dynamic attribute creation.** `setattr(obj, name, value)`, `obj.__dict__[name] = value`, and `__getattr__` overrides are invisible to static analysis.

**Practical implication:** We are building a *syntactic* taint tracker, not a *semantic* one. This is not a weakness to apologize for — it's a design constraint to embrace. The declaration model (`@external_boundary`, `@validates_external`) exists precisely to bridge the gap between what the AST can see (syntax) and what we need to know (provenance).

### 2. Taint Propagation Feasibility

**Intra-function taint analysis (v0.1) — what's tractable:**

Within a single function body, we can track taint through a subset of Python's assignment and expression forms. The core algorithm: walk the function's AST in statement order, maintaining a set of tainted names, and propagate taint through assignments.

**Propagation rules I propose:**

```
TAINT SOURCES (initial taint set):
  - Return values of functions decorated @external_boundary
  - Return values of heuristic external calls (requests.get, json.loads, etc.)
  - Parameters annotated or declared as external

PROPAGATION (intra-function):
  Simple assignment:    x = tainted_expr        → x is tainted
  Tuple unpacking:      a, b = tainted_expr     → a, b both tainted
  Star unpacking:       a, *b = tainted_expr    → a, b both tainted
  Augmented assign:     x += tainted_expr       → x is tainted
  Walrus operator:      if (x := tainted_expr)  → x is tainted
  Subscript:            x = tainted["key"]      → x is tainted
  Attribute:            x = tainted.attr        → x is tainted
  Dict/list literal:    x = {"k": tainted}      → x is tainted (conservative)
  F-string:             x = f"{tainted}"        → x is tainted
  Binary op:            x = tainted + clean     → x is tainted

CLEANSING:
  - Passing tainted value through @validates_external function
  - Explicit isinstance() check in an if-branch (within that branch only)
  - Assignment from a non-tainted source overwrites taint

NOT PROPAGATED (v0.1 — false negatives accepted):
  - Through function calls to non-decorated functions
  - Through class attribute access (self.field = tainted, later self.field)
  - Through container mutations (list.append(tainted), dict[key] = tainted)
  - Through closures and nested functions
  - Through global/nonlocal assignments
```

**Where intra-function taint breaks down — concrete examples:**

```python
# CASE 1: Container mutation — taint escapes tracking
result = {}
result["data"] = json.loads(response.text)  # taint stored in result["data"]
process(result["data"])  # Is result["data"] tainted? We lost track at mutation.

# CASE 2: Helper function — taint crosses function boundary
def extract_field(response, field):
    return response[field]  # Returns tainted data, but caller doesn't know

data = extract_field(api_response, "users")  # Taint lost at call boundary

# CASE 3: Conditional taint — path sensitivity
if validate(external_data):
    clean = external_data  # Tainted or clean? Depends on validate() semantics
else:
    raise ValueError(...)
use(clean)  # Only reached if validate() passed — but AST can't prove this

# CASE 4: *args/**kwargs — taint explosion
def forward(*args, **kwargs):
    return downstream(*args, **kwargs)  # All args/kwargs carry taint? Too noisy.
```

**The v0.1 → v1.0 gap** is enormous. Inter-procedural analysis requires building a call graph (which files call which functions), computing summary effects for each function ("this function returns tainted data if argument 0 is tainted"), and iterating to a fixed point. This is a whole-program analysis — it's what tools like pytype and mypy do, and they have tens of thousands of lines of code dedicated to it. I strongly recommend that v0.1 explicitly document that inter-procedural taint is out of scope and that the `@external_boundary` / `@validates_external` declarations are the mitigation for this gap.

### 3. Symbol Table Design

I propose a two-pass architecture with these data structures:

**Pass 1 — Symbol Collection (per-file):**

```python
@dataclass
class FileSymbols:
    """Collected from a single file in Pass 1."""
    path: str

    # Decorated functions: name → decorator info
    boundary_functions: dict[str, BoundaryDecl]  # @external_boundary
    validator_functions: dict[str, ValidatorDecl]  # @validates_external

    # Import map: local_name → fully_qualified_module
    imports: dict[str, str]

    # Class definitions: class_name → list of method names
    classes: dict[str, ClassInfo]

    # Top-level assignments (for module-level constant tracking)
    module_assignments: dict[str, ast.expr]  # name → RHS node

@dataclass
class BoundaryDecl:
    func_name: str
    lineno: int
    is_method: bool
    enclosing_class: str | None

@dataclass
class ValidatorDecl:
    func_name: str
    lineno: int
    has_control_flow: bool  # Verified in Pass 1
    control_flow_types: frozenset[str]  # {"try/except", "isinstance", "raise", ...}
```

**Pass 2 — Rule Evaluation (per-function):**

```python
@dataclass
class TaintState:
    """Per-function taint tracking during Pass 2 walk."""
    tainted_names: set[str]  # Names currently carrying taint
    taint_sources: dict[str, TaintOrigin]  # name → where taint came from
    cleansed_names: set[str]  # Names that passed through validation

@dataclass
class TaintOrigin:
    source_type: str  # "decorator", "heuristic", "parameter"
    source_detail: str  # e.g., "requests.get" or "@external_boundary"
    lineno: int
```

**Why two passes?** Pass 1 must complete for the entire file (or project) before Pass 2 can evaluate rules, because a function decorated `@validates_external` at line 200 might be called as a cleanser at line 50. The existing enforcer's single-pass `ast.NodeVisitor` approach works for pattern matching (every `.get()` is suspect regardless of context) but cannot support taint analysis where the meaning of a call depends on what the callee is decorated with.

### 4. Structural Verification of `@validates_external`

The requirement: functions decorated `@validates_external` must actually contain validation logic, not just claim to validate. The AST nodes that constitute "control flow indicating validation":

| AST Node | Pattern | Example |
|----------|---------|---------|
| `ExceptHandler` | Any `try/except` | `try: parse(data) except ValueError: ...` |
| `Raise` | Any `raise` statement | `raise ValidationError(...)` |
| `If` with `isinstance` | `isinstance()` in test | `if isinstance(data, dict): ...` |
| `If` with comparison | Comparison in test | `if len(data) > 0: ...` |
| `Assert` | Any assertion | `assert "key" in data` |

**Edge cases to handle:**

```python
# PASSES — has control flow
@validates_external
def validate_response(data):
    if not isinstance(data, dict):
        raise TypeError("Expected dict")
    return data

# FAILS — no validation logic, just passthrough
@validates_external
def fake_validate(data):
    return data  # Decorator lies — no control flow

# AMBIGUOUS — comprehension with conditional
@validates_external
def filter_valid(items):
    return [x for x in items if x.get("valid")]  # if-clause in comprehension

# AMBIGUOUS — nested function has control flow, outer doesn't
@validates_external
def tricky(data):
    def inner(x):
        if not x:
            raise ValueError()
    return inner(data)  # Outer function has no direct control flow
```

**My recommendation:** For v0.1, require control flow nodes to be *direct children* of the function body (not inside nested functions, comprehensions, or lambda). This is conservative — it may reject valid validators that delegate to helpers — but it prevents the `fake_validate` evasion pattern. The check is simple: walk only `node.body` one level deep (plus nested `if`/`try` blocks), not the full subtree.

Concretely, the check walks the function body and looks for `ExceptHandler`, `Raise`, `If` (with a non-trivial test), or `Assert` nodes. Comprehension `if` clauses (`ast.comprehension.ifs`) should NOT count — they're filtering, not validating.

### 5. Performance

**Parsing cost:** `ast.parse()` is implemented in C and is fast. Benchmarks on CPython 3.12:

- A 500-line file: ~1-2ms to parse
- A 2000-line file: ~5-8ms to parse
- Walking the tree with `ast.NodeVisitor`: roughly 2x the parse time

**ELSPETH's `src/elspeth/` directory** has approximately 100-120 Python files. At ~5ms per file (parse + walk), that's ~500-600ms for a full scan. With two passes, double that to ~1-1.2s. Well within a 2s pre-commit budget.

**The real cost is not parsing — it's I/O and YAML loading.** The current enforcer loads per-module YAML allowlists. For the new tool, loading `strict.toml` and resolving heuristic lists will add latency. Keep the manifest format simple and cache-friendly.

**Scaling concern:** If the tool is distributed as a standalone PyPI package and applied to large projects (10,000+ files), the linear scan becomes expensive. However, for pre-commit, `--files` mode (scan only changed files) is the norm. For CI, 10,000 files at 5ms each is 50s — acceptable for CI, not for pre-commit. The `--stdin` agent self-check mode should process a single file in <100ms.

### 6. Key Design Concern: The False Positive Boundary

The hardest problem is not parsing or taint propagation — it's **false positive rate on `.get()` calls**. The current enforcer already demonstrates this: it fires on *every* `.get()`, including legitimate Tier 3 boundary code, and relies on an allowlist to manage the noise. The new tool must do better.

**The fundamental tension:** Without type information, `x.get("key", default)` is ambiguous. It could be:
- A `dict.get()` on Tier 1 data (violation — fabricating defaults on audit data)
- A `dict.get()` on Tier 3 data in a source plugin (legitimate — coercion at boundary)
- An `os.environ.get()` (legitimate — environment variables are Tier 3)
- A method named `.get()` on a custom class that has nothing to do with dicts

**My proposed resolution hierarchy (from most to least reliable):**

1. **Decorator-based taint:** If the variable was assigned from an `@external_boundary` call, `.get()` is legitimate (Tier 3 handling). Clear the finding.
2. **Heuristic source matching:** If the variable was assigned from `requests.get()`, `json.loads()`, `os.environ`, etc., treat `.get()` as legitimate.
3. **Positional context:** If the enclosing function is inside a class that inherits from a known Source base class (heuristic, fragile), relax the rule.
4. **Manifest override:** `strict.toml` can declare specific functions/methods as boundary code where `.get()` is allowed.
5. **Default: flag it.** If none of the above apply, flag it as a finding. The precision target (>95%) means we must ensure cases 1-4 catch the legitimate uses before we reach this fallback.

This hierarchy is the core architectural decision. Get it wrong and we either drown in false positives (tool gets disabled) or miss real violations (tool provides false assurance).

## Key Design Proposal

**A `TaintMap` that flows forward through the function body, keyed by variable name, with taint provenance attached.** Each assignment statement updates the map. Each `.get()` / `getattr()` / broad-except is evaluated *in the context of* the taint state at that point. This transforms the current enforcer's context-free pattern matching into context-sensitive rule evaluation.

The implementation is a custom `ast.NodeVisitor` subclass that processes function bodies in statement order (not the default recursive walk), maintaining `TaintState` as mutable state. This requires overriding `generic_visit` to enforce statement ordering within function bodies while still recursing into expressions.

```python
class TaintTrackingVisitor(ast.NodeVisitor):
    def __init__(self, symbols: FileSymbols):
        self.symbols = symbols
        self.taint: TaintState = TaintState()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Reset taint state per function (v0.1 — no inter-procedural)
        saved = self.taint
        self.taint = TaintState()
        self._taint_from_params(node)

        # Process body IN ORDER (not recursive walk)
        for stmt in node.body:
            self._visit_statement(stmt)

        self.taint = saved

    def _visit_statement(self, stmt: ast.stmt):
        if isinstance(stmt, ast.Assign):
            self._handle_assign(stmt)
        elif isinstance(stmt, (ast.If, ast.Try)):
            self._handle_control_flow(stmt)
        # ... etc
```

This is the minimal viable taint engine for v0.1. It handles the 80% case (linear code with assignments and calls) and explicitly documents what it doesn't handle (mutations, closures, inter-procedural flow).

## Technical Risks

1. **Over-tainting.** Conservative propagation (any operation on tainted data produces tainted result) will taint most variables in functions that process external data. If 20 out of 25 variables are tainted, the tool effectively says "everything is fine" — taint becomes meaningless. We need cleansing to be easy and well-documented, or taint will saturate.

2. **Statement ordering in non-linear control flow.** Python allows `else` clauses on `for`/`while`/`try`. Taint state after an `if/else` requires merging two branches (union of tainted names). Taint state after `try/except` is complex — the `except` branch may execute with different taint than the `try` branch. Getting merge semantics right without a full CFG (control flow graph) is fragile.

3. **The heuristic list is an attack surface.** If the tool ships with a built-in list of "known external calls" (`requests.get`, `json.loads`, etc.), an adversarial agent can use unlisted external calls to bypass detection. The list must be extensible via `strict.toml` and the default list must be conservative (flag unknown calls as potentially external rather than assume they're internal).

4. **Decorator name resolution.** `@external_boundary` is clear, but what about `@my_module.external_boundary` or `from decorators import external_boundary as eb; @eb`? The AST gives us the syntactic form of the decorator, not its runtime identity. We need to handle aliased imports in Pass 1 or we'll miss decorated functions.

5. **Comprehension scoping.** Python 3 comprehensions have their own scope. `[f(x) for x in tainted_list]` — the `x` is tainted within the comprehension's implicit function, but the list result is also tainted. Handling this correctly requires treating comprehensions as mini-functions with their own taint state, then propagating the result's taint back to the enclosing scope.

6. **`ast.parse()` does not give us the type of `self`.** In `def process(self, row, ctx)`, we know `self` is a parameter but not that it's an instance of `LLMTransform`. Without type info, we can't infer that `row` is Tier 2 pipeline data. This is why the declaration model is essential — we need annotations or decorators to bridge this gap, not increasingly clever AST heuristics that will always be brittle.
