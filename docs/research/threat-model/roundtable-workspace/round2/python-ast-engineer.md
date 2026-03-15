# Round 2 — Dissent: Pyre (Python AST Engineer)

## Target: Seren — Immutable Precision Threshold (Leverage Point 3)

## Steelman

Seren's argument is elegant and draws from a real dynamic. The "Eroding Goals" archetype predicts that any configurable threshold will be lowered under pressure: first from 95% to 90% ("we have too many advisory rules"), then to 85% ("we're being too strict"), then eventually to a number so low the threshold is meaningless. Making the threshold a constant in source code — not a config parameter — forces rule authors to meet the standard or accept permanent advisory status. The precision target becomes a structural property of the system rather than a policy decision subject to renegotiation.

This is a sound systems-thinking argument. The dynamic Seren describes is real: I've seen it in linter configurations where `max-line-length` starts at 80, becomes 100, becomes 120, becomes "we just disable that rule." The ratchet only turns one way.

Furthermore, Seren correctly identifies that the golden corpus can be gamed — teams unconsciously curate samples that validate their preferred rules. An immutable threshold at least prevents the *overt* degradation path, even if the *covert* path (corpus curation bias) remains open.

## Attack

The argument fails because it treats all rules as having the same precision ceiling, when the AST fundamentally cannot achieve uniform precision across different syntactic patterns. This is not a tuning problem — it's a structural property of what `ast.parse()` can and cannot distinguish.

**Concrete evidence: the precision ceiling varies by rule.**

Consider rule R1 (`.get()` detection) versus rule R3 (`hasattr()` detection):

- **R3 (`hasattr`)** is unconditionally banned in ELSPETH. Every `hasattr()` call in the codebase is a violation, regardless of context, tier, or data provenance. The AST gives us `Call(func=Name(id="hasattr"))` — a perfect match. Expected precision: **~99%** (the only false positives are third-party code accidentally scanned). R3 could comfortably operate at a 98% threshold.

- **R1 (`.get()`)** fires on every `Call(func=Attribute(attr="get"))`. But `.get()` is legitimately used at Tier 3 boundaries (source plugins coercing external data), in `os.environ.get()`, and on custom objects with `.get()` methods that have nothing to do with dicts. Without type information, the AST cannot distinguish these. Even with my proposed 5-level resolution hierarchy (decorator taint → heuristic matching → positional context → manifest → default-flag), precision will realistically land around **85-92%** in a codebase like ELSPETH that has genuine Tier 3 boundary code.

- **R4 (broad except)** is context-dependent by design: `except Exception` is *required* around external API calls (Tier 3) and *forbidden* around Landscape reads (Tier 1). Without taint context, the AST sees identical syntax. Precision depends entirely on the taint engine's ability to determine which tier the wrapped code operates in. Realistic precision: **80-90%** in v0.1, improving with taint maturity.

**The consequence of a single immutable 95% threshold:**

R1 and R4 — which catch the most dangerous violations (ACF-I1 silent fabrication via defaults, ACF-I3 audit trail destruction) — may *never* reach blocking status. They'll remain perpetually advisory while R3 (`hasattr`, which is already caught by a simple grep) operates as the flagship blocking rule. The tool's most valuable rules are the ones the AST has the hardest time being precise about, because those are the context-dependent rules where human review fails too.

Meanwhile, R3 is held to 95% when it could meet 99%. A single threshold means high-precision rules underperform their potential and low-precision rules are permanently excluded.

**Why Quinn's dual threshold is technically superior:**

Quinn proposed ≥95% precision over 100 firings AND ≤5 FPs per full-repo scan. The per-scan FP cap is the insight Seren's model misses. A rule at 88% precision that fires 30 times per scan produces ~4 false positives — annoying but manageable. A rule at 96% precision that fires 200 times produces ~8 false positives — technically "precise" but more disruptive in practice. Quinn's model captures both dimensions; Seren's captures neither.

**My proposed synthesis:** Per-rule precision thresholds with an immutable *floor*. The floor (say, 80%) is a constant in code — no rule can operate in blocking mode below it, period. But individual rules earn their own threshold based on measured data, and that threshold can only increase (monotonicity — borrowing Riven's principle). R3 blocks at 98%. R1 blocks at 88%. R4 blocks at 85%. The floor prevents erosion; per-rule thresholds prevent the precision ceiling from permanently excluding valuable rules.

## Addressing the Scribe's Question: Aliasing Evasions

The scribe correctly identified that Riven's aliasing evasions (`_g = getattr`) operate below the level my 5-level resolution hierarchy addresses. The hierarchy resolves `.get()` false positives by determining the *provenance of the object* being accessed — it doesn't protect against indirect *call* patterns.

This is a real gap, but it's a solvable one within v0.1 scope. The fix is a **name-binding tracker** in Pass 1 that detects when a known dangerous builtin or method is assigned to a local name:

```python
# Pass 1 detects:
_g = getattr        # Assign(targets=[Name("_g")], value=Name("getattr"))
_safe = dict.get    # Assign(targets=[Name("_safe")], value=Attribute(value=Name("dict"), attr="get"))

# Adds to symbol table:
#   _g → alias_of("getattr")
#   _safe → alias_of("dict.get")

# Pass 2 then treats:
_g(obj, "attr", None)  # Same as getattr(obj, "attr", None) → R2 finding
_safe(d, "key", "")    # Same as dict.get(d, "key", "") → R1 finding
```

This handles direct aliasing. It does NOT handle `operator.methodcaller` or `functools.partial(getattr, ...)` — those require inter-procedural analysis of stdlib function semantics. But direct aliasing is the 90% case an agent would reach for first, and it's cheap to detect.

Riven is right that this is an arms race. But the arms race is bounded by Python's syntax: there are only so many ways to spell "call a function" in the AST. `Call(func=...)` where `func` is `Name`, `Attribute`, `Subscript`, or `Starred` — that's the complete set. Track aliases through all four, and you've covered the syntactic surface.

## Proposed Verdict

1. **Reject** Seren's immutable single threshold. Accept the "Eroding Goals" risk but mitigate it structurally rather than through rigidity.
2. **Adopt** per-rule precision thresholds with an immutable floor (80%) constant in code. Individual rule thresholds are monotonically non-decreasing and stored in the manifest (CODEOWNERS-protected).
3. **Adopt** Quinn's per-scan FP cap (≤5) as a complementary constraint — a rule that's precise per-firing but noisy per-scan still fails the review-burden test.
4. **Add** name-binding alias tracking to v0.1 scope to close Riven's syntactic aliasing evasion. This is intra-function, low-cost, and directly addresses the gap the scribe flagged.
