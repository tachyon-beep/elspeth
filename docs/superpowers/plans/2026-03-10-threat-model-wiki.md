# Threat Model Wiki Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static MkDocs wiki as a navigation and access layer over the Agentic Code Threat Model Discussion Paper (DRAFT v0.3).

**Architecture:** MkDocs with Material for MkDocs theme, deployed to GitHub Pages. The wiki has ~25 pages: the full paper as a single navigable page, 13 individual ACF taxonomy entries, and ~10 authored/extracted navigation pages. The paper remains the canonical source of truth; the wiki makes it findable, linkable, and actionable for 5 distinct audiences.

**Tech Stack:** MkDocs, mkdocs-material, Python (uv for package management), GitHub Pages

**Source paper:** `docs/research/threat-model/2026-03-07-agentic-code-threat-model-discussion-paper.md`

**Spec:** The user's task description in the conversation that produced this plan. The roundtable minutes at `docs/research/threat-model/wiki-structure-roundtable-minutes.md` provide design rationale.

---

## Two-Repo Setup

**CRITICAL: The working repo and the publish repo are different.**

| Role | Repo | Purpose |
|------|------|---------|
| **Working repo** | `/home/john/elspeth` (private, ELSPETH codebase) | Source paper lives here. Plan lives here. Wiki is built here under `wiki/`. |
| **Publish repo** | `github.com/johnm-dta/agentic-coding-threat-model` (public, empty) | Where the wiki deploys from. GitHub Pages is enabled with Actions source. |

**Workflow:**

1. All wiki content is authored in the **working repo** under `wiki/` — this is where the source paper is, and where subagents can read it.
2. Once the wiki is built and verified (Tasks 1-14), the entire `wiki/` directory and `.github/workflows/deploy-wiki.yml` are **copied to the publish repo** and pushed there.
3. The GitHub Actions workflow runs in the **publish repo** on push to `main`.

**Task 15 handles the handoff** — it copies the built wiki content to the publish repo, commits, and pushes. Subagents working on Tasks 1-14 should NOT attempt to push to the publish repo. All commits during Tasks 1-14 are local to the working repo (on the current branch).

**For subagents reading the source paper:** The source paper is at the absolute path `/home/john/elspeth/docs/research/threat-model/2026-03-07-agentic-code-threat-model-discussion-paper.md` in the working repo. All `wiki/` paths are relative to the working repo root (`/home/john/elspeth/wiki/`).

---

## File Structure

All wiki content lives under a new top-level `wiki/` directory (separate from the project's existing `docs/`):

```
wiki/
├── mkdocs.yml                            # Site configuration
├── docs/
│   ├── index.md                          # Landing page — audience router
│   ├── executive-brief.md                # 3-screen SES brief
│   ├── paper.md                          # Full paper as single navigable page
│   ├── reading-guides.md                 # 5 curated link-lists
│   ├── when-this-does-not-apply.md       # Scope boundaries
│   ├── compounding-effect.md             # How threats interact (§3.3)
│   ├── glossary.md                       # Terminology + ACF IDs
│   ├── about.md                          # Provenance, citation, version
│   ├── citizen-programmer/
│   │   ├── index.md                      # "I Use AI to Build Things at Work"
│   │   └── manager-brief.md             # One-paragraph + checklist for managers
│   └── taxonomy/
│       ├── index.md                      # ACF summary table + detection coverage
│       ├── acf-s1.md                     # Competence Spoofing
│       ├── acf-s2.md                     # Hallucinated Field Access
│       ├── acf-s3.md                     # Structural Identity Spoofing
│       ├── acf-t1.md                     # Trust Tier Conflation (Critical)
│       ├── acf-t2.md                     # Silent Coercion
│       ├── acf-r1.md                     # Audit Trail Destruction
│       ├── acf-r2.md                     # Partial Completion
│       ├── acf-i1.md                     # Verbose Error Response
│       ├── acf-i2.md                     # Stack Trace Exposure
│       ├── acf-d1.md                     # Finding Flood
│       ├── acf-d2.md                     # Review Capacity Exhaustion
│       ├── acf-e1.md                     # Implicit Privilege Grant (Critical)
│       └── acf-e2.md                     # Unvalidated Delegation
└── overrides/                            # (optional) Custom Material theme overrides
```

---

## Chunk 1: Foundation — MkDocs Setup and Full Paper Page

This chunk establishes the project skeleton and the canonical source page that everything else links into. Nothing else can be built until `paper.md` exists with correct anchor IDs.

### Task 1: Project Setup and mkdocs.yml

**Files:**
- Create: `wiki/mkdocs.yml`

**Context for the worker:**
- Use `uv` for package management (project rule — never use pip directly)
- The wiki is OFFICIAL classification Australian Government content — professional, not flashy
- Material theme with navy/dark blue primary palette

- [ ] **Step 1: Install MkDocs and Material theme**

```bash
uv pip install mkdocs "mkdocs-material[imaging]"
```

Note: If the project uses a `pyproject.toml` with managed dependencies, prefer `uv add --dev mkdocs mkdocs-material` instead. Check what exists first.

- [ ] **Step 2: Create the wiki directory structure**

```bash
mkdir -p wiki/docs/taxonomy wiki/docs/citizen-programmer
```

- [ ] **Step 3: Create mkdocs.yml**

Create `wiki/mkdocs.yml` with the following configuration:

```yaml
site_name: "Agentic Code Threat Model"
site_description: "A threat model for AI-assisted software development in government systems"
site_url: "https://johnm-dta.github.io/agentic-coding-threat-model/"
repo_url: "https://github.com/johnm-dta/agentic-coding-threat-model"

theme:
  name: material
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode
  features:
    - navigation.tabs
    - navigation.indexes
    - navigation.top
    - navigation.footer
    - search.suggest
    - search.highlight
    - content.tabs.link
    - content.code.copy
    - toc.integrate
  icon:
    repo: fontawesome/brands/github

plugins:
  - search

markdown_extensions:
  - admonition
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  - pymdownx.highlight:
      anchor_linenums: true
  - pymdownx.inlinehilite
  - tables
  - attr_list
  - md_in_html
  - toc:
      permalink: true

extra:
  version: "0.3"
  classification: "OFFICIAL"
  status: "DRAFT"

nav:
  - Home: index.md
  - Executive Brief: executive-brief.md
  - Reading Guides: reading-guides.md
  - The Threat Model:
      - Full Paper: paper.md
      - How Threats Compound: compounding-effect.md
      - When This Does NOT Apply: when-this-does-not-apply.md
  - ACF Taxonomy:
      - taxonomy/index.md
      - "ACF-S1: Competence Spoofing": taxonomy/acf-s1.md
      - "ACF-S2: Hallucinated Field Access": taxonomy/acf-s2.md
      - "ACF-S3: Structural Identity Spoofing": taxonomy/acf-s3.md
      - "ACF-T1: Trust Tier Conflation": taxonomy/acf-t1.md
      - "ACF-T2: Silent Coercion": taxonomy/acf-t2.md
      - "ACF-R1: Audit Trail Destruction": taxonomy/acf-r1.md
      - "ACF-R2: Partial Completion": taxonomy/acf-r2.md
      - "ACF-I1: Verbose Error Response": taxonomy/acf-i1.md
      - "ACF-I2: Stack Trace Exposure": taxonomy/acf-i2.md
      - "ACF-D1: Finding Flood": taxonomy/acf-d1.md
      - "ACF-D2: Review Capacity Exhaustion": taxonomy/acf-d2.md
      - "ACF-E1: Implicit Privilege Grant": taxonomy/acf-e1.md
      - "ACF-E2: Unvalidated Delegation": taxonomy/acf-e2.md
  - For Citizen Programmers:
      - citizen-programmer/index.md
      - Brief for Managers: citizen-programmer/manager-brief.md
  - Glossary: glossary.md
  - About This Project: about.md
```

- [ ] **Step 4: Verify MkDocs can start**

```bash
cd wiki && mkdocs build --strict 2>&1 | head -20
```

This will fail with missing pages — that's expected. We just want to confirm mkdocs.yml parses correctly (look for "Config file: wiki/mkdocs.yml" not a YAML parse error).

- [ ] **Step 5: Commit**

```bash
git add wiki/mkdocs.yml
git commit -m "feat: scaffold MkDocs wiki for threat model discussion paper"
```

---

### Task 2: Full Paper Page (paper.md)

**Files:**
- Create: `wiki/docs/paper.md`
- Read: `docs/research/threat-model/2026-03-07-agentic-code-threat-model-discussion-paper.md` (source)

**Context for the worker:**
- This is the most important page — everything else links into it via anchor IDs
- The source paper is ~1700 lines of markdown
- You must fix three things during the copy:
  1. The LaTeX `\epigraphbox{...}` command (line ~64) → convert to a standard markdown blockquote
  2. The LaTeX diagram in §5.3 (lines ~585-606, wrapped in `{=latex}` / `\begin{BVerbatim}`) → convert to a markdown code block
  3. Add an intro line at the very top before the paper content
- Every section heading must have a stable anchor ID. MkDocs auto-generates anchors from headings. Verify the auto-generated anchors match the paper's existing TOC links (e.g., `#1-introduction-and-scope`)
- The paper's existing `## Table of Contents` section (lines ~46-61) uses anchor links — these must work with MkDocs's auto-generated IDs

- [ ] **Step 1: Copy the source paper into paper.md**

Read the full source paper from `docs/research/threat-model/2026-03-07-agentic-code-threat-model-discussion-paper.md`.

Add this intro block at the very top of `wiki/docs/paper.md`, before the paper content:

```markdown
---
title: "Full Paper"
---

!!! info "Navigation"
    This is the complete discussion paper. For guided reading paths, see [Reading Guides](reading-guides.md). For the executive summary, see [Executive Brief](executive-brief.md).

    **Classification:** OFFICIAL | **Status:** DRAFT v0.3 | **Date:** March 2026

---

```

Then paste the full paper content below.

- [ ] **Step 2: Fix the LaTeX epigraph**

Find the line (around line 64 of the source):
```
\epigraphbox{The concern is not that AI outputs are always poor, but that they may become persuasive, efficient, and operationally privileged faster than institutions adapt their assurance methods.}{ChatGPT 5.4, on being asked to review this paper}
```

Replace with:
```markdown
> *"The concern is not that AI outputs are always poor, but that they may become persuasive, efficient, and operationally privileged faster than institutions adapt their assurance methods."*
>
> — ChatGPT 5.4, on being asked to review this paper
```

- [ ] **Step 3: Fix the LaTeX diagram in §5.3**

Find the LaTeX block (around lines 585-606 of the source) that starts with `` ```{=latex} `` and contains `\begin{BVerbatim}`.

Replace the entire block (from `` ```{=latex} `` to the closing `` ``` ``) with:

````markdown
```text
Agent generates code
        │
        v
┌──────────────────────┐
│  VALIDATION BOUNDARY │  ← This is the trust boundary
│                      │
│  • Automated semantic│     Not just syntax/type checking —
│    boundary checking │     trust tier flow, defensive pattern
│  • Human review of   │     detection, audit trail completeness
│    semantic intent   │
│  • Attestation       │     Reviewer attests validation was
│                      │     meaningful, not rubber-stamped
└──────────────────────┘
        │
        v
Code enters repository
(now Tier 2 — validated)
```
````

- [ ] **Step 4: Verify anchor IDs work**

Build the site and check that the paper's internal TOC links resolve:

```bash
cd wiki && mkdocs build --strict 2>&1 | grep -i "paper.md" | head -20
```

Note: `--strict` will warn about broken internal links. Some warnings about other missing pages are expected at this stage — we only care about paper.md internal anchors.

- [ ] **Step 5: Create placeholder files for all other pages**

Create minimal placeholder files so `mkdocs build` doesn't fail on missing nav entries. Each placeholder should contain just:

```markdown
# [Page Title]

*Content coming soon.*
```

Create placeholders for: `index.md`, `executive-brief.md`, `reading-guides.md`, `when-this-does-not-apply.md`, `compounding-effect.md`, `glossary.md`, `about.md`, `citizen-programmer/index.md`, `citizen-programmer/manager-brief.md`, `taxonomy/index.md`, and all 13 `taxonomy/acf-*.md` files.

- [ ] **Step 6: Verify full build succeeds**

```bash
cd wiki && mkdocs build --strict
```

All warnings about missing pages should be gone. There may be warnings about broken cross-links in paper.md — that's expected until other pages exist with real content.

- [ ] **Step 7: Commit**

```bash
git add wiki/docs/
git commit -m "feat: add full paper page and placeholder wiki pages"
```

---

## Chunk 2: ACF Taxonomy Pages

All 13 ACF entries plus the taxonomy hub. These are mechanical extractions from Appendix A of the paper. The 13 individual pages are independent of each other and can be built in parallel by subagents.

**IMPORTANT for parallel execution:** Each ACF page is independent — no cross-dependencies between pages. The taxonomy hub (Task 4) depends on all 13 entries being complete but can be built from the source paper directly, so it can also be parallelized.

### Task 3: ACF Template Entry — ACF-T1 (build first as template)

**Files:**
- Create: `wiki/docs/taxonomy/acf-t1.md`
- Read: Source paper, lines 1295-1339 (ACF-T1 entry in Appendix A)

**Context for the worker:**
- ACF-T1 is the richest entry and one of two Critical-rated entries — build it first as the template for all others
- Extract content verbatim from Appendix A of the source paper at `docs/research/threat-model/2026-03-07-agentic-code-threat-model-discussion-paper.md`
- Use Material's content tabs (`=== "Agent-Generated (BAD)"` / `=== "Correct"`) for side-by-side code examples
- The detection feasibility tier for ACF-T1 is **Taint-required** (requires data flow / taint tracking)

- [ ] **Step 1: Create ACF-T1 page**

Create `wiki/docs/taxonomy/acf-t1.md` with this exact structure:

```markdown
---
title: "ACF-T1: Trust Tier Conflation"
---

# ACF-T1: Trust Tier Conflation

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Tampering |
| **Risk Rating** | Critical |
| **Existing Detection** | None |
| **Detection Feasibility** | Taint-required |

## Description

Data from an external (untrusted) source is used in an internal (trusted) context without passing through a validation boundary. The data's effective trust level is silently elevated.

## Why Agents Produce This

Python's type system doesn't distinguish between data from different sources. A `dict` from `requests.get().json()` and a `dict` from a validated internal query are the same type. Agents see both as "a dict" and treat them interchangeably because nothing in the language tells them otherwise.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — clean, readable, catastrophically wrong
    def sync_partner_records(partner_api_url):
        response = requests.get(f"{partner_api_url}/records")
        records = response.json()
        for record in records:
            db.execute(
                insert(internal_records).values(**record)
            )
        # External data inserted directly into internal database.
        # No schema validation, no field allowlisting, no type checking.
        # Partner could send arbitrary fields, wrong types, injection payloads.
    ```

=== "Correct"

    ```python
    # Correct — validate at the boundary
    def sync_partner_records(partner_api_url):
        response = requests.get(f"{partner_api_url}/records")
        raw_records = response.json()
        for raw in raw_records:
            try:
                validated = PartnerRecordSchema.validate(raw)
            except ValidationError as e:
                quarantine(raw, reason=str(e))
                continue
            db.execute(
                insert(internal_records).values(
                    name=validated.name,
                    status=validated.status,
                )
            )
    ```

## Why It's Dangerous

This is the most critical failure mode because it compromises the integrity of the internal data store — the system's source of truth. Once external data enters the internal store without validation, every downstream consumer trusts it as internal data. Corruption propagates invisibly.

## Detection Approach

Taint analysis — trace the return values of functions marked `@external_boundary` (or matched by the known external call heuristic list) and flag if they reach data store operations without passing through a function marked `@validates_external`. This is the core capability of the tool described in Appendix B of the paper.

## Related Entries

- [ACF-T2: Silent Coercion](acf-t2.md) — related tampering pattern involving type coercion across boundaries
- [ACF-E1: Implicit Privilege Grant](acf-e1.md) — the elevation consequence of trust tier conflation
- [How Threats Compound](../compounding-effect.md) — trust tier conflation is step 1 in the 5-step compounding scenario

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
```

- [ ] **Step 2: Verify build**

```bash
cd wiki && mkdocs build --strict 2>&1 | grep -i "acf-t1" | head -10
```

- [ ] **Step 3: Commit**

```bash
git add wiki/docs/taxonomy/acf-t1.md
git commit -m "feat: add ACF-T1 taxonomy page — template for remaining entries"
```

---

### Task 4: Remaining 12 ACF Entry Pages (parallelizable)

**Files:**
- Create: `wiki/docs/taxonomy/acf-s1.md` through `wiki/docs/taxonomy/acf-e2.md` (12 files)
- Read: Source paper Appendix A (lines 1152-1534)

**Context for the worker:**
- Follow the exact template established in Task 3 (ACF-T1)
- Extract all content verbatim from Appendix A of the source paper
- For ACF-D1 and ACF-D2 (process threats): replace the code example section with a description of the process failure mode, and set Detection Feasibility to "Process threat — not a code pattern"
- Use Material content tabs for code examples on all entries that have BAD/GOOD pairs
- ACF-I2 has minimal content (noted in paper as "included for taxonomy completeness")

**Detection feasibility tiers to assign:**

| ACF ID | Detection Feasibility |
|--------|----------------------|
| ACF-S1 | Annotation-required |
| ACF-S2 | AST-matchable (if typed) |
| ACF-S3 | AST-matchable |
| ACF-T2 | Annotation-required |
| ACF-R1 | Annotation-required |
| ACF-R2 | Human-judgment |
| ACF-I1 | AST-matchable (partial) |
| ACF-I2 | AST-matchable |
| ACF-D1 | Process threat — not a code pattern |
| ACF-D2 | Process threat — not a code pattern |
| ACF-E1 | Taint-required |
| ACF-E2 | Taint-required (partial) |

**Related entries to cross-link (extract from paper cross-references):**

| ACF ID | Related Entries |
|--------|----------------|
| ACF-S1 | ACF-S2, ACF-S3, ACF-T2, compounding-effect |
| ACF-S2 | ACF-S1, ACF-S3 |
| ACF-S3 | ACF-S1, ACF-E1, compounding-effect |
| ACF-T2 | ACF-T1, ACF-S1 |
| ACF-R1 | ACF-R2, compounding-effect |
| ACF-R2 | ACF-R1 |
| ACF-I1 | ACF-I2 |
| ACF-I2 | ACF-I1 |
| ACF-D1 | ACF-D2 |
| ACF-D2 | ACF-D1 |
| ACF-E1 | ACF-T1, ACF-S3, ACF-E2, compounding-effect |
| ACF-E2 | ACF-E1, ACF-T1 |

**Parallel execution strategy:** This task can be split across up to 4 subagents, each handling 3 entries:
- Agent A: ACF-S1, ACF-S2, ACF-S3
- Agent B: ACF-T2, ACF-R1, ACF-R2
- Agent C: ACF-I1, ACF-I2, ACF-D1
- Agent D: ACF-D2, ACF-E1, ACF-E2

Each subagent should:
1. Read the source paper's Appendix A for its assigned entries
2. Create each page following the ACF-T1 template exactly
3. Use content tabs for BAD/GOOD code examples
4. Include the provenance banner, scope warning, property table, and footer links

- [ ] **Step 1: Create all 12 ACF pages** (see parallel strategy above)

- [ ] **Step 2: Verify all pages build**

```bash
cd wiki && mkdocs build --strict 2>&1 | grep -i "warning\|error" | head -20
```

- [ ] **Step 3: Commit**

```bash
git add wiki/docs/taxonomy/acf-*.md
git commit -m "feat: add remaining 12 ACF taxonomy entry pages"
```

---

### Task 5: ACF Taxonomy Hub Page

**Files:**
- Create: `wiki/docs/taxonomy/index.md`
- Read: Source paper Appendix A summary table (lines 1156-1173) and detection capability summary (lines 1525-1534)

**Context for the worker:**
- This is the index page for the taxonomy section — the page a CISO bookmarks
- Extract the summary table verbatim from Appendix A, making each ACF ID a link to its detail page
- Extract the detection capability summary table verbatim
- Highlight that both Critical-rated entries have zero detection

- [ ] **Step 1: Create taxonomy hub page**

Create `wiki/docs/taxonomy/index.md` with:

1. Title: "ACF Taxonomy"
2. Provenance banner (same as ACF entries)
3. Brief intro paragraph: what the taxonomy is, that it's provisional (v0.3), mapped to STRIDE
4. Summary table from Appendix A with ACF IDs as links to detail pages — columns: ID, Name, STRIDE Category, Risk Rating, Existing Detection
5. Detection Capability Summary section with the None/Partial/Good/N/A breakdown table, including the specific failure IDs in each category. Add an admonition highlighting: "Both Critical-rated entries — ACF-T1 and ACF-E1 — have zero existing detection."
6. Link to "When This Does NOT Apply" page
7. Footer link back to paper.md Appendix A

- [ ] **Step 2: Verify build**

```bash
cd wiki && mkdocs build --strict 2>&1 | grep -i "warning\|error" | head -20
```

- [ ] **Step 3: Commit**

```bash
git add wiki/docs/taxonomy/index.md
git commit -m "feat: add ACF taxonomy hub with summary table and detection coverage"
```

---

## Chunk 3: Authored and Extracted Navigation Pages

These pages require either original authoring (citizen programmer, executive brief, when-this-does-not-apply) or careful extraction with editorial framing (compounding effect, glossary, about). They are mostly independent and can be built in parallel.

**Parallel execution strategy:** These 8 pages can be split across 3-4 subagents:
- Agent A: `executive-brief.md`, `about.md`
- Agent B: `citizen-programmer/index.md`, `citizen-programmer/manager-brief.md`
- Agent C: `when-this-does-not-apply.md`, `compounding-effect.md`
- Agent D: `glossary.md`, `index.md` (landing page)

### Task 6: Landing Page

**Files:**
- Create: `wiki/docs/index.md`

**Context for the worker:**
- This is the audience router — the first thing everyone sees
- Risk statement must pass the "Senate Estimates test" (could be read aloud without embarrassment)
- No code, no jargon
- Use Material admonitions for the three priority actions and audience entry points
- The SES officer from the roundtable demanded: "What's the risk, what do I sign, what does it cost?"
- Tone: direct, professional, slightly urgent — "hey, are you watching for this" not "we have determined that"

- [ ] **Step 1: Create landing page**

Create `wiki/docs/index.md` with:

1. Title: "When Agents Write Code"
2. One-line description: "A threat model for AI-assisted software development in government systems"
3. Classification line: `**Classification:** OFFICIAL | **Status:** DRAFT v0.3 | **Date:** March 2026`
4. Risk statement (2-3 paragraphs, no code, no jargon) — synthesize from the Abstract and Executive Summary of the paper. Key points:
   - AI coding agents produce professional-looking code that silently violates security boundaries
   - Current guidance (ISM, NIST SSDF, Essential Eight) doesn't address this
   - 5 of 13 identified failure patterns have no detection mechanism at all, including both Critical-rated entries
5. Three priority actions as a `!!! danger "Three Priority Actions"` admonition:
   - Recommendation 2: Issue guidance on treating agent output as a trust boundary
   - Recommendation 3: Extend ISM controls for agent-generated code
   - Recommendation 11: Document institutional security knowledge in machine-readable form
   - Link each to the relevant section anchor in paper.md
6. Audience entry points using `!!! tip` or `!!! example` admonitions for 5 paths:
   - **Executive / SES**: → Executive Brief
   - **CISO / IRAP Assessor**: → Reading Guides (CISO path)
   - **Developer / Architect**: → ACF Taxonomy
   - **Tool Builder**: → ACF Taxonomy (detection approaches)
   - **I Use AI to Build Things at Work**: → Citizen Programmer guide
7. Link to full paper

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/index.md
git commit -m "feat: add wiki landing page with audience router"
```

---

### Task 7: Executive Brief

**Files:**
- Create: `wiki/docs/executive-brief.md`
- Read: Source paper Executive Summary (lines 30-42), §6.6 (lines 746-758), §1.2.8 (lines 125-135), §10.1 Recs 2/3 and §10.3 Rec 11

**Context for the worker:**
- This page is for SES officers and CIOs — no code, no taxonomy codes, no hedging beyond accuracy
- Must pass the "Senate Estimates test"
- Every recommendation includes a sense of what it costs/involves
- Extract and condense from the paper — do NOT paraphrase the arguments, just tighten the language

- [ ] **Step 1: Create executive brief**

Create `wiki/docs/executive-brief.md` with:

1. Title and provenance banner
2. **The Risk** — one paragraph, no code. Agents produce plausible, test-passing code that silently violates security boundaries. The novel risk isn't malicious code, it's plausible-but-wrong code at volume. Use the `session.get("username", "root")` example described in plain language (not as code).
3. **The Gap** — the 5-of-13 stat, ISM/NIST coverage gaps condensed from §6. Both Critical-rated failure modes have zero detection. Current frameworks address human-authored code; agent code has different failure characteristics (correlated, consistent surface quality, no persistent learning).
4. **The Expanding Perimeter** — citizen programmers condensed from §1.2.8. Domain specialists with legitimate access producing executable logic outside SDLC controls.
5. **Three Priority Actions** — Recommendations 2, 3, and 11 with one-sentence description of what each involves and why it's the priority. Include cost/effort framing:
   - Rec 2 (trust boundary guidance): "Requires policy development, no new tooling"
   - Rec 3 (ISM extensions): "Extends existing controls, leverages June 2025 ISM foundations"
   - Rec 11 (machine-readable security knowledge): "Requires no new tooling — encodes existing knowledge in checkable form"
6. **Where to Read More** — links to full paper, gap analysis section, case study section

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/executive-brief.md
git commit -m "feat: add executive brief page"
```

---

### Task 8: Citizen Programmer Pages

**Files:**
- Create: `wiki/docs/citizen-programmer/index.md`
- Create: `wiki/docs/citizen-programmer/manager-brief.md`
- Read: Source paper §1.2.8 (lines 125-135) for the governance perimeter argument

**Context for the worker:**
- CRITICAL: No jargon, no taxonomy codes, no STRIDE, no ISM control numbers
- This is new authored content, not extraction — drawing on §1.2.8 and the four most critical ACF entries (S1, T1, R1, E1)
- The citizen programmer agent from the roundtable demanded: "Am I doing something dangerous? What do I do Monday morning?"
- The scenarios must be things a BA or analyst might actually do
- Tone: empathetic, not alarming — "it's not your fault" and "you've built something valuable"

- [ ] **Step 1: Create citizen programmer main page**

Create `wiki/docs/citizen-programmer/index.md` with the following content:

1. Title: "I Use AI to Build Things at Work"

2. Opening paragraph (use this verbatim):

> If you use AI tools like ChatGPT, Claude, Copilot, or similar to build plugins, automations, scripts, dashboards, or integrations at work — this page is for you. You may be doing something risky without realising it, and it's not your fault.

3. **3-4 plain-language scenarios** — rewrite these ACF failure modes as things a BA/analyst might actually do. Use approximately these scenarios:

   - **(From ACF-S1 — Competence Spoofing):** "You asked an AI to build a reporting plugin. It pulls data from your database and shows a dashboard. But when the database connection drops briefly, the plugin silently shows yesterday's data with no indication anything is wrong. Your team makes decisions based on stale numbers."

   - **(From ACF-T1 — Trust Tier Conflation):** "You asked an AI to connect two systems. It takes data from the external system and puts it straight into your internal database. No validation, no checking. If the external system sends bad data, your internal records are corrupted."

   - **(From ACF-R1 — Audit Trail Destruction):** "You asked an AI to automate an approval workflow. When the approval fails to save, the AI wrote code that logs the error and moves on. The approval happened, but there's no record of it. If someone asks 'who approved this and when?' — the answer is 'we don't know.'"

   - **(From ACF-E1 — Implicit Privilege Grant):** "You asked an AI to build an integration with a partner system. The partner system says 'this person is verified' and your tool grants them access — no independent check, no record of why access was given. If the partner system is wrong or compromised, everyone it vouches for gets in."

4. **Self-assessment checklist** (format as a numbered list of yes/no questions):

   1. Does your AI-built tool connect to a database or system that other people rely on?
   2. Does it run automatically (on a schedule, on a trigger) without you watching?
   3. Would anyone be harmed, misinformed, or unable to do their job if it silently produced wrong results?
   4. Did you test what happens when a connection fails or data is missing?
   5. Does anyone in IT or security know this tool exists?
   6. If you answered "yes" to two or more of these questions, talk to your IT team. You've probably built something valuable — but it may need guardrails you can't add yourself.

5. **"What to Do Monday Morning"** section: Talk to your IT team or manager. Share what you've built. Ask them to review it. This isn't about getting in trouble — it's about making sure the useful thing you built doesn't accidentally cause problems.

6. Link to the full governance perimeter argument in the paper: `[Read the full security analysis →](../paper.md#128-coding-is-no-longer-confined-to-developers)`

- [ ] **Step 2: Create manager brief**

Create `wiki/docs/citizen-programmer/manager-brief.md` with:

1. Title: "Brief for Managers"

2. Opening paragraph (use this verbatim):

> Your team members may be building software with AI tools without realising it. A business analyst who uses an AI tool to build a reporting dashboard, a data integration, or a workflow automation is producing executable logic that can affect your organisation's data integrity, security, and audit trails — even though they don't think of themselves as programmers, and even though they have legitimate access to the systems involved.

3. Link to the self-assessment checklist: "Share the [self-assessment checklist](index.md#self-assessment) with your team."

4. **"What to Do"** section: Have a team conversation about AI tool usage. No blame, no prohibition. The goal is visibility — knowing what exists so IT can help make it safe. If team members have built tools that connect to shared databases or systems, loop in IT for a lightweight review.

5. Link to Recommendation 5 in paper.md: `[Read the full policy recommendation →](../paper.md#101-for-security-policy-bodies-asd-acsc)`

- [ ] **Step 3: Commit**

```bash
git add wiki/docs/citizen-programmer/
git commit -m "feat: add citizen programmer guide and manager brief"
```

---

### Task 9: When This Does NOT Apply

**Files:**
- Create: `wiki/docs/when-this-does-not-apply.md`
- Read: Source paper §2.2 "A necessary clarification" paragraph (lines 214-215)

**Context for the worker:**
- Purpose: prevent cargo-culting — state clearly where the paper's guidance does NOT apply
- This page is linked from EVERY ACF entry page's scope warning
- Content is authored, drawing on §2.2's "necessary clarification"

- [ ] **Step 1: Create the page**

Create `wiki/docs/when-this-does-not-apply.md` with the 4-part structure from the task description:

1. Defensive programming is correct in most software (web app "Unknown" example, `.get()` with defaults is fine in most contexts)
2. This paper applies specifically when silent data corruption is worse than a crash (list the system types)
3. Decision test: "If a field is missing from a record, is it better for the system to crash, or to continue with a default value?"
4. Even in applicable systems, not every function is security-critical — link to trust tier model (§5)

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/when-this-does-not-apply.md
git commit -m "feat: add scope boundaries page — when this does NOT apply"
```

---

### Task 10: Compounding Effect

**Files:**
- Create: `wiki/docs/compounding-effect.md`
- Read: Source paper §3.3 (lines 496-507)

**Context for the worker:**
- Extract §3.3 almost verbatim
- The 5-step scenario (E → R → S → T → D) is the core content
- Add links to each referenced ACF entry
- Brief intro explaining why this matters

- [ ] **Step 1: Create the page**

Create `wiki/docs/compounding-effect.md` with:

1. Title: "How Threats Compound"
2. Provenance banner
3. Intro paragraph: "Each individual pattern looks like ordinary defensive coding. The compound effect is a system that silently produces wrong results, can't explain why, and passed every review gate."
4. The 5-step scenario from §3.3, with each step linking to its ACF entry:
   - Step 1: Trust tier conflation → [ACF-E1](taxonomy/acf-e1.md) — NOTE: the paper says E (Elevation) not E1 specifically, but the step describes trust tier conflation which is actually ACF-T1. Check the paper carefully — §3.3 says "trust tier conflation (E)" meaning the STRIDE category E, but the ACF entry for trust tier conflation is ACF-T1. The compounding scenario uses STRIDE letters, not ACF IDs. Map correctly:
     - (E) trust tier conflation → [ACF-T1](taxonomy/acf-t1.md) and [ACF-E1](taxonomy/acf-e1.md)
     - (R) audit trail destruction → [ACF-R1](taxonomy/acf-r1.md)
     - (S) competence spoofing → [ACF-S1](taxonomy/acf-s1.md)
     - (T) silent trust tier coercion → [ACF-T1](taxonomy/acf-t1.md) and [ACF-T2](taxonomy/acf-t2.md)
     - (D) finding flood → [ACF-D1](taxonomy/acf-d1.md) and [ACF-D2](taxonomy/acf-d2.md)
5. Closing line about why the interaction matters

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/compounding-effect.md
git commit -m "feat: add compounding effect page showing threat interaction"
```

---

### Task 11: Glossary

**Files:**
- Create: `wiki/docs/glossary.md`
- Read: Source paper §1.3 (lines 137-148) and Appendix A summary table (lines 1156-1173)

**Context for the worker:**
- Extract the §1.3 terminology table verbatim
- Add ACF taxonomy IDs with one-line plain-language definitions, each linking to its taxonomy page
- Format as a definition list or table

- [ ] **Step 1: Create glossary**

Create `wiki/docs/glossary.md` with:

1. Title: "Glossary"
2. Provenance banner
3. Section: "Key Terms" — the terminology table from §1.3 (Agent, Agentic code, Autocomplete, Agent deployment spectrum, Trust boundary, Trust tier, Validation boundary, Defensive anti-pattern)
4. Section: "ACF Taxonomy Quick Reference" — all 13 ACF IDs with one-line plain-language definitions. Example: "**ACF-S1 (Competence Spoofing):** Code that fabricates default values where the absence of data should be treated as an error. [Details →](taxonomy/acf-s1.md)"

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/glossary.md
git commit -m "feat: add glossary with terminology and ACF quick reference"
```

---

### Task 12: About Page

**Files:**
- Create: `wiki/docs/about.md`
- Read: Source paper version table (lines 8-14), citation (lines 1701), methodology (lines 150-168)

**Context for the worker:**
- Provenance, citation, version history — straightforward extraction

- [ ] **Step 1: Create about page**

Create `wiki/docs/about.md` with:

1. Title: "About This Project"
2. Classification: OFFICIAL
3. Paper citation: `Morrissey, J. (ORCID: 0009-0000-5654-3782). "When Agents Write Code: A Threat Model for AI-Assisted Software Development in Government Systems." Discussion Paper, DRAFT v0.3, 8 March 2026. Digital Transformation Agency.` **Note:** The source paper's closing citation line says "v0.2" (it was written before the v0.3 update). Use "v0.3" as shown above — the paper header confirms v0.3 is the current version.
4. Version history table extracted from paper (versions 0.1 through 0.3)
5. Statement that this is a discussion paper — community input welcomed
6. Link to paper's methodology section (§1.4)
7. Note that the wiki is a navigation layer over the paper; the paper is the canonical source
8. Placeholder for feedback mechanism: "Feedback and contributions can be directed to [contact mechanism TBD]."

- [ ] **Step 2: Commit**

```bash
git add wiki/docs/about.md
git commit -m "feat: add about page with provenance and citation"
```

---

## Chunk 4: Reading Guides and Final Verification

Reading guides depend on paper.md anchors and all other pages existing. This chunk must run last.

### Task 13: Reading Guides

**Files:**
- Create: `wiki/docs/reading-guides.md`
- Read: Source paper Table of Contents (lines 46-61) for anchor IDs

**Context for the worker:**
- These are ordered link-lists with one-sentence context per link — NOT separate content
- Each link points to an anchor in paper.md or to a standalone wiki page
- The anchor format in paper.md follows MkDocs auto-generation: heading text lowercased, spaces to hyphens, special chars removed
- You must verify that every anchor you reference actually exists in paper.md

- [ ] **Step 1: Create reading guides page**

Create `wiki/docs/reading-guides.md` with:

1. Title: "Reading Guides"
2. Provenance banner
3. Brief intro: "Five curated paths through the paper for different audiences. Each path is an ordered sequence of links with one-sentence context — not separate content."
4. Five sections, each with an ordered list of links:

**SES / Executive** (~5 links):
- The classification example (paper.md#23-a-concrete-example)
- Executive Brief (executive-brief.md)
- Self-assessment (paper.md#appendix-c-agent-autonomy-self-assessment)
- Recommendations for policy bodies (paper.md#101-for-security-policy-bodies-asd-acsc)

**CISO / IRAP Assessor** (~7 links):
- The insidious threat (paper.md#22-the-insidious-threat-model)
- Gap analysis (paper.md#6-current-guidance-gap-analysis)
- Detection coverage (paper.md#66-detection-coverage-is-worst-where-risk-is-highest)
- Review as attack surface (paper.md#4-the-review-process-as-attack-surface)
- Recommendations for assessors (paper.md#102-for-irap-assessors)
- ACF taxonomy summary (taxonomy/index.md)
- Open questions (paper.md#9-open-questions-for-the-community)

**Developer / Architect** (~8 links):
- The insidious threat model (paper.md#22-the-insidious-threat-model)
- Concrete example (paper.md#23-a-concrete-example)
- Trust boundary model (paper.md#5-agent-output-as-a-trust-boundary)
- ACF taxonomy detailed entries (taxonomy/index.md)
- Technical controls (paper.md#72-technical-controls-whats-buildable)
- Case study (paper.md#8-case-study-agentic-development-under-compliance-constraints)
- Recommendations for organisations (paper.md#103-for-organisations-using-agentic-coding)

**Tool Builder** (~6 links):
- ACF taxonomy entries (taxonomy/index.md) — focus on detection approaches
- Detection coverage summary (taxonomy/index.md#detection-capability-summary)
- Technical feasibility (paper.md#appendix-b-technical-feasibility-of-automated-enforcement)
- Technical controls (paper.md#72-technical-controls-whats-buildable)
- Case study enforcement sections (paper.md#84-where-the-current-process-fails)

**Citizen Programmer** (~4 links):
- Governance perimeter (paper.md#128-coding-is-no-longer-confined-to-developers)
- Citizen programmer guide (citizen-programmer/index.md)
- Self-assessment (paper.md#appendix-c-agent-autonomy-self-assessment)
- Recommendations §10.1 Rec 5 (paper.md#101-for-security-policy-bodies-asd-acsc)

**IMPORTANT:** The anchor IDs above are best guesses based on MkDocs auto-generation rules. After creating the page, verify each anchor by checking paper.md headings. MkDocs generates anchors by: lowercasing, replacing spaces with hyphens, removing special characters except hyphens. For example:
- `## 2.3 A Concrete Example` → `#23-a-concrete-example`
- `### 10.1 For Security Policy Bodies (ASD, ACSC)` → `#101-for-security-policy-bodies-asd-acsc`
- `## Appendix C: Agent Autonomy Self-Assessment` → `#appendix-c-agent-autonomy-self-assessment`

- [ ] **Step 2: Verify all links resolve**

```bash
cd wiki && mkdocs build --strict 2>&1 | grep -i "warning\|error" | head -30
```

Fix any broken anchors.

- [ ] **Step 3: Commit**

```bash
git add wiki/docs/reading-guides.md
git commit -m "feat: add reading guides with 5 audience paths"
```

---

### Task 14: Final Verification

**Files:**
- All wiki files

**Context for the worker:**
- Verify the entire wiki builds cleanly and all cross-links work
- Test local serving

- [ ] **Step 1: Full strict build**

```bash
cd wiki && mkdocs build --strict 2>&1
```

Fix any warnings or errors.

- [ ] **Step 2: Verify local serving**

```bash
cd wiki && mkdocs serve --dev-addr 127.0.0.1:8001 &
sleep 3
# Check key pages load
curl -s http://127.0.0.1:8001/ | head -20
curl -s http://127.0.0.1:8001/paper/ | head -20
curl -s http://127.0.0.1:8001/taxonomy/ | head -20
curl -s http://127.0.0.1:8001/taxonomy/acf-t1/ | head -20
kill %1
```

- [ ] **Step 3: Verify Material content tabs render correctly**

The `=== "Agent-Generated (BAD)"` / `=== "Correct"` syntax in ACF entry pages is the feature most likely to silently fail (renders as plain text instead of tabbed panels if whitespace is wrong). Check that it actually produces tabbed HTML:

```bash
cd wiki && mkdocs build --strict
# Check ACF-T1 for tabbed content rendering
grep -c "tabbed-set" site/taxonomy/acf-t1/index.html
```

Expected: a count > 0 (confirms Material's tabbed extension is rendering). If the count is 0, the content tabs are rendering as plain text — check the `pymdownx.tabbed` extension is enabled in mkdocs.yml and that the `===` lines in the ACF pages have correct indentation (the content under each tab must be indented 4 spaces).

- [ ] **Step 4: Verify search works**

```bash
# Check search index was generated
ls -la wiki/site/search/search_index.json
```

- [ ] **Step 5: Commit any fixes**

```bash
git add wiki/
git commit -m "fix: resolve build warnings and cross-link issues"
```

- [ ] **Step 6: Final status report**

Report:
- Total pages built
- Any remaining warnings
- Content tabs rendering confirmed (yes/no)
- Whether the site is ready for publish (Task 15)

---

### Task 15: Publish to Target Repo and Deploy

**Files:**
- Create (in publish repo): `.github/workflows/deploy-wiki.yml`
- Copy (to publish repo): `wiki/` directory

**Context for the worker:**
- **This task copies the built wiki from the ELSPETH working repo to the publish repo and triggers deployment.**
- The working repo is `/home/john/elspeth` — this is where `wiki/` was built during Tasks 1-14.
- The publish repo is `github.com/johnm-dta/agentic-coding-threat-model` — currently empty, with GitHub Pages enabled (Actions source).
- GitHub Pages is already configured: `build_type: "workflow"`, URL: `https://johnm-dta.github.io/agentic-coding-threat-model/`
- Do NOT modify the ELSPETH repo's git history — all pushes go to the publish repo only.

- [ ] **Step 1: Clone the publish repo**

```bash
cd /tmp
git clone https://github.com/johnm-dta/agentic-coding-threat-model.git
cd agentic-coding-threat-model
```

- [ ] **Step 2: Copy wiki content from working repo**

```bash
cp -r /home/john/elspeth/wiki/* .
# Result: mkdocs.yml, docs/, and any overrides/ are now at the repo root
# The publish repo structure is:
#   mkdocs.yml
#   docs/
#     index.md
#     paper.md
#     taxonomy/
#     ...
```

**Note:** In the publish repo, the wiki content lives at the ROOT (not under `wiki/`). The `mkdocs.yml` is at the repo root. Adjust the GitHub Actions workflow paths accordingly.

- [ ] **Step 3: Create the GitHub Actions workflow**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches:
      - main
  workflow_dispatch:  # Allow manual trigger

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install mkdocs mkdocs-material

      - name: Build site
        run: mkdocs build --strict

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 4: Update mkdocs.yml paths for publish repo layout**

Since the publish repo has `mkdocs.yml` at the root (not under `wiki/`), verify `docs_dir` is set correctly. The default (`docs/`) should work since we copied `wiki/docs/` → `docs/`.

Confirm `site_url` and `repo_url` are set:
```yaml
site_url: "https://johnm-dta.github.io/agentic-coding-threat-model/"
repo_url: "https://github.com/johnm-dta/agentic-coding-threat-model"
```

- [ ] **Step 5: Commit and push to publish repo**

```bash
git add -A
git commit -m "feat: initial wiki — Agentic Code Threat Model navigation layer

25 pages: full paper, 13 ACF taxonomy entries, executive brief,
citizen programmer guide, reading guides, glossary, and more.

Source: Discussion Paper DRAFT v0.3 (March 2026)"
git push origin main
```

- [ ] **Step 6: Verify deployment**

```bash
# Check the Actions workflow ran
gh run list --repo johnm-dta/agentic-coding-threat-model --limit 1

# Wait for it to complete, then verify the site
gh run view --repo johnm-dta/agentic-coding-threat-model $(gh run list --repo johnm-dta/agentic-coding-threat-model --limit 1 --json databaseId -q '.[0].databaseId')
```

Then confirm the site is accessible at `https://johnm-dta.github.io/agentic-coding-threat-model/`.

**Note:** GitHub Pages is already enabled with Source set to "GitHub Actions". No manual settings changes needed.

---

## Execution Summary

| Chunk | Tasks | Parallelizable? | Dependencies |
|-------|-------|-----------------|-------------|
| 1: Foundation | Tasks 1-2 | Sequential | None |
| 2: ACF Taxonomy | Tasks 3-5 | Task 4 (12 entries) fully parallel across 4 agents; Task 5 parallel with Task 4 | Chunk 1 complete |
| 3: Authored Pages | Tasks 6-12 | Fully parallel across 3-4 agents | Chunk 1 complete |
| 4: Final | Tasks 13-15 | Sequential (13-14 verify, 15 deploys) | Chunks 1-3 complete |

**Optimal subagent allocation:**
- Stage 1 (sequential): 1 agent does Tasks 1-2
- Stage 2 (parallel): 4-5 agents split Tasks 3-12 (ACF entries + authored pages simultaneously)
- Stage 3 (sequential): 1 agent does Tasks 13-14, then Task 15 (deployment, requires user input)

**Total estimated tasks:** 15 tasks, ~25 files created
