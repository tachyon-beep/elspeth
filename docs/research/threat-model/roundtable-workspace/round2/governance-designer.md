# Round 2 — Dissent: Gideon (Governance Designer)

## Target: Iris (Integration Engineer) — Dual Enforcement Profiles

I am directly addressing Scribe Observation 1: Iris's config includes `[tool.strict.profiles] agent = "blocking"` / `human = "graduated"` — the exact mechanism I rejected in Round 1. This is not a peripheral disagreement; it is a load-bearing design choice that will determine whether the tool's governance model survives contact with real development workflows.

## Steelman

Iris's position, presented at its strongest: Agents produce defensive anti-patterns at a systematically higher rate than human developers because their training data is biased toward "safe" Python idioms (`.get()` with defaults, broad `except` blocks, `hasattr()` guards). This is empirically observable — the discussion paper documents it as ACF-I1 through ACF-I3. A tool that catches these patterns should therefore apply stricter enforcement to the code most likely to contain them. Graduated promotion for human code respects the reality that experienced developers sometimes use `.get()` deliberately (e.g., on genuinely optional config fields), while blocking for agent code reflects the reality that agents almost never have a legitimate reason for these patterns in ELSPETH's trust model.

The dual profile is not punitive — it is calibrated to base rates. If 95% of agent `.get()` calls are genuine violations but only 60% of human `.get()` calls are, then blocking agents immediately while graduating humans through advisory-then-blocking is statistically rational. The cost of a false positive is higher for humans (context switch, frustration, --no-verify temptation) than for agents (automated retry loop, no emotional cost). Iris's config also cleanly separates the two profiles, making the asymmetry explicit and auditable rather than hidden in implementation details.

Furthermore, Iris's `--stdin` mode for agents creates a natural enforcement point. Agent code passes through `strict check --stdin` before it ever reaches a file, making the blocking profile a pre-write filter rather than a post-commit gate. This is architecturally elegant — the agent gets feedback before the code exists, so there's no suppression workflow needed. The dual profile isn't just about severity; it's about where in the pipeline enforcement occurs.

This is the strongest version of the argument for dual profiles. I believe it is wrong.

## Attack

### The Classification Problem Is Unsolvable

The dual profile requires answering the question: "Was this code written by an agent or a human?" This question has no reliable answer in mixed workflows, and the mechanisms to answer it are all gameable or ambiguous.

**Mechanism 1: Git metadata.** `Co-Authored-By: Claude` trailers are voluntary. Nothing prevents a human from omitting them. Nothing prevents a human from adding them to code they wrote themselves (perhaps to get stricter checking on code they're uncertain about — an ironic inversion). In ELSPETH's own development, every commit has `Co-Authored-By: Claude` because the development is agent-assisted. Does that make every line "agent code"? The human reviewed it, edited it, committed it. The boundary is meaningless.

**Mechanism 2: The `--stdin` pipeline.** Iris's `--stdin` mode implies agent code is identifiable because agents pipe code through `strict check` before writing it. But nothing constrains this — a human developer might pipe their own code through `--stdin` for quick feedback (it's faster than committing and waiting for CI). And an agent that writes code directly to disk through an editor integration never passes through `--stdin`. The mode of invocation is a proxy for authorship, and proxies can be wrong in both directions.

**Mechanism 3: File-level designation.** Some tools (like ESLint's `overrides`) let you designate entire directories as "agent-generated." But ELSPETH doesn't have agent-only directories — agents edit the same files humans edit. Line-level attribution is theoretically possible but practically absurd (what happens when a human edits one line in an agent-generated function?).

None of these mechanisms are reliable. The tool will either misclassify code (applying the wrong profile) or create an adversarial dynamic where the classification itself becomes a point of friction.

### The Incentive Structure Is Perverse

Seren identified this in Round 1 as a "Success to the Successful" archetype, and I want to make the dynamic concrete.

If agent code faces blocking enforcement while human code faces graduated enforcement, the rational response for any developer who trusts their agent is to **commit agent code as human code**. This isn't a theoretical concern — it's the path of least resistance. Why would a developer voluntarily opt into stricter enforcement for code they've already reviewed and accepted? The dual profile creates an incentive to obscure provenance, which is the opposite of what an audit-focused system should want.

Worse: the developer who routes agent code through the human profile isn't doing anything wrong by the project's own standards. ELSPETH's CLAUDE.md says nothing about agent vs. human code quality tiers. The Three-Tier Trust Model is about *data provenance*, not *code authorship*. A `.get()` on Tier 1 data is equally dangerous regardless of who typed it.

### The Existing Evidence Contradicts the Premise

Look at ELSPETH's own allowlist. The `core.yaml` file has ~40 `allow_hits` entries. The `owner` field shows values like `architecture`, `bugfix`, and specific bug IDs (`P2-2026-02-02-76r`). These are legitimate exceptions created during agent-assisted development where the human and agent collaboratively decided that the pattern was correct for the context.

If dual enforcement had been in place, these entries would have been blocked outright for agent code, requiring the developer to either: (a) manually retype the code to avoid `--stdin` classification, (b) add an exception through the manifest workflow, or (c) disable the tool. Option (a) is governance theatre. Option (b) is the correct path but adds friction that the graduated profile was designed to avoid. Option (c) is the failure mode we're trying to prevent.

The current allowlist demonstrates that agent-assisted code with legitimate exceptions is the *norm*, not the exception. A governance model that treats this norm as suspicious will be circumvented.

### What "Graduated" Actually Means Is Underspecified

Iris's config shows `human = "graduated"` but doesn't define the graduation mechanism. Does "graduated" mean advisory findings that promote to blocking after a precision threshold? After a calendar date? After N firings? The `SBE-E01 = { level = "advisory", promoted_after = "2026-06-01" }` entry in Iris's config suggests date-based promotion, but this applies per-rule, not per-profile. The interaction between per-rule graduation and per-profile severity is undefined. Does a rule that is `advisory` for humans and `blocking` for agents ever become `blocking` for humans? If so, what triggers it? If not, the dual profile creates a permanent asymmetry that no amount of precision data can close.

## Proposed Verdict

**The roundtable should reject dual enforcement profiles and adopt uniform enforcement with velocity-based governance signals.** Specifically:

1. **All code gets the same rules at the same severity.** Rules are `advisory` or `blocking` based on measured precision, not code authorship. A rule that is 97% precise over 100 firings is `blocking` for everyone.

2. **Exception velocity replaces authorship as the governance signal.** If a developer (or their agent) is generating exceptions at an unusual rate, that's a signal for process review — not because the code is "agent code," but because the rate suggests either rule miscalibration or systematic boundary misunderstanding.

3. **The `--stdin` mode retains its value without dual profiles.** Agents still get pre-write feedback. They still self-correct. The difference is that the feedback uses the same rule severity as CI, so there's no classification game and no incentive to avoid `--stdin`.

4. **Iris's config format should drop the `[tool.strict.profiles]` section entirely.** The `[tool.strict.rules]` section with per-rule `level` settings already provides the right granularity. Adding a profile layer on top creates complexity without governance value.

The tool should be a trust-boundary enforcer, not an authorship-attribution system. The Three-Tier Trust Model distinguishes data by provenance. The enforcement model should distinguish code by measured precision, not by who or what typed it.
