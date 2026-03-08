# Round 2 — Dissent: Iris (Integration Engineer)

## Target: Gideon — Decision-Scoped Exceptions

## Concession First: Dual Enforcement Is Dead

The scribe correctly flagged that my Round 1 config included `[tool.strict.profiles] agent = "blocking"` and `human = "graduated"` — the exact mechanism Gideon rejected. I included it reflexively from the Appendix B design without engaging with Gideon's argument.

Having now read his full position, **I concede.** Gideon's argument is airtight on two points:

1. **Attribution is unsolvable.** In a typical ELSPETH development session, Claude Code writes code, the developer reviews and edits, commits with `Co-Authored-By`. The enforcer would need to parse commit trailers, which are voluntary, inconsistent, and trivially omitted. Building a CI gate on data that the subject of enforcement controls is governance theatre.

2. **The incentive gradient is backwards.** Seren's "Success to the Successful" analysis seals it: if agent code is blocked harder, complex boundary-crossing code gets routed to the human track — pushing the highest-risk code toward weaker enforcement. This is not a theoretical risk; it's what I'd do as a developer facing a deadline.

I withdraw the `[tool.strict.profiles]` section from my config proposal. All code gets uniform enforcement. Exception velocity monitoring (Gideon's counter-proposal) is the right signal.

**But Gideon's alternative — decision-scoped exceptions — has a critical implementation flaw that will undermine the very governance it's designed to improve.**

## Steelman

Gideon's decision-scoped exception model is the strongest governance proposal in the roundtable. Its core insight is correct and important: the current per-finding allowlist in ELSPETH creates a **governance cost that scales with N findings per architectural decision, while the intellectual review cost is always 1.** The eight identical `_iter_records` entries in `core.yaml` are exhibit A — one decision, eight entries, eight fingerprints, eight expiry dates to manage. This is real overhead I've seen in the existing enforcer.

Decision-scoping collapses this:

```yaml
- id: EXC-2026-042
  decision: "Sparse token lookup in batch export"
  scope:
    file: core/landscape/exporter.py
    function: _iter_records
    rule: R1
```

One entry covers all eight findings. The structured review fields (`trust_tier`, `failure_mode`, `upstream_validation`) force developers to articulate *why* the exception exists, not just *that* it exists. The three expiry classes (permanent, version-bound, review-dated) with escalation on repeated renewal address the "perpetual 90-day renewals" anti-pattern. The module budget cap (`max_entries`) creates structural pressure against exception inflation.

This is the most thoughtful governance design in the roundtable, and if it could be implemented deterministically, I'd adopt it wholesale.

## Attack

**Decision-scoped exceptions require fuzzy scope matching that breaks the tool's determinism guarantee.**

The brief's verification properties (§Verification Properties, point 4) require: *"Deterministic output — byte-identical on identical input."* Per-finding fingerprints satisfy this trivially: `hash(rule_id + file + line + symbol_context + code_snippet)` produces the same fingerprint for the same code. Scope matching for decision-scoped exceptions does not.

### Problem 1: Function-scoped decisions don't survive refactoring

Gideon's example scopes an exception to `function: _iter_records`. When `_iter_records` is refactored — renamed, split into helper methods, or inlined into its caller — the scope no longer matches. The findings reappear as new violations with no connection to the existing exception.

With per-finding fingerprints, this is already a known problem, but it's bounded: a renamed function changes N fingerprints, and the developer updates N entries. With decision-scoped exceptions, a renamed function *silently invalidates the entire decision* — the tool sees zero findings matching the scope and the exception becomes stale, while the findings in the renamed function appear as brand-new violations with no trail back to the original decision.

The per-finding model degrades gracefully (some fingerprints survive renaming if symbol_context is partial). The decision-scoped model has a cliff edge.

### Problem 2: "All findings within scope" is underdetermined

Gideon says the entry "specifies a scope (function + rule), and the tool validates that all findings within scope match the stated pattern." But what does "match the stated pattern" mean algorithmically?

Consider: the `_iter_records` exception covers `.get()` calls for sparse token lookup. A developer later adds a *new* `.get()` call in `_iter_records` for a completely different reason — say, accessing an optional metadata field. Does the decision-scope cover this new finding? The scope says `function: _iter_records, rule: R1`. The new finding is in `_iter_records` and triggers R1. By scope matching, it's covered. By intent, it shouldn't be — it's a different architectural decision.

Per-finding exceptions don't have this problem. A new `.get()` call generates a new fingerprint. The developer must explicitly add it to the allowlist. The governance overhead is higher, but the *precision* of coverage is exact.

Decision-scoping trades governance overhead for coverage precision. In a tool whose entire purpose is catching semantic violations that syntactic checks miss, trading precision feels like paying with the thing you most need.

### Problem 3: Structured review fields become boilerplate faster than free text

Gideon argues structured fields (`trust_tier`, `failure_mode`, `upstream_validation`) resist rubber-stamping better than free-text `reason` and `safety` fields. I've seen the opposite in practice.

Structured fields create a template. Templates get copy-pasted. Within three months of deployment, every exception in the `engine/` module will say:

```yaml
trust_tier: "Tier 2 — pipeline data from upstream transform"
failure_mode: "KeyError if field missing — handled by conditional"
upstream_validation: "Validated by source plugin schema contract"
```

This isn't wrong — it's just the same answer for 80% of engine-layer exceptions, because most engine-layer `.get()` findings *are* Tier 2 data with the same trust justification. The structured fields don't add information; they add ceremony. A reviewer scanning 20 exceptions with identical structured fields is rubber-stamping just as surely as one scanning 20 entries with identical free-text reasons.

Free text at least allows varied expression that signals "I actually thought about this." Structured fields converge to a single canonical answer that signals "I filled in the form."

### Problem 4: The max_entries budget creates perverse incentives

A per-module `max_entries` cap sounds like structural pressure against inflation. In practice, it creates two failure modes:

1. **Budget gaming:** Developers restructure code to move findings across module boundaries, not to fix the underlying issue. "We're at 15/15 exceptions in `core.yaml`, so let's move this function to `engine/` where we have budget."

2. **Premature permanence:** When a module approaches its cap, developers promote `review-dated` exceptions to `permanent` to avoid hitting the limit — the exact opposite of the escalation dynamic Gideon wants.

## Proposed Verdict

**Keep per-finding fingerprints as the matching mechanism. Adopt decision-scoping as a metadata layer on top.**

Concretely:

1. **Each finding gets a content-addressed fingerprint** (the existing model). This is the key the tool uses for matching, suppression tracking, and SARIF output. Deterministic, refactoring-resilient (to the degree any fingerprint can be), and precise.

2. **Exceptions can declare a `decision_group` tag.** Multiple per-finding exceptions sharing a `decision_group` are displayed, reviewed, and expired as a unit. This captures Gideon's insight — the 8 `_iter_records` entries become 8 fingerprint entries with `decision_group: sparse-token-lookup`. Governance UI groups them. Expiry applies to the group. But matching is still per-fingerprint.

3. **Structured review fields are optional metadata, not required schema.** Provide them as suggested fields in `strict manifest add-exception` output. Don't enforce them. Let teams adopt them if they find them useful, rather than mandating ceremony that degrades to boilerplate.

4. **Drop the module budget cap.** Replace with Seren's suppression rate metric — a percentage-based signal that scales naturally, rather than an absolute cap that creates cliff edges.

This preserves deterministic matching (my concern), captures architectural decision grouping (Gideon's insight), and avoids the structured-field boilerplate trap. The governance benefit of decision-scoping is real — but it belongs in the presentation layer, not the matching layer.
