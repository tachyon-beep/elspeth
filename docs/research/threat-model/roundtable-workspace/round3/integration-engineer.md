# Round 3 — Steelman Synthesis: Iris (Integration Engineer)

## Steelman: Seren — Taint Attenuation and "Validated-Not-Verified"

Seren's argument is the most uncomfortable position in this roundtable because it attacks the tool at the level of *system effects*, not *technical correctness*. The core claim: binary taint cleansing (tainted → passes through `@validates_external` → clean) creates a compliance ritual loop where validators satisfy structural checks without validating content, the tool reports GREEN, human review is displaced, and actual validation quality degrades. This is "Fixes that Fail" made concrete.

The strongest version of this argument goes beyond the specific mechanism. Even if we fix the taint model — even if we adopt Riven's provenance labels, Quinn's rejection-path requirement, and a tautological detector — the fundamental dynamic persists: **any automated gate that can be satisfied by structural compliance will eventually be satisfied by structural compliance alone.** A tool that says "data is clean because it passed through a validator" is making a claim stronger than its evidence supports, and that overclaim displaces the human judgment that would have caught the gap.

Seren's proposed three-state model (tainted → validated-not-verified → clean) addresses this by making the tool honest about what it actually knows. The tool knows data passed through something decorated as a validator. It does *not* know whether the validation was adequate. The middle state encodes this epistemological humility into the taint engine itself, rather than hoping the developer reads between the lines of a binary GREEN.

The "notes" mechanism — showing data flow paths through validators for human review — is the logical consequence: if the tool can't determine adequacy, it should make the flow visible so a human can. This is Seren's "feedback instrument" concept applied at the taint level, and it's internally consistent.

## Concession

Seren is right about two things:

**1. Binary cleansing overclaims.** A tool that says "clean" after `@validates_external` is asserting something it cannot verify. In ELSPETH's trust model, this matters enormously — the Landscape audit trail demands that "I don't know what happened" is never an acceptable answer. A tool that reports "clean" when it means "structurally validated, semantic adequacy unknown" is fabricating certainty. By the project's own data manifesto, that's Tier 1 behaviour: if you can't prove it, don't claim it.

**2. The compliance ritual is real, not theoretical.** I've seen it with the existing `enforce_tier_model.py`. When the tool flags a `.get()` and the developer writes an allowlist entry with `safety: "Checked by upstream validation"`, the review process accepts that claim at face value. Nobody navigates to the upstream validation to verify it actually validates the relevant field. The structured allowlist entry *looks* like due diligence. The existing tool already creates this dynamic; a taint engine that reports "clean" would intensify it.

## Synthesis

Here's what neither side has addressed: **what does the developer actually see?**

Seren's attenuation model is correct about the epistemological gap but wrong about the output mechanism. The "validated-not-verified notes" proposal creates a third output category (not-finding, not-suppression, note) that maps to nothing in existing developer workflows. It doesn't appear as a SARIF finding. It doesn't trigger a CI exit code. It doesn't show up in PR annotations. In every integration context I've designed — pre-commit, CI, agent `--stdin` — output is binary: finding or not-finding, pass or fail. A "note" is, operationally, a verbose log line that gets piped to `/dev/null`.

Riven's provenance model is correct about the taint representation but hasn't connected it to actionable developer output. Five provenance labels (TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED) give the rule engine perfect information, but the developer sees... what? An error message that says "`.get()` on TIER_2 data"? They need to understand the tier model to act on it.

**My synthesis: provenance-labelled taint (Riven) with tier-contextualized findings (new) and attenuation expressed as rule confidence, not taint state (reframing Seren).**

### 1. Taint engine tracks provenance, not validation status

The `TaintMap` tracks `TIER_1 | TIER_2 | TIER_3 | UNKNOWN | MIXED` per variable, as Riven proposes. Passing through `@validates_external` does NOT change the provenance label — data from `requests.get()` that passes through a validator is still `TIER_3` provenance. What changes is the *validation status*, tracked as a separate boolean flag on the taint entry: `(provenance=TIER_3, validated=True)`.

This addresses Seren's overclaim concern without introducing a third taint state. The taint engine knows two things: where data came from, and whether it passed through a declared validator. It makes no claim about validation adequacy.

### 2. Rule evaluation uses provenance for applicability and validation status for confidence

The `.get()` rule becomes:

| Provenance | Validated? | Finding | Level | Message |
|-----------|-----------|---------|-------|---------|
| TIER_1 | N/A | YES | error | `.get("key", default)` on audit data fabricates values on corruption — crash, don't mask |
| TIER_2 | N/A | YES | error | `.get("key", default)` on pipeline data hides upstream plugin bugs — crash, don't mask |
| TIER_3 | No | NO | — | Legitimate boundary handling — `.get()` with default is correct for untrusted data |
| TIER_3 | Yes | NO | — | Data validated and accessing with default — both legitimate |
| UNKNOWN | No | YES | warning | Unable to determine data provenance — `.get()` with default may fabricate values |
| UNKNOWN | Yes | YES | note | Data passed through validator but provenance unknown — review whether `.get()` default is appropriate |
| MIXED | N/A | YES | warning | Container mixes data from multiple tiers — `.get()` default may mask corruption on trusted components |

The `MIXED` row is Riven's contamination case solved without binary over-tainting. The `UNKNOWN + validated` row is Seren's "validated-not-verified" concept expressed as a finding with reduced severity, not a separate taint state.

### 3. Findings carry provenance context in the message, not just the rule ID

This is the integration insight neither side reached: **the same rule ID with different provenance produces different messages.**

Pre-commit output:
```
src/elspeth/engine/processor.py:142:8  SBE-T02  .get() with default on audit data (Tier 1)
  │ row_state.get("last_seen", None)
  │ ↑ provenance: TIER_1 via self._recorder.get_row_state() at :138
  │ Audit data must crash on anomaly, not fabricate defaults.
```

vs.

```
src/elspeth/engine/processor.py:156:8  SBE-T02  .get() with default on unknown-provenance data
  │ combined.get("metadata", {})
  │ ↑ provenance: MIXED (TIER_3 from api_response :150 + TIER_1 from audit_state :152)
  │ Container mixes trust tiers. Consider separating access paths.
```

Same rule, different provenance, different severity, different message, different developer action. The SARIF output includes provenance metadata in the `properties` field:

```json
"properties": {
  "provenance": "TIER_1",
  "provenanceSource": "self._recorder.get_row_state()",
  "provenanceSourceLine": 138,
  "validated": false
}
```

### 4. Exit codes map provenance-aware severity to CI gates

| Finding severity | Pre-commit | CI | Agent `--stdin` |
|-----------------|-----------|-----|-----------------|
| error (TIER_1/TIER_2 violations) | Block | Block (exit 1) | Exit 1 |
| warning (UNKNOWN/MIXED) | Block | Block (exit 1) | Exit 1 |
| note (UNKNOWN+validated) | Pass | Pass (exit 3, advisory) | Exit 3 |

Notes — Seren's "validated-not-verified" concept — exist in the output but don't block. They appear as GitHub PR annotations at "notice" severity. They're visible but not gating. This respects Seren's insight (the tool shouldn't claim adequacy) while respecting the operational reality that non-blocking output needs a home in the workflow or it disappears.

### Why neither side reaches this alone

Riven's provenance model gives the taint engine the right information but doesn't specify how it reaches the developer. Seren's attenuation model correctly identifies the overclaim but proposes an output mechanism (notes) that has no integration pathway. The synthesis: provenance in the engine, tier-contextualized messages at the output, validation status as a confidence modifier rather than a taint state, and severity mapping that gives the "validated-not-verified" concept a real home (advisory annotations) rather than a theoretical one (notes that go nowhere).

The developer sees *why* their `.get()` is wrong *here* — because the data came from `self._recorder` (Tier 1), or because the container mixes trust tiers — not just *that* it's wrong. Provenance context in the finding message is the difference between "fix this" and "understand this."
