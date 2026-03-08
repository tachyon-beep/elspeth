# Round 5 — Scribe Minutes

**Scribe: Morgan (Roundtable Orchestrator)**

## Commitment Status

All seven agents commit to the decided design. The roundtable is closed.

| Agent | Commitment | Minority Reports | Conditions |
|-------|-----------|-----------------|------------|
| **Pyre** | Commit | 1 filed (INTERNAL alias) | None |
| **Sable** | Commit | 2 filed (INFO boundaries, decorator-consistency gaps) | None |
| **Seren** | Commit | 2 filed (ERROR rate erosion, INFO validated-not-verified) | None |
| **Riven** | **Conditional commit** | 0 filed | INFO action-rate metric must ship in v0.1 |
| **Quinn** | Commit | 1 filed (embedded validation — self-closed) | None |
| **Gideon** | Commit | 0 filed | None |
| **Iris** | Commit | 0 filed | None |

**Commitment is 7/7.** Six unconditional, one conditional. Riven's condition is concrete and resolvable (see §Conditional Commitments).

## Minority Reports Filed

Five minority reports were filed across three agents. All are non-blocking — they identify enhancement paths, not design flaws.

### MR-1: @internal_data Alias for TIER_2 (Pyre)

**Position rejected:** The public API should offer `@internal_data` as syntactic sugar resolving to TIER_2 at parse time.

**Argument:** Most transform authors will never need TIER_1. Forcing a choice between `@tier2_data` and `@audit_data` when developers mean "this isn't external" creates friction that pushes toward UNKNOWN (no annotation at all). `@internal_data` captures the intent without the cognitive load.

**Why not blocking:** This is a UX convenience, not a semantic objection. The taint engine, matrix, and governance model are unaffected. Implementable as a post-v0.1 alias without design changes.

**Scribe assessment:** Pyre applies Iris's developer experience arguments to the declaration surface. The argument has merit — annotation friction is a real adoption risk (Seren independently identifies this as the "annotation treadmill" in Risk 3). However, the alias could mask genuine TIER_1 data behind a TIER_2 default. The correct resolution is documentation: explain when `@audit_data` (TIER_1) vs `@pipeline_data` (TIER_2) applies, and let developers choose.

### MR-2: INFO Advisory Boundary Conditions (Sable)

**Position accepted with reservations:** INFO is advisory (exit 3) for v0.1.

**Boundary conditions registered:**

| Condition | Threshold | Effect |
|-----------|-----------|--------|
| INFO action-rate | <5% after 6 months | Reclassify affected cells to SUPPRESS |
| Team size | >15 engineers | "Someone reads notices" assumption fails — implement Riven's Option 2 (threshold gate) |
| Agent-generated code share | >50% of new data flows | Compliance laundering surface becomes majority case — revisit Riven's Option 1 |

**Why not blocking:** The INFO surface is narrow (5 cells, 10% of matrix). Defence-in-depth via SARIF persistence, trend analysis, and review annotations provides multiple catch points. Sable's concern is about *scaling assumptions*, not *current design adequacy*.

**Scribe assessment:** Sable provides the most precise framing of when the INFO decision should be revisited. The three thresholds (action-rate, team size, agent code share) are measurable triggers, not vague concerns. These should appear in the specification as documented assumptions.

### MR-3: Decorator-Consistency Checker Gaps (Sable)

**Position accepted with documented limitations:** The decorator-consistency checker ships in v0.1 as a first-pass rule.

**Two gaps identified:**

| Gap | Description | Detection |
|-----|-------------|-----------|
| **Scenario C** | Function with correct `@external_boundary` returns mixed-provenance dict (TIER_3 API response + TIER_1 tracking ID). Consistency checker says "consistent." TIER_1 data painted as TIER_3. | Requires inter-procedural return-value analysis (v1.0+) |
| **Decorator omission** | Functions with no decorator default to TIER_2. Undecorated function calling external API → return is TIER_2 → defensive patterns become ERROR findings instead of SUPPRESS. | Detectable via coverage metrics ("N functions in transform plugins make external calls without provenance decorators") |

**Sable's recommendation:** Ship checker in v0.1. Add decorator omission detection in v0.2 via Layer 3 coverage report. Document both gaps as known limitations (KL-2a, KL-2b).

**Scribe assessment:** The checker catches mechanical mislabelling — the high-volume case that agents will produce. The residual gaps (Scenario C and omission) are code review concerns with concrete v0.2/v1.0 remediation paths.

### MR-4: 39% ERROR Rate and Eroding Goals (Seren)

**Position accepted with system dynamics warning:** The 39% ERROR rate (19 of 49 cells) is correct for ELSPETH's current context.

**Residual risk:** The 25 governable cells (STANDARD + LIBERAL) represent 51% of the matrix. Under false-positive pressure, the path of least resistance is exception proliferation rather than cell reclassification (which the precision ratchet prevents). The suppression rate metric catches this, but it has no automatic escalation.

**What Seren would change:** A suppression rate threshold that auto-elevates from Layer 3 diagnostic to Layer 1 concern (SARIF finding: "suppression rate on R4/TIER_2 exceeds 30%"). Accepts this is over-engineering for v0.1.

**Scribe assessment:** Seren correctly identifies that the design's three structural defences (24 UNCONDITIONAL cells, precision ratchet, suppression rate visibility) address cell reclassification but not exception accumulation. The distinction matters — both erode enforcement, but through different mechanisms. The suppression rate metric is the right sensor; the missing piece is the actuator.

### MR-5: Embedded Validation for v0.1 (Quinn)

**Position rejected:** Treat validation as embedded in provenance (VALIDATED as a provenance label) rather than as a separate dimension.

**Quinn's rationale:** For v0.1's intra-function scope, `VALIDATED` as provenance is operationally equivalent to `TIER_3 × STRUCTURALLY_VALIDATED`. The 2D model creates UNKNOWN+SV cells that carry less information than they appear to (if provenance is unknown, validation status is hard to interpret).

**Why self-closed:** Quinn concedes the 2D model is *structurally* correct (provenance is immutable; validation status evolves) and that the migration debt from starting with the wrong abstraction outweighs the corpus size savings (~12 entries). "The roundtable optimized for conceptual integrity. They were right."

**Scribe assessment:** This minority report is notable because Quinn files and closes it in the same document. The 2D model won on structural correctness, not operational necessity. Quinn's residual note — that expanding validation to TIER_1/TIER_2/MIXED requires roundtable review because it expands effective states from 7 to 10 — is load-bearing and should appear in the specification.

## Conditional Commitments

### Riven: INFO Action-Rate Metric Must Ship in v0.1

**The only conditional commitment in the roundtable.**

Riven commits to the design on one condition: Quinn's INFO action-rate metric (measuring whether developers act on INFO findings) must be included in v0.1, not deferred to v0.2.

**Riven's argument:** "If INFO findings are advisory with no measurement of whether anyone acts on them, they are decorative. Quinn's metric is the difference between 'advisory with feedback loop' and 'advisory as a polite word for ignored.'"

**Quinn's operational definition resolves the condition.** Quinn provided a concrete measurement mechanism in Round 5:

| Component | Definition |
|-----------|-----------|
| **What counts as "action"** | Code change within the same PR or subsequent 3 commits that modifies the code region identified by an INFO finding |
| **What doesn't count** | Allowlist suppression without code change, merging without addressing, modifying unrelated code in same file |
| **Measurement mechanism** | SARIF finding fingerprints + git diff correlation (file:line-range ± 5 lines tolerance) |
| **Promotion threshold** | >30% action rate after 20+ observations → promote cell to WARN |
| **Suppression threshold** | <5% action rate after 50+ observations → reclassify cell to SUPPRESS |
| **Hold range** | 5–30% action rate → hold at INFO |

**Scribe assessment:** This condition is resolvable. The measurement mechanism is concrete (SARIF + git diff correlation), the thresholds are quantified, and the implementation is bounded (~50 lines of post-merge analysis). Riven's conditional commitment becomes unconditional once this ships. The condition does not block design closure — it's a v0.1 implementation commitment, not a design disagreement.

## Implementation Concerns Surfaced

### Pyre: 5 AST Edge Cases

None of these are design objections. All are implementation concerns with identified mitigations.

| # | Edge Case | Risk | Mitigation | Effort |
|---|-----------|------|-----------|--------|
| 1 | **Walrus operator in comprehensions** — `:=` targets leak to enclosing scope; comprehension variables don't | Taint map pollution or loss | Shadow scope for comprehension variables; walrus targets write to enclosing scope | ~20 lines |
| 2 | **Method decorator resolution** — `self.fetch()` must link to `@external_boundary` on class method | Breaks for aliased self, passed-in instances, inherited methods | Restrict to direct `self` references in v0.1 (zero aliased-self instances in ELSPETH codebase) | Bounded |
| 3 | **MIXED unpacking** — `a, b = mixed_container[k1], mixed_container[k2]` | Cannot determine per-element provenance from AST | All unpacked variables from MIXED inherit MIXED (conservative, sound) | Trivial |
| 4 | **f-string interpolation** — `f"{tier3_var}"` produces MIXED string | Not consumed by v0.1 rules but positions for v0.2 injection rules | Implement propagation as infrastructure (~15 lines), no rules consume it yet | ~15 lines |
| 5 | **try/except/else** — `else` block is not covered by `try`'s handlers | R4 (broad except) may false-positive on code in `else` that has distinct exception context | Track AST subtree membership when evaluating R4 | Moderate |

### Iris: 5 Implementer Clarifications

Implementation details, not design disputes. All have recommended resolutions.

| # | Clarification | Recommendation |
|---|--------------|---------------|
| 1 | **Topology glob semantics** — does `"core/landscape/*"` match recursively? | Use `**` for recursive, `*` for single-level. Follow `.gitignore`/`ruff` conventions. |
| 2 | **Topology overlap resolution** — file matches both `tier_1` and `tier_2` globs | Exit 2 (tool error). Overlapping topology is a manifest error. |
| 3 | **Exception review required fields** — which fields in `[review]` sub-table are mandatory? | `decision_rationale` required; `reviewer`, `trust_tier` optional. UNCONDITIONAL cells reject exception creation at parse time. |
| 4 | **`sbe.provenanceSource` format** — no closed set defined | 6 source types: method call, parameter, decorator, heuristic, topology, default (`"unknown"`). |
| 5 | **SARIF `invocations` array** — spec says no timestamps but SARIF expects `invocations` | Include `invocations` with `executionSuccessful` and `exitCode`; omit `startTimeUtc`/`endTimeUtc`. |

### Quinn: Corpus Authoring Estimate

| Category | Cells | Entries | Hours | Notes |
|----------|-------|---------|-------|-------|
| R3 `hasattr()` | 7 | ~7 | 1 | All ERROR, structurally identical |
| R1/R2 `.get()`/`getattr()` | 14 | ~56 | 4–5 | Paired rules, shared structure |
| R4 Broad `except` | 7 | ~28 | 3–4 | Realistic try/except blocks |
| R5 Data→audit | 7 | ~30 | 4–5 | Hardest — requires realistic audit write paths |
| R6 `except: pass` | 7 | ~28 | 2–3 | Simpler than R4 |
| R7 `isinstance()` | 7 | ~24 | 2–3 | Polymorphic dispatch for TN cases |
| Cross-cutting review | — | — | 2–3 | Deduplication, adversarial edges |
| **Total** | **49** | **~208** | **16–24** | 2–3 focused days |

**Maintenance cost:** ~2 entries/quarter from red-team evolution. New rules add 7 cells each (~28–35 entries, ~4–5 hours). Corpus is append-mostly.

### Quinn: INFO Action-Rate Operational Definition

See §Conditional Commitments above for the full definition. Key design decisions:

- **Action = code change in flagged region**, not allowlist suppression
- **Window = merge commit + subsequent 3 commits** on target branch
- **Line tolerance = ± 5 lines** (heuristic for line drift)
- **Observation minimums** prevent premature reclassification (20+ for promotion, 50+ for suppression)

### Quinn: 3 Testability Gaps

| Gap | Scope | Test Type | Estimated Entries | Hours |
|-----|-------|-----------|-------------------|-------|
| **Taint propagation depth** | Multi-step assignment chains (2-step, 3-step, cross-function) | Integration tests | ~15–20 | 4–6 |
| **Decorator consistency** | Correct vs. inconsistent decorator usage | Separate test suite | ~20 | 2–3 |
| **MIXED construction** | How containers become MIXED via mixed-tier assignments | Taint engine tests | ~8–10 | 1–2 |

**Total additional test surface:** ~43–50 entries, 7–11 hours beyond the 208-entry golden corpus.

## Known Limitations and Future Work

### Design-Documented Known Limitations

| ID | Limitation | Identified By | Severity | Remediation | Timeline |
|----|-----------|--------------|----------|-------------|----------|
| **KL-1** | Validator field-coverage gap — SUPPRESS cells assume validator covers accessed field without verification | Riven | Medium | VERIFIED validation status with per-field coverage tracking | v1.0 |
| **KL-2a** | Decorator-consistency checker: Scenario C — mixed-provenance returns from correctly-decorated functions | Sable | Low | Inter-procedural return-value analysis | v1.0+ |
| **KL-2b** | Decorator-consistency checker: decorator omission — undecorated functions default to TIER_2 regardless of actual behaviour | Sable | Low | Layer 3 coverage report ("N functions make external calls without decorators") | v0.2 |
| **KL-3** | MIXED provenance underdetection — functions mixing tier provenance in return values produce single-tier labels | Riven | Low | Intra-procedural data flow analysis on dict value assignments | v1.0 |

**KL-1 is the most dangerous.** Riven's assessment: "The field-coverage gap produces a SUPPRESS — no finding at all. Zero signal. The false negative is invisible to every channel in the integration stack." This is the gap that motivates VERIFIED as a v1.0 validation status.

### Governance Gaps

| Gap | Identified By | Severity | Proposed Behaviour |
|-----|--------------|----------|-------------------|
| **Orphaned exception cleanup** | Gideon | Minor | Fingerprints matching zero findings for 3 consecutive CI runs → flagged as `orphaned`. Auto-removed after 30 days with CI output comment. |
| **Exception audit trail fields** | Gideon | Moderate | Add `created_by`, `created_at`, `last_renewed_by`, `last_renewed_at` to each exception entry in `strict.toml`. Populated by `strict review` command. |

Gideon notes the irony: "A governance model for an auditability tool that isn't itself fully auditable."

### System Dynamics Risks (12–24 Month Horizon)

| Risk | Identified By | Likelihood | Mechanism | Mitigation |
|------|--------------|-----------|-----------|-----------|
| **Validator monoculture** | Seren | High (6–12 months) | Developers clone working validators → shared semantic inadequacy propagates across all flows. Concentration metric shows healthy distribution but structural similarity is high. | `strict health` reports validator structural similarity metric (>80% shared AST = warning). v0.2+ enhancement. |
| **Exception governance coordination cost** | Seren | Medium (12+ months) | Exceptions cluster around same expiry dates (created in same sprint) → batch-renewal burden displaces feature work → bulk renewal without review or reactive CI disruption. | Staggered expiry — new exceptions assigned dates that distribute evenly across the renewal calendar. Governance policy, not tool change. |
| **Annotation treadmill** | Seren | High (inevitable) | Annotation correctness at creation degrades as implementations evolve. Decorator-consistency checker catches some cases but not indirect external dependencies (helper calls helper calls API). | Inter-procedural taint analysis (v1.0) is the structural fix. Until then, staleness rate depends on codebase churn and review discipline. |

## Security Hardening Recommendations

Four recommendations from Sable, all accepted without objection.

### SH-1: UNCONDITIONAL Cells Hardcoded in Source

The 24 UNCONDITIONAL cells must be encoded as constants in the rule engine source code, not in `strict.toml` or any editable configuration. If the exceptionability matrix lives in config, a single-line change downgrades `hasattr()` from UNCONDITIONAL to STANDARD.

**STANDARD and LIBERAL classifications may live in configuration** — they represent policy choices that may evolve. UNCONDITIONAL is a project invariant.

### SH-2: CI Test Verifying UNCONDITIONAL Count ≥ 24

The CI pipeline must include a test:

```
assert len(UNCONDITIONAL_CELLS) >= 24, \
    "UNCONDITIONAL cell count decreased — requires security review"
```

A monotonically non-decreasing guard. If new rules add UNCONDITIONAL cells, the threshold increases. If a cell is proposed for downgrade, the test forces explicit review.

### SH-3: Exit 2 Self-Test on First CI Run

On first run in a CI environment, `strict` intentionally emits exit 2 and verifies the pipeline treats it as failure. If the pipeline continues (e.g., `continue-on-error: true`), emit a WARN-level finding: "CI pipeline does not block on tool errors (exit 2). Security gate is ineffective."

One-time setup verification, not per-run.

### SH-4: Warning Phase Prominence in Layer 3 Diagnostics

Sable recommends the 14-day exception expiry warning appear in Seren's Layer 3 diagnostics as a first-class signal, not just in the governance output block. "3 exceptions expiring in 14 days" should be as prominent as "2 new violations this sprint" in the `strict health` display.

The warning phase is the security-relevant window — it is when human attention determines whether accumulated risk gets addressed or rubber-stamped.

## Novel Concepts Introduced in Round 5

| Concept | Introduced By | Description |
|---------|--------------|-------------|
| **@internal_data alias** | Pyre | Syntactic sugar for TIER_2 — captures "not external" intent without forcing TIER_1/TIER_2 choice |
| **INFO boundary conditions** | Sable | Three measurable thresholds for revisiting INFO-as-advisory: action-rate, team size, agent code share |
| **Validator structural similarity metric** | Seren | AST-based diff metric detecting when multiple `@validates_external` functions share >80% structure |
| **Staggered exception expiry** | Seren | Distribute expiry dates across renewal calendar to prevent batch-renewal coordination burden |
| **Bidirectional INFO reclassification** | Seren | Action rate >20% → promote to WARN (developers treating as actionable); <5% → demote to SUPPRESS |
| **INFO action-rate operational definition** | Quinn | "Action" = code change in flagged region within merge commit or next 3 commits, ± 5 lines tolerance |
| **Observation minimums for reclassification** | Quinn | 20+ observations for promotion, 50+ for suppression — prevents premature threshold decisions |
| **Total test surface estimate** | Quinn | ~251–258 entries (208 corpus + ~50 engine tests), 23–35 hours total |
| **Orphaned exception cleanup** | Gideon | Fingerprints matching zero findings for 3 runs → flagged; auto-removed after 30 days |
| **Exception audit trail fields** | Gideon | `created_by`, `created_at`, `last_renewed_by`, `last_renewed_at` per exception entry |
| **Stale fingerprint count in warning phase** | Gideon | "Your exception group expires in 12 days and 3 of 8 fingerprints are stale" — stronger renewal prompt |
| **SARIF invocations without timestamps** | Iris | Include `invocations` with `executionSuccessful`/`exitCode`, omit time fields for determinism |
| **provenanceSource closed format set** | Iris | 6 source types (method call, parameter, decorator, heuristic, topology, default) for stable SARIF parsing |
| **Walrus operator scope handling** | Pyre | `:=` targets write to enclosing scope; comprehension variables get shadow scope in TaintMap |

## Position Shift Tracking (Round 5)

| Agent | Round 4 Position | Round 5 Position | Shift |
|-------|-----------------|-----------------|-------|
| **Pyre** | Collapsed TIER_1/TIER_2, proposed 4-provenance model | **Conceded collapse was wrong.** Commits to 5-label model. | CONCESSION |
| **Sable** | Reversed collapse, full 2D model, defence-in-depth on INFO | Commits. Registers boundary conditions for revisiting INFO. | HELD + PRECISION |
| **Seren** | Reconciled 3-layer stack with testability | Commits. Files minority reports on error rate erosion and INFO gap. Identifies 3 system dynamics risks. | HELD + EXTENSION |
| **Riven** | Attacked INFO as compliance laundering, proposed --stdin mode | **Withdrew --stdin proposal.** Conditional commit on action-rate metric. | CONCESSION |
| **Quinn** | Split tiers (conceded), embedded validation (pragmatic position) | Commits. Files and self-closes embedded validation minority report. Provides operational definitions. | CONCESSION COMPLETED |
| **Gideon** | Exceptionability matrix, 4-phase expiry lifecycle | Commits. Self-critiques 24 UNCONDITIONAL count (affirms it). Identifies 2 governance gaps. | HELD + SELF-CRITIQUE |
| **Iris** | Complete integration spec (CLI, SARIF, exit codes, manifest, performance) | Commits unconditionally. Provides 5 implementer clarifications. | HELD + REFINEMENT |

## Scribe Observations

### Observation 1: The Design Is Complete — 7/7 Commit

Five rounds. Seven agents. Zero blocking objections remaining. The design that emerged:

| Component | Specification |
|-----------|--------------|
| **Taint model** | 5 provenance × 2 validation, 7 effective states |
| **Rule matrix** | 49 cells, all defined, 4-level severity (ERROR 19 / WARN 14 / INFO 5 / SUPPRESS 11) |
| **Corpus** | ~208 entries, 16–24 hours authoring, <5s CI execution |
| **Integration** | 4 exit codes (0/1/2/3), SARIF 2.1.0, deterministic output |
| **Governance** | 4-class exceptionability (24 UNCONDITIONAL / 22 STANDARD / 10 LIBERAL / 8 TRANSPARENT), grouped fingerprints, 4-phase expiry |
| **Diagnostics** | 3-channel Layer 3 (CI summary, `strict-health.json` sidecar, `strict health` command) |
| **Manifest** | `strict.toml` with topology, rules, heuristics, exceptions |
| **Security hardening** | UNCONDITIONAL in source code, count-decrease CI test, exit 2 self-test |
| **Known limitations** | 4 documented (KL-1 through KL-3, plus decorator omission), all with remediation timelines |

### Observation 2: Riven's Conditional Commitment Is Resolvable

Riven's condition — the INFO action-rate metric ships in v0.1 — is the only hard requirement outstanding. Quinn's operational definition in Round 5 makes this concrete:

- **Measurement:** SARIF fingerprints + git diff correlation
- **Thresholds:** >30% → promote to WARN; <5% → demote to SUPPRESS; 5–30% → hold
- **Observation minimums:** 20+ for promotion, 50+ for suppression
- **Implementation scope:** ~50 lines of post-merge analysis

This is not a design question — it's a build commitment. The condition becomes unconditional once the metric is implemented. No further roundtable deliberation is needed.

### Observation 3: Minority Reports Are Enhancement Paths, Not Design Flaws

The five minority reports share a structural pattern: each identifies a scenario where the v0.1 design is *adequate but not optimal*, with a concrete improvement path for v0.2 or v1.0.

| Minority Report | v0.1 Status | Enhancement Path |
|----------------|-------------|-----------------|
| MR-1: @internal_data alias | Developers choose TIER_1 or TIER_2 explicitly | Alias added as UX convenience |
| MR-2: INFO boundary conditions | INFO is advisory with action-rate metric | Revisit at 3 thresholds |
| MR-3: Decorator gaps | Consistency checker ships with documented gaps | Coverage report (v0.2), inter-procedural analysis (v1.0) |
| MR-4: ERROR rate erosion | Suppression rate metric as sensor | Auto-escalation actuator (v0.2) |
| MR-5: Embedded validation | 2D model with 7 effective states | Self-closed — no enhancement needed |

None of these would change a single cell in the 49-cell matrix. None would change an exit code, a SARIF output format, or a governance class. They are refinements to measurement, UX, and long-term sustainability — exactly the kind of concerns that should be documented and deferred, not the kind that should block a design.

### Observation 4: The Design Improved from Round 4 to Round 5

Round 4 produced the design. Round 5 stress-tested it and crystallized implementation details. The specific improvements:

1. **Pyre's AST edge cases** — 5 concrete challenges with mitigations, none requiring design changes. This is the strongest evidence that the design is implementable: the person who will build the AST engine says "I can build this" and identifies the hard parts.

2. **Quinn's operational definitions** — The INFO action-rate metric went from "measure whether anyone acts" to a specified measurement mechanism with observation minimums and bidirectional thresholds. This transforms Riven's conditional commitment into a concrete implementation task.

3. **Iris's implementer clarifications** — 5 ambiguities in the Round 4 spec that would have become implementation questions. Resolving them here saves implementation time.

4. **Gideon's self-critique** — The 24 UNCONDITIONAL cells were defended with a detailed breakdown. The two governance gaps (orphaned cleanup, audit trail fields) are minor additions that strengthen the model's internal consistency.

5. **Seren's system dynamics risks** — Three 12–24 month risks (validator monoculture, coordination cost, annotation treadmill) that the design should document but cannot solve at v0.1 scope. These are the responsible articulation of what the design *doesn't* do.

### Observation 5: Riven's Red-Team Assessment Validates the Design

Riven's final assessment is the most consequential endorsement in the roundtable. The adversarial agent whose role was to break the design concludes:

> "Is this design meaningfully better than `enforce_tier_model.py`? Yes. Unambiguously."

Riven identifies three categorical improvements: provenance-aware severity, governance lifecycle, and the golden corpus. Riven's residual risk assessment rates all five remaining vectors as acceptable for v0.1, with the most dangerous (KL-1: validator field-coverage gap) documented and remediated in v1.0.

When the red-teamer says "ship it," the design is ready.

---

*Round 5 closes the adversarial roundtable. The design proceeds to specification and implementation.*
