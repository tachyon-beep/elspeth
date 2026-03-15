# Round 5 — Final Dissent and Commitment: Riven (Adversarial Red-Teamer)

## 1. Commitment with Registered Dissent

I commit to the design. I do not file a minority report.

The compliance laundering attack is real and I stand behind every word of it. But a minority report implies the design is fatally flawed absent the fix. It isn't. The design is meaningfully better than `enforce_tier_model.py` (see §3), and my dissent targets a 5-cell surface (10% of the matrix) that has a measurement mechanism (Quinn's action-rate metric) with a concrete reclassification trigger. I don't need to block the design — I need the metric to run.

**My commitment is conditional on one thing:** the INFO action-rate metric must ship in v0.1, not be deferred to v0.2. If INFO findings are advisory with no measurement of whether anyone acts on them, they are decorative. Quinn's metric is the difference between "advisory with feedback loop" and "advisory as a polite word for ignored." The scribe recorded Quinn's <5% reclassification threshold. That threshold is the accountability mechanism for my concession. Without it, I would file the minority report.

## 2. The `--stdin` Distinction: Concession

The scribe notes that my INFO-blocks-in-agent-mode proposal (Option 1) resembles the dual enforcement profiles rejected 7/7 in Round 2. I accept this reasoning partially and concede the proposal.

**Where the scribe is right:** The practical effect is identical — code arriving via `--stdin` gets stricter enforcement than code arriving via file path. Whether we call it "authorship-based" or "mode-based," the developer experience is the same: "why does my CI fail when I paste this code into the agent but pass when I commit it directly?" That question destroys trust in the tool faster than any evasion vector I've identified.

**Where the distinction was real but not worth defending:** Mode-based enforcement keys on *invocation context* (how the tool was called), not *authorship claim* (who wrote the code). These are genuinely different signals — the tool knows its invocation mode with certainty but can never verify authorship. However, the UX damage from differential enforcement outweighs the theoretical cleanliness of the distinction. Users don't care about our taxonomy of enforcement triggers. They care that the same code gets the same result.

I withdraw Option 1. Quinn's action-rate metric (my conditional commitment in §1) is the correct v0.1 mechanism. Option 3 (mandatory review lifecycle) remains my recommendation for v1.0.

## 3. Remaining Evasion Vectors

### The Single Most Dangerous Vector: Validator Field-Coverage Gap

The most dangerous evasion vector in the final design is not decorator abuse (partially mitigated by the consistency checker) or compliance laundering (measured by the action-rate metric). It is the **field-coverage gap** in the SUPPRESS cells.

The matrix has 11 SUPPRESS cells. Four of them are `.get()`/`getattr()` on `(TIER_3, STRUCTURALLY_VALIDATED)` data. The suppression assumes the validator covers the accessed field. The tool cannot verify this — and in Round 4 I showed a concrete example where a validator checks `status` but the suppressed `.get()` accesses `customer_name`. The finding is suppressed. The fabrication via default proceeds. The audit trail records a fabricated value. This is the exact ACF-I1 pattern, undetected.

**Why this is more dangerous than compliance laundering:** Compliance laundering produces an INFO finding that someone *could* act on. The field-coverage gap produces a SUPPRESS — no finding at all. Zero signal. The false negative is invisible to every channel in the integration stack: no SARIF entry, no GitHub annotation, no CI output, no sidecar metric. The only way to detect it is code review of the validator's field coverage, which is the pre-tool status quo.

**Why I'm not escalating this to a minority report:** The attack requires a validator that (a) passes the rejection-path check, (b) passes the tautological detector, (c) validates *some* fields genuinely, but (d) doesn't validate the specific field accessed downstream. This is a narrow-but-real gap. It's also the gap that motivates `VERIFIED` as a v1.0 validation status — per-field coverage tracking closes this completely. The v0.1 design correctly defers this (the AST analysis for per-field coverage is a substantial implementation effort), and the SUPPRESS cells are the right v0.1 severity because the alternative (INFO on every `.get()` after any validator) would flood the output and undermine adoption.

**Recommendation for the design document:** Document this as "Known Limitation KL-1: Validator field-coverage is not verified. SUPPRESS on (TIER_3, STRUCTURALLY_VALIDATED) assumes but does not confirm that the validator covers the accessed field. Per-field coverage tracking is planned for v1.0 via the VERIFIED validation status."

### Secondary Vector: MIXED Provenance Underdetection

The decorator-consistency checker catches mechanical mislabelling (Scenarios A and B from Round 4). It does not catch Scenario C: a function with a correct `@external_boundary` decorator that returns a dict mixing TIER_3 and TIER_1 values. The entire return is labelled TIER_3. The TIER_1 component loses its provenance.

This is a real gap but a *design-time* gap, not a *runtime* gap. The tool's heuristic analysis operates on static code. A function that constructs a dict from mixed sources is detectable by more sophisticated analysis (track provenance of each dict value assignment), but this requires intra-procedural data flow analysis beyond the v0.1 scope.

**Residual risk:** Acceptable for v0.1. The volume of functions that genuinely mix tier provenance in return values is small (most functions operate within a single tier). The decorator-consistency checker catches the high-volume mechanical case. The residual is a code review concern.

## 4. Final Red-Team Assessment

### Is this design meaningfully better than `enforce_tier_model.py`?

**Yes. Unambiguously.**

The existing `enforce_tier_model.py` is a pattern-matching grep with an allowlist. It has three fundamental limitations that the new design addresses:

| Limitation | `enforce_tier_model.py` | New Design |
|-----------|------------------------|------------|
| **Provenance awareness** | None — all `.get()` findings are equal regardless of data origin | 7 effective states determine severity per finding |
| **False positive management** | Binary allowlist (suppress or block) with no expiry | 4-class governance (UNCONDITIONAL/STANDARD/LIBERAL/TRANSPARENT) with expiry lifecycle |
| **Validated data handling** | No concept of validation status | 2D model tracks validation separately from provenance |

The improvement is not incremental — it's categorical. The existing tool cannot distinguish `.get()` on audit data (critical) from `.get()` on validated external data (legitimate). Every finding has the same severity. The allowlist grows monotonically because there's no mechanism to distinguish "this is genuinely fine" from "this is a compliance entry to make the build pass." The new design's provenance-aware matrix eliminates the majority of false positives structurally (SUPPRESS cells for legitimate boundary handling), which means the remaining findings have higher signal, which means developers engage with them rather than reflexively allowlisting.

The golden corpus is the second categorical improvement. The existing tool has no ground truth — "is this finding correct?" is a matter of opinion, resolved by whoever last edited the allowlist. The corpus makes correctness testable: for this code at this provenance, the tool should emit this severity. When the tool is wrong, the corpus entry is the evidence. When the allowlist is wrong, the corpus entry is the arbiter. This closes the feedback loop that the existing tool lacks entirely.

### Residual Risk Assessment for v0.1

| Risk | Severity | Mitigation | Acceptable? |
|------|----------|-----------|-------------|
| Validator field-coverage gap (KL-1) | **Medium** | VERIFIED status in v1.0; documented as known limitation | Yes |
| Compliance laundering on INFO cells | **Low-Medium** | Quinn's action-rate metric with <5% reclassification trigger | Yes, if metric ships in v0.1 |
| Decorator mislabelling (mechanical) | **Low** | Decorator-consistency checker (first-pass rule) | Yes |
| Mixed-provenance returns (Scenario C) | **Low** | Code review; intra-procedural analysis in v1.0 | Yes |
| UNKNOWN provenance accumulation | **Low** | Seren's system health metrics track UNKNOWN rate | Yes |

**Overall: the residual risk is acceptable for a v0.1 tool.** No single vector undermines the design's core value proposition (provenance-aware severity differentiation). The known limitations have concrete v1.0 remediation paths. The measurement mechanisms (action-rate metric, health sidecar, corpus regression) provide the feedback loops needed to validate the design's assumptions empirically.

## 5. Summary

| Question | Answer |
|----------|--------|
| Commit or dissent? | **Commit** — conditional on INFO action-rate metric shipping in v0.1 |
| Accept `--stdin` rejection reasoning? | **Yes** — UX damage outweighs theoretical distinction. Option 1 withdrawn. |
| Most dangerous remaining vector? | **Validator field-coverage gap** — SUPPRESS cells assume field coverage without verification. No signal at all on false negatives. Document as KL-1. |
| Design better than `enforce_tier_model.py`? | **Yes, categorically.** Provenance awareness, governance lifecycle, and golden corpus are each independently sufficient improvements. Together they transform a pattern-matching grep into an evidence-based enforcement tool. |
