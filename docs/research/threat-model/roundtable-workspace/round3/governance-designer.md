# Round 3 — Steelman Synthesis: Gideon (Governance Designer)

## Steelman: Iris's Attack on Decision-Scoped Exceptions

Iris's Round 2 attack was the most technically precise dissent in the roundtable. Let me present it at full strength, because the argument deserves it.

Decision-scoped exceptions, as I proposed them, use function-scope matching: an exception declares `scope: { file: X, function: Y, rule: Z }` and covers all findings within that scope. Iris identified four failure modes, two of which are devastating:

**The refactoring cliff-edge.** When `_iter_records` is renamed to `_build_export_records`, the scope `function: _iter_records` matches nothing. The exception becomes silently stale — eight findings reappear as brand-new violations with no trail back to the original architectural decision. Per-finding fingerprints degrade gracefully under renaming (partial symbol context may survive); decision-scoped exceptions have a binary cliff: they match or they don't.

**The auto-suppression trap.** A scope matching `function: _iter_records, rule: R1` suppresses *all* R1 findings in that function — including new `.get()` calls added later for entirely different reasons. The developer who adds a `.get()` on Tier 1 audit data inside `_iter_records` gets zero feedback, because the existing decision-scope covers it. Per-finding fingerprints don't have this problem: every new code pattern generates a new fingerprint that requires explicit exception creation.

Iris is right that these two problems are fundamental to scope-based matching, not incidental to my implementation. They arise because scope matching answers "is this finding in a region we've already reviewed?" while per-finding matching answers "is this specific code pattern one we've already reviewed?" The first question has false positives (new patterns in old regions). The second has higher governance cost (N entries for one decision) but exact coverage.

Iris's counter-proposal — per-finding fingerprints for matching, `decision_group` as a metadata tag for grouped governance — captures my insight (governance cost should scale with decisions, not findings) without compromising matching precision. The eight `_iter_records` entries become eight fingerprints with `decision_group: sparse-token-lookup`. The tool groups them for display, review, and expiry. But matching remains per-fingerprint — deterministic, refactoring-resilient (to the degree fingerprints are), and precise.

## Concession

Iris is right on the implementation. I was wrong to put decision-scoping in the matching layer.

My Round 1 proposal conflated two separable concerns: **governance ergonomics** (how humans reason about and manage exceptions) and **suppression precision** (how the tool identifies which findings are covered). The insight — that one architectural decision generates N findings with governance cost N but review cost 1 — is correct and universally accepted. But the solution should address governance ergonomics without sacrificing suppression precision.

The auto-suppression trap is particularly damning because it undermines the very purpose of the tool. A governance mechanism that silently suppresses new violations in "already-reviewed" regions is an enforcement gap masquerading as a governance improvement. In ELSPETH's trust model terms: decision-scope matching is a Tier 1 access on exception data that uses `.get()` semantics (return a default if missing) instead of direct access (crash if unexpected). I was proposing the exact anti-pattern I built my Round 1 position around.

I also concede on the module budget cap. Iris's point about budget gaming (moving code across module boundaries to avoid the cap) and premature permanence (promoting review-dated to permanent to stay under the cap) are legitimate failure modes. Seren's suppression rate metric — a percentage that scales naturally rather than an absolute cap with cliff edges — is better structural pressure.

On structured review fields: Iris is partially right that they converge to boilerplate for common cases. But I maintain that the convergence itself is informative — if 80% of engine-layer exceptions have the same trust-tier justification, that's a signal that the rule needs calibration for the engine layer, not that the structure is useless. I'll address this in the synthesis.

## Synthesis: Grouped Fingerprint Governance with Adaptive Review Prompts

Neither Iris's bare `decision_group` tag nor my original decision-scoped matching reaches the right design. Here's what both positions miss independently:

**Iris misses the review lifecycle problem.** A `decision_group` tag enables grouped display, but it doesn't answer: when the group expires, what happens? Does the developer re-review all N fingerprints individually? If so, the governance cost snaps back to N at every renewal, defeating the purpose. If they renew the group as a unit, they need a mechanism to verify that all fingerprints in the group still share the same justification — which is the auto-suppression trap returning through the back door at review time rather than match time.

**I missed the precision requirement.** Suppression must be per-fingerprint because the tool's determinism guarantee requires it. But review and lifecycle management must be per-decision because that's how humans reason about exceptions.

**The synthesis: grouped fingerprint governance with adaptive review prompts.**

```toml
# Per-finding fingerprint — deterministic matching (Iris's model)
[[tool.strict.exceptions]]
fingerprint = "a1b2c3d4"
rule = "SBE-T02"
file = "src/elspeth/core/landscape/exporter.py"

# Decision group — governance metadata (my insight, Iris's layer)
decision_group = "sparse-token-lookup"
expires = "2026-09-01"

# Adaptive review context (the synthesis neither side proposed)
[tool.strict.exceptions.review]
trust_tier = "tier2"
decision_rationale = "Sparse token lookup — not all rows have tokens in batch export"
```

The key innovation is what happens at **review time**. When a `decision_group` approaches expiry, the tool's `strict manifest audit` command (Sable's proposal) generates a **review digest** that:

1. **Lists all fingerprints in the group** — showing which ones still match active findings, which are stale (code changed), and which are new (added since last review).
2. **Highlights divergence** — if a fingerprint in the group now covers code that doesn't match the `decision_rationale` (e.g., a new `.get()` call in `_iter_records` that accesses metadata instead of tokens), it's flagged as "review required: finding may not match group rationale."
3. **Calculates group health** — what percentage of the group's fingerprints are still active? If 6 of 8 are stale because the code was refactored, the group is dying and should be cleaned up rather than renewed.

This divergence detection is the piece neither Iris nor I proposed. It addresses:

- **Iris's precision concern:** Matching is per-fingerprint. No auto-suppression of new findings.
- **My governance cost concern:** Review is per-decision-group. Renewal is one action that covers all fingerprints in the group.
- **The auto-suppression gap:** New findings in `_iter_records` get new fingerprints that aren't in any group. They appear as ungrouped findings requiring explicit triage. The developer can add them to the existing group (if same rationale) or create a new exception (if different rationale). This is the explicit act of review that scope-matching skipped.
- **The refactoring cliff-edge:** When `_iter_records` is renamed, fingerprints that depended on the function name become stale. The group health check reports "6/8 fingerprints stale after refactoring." The developer re-runs the analysis on the renamed function, gets new fingerprints for the same patterns, and adds them to the group. The decision survives; the fingerprints rotate.

On structured review fields: I propose making them **group-level, not per-finding**. The `decision_rationale` and `trust_tier` describe the architectural decision, not each individual finding. This is where boilerplate is acceptable — it's the *same answer* because it's the *same decision*. Per-finding review fields are where Iris's boilerplate critique applies; group-level context is where structure adds value.

Finally, on suppression rate replacing the module budget: accepted. Seren's metric is the right structural pressure. But I'd add one governance trigger: when a module's suppression rate exceeds 15% of total findings, the `strict manifest audit` command should flag it for architectural review — not as a hard cap, but as an attention signal. The question shifts from "are you under budget?" to "is this module generating more exceptions than its complexity warrants?"

**What this synthesis produces that neither side would reach alone:** Iris's model gives precise matching but no lifecycle management for grouped decisions. My model gives lifecycle management but imprecise matching. The synthesis gives precise matching with grouped lifecycle management and divergence detection at review boundaries — a governance model that scales with decisions (not findings) without sacrificing the per-finding precision that the tool's determinism guarantee requires.
