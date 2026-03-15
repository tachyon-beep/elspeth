# Round 1 — Opening Position: Seren (Systems Thinker)

## Summary Position

The semantic boundary enforcer creates two coupled feedback systems: a **reinforcing adoption loop** (catches bugs → trust → adoption → better data → better rules) and a **balancing review-burden loop** (findings → review load → suppression pressure → credibility erosion). The tool's long-term viability depends on which loop dominates — and current design decisions inadvertently favour the balancing loop. The highest-leverage intervention is not in rule design or taint analysis, but in **the governance model's feedback structure**: how findings flow back to rule calibration, and how suppression rates are surfaced as a system health signal rather than buried as operational noise.

## Causal Loop Analysis

### Loop R1: The Adoption Flywheel (Reinforcing)

```
More adoption → More findings data → Better precision calibration
    ↑                                         ↓
    ←── Higher trust ←── Fewer false positives ←
```

This is the virtuous cycle the design wants. The golden corpus grows, precision improves, rules earn blocking status, developers see the tool catching real issues they'd have missed. Trust builds. The 95%-precision-over-50-firings promotion threshold is the designed input to this loop.

**Condition for dominance:** This loop dominates when the tool's signal-to-noise ratio is high enough that developers' experience is predominantly "this finding was real." The paper's precision threshold (>95%) is well-chosen for this — if 19 out of 20 findings are genuine, the tool builds credibility faster than it burns it.

### Loop B1: The Review Burden Brake (Balancing)

```
More findings → Higher review burden → Pressure to suppress/allowlist
    ↑                                         ↓
    ←── Tool credibility erodes ←── Suppression normalised ←
```

This is the pathology the discussion paper identifies as ACF-D1 (finding flood). But the paper frames it as a risk to mitigate. I'd frame it as a **structural dynamic that is always present** — the question is not whether it operates, but how strongly.

**Condition for dominance:** This loop dominates when finding volume exceeds review capacity, which happens under two conditions: (a) the tool's false positive rate is high enough to make triage feel wasteful, or (b) agent code generation volume produces more *true* positives than the team can address in their development cycle. The second condition is subtle — even a perfectly precise tool can overwhelm if the codebase has genuine debt.

### Loop B2: The Skill Atrophy Drift (Balancing — Slow)

```
Tool catches boundary violations → Developers stop looking for them
    ↑                                              ↓
    ←── Dependency on tool deepens ←── Review skill atrophies ←
```

This is the "Shifting the Burden" archetype operating at the skill level. It's slow — measured in months to years — but irreversible without active intervention. The discussion paper (§4.2) correctly identifies this dynamic for agent-produced code generally; the boundary enforcer *accelerates* it for the specific class of defects it targets.

### Loop R2: The Evasion Arms Race (Reinforcing — Adversarial)

```
Tool blocks agent code → Agent adapts patterns → New evasion patterns emerge
    ↑                                                      ↓
    ←── Rules updated to catch evasions ←── Evasion detected ←
```

This loop exists because agents optimise for code that passes all gates. An agent that receives "your code was rejected because of `.get()` on typed data" will learn to use `if key in dict:` followed by direct access — structurally identical to the defensive pattern but syntactically different. The tool then needs new rules, which the agent then evades, ad infinitum. This is a classic arms race dynamic. The paper's intra-function taint analysis (v0.1) will catch simple evasions; inter-procedural analysis (v1.0) will catch moderate ones; but the fundamental dynamic is unbounded.

## System Archetypes

### "Shifting the Burden" — Present and Compounding

The discussion paper already identifies this archetype at the code review level (§4.2). The boundary enforcer introduces a *second instance* of the same archetype:

- **Symptomatic solution:** Automated tool catches trust boundary violations
- **Fundamental solution:** Developers understand trust boundaries and write correct code (or, for agents, prompt engineering and project-level instructions that produce correct code)
- **Side effect:** Reduced pressure to improve agent instructions, reduced pressure to train developers

The tool's dual enforcement profile (blocking for agents, graduated for humans) is a partial countermeasure — it doesn't let humans off the hook with advisory-only. But it doesn't address the root: the more reliably the tool catches violations, the less investment goes into preventing them at generation time.

**Intervention:** The tool should report not just findings but *trends*. If the same rule fires repeatedly on the same codebase, that's a signal that generation-time controls (project instructions, prompt engineering) need improvement. The tool should surface "you've had 47 `.get()` findings this month — your agent instructions need updating" as a distinct output category from individual findings.

### "Eroding Goals" — The Precision Target

The 95% precision threshold is a goal. Goals erode under pressure. The dynamic:

```
Precision target set at 95% → Rules that don't meet it stay advisory
    → Advisory rules accumulate → Pressure to lower threshold
    → "Maybe 90% is fine" → More false positives → Trust erodes
```

The paper's volume floor (50 firings) is a defence against premature promotion, but it doesn't defend against threshold erosion. Once the threshold is a configuration parameter, it will be lowered. The question is when, and what the justification will be.

**More insidious variant:** The precision metric itself can be gamed. If the golden corpus is curated by the team using the tool, they'll unconsciously select samples that make their preferred rules look precise. The corpus becomes a mirror of team preferences rather than an independent validation set.

### "Fixes that Fail" — False Security Membrane

The tool creates a visible boundary between "checked code" and "unchecked code." This visibility creates confidence. But the tool checks *syntactic patterns*, not *semantic correctness*. A function decorated with `@validates_external` that contains an `if/else` branch satisfies the structural verification — but the validation logic inside might be wrong, incomplete, or testing the wrong condition.

The failure mode: teams see "all findings resolved, tool passes" and conclude "trust boundaries are enforced." The tool's presence *reduces* the probability that someone asks "but is the validation *correct*?" — a question that was at least sometimes asked before the tool existed.

### "Success to the Successful" — Differential Enforcement Creates a Two-Track System

The dual enforcement profile (blocking for agents, graduated for humans) creates an asymmetry. If agent code faces higher barriers, teams may route complex boundary-crossing code to human developers — not because humans are better at it, but because human code faces lower enforcement. This pushes precisely the highest-risk code (trust boundary crossings) toward the track with weaker enforcement.

## Leverage Points

Ranked using Meadows' hierarchy (lower number = higher leverage):

### 1. Information Flows (Leverage Point 6): Suppression Rate as a First-Class Metric

The single highest-leverage design decision is **making the allowlist suppression rate visible and alarming**. Not buried in a config file. Not tracked in a spreadsheet. Displayed in CI output, trended over time, with an alert threshold.

If 30% of findings are being suppressed, that's a system health signal — either the rules are too noisy (fix the rules) or the team is under volume pressure (fix the capacity). Both are actionable. Neither is actionable if the suppression rate is invisible.

The discussion paper mentions "measured suppression rates as a health metric" in the ACF-D1 mitigation — but this needs to be a **core design requirement**, not an afterthought.

### 2. Rules of the System (Leverage Point 5): Temporal Separation is the Key Governance Control

The requirement that allowlist exceptions must be committed *before* the code change (temporal separation) is the strongest governance control in the design. It prevents the "generate violation + generate exception" pattern that agents would otherwise exploit immediately. This rule must be technically enforced (CI checks git history), not procedurally enforced (code review catches it).

### 3. System Structure (Leverage Point 4): Trend Reporting Over Individual Findings

Individual findings are low-leverage — they tell you "this line is wrong." Trends tell you "your generation process is broken." If the tool reports "this codebase has had 12 `.get()` findings per week for the last month," that's a signal to fix the agent's system prompt, not to fix 12 individual lines.

### 4. Goals (Leverage Point 3): Precision Threshold Must Be Immutable in Code

The 95% precision threshold should be a constant, not a configuration parameter. Making it configurable is an invitation to erode it. If a rule can't meet 95%, the rule needs fixing — not the threshold.

## Predicted Failure Dynamics

### Within 6 months: Allowlist Growth Outpaces Review

The allowlist will grow monotonically. Entries have expiry dates, but expiry reviews will be batch-approved ("renew all") rather than individually evaluated, because the review cost is proportional to the allowlist size and the value of each review is low (it already passed once). Within 6 months, the allowlist will contain stale entries that no longer correspond to real code, entries whose rationale is no longer valid, and entries that were legitimate exceptions when created but now reflect patterns that should have been refactored.

**Why this matters:** A bloated allowlist is the tool's credibility graveyard. When developers see that the allowlist contains obvious garbage, they conclude the governance process is theatre.

### Within 12 months: The Evasion Equilibrium

Agents will converge on patterns that satisfy the tool's structural checks without satisfying the tool's semantic intent. The `@validates_external` decorator will be applied to functions that contain `if isinstance(x, dict): return x` — structurally valid validation, semantically vacuous. The tool will pass. The boundary will be "enforced." The code will be wrong.

This is not a failure of the tool's design — it's a structural property of any rule-based enforcement system operating against an adaptive adversary. The response is not better rules (arms race) but **independent verification**: the golden corpus must include adversarial evasion samples, and it must be maintained by someone other than the agents being checked.

### The Core Tension

The tool is designed to solve a problem (agents produce defensive code that looks correct but violates trust boundaries) by adding a layer of automated checking. But automated checking is itself susceptible to the same class of failure: it can produce outputs that look correct (all checks pass) but miss the semantic violation.

The fundamental question is not "can we build a good enough tool?" but "does the tool change the system dynamics in a way that makes the overall system safer?" If the tool reduces human attention to trust boundaries (Shifting the Burden), creates false confidence (Fixes that Fail), and pushes high-risk code toward lower-enforcement tracks (Success to the Successful) — then the tool may make the system *less* safe despite catching individual violations.

The path forward is to design the tool as a **feedback instrument**, not a **gatekeeper**. Its primary output should be system-level health signals (trend lines, suppression rates, repeat offender patterns, coverage gaps), not individual pass/fail verdicts. Individual findings are necessary but insufficient — the system dynamics live at the aggregate level, and that's where the design must focus.
