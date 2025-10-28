# Documentation Philosophy and Strategy

**Document Purpose**: Define the guiding principles, strategic approach, and quality standards for Elspeth's formal documentation site.

---

## Core Philosophy: Quality First

### Primary Factor
**Document quality** is the primary factor in all documentation decisions. All other factors—speed, scope, tooling complexity, maintenance burden—are secondary trade-offs.

### What "Quality" Means

**For Users**:
- **Clarity**: Concepts explained simply without sacrificing accuracy
- **Completeness**: Enough information to accomplish goals without needing to ask
- **Usability**: Easy to find what you need, navigate between related topics
- **Trustworthiness**: Professional presentation signals project maturity

**For Contributors**:
- **Accuracy**: Technical details match implementation
- **Currentness**: Documentation updated alongside code changes
- **Examples**: Working code snippets that can be copy-pasted
- **Context**: Explains *why* decisions were made, not just *what* exists

**For Compliance Reviewers**:
- **Traceability**: Security controls mapped to implementation
- **Verifiability**: Claims backed by evidence (test results, audit logs)
- **Comprehensiveness**: All security-relevant features documented
- **Maintainability**: Documentation versioned alongside code releases

---

## Strategic Principles

### Principle 1: Dual-Documentation Strategy

**Strategy**: Maintain two separate documentation sets with distinct purposes and quality standards.

**Developer Docs** (`docs/`):
- **Purpose**: Comprehensive historical record, working notes, decision context
- **Audience**: Core contributors, security auditors, future maintainers
- **Quality Standard**: Complete > Polished
- **Update Frequency**: Continuously (living document)
- **Content Examples**: Raw ADRs, refactoring methodology, migration plans, risk assessments, execution logs

**Formal Docs** (`site-docs/`):
- **Purpose**: User-facing guides, polished architecture overviews, API reference
- **Audience**: End users, new contributors, compliance reviewers, potential adopters
- **Quality Standard**: Polished > Comprehensive
- **Update Frequency**: Versioned releases (matches software versions)
- **Content Examples**: Getting started, security model guide, plugin catalogue, configuration patterns, API reference

**Why This Works**:
- Removes pressure to "clean up" developer docs (historical context preserved)
- Enables formal docs to be highly curated (no obligation to document everything)
- Mirrors security philosophy: defense in depth for knowledge management

**Relationship Between Docs**:
```
┌─────────────────────────────────────────────────────────────┐
│ DEVELOPER DOCS (docs/)                                      │
│ - ADR-002: Multi-Level Security Enforcement (full spec)    │
│ - Risk assessment with 15 threat scenarios                 │
│ - Implementation details with code references              │
│ - Historical context (why certain approaches rejected)     │
│                                                             │
│ ↓ DISTILLED INTO ↓                                         │
│                                                             │
│ FORMAL DOCS (site-docs/)                                    │
│ - Security Model Guide (user-friendly explanation)         │
│ - Visual diagrams (Bell-LaPadula "no read up")            │
│ - Common scenarios (datasource + sink combinations)        │
│ - Troubleshooting (security validation errors)            │
└─────────────────────────────────────────────────────────────┘
```

**Not Duplication**: Developer docs prove *why* decisions were made (auditor requirement). Formal docs prove *what* the system does (user requirement).

---

### Principle 2: Content Strategies (Not Just Migration)

**Strategy**: Use appropriate content strategy for each piece of documentation, not blanket "migrate everything."

**Four Content Strategies**:

1. **COPY** - Use as-is with minimal changes
   - **When**: Content is already polished, audience-appropriate
   - **Example**: `docs/compliance/security-controls.md` → `site-docs/docs/compliance/security-controls.md`
   - **Effort**: LOW (1.0x - 1.2x time to review and reformat)

2. **REFINE** - Use existing content but improve organization, examples, clarity
   - **When**: Content is accurate but needs better structure or examples
   - **Example**: `docs/architecture/plugin-catalogue.md` → `site-docs/docs/plugins/overview.md`
   - **Effort**: MEDIUM (1.5x - 2.0x time to reorganize and enhance)

3. **DISTILL** - Extract essence from comprehensive docs into focused guides
   - **When**: Source is too detailed/technical for target audience
   - **Example**: ADR-002 (10+ pages) → `site-docs/docs/user-guide/security-model.md` (2-3 pages)
   - **Effort**: MEDIUM-HIGH (2.0x - 3.0x time to understand, extract, simplify)

4. **NEW** - Write from scratch for formal docs
   - **When**: No suitable source exists, or existing content is too mismatched
   - **Example**: `site-docs/docs/getting-started/quickstart.md` (no direct source)
   - **Effort**: HIGH (3.0x - 5.0x time to research, write, test, review)

**Content Strategy Selection Matrix**:

| Content Area | Source Quality | Audience Match | Complexity | Strategy |
|--------------|----------------|----------------|------------|----------|
| Security Controls | HIGH | GOOD | MEDIUM | **COPY** |
| Plugin Catalogue | MEDIUM | GOOD | MEDIUM | **REFINE** |
| ADR-002 (Security) | HIGH | POOR (too technical) | HIGH | **DISTILL** |
| Getting Started | N/A (none exists) | N/A | LOW | **NEW** |

---

### Principle 3: Progressive Disclosure

**Strategy**: Structure documentation so users can get value at multiple depth levels.

**Three-Level Hierarchy**:

1. **Level 1: Quickstart** (5-10 minutes)
   - "I want to run my first experiment right now"
   - Minimal explanation, maximum action
   - Copy-paste commands, pre-built example
   - Links to deeper explanations for those who want them

2. **Level 2: User Guides** (30-60 minutes)
   - "I want to understand how this works"
   - Conceptual explanations with examples
   - Common patterns and troubleshooting
   - Links to API reference for implementation details

3. **Level 3: API Reference + Architecture** (Ongoing reference)
   - "I need to know exactly how this function behaves"
   - Detailed specifications, edge cases, constraints
   - Links back to user guides for context

**Example: Security Model Documentation**

- **Level 1** (Quickstart):
  ```markdown
  Elspeth uses Bell-LaPadula Multi-Level Security. This means:
  - Each component (datasource, transform, sink) has a security level
  - Components can only access data at their level or below
  - The pipeline operates at the LOWEST level in the chain
  ```

- **Level 2** (User Guide):
  ```markdown
  # Understanding Elspeth's Security Model

  ## The Bell-LaPadula Model
  [Visual diagram showing "no read up" rule]

  ## Security Levels
  UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET

  ## Common Scenarios
  ### Scenario 1: UNOFFICIAL datasource + SECRET sink
  ❌ **Fails**: Datasource has insufficient clearance...

  [Detailed explanation with troubleshooting]
  ```

- **Level 3** (API Reference):
  ```markdown
  # elspeth.core.base.plugin.BasePlugin

  ## validate_can_operate_at_level(operating_level: SecurityLevel) -> None

  Validates whether this plugin can operate at the specified security level...

  **Args:**
    operating_level: The security level the pipeline is operating at

  **Raises:**
    SecurityValidationError: If operating_level > self.security_level...

  [Detailed behavior, edge cases, related methods]
  ```

---

### Principle 4: Quality Gates Over Speed

**Strategy**: Each phase has explicit quality criteria. Content isn't "done" until it meets the bar.

**Anti-Pattern** (Avoid):
```
✅ Write Getting Started guide
✅ Write Security Model guide
✅ Write Configuration guide
⏸️ Polish and review later
```

**Correct Pattern** (Use):
```
✅ Write Getting Started guide
✅ Test Getting Started with new contributor (<30min completion time)
✅ Stakeholder review and approval
✅ Mark Getting Started COMPLETE

✅ Write Security Model guide
✅ Test with non-expert (can they explain Bell-LaPadula?)
✅ Add visual diagrams
✅ Stakeholder review and approval
✅ Mark Security Model COMPLETE
```

**Why This Matters**:
- Partial polish is wasted effort (users see quality inconsistency)
- Quality defects compound (unclear guide → user asks question → interrupt development)
- Psychological: "Done" feels good, but "done well" builds trust

**Quality Gate Examples**:
- **Code examples**: Must be tested and working (not pseudocode)
- **Cross-references**: All links validated (no 404s)
- **Readability**: Flesch-Kincaid score ≥60 (accessible to college graduates)
- **Stakeholder approval**: Someone unfamiliar with the content gives thumbs-up

---

### Principle 5: Audience-Specific Content

**Strategy**: Write for specific personas, not "general users."

**Primary Personas**:

1. **New User (Evaluator)**
   - **Goal**: Determine if Elspeth fits their needs
   - **Questions**: "What does this do? How does it work? Can I trust it?"
   - **Content Needs**: Overview, quickstart, security model, plugin catalogue
   - **Success Metric**: Decision to adopt (or not) within 1 hour

2. **Active User (Implementer)**
   - **Goal**: Configure and run experiments successfully
   - **Questions**: "How do I configure X? Why is Y failing? What's best practice for Z?"
   - **Content Needs**: Configuration guides, troubleshooting, patterns, API reference
   - **Success Metric**: Experiment runs without support request

3. **Contributor (Developer)**
   - **Goal**: Add features or fix bugs
   - **Questions**: "How is this implemented? Where is the validation logic? What's the design rationale?"
   - **Content Needs**: Architecture overview, API reference, developer docs (raw ADRs)
   - **Success Metric**: PR submitted without architecture questions

4. **Compliance Reviewer (Auditor)**
   - **Goal**: Verify security controls and compliance claims
   - **Questions**: "How is PII protected? What audit trail exists? Is this FIPS-compliant?"
   - **Content Needs**: Security controls, compliance documentation, architecture (security focus)
   - **Success Metric**: Audit completed without requesting additional evidence

**Content Mapping**:

| Content Area | New User | Active User | Contributor | Compliance Reviewer |
|--------------|----------|-------------|-------------|---------------------|
| Getting Started | 🔥 CRITICAL | ✅ Helpful | ✅ Helpful | ❌ Not relevant |
| Security Model | ⚡ HIGH | ⚡ HIGH | ⚡ HIGH | 🔥 CRITICAL |
| Plugin Catalogue | ⚡ HIGH | 🔥 CRITICAL | ✅ Helpful | ❌ Not relevant |
| Configuration Guide | ✅ Helpful | 🔥 CRITICAL | ⚡ HIGH | ❌ Not relevant |
| API Reference | ❌ Not relevant | ⚡ HIGH | 🔥 CRITICAL | ❌ Not relevant |
| Security Controls | ✅ Helpful | ❌ Not relevant | ✅ Helpful | 🔥 CRITICAL |
| Architecture Overview | ⚡ HIGH | ✅ Helpful | 🔥 CRITICAL | ⚡ HIGH |

**Writing Guidelines by Persona**:

- **For New Users**: Lead with benefits, explain concepts simply, use visuals
- **For Active Users**: Focus on how-to, provide troubleshooting, link to details
- **For Contributors**: Explain design rationale, provide code examples, link to raw ADRs
- **For Compliance Reviewers**: Map controls to implementation, provide evidence, use precise language

---

### Principle 6: Documentation as Code

**Strategy**: Treat documentation with the same rigor as production code.

**Practices from Software Engineering**:

1. **Version Control**: All docs in Git (audit trail, blame, history)
2. **Code Review**: Documentation PRs reviewed like code PRs (technical accuracy, clarity)
3. **Testing**: Code examples tested in CI (broken examples = broken docs)
4. **CI/CD**: Automated build and deployment (broken links fail CI)
5. **Versioning**: Documentation versions match software versions (v1.2.3 docs ↔ v1.2.3 release)
6. **Metrics**: Measure quality (broken links, build time, search relevance)

**Quality Standards Borrowed from Code**:

| Code Standard | Documentation Equivalent |
|---------------|--------------------------|
| Zero compiler warnings | Zero MkDocs build warnings |
| Passing tests | All code examples tested |
| Type annotations | Explicit Args/Returns in API docs |
| Linting (Ruff) | Link checking, spell checking |
| Coverage ≥80% | API reference coverage ≥80% |
| Performance benchmarks | Build time <30 seconds, search <1 second |

**Acceptance Criteria (Like "Done" for Code)**:
- ✅ Technical accuracy verified (someone reviewed for correctness)
- ✅ Code examples tested (run in CI or manually confirmed working)
- ✅ Cross-references work (no broken links)
- ✅ Readability acceptable (Flesch-Kincaid ≥60)
- ✅ Stakeholder approval (someone says "ship it")

---

## Strategic Trade-offs

### What We're Optimizing For

✅ **Quality of User Experience**
- Beautiful, professional presentation
- Clear, accurate explanations
- Working examples
- Easy navigation

✅ **Long-Term Maintainability**
- Single source of truth (developer docs)
- Automated API reference (from docstrings)
- Versioning aligned with releases
- Clear update process

✅ **Compliance Readiness**
- Security controls documented
- Audit trail (Git history)
- Traceability (claims → evidence)
- Professional presentation for reviewers

### What We're Trading Away

❌ **Speed to First Version**
- Accepting 40-55 hour effort (not 10-hour "minimal viable docs")
- Quality gates slow down each phase
- Stakeholder reviews add time

❌ **Comprehensive Coverage**
- Phase 1 limited to 5 core content areas (not everything)
- API reference can be ≥80% coverage (not 100%)
- Some plugins deferred to post-1.0 documentation

❌ **Simplicity**
- Two doc sets to maintain (developer + formal)
- MkDocs + Material adds dependencies
- Versioning adds complexity

### Why These Trade-offs Are Acceptable

**Quality → Trust → Adoption**:
- Users judge project maturity by documentation quality
- Poor docs → Users assume code is also poor → Project not adopted
- Excellent docs → Users assume code is also excellent → Project adopted

**Compliance → Enterprise Adoption**:
- Regulated industries require professional documentation
- "Good for open source" quality isn't good enough
- Audit-ready docs unlock enterprise use cases

**Long-Term ROI**:
- 40-55 hours upfront investment
- Saves 100+ hours in support questions over project lifetime
- Enables new contributors to onboard without hand-holding

---

## Success Criteria

### Phase-by-Phase

**Phase 0 Success**:
- ✅ Local preview works
- ✅ Theme customized (not default)
- ✅ Navigation structure defined

**Phase 1 Success**:
- ✅ New user can complete quickstart in <30 minutes
- ✅ Non-expert can explain Bell-LaPadula after reading Security Model
- ✅ Every plugin has usage example
- ✅ Stakeholder approves content quality

**Phase 2 Success**:
- ✅ API reference covers ≥80% of core modules
- ✅ Every public class has Google-style docstring
- ✅ ≥50% of classes have usage examples

**Phase 3 Success**:
- ✅ Navigation tested by unfamiliar user
- ✅ 0 broken links
- ✅ Search returns relevant results for top 10 queries
- ✅ Stakeholder approves for 1.0 release

**Phase 4 Success**:
- ✅ Site deployed and publicly accessible
- ✅ CI/CD auto-deploys on merge to main
- ✅ Versioning configured

### Overall Success

**User Success**:
- New users can self-serve (no support questions for common tasks)
- Existing users find answers quickly (search + navigation)
- Contributors can onboard without architecture deep-dive meetings

**Business Success**:
- Compliance reviewers approve without requesting additional evidence
- Documentation cited as project strength (not weakness)
- Adoption increases (docs lower barrier to entry)

**Technical Success**:
- Build time <30 seconds
- 0 broken links (internal or external)
- CI validates documentation on every PR
- Documentation versions match software releases

---

## Key Insights

### Insight 1: Quality Documentation Is a Force Multiplier

**Poor Docs**:
- Users struggle → Ask questions → Interrupt development → Slow velocity

**Good Docs**:
- Users self-serve → Build successfully → Share project → Organic growth

**Calculation**:
- 40-55 hours upfront investment
- 10+ support questions avoided per week (30 min each = 5 hours/week saved)
- Break-even: ~2 months
- ROI after 1 year: 250+ hours saved

### Insight 2: Documentation Philosophy Mirrors Code Philosophy

**Elspeth's Code Philosophy** (from ADR-001):
1. Security > Features > Performance
2. Fail-fast validation
3. Zero-regression refactoring methodology

**Elspeth's Documentation Philosophy** (this document):
1. Quality > Speed > Scope
2. Quality gates at each phase
3. Documentation-as-code rigor

**Both are security-first approaches**:
- Code: Prevent insecure data access
- Docs: Prevent user confusion (which leads to insecure usage)

### Insight 3: The "Incomplete but Polished" Strategy

**Traditional Approach**:
- Document everything at 70% quality
- Plan to "polish later" (never happens)
- Result: Comprehensive but mediocre docs

**Our Approach**:
- Document 5 core areas at 95% quality (Phase 1)
- Leave some areas undocumented (explicitly marked as TODO)
- Result: Incomplete but excellent docs (users trust what exists)

**Why This Works**:
- Users prefer "some excellent docs" to "all mediocre docs"
- Clear TODOs set expectations (users know what's missing)
- High quality in core areas signals "this project is serious"

---

`★ Insight ─────────────────────────────────────`
**The Meta-Strategy: Quality as a Filtering Mechanism**

High-quality documentation acts as a **quality signal** for the entire project:
- Users: "If docs are this good, code must be too"
- Contributors: "If they care this much about docs, they care about code"
- Reviewers: "If docs are audit-ready, implementation likely is too"

This is why **quality is the primary factor**. It's not just about user experience—it's about **project credibility**. In security-sensitive domains (Elspeth's target market), credibility determines adoption.

The 40-55 hour investment isn't "documentation time"—it's **reputation building**.
`─────────────────────────────────────────────────`

---

## References

- **Methodology Inspiration**: `docs/refactoring/METHODOLOGY.md` (quality-first refactoring)
- **Security Philosophy**: ADR-001 (Design Philosophy - security > features)
- **Content Sources**: `docs/architecture/`, `docs/compliance/`, CLAUDE.md
- **Tech Stack Rationale**: README.md (this work package)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
