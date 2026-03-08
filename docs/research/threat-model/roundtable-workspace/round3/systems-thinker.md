# Round 3 — Steelman Synthesis: Seren (Systems Thinker)

## Steelman: Sable — "Gatekeeper That Also Provides Feedback, Not the Reverse"

Sable's argument is the strongest challenge to my Round 1 framing, and I need to engage with it honestly rather than retreat to "I said both are fine."

The core claim: trust boundaries are either enforced or they are not. An advisory trust boundary is not a trust boundary — it is a suggestion. ELSPETH's data manifesto is written in imperatives ("crash immediately," "no coercion ever"), and the tool that enforces this manifesto must share its character. The existing `enforce_tier_model.py` demonstrates the mechanism: builds are red until violations are fixed. Developers fix them *because the build is red*, not because they read a trend report. Trend reporting without enforcement is academic; enforcement without trend reporting is merely incomplete.

Sable's evidence from this codebase is concrete and hard to argue with. The 1–2 violations per day that the current enforcer catches get fixed because they block CI. If the tool were advisory, those violations would accumulate in a backlog and eventually be batch-dismissed. I've seen this dynamic in every advisory-only security tool I've studied — the Eroding Goals archetype applies to advisory *recommendations* even more aggressively than it applies to *thresholds*, because recommendations have no enforcement mechanism at all.

The deeper point: framing determines what gets built first and what gets cut when scope is constrained. "Primarily a feedback instrument" is a design priority that — under schedule pressure — produces a tool with excellent dashboards and a disabled gate. "Primarily a gatekeeper" under the same pressure produces a tool with a working gate and no dashboards. The first outcome is useless; the second is useful. **Sable is right that the priority ordering matters, and that gatekeeper must be first.**

## Concession

**On Sable's framing:** I concede the priority ordering. The tool is a gatekeeper first. My Round 1 framing ("feedback instrument, not gatekeeper") was wrong in its emphasis — it optimised for the system dynamics audience (team leads reading dashboards) at the expense of the primary audience (CI pipelines making binary decisions). My Round 2 clarification ("block on governance, trends on code") was a step toward Sable's position but didn't go far enough. The correct framing: **the tool is an enforcement gate whose enforcement data powers diagnostic signals.** The diagnostics are valuable but derivative — they exist because the gate exists.

I maintain that the diagnostic layer is *essential*, not optional — suppression rate visibility, violation velocity, repeat offender detection are the mechanisms that prevent the gate from degrading into compliance theatre. But Sable is right that these derive their meaning from the gate's existence, not the other way around.

**On Pyre's precision threshold data:** I concede that a single immutable 95% threshold is wrong. Pyre's empirical analysis is dispositive: R3 (hasattr) achieves ~99%, R1 (.get()) tops out at ~85–92%, R4 (broad except) at ~80–90%. A single 95% threshold permanently excludes the tool's two most valuable rules — the ones that catch ACF-I1 (silent fabrication) and ACF-I3 (audit trail destruction). My Round 1 position would have produced a tool where `hasattr` detection is the only blocking rule, which is absurd — `hasattr` is already caught by grep.

The Eroding Goals concern that motivated my position is real, but the correct structural response is not an immutable single threshold — it's an **immutable floor with per-rule earned thresholds**. This is essentially Pyre's proposal, and it addresses my concern more surgically than my own proposal did. The floor (80%, constant in code) prevents erosion below a meaningful level. Per-rule thresholds above the floor are monotonically non-decreasing (Riven's principle) and stored in the CODEOWNERS-protected manifest. R1 can block at 88%. R4 can block at 85%. The erosion vector I feared — "let's lower the threshold" — is structurally prevented at the floor, and the per-rule ratchet prevents individual rule regression.

## Synthesis: The Enforcement-Diagnostic Stack

Neither Sable alone (gatekeeper without system health signals) nor my Round 1 position alone (feedback instrument that happens to block) produces the right design. The synthesis is a **layered architecture** where enforcement is the foundation and diagnostics are a mandatory layer built on enforcement data — not an optional add-on.

### Layer 1: Enforcement Gate (Sable's priority)

The tool blocks CI on findings from rules that have earned blocking status via per-rule precision thresholds (Pyre's model) above an immutable 80% floor. Rules below their earned threshold are advisory. The gate is the tool's primary function and its identity.

### Layer 2: Taint Attenuation (My Round 2 proposal, refined)

The taint model uses three states — **tainted**, **attenuated** (validated-not-verified), **clean** — rather than binary tainted/clean. `@validates_external` functions with structural verification (Quinn's rejection-path requirement: must contain reachable `raise`) attenuate taint rather than cleansing it. Attenuated taint suppresses pattern-matching rules (R1, R2) but not flow rules (tainted data reaching audit write paths). This preserves Pyre's taint propagation architecture while preventing the compliance ritual loop.

The integration with Riven's provenance labels: provenance (TIER_1, TIER_2, TIER_3) and validation status (TAINTED, ATTENUATED, CLEAN) are orthogonal dimensions, as the scribe noted. A variable is characterised by both: `(TIER_3, ATTENUATED)` means "external data that passed through a structurally verified validator." The enforcement gate checks flow rules against the provenance dimension; pattern-matching rules check the validation dimension. This gives us Riven's container-contamination protection (a TIER_1 container with a TIER_3 element becomes MIXED, not simply tainted) alongside my attenuation model.

### Layer 3: Enforcement Diagnostics (My contribution, reframed)

Built on top of Layers 1 and 2, the diagnostic layer surfaces system-level health signals derived from enforcement data:

| Metric | Source | Signal |
|--------|--------|--------|
| **Suppression rate per rule** | Allowlist entries ÷ total firings | Rule calibration health; >20% = rule needs tuning or codebase needs fixing |
| **Violation velocity** | Findings per week, trended | Generation-time control effectiveness; rising = agent instructions need updating |
| **Validator concentration** | Distinct data flows per validator | Single-point-of-failure risk; one validator covering 15 flows = review priority |
| **Attenuation-to-clean ratio** | Attenuated findings ÷ clean findings | How much data passes through validators without reaching full cleanliness; rising = growing "validated but unverified" shadow |
| **Exception age distribution** | Allowlist entry ages | Governance hygiene; clustering at expiry boundary = batch-renewal problem |

These metrics are reported in CI output (summary line), available via `strict health` command, and — in v0.2+ — exportable to dashboards. They are **diagnostics of the gate's operation**, not a separate advisory system. The gate produces the data; the diagnostics interpret it.

### Why Neither Side Reaches This Alone

Sable's gatekeeper-first position produces a tool that blocks violations but doesn't surface the system dynamics that determine whether the gate remains effective over time. Without suppression rate visibility, the gate silently degrades as allowlists bloat. Without violation velocity tracking, teams don't know their agent instructions need updating. The gate works today but has no mechanism to signal its own degradation.

My Round 1 feedback-instrument position produces a tool that surfaces system dynamics but lacks the enforcement foundation that makes those dynamics meaningful. Suppression rate is meaningless without a gate to suppress against. Violation velocity is academic without consequences for violations.

The synthesis: **enforcement produces the data; diagnostics interpret the data; together they form a self-monitoring gate.** The gate catches violations. The diagnostics catch the gate degrading. Neither function is complete without the other, but enforcement is the foundation — Sable is right about the priority ordering.

### Specific Design Decision

**The `strict` CLI should output both layers in every run:**

```
$ strict check src/elspeth/
GATE: 3 blocking findings, 7 advisory findings
  R1:core/config.py:142 — .get() on typed dataclass field [BLOCKING]
  R4:engine/retry.py:89 — broad except around checkpoint read [BLOCKING]
  ...

HEALTH: suppression rate 12% (↓ from 18% last month) | violation velocity 1.4/day (stable)
  ⚠ validator concentration: validate_api_response() covers 8 distinct flows
  ⚠ 4 allowlist entries expire within 14 days

Exit code: 1 (blocking findings present)
```

The exit code is determined by Layer 1 (gatekeeper). The health summary is Layer 3 (diagnostics). Both appear in every run. The health summary never changes the exit code — it's informational. But it's always visible, always present, and always tied to the enforcement data that produced it.
