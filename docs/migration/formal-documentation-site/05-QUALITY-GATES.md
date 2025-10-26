# Quality Gates - Acceptance Criteria

**Document Purpose**: Define explicit quality criteria for each phase. Content isn't "done" until it meets these gates.

**Core Principle**: Quality is the primary factor. These gates ensure polished, professional documentation.

---

## Phase 0: Bootstrap

### Exit Criteria

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Local preview works | Run `mkdocs serve` | No errors, site loads at http://127.0.0.1:8000 |
| Theme customized | Visual inspection | Not default blue, uses indigo/custom colors |
| Navigation structure defined | Check mkdocs.yml nav section | All sections present (Getting Started, User Guide, Plugins, Architecture, Compliance, Operations, API) |
| Search enabled | Type query in search box | Search box visible, returns results (even if "no matches") |
| Dark mode toggle | Click moon/sun icon | Theme switches between light and dark |
| Mobile responsive | Resize browser to 375px width | Layout adapts, no horizontal scroll |
| No build warnings | Run `mkdocs build --strict` | Zero warnings or errors |

### Deliverables Checklist

- [ ] `site-docs/` folder structure created
- [ ] `site-docs/mkdocs.yml` configuration complete
- [ ] `site-docs/docs/index.md` landing page written
- [ ] `site-docs/requirements.txt` created
- [ ] `.gitignore` updated (ignore `site/`)
- [ ] `Makefile` updated (add `docs-serve`, `docs-build`, `docs-deploy`)
- [ ] Phase 0 changes committed to feature branch

---

## Phase 1: Core Content

### Quality Gates Per Content Area

#### Getting Started (All Files)

**Quality Gate: New Contributor Test**

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Quickstart completion time | Time new contributor | ≤30 minutes from "I'm new" to "experiment ran" |
| Installation commands work | Test on fresh VM/container | All commands succeed, no errors |
| First experiment runs | Follow guide step-by-step | Experiment completes, outputs visible |
| Code examples tested | Run every command | All examples work, outputs match docs |
| Cross-references work | Click every link | No 404s, links go to correct pages |

**Specific Tests**:
- [ ] Installation: Can someone with Python 3.12 install Elspeth in <15 minutes?
- [ ] Quickstart: Can someone run their first experiment in 5-10 minutes?
- [ ] First Experiment: Can someone create a config from scratch in 15-20 minutes?

---

#### Security Model

**Quality Gate: Non-Expert Understanding Test**

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Bell-LaPadula comprehension | Ask non-expert to explain "no read up" | Can explain in their own words without jargon |
| Security level hierarchy | Ask to list levels in order | Correct: UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET |
| Operating vs. security level | Ask to explain difference | Can distinguish between pipeline level and plugin level |
| Scenario understanding | Give scenario, ask if it passes/fails | 4/4 correct answers (e.g., UNOFFICIAL datasource + SECRET sink = fail) |
| Troubleshooting | Give security validation error, ask how to fix | Can identify root cause and solution |

**Specific Tests**:
- [ ] Visual diagrams included (≥2: Bell-LaPadula rule, security hierarchy)
- [ ] ≥4 concrete scenarios with explanations (pass/fail examples)
- [ ] Troubleshooting section with ≥3 common errors and fixes
- [ ] Links to full ADRs for deep dives

---

#### Plugin Catalogue

**Quality Gate: Every Plugin Has Example**

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Usage example per plugin | Count examples | Every datasource, transform, sink has ≥1 config example |
| Examples tested | Run configs | All examples work without modification |
| When to use guidance | Read plugin descriptions | Clear use case guidance (e.g., "Use CSV local for small files, CSV blob for large datasets") |
| Organization clarity | Unfamiliar user test | Can find appropriate plugin for their use case in <2 minutes |

**Specific Tests**:
- [ ] Overview page explains plugin architecture
- [ ] Every plugin type has dedicated page (datasources, transforms, sinks)
- [ ] ≥1 working configuration example per plugin
- [ ] Links to API reference for implementation details

---

#### Configuration Guide

**Quality Gate: Multi-Sink Configuration Without Help**

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Merge order understanding | Ask user to explain priority | Can explain: suite defaults → prompt packs → experiment overrides |
| Configuration examples | Test provided configs | ≥3 complete examples work (single sink, multi-sink, baseline) |
| Troubleshooting completeness | Count common errors | ≥5 errors documented with solutions |
| Schema validation | Explain when to use `validate-schemas` | Can explain purpose and when to run |

**Specific Tests**:
- [ ] Configuration file structure explained (YAML sections)
- [ ] Merge order visualized (diagram or clear explanation)
- [ ] ≥3 complete configuration examples (tested, working)
- [ ] Troubleshooting section (≥5 common errors: validation errors, security errors, merge conflicts)

---

#### Architecture Overview

**Quality Gate: New Contributor Understanding**

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| System flow comprehension | Ask contributor to explain pipeline | Can explain: sources → transforms → sinks with security enforcement |
| Component understanding | Ask about ExperimentSuiteRunner vs. ExperimentOrchestrator | Can distinguish suite-level vs. experiment-level orchestration |
| Diagram clarity | Show diagram to unfamiliar person | Can explain data flow without additional context |

**Specific Tests**:
- [ ] High-level system architecture diagram
- [ ] Pipeline flow diagram (sources → transforms → sinks)
- [ ] Security enforcement points explained
- [ ] Links to detailed ADRs for full specifications

---

### Phase 1 Overall Exit Criteria

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| All 5 core areas complete | Count completed files | 10/10 files written |
| All code examples tested | Run every snippet | 100% work without errors |
| All cross-references validated | Link checker | 0 broken internal links |
| Readability acceptable | Flesch-Kincaid readability test | ≥60 (college graduate level) |
| Technical review passed | Stakeholder review | Stakeholder approves technical accuracy |
| Stakeholder approval | Stakeholder judgment | "Ready to show users" thumbs-up |

---

## Phase 2: API Reference

### Docstring Quality Gates

**Per Module Quality Checklist**:

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Every public class has docstring | Code inspection | 100% coverage |
| Docstrings use Google style | Format check | All follow Args/Returns/Raises pattern |
| Every public method documented | Code inspection | All public methods have Args/Returns |
| Usage examples in class docstrings | Count examples | ≥50% of classes have usage examples |
| Cross-references correct | Check ::: references | All module paths resolve correctly |

**Specific Modules**:
- [ ] `elspeth.core.base.plugin` - All methods documented
- [ ] `elspeth.core.security.classified_data` - SecureDataFrame API complete
- [ ] `elspeth.core.pipeline.artifact_pipeline` - Chaining behavior explained
- [ ] `elspeth.core.registries.base` - Registration patterns documented

---

### mkdocstrings Integration

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Auto-generation works | Run `mkdocs build` | No mkdocstrings warnings or errors |
| API pages render correctly | Visual inspection | Classes, methods, signatures display correctly |
| Source links work | Click "view source" links | Links point to correct files on GitHub |
| Search includes API | Search for class name | API reference pages appear in results |

**Specific Tests**:
- [ ] mkdocstrings plugin configured in mkdocs.yml
- [ ] Python handler points to `../src` correctly
- [ ] ≥4 API reference pages created (core, security, pipeline, registries)
- [ ] Navigation from user guide to API seamless

---

### Usage Examples

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Examples tested | Run code snippets | 100% of examples work |
| Examples realistic | Code review | Examples demonstrate real use cases (not toy examples) |
| Examples complete | Inspection | No "..." placeholders, full working code |
| Coverage adequate | Count examples | ≥10 working examples across all API pages |

**Specific Examples Required**:
- [ ] BasePlugin: Implement custom plugin (complete example)
- [ ] SecureDataFrame: create_from_datasource + uplifting (2 examples)
- [ ] Artifact Pipeline: Multi-sink chaining (1 example)
- [ ] BasePluginRegistry: Register and retrieve plugins (1 example)

---

### Phase 2 Overall Exit Criteria

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| API coverage | Count documented modules | ≥80% of core modules documented |
| Docstring quality | Inspection | Every public class/method has Google-style docstring |
| Examples sufficient | Count + quality check | ≥10 working examples, ≥50% of classes have examples |
| No mkdocstrings warnings | Run `mkdocs build --strict` | Zero warnings |
| Navigation seamless | User test | Can navigate from user guide to API reference and back |

---

## Phase 3: Polish

### Navigation UX Testing

**Test Scenarios**:

1. **Scenario: New User Installation**
   - **Task**: "I'm a new user, can I install and run Elspeth in 30 minutes?"
   - **Pass Criteria**: User completes without asking questions

2. **Scenario: Troubleshooting**
   - **Task**: "I'm getting a security validation error, can I troubleshoot?"
   - **Pass Criteria**: User finds troubleshooting section, identifies fix

3. **Scenario: API Lookup**
   - **Task**: "I want to add a new sink, where do I find the API docs?"
   - **Pass Criteria**: User navigates from plugin catalogue to API reference in <2 minutes

**Acceptance**:
- [ ] Unfamiliar user completes 3/3 scenarios without help
- [ ] Navigation improvements implemented based on feedback
- [ ] "Related pages" links added where appropriate

---

### Visual Diagrams

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Diagrams present | Count | ≥4 diagrams (security model, architecture, pipeline flow) |
| Diagrams render correctly | Visual inspection | Display correctly in light AND dark mode |
| Diagrams clear | Unfamiliar person test | Can explain diagram without reading surrounding text |
| Diagrams editable | Check source files | Source files (draw.io, mermaid, etc.) available for future updates |

**Required Diagrams**:
- [ ] Bell-LaPadula "no read up" visual
- [ ] Security level hierarchy (UNOFFICIAL → SECRET)
- [ ] High-level system architecture
- [ ] Pipeline flow (sources → transforms → sinks)

---

### Search Optimization

**Test Queries** (Common User Searches):

| Query | Expected Top Result | Pass/Fail |
|-------|---------------------|-----------|
| "install" | Getting Started > Installation | ⏸️ |
| "security level" | User Guide > Security Model | ⏸️ |
| "datasource" | Plugins > Datasources | ⏸️ |
| "validation error" | User Guide > Configuration (troubleshooting) | ⏸️ |
| "plugin" | Plugins > Overview | ⏸️ |
| "configuration" | User Guide > Configuration | ⏸️ |
| "API reference" | API Reference > Core | ⏸️ |
| "Bell-LaPadula" | User Guide > Security Model | ⏸️ |
| "sink" | Plugins > Sinks | ⏸️ |
| "quickstart" | Getting Started > Quickstart | ⏸️ |

**Acceptance**: ≥9/10 queries return relevant top result

---

### Quality Assurance

**Link Checking**:
- [ ] Run `mkdocs build --strict` (no warnings)
- [ ] Manual check: Click every internal link (no 404s)
- [ ] External link validation (all external URLs load)

**Code Example Testing**:
- [ ] Every code snippet tested (run and verify output)
- [ ] Outputs match documentation (if output shown)
- [ ] No pseudocode or "..." placeholders

**Proofreading**:
- [ ] Spell check all content (no typos)
- [ ] Grammar check (tools: Grammarly, LanguageTool)
- [ ] Consistency check:
  - [ ] Terminology (e.g., "datasource" vs. "data source")
  - [ ] Capitalization (e.g., "Bell-LaPadula" vs. "bell-lapadula")
  - [ ] Code style (consistent indentation, quotes)

**Stakeholder Review**:
- [ ] Walk through site with stakeholder
- [ ] Collect feedback (document in review notes)
- [ ] Implement feedback
- [ ] Get sign-off for 1.0 release

---

### Phase 3 Overall Exit Criteria

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Navigation tested | Unfamiliar user test | 3/3 scenarios passed |
| All diagrams rendering | Visual inspection | 4/4 diagrams render in light + dark mode |
| Zero broken links | Link checker + manual | 0 broken internal or external links |
| Search optimized | 10 query test | ≥9/10 return relevant results |
| Mobile tested | Actual device test | Site usable on 375px width screen |
| All examples verified | Code execution | 100% of examples work |
| Content proofread | Spell + grammar check | Zero typos, grammar errors |
| Stakeholder approval | Sign-off | Stakeholder approves for 1.0 release |

---

## Phase 4: Deployment

### Hosting Setup

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Site deployed | Visit deployment URL | Site loads, no errors |
| HTTPS enabled | Check URL scheme | https:// (if public) |
| Custom domain configured | Visit custom domain | Resolves correctly (if applicable) |
| Matches local preview | Visual comparison | Deployed site identical to local |

---

### CI/CD Integration

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Workflow file created | Check `.github/workflows/docs.yml` | File exists, correctly configured |
| Auto-deploy works | Merge PR to main | Docs auto-deploy within 5 minutes |
| Build validation on PRs | Open docs PR | CI runs `mkdocs build --strict`, fails if warnings |
| Deployment success notification | Check GitHub Actions | Green checkmark, no errors |

**CI/CD Test**:
- [ ] Create test PR (minor doc change)
- [ ] Verify CI runs build check
- [ ] Merge PR
- [ ] Verify auto-deployment completes
- [ ] Verify deployed site updated

---

### Versioning Setup

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| `mike` configured | Check requirements, mkdocs.yml | `mike` installed, provider set in mkdocs.yml |
| Version dropdown visible | Visual inspection | Version selector in header/footer |
| Switching versions works | Click version dropdown, select version | Content changes to correct version |
| Latest alias works | Visit /latest/ | Redirects to most recent version |

**Versioning Test**:
- [ ] Deploy version 0.1.0-dev
- [ ] Deploy version 1.0.0 (when ready)
- [ ] Switch between versions
- [ ] Verify content differences

---

### Phase 4 Overall Exit Criteria

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Site deployed | Visit URL | Accessible, no errors |
| CI/CD working | Merge test PR | Auto-deploys within 5 minutes |
| Deployment speed | Time deployment | <5 minutes from merge to live |
| Versioning configured | Version selector test | Version dropdown works, switching successful |
| HTTPS enabled | Check connection | Secure (if public) |
| Deployment documented | Read docs | Process documented in README or operations guide |

---

## Readability Standards

### Flesch-Kincaid Readability

**Target**: ≥60 (college graduate level)

**Test Method**: Use online tools or Python libraries

```python
import textstat

text = """Your documentation content here"""
score = textstat.flesch_reading_ease(text)
print(f"Flesch Reading Ease: {score}")  # Target: ≥60
```

**Interpretation**:
- 90-100: Very easy (5th grade)
- 80-90: Easy (6th grade)
- 70-80: Fairly easy (7th grade)
- **60-70: Standard (8th-9th grade)** ← TARGET
- 50-60: Fairly difficult (10th-12th grade)
- 30-50: Difficult (college)
- 0-30: Very difficult (college graduate)

**Acceptance**: Core content (Getting Started, User Guide) should score ≥60. API Reference can score lower (technical content).

---

## Accessibility Standards

### WCAG 2.1 Compliance

Material theme provides good defaults, but verify:

| Criterion | Test Method | Acceptance |
|-----------|-------------|------------|
| Color contrast | Use contrast checker tool | ≥4.5:1 for normal text, ≥3:1 for large text |
| Keyboard navigation | Tab through site | All interactive elements accessible |
| Alt text on images | Inspect image tags | All diagrams have descriptive alt text |
| Heading hierarchy | Check HTML structure | Logical heading order (h1 → h2 → h3, no skips) |

---

## Performance Standards

### Build Performance

| Metric | Target | Test Method |
|--------|--------|-------------|
| Build time | <30 seconds | `time mkdocs build` |
| Incremental build | <5 seconds | `time mkdocs build` (after first build) |
| Preview startup | <3 seconds | Time to "Serving on..." message |

### Runtime Performance

| Metric | Target | Test Method |
|--------|--------|-------------|
| Page load time | <2 seconds | Browser dev tools Network tab |
| Search response | <1 second | Type query, measure time to results |
| Large page scroll | Smooth | Test with architecture diagram page |

---

## Summary: Quality Gate Hierarchy

**Phase 0**: Foundation
- Local preview works, theme customized, navigation defined

**Phase 1**: Content Quality
- User-tested (new contributor, non-expert)
- All examples work
- Stakeholder approval

**Phase 2**: API Completeness
- ≥80% coverage
- Every public class documented
- ≥10 working examples

**Phase 3**: User Experience
- Navigation tested
- Zero broken links
- Search optimized
- Stakeholder sign-off for 1.0

**Phase 4**: Production Readiness
- Deployed and accessible
- CI/CD auto-deploys
- Versioning configured

---

`★ Insight ─────────────────────────────────────`
**Quality Gates as Forcing Functions**:

These gates aren't bureaucratic checkboxes—they're **forcing functions** that prevent "good enough" from shipping. By defining explicit criteria BEFORE starting work, we eliminate the temptation to cut corners when tired or behind schedule.

This mirrors Elspeth's **fail-fast security validation**: We'd rather ABORT than ship insecure code. Here, we'd rather BLOCK than ship mediocre docs.

The methodology works because **quality is measurable** (zero broken links, <30min quickstart completion, stakeholder approval). No subjective "it's probably fine."
`─────────────────────────────────────────────────`

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
