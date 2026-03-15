# Round 3 — Steelman Synthesis: Pyre (Python AST Engineer)

## Steelman: Seren — Binary Taint Cleansing Creates a Compliance Ritual

Seren's argument is the most uncomfortable challenge I've faced in this roundtable, because it attacks not the *implementation* of my taint model but its *effect on the system it operates within*. The strongest version:

Binary taint cleansing with structural validator verification creates a closed loop where the tool generates its own false assurance. The mechanism: agents learn that `@validates_external` + one `isinstance` check + one `raise` satisfies the tool. They write minimum-viable validators. The tool marks taint as cleansed. CI passes green. The human reviewer sees green and moves on. No selective pressure exists to improve the validator, because the tool — which is now the authority on validation adequacy — says it's fine.

The critical move in Seren's argument is the comparison to the status quo: the current `enforce_tier_model.py` flags *every* `.get()` and says "human, please evaluate." It's noisy, but it never claims validation is adequate. My binary taint model trades false positives for false confidence — and in a system where false confidence is the primary threat vector (the entire discussion paper's thesis), that trade is net negative.

This is not a hand-wave. Seren identifies a concrete measurement blind spot: minimum-viable validators are invisible to precision measurement (they're true negatives — the tool *correctly* doesn't fire), invisible to the golden corpus (there are infinite structurally-valid-but-semantically-vacuous validators), and invisible to suppression rate (nothing is suppressed). The failure exists in a category no proposed metric can observe.

## Concession

Seren is right that binary cleansing is the wrong model. My Round 1 proposal treats validation as a binary gate: data passes through `@validates_external` and becomes "clean," full stop. This is architecturally equivalent to a firewall that says "this packet passed through the DMZ, therefore it's trusted" — without inspecting whether the DMZ actually filtered anything. The structural verification (control flow must exist) is the equivalent of checking that the DMZ has a firewall appliance powered on, not that its rules are correct.

Riven is also right — and the two attacks compose into something stronger than either alone. My conservative propagation rule (`dict containing tainted value → dict is tainted`) causes container contamination that suppresses Tier 1 findings. The concrete example is devastating: `combined = {"llm": tainted_response, "audit": recorder.get_state()}` makes `combined` tainted, so `.get()` on the audit path is suppressed. My model produces false assurance on *exactly the access patterns that matter most*.

Where I pushed back too hard in Round 1: I framed the AST's inability to distinguish types as a constraint to "embrace." It is a constraint — but I then designed a taint model that pretends it can resolve provenance through a binary gate, which is exactly the kind of false confidence the constraint should prevent. I tried to bridge the type-information gap with declarations and heuristics, but the bridge itself introduced failure modes worse than the gap.

## Synthesis: Provenance-Labelled Taint with Attenuation Semantics

Neither Riven's provenance labels alone nor Seren's attenuation alone is sufficient. But they compose into a model that addresses both the container contamination problem and the compliance ritual problem, within the constraints of what `ast.parse()` can deliver.

### The Two-Dimensional Taint State

Each variable in the `TaintMap` carries two independent properties:

| Dimension | Values | Source of Truth |
|-----------|--------|----------------|
| **Provenance** (where from?) | `TIER_1`, `TIER_2`, `TIER_3`, `UNKNOWN`, `MIXED` | Declaration model + heuristics |
| **Validation status** (has it been checked?) | `UNCHECKED`, `STRUCTURALLY_VALIDATED`, `VERIFIED` | Decorator + structural analysis |

Provenance comes from Riven. Validation status comes from Seren (with a rename: `tainted` → `UNCHECKED`, `validated-not-verified` → `STRUCTURALLY_VALIDATED`, `clean` → `VERIFIED`). The key insight: **provenance is never changed by validation.** Data from Tier 3 remains Tier 3-provenance forever — validation changes its *status*, not its *origin*.

### How Rules Evaluate Against Two Dimensions

```
RULE: .get() with default
  TIER_1 + any status     → VIOLATION (Tier 1 data must crash on missing key)
  TIER_2 + any status     → VIOLATION (pipeline data types are contracted)
  TIER_3 + UNCHECKED      → FINDING (external data not yet validated)
  TIER_3 + STRUCTURALLY_VALIDATED → SUPPRESSED (pattern-level noise)
  TIER_3 + VERIFIED       → SUPPRESSED
  MIXED                   → FINDING at reduced confidence (explain why)
  UNKNOWN                 → FINDING (provenance undetermined)

RULE: broad except without re-raise
  TIER_1 context          → VIOLATION (audit trail destruction)
  TIER_3 context          → SUPPRESSED (expected at external boundary)
  TIER_2/UNKNOWN context  → FINDING (needs human evaluation)

RULE: data reaches audit write path
  TIER_3 + UNCHECKED      → VIOLATION (unvalidated external data in audit)
  TIER_3 + STRUCTURALLY_VALIDATED → NOTE (structurally validated, semantic
                                     adequacy requires human review)
  TIER_1/TIER_2           → PASS (internal data, expected)
```

### Container Contamination Solved

Riven's devastating example now works correctly:

```python
combined = {
    "llm": llm_response,      # TIER_3 + UNCHECKED
    "audit": recorder.get(),   # TIER_1 + N/A
}
# combined → provenance: MIXED (contains both TIER_1 and TIER_3)

combined.get("audit", {})  # MIXED provenance → FINDING, not suppressed
```

`MIXED` provenance means "this container holds data from multiple tiers." The tool flags `.get()` on `MIXED` data rather than suppressing it, because it cannot determine which tier the accessed value belongs to. This is the *honest* answer — the AST genuinely cannot resolve this, so the tool says "I don't know, human please evaluate" rather than claiming it's clean.

### Compliance Ritual Mitigated

Seren's compliance ritual loop breaks at the "Tool reports GREEN" step. Under attenuation semantics, passing through `@validates_external` moves status from `UNCHECKED` to `STRUCTURALLY_VALIDATED` — which suppresses pattern-matching rules (`.get()` noise) but still emits a NOTE when that data reaches audit write paths. The note says: "External data from line 12 reaches audit write at line 45 via `validate_response()`. Structurally verified. Semantic adequacy requires human review."

The tool never claims validation is adequate. It claims validation is *structurally present*. The human remains the authority on semantic adequacy, and the tool makes their job easier by showing the flow rather than hiding it behind a green light.

### What Reaches `VERIFIED` Status?

Nothing, in v0.1. `VERIFIED` is reserved for v1.0 when inter-procedural analysis can verify that a validator's output schema satisfies its consumer's input requirements. In v0.1, the maximum attainable status is `STRUCTURALLY_VALIDATED`. This is by design — it preserves the human review feedback loop that Seren correctly identifies as essential, while still reducing `.get()` false positive noise to manageable levels.

### Implementation Cost

The `TaintMap` changes from `dict[str, bool]` to `dict[str, TaintState]` where `TaintState` is a 2-field struct. Propagation rules update both dimensions independently. The AST walk is unchanged in structure — only the state being tracked is richer. Performance impact: negligible (a few extra comparisons per variable lookup).

The rule evaluation layer becomes a lookup table (provenance × status → verdict) rather than the 5-level hierarchy. This is simpler to implement, easier to test, and more transparent to users — the verdict explanation can show both dimensions: "Flagged: `.get()` on MIXED-provenance data (TIER_1 + TIER_3 in container at line 8)."

### What This Synthesis Achieves That Neither Side Reaches Alone

- **Riven alone** solves container contamination but doesn't address the compliance ritual — provenance labels without attenuation still produce binary "is validation present?" checks.
- **Seren alone** solves the compliance ritual but doesn't prevent over-tainting from contaminating Tier 1 findings — attenuation without provenance labels still collapses all tiers into a single taint dimension.
- **The synthesis** preserves provenance through containers (solving contamination) AND refuses to claim semantic adequacy (solving compliance ritual), while staying within the stdlib `ast` constraint. The `TaintMap` architecture from my Round 1 proposal survives intact — only the state it tracks is richer.

I concede my binary model was wrong. I believe this synthesis is what the tool should build.
