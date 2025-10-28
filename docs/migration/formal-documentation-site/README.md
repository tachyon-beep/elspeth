# Formal Documentation Site - Work Package

**Work Package Start Date**: 2025-10-26
**Methodology**: Quality-First Documentation Development
**Current Phase**: Phase 0 - Bootstrap (**READY TO START**)
**Tech Stack**: MkDocs + Material for MkDocs + mkdocstrings

---

## Executive Summary

We're establishing a formal, polished documentation site (`site-docs/`) alongside our existing developer documentation (`docs/`). This dual-documentation strategy allows us to:

1. **Maintain comprehensive developer docs** - Raw ADRs, refactoring methodologies, migration plans (audit trail for compliance)
2. **Create curated public docs** - User-focused guides, polished architecture overviews, API reference (external stakeholders)

**Core Philosophy**: **Document quality is the primary factor**, with speed, scope, and tooling as secondary trade-offs. We're treating documentation as a first-class engineering artifact with the same rigor as our refactoring methodology.

---

## Quick Status

| Phase | Task | Status | Effort | Quality Gates |
|-------|------|--------|--------|---------------|
| **0** | **Bootstrap** | 🟡 **READY** | 1-2h | Local preview works, theme customized |
| **1** | **Core Content** | ⏸️ **PENDING** | 12-16h | Technical review, tested examples, diagrams |
| **2** | **API Reference** | ⏸️ **PENDING** | 8-12h | Docstring quality audit, working examples |
| **3** | **Polish** | ⏸️ **PENDING** | 6-10h | UX testing, stakeholder approval |
| **4** | **Deployment** | ⏸️ **PENDING** | 2-4h | CI/CD working, versioning configured |
| **Total** | **Complete Site** | ⏸️ **0% COMPLETE** | **40-55h** | **2-3 weeks** |

---

## Why This Matters

### For Users
- **Findability**: Search-enabled docs with instant results
- **Learnability**: Progressive disclosure (quickstart → deep dives)
- **Trust**: Professional presentation signals project maturity

### For Contributors
- **Onboarding**: "Getting Started" reduces time-to-first-contribution
- **Architecture Understanding**: Distilled ADRs explain *why* decisions were made
- **API Discovery**: Auto-generated reference from docstrings

### For Compliance
- **Regulatory Review**: Polished security controls documentation
- **Audit Trail**: Git-tracked docs with versioning matching releases
- **Evidence**: SBOM, audit logging, security model in one authoritative location

---

## Strategic Context

### The Dual-Documentation Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│ DEVELOPER DOCS (docs/)                                          │
│ - Raw, comprehensive, "working messy"                          │
│ - ADRs with full decision history                              │
│ - Refactoring methodology (process documentation)              │
│ - Migration plans (temporary, version-specific)                │
│ - Archive folder (historical context)                          │
│                                                                 │
│ Audience: Core contributors, security auditors                 │
│ Quality Standard: Complete > Polished                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ FORMAL DOCS (site-docs/)                                        │
│ - Curated, polished, "publication-ready"                       │
│ - Architecture overviews (distilled from ADRs)                 │
│ - User guides (how to use, not how to build)                   │
│ - API reference (auto-generated, organized)                    │
│ - Getting started (installation → first experiment)            │
│                                                                 │
│ Audience: End users, new contributors, compliance reviewers    │
│ Quality Standard: Polished > Comprehensive                     │
└─────────────────────────────────────────────────────────────────┘
```

**This isn't duplication** - it's **defense in depth for knowledge management**:
- Developer docs prove *why* decisions were made (auditor requirement)
- Formal docs prove *what* the system does (user requirement)

---

## Tech Stack Rationale

### Core Components

| Component | Version | Purpose |
|-----------|---------|---------|
| **MkDocs** | ≥1.5.0 | Static site generator (Python-native) |
| **Material for MkDocs** | ≥9.5.0 | Premium theme (quality-focused) |
| **mkdocstrings[python]** | ≥0.24.0 | API doc auto-generation |
| **pymdown-extensions** | ≥10.7 | Enhanced Markdown features |

### Why This Stack?

**Quality of Output** (PRIMARY FACTOR):
- Material theme produces professional, beautiful documentation out-of-box
- Typography, spacing, colors are carefully designed (not "good enough")
- Mobile-responsive, accessibility-compliant (WCAG 2.1)
- Code blocks with syntax highlighting rival Read the Docs

**Developer Experience → Documentation Quality Loop**:
- Hot-reload in <1 second → You'll actually keep docs updated
- Instant preview → See quality in real-time while writing
- Markdown familiarity → Focus on content, not markup syntax
- Fast iteration → More time for polish, less for tooling fights

**Compliance & Security Alignment**:
- Static HTML output → No server-side vulnerabilities
- Offline-capable → Airgapped environments (regulated industries)
- Versioned docs → Matches signed artifacts (v1.2.3 docs ↔ v1.2.3 SBOM)
- Full audit trail → Git tracks every doc change

**Trade-offs We're Accepting**:
- ✅ **Chose**: MkDocs Material (modern, beautiful, fast)
- ❌ **Rejected**: Sphinx (more powerful but dated UI, slower builds, RST conversion needed)
- ❌ **Rejected**: Docusaurus (too heavy, Node.js dependency, overkill for Python project)

---

## Project Structure

```
elspeth/
├── docs/                          # 🔧 DEVELOPER DOCS (keep as-is)
│   ├── architecture/
│   ├── development/
│   ├── migration/
│   ├── refactoring/
│   └── ...
│
├── site-docs/                     # 📘 FORMAL DOCUMENTATION (new)
│   ├── docs/                      # Markdown source content
│   │   ├── index.md
│   │   ├── getting-started/
│   │   ├── user-guide/
│   │   ├── plugins/
│   │   ├── api-reference/
│   │   ├── architecture/
│   │   ├── compliance/
│   │   └── operations/
│   ├── mkdocs.yml                 # MkDocs configuration
│   ├── overrides/                 # Theme customizations
│   └── requirements.txt           # MkDocs dependencies
│
└── site/                          # 🌐 BUILT SITE (gitignored)
```

---

## Phase Breakdown

### Phase 0: Bootstrap (1-2 hours)

**Objective**: Get local MkDocs site running with minimal content

**Tasks**:
1. Create `site-docs/` folder structure
2. Install MkDocs + Material in dev lockfile
3. Create initial `mkdocs.yml` with all features enabled
4. Write skeleton `index.md` (landing page)
5. Configure theme (colors, logo, navigation)
6. Test local build (`mkdocs serve`)
7. Update `.gitignore` and `Makefile`

**Exit Criteria**:
- ✅ `mkdocs serve` runs without errors
- ✅ Landing page displays with Material theme
- ✅ Search works
- ✅ Navigation structure defined

**Quality Gates**:
- Theme customized (not default colors)
- All MkDocs warnings addressed
- Local preview mobile-responsive

---

### Phase 1: Core Content Migration (12-16 hours)

**Objective**: Migrate/write essential user-facing content

**Priority Order** (highest ROI first):

1. **Getting Started** (NEW, 3-4 hours)
   - Installation guide (distill from CLAUDE.md)
   - Quickstart (simple experiment walkthrough)
   - First experiment (end-to-end with explanations)

2. **Security Model** (DISTILL, 3-4 hours) - CRITICAL
   - User-friendly explanation of Bell-LaPadula MLS
   - Visual diagrams ("no read up", security levels)
   - Common scenarios (datasource + sink combinations)
   - Troubleshooting security validation errors

3. **Plugin Catalogue** (REFINE, 2-3 hours)
   - Use existing `docs/architecture/plugin-catalogue.md`
   - Reorganize by use case (not plugin type)
   - Add usage examples for each plugin
   - Link to API reference

4. **Configuration Guide** (DISTILL, 2-3 hours)
   - Explain merge order (suite defaults → prompt packs → experiment)
   - Common patterns (multi-sink, baseline comparison)
   - Troubleshooting validation errors

5. **Architecture Overview** (DISTILL, 2-3 hours)
   - High-level system design (sources → transforms → sinks)
   - Pipeline orchestration
   - Security enforcement model
   - Plugin registry framework

**Exit Criteria**:
- ✅ All 5 core content areas complete
- ✅ Technical review by stakeholder
- ✅ Code examples tested and working
- ✅ Cross-references validated

**Quality Gates**:
- Each guide has ≥1 working example
- No broken internal links
- Readability score: Flesch-Kincaid ≥60 (accessible to college grads)
- Stakeholder approval

---

### Phase 2: API Reference (8-12 hours)

**Objective**: Auto-generate comprehensive API docs from docstrings

**Tasks**:

1. **Docstring Quality Audit** (3-4 hours)
   - Review docstrings in `src/elspeth/core/`
   - Ensure Google-style formatting
   - Add missing Args/Returns/Raises sections
   - Add usage examples to key classes

2. **mkdocstrings Integration** (2-3 hours)
   - Configure mkdocstrings plugin
   - Organize by module (security, pipeline, registries)
   - Create summary tables (class overview, function index)

3. **Code Examples** (3-5 hours)
   - Add examples to API reference pages
   - Test all code snippets
   - Link to relevant user guide sections

**Exit Criteria**:
- ✅ API reference covers core modules
- ✅ Docstrings pass quality audit
- ✅ Examples tested and working
- ✅ Navigation from user guide to API reference seamless

**Quality Gates**:
- Every public class has docstring
- Every public method has Args/Returns
- ≥50% of classes have usage examples
- No mkdocstrings warnings

---

### Phase 3: Polish (6-10 hours)

**Objective**: Elevate from "good" to "excellent"

**Tasks**:

1. **Navigation UX** (2-3 hours)
   - Test navigation flow (can users find what they need?)
   - Reorganize if needed
   - Add "Related pages" sections
   - Create breadcrumb trails

2. **Visual Design** (2-3 hours)
   - Add diagrams (architecture, security model, pipeline flow)
   - Customize theme colors (brand alignment)
   - Add logo/favicon
   - Improve code block presentation

3. **Search Optimization** (1-2 hours)
   - Test search queries users might try
   - Add keywords to pages
   - Ensure titles are descriptive

4. **Quality Assurance** (2-3 hours)
   - Run link checker
   - Test all code examples
   - Proofread all content
   - Stakeholder review session

**Exit Criteria**:
- ✅ Navigation tested by someone unfamiliar with project
- ✅ All diagrams rendering correctly
- ✅ No broken links
- ✅ Stakeholder approval for 1.0 release

**Quality Gates**:
- Navigation depth ≤3 levels (avoid overwhelming users)
- Search returns relevant results for top 10 queries
- Mobile preview tested on actual device
- Stakeholder sign-off

---

### Phase 4: Deployment (2-4 hours)

**Objective**: Make docs publicly accessible with versioning

**Tasks**:

1. **Hosting Setup** (1-2 hours)
   - Configure GitHub Pages (or internal server)
   - Test deployed site
   - Configure custom domain (if applicable)

2. **CI/CD Integration** (1-2 hours)
   - Create `.github/workflows/docs.yml`
   - Auto-deploy on main branch changes
   - Build validation on PRs

3. **Versioning** (1-2 hours)
   - Integrate `mike` for version management
   - Configure version dropdown
   - Document versioning workflow

**Exit Criteria**:
- ✅ Site deployed and accessible
- ✅ CI/CD working (auto-deploy on merge)
- ✅ Versioning configured
- ✅ Deployment documented

**Quality Gates**:
- Deployment completes in <5 minutes
- No broken links on deployed site
- Version selector works
- HTTPS enabled (if public)

---

## Success Metrics

### Quantitative
- ✅ 100% of core content areas complete (Getting Started, Security Model, Plugins, Config, Architecture)
- ✅ ≥80% API reference coverage (all core modules documented)
- ✅ 0 broken links
- ✅ Build time <30 seconds
- ✅ Search returns relevant results for ≥90% of queries

### Qualitative
- ✅ Stakeholder approval ("I'd be proud to show this to users")
- ✅ New contributor can complete quickstart in <30 minutes
- ✅ Security model explanation understandable to non-experts
- ✅ Professional presentation (not "good for open source")

---

## Risk Assessment

### High Risk
- **Content Quality**: Risk of rushing and producing mediocre docs
  - **Mitigation**: Quality gates at each phase, stakeholder reviews

- **Scope Creep**: Risk of trying to document everything before 1.0
  - **Mitigation**: Strict priority matrix, "must-have" vs. "nice-to-have"

### Medium Risk
- **Docstring Quality**: API reference only as good as source docstrings
  - **Mitigation**: Phase 2 includes docstring audit

- **Maintenance Burden**: Two doc sets to maintain
  - **Mitigation**: Clear separation (developer vs. formal), automation where possible

### Low Risk
- **Tech Stack**: MkDocs is mature and widely used
- **Migration**: No conversion needed (already using Markdown)

---

## Files in This Work Package

| File | Purpose | Status |
|------|---------|--------|
| `README.md` | Work package overview (this file) | ✅ Complete |
| `00-STATUS.md` | Progress dashboard | ⏸️ Next |
| `01-PHILOSOPHY-AND-STRATEGY.md` | Quality-first principles | ⏸️ Pending |
| `02-IMPLEMENTATION-PLAN.md` | Detailed phased approach | ⏸️ Pending |
| `03-CONTENT-MIGRATION-MATRIX.md` | Content inventory with priorities | ⏸️ Pending |
| `04-BOOTSTRAP-GUIDE.md` | Step-by-step initial setup | ⏸️ Pending |
| `05-QUALITY-GATES.md` | QA criteria for each phase | ⏸️ Pending |
| `mkdocs-configs/mkdocs.yml.template` | Full MkDocs configuration | ⏸️ Pending |
| `mkdocs-configs/nav-structure.yml` | Navigation organization | ⏸️ Pending |

---

## Key Insights

### Insight 1: Documentation Quality Mirrors Code Quality

Just as Elspeth uses **zero-regression refactoring methodology** for code, this work package uses **quality gates for documentation**. Each phase has explicit quality criteria (not just "done" vs. "not done").

### Insight 2: Dual-Docs Strategy Enables Quality

Keeping developer docs (`docs/`) as-is removes pressure to "clean up" raw content. This frees formal docs (`site-docs/`) to be curated and polished without losing historical context.

### Insight 3: Tech Stack Enables Quality

MkDocs Material's hot-reload isn't about speed - it's about **reducing friction to maintain quality**. When preview updates instantly, you iterate until content is excellent (not just "good enough").

---

`★ Insight ─────────────────────────────────────`
**Quality-First Documentation Philosophy**:

1. **Primary Factor**: Document quality (clarity, completeness, presentation)
2. **Secondary Factors**: Speed, scope, tooling complexity

This mirrors Elspeth's **security-first architecture**:
- Security isn't a feature → Quality isn't a phase
- Fail-fast validation → Quality gates at each stage
- Bell-LaPadula rigor → Documentation rigor

The methodology is proven: **Refactoring PRs #10 and #11 achieved zero regressions by spending 30-40% of time on safety nets**. This work package spends 30-40% of time on quality gates (Phase 3 polish + reviews).
`─────────────────────────────────────────────────`

---

## Next Actions

### Immediate (This Session)
1. ✅ Create work package structure (DONE)
2. ⏸️ Write remaining planning documents
3. ⏸️ Create configuration templates

### Next Session (Phase 0 Start)
1. Install MkDocs + Material in dev lockfile
2. Create `site-docs/` folder structure
3. Write skeleton content and initial config
4. Test local preview

### Future Sessions
- Phase 1: Core content migration (12-16 hours)
- Phase 2: API reference (8-12 hours)
- Phase 3: Polish (6-10 hours)
- Phase 4: Deployment (2-4 hours)

---

**Work Package Start**: 2025-10-26
**Estimated Completion**: 2-3 weeks (allowing for quality review cycles)
**Status**: Planning phase complete, ready for Phase 0 bootstrap

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
