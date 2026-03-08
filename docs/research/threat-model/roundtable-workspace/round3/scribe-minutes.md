# Round 3 — Scribe Minutes

**Scribe: Morgan (Roundtable Orchestrator)**

## Convergence Summary

Round 3 produced the roundtable's most significant structural convergence. Six of seven agents now propose some form of **two-dimensional taint model** combining provenance (where data came from) with validation status (what processing it received). The seventh (Quinn) proposes a reduced-dimension variant that is structurally compatible. Binary taint is unanimously rejected.

Three major concessions were recorded — each involving an agent abandoning a position they defended through two prior rounds. The roundtable is narrowing toward implementable consensus.

## Major Concessions

| Agent | Conceded Position | Conceded To | Significance |
|-------|--------------------|-------------|--------------|
| **Pyre** | Binary taint model (defended Rounds 1-2) | Riven (container contamination) + Seren (compliance ritual) | **MAJOR REVERSAL** — Pyre's taint model was the technical centrepiece of Round 1. Conceding it after two convergent attacks validates the scribe's Round 2 Observation 4. |
| **Seren** | "Feedback instrument, not gatekeeper" (Round 1) AND single immutable precision threshold (Round 1) | Sable (gatekeeper priority) + Pyre (empirical precision ceilings) | **DOUBLE CONCESSION** — Both of Seren's signature Round 1 positions yielded. New position: "enforcement gate whose enforcement data powers diagnostic signals." |
| **Gideon** | Decision-scoped exception matching (Round 1) | Iris (refactoring cliff-edge, auto-suppression trap) | **CONCESSION ON IMPLEMENTATION** — Insight preserved ("governance cost scales with decisions"), implementation abandoned (matching layer → metadata layer). |

## Position Shift Tracking (Full)

| Agent | Round 1 Position | Round 2 Position | Round 3 Position | Shift |
|-------|-----------------|-----------------|-----------------|-------|
| **Pyre** | Binary taint, 5-level hierarchy | Added alias tracker, attacked Seren's threshold | **Conceded binary taint. Proposed 2D model: provenance × validation status.** | MAJOR REVERSAL |
| **Sable** | Default-deny heuristic list, defence-in-depth | Attacked Seren's framing | **Conceded binary taint is single point of failure. Proposed full 2D model: provenance (TIER_1/TIER_2/TIER_3/UNKNOWN + MIXED) × validation (RAW/STRUCTURALLY_VALIDATED/UNTRACKED).** | SIGNIFICANT SHIFT |
| **Seren** | Feedback instrument, immutable 95% threshold, 4 archetypes | Clarified "block on governance, trends on code" | **Conceded gatekeeper-first AND per-rule thresholds. Proposed 3-layer Enforcement-Diagnostic Stack.** | DOUBLE CONCESSION |
| **Riven** | Structural validation insufficient, evasion taxonomy | Tier-labelled provenance (5 labels) | **Conceded to Quinn on nirvana fallacy. Proposed 6-label provenance model with validation integration.** | CONCESSION + EXTENSION |
| **Quinn** | 18 samples/rule, dual precision threshold | Rejection-path requirement, tautological detector | **Proposed 4-label provenance (EXTERNAL/INTERNAL/VALIDATED/UNKNOWN) with 4-severity grading.** | EXTENSION |
| **Gideon** | Decision-scoped exceptions in matching layer | (Owed response to Iris) | **Conceded matching layer to Iris. Proposed grouped fingerprint governance with divergence detection.** | CONCESSION ON IMPLEMENTATION |
| **Iris** | Dual enforcement profiles, SARIF-native design | Conceded dual profiles, proposed decision_group metadata | **Conceded binary cleansing overclaims. Mapped provenance to tier-contextualized SARIF findings.** | EXTENSION |

## DECIDED: Binary Taint — REJECTED (7/7)

Every agent now explicitly rejects binary taint cleansing. The convergence is unanimous:

| Agent | Rejection Basis | Proposed Replacement |
|-------|----------------|---------------------|
| Pyre | "Binary cleansing is architecturally equivalent to a firewall that checks the DMZ has an appliance powered on, not that its rules are correct" | 2D: Provenance (5 labels) × Validation (3 states) |
| Sable | "Binary cleansing is a single point of failure — once data is clean, tool's entire detection capability for that flow is disabled" | 2D: Provenance (4 labels + MIXED) × Validation (3 states: RAW/STRUCTURALLY_VALIDATED/UNTRACKED) |
| Seren | "Binary cleansing creates compliance ritual loop" | 3-layer stack with attenuation (tainted/attenuated/clean) |
| Riven | "Container contamination suppresses Tier 1 findings" | 6 flat provenance labels incorporating validation status |
| Quinn | "Binary taint treats validated data as clean — cannot express mixed-tier container rules" | 4 provenance labels × 4 severity grades |
| Gideon | (Implicit — focused on governance, accepted taint model from others) | Deferred to Pyre/Sable synthesis |
| Iris | "Binary cleansing overclaims — fabricating certainty violates ELSPETH's own data manifesto" | Provenance in engine, tier-contextualized messages at output |

**Scribe verdict: CLOSED.** Binary taint is dead. The replacement is a multi-dimensional model. The remaining question is the exact dimensionality and label set.

## EMERGING: Two-Dimensional Taint Model — Converging

All proposals share the same architectural insight: **provenance (where data came from) and validation status (what processing it received) are orthogonal dimensions that should be tracked independently.** The divergence is on granularity.

### Dimension 1: Provenance Labels

| Agent | Labels | TIER_1 | TIER_2 | TIER_3 | UNKNOWN | MIXED | Notes |
|-------|--------|--------|--------|--------|---------|-------|-------|
| Pyre | 5 | Yes | Yes | Yes | Yes | Yes | Full model |
| Sable | 4+MIXED | Yes | Yes | Yes | Yes | Yes (in cross-product) | Full model — MIXED appears as derived state in cross-product table |
| Riven | 3+MIXED+UNKNOWN | Yes | Yes | Yes | Yes | Yes | Functionally identical to Pyre |
| Quinn | 4 | — | — | — | Yes | — | EXTERNAL, INTERNAL, VALIDATED, UNKNOWN |
| Seren | 3 | Yes | Yes | Yes | — | — | Deferred to Riven/Pyre for details |
| Iris | 5 | Yes | Yes | Yes | Yes | Yes | Adopted Riven's model directly |

**Key disagreement: Should TIER_1 and TIER_2 be distinct?**

- **Yes (Pyre, Sable, Riven, Iris, Seren):** Different rules apply — `.get()` on Tier 1 is catastrophic (audit trail corruption), `.get()` on Tier 2 is a bug (upstream contract violation). The distinction matters for severity. Sable's Round 3 cross-product table explicitly uses both TIER_1 and TIER_2 with different rule outcomes.
- **No (Quinn):** "The Tier 1/Tier 2 distinction is not AST-observable. Both are 'our data' — the difference is whether it's the audit trail or pipeline data, and that's a semantic distinction the AST can't make."

**Scribe assessment:** Quinn's objection is technically correct — the AST cannot distinguish Tier 1 from Tier 2 by inspection. The distinction depends on decorators or manifest declarations. Since the tool already uses decorators for `@external_boundary` and `@validates_external`, using `@internal_data` (or equivalent) for Tier 1/2 distinction is architecturally consistent. The question is whether the additional declaration burden is worth the rule precision gain. **Round 4 should resolve this.**

**Key disagreement: How should MIXED be handled?**

- **Explicit MIXED label (Pyre, Riven, Sable, Iris):** Container with values from different tiers gets MIXED provenance. Rules evaluate conservatively on MIXED.
- **Collapse to UNKNOWN (Quinn):** "MIXED is a testing problem — a garbage-can state that will accumulate without clear corpus verdicts."
- **Conservative default (Seren):** Deferred but aligned with MIXED concept via attenuation.

**Scribe assessment:** Quinn's concern about testability is valid — MIXED needs clear corpus verdicts. But Quinn's solution (collapse to UNKNOWN) loses information: UNKNOWN means "we don't know the provenance" while MIXED means "we know the provenance but it's heterogeneous." These should trigger different developer actions. **Recommendation: keep MIXED, define clear corpus verdicts for it.** Quinn should address this in Round 4.

### Dimension 2: Validation Status

| Agent | States | UNCHECKED/RAW | STRUCTURALLY_VALIDATED | VERIFIED/CLEAN | Notes |
|-------|--------|---------------|----------------------|---------------|-------|
| Pyre | 3 | UNCHECKED | STRUCTURALLY_VALIDATED | VERIFIED (reserved for v1.0) | |
| Sable | 3 | RAW | STRUCTURALLY_VALIDATED | UNTRACKED (for internal data) | Active in model — TIER_1/TIER_2 rows use UNTRACKED status |
| Seren | 3 | TAINTED | ATTENUATED | CLEAN | |
| Iris | 2 | validated=false | validated=true | — | Boolean flag, not enum |
| Quinn | (collapsed into provenance) | — | — | — | VALIDATED as a provenance label |
| Riven | (embedded in provenance) | — | — | — | TIER_3_VALIDATED as label |

**Key disagreement: Is validation status a separate dimension or embedded in provenance?**

- **Separate dimension (Pyre, Sable, Seren):** Provenance never changes; validation status changes when data passes through a validator. Two independent axes.
- **Embedded in provenance (Riven, Quinn):** Validation is expressed as a provenance variant (TIER_3_VALIDATED or VALIDATED as a distinct provenance label).
- **Boolean flag (Iris):** Minimal representation — validated yes/no alongside provenance.

**Scribe assessment:** The separate-dimension model (Pyre/Sable/Seren) is cleaner because it preserves the invariant that **provenance never changes**. Riven's TIER_3_VALIDATED violates this — it's a compound state masquerading as a provenance label. Quinn's VALIDATED-as-provenance loses the origin information (you know it was validated but not where it came from originally). Iris's boolean flag is operationally identical to the separate dimension but loses the ability to express VERIFIED/CLEAN as a third state.

**Recommendation for Round 4: adopt two explicit dimensions.** Provenance: {TIER_1, TIER_2, TIER_3, UNKNOWN, MIXED}. Validation: {RAW, STRUCTURALLY_VALIDATED}. VERIFIED deferred to v1.0 (Pyre's proposal). This gives a 5×2=10 state matrix in v0.1. Riven and Quinn should respond to the dimensionality question.

## DECIDED: Gatekeeper-First Framing — ACCEPTED (7/7)

Seren's Round 3 concession closes this debate:

> "The tool is an enforcement gate whose enforcement data powers diagnostic signals."

All seven agents now agree:
1. The tool's primary function is blocking CI on violations (gatekeeper)
2. Diagnostic signals (suppression rate, violation velocity, validator concentration) are valuable but derivative
3. The exit code is determined by enforcement findings, never by diagnostic metrics
4. Both layers appear in every run output

**Scribe verdict: CLOSED.**

## DECIDED: Per-Rule Precision Thresholds with Immutable Floor — ACCEPTED (6/7)

Seren's concession on the precision threshold, combined with broad pre-existing support:

| Agent | Position |
|-------|----------|
| Seren | **Conceded.** "An immutable floor with per-rule earned thresholds... addresses my concern more surgically than my own proposal." |
| Pyre | Proposed the model (Round 2) |
| Quinn | Compatible — per-rule corpus supports per-rule thresholds |
| Sable | "Immutable threshold in default profile" — compatible |
| Riven | Monotonically non-decreasing — compatible constraint |
| Iris | No objection |
| Gideon | No objection |

**Parameters:**
- Floor: 80% precision, immutable in code
- Per-rule thresholds: earned via corpus evidence, monotonically non-decreasing
- Storage: CODEOWNERS-protected manifest
- R3 (hasattr): can block at ~99%
- R1 (.get()): can block at ~88%
- R4 (broad except): can block at ~85%

**Scribe verdict: CLOSED.**

## DECIDED: Decision-Scope Matching — REPLACED with Grouped Fingerprint Governance (Gideon concession)

Gideon conceded that decision-scoping belongs in the metadata/presentation layer, not the matching layer. The agreed model:

1. **Matching:** Per-finding fingerprints (Iris's model). Deterministic, refactoring-resilient, no auto-suppression.
2. **Governance:** `decision_group` metadata tag (Iris's proposal). Groups findings that share an architectural rationale.
3. **Lifecycle:** Group-level review with divergence detection (Gideon's synthesis). Review digest shows stale fingerprints, new unassigned findings, group health percentage.
4. **Review fields:** Group-level, not per-finding (Gideon's refinement). `decision_rationale` and `trust_tier` describe the decision, not each finding.

**Scribe verdict: CLOSED.** Gideon and Iris have converged. The remaining design work is implementation detail.

## EMERGING: Rule Evaluation Matrix (Provenance × Validation → Severity)

Multiple agents proposed concrete matrices mapping provenance × validation status to finding severity. These are broadly compatible but use different severity vocabularies:

| Agent | Severity Levels | Notes |
|-------|----------------|-------|
| Pyre | VIOLATION / FINDING / SUPPRESSED / NOTE | NOTE = "structurally validated, human review" |
| Sable | BLOCK / FINDING / NOTE / Suppress | |
| Quinn | ERROR / WARN / INFO / SUPPRESS | Explicitly testable — each maps to corpus verdict |
| Iris | error / warning / note | Maps to SARIF severity levels |
| Riven | Finding (critical) / Finding / Finding (low confidence) / Suppress | |

**Quinn's contribution is structurally strongest here** because the severity grades map directly to corpus verdicts:
- ERROR → corpus verdict `true_positive` (must fire, blocking)
- WARN → corpus verdict `true_positive_reduced` (fires at reduced confidence)
- INFO → corpus verdict `true_note` (emitted, non-blocking)
- SUPPRESS → corpus verdict `true_negative` (must not fire)

**Iris's contribution is operationally strongest** because the severity levels map to real integration points:
- error → exit 1 (block CI)
- warning → exit 1 (block CI)
- note → exit 3 (advisory, GitHub annotation at "notice" severity)

**Scribe recommendation:** Adopt Quinn's 4-level severity vocabulary for corpus testing AND Iris's exit code mapping for integration. These are compatible — ERROR/WARN → exit 1, INFO → exit 3, SUPPRESS → no output.

## EMERGING: Enforcement-Diagnostic Stack (Seren)

Seren proposed a three-layer architecture that integrates enforcement and diagnostics:

| Layer | Function | Owner |
|-------|----------|-------|
| **Layer 1: Enforcement Gate** | Blocks CI on findings from rules above precision threshold | Sable's priority |
| **Layer 2: Taint Attenuation** | Provenance × validation status tracking, rule evaluation | Pyre/Riven/Seren synthesis |
| **Layer 3: Enforcement Diagnostics** | Suppression rate, violation velocity, validator concentration, exception age | Seren's contribution |

This framing is useful as an architectural organising principle. Layer 3 metrics are derived from Layer 1 data — they don't introduce new detection logic, they interpret enforcement patterns. **No agent has objected to this framing.** Round 4 should confirm or refine it.

## Novel Concepts Introduced in Round 3

| Concept | Introduced by | Description |
|---------|--------------|-------------|
| **Two-dimensional taint: provenance × validation** | Pyre, Sable (independently) | Replace binary taint with two orthogonal dimensions tracked per variable |
| **VERIFIED deferred to v1.0** | Pyre | Maximum validation status in v0.1 is STRUCTURALLY_VALIDATED; VERIFIED requires inter-procedural analysis |
| **Enforcement-Diagnostic Stack** | Seren | Three-layer architecture: enforcement gate, taint attenuation, enforcement diagnostics |
| **Attenuation-to-clean ratio** | Seren | Metric tracking proportion of data in "validated but unverified" state |
| **Validator concentration metric** | Seren | Number of distinct data flows per validator — single-point-of-failure risk signal |
| **Grouped fingerprint governance** | Gideon | Per-finding fingerprints for matching + decision_group for lifecycle, with divergence detection at review |
| **4-category corpus verdict system** | Quinn | ERROR/WARN/INFO/SUPPRESS mapped to true_positive/true_positive_reduced/true_note/true_negative |
| **Tier-contextualized SARIF messages** | Iris | Same rule ID with different provenance produces different messages, severities, and developer actions |
| **Provenance metadata in SARIF properties** | Iris | `provenanceSource`, `provenanceSourceLine`, `validated` fields in SARIF result properties |

## Scribe Observations

### Observation 1: The Label Set Must Be Decided in Round 4

The two-dimensional model is consensus. The exact label set is not. Three variants are on the table:

- **Full model (Pyre/Sable/Riven/Iris):** 5 provenance × 2-3 validation = 10-15 states. Sable's model is functionally equivalent to Pyre's (both keep TIER_1/TIER_2 distinct, both include MIXED).
- **Reduced model (Quinn):** 4 collapsed labels with embedded validation = 4 states

The full model is the majority position (4 agents) and more expressive, but creates a larger corpus requirement. The reduced model is simpler but loses information (TIER_1/TIER_2 distinction, MIXED vs UNKNOWN). **Round 4 must converge on a single label set or document the trade-off as a design decision with explicit rationale.**

### Observation 2: Quinn's Testability Argument is Under-Addressed

Quinn consistently centres testability — every design element must map to a corpus verdict with clear pass/fail criteria. This is the strongest methodological constraint in the roundtable, and several proposals don't yet meet it:

- Seren's "notes" — what is a correct note vs. an incorrect note?
- Riven's MIXED — what is the corpus verdict for a finding on MIXED-provenance data?
- Pyre's NOTE (TIER_3 + STRUCTURALLY_VALIDATED reaching audit write) — is this testable as a finding or an advisory?

**Round 4 must ensure every cell in the provenance × validation × rule matrix has a defined corpus verdict.** Empty cells are design gaps, not testing gaps (Quinn's correct framing).

### Observation 3: Iris's Integration Insight is Load-Bearing

Iris's observation that "notes" have no integration pathway in existing developer workflows (pre-commit, CI, SARIF, PR annotations) is the most practical constraint in Round 3. Any output category the tool produces must map to an actionable integration point:

| Output | Pre-commit | CI exit code | SARIF level | GitHub annotation |
|--------|-----------|-------------|-------------|-------------------|
| ERROR | Block | 1 | error | Error |
| WARN | Block | 1 | warning | Warning |
| INFO/NOTE | Pass | 3 (advisory) | note | Notice |
| SUPPRESS | — | — | — | — |

If the tool's output doesn't fit this table, it won't reach the developer. **Round 4 proposals must specify their integration mapping.**

### Observation 4: Container Contamination Is Solved in Principle

Every agent who addressed Riven's container contamination example reached the same conclusion: mixed-tier containers get MIXED provenance, and findings on MIXED are conservative (flag, don't suppress). The mechanism varies (Pyre: MIXED label; Quinn: UNKNOWN fallback; Iris: MIXED with contextual message) but the behaviour is consistent. **This is no longer a contentious design question — it's an implementation detail.**

### Observation 5: Three Items Remain for Round 4

1. **Exact label set** for provenance and validation status dimensions
2. **Complete provenance × validation × rule matrix** with corpus verdicts for every cell
3. **Integration mapping** for all output categories

Everything else (gatekeeper framing, per-rule thresholds, binary taint rejection, decision-scope governance, structural validation with rejection-path) is decided. Round 4 should focus exclusively on the three open items and produce a design that can be implemented.
