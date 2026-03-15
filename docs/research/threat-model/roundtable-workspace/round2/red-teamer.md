# Round 2 — Dissent: Riven (Adversarial Red-Teamer)

## Target: Pyre — The 5-Level Resolution Hierarchy for `.get()` False Positive Suppression

## Steelman

Pyre's proposal is the most technically honest position in Round 1. It explicitly catalogues what `ast.parse()` can and cannot do, identifies the `.get()` false positive problem as the hardest challenge (not taint propagation, not governance), and proposes a graduated resolution hierarchy:

1. **Decorator taint** — `.get()` on a variable assigned from `@external_boundary` → suppress (legitimate Tier 3)
2. **Heuristic source matching** — `.get()` on a variable assigned from `requests.get()`, `os.environ`, etc. → suppress
3. **Positional context** — `.get()` inside a Source plugin class → suppress (fragile, acknowledged)
4. **Manifest override** — `strict.toml` declares specific code as boundary → suppress
5. **Default: flag it** — if nothing above applies, report a finding

The hierarchy is elegant: it layers multiple imperfect signals from most reliable (explicit declaration) to least reliable (default assumption), and claims that if levels 1–4 catch the legitimate uses, the remaining level-5 findings will meet the 95% precision target. The `TaintMap` that flows forward through function bodies is the right architecture, and Pyre's acknowledgement of its own limitations (over-tainting, branch merge fragility, comprehension scoping) is unusually forthcoming.

This is the strongest technical proposal in the roundtable. That's exactly why its blind spot matters.

## Attack

**The hierarchy conflates two orthogonal concerns: taint state (a data-flow property) and finding suppression (a reporting decision).** Levels 1–2 answer "is this variable tainted?" while levels 3–5 answer "should we report this `.get()` call?" These are different questions with different failure modes, and mixing them in a single ordered hierarchy creates a class of errors that no individual level can catch.

### The Conflation Problem, Concretely

Consider this code in a transform's `process()` method:

```python
def process(self, row, ctx):
    # Call an LLM (external boundary)
    llm_response = self._client.query(row["prompt"])  # Tainted (level 1 or 2)

    # Validate the response
    parsed = self._validate_llm(llm_response)  # Cleansed (if _validate_llm is @validates_external)

    # Now access Tier 1 audit data
    audit_state = self._recorder.get_row_state(row["token_id"])

    # BUG: .get() on Tier 1 data — this is a genuine violation
    previous = audit_state.get("last_classification", "unknown")
```

The hierarchy processes this as follows:
- `llm_response` is tainted (level 1/2). `.get()` on it would be suppressed. Correct.
- `parsed` is cleansed. `.get()` on it would be flagged. Correct.
- `audit_state` is... what? It's not from an `@external_boundary`. It's not from the heuristic list. It's a return value from `self._recorder.get_row_state()`. The hierarchy reaches **level 5: flag it**. Correct.

But now change the scenario slightly:

```python
def process(self, row, ctx):
    llm_response = self._client.query(row["prompt"])

    # Agent "refactors" to combine results
    combined = {
        "llm": llm_response,
        "audit": self._recorder.get_row_state(row["token_id"]),
    }

    # .get() on combined — what tier is this?
    classification = combined.get("llm", {}).get("category", "unknown")
    previous = combined.get("audit", {}).get("last_classification", "unknown")
```

Now `combined` is a dict containing both tainted external data and Tier 1 audit data. Pyre's propagation rules say: `Dict/list literal: x = {"k": tainted} → x is tainted (conservative)`. So `combined` is tainted because it contains `llm_response`. Therefore `.get()` on `combined` is suppressed at level 1 — **including the `.get()` on the audit data path**. The taint from the LLM response has *contaminated the audit path's finding suppression*.

This is not a contrived example. It's exactly what happens when an agent refactors two separate data accesses into a "clean" combined dict. The refactoring is natural, the code works correctly at runtime, and the tool silently suppresses a genuine Tier 1 violation because conservative taint propagation made the container "look external."

### Over-Tainting Doesn't Degrade Gracefully — It Inverts

Pyre's Risk #1 acknowledges over-tainting: "If 20 out of 25 variables are tainted, the tool effectively says 'everything is fine.'" But Pyre frames this as a saturation problem — taint becomes meaningless when it's everywhere. The actual failure mode is worse: **over-tainting doesn't make the tool useless, it makes it actively misleading**.

When the tool suppresses `.get()` findings because the variable is "tainted" (i.e., from an external source where `.get()` is legitimate), it's telling the developer: "this access pattern is fine — you're at a trust boundary." If over-tainting causes Tier 1 data to be labelled as tainted, the tool gives **false assurance** on the most critical access paths.

The hierarchy's ordering (decorator → heuristic → positional → manifest → default) means that more specific signals are checked first. But taint propagation happens *before* the hierarchy runs — the `TaintMap` is populated in statement order, and by the time the `.get()` finding is evaluated, the variable's taint state is already determined. If the taint state is wrong (over-tainted), no amount of hierarchy ordering can fix it.

### The Heuristic List Is an Unfalsifiable Commitment

Level 2 (heuristic source matching) requires maintaining a list of "known external calls." Pyre proposes the list be extensible via `strict.toml`. But notice the asymmetry:

- **Adding to the list** (declaring a new external call pattern) is safe — it may cause false negatives on `.get()` but won't miss violations.
- **Omitting from the list** (failing to declare an external call) means the tool doesn't know the data is external, so `.get()` on it reaches level 5 and is flagged. This is a false positive.

The heuristic list therefore has a **one-directional pressure**: every false positive on `.get()` creates pressure to add the call to the heuristic list. Over time, the list grows to include more and more call patterns, each one expanding the tool's blind spot for Tier 1 data that happens to be returned by a function matching the pattern.

In ELSPETH specifically: `self._recorder.get_row_state()` is a method with `.get` in its name that returns a dict. If the heuristic list ever matches on `*.get*()` patterns (not inconceivable as it grows), Tier 1 reads become invisible.

## Proposed Verdict

The roundtable should **separate taint analysis from finding suppression** into two independent systems:

1. **Taint analysis** answers: "where did this data come from?" Its output is a provenance label per variable, not a suppress/flag decision. Provenance is not binary (tainted/clean) — it should be a tier label: `TIER_3`, `TIER_2`, `TIER_1`, `UNKNOWN`.

2. **Rule evaluation** answers: "given this variable's provenance, is this pattern a violation?" The rule for `.get()` becomes: "`.get()` with default on `TIER_1` or `TIER_2` data is a violation; on `TIER_3` data it is legitimate; on `UNKNOWN` it is a finding at reduced confidence."

This separation prevents the contamination problem: a dict containing both Tier 1 and Tier 3 data gets provenance `MIXED` or `UNKNOWN`, and `.get()` on it is flagged (with context explaining why), rather than silently suppressed because one ingredient was external.

Pyre's `TaintMap` is the right data structure — but it should track provenance tiers, not binary taint. The 5-level hierarchy should be replaced with tier-aware rule evaluation. Levels 3–5 (positional context, manifest override, default flag) remain useful as the fallback when provenance is unknown, but they should never override a known provenance determination.
