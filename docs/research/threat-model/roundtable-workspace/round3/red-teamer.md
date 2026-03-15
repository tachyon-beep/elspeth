# Round 3 — Steelman Synthesis: Riven (Adversarial Red-Teamer)

## Steelman: Quinn — "Structural Validation Is Sufficient With Bounded Tautological Detection"

Quinn's Round 2 counter-attack is the strongest rebuttal to my Round 1 position and I need to engage with it honestly.

Quinn's argument has three pillars, each independently strong:

**Pillar 1: The nirvana fallacy.** My claim that structural validation is "fundamentally insufficient" implicitly compares it to a perfect alternative — one that verifies semantic adequacy of validators. That alternative doesn't exist and can't exist (halting problem). The real comparison is: structural validation with rejection-path requirements vs. no structural validation at all. The second option is strictly worse — it either trusts decorators unconditionally or eliminates validators entirely, both of which degrade the tool's false-positive management. Quinn is right that I identified a failure mode without proposing a superior mechanism.

**Pillar 2: The tautological space is bounded.** My examples (`isinstance(x, object)`, `if data: return data`, dead-code validator) feel like an unbounded evasion surface, but syntactically they fall into a small number of categories: constant-valued tests, always-true type checks, and return-target mismatches. Each category has a finite AST signature that can be detected. An agent generating "satisfy the linter" code will produce *mechanical* tautologies from this bounded space, not novel semantic evasions — and the rejection-path requirement catches the degenerate cases.

**Pillar 3: The golden corpus has a different lifecycle than the allowlist.** My implicit concern was that the corpus would go stale like the allowlist. Quinn correctly distinguishes them: corpus entries are tied to Python syntax patterns (stable), not to the evolving codebase (unstable). A corpus entry for "`.get()` with default on frozen dataclass" doesn't go stale when someone refactors the dataclass — it goes stale only if Python removes `.get()`. This makes the corpus a viable long-term backstop for the cases structural checks miss.

Quinn's complete picture — rejection-path requirement + tautological detector blocklist + adversarial golden corpus — is a pragmatic, implementable, and honestly-scoped solution to a problem I declared unsolvable.

## Concession

Quinn is right on two points I was wrong about:

**1. The rejection-path requirement is a genuine improvement, not a cosmetic one.** My Round 1 examples all fail the rejection-path test: `isinstance(x, object)` with `pass` has no `raise`; `if data: return data` has no rejection branch; the dead-code validator returns `raw` without the validated `result`. I treated these as proving structural validation is fundamentally broken, but they actually prove that the *original* structural check (any control flow) was too weak. The rejection-path check raises the bar meaningfully — a validator that can never reject input is not a validator, and the AST *can* detect this.

**2. I committed the nirvana fallacy on tautological detection.** Saying "you can't catch all tautologies" is true but irrelevant if you can catch the *mechanically generated* ones. The adversary model isn't a human cryptographer crafting novel evasions — it's an LLM that will reach for the nearest syntactic pattern that satisfies the check. That nearest pattern is almost always in the bounded tautological space. The cost of a novel tautological evasion (one that has a rejection path, passes the blocklist, but still validates nothing meaningful) is high enough to shift the economics away from evasion and toward just writing a real validator.

## Synthesis: Tier-Labelled Provenance with Quinn's Structural Graduation

Neither Quinn's structural-validation-is-sufficient position nor my structural-validation-is-insufficient position addresses the central unresolved question: **what should the taint model be?** Both of us were arguing about validator verification while the taint propagation architecture — the load-bearing question per Scribe Observation 3 — remained unresolved. Here is a synthesis that integrates my provenance labels, Quinn's structural graduation, and Seren's attenuation insight into a single coherent model.

### The Provenance-Aware Taint Model

**Variables carry a tier label, not a binary taint flag:**

| Label | Meaning | Source |
|-------|---------|--------|
| `TIER_3` | External data, unvalidated | `@external_boundary` returns, heuristic-matched calls |
| `TIER_3_VALIDATED` | External data that passed through a structurally verified validator | Return value of `@validates_external` function |
| `TIER_2` | Pipeline data (function parameters in transforms, source-emitted rows) | Declared via manifest or decorator |
| `TIER_1` | Audit data (Landscape reads, checkpoint deserialization) | Declared via manifest |
| `MIXED` | Container holding data from multiple tiers | Dict/list/tuple containing values from different tiers |
| `UNKNOWN` | Provenance cannot be determined | Default for untracked variables |

**Key design decision: `TIER_3_VALIDATED` is NOT equivalent to `TIER_2`.** This is where Seren's insight integrates. A validator structurally verified by Quinn's rejection-path check gives *structural confidence* but not *semantic certainty*. The label tracks this distinction explicitly.

### Rule Evaluation on Provenance Labels

| Rule | TIER_3 | TIER_3_VALIDATED | TIER_2 | TIER_1 | MIXED | UNKNOWN |
|------|--------|-----------------|--------|--------|-------|---------|
| `.get()` with default (R1) | Suppress | Suppress | **Finding** | **Finding (critical)** | **Finding** | Finding (low confidence) |
| Broad except (R4) | Suppress | Note (review validator) | **Finding** | **Finding (critical)** | **Finding** | Finding |
| `hasattr` (R3, banned) | Finding | Finding | Finding | Finding | Finding | Finding |
| Data reaches audit write | **Finding** | Note (validator adequate?) | Pass | Pass | **Finding** | **Finding** |

**The critical row is "data reaches audit write."** Under binary taint, `TIER_3_VALIDATED` data is "clean" and reaches audit writes silently. Under provenance labels, `TIER_3_VALIDATED` data reaching an audit write emits a *note* — not a blocking finding, but a visible annotation that says: "external data from `requests.get()` at line 12 reaches `recorder.record_state()` at line 45 via `validate_response()` at line 20. Validator structurally verified. Semantic adequacy requires human review."

This is Seren's "validated-not-verified" concept, but attached to my provenance labels rather than as a standalone taint state. The note makes the data flow visible without blocking CI, preserving Quinn's practical concern about tool adoption while addressing Seren's concern about displaced human review.

### Why Neither Side Reaches This Alone

- **My Round 1 position** (provenance labels without structural graduation) would treat all validators equally — a validator with a rejection path and one with `isinstance(x, object)` both produce `TIER_3_VALIDATED`. Quinn's rejection-path requirement and tautological detector *differentiate validator quality at the structural level*, which my provenance model consumes but doesn't generate.

- **Quinn's position** (structural validation is sufficient) operates on binary taint and treats validated data as clean. It cannot express the rule "`.get()` is fine on validated external data but dangerous on audit data mixed into the same container" because it doesn't track provenance — only taint/clean.

- **Seren's position** (taint attenuation) captures the validation-status dimension but not the origin-tier dimension. It can't distinguish "validated Tier 3 data" from "validated Tier 2 data" — both are "validated-not-verified."

The synthesis gives each rule access to both dimensions: where the data came from (tier) and what happened to it (validation status). This is a 2D model collapsed into 6 labels, implementable as a simple enum with no runtime overhead beyond what binary taint already requires.

### Addressing the Container Contamination Problem

My Round 2 attack showed that a dict containing both Tier 3 and Tier 1 data becomes uniformly "tainted" under binary taint, suppressing findings on the Tier 1 path. Under provenance labels:

```python
combined = {
    "llm": llm_response,        # TIER_3
    "audit": audit_state,        # TIER_1
}
# combined is MIXED — not TIER_3, not TIER_1

combined.get("audit", {})  # Finding: .get() on MIXED data
```

`MIXED` is never suppressed for `.get()` — the tool doesn't know which tier the accessed key belongs to, so it flags conservatively. This is a false positive if the developer accesses only the Tier 3 portion, but that's the correct trade-off: false positive on mixed-tier containers is better than false suppression of Tier 1 violations. The developer can either destructure the dict (separate variables, separate provenance) or add an allowlist entry with a rationale explaining the access pattern.

### What This Costs

Provenance tracking adds 4 additional labels to the taint state (vs. binary's 2). The propagation rules are slightly more complex: binary operations on mixed tiers produce `MIXED`, function calls to undecorated functions produce `UNKNOWN`, and container construction with mixed-tier values produces `MIXED`. This is a modest increase in implementation complexity for a significant gain in rule evaluation precision.

The golden corpus needs entries for each label state × rule combination, which increases Quinn's 18-per-rule to roughly 25-per-rule (additional entries for `MIXED` and `UNKNOWN` edge cases). This is within Quinn's acceptable range and the entries are stable (tied to Python syntax, not the codebase).
