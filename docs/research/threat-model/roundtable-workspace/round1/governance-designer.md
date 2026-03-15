# Round 1 — Opening Position: Gideon (Governance Designer)

## Summary Position

The proposed semantic boundary enforcer is technically sound but governmentally fragile. The existing ELSPETH allowlist already shows early symptoms of the disease that kills static analysis tools at scale: **exception accumulation outpacing exception retirement**. The dual enforcement profile (human vs. agent) is the right instinct but the wrong mechanism — authorship attribution is an unsolvable problem in mixed human-agent workflows, and building policy around it creates an adversarial classification game rather than a trust boundary. The governance model must be designed around *review throughput*, not *authorship identity*.

## Detailed Analysis

### 1. Allowlist Lifecycle: The Existing Model Is Already Strained

The current ELSPETH allowlist (`config/cicd/enforce_tier_model/`) provides an excellent case study. Looking at `core.yaml` alone, I count approximately 40 `allow_hits` entries. Several patterns are visible:

**What's working:** Each entry has a fingerprint, owner, reason, and safety justification. Entries like `fp=6467dcaaf8795f52` (idempotent delete in PayloadStore) have clear, defensible rationales. The `owner` field creates accountability. The `expires` dates create pressure to revisit.

**What's straining:** Many entries share identical rationales — the eight `LandscapeExporter:_iter_records` entries all say "Sparse lookup — not all rows have tokens (batch export uses pre-loaded dicts)." This is a single architectural decision requiring eight separate allowlist entries because the enforcer operates at finding granularity rather than decision granularity. When one architectural choice generates N allowlist entries, the governance cost scales with N, but the intellectual review cost is 1. This mismatch is the seed of rubber-stamping.

**Expiry model assessment:** The current mix of `null` (permanent) and date-based expiry is pragmatic but incomplete. Permanent entries for `isinstance()` dispatch (R5) are correct — these are structural patterns that won't change. Date-based entries for bugfixes (e.g., `expires: '2026-05-12'`) create review checkpoints. But the dates are chosen by the person creating the exception, with no external validation that the date is reasonable. A developer under pressure will set `expires: '2027-12-31'` and move on.

**My proposal for the new tool:**

- **Three expiry classes:** `permanent` (architectural — reviewed annually), `version-bound` (expires when a specific code version ships or a refactoring milestone lands), and `review-dated` (calendar date, maximum 90 days, enforced by the tool itself).
- **Expiry escalation:** When a `review-dated` entry is renewed more than twice, the tool flags it for promotion to `permanent` with mandatory architectural justification, or elimination. Perpetual 90-day renewals are a governance smell — either the exception is legitimate (make it permanent) or the code should be fixed (eliminate it).
- **Decision-level grouping:** Allow a single allowlist entry to cover multiple findings from the same architectural decision (e.g., "all `.get()` calls in `_iter_records` for sparse token lookup"). The entry specifies a scope (function + rule), and the tool validates that all findings within scope match the stated pattern. This reduces the 8-entry problem to a 1-entry problem without losing traceability.

### 2. Human-Agent Enforcement Asymmetry: The Wrong Axis

The proposal distinguishes human code (graduated promotion) from agent code (blocking by default). This distinction is attractive in theory but unenforceable in practice.

**The attribution problem:** In a typical agentic development session, the agent writes code, the human reviews and edits it, the agent refactors based on feedback, and the human commits. Who authored the result? Git blame shows the committer, not the intellectual author. `Co-Authored-By` trailers are voluntary and inconsistent. An agent writing through a human's editor session leaves no distinguishing trace.

**The adversarial dynamic:** If agent-authored code faces stricter enforcement, the rational response is to launder agent code through human commits. This isn't even malicious — a developer who trusts their agent's output will naturally commit it as their own work. The policy creates an incentive to obscure provenance, which is the opposite of what an audit-focused system wants.

**The deeper problem:** The concern isn't really about *who* wrote the code — it's about *whether the code was reviewed with understanding*. A human who writes `.get("key", 0)` on a Tier 1 access probably knows why. An agent that writes the same pattern is following training data bias. But a human who accepts an agent's PR without reading it is no better than the agent.

**My counter-proposal:** Replace authorship-based enforcement with **review-depth-based enforcement**:

- **All code** gets the same rules at the same severity levels.
- **Exceptions** require a structured justification (the current `reason` + `safety` fields are already close to this).
- **Exception velocity** is the governance signal. If a developer is creating more than N exceptions per week, that's a process flag — either the rules need calibration, or the developer (or their agent) is systematically violating boundaries.
- **Batch exception creation** (more than 3 in a single commit) requires a second reviewer, regardless of authorship. This catches both "agent dumped 50 violations" and "human cargo-culted a pattern across 50 files."

### 3. Temporal Separation: Enforceable but Brittle

The requirement that manifest changes occur in a separate prior commit from source changes is a good forcing function — it makes exception creation a deliberate act rather than a drive-by. But enforcement has edge cases:

**Enforceable scenarios:** Linear commit history on a protected branch with a CI gate that checks commit ordering. The gate verifies: (a) the manifest-changing commit contains no `.py` files, and (b) the source-changing commit contains no manifest files.

**Problematic scenarios:**
- **Squash merges** destroy the temporal separation. If a PR with commits [manifest change, source change] is squash-merged, the gate sees a single commit with both. The CI gate must run on the *PR commit sequence*, not the merge commit.
- **Rebases** can reorder commits. A rebase that moves the manifest commit after the source commit breaks the invariant silently. The gate must validate commit ordering at merge time, not just at PR creation.
- **Cherry-picks** can extract just the source commit without its prerequisite manifest commit. The gate must verify that every source file's violations are covered by the manifest *as of that commit*, not just that the manifest was changed "recently."

**Can agents game this?** Easily. An agent can create a manifest commit, then a source commit, in perfect compliance. The temporal separation only prevents *accidental* co-mingling — it doesn't prove the exception was thoughtfully considered. This is fine! The goal is forcing deliberate action, not preventing all possible gaming. The second line of defense is the CODEOWNERS review.

### 4. Governance Scaling: The 50-Rule, 500-Entry Problem

The current ELSPETH model has ~10 rules and ~70 allowlist entries across 10 module files. It's manageable. At 50 rules and 500 entries, several failure modes emerge:

**Rule interaction complexity:** With 50 rules, a single code pattern might trigger 3-4 rules simultaneously. The developer must understand which rules are relevant, which exceptions to file, and how the rules interact. Rule documentation becomes critical and rule *overlap* becomes a source of confusion and duplicate exceptions.

**Allowlist search cost:** Finding "does an exception already exist for this pattern?" becomes non-trivial at 500 entries. The fingerprint system helps for exact matches, but understanding *why* similar code nearby is allowed requires reading human-written rationales across multiple entries. This is where developers start copying rationale text from adjacent entries without understanding it.

**Staleness accumulation:** With `fail_on_stale: true` and `fail_on_expired: true` in `_defaults.yaml`, expired entries break the build. This is correct! But at 500 entries, expiry management becomes a background tax. Someone must regularly audit expiring entries, decide whether to renew or fix, and submit the changes. If this maintenance is nobody's job, it becomes everybody's emergency when the build breaks.

**My proposal:**
- **Allowlist budget per module.** Each module YAML file has a `max_entries` cap. Exceeding it requires architectural review — the question shifts from "is this individual exception valid?" to "why does this module need so many exceptions?"
- **Quarterly allowlist audit** as a calendar event, not an ad-hoc response to build breakage. The audit asks: which permanent entries are still justified? Which expired entries were renewed without progress on the underlying fix?
- **Rule categories with independent maturity.** Not all 50 rules need the same governance weight. Critical rules (trust boundary violations) get strict governance. Stylistic rules (naming conventions) get lightweight governance. The tool should support tiered rule severity that maps to different exception requirements.

### 5. The CODEOWNERS Bottleneck

If the manifest is CODEOWNERS-protected, every exception needs code owner approval. This is correct for a 10-person team with 70 entries. At agent-scale volume, it creates two failure modes:

**Throughput bottleneck:** If agents generate 10-20 violations per day across a team, the code owners become a review queue. Review latency blocks merges. Blocked merges create pressure to rubber-stamp. Rubber-stamping destroys the governance signal.

**Expertise concentration:** CODEOWNERS protection assumes the owners understand both the rule semantics and the code context. At scale, the owner is reviewing exceptions for code they didn't write in modules they don't maintain. The review becomes mechanical ("does it have a reason? does it have a safety field? LGTM") rather than substantive.

**My proposal:**
- **Tiered approval authority.** Critical rules (trust boundary bypass, audit trail destruction) require CODEOWNERS. Lower-severity rules can be approved by any reviewer with module familiarity.
- **Exception review checklists** embedded in the manifest format. Instead of free-text `reason` and `safety` fields, require structured answers: "What trust tier is this data?" "What happens if this value is wrong?" "Is there a code path that validates this data upstream?" Structured fields are harder to rubber-stamp than prose.
- **Weekly exception digest** to CODEOWNERS showing new exceptions, renewed exceptions, and exception velocity trends. This shifts owners from per-exception gatekeeping to pattern oversight.

### 6. The CODEOWNERS Problem as Systemic Dynamic

The deepest concern here is a "Shifting the Burden" archetype (in systems thinking terms): the tool catches violations, but the *real* fix is developer/agent education about trust boundaries. Each allowlist exception is a symptom treatment. If exceptions accumulate faster than developers learn the trust model, the allowlist becomes the de facto policy — and it's a policy of "everything is allowed with paperwork."

## Key Design Proposal

**Decision-scoped exceptions with structured review fields and velocity monitoring.**

Replace the current per-finding allowlist with per-decision exceptions:

```yaml
exceptions:
  - id: EXC-2026-042
    decision: "Sparse token lookup in batch export — not all rows have tokens"
    scope:
      file: core/landscape/exporter.py
      function: _iter_records
      rule: R1
    class: permanent  # or version-bound, review-dated
    review:
      trust_tier: "Tier 2 — pre-loaded dict from our own query"
      failure_mode: "KeyError if token missing — handled by conditional"
      upstream_validation: "Tokens loaded by _load_token_map which queries nodes table"
    owner: architecture
    approved_by: [john]
    created: 2026-01-15
    last_reviewed: 2026-03-01
    velocity_context:
      related_exceptions: 0  # How many other exceptions in this file?
      month_created: 2  # How many exceptions were created this month?
```

This collapses the 8 identical `_iter_records` entries into 1, requires structured justification instead of free text, and captures velocity metadata for governance dashboards.

## Governance Risks

**Risk 1: Exception Inflation (likely, high impact).** The primary failure mode. Every false positive becomes an exception. Every exception requires maintenance. Maintenance burden grows linearly with codebase size. At some threshold, the cost of maintaining exceptions exceeds the value of the violations caught. The tool gets disabled "temporarily" and never re-enabled. *Mitigation:* Decision-scoped exceptions, module budgets, and rule maturity tiers that match governance cost to rule value.

**Risk 2: Authorship Classification Games (likely if dual-profile ships).** Developers route code through whichever enforcement profile is lighter. The tool's governance model becomes a sorting game rather than a quality gate. *Mitigation:* Drop the dual profile entirely. Enforce uniformly. Use exception velocity as the quality signal.

**Risk 3: CODEOWNERS Exhaustion (likely at scale).** Review fatigue leads to rubber-stamping. Rubber-stamping destroys trust in the exception process. Developers stop writing meaningful rationales because reviewers don't read them anyway. *Mitigation:* Tiered approval authority, structured review fields that resist rubber-stamping, and weekly digests that shift owners to pattern oversight.

**Risk 4: Temporal Separation Erosion (moderate).** Teams adopt squash-merge workflows that silently bypass the temporal separation guarantee. The CI gate reports green because it checks the merge commit, not the PR history. *Mitigation:* The CI gate must validate the PR commit sequence, and squash merges of manifest+source changes must be explicitly blocked.

**The governance failure mode that will kill adoption:** Exception inflation without retirement. The tool that catches 100 violations per week but only retires 10 exceptions per month is a tool that will drown in its own governance overhead within a year. Every design decision should be evaluated against this dynamic: does it increase exception creation rate, or decrease it? Does it increase retirement rate, or decrease it? The ratio of retirement to creation is the tool's vital sign.
