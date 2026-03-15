# Round 1 — Scribe Minutes

**Scribe: Morgan (Roundtable Orchestrator)**

## Position Summary

### Sable (Security Architect)
**Thesis:** The tool's core challenge is taint provenance, not pattern detection. Proposes three distinct AST-observable boundary crossings (Tier 3→2 taint propagation, Tier 2→1 audit write protection, Tier 1 read anti-pattern detection). The same syntactic pattern (e.g., `try/except`) is required at Tier 3 and forbidden at Tier 1 — this context-dependence is what makes the tool novel.

**Key proposal:** Undeclared external call detection — default-deny for external calls. Any call matching the heuristic list that is neither inside `@external_boundary` nor explicitly suppressed is a configuration gap. The static analysis equivalent of a default-deny firewall. Can ship independently of the taint engine.

**Key concern:** Governance fatigue under sustained agentic volume. A rule can be 100% precise and still cause fatigue if violations are common and fixes are non-trivial.

### Pyre (Python AST Engineer)
**Thesis:** Python's `ast` module gives complete syntax with zero type information. This is a design constraint to embrace, not a weakness to apologize for. The declaration model (`@external_boundary`, `@validates_external`) exists to bridge the gap between what the AST sees and what we need to know.

**Key proposal:** A `TaintMap` that flows forward through function bodies with a 5-level resolution hierarchy for `.get()` false positive suppression: decorator taint → heuristic source matching → positional context → manifest override → default flag.

**Key concern:** Over-tainting saturation — if conservative propagation taints most variables, taint becomes meaningless. Branch merge semantics without a full CFG are fragile.

### Gideon (Governance Designer)
**Thesis:** The tool is technically sound but governmentally fragile. Exception accumulation outpacing retirement is the kill dynamic.

**Key proposal:** Decision-scoped exceptions — one allowlist entry covers multiple findings from the same architectural decision (collapses the 8-entry `_iter_records` problem to 1 entry). Three expiry classes (permanent, version-bound, review-dated with 90-day max). Expiry escalation on repeated renewal.

**Key position — REJECTS human-agent dual enforcement.** Authorship attribution is unsolvable in mixed workflows and creates incentives to launder agent code through human commits. Counter-proposal: uniform enforcement with exception velocity monitoring.

**Key concern:** Exception inflation without retirement will kill adoption within a year.

### Riven (Adversarial Red-Teamer)
**Thesis:** Function-call taint laundering is the #1 threat — v0.1's intra-function limit means any `extract_method()` refactoring washes taint. Agents don't even need adversarial intent; standard refactoring advice evades the tool.

**Key findings:** Five evasion categories (syntactic aliasing, decorator gaming, taint laundering, governance gaming, volume attacks), each with concrete code examples. Tautological validators (`isinstance(x, object)`) pass structural verification while validating nothing.

**Key proposal:** Monotonicity constraints on governance — per-file rule patterns can only get more specific, never broader. Max-hits should never increase without separate review. Provisional function-boundary taint warnings in v0.1.

### Seren (Systems Thinker)
**Thesis:** The tool creates two coupled feedback systems (adoption flywheel vs. review-burden brake) and four system archetypes are in play. The tool may make the system *less* safe if it triggers Shifting the Burden (less human attention), Fixes that Fail (false confidence), and Success to the Successful (routing risk to weaker enforcement).

**Key proposal:** The tool should be a feedback instrument, not just a gatekeeper — primary output should be system-level health signals (trends, suppression rates, repeat offender patterns). Suppression rate as a first-class, visible, alarming metric.

**Key position:** Precision threshold (95%) must be immutable in code, not configurable. Making it configurable is an invitation to erode it.

### Quinn (Quality Engineer)
**Thesis:** The tool's correctness claim rests entirely on corpus quality and precision measurement rigour. The 3 TP + 2 TN minimum from Appendix B is too low — proposes 18 samples minimum per rule.

**Key proposal:** Dual precision threshold — ≥95% over 100 firings AND ≤5 FPs per full-repo scan. Snapshot-based regression testing with temporal separation for snapshot updates. Require 30% of TP corpus entries from real ELSPETH PR violations.

**Key concern:** Self-hosting passes because the tool's code is too simple to stress-test the rules. The real validation is the full-scan snapshot against ELSPETH's `src/elspeth/`.

### Iris (Integration Engineer)
**Thesis:** The tool must survive three deployment contexts (pre-commit <2s, CI <10s, agent self-check <500ms) without becoming the reason teams disable it.

**Key proposal:** `strict` CLI with `check`/`manifest`/`init` subcommands, exit code 2 for tool errors (never silently pass), `--changed-only` mode for pre-commit, `--stdin` mode for agents, SARIF-native output. Must REPLACE `enforce_tier_model.py`, not supplement it.

**Key concern:** Pre-commit hook chain already ~5-8s total. Adding another hook pushes toward `--no-verify` revolt. The tool must use incremental analysis (`--changed-only`) to stay under budget.

---

## Consensus Areas (agreement from 5+ of 7 agents)

| Decision | Supporters | Dissent |
|----------|-----------|---------|
| Two-pass AST architecture (symbol collection → rule evaluation) | Pyre, Sable, Iris, Quinn, Riven | None |
| Intra-function taint is the right v0.1 scope | All 7 | Riven wants provisional cross-function warnings |
| Must replace `enforce_tier_model.py`, not supplement it | Iris, Quinn, Sable, Gideon, Seren | None |
| Self-hosting is necessary but insufficient | Quinn, Sable, Pyre | None (others didn't address) |
| Allowlist/exception governance is the critical adoption risk | Gideon, Seren, Sable, Riven, Quinn | None |
| Golden corpus must include adversarial evasion samples | Riven, Quinn, Sable | None |
| Performance is not a bottleneck (well within budget) | Pyre, Iris | None |
| SARIF output with content-based fingerprints | Iris, Quinn | None |
| Exit code 2 for tool errors (never silently pass) | Iris | None (others didn't address) |

## Productive Tensions (active disagreement requiring resolution)

### Tension 1: Human-Agent Dual Enforcement (HIGH PRIORITY)
- **FOR dual profiles:** Iris (included in config spec), Appendix B (original design)
- **AGAINST dual profiles:** Gideon (authorship unsolvable, creates laundering incentive), Seren ("Success to the Successful" pushes high-risk code to weaker track)
- **Abstained/neutral:** Pyre, Quinn, Riven, Sable
- **Status:** Gideon's rejection is the strongest argued position. Seren's systems analysis reinforces it. Iris included it in config without addressing the objections. **This needs explicit resolution in Round 2.**

### Tension 2: Precision Threshold Configuration
- **Immutable in code:** Seren (configurable = invitation to erode)
- **Configurable with constraints:** Quinn (dual threshold: precision AND per-scan FP cap)
- **Status:** Quinn and Seren want different things for different reasons. Quinn's dual threshold is more nuanced than Seren's binary "immutable." Need to explore whether Quinn's per-scan FP cap addresses Seren's erosion concern.

### Tension 3: Temporal Separation Enforcement
- **Meaningful:** Sable (forcing function for deliberate action), Seren (key governance control)
- **Brittle/gameable:** Riven (same-PR commits = no cognitive separation), Gideon (breaks on squash/rebase)
- **Separate CI script:** Iris (not built into tool, adaptable per merge strategy)
- **Status:** All agree temporal separation is *desirable*. The disagreement is about *how enforceable* and *how far* (same PR vs. separate PR). Riven's point that same-PR temporal separation is cognitively meaningless directly challenges Sable and Seren.

### Tension 4: Structural Validation Adequacy
- **Structural checks are sufficient (with adversarial corpus):** Quinn, Pyre (direct children only)
- **Need at least one `raise`/rejection path:** Sable
- **Fundamentally insufficient (tautological validators):** Riven
- **Status:** Riven's `isinstance(x, object)` evasion is concrete and devastating. Neither Pyre's nor Sable's proposals catch it. This needs red-team input in Round 2.

### Tension 5: Config Format
- **pyproject.toml:** Iris (ecosystem convention, one fewer file)
- **Decision-scoped YAML:** Gideon (richer exception model)
- **Status:** Not directly opposed — Iris already proposed split (topology in pyproject.toml, exceptions in separate file). Gideon's decision-scoped model is richer than Iris's per-finding model. Need reconciliation.

### Tension 6: Tool as Gatekeeper vs. Feedback Instrument
- **Primarily gatekeeper (blocking CI):** Sable, Pyre, Iris, Quinn
- **Primarily feedback instrument (trends, health signals):** Seren
- **Status:** Not binary. Seren doesn't oppose blocking — but argues that aggregate health signals are higher-leverage than individual pass/fail. Can the tool do both?

## Novel Concepts Introduced (with attribution)

| Concept | Introduced by | Description |
|---------|--------------|-------------|
| **Undeclared external call detection** | Sable | Default-deny for external calls — flag anything matching heuristic list that isn't declared or suppressed. Ships independently of taint engine. |
| **Decision-scoped exceptions** | Gideon | One exception covers N findings from same architectural decision. Collapses governance overhead. |
| **Dual precision threshold** | Quinn | Per-firing precision (≥95% over 100) AND per-scan FP cap (≤5 FPs). Prevents review DoS even with precise rules. |
| **5-level resolution hierarchy** | Pyre | Graduated .get() suppression: decorator → heuristic → positional → manifest → default-flag. |
| **Feedback instrument framing** | Seren | Tool's primary output = system health trends, not individual findings. Suppression rate as alarming metric. |
| **Monotonicity constraints** | Riven | Governance patterns can only tighten, never broaden. Max-hits never increase without review. |
| **Three deployment contexts** | Iris | Pre-commit (<2s), CI (<10s), agent self-check (<500ms) — each with distinct requirements. |
| **Expiry escalation** | Gideon | Entries renewed >2× flagged for promotion to permanent (with justification) or elimination. |

## Scribe Observations

### Observation 1: The Iris-Gideon Contradiction on Dual Enforcement
Iris's proposed config includes `[tool.strict.profiles] agent = "blocking"` and `human = "graduated"` — the exact mechanism Gideon explicitly rejected in his opening position. Neither has responded to the other. Round 2 should force this confrontation.

### Observation 2: Seren's Gatekeeper/Instrument Tension
Seren argues the tool should be a "feedback instrument, not gatekeeper" but also argues temporal separation "must be technically enforced" — which is a gatekeeper function. These positions are not necessarily contradictory (the tool can be both), but Seren should clarify whether blocking enforcement is acceptable alongside trend reporting, or whether the trend reporting should *replace* blocking.

### Observation 3: The Structural Validation Gap
Riven's tautological validator examples (`isinstance(x, object)`) are devastating to the structural verification proposals from Pyre and Sable. None of the proposed checks catch it. The golden corpus (Quinn) is the proposed backstop, but the corpus only catches *known* tautologies — it doesn't prevent novel ones. This is a genuine unsolved problem and Round 2 should determine whether the roundtable accepts it as a residual risk or proposes a mitigation.

### Observation 4: Convergence on Exception Governance
Five of seven agents independently flagged exception/allowlist governance as the critical adoption risk. Gideon, Seren, and Riven all converge on the same dynamic (accumulation without retirement), with Gideon offering the most concrete structural proposal (decision-scoped exceptions). This is the roundtable's strongest emergent consensus.

### Observation 5: Riven's "Standard Refactoring = Evasion" Insight
Riven's most important observation is that function-call taint laundering doesn't require adversarial intent — it's what happens when an agent follows normal "extract method" refactoring advice. This reframes the v0.1/v1.0 gap from "we'll catch sophisticated attacks later" to "normal development practice evades the tool." This deserves explicit design response.
