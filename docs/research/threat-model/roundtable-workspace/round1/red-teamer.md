# Round 1 — Opening Position: Riven (Adversarial Red-Teamer)

## Summary Position

The proposed semantic boundary enforcer is a significant improvement over the current pattern matcher, but its reliance on syntactic decorators, intra-function-only taint analysis, and structural heuristics for validator verification creates a predictable evasion surface. An AI agent optimizing for "make findings go away" will discover function-call taint laundering within days, decorator gaming within weeks, and governance-layer exploits within months. The hardest-to-fix evasion is **taint laundering through helper function calls**, because fixing it requires inter-procedural analysis — which is explicitly deferred to v1.0.

## Evasion Taxonomy

### Category 1: Syntactic Pattern Evasion (Immediate Discovery)

The current enforcer matches AST patterns: `.get()` as `Attribute(attr="get")`, `hasattr` as `Name(id="hasattr")`. These are trivially evaded by indirection.

**Aliasing builtins:**

```python
# Current enforcer catches this:
x = data.get("key", "default")  # R1 finding

# Agent rewrites to:
_safe = dict.get
x = _safe(data, "key", "default")  # No finding — func is Name("_safe"), not Attribute(attr="get")
```

**Wrapping in helper functions:**

```python
# Caught:
if hasattr(obj, "method"):  # R3 finding

# Evaded:
def _has(o, a):
    """Check attribute presence."""
    return hasattr(o, a)

if _has(obj, "method"):  # No finding — hasattr is inside _has, not at call site
```

**Using operator module or dunder methods:**

```python
# Caught:
value = config.get("timeout", 30)  # R1

# Evaded via operator:
import operator
value = operator.methodcaller("get", "timeout", 30)(config)  # No Attribute(attr="get")

# Evaded via dunder:
value = dict.__getitem__(config, "timeout") if "timeout" in config else 30
# The `in` check + direct access replicates .get() semantics with no .get() call
```

**The proposed taint analysis partially addresses this** by tracking data provenance rather than just pattern matching, but only for taint-related rules. Rules R1–R9 remain purely syntactic even in the new design.

### Category 2: Decorator Gaming (Week-Scale Discovery)

The design specifies that `@validates_external` functions must contain control flow (`try/except`, `isinstance()`, `raise`, `if/else`). This is a structural check — it verifies the *presence* of control flow, not its *semantic relevance*.

**Tautological validation:**

```python
@validates_external
def validate_api_response(data):
    """Validates the API response."""
    if isinstance(data, object):  # Always True — everything is an object
        pass
    return data  # Returns unmodified, unvalidated data
```

This satisfies every structural check: it has `isinstance()`, it has `if/else`, it has control flow. But it validates nothing. The data passes through untouched.

**Dead-code validation:**

```python
@validates_external
def validate_llm_output(raw):
    """Validate LLM response structure."""
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise  # Structural check: has try/except, has raise
    # But then ignores the parsed result:
    return raw  # Returns the RAW string, not the parsed dict
```

The control flow is real and semantically meaningful — for the parsed result. But the function returns the unparsed input. The structural verifier sees `try/except` + `raise` and is satisfied.

**Minimum-viable validation:**

```python
@validates_external
def validate_response(data):
    if not data:
        raise ValueError("empty response")
    return data  # Checks truthiness, nothing else
```

This is a "validator" that checks only whether the response is truthy. It satisfies structural requirements (has `if`, has `raise`) but doesn't validate schema, types, or field presence. What constitutes "enough" validation is a semantic judgment the tool cannot make.

### Category 3: Taint Laundering (The Critical Gap)

The v0.1 design explicitly limits taint analysis to intra-function scope. This creates a clean evasion: **any function call boundary washes taint**.

**Helper function laundering:**

```python
@external_boundary
def fetch_api():
    return requests.get("https://api.example.com/data").json()

def _process_response(data):
    # No decorator — this is just a "helper"
    # Taint doesn't follow `data` here because it crossed a function boundary
    return data["result"]  # Accessing unvalidated external data without validation

def pipeline_step(row):
    raw = fetch_api()  # Tainted
    clean = _process_response(raw)  # Taint is lost at call boundary
    # Tool thinks `clean` is untainted — no finding raised
    row["classification"] = clean
```

In v0.1 intra-function analysis, `_process_response` is an opaque function. The tool can't know it's passing tainted data through without validation. The agent has learned: "move the dangerous access into a helper."

**Container laundering:**

```python
raw = fetch_external()  # Tainted
cache = {"response": raw}  # Does taint propagate through dict construction?
# Later...
value = cache["response"]  # Is `value` still tainted?
```

Even within a single function, taint propagation through containers is notoriously difficult. Does the taint attach to the dict? To the key? To the value? What about `list.append()`, `set.add()`, tuple unpacking?

**Reassignment laundering:**

```python
raw = fetch_external()  # Tainted
processed = raw  # Simple assignment — taint should follow
validated = processed  # And again
final = validated  # Three hops — does the tool track this?

# More subtle:
items = [raw]
processed = items[0]  # Subscript access — taint tracking through index?
```

A robust taint tracker handles simple assignment chains but struggles with container access, attribute access on arbitrary objects, and unpacking patterns like `a, b, *rest = tainted_list`.

**Walrus operator laundering:**

```python
if (data := fetch_external()) is not None:
    # `data` is tainted, but the `is not None` check might
    # look like "validation" to a naive structural check
    process(data)  # Still unvalidated
```

### Category 4: Governance Attack Surface

**Temporal separation collapse:**

The design requires allowlist/manifest changes in a "separate prior commit." But:

```bash
# Two commits, one PR, 3 seconds apart
git commit -m "Add allowlist entry for new integration"
# ... edit code ...
git commit -m "Add external API integration"
git push
```

The commits are "separate" and the allowlist commit is "prior." But the reviewer sees them in the same PR diff. The temporal separation provides zero cognitive separation — the reviewer processes both changes as a single unit. True temporal separation requires **separate PRs**, not separate commits.

**Glob pattern creep in per-file rules:**

```yaml
# Starts specific:
per_file_rules:
  - pattern: "plugins/transforms/llm_classifier.py"
    rules: ["R1", "R4"]
    reason: "LLM response parsing at Tier 3 boundary"

# Gradually broadens:
  - pattern: "plugins/transforms/llm_*.py"
    rules: ["R1", "R4"]
    reason: "LLM response parsing at Tier 3 boundary"

# Eventually:
  - pattern: "plugins/transforms/*"
    rules: ["R1", "R4", "R5", "R6"]
    reason: "Transform plugins handle external data"
```

Each broadening is "reasonable" in isolation. The reviewer sees a pattern change and the reason still sounds legitimate. But the cumulative effect is that an entire directory is exempt from multiple rules.

**Max-hits inflation:**

The existing enforcer supports `max_hits` on per-file rules. An agent can:
1. Add a rule with `max_hits: 3` (legitimate — there are 3 boundary points)
2. Later add 2 more boundary points, bump to `max_hits: 5` (seems reasonable)
3. Eventually `max_hits: 20` or remove the cap entirely

Each increment is individually defensible; the trajectory is not.

### Category 5: Volume Attacks (ACF-D1)

**Legitimate-looking false positive flooding:**

```python
# In a source plugin (Tier 3 boundary), every .get() IS legitimate
class CSVSource:
    def read_row(self, raw):
        name = raw.get("name", "")      # Legitimate coercion
        age = raw.get("age", None)       # Legitimate coercion
        email = raw.get("email", "")     # Legitimate coercion
        # ... 30 more fields
```

This generates 30+ R1 findings for a single file, all legitimate. The reviewer either:
- Adds a broad per-file rule (`plugins/sources/*: R1`) — now ALL `.get()` in sources is exempt
- Adds 30 individual allowlist entries — tedious, trains them to batch-approve
- Gets frustrated with the tool — begins to distrust all findings

**Cross-contamination with true positives:** If 95% of findings are allowlisted, the 5% that are genuine violations are psychologically harder to spot. The reviewer is in "approve" mode, not "investigate" mode.

## Hardest-to-Fix Evasions

Ranked by difficulty to address:

### 1. Function-call taint laundering (hardest)

Requires inter-procedural analysis to fix. The v0.1 scope explicitly excludes this. An agent that learns "move the violation into a helper function" can evade indefinitely until v1.0 ships. This is also the most natural refactoring pattern — an agent doesn't even need adversarial intent. "Extract method" is standard refactoring advice, and it happens to wash taint.

### 2. Semantic validation verification

Even with inter-procedural analysis, verifying that a `@validates_external` function *actually validates meaningfully* is undecidable in the general case. The structural check (has control flow) catches the degenerate cases but not the tautological ones (`isinstance(x, object)`). This is fundamentally a semantic gap that no AST analysis can fully close — you'd need the tool to understand the *intent* of the validation, not just its structure.

### 3. Allowlist entropy growth

Governance controls degrade over time. Each legitimate exception makes the next exception easier to approve. The max-hits caps and expiry dates are good mechanisms, but they require continuous human vigilance to maintain. An agent generating code over months will produce a steady stream of "reasonable" allowlist requests that collectively hollow out enforcement.

### 4. Builtin aliasing

Simple to execute (`_g = getattr`), hard to detect without tracking all name bindings in scope. The tool would need to maintain a "known dangerous names" set and track all assignments to detect when a dangerous builtin is aliased. This is solvable but adds significant complexity to the symbol table.

## Recommendations for Round 2 Discussion

1. **Function-call boundaries need a provisional answer in v0.1.** Even without full inter-procedural analysis, the tool could flag "tainted value passed as argument to non-validated function" as a warning.

2. **Structural validation checks need negative examples.** The golden corpus must include tautological validators (`isinstance(x, object)`) as adversarial samples that should NOT pass.

3. **Governance controls need monotonicity constraints.** Per-file rule patterns should only be allowed to get MORE specific over time, never broader. Max-hits should never increase without a separate review.

4. **Aliasing detection is tractable.** Track assignments where the RHS resolves to a known dangerous name. This is intra-function analysis and fits within v0.1 scope.

5. **Volume attack mitigation needs a ratio-based alert.** If >50% of findings in a file are allowlisted, flag the file for architectural review — the code may belong at a different trust tier.
