# Round 2 — Dissent: Quinn (Quality Engineer)

## Target: Riven — "Structural Validation is Fundamentally Insufficient"

## Steelman

Riven's position is the strongest attack on the roundtable's proposed `@validates_external` verification. The argument is devastating in its simplicity: any structural check that looks for "the presence of control flow" can be satisfied by tautological control flow that validates nothing. `isinstance(x, object)` is always true. `if data: return data` checks only truthiness. `try: json.loads(raw) except: raise` followed by `return raw` validates and then discards the validated result. These are not exotic constructions — they are exactly the patterns a code-completion model would produce when prompted "add validation to satisfy a linter."

The deeper point is that structural verification conflates *form* with *function*. A validator's purpose is to reduce the state space of its output relative to its input — to make guarantees about what comes out. No AST check can verify that the output state space is actually narrower. This is a semantic property, and the halting problem tells us it's undecidable in the general case. Riven is correct that this is not a gap we can close with better heuristics; it's a category error to try.

Furthermore, Riven's strongest example — the dead-code validator that parses JSON and then returns the unparsed raw string — is particularly insidious because it contains *real* validation logic that operates on a variable the function doesn't return. A human reviewer could miss this. An agent generating "fix this linter warning" code would produce exactly this pattern.

## Attack

Riven's analysis is correct on the technical limits. The flaw is in the **conclusion drawn from those limits**: that structural validation is "fundamentally insufficient" and that the roundtable needs a fundamentally different approach. This commits the nirvana fallacy — comparing a real, implementable mechanism against an ideal that cannot exist, and declaring the real one unacceptable.

### The Alternative to Structural Validation is Worse

If we accept Riven's conclusion and drop structural verification of `@validates_external`, we have exactly two options:

1. **Trust the decorator unconditionally.** Anyone who writes `@validates_external` is believed. The decorator becomes a `# type: ignore` comment with extra steps. Tautological validators pass silently. This is strictly worse than structural verification because it catches *fewer* evasions, not more.

2. **Don't have a validator declaration at all.** Every tainted value must be manually cleansed through allowlist entries. This eliminates the tautological validator problem by eliminating validators entirely — but it also eliminates the tool's primary false-positive suppression mechanism. Without `@validates_external`, every `.get()` on data that touched an external boundary is a finding, and we're back to the current enforcer's noise level. Gideon and Seren's adoption-killing dynamic activates immediately.

Riven identifies a failure mode of structural validation but proposes no alternative that performs better. The recommendation is "the golden corpus must include tautological validators as adversarial samples" — which is exactly my Round 1 proposal. This is not a rejection of structural validation; it's a concession that structural validation plus corpus testing is the best available approach.

### The Tautological Validator Problem is Bounded, Not Unbounded

Riven frames tautological validation as an open-ended evasion surface. In practice, the space of *syntactically valid tautological validators that pass structural checks* is constrained:

| Tautological Pattern | Catchable? | How |
|---------------------|-----------|-----|
| `isinstance(x, object)` | **Yes** — blocklist `object`, `type`, `Any` as isinstance targets | AST check on isinstance second argument |
| `if data: return data` | **Yes** — require at least one `raise` or `except` path | Structural requirement: control flow must include a rejection branch |
| `try/except` that returns raw input | **Partially** — check that `return` target matches a variable assigned inside the `try` | Data-flow check within the validator body |
| `if True: ...` / `if not False:` | **Yes** — detect constant-valued test expressions | AST check for `Constant(value=True)` or `UnaryOp(Not, Constant(False))` |

The point is not that we can catch *every* tautological validator — Riven is right that we can't. The point is that we can catch the **mechanical, template-generated ones** that an agent will produce when optimizing for "satisfy the structural check." The remaining evasions require a human-level understanding of validation semantics, and an agent sophisticated enough to craft those evasions is sophisticated enough to write real validators.

### The Rejection Branch Requirement Closes the Biggest Gap

Pyre's Round 1 proposal checks for control flow as "direct children" of the function body. This is too permissive — it accepts `if isinstance(x, object): pass`. I propose a stricter structural requirement:

**A `@validates_external` function must contain at least one unconditional rejection path:** a `raise` statement or a `return` of a falsy sentinel that is reachable from the function's top-level control flow. The absence of a rejection path means the function accepts all inputs — by definition, it validates nothing.

This catches Riven's three examples:
- `isinstance(x, object)` — no rejection path (the `if` body just has `pass`)
- `if data: return data` — no `raise`, no `except`
- Dead-code validator returning `raw` — the `raise` is inside `except`, which is a rejection path for the parse failure, but `return raw` at the end accepts all *parseable* inputs without validating them... this one is harder. It requires checking that the return variable was assigned inside the validation logic, which is a mini data-flow check.

I'm not claiming this catches everything. I'm claiming it raises the bar from "any control flow" to "control flow that can actually reject input," which eliminates the degenerate cases.

### Defending 18 Samples Per Rule Against Maintenance Burden

The scribe rightly asks: does a 126-entry corpus become the stale evidence problem I warned about?

**No, because corpus entries have a fundamentally different lifecycle from allowlist entries.**

Allowlist entries go stale when the code they excuse changes — they're tied to a moving target (the codebase). Corpus entries go stale only when the *language of evasion changes* — they're tied to a slow-moving target (Python syntax patterns and agent generation tendencies).

Concretely:
- An allowlist entry for `core/config.py:R1:ConfigLoader:fp=a3b4c5` goes stale the moment someone refactors `ConfigLoader`. This happens weekly.
- A corpus entry testing "`.get()` with default on a frozen dataclass field" goes stale only if we stop using frozen dataclasses or `.get()` stops being a Python method. This happens never.

**The maintenance cost is not 126 entries × annual review. It is:**
1. **Initial creation:** ~2 hours per rule (including sourcing 30% from real PR violations). One-time.
2. **Adversarial additions:** ~2 entries per quarter per rule, from red-team and production evasion discoveries. Append-only.
3. **Rule-change verification:** When a rule changes, corpus tests run automatically. No manual review needed unless they fail.

The snapshot-based regression (full-scan of `src/elspeth/`) does need periodic review — but the per-snippet corpus entries are self-maintaining. A failing corpus test is a signal, not a chore.

**The 18-per-rule minimum is the cost of earning blocking status.** A rule that can't justify 18 labelled examples shouldn't be blocking CI. If the evidence burden feels heavy, that's evidence the rule isn't well-understood enough to enforce.

## Proposed Verdict

1. **Structural validation stays**, with a strengthened requirement: `@validates_external` functions must contain at least one rejection path (`raise` statement reachable from top-level control flow, or `except` handler that re-raises or raises a new exception). "Has control flow" is necessary but insufficient; "has a rejection path" is the right bar.

2. **Tautological validator detection** is added as a focused set of AST checks: blocklist on `isinstance` targets (`object`, `type`), constant-valued test expressions, and truthiness-only checks. These are not comprehensive — they target the mechanical patterns agents will generate.

3. **The golden corpus includes ≥3 adversarial validator entries per rule** from Riven's taxonomy, with an append-only lifecycle. Riven's evasion examples from Round 1 become the seed corpus for this category.

4. **The residual risk is documented explicitly** in the tool's own output: "Structural verification confirms that `@validates_external` functions contain rejection logic. It cannot verify that the validation is semantically meaningful. Review validator implementations as part of code review." This is honest about limits without abandoning the mechanism.

5. **18 samples per rule remains the standard for blocking promotion.** The maintenance burden argument conflates corpus maintenance (low, entries are stable) with allowlist maintenance (high, entries track a moving codebase). These are different dynamics.
