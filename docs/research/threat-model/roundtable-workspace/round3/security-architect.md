# Round 3 — Steelman Synthesis: Sable (Security Architect)

## Steelman: Seren's Taint Attenuation Model (validated-not-verified)

Seren's three-state taint model — `tainted → validated-not-verified → clean` — is the position I initially found least convincing. My instinct as a security architect is that trust states should be binary: data either has the required assurance level or it doesn't. A middle state that says "something happened but we can't confirm what" feels like a bureaucratic hedge that weakens enforcement.

But the strongest version of Seren's position is not about hedging — it's about **preserving information that binary models destroy**. Here's what I mean:

In Pyre's binary model, passing through `@validates_external` *erases the history* of the data. Before the validator, the tool knows "this came from `requests.get()` and hasn't been checked." After the validator, the tool knows "this is clean." The provenance information is gone. The tool cannot tell you *how* the data was validated, *which* validator it passed through, or *whether that validator is adequate for the specific downstream operation*. If the data later reaches a Tier 1 audit write, the tool says "clean data reached audit write — no finding." The human reviewer sees no signal.

Seren's attenuation model preserves information: "this data came from an external source, passed through `validate_response()` which has structural control flow, and now reaches an audit write." The tool doesn't claim the data is safe — it claims the data has been *processed by something that looks like validation*. This distinction matters precisely at the security boundary: when external data reaches Tier 1 operations, the difference between "we verified this" and "something with control flow touched this" is the difference between assurance and hope.

The compliance ritual concern is the strongest part: binary cleansing creates a one-bit gate (did data pass through a decorator?) that, once satisfied, eliminates all further scrutiny. In security terms, this is a **single point of trust** with no depth. Defence-in-depth requires that crossing one boundary doesn't eliminate all subsequent checks.

This is actually my own defence-in-depth principle applied against my own initial position. I was wrong to dismiss it.

## Concession

Seren is right that binary taint cleansing is a single point of failure. Once data is marked "clean," the tool's entire detection capability for that data flow is disabled. If the validator is inadequate — and static analysis cannot verify semantic adequacy — the tool provides false assurance on the most critical paths (external data reaching audit operations).

Seren is also right that the "validated-not-verified" state serves a real purpose: it tells the human reviewer "this is a data flow you should examine" without blocking the CI gate on every validated external data path. The blocking/advisory distinction maps well to the gate-plus-feedback model we converged on in Round 2.

Where I still disagree: the three-state model alone (tainted / validated-not-verified / clean) loses provenance. "Validated-not-verified" tells you the validation *status* but not the data's *origin tier*. Riven's provenance labels (TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED) tell you the *origin* but not the validation status. Both are single-axis models that capture one dimension while losing the other.

## Synthesis: Two-Dimensional Taint — Provenance × Validation Status

Neither Riven nor Seren would reach this alone because each designed their model to replace Pyre's binary taint on a single axis. The synthesis is to recognise that the two axes compose.

**The model:** Each variable in the taint map carries two labels:

| Dimension | Values | What it tracks |
|-----------|--------|----------------|
| **Provenance** | `TIER_1`, `TIER_2`, `TIER_3`, `UNKNOWN` | Where the data originated |
| **Validation** | `RAW`, `STRUCTURALLY_VALIDATED`, `UNTRACKED` | What processing has been applied |

The cross-product creates the rule evaluation space:

| Provenance | Validation | `.get()` finding? | Reaches audit write? | Reaches pipeline op? |
|-----------|-----------|-------------------|---------------------|---------------------|
| TIER_3 + RAW | Unvalidated external | Suppress (legitimate coercion) | **BLOCK** — unvalidated external reaching Tier 1 | **BLOCK** — unvalidated external in pipeline |
| TIER_3 + STRUCTURALLY_VALIDATED | Validated external | Suppress | **NOTE** — validated but adequacy unverified | Pass |
| TIER_2 + UNTRACKED | Pipeline data | **FINDING** — fabrication on pipeline data | Pass (pipeline data is legitimate in audit context) | Pass |
| TIER_1 + UNTRACKED | Audit data | **FINDING** — fabrication on audit data | Pass (reading audit data) | Pass |
| UNKNOWN + RAW | Can't determine | **FINDING** at reduced confidence | **FINDING** — unknown provenance reaching Tier 1 | **FINDING** at reduced confidence |
| MIXED | Container with mixed origins | **FINDING** — mixed provenance requires decomposition | **BLOCK** — mixed data must not reach audit | **FINDING** |

**Why this solves Riven's container contamination problem:** When tainted external data and Tier 1 audit data are combined in a dict, the result is `MIXED` provenance, not `TIER_3`. A `.get()` on `MIXED` provenance is a finding (the developer needs to decompose the access), and `MIXED` data reaching an audit write is a blocking finding. This is what Riven wanted — but with an explicit `MIXED` label rather than over-tainting that silently suppresses Tier 1 findings.

**Why this solves Seren's compliance ritual problem:** Passing through `@validates_external` changes validation status from `RAW` to `STRUCTURALLY_VALIDATED` but does *not* change provenance. TIER_3 data remains TIER_3 data after validation — the tool knows it came from outside and can emit a note when it reaches audit writes. The validator doesn't erase history; it adds a processing record. The human reviewer sees: "external data from `requests.get()` at line 12, structurally validated by `validate_response()` at line 20, reaches audit write at line 45." They evaluate whether the validator is adequate for this specific flow. The tool doesn't claim it's clean; it claims it's been processed.

**Why this is implementable in v0.1:** The `TaintMap` data structure changes from `dict[str, bool]` (binary taint) to `dict[str, TaintLabel]` where `TaintLabel` is a pair `(Provenance, ValidationStatus)`. Propagation rules are the same as Pyre's — assignments propagate both dimensions. The only new complexity is the `MIXED` state for container construction: `{a: tier3_var, b: tier1_var}` produces `MIXED` provenance. This is a constant-factor increase in implementation complexity, not an algorithmic change.

**Propagation rules for the two dimensions:**

```
PROVENANCE propagation:
  assignment from source:     inherits source provenance
  container with mixed:       MIXED
  function call return:       UNKNOWN (v0.1 — inter-procedural deferred)
  binary op (tier_a + tier_b): MIXED if different, same if identical

VALIDATION propagation:
  passes through @validates_external:  RAW → STRUCTURALLY_VALIDATED
  assignment:                          inherits source validation status
  container construction:              min(validation statuses)
  function call return:                UNTRACKED (v0.1)
```

**Rule evaluation becomes a lookup in the cross-product table** rather than a branching hierarchy. This is simpler to reason about, easier to test (each cell in the table is a test case), and produces more informative findings ("TIER_3 + RAW reaching audit write" vs. "tainted value reaching audit write").

**Addressing the scribe's observation on my heuristic list:** The provenance dimension actually *reduces* the heuristic list's attack surface. In Pyre's binary model, the heuristic list determines whether `.get()` is suppressed (binary consequence — high stakes). In the two-dimensional model, the heuristic list determines provenance labelling, and provenance is one of two dimensions used for rule evaluation. A missing entry in the heuristic list means a variable gets `UNKNOWN` provenance, which triggers findings at reduced confidence — not silent suppression. The failure mode of an incomplete heuristic list shifts from "silent pass" to "noisier than optimal," which is the correct direction for a security tool.
