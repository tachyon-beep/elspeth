# Wiki Structure Roundtable — Minutes

**Subject:** Restructuring the Agentic Code Threat Model Discussion Paper into a Wiki
**Source paper:** `2026-03-07-agentic-code-threat-model-discussion-paper.md` (DRAFT v0.3)
**Date:** 2026-03-10
**Format:** 5-round structured deliberation with steelman obligations and mandatory dissent
**Scribe:** Claude (roundtable scribe agent)

## Participants

### Customer Personas (5)

| Agent | Perspective | Core test for the wiki |
|-------|------------|----------------------|
| **Policy Practitioner** | CISO / risk manager / IRAP assessor | "Can I put ACF-T1 in a risk register and link to a canonical definition?" |
| **Technical Practitioner** | Developer on compliance-constrained codebase | "Can I go from CI flag to code fix in 60 seconds?" |
| **Tool Builder** | SAST / CI/CD pipeline developer | "Can I write a detection rule from this page alone?" |
| **Citizen Programmer** | Business analyst building with AI tools | "Am I doing something dangerous? What do I do Monday morning?" |
| **SES Officer** | SES Band 1 executive decision-maker | "What's the risk, what do I sign, what does it cost?" |

### Structural Specialists (5)

| Agent | Perspective | Core concern |
|-------|------------|-------------|
| **UX Specialist** | Navigation architecture, task-based design | Audience self-selection, progressive disclosure patterns |
| **Information Architect** | Content decomposition, cross-reference integrity | Page count, tagging, canonical concept homes |
| **Educator** | Concept dependencies, learning paths, belief revision | Prerequisite bottlenecks, pedagogical sequencing |
| **Adversarial Reader** | Cold-landing stress test, search-engine arrivals | Context-free page survival, misleading-in-isolation risk |
| **Compliance Mapper** | Framework cross-referencing (ISM, NIST, E8, OWASP) | Bidirectional navigation, gap register traceability |

---

## Round 1 — Opening Statements

### Summary

All 10 agents proposed their ideal wiki structure. Proposals ranged from 3 pages (SES officer) to 37 pages (information architect).

### Universal Agreement (all 10 agents)

- The paper's linear structure must not be reproduced in the wiki
- Audience-aware navigation is essential
- The ACF taxonomy is the paper's most reusable artifact

### Key Proposals

**Policy Practitioner:** 5 audience-driven pages. Invert the paper — lead with "what to do" (recommendations + candidate controls), support with "why" (gap analysis + taxonomy), defer "how we got here" (threat model + case study). ACF entries need stable anchors for risk registers. Zero code on policy pages.

**Technical Practitioner:** 11 pages in 3 tiers by usage frequency. Tier 1 "Lookup Layer" (ACF cards with BAD/GOOD code examples, detection matrix, trust tier quick reference). Tier 2 "Understanding Layer" (STRIDE, review problem, tooling guide). Tier 3 "Policy Layer" (gap analysis, recommendations). Principle: "lookup-first, narrative-second."

**Tool Builder:** 5 pages focused on implementability. ACF Registry with machine-actionable AST pattern specifications per entry. Detection feasibility tiers (AST-matchable / taint-required / annotation-required / human-judgment). Taint model and governance model as standalone references. Detection Gap Dashboard as a living page.

**Citizen Programmer:** Separate non-developer path. "I use AI to build things at work" landing → self-assessment checklist (plain yes/no questions) → plain-language failure modes as scenarios → immediate individual actions → escalation triggers. Key demand: no jargon, no taxonomy codes, no STRIDE. "The paper diagnosed my situation in §1.2.8 and then wrote the rest for someone else."

**SES Officer:** 3 pages maximum. Landing page (one screen): risk in one paragraph, gap stat, three decision points, cost of inaction. Page 2: "What We Need to Do" — recommendations with resource/budget implications. Page 3: "Evidence Base" — tables as exhibits. No code, no hedging. "What do I sign?"

**UX Specialist:** Audience router landing page (5 pathways, not a TOC). Progressive disclosure via structural separation (split monoliths into summary/detail page pairs). Audience tags, prerequisites blocks, and role-differentiated next-steps on every page. ACF as hub-and-spoke. Core diagnosis: task-based navigation over argument-based navigation.

**Information Architect:** 37 pages across 3 tiers. Tier 1: 12 standalone pages mirroring major sections. Tier 2: ACF hub + 13 individual entry pages + Appendix B split into 3. Tier 3: 6 atomic concept pages for foundational ideas referenced 4+ times (Trust Tier Model, Validation Boundary, Defensive Anti-Pattern, Correlated Failure, Review Capacity, Governance Perimeter). Multi-dimensional tagging scheme. Cross-reference density map.

**Educator:** 5-layer concept dependency graph (Layer 0 foundational → Layer 4 actionable). 4 prerequisite bottlenecks identified, with defensive programming inversion as CRITICAL. 4 audience learning paths. Key insight: this paper requires belief revision (convincing practitioners that "good" patterns are contextually dangerous), not knowledge acquisition. The citizen programmer has NO learning path in the current paper.

**Adversarial Reader:** 7 cold-landing confusion points. 6 "every page must have" rules: context sentence, breadcrumb, term definitions, audience marker, prerequisites, self-contained claims. Core risk: wiki fragmentation will destroy the compounding argument (§3.3). Proposed dedicated "How These Threats Compound" page.

**Compliance Mapper:** Bidirectional framework cross-reference as first-class navigation (ACF→Framework and Framework→ACF). 5 proposed cross-reference views (ISM mapping, NIST mapping, ACF cross-ref, Gap Register, Recommendation Traceability). Noted absence of PSPF mapping despite Australian Government context.

### Key Tensions Identified

| Tension | Positions |
|---------|-----------|
| Code examples | Inline (technical) · Collapsible (UX) · Sub-pages (policy) · Plain-language (citizen) · AST specs (tool-builder) |
| Page count | 3 (SES) · 5 (policy) · 11 (technical) · 37 (info-architect) |
| ACF entry depth | Risk register anchors (policy) · Lookup cards (technical) · Machine specs (tool-builder) · Scenarios (citizen) |
| Entry point | "What's your role?" (UX) · "Do you use AI?" (citizen) · "What do I sign?" (SES) |

---

## Round 2 — Steelman Round

### Summary

Each agent steelmanned another agent's proposal. The SES officer's "3 pages max" position was steelmanned by 6 agents — the most-validated position in the roundtable. Two significant position shifts occurred.

### Steelman Map

| Agent | Steelmanned | Key insight added |
|-------|-------------|-------------------|
| Compliance Mapper | SES Officer | "Compliance mapping nobody reads is worse than no compliance mapping" |
| Adversarial Reader | SES Officer | "Attention is a security resource" — finding-flood DoS applied to the wiki |
| SES Officer | Info Architect | "My 3 pages need the 37-page evidence base to be trustworthy" |
| Info Architect | SES Officer | **POSITION SHIFT:** "Changed my thinking" — 37 pages is reference layer, not entry layer |
| Technical Practitioner | SES Officer | "The wiki doesn't exist until someone funds it" — deploy 3 now, add 34 later |
| Educator | SES Officer | Cognitive load theory — extraneous information degrades decision quality |
| Tool Builder | Citizen Programmer | Checklist is "human-executed triage gate at the only boundary where detection can occur" |
| UX Specialist | SES Officer | Two interaction modes: navigation (guided paths) vs. decision (self-contained brief) |
| Policy Practitioner | Citizen Programmer | Parallel path is a coverage failure fix, not an accessibility accommodation |
| Citizen Programmer | Technical Practitioner | **POSITION SHIFT:** "ACF codes are coordinates, not jargon" — sustained use > first contact |

### Emerging Consensus After Round 2

Progressive disclosure architecture with 3-layer design: executive decision surface (entry) → audience-routed navigation paths → comprehensive reference layer. Plus a parallel citizen-programmer path as a structurally separate intake mechanism.

---

## Round 3 — Dissent Round

### Summary

The dissent round fundamentally challenged the Round 2 consensus. 5 of 10 agents dissented on their own Round 1 proposals — genuine self-correction, not just cross-criticism. The 3-layer progressive disclosure architecture was attacked from 5 directions.

### Dissent Inventory

| Agent | Target | Core Argument | Self-Dissent? |
|-------|--------|---------------|---------------|
| Compliance Mapper | Own cross-ref pages | ISM revises quarterly; stale mappings produce incorrect accreditation decisions. O(n×m) maintenance surface. | Yes |
| SES Officer | Own "3 pages" + consensus | Cathedral vs. leaflet — ship a PDF now. Also: "decisions separated from analysis" has the same automation bias the paper warns about. No maintenance model. | Yes |
| Adversarial Reader | Progressive disclosure | 80%+ of traffic arrives via search engines at Layer 3. PD arrows point the wrong way. Missing "when does this NOT apply?" page — risk of "`.get()` is always dangerous" cargo cult. | No |
| Info Architect | Own atomic concept pages | Concepts shift meaning by context (Trust Tier = data classification in §5.1, taint dimension in App B, CI gate in §8.4). No editorial team. Proposed inline callouts as alternative. Revised page count to ~20. | Yes |
| Educator | Progressive disclosure | PD is for courses; wikis are for reference. 80%+ of steady-state traffic bypasses Layers 1-2. Citizen-programmer path can't close a prerequisite gap with a navigation layer. | No |
| Technical Practitioner | Own ACF cards as structure | 150-200 cross-references = ACF-S1 (competence spoofing) applied to documentation. Broken semantic links are silently misleading. Proposed organising around stable frames (STRIDE, trust tiers, control hierarchy) with ACF as content, not structure. | Yes |
| Tool Builder | Taxonomy governance gap | Taxonomy is incomplete, Python-specific, and will evolve. No process for new entries, severity reclassification, or language-specific implementations. Needs governance & contribution layer. | No |
| UX Specialist | Audience self-selection + scope | Self-selection is fiction — CISO routes around Critical-rated entries they need. Citizen-programmer path is new content authoring, not decomposition. Counter-proposed: paper as single page + ACF hub-and-spoke + reading guides. | No |
| Citizen Programmer | Reach/distribution assumption | Structure doesn't solve reach. 95% drop-off at discovery/navigation. Needs embeddable artefacts, trigger mechanisms, content for secondary distribution. "Designing a beautiful library; my audience doesn't go to libraries." | No |
| Policy Practitioner | Versioning/authority gap | No version contract for taxonomy IDs (ACF-T1 split scenario). No recommendation lifecycle tracking. Progressive disclosure strips epistemic humility. "Build less. Maintain it. Version it. Or don't build it at all." | Yes |

### Five Dissent Clusters

1. **Maintenance / Silent Rot** (5 agents — strongest cluster): Cross-references, atomic pages, audience paths, and compliance mappings will silently degrade. Stale compliance content is worse than no content.

2. **Architecture Mismatch** (2 agents): Progressive disclosure assumes top-down learning navigation; real use is bottom-up reference lookup via search engines. Audience routing pages will be ghost pages.

3. **Deployment Tempo** (1 agent, reinforced by others): Ship a PDF this month, iterate later. "Don't build the cathedral. Print the pamphlet."

4. **Reach / Distribution** (1 agent): The wiki lives where citizen programmers never go. Needs embeddable artefacts designed for secondary distribution.

5. **Governance / Versioning** (2 agents): No versioning for a provisional taxonomy, no lifecycle tracking, no provenance banner.

### New Structural Requirements Surfaced

- Provenance banner on every page (policy practitioner)
- "When does this NOT apply?" page (adversarial reader)
- Embeddable artefacts for secondary distribution (citizen programmer)
- Taxonomy governance process (tool builder)
- Version contract for ACF IDs (policy practitioner)
- Recommendation lifecycle tracking (policy practitioner)
- Inline definition callouts replacing atomic concept pages (information architect)

---

## Round 4 — Steelman the Dissents

### Summary

The scope conflation dissent ("decompose a paper" ≠ "build a knowledge base") was steelmanned by 6 of 10 agents — the strongest consensus signal in the entire roundtable. This fundamentally reframed the deliverable from "what should the wiki look like?" to "which project are we scoping, and when?"

### Steelman Map

| Agent | Dissent Steelmanned | Key Insight |
|-------|-------------------|-------------|
| SES Officer | Scope conflation | Two-deliverable split: paper decomposition (2-4 weeks) vs. knowledge base (separate funding) |
| Compliance Mapper | Scope conflation | Own R3 maintenance dissent was actually scope conflation in disguise |
| Info Architect | Scope conflation | "Appropriate fidelity" — structure must match content maturity. 3-phase proposal with adoption triggers |
| Technical Practitioner | Scope conflation | Phase 2 features in Phase 1 budget = `record.get('maintenance_owner', 'someone_will_do_it')` — competence spoofing with a plausible default |
| Policy Practitioner | Scope conflation | Governance demands dissolve when scope is paper decomposition — citations become bibliographic |
| Educator | Scope conflation | "Study guide, not textbook" — wiki wraps the paper, doesn't replace it. Genre translation destroys argument + calibrated confidence |
| Tool Builder | Maintenance rot | Data normalisation: ACF taxonomy as YAML/JSON structured data, wiki pages generated from it. 2hrs/month maintenance budget as design constraint |
| UX Specialist | Governance gap | ACF entries are citation targets — need version badges, changelog anchors, taxonomy status page. Silent mutation = ACF-R1 applied to the wiki itself |
| Adversarial Reader | Maintenance rot | Wiki is a navigation layer over the paper, not a decomposition of it. Single-source-of-truth: every fact in one place only |
| Citizen Programmer | Maintenance rot | "The more accessible the content, the more damage maintenance rot does" — plain-language readers have no independent verification capability |

### The Phased Model Emerges

All 10 agents independently converged on a phased delivery model:

- **Phase 1 (now):** Paper decomposition — navigable web page + ACF entries + executive brief + reading guides. Days to weeks. Near-zero maintenance.
- **Phase 2 (triggered by adoption):** Enhanced navigation — faceted views, version semantics, structural pages. Moderate maintenance.
- **Phase 3 (triggered by taxonomy stabilisation):** Full knowledge base — community contributions, living compliance mappings, editorial governance.

### Key Design Principles Established

1. The paper remains the canonical source of truth — the wiki is a navigation layer, not a replacement
2. Only decompose what earns its maintenance cost
3. Maintenance budget (~2hrs/month realistic) is a design constraint, not an afterthought
4. Every fact in exactly one place — audience-specific pages link into the paper, not duplicate from it
5. Provenance and versioning are structural, not cosmetic

---

## Round 5 — Final Convergence + Minority Report

### Result

**Unanimous support** for the phased consensus (all 10 agents). One minority report filed.

### Final Positions

| Agent | Verdict | Key Caveats/Modifications |
|-------|---------|--------------------------|
| Policy Practitioner | SUPPORT | Citizen-programmer to Phase 2 (not 3). ACF as individual pages. |
| Technical Practitioner | SUPPORT | ACF as individual pages with full code examples. Worked compounding example in Phase 1. |
| Tool Builder | SUPPORT | ACF pages must include detection feasibility tiers and pattern specs. Structured YAML/JSON registry in Phase 1. |
| Citizen Programmer | CONDITIONAL SUPPORT | **MINORITY REPORT:** Citizen-programmer content must be Phase 1 (1 page + 1 checklist + 1 manager brief). |
| SES Officer | SUPPORT | Resource implications on every recommendation. Landing page risk statement must pass Senate Estimates test. |
| UX Specialist | SUPPORT | ACF as individual pages. Version badges (`v0.3 — DRAFT`) on ACF pages from Phase 1. |
| Info Architect | SUPPORT | ACF as individual pages. Explicit cross-reference principle: structural links encouraged, semantic links discouraged. Detection matrix as canonical cross-reference location. |
| Educator | SUPPORT | Worked compounding example in Phase 1. Citizen-programmer companion to Phase 2 (not 3). |
| Adversarial Reader | SUPPORT | "When Does This NOT Apply?" page mandatory in Phase 1. Contextual scope line on every ACF page. |
| Compliance Mapper | SUPPORT | Framework reference anchors (ISM controls, NIST practices) in §6 as linkable in-page anchors. |

### Resolved Tensions

| Tension | Resolution | Vote |
|---------|-----------|------|
| ACF entry format | **Individual pages** | 7-2 consensus |
| "When does this NOT apply?" | **Phase 1** | 6-1 consensus |
| Compounding example | **Phase 1** (recommended) | 4-2, leaning yes |
| Version badges on ACF pages | **Phase 1** (recommended) | 2 explicit, others silent |
| Citizen-programmer timing | **Unresolved** — minority report filed | 1 Phase 1, 2 Phase 2, 4 Phase 3 |

---

## Final Consensus: The Wiki Structure Recommendation

### Architecture: Phased Delivery with Paper as Canonical Source

The wiki is a **navigation and access layer** over the paper, not a replacement for it. The paper retains its argumentative structure, calibrated confidence levels, and epistemic caveats. The wiki makes the paper's content findable, linkable, and actionable for multiple audiences.

### Phase 1 — Paper Decomposition (ship in days to weeks)

**Scope:** Restructure existing paper content for web navigation. No new analytical content except where noted.

**Pages:**

1. **Landing Page** — Audience router with risk statement that passes the Senate Estimates test: *"Current security guidance does not address AI coding tools that produce professional-looking code which silently violates security boundaries — and five of the thirteen identified failure patterns have no detection mechanism at all."* Routes to: executive brief, audience reading guides, ACF taxonomy, full paper.

2. **Executive Brief** (3 pages, also available as PDF) — The risk (one paragraph, no code), the gap (5-of-13 stat, ISM/NIST coverage gaps), three priority actions (Recommendations 2, 3, 11 with resource implications per recommendation). Links to evidence, does not require reading evidence.

3. **The Full Paper** — The paper itself as a single navigable web page with sticky table of contents, anchor links on every section and subsection, and collapsible sections for long appendices. This is the canonical source of truth. Framework references in §6 (ISM controls, NIST practices, Essential Eight) are linkable anchors.

4. **ACF Taxonomy Hub** — The Appendix A summary table + detection capability summary as a standalone page. Links to individual ACF entry pages. Filterable/sortable by STRIDE category, risk rating, and detection status.

5. **13 Individual ACF Entry Pages** (ACF-S1 through ACF-E2) — Each page contains the full Appendix A detailed entry: failure mode name, STRIDE category, risk rating, detection status, description, code example (BAD/GOOD), detection approach, "why agents produce this." Each page carries:
   - Provenance banner: `Based on Discussion Paper DRAFT v0.3 (March 2026)`
   - Version badge: `v0.3 — DRAFT`
   - Contextual scope line: *"This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When Does This NOT Apply?]."*
   - Detection feasibility tier: AST-matchable / taint-required / annotation-required / human-judgment (additive content from tool-builder)

6. **"When Does This NOT Apply?" Page** — States clearly that defensive programming is correct in most software. Defines conditions where the paper's guidance applies (audit-critical, crash-on-corruption, evidence-trail systems). Provides decision test: "Is silent data corruption worse than a crash in your system?" Linked from every ACF entry page.

7. **Audience Reading Guides** — A single "How to Read This" page with 5 curated ordered-link-lists through the paper (not separate content). Each guide is a sequence of anchor links with 1-sentence context per link:
   - SES / Executive: §2.3 example → Executive Brief → Appendix C self-assessment
   - CISO / IRAP: §6 gap analysis → §10.1-10.2 recommendations → ACF summary table
   - Developer: §2.2-2.5 threat model → §5 trust boundary → ACF detailed entries → §7.2 technical controls
   - Tool Builder: ACF entries (detection approaches) → Appendix B → §7.2
   - Citizen Programmer: §1.2.8 governance perimeter → Appendix C self-assessment → §10.1 Rec 5

8. **Glossary** — Extracted from §1.3 terminology table, extended with ACF IDs and plain-language definitions. Linked contextually from pages that use domain terms.

9. **Compounding Effect Page** (recommended) — The §3.3 argument that failure modes interact and amplify, presented as a dedicated page with the 5-step scenario (E → R → S → T → D). Prominently linked from every ACF entry page and the landing page. Stable content that doesn't change with taxonomy evolution.

**Phase 1 does NOT include:**
- Separate audience-specific content (audience reading guides link INTO the paper, they don't rewrite it)
- Bidirectional framework cross-reference indexes (Phase 2/3)
- Atomic concept pages (replaced by inline definitions where needed)
- Citizen-programmer companion guide (see Minority Report)
- Community contribution mechanisms
- Living compliance mappings

**Maintenance model:** Near-zero. Content is the paper's content. Updates when the paper versions. ACF pages are mechanical extractions. The only authored content is the executive brief, reading guides, "When Does This NOT Apply?" page, and compounding effect page — all stable.

### Phase 2 — Enhanced Navigation (triggered by adoption)

**Trigger:** Evidence of external citation — ACF entries appearing in risk registers, IRAP reports, policy documents, or tool implementations.

**Adds:**
- Faceted navigation through STRIDE categories and trust tiers as stable organisational frames
- Version semantics: changelogs on ACF pages, taxonomy status page
- Structural pages for gap analysis (§6) and recommendations (§10) as standalone navigable pages with framework cross-references
- Inline definition callouts for key concepts (Trust Tier Model, Validation Boundary, Defensive Anti-Pattern) — denormalised, lintable for consistency
- Detection capability matrix as the single canonical location for cross-cutting ACF relationships
- Citizen-programmer companion guide (if Phase 3 trigger is changed per minority report fallback)

**Maintenance model:** Moderate. Requires periodic review (~monthly) when frameworks update or detection tools mature. Sustainable within 2-4hrs/month.

### Phase 3 — Knowledge Base (triggered by taxonomy stabilisation or formal endorsement)

**Trigger:** v1.0 of the taxonomy with formal endorsement by a standards body, or sustained community contribution demonstrating the taxonomy is stable enough for living reference.

**Adds:**
- Community contribution model with taxonomy governance (new ACF proposals, severity reclassification, retirement process)
- Living compliance mappings with "last verified against [framework] [revision]" timestamps
- Language-specific detection implementations (Python as reference, others as registered implementations with measured precision)
- Structured ACF registry (YAML/JSON) as single source of truth, with wiki pages generated from it
- Recommendation lifecycle tracking (proposed / under consultation / adopted / rejected)
- Full citizen-programmer companion guide with embeddable artefacts and distribution strategy
- Editorial governance and dedicated maintenance budget

**Maintenance model:** Ongoing editorial commitment. Requires identified content owner, contribution workflows, and review processes.

### Cross-Reference Design Principle

**Structural links (facet membership) are encouraged.** ACF entries tagged with STRIDE category, risk level, detection status = mechanical, lintable, maintained by updating metadata.

**Semantic links (argument-dependent claims) are discouraged.** "This pattern compounds with ACF-R1 as described in the STRIDE mapping" = argument-dependent, rot-prone, requires human audit.

The **detection capability matrix** (centralised table mapping failure modes to detection status and control coverage) is the single canonical location for cross-cutting relationships between ACF entries. This prevents distribution of semantic claims across multiple pages.

---

## Minority Report

### Filed by: Citizen Programmer

### Position

The citizen-programmer companion guide was placed in Phase 3, the last phase, triggered by taxonomy stabilisation. This deferral is wrong. The citizen-programmer population — business analysts, operations staff, and other non-developers producing executable logic with AI tools — is the fastest-growing ungoverned risk vector identified by the paper (§1.2.8). Deferring their guidance to Phase 3 means the population most likely to cause the problems the paper describes is the last to receive any guidance.

### Argument

The paper's §1.2.8 argument is that the governance perimeter problem and the volume problem together are "materially worse than either alone." The phased consensus addresses the volume problem (developers, security practitioners) in Phase 1 and defers the perimeter problem (citizen programmers) to Phase 3. During the gap, ungoverned code production continues unchecked, and unlike the volume problem, it cannot be addressed retroactively — ungoverned code produced during the deferral period doesn't get reviewed when the companion guide eventually ships.

The citizen-programmer guide does not depend on taxonomy stabilisation. It depends on the trust tier concept (stable from the paper) and the governance perimeter argument (stable from §1.2.8). These are Phase 1 concepts.

### Requested Minimum Viable Phase 1 Addition

1. **One standalone page:** "I Use AI to Build Things at Work" — 3-4 plain-language scenarios drawn from the most critical ACF entries (S1, T1, R1, E1), a self-assessment checklist (5-6 yes/no questions), and an escalation path. Estimated authoring: ~2 hours. Ongoing maintenance: negligible (coupled to 4 ACF entries via visible provenance links).

2. **One embeddable artefact:** The self-assessment checklist formatted for extraction and placement in Confluence, SharePoint, intranet pages, or email. This is the distribution mechanism — the checklist reaches people where they already are, not where the wiki lives.

3. **One paragraph for managers:** "Your team members may be building software with AI tools without realising it. Here's a checklist to help them assess the risk." This is the trigger mechanism — managers are how you reach people who don't self-identify as your audience.

### Fallback Request

If the minimum viable addition is rejected for Phase 1, the citizen-programmer requests that the Phase 3 trigger be changed from "taxonomy stabilisation" to "first external publication of the wiki" — ensuring the companion guide ships no later than the wiki's first public release, even if the taxonomy is still provisional.

### Support for this Position

- **Policy Practitioner** and **Educator** independently proposed moving the citizen-programmer guide to Phase 2 (not Phase 3)
- **Tool Builder** argued in Round 2 that the citizen-programmer's self-assessment checklist reaches code that no automated tool will ever touch — it's upstream of the entire detection pipeline
- **UX Specialist** noted a near-minority-report on this issue but accepted Phase 3 as honest given Phase 1 budget constraints

### Counterarguments Acknowledged

- Phase 1 budget is scoped for paper decomposition, not new content authoring (UX specialist, information architect)
- A provisional taxonomy companion guide may need rewriting, violating the 2hrs/month budget (compliance mapper)
- Creating translated content requires different expertise than security architecture (SES officer)
- The distribution problem (citizen programmers won't find the wiki) exists regardless of when the content ships (adversarial reader)

The citizen programmer accepts these counterarguments as legitimate constraints but maintains that ~2 hours of authoring for a 1-page guide + embeddable checklist is within Phase 1's budget and addresses the paper's most urgent ungoverned risk.

---

## Position Evolution Tracker

Notable position shifts across the 5 rounds, demonstrating genuine intellectual movement:

| Agent | R1 Position | Final Position | Key shift |
|-------|------------|----------------|-----------|
| Info Architect | 37 pages, rich decomposition | Phased delivery, individual ACF pages only in Phase 1 | "Appropriate fidelity" — structure must match content maturity |
| SES Officer | 3 pages max, decisions separated from analysis | Phased delivery, 3-page executive brief as artifact not entry point | Self-dissented: separation creates automation bias |
| Technical Practitioner | 11 pages, ACF cards as structural crown jewel | Phased delivery, ACF as content within stable frames | ACF entries are valuable content but wrong as organisational structure |
| Citizen Programmer | Parallel non-developer path in the wiki | Separate companion deliverable + minority report on timing | "ACF codes are coordinates, not jargon" — accepted technical framing while maintaining reach concern |
| Compliance Mapper | 5 bidirectional cross-reference pages | Paper decomposition first, cross-references in Phase 2/3 | Own maintenance dissent traced back to scope conflation |
| Policy Practitioner | 5 audience-driven pages with stable ACF anchors | Phased delivery with bibliographic citations | Versioning demands dissolve when scope is paper decomposition |
| UX Specialist | Rich audience router with progressive disclosure | Paper as single page + ACF hub-and-spoke + reading guides | Self-selection is fiction; navigation mode ≠ decision mode |
| Educator | 5-layer concept dependency graph as wiki architecture | "Study guide, not textbook" — wiki wraps paper | Progressive disclosure is for courses; wikis are for reference |

---

## Key Insights and Memorable Framings

Collected from across all 5 rounds — the roundtable's most quotable contributions:

- **"Attention is a security resource."** — Adversarial Reader (R2), applying the paper's finding-flood DoS to the wiki's own dissemination
- **"We've been designing a knowledge base and pricing it as a paper decomposition."** — SES Officer (R4), identifying the scope conflation
- **"The more accessible the content, the more damage maintenance rot does."** — Citizen Programmer (R4), on why plain-language translations are most vulnerable to drift
- **"ACF codes aren't jargon — they're coordinates. Meaningless to a tourist, essential to anyone who lives there."** — Citizen Programmer (R2), steelmanning the technical practitioner
- **"That's the documentation equivalent of `record.get('maintenance_owner', 'someone_will_do_it')` — competence spoofing with a plausible default."** — Technical Practitioner (R4), applying the paper's own ACF-S1 to the wiki plan
- **"Designing a beautiful library. My audience doesn't go to libraries."** — Citizen Programmer (R3), on why structure doesn't solve reach
- **"Don't build the cathedral. Print the pamphlet."** — SES Officer (R3)
- **"Study guide, not textbook."** — Educator (R4), on the wiki's correct genre
- **"Build less. Maintain it. Version it. Or don't build it at all."** — Policy Practitioner (R3)
- **"A wiki that's consistently wrong can be identified and fixed. A wiki where some pages reflect the latest thinking and others reflect last year's is a wiki that destroys the reader's ability to trust any individual page."** — Citizen Programmer (R4)

---

## Meta-Observation

The roundtable process — 5 rounds of structured deliberation with steelman obligations and mandatory dissent — itself demonstrates the paper's §7.1 argument about prompted perspective diversity. Ten agents with different analytical frames, forced to argue positions they disagree with, produced a materially different (and stronger) architecture than any single perspective would have generated. The paper argues this works for code review. This roundtable demonstrated it works for document architecture.

The most important structural insight — that the roundtable was solving the wrong problem (wiki design when the real question was scope) — emerged only in Round 3-4, after the steelman exercise in Round 2 built sufficient mutual understanding for the dissent round to be productive rather than defensive. Without the steelman obligation, the scope conflation would likely have remained invisible, producing an elegant architecture for a wiki that would have rotted within months.

---

*Minutes compiled by the Scribe agent from 50+ messages across 5 rounds of structured deliberation.*
