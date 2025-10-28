# Content Migration Matrix

**Document Purpose**: Comprehensive inventory of all content to migrate with priorities, strategies, and tracking.

---

## Legend

**Migration Strategies**:
- **COPY**: Use as-is with minimal changes (1.0x - 1.2x effort)
- **REFINE**: Improve organization/examples (1.5x - 2.0x effort)
- **DISTILL**: Extract essence from comprehensive docs (2.0x - 3.0x effort)
- **NEW**: Write from scratch (3.0x - 5.0x effort)

**Priorities**:
- 🔥 **CRITICAL**: Must-have for 1.0 release
- ⚡ **HIGH**: Important for 1.0, high user value
- ✅ **MEDIUM**: Nice-to-have for 1.0, can defer
- 📅 **LATER**: Post-1.0 content

**Status**:
- ⏸️ TODO
- 🟡 IN PROGRESS
- ✅ COMPLETE

---

## Phase 1: Core Content (12-16 hours)

### Getting Started (3-4 hours, NEW)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `getting-started/installation.md` | CLAUDE.md | DISTILL | 🔥 CRITICAL | 1h | Commands tested | ⏸️ TODO |
| `getting-started/quickstart.md` | None | NEW | 🔥 CRITICAL | 1.5h | <30min completion | ⏸️ TODO |
| `getting-started/first-experiment.md` | None | NEW | 🔥 CRITICAL | 1.5h | End-to-end works | ⏸️ TODO |

### Security Model (3-4 hours, DISTILL)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `user-guide/security-model.md` | ADR-002, ADR-002a, ADR-005 | DISTILL | 🔥 CRITICAL | 3-4h | Non-expert understands | ⏸️ TODO |

**Source Files**:
- `docs/architecture/decisions/002-security-architecture.md`
- `docs/architecture/decisions/002a-classified-dataframe-constructor.md`
- `docs/architecture/decisions/005-frozen-plugin-protection.md`

**Key Content to Extract**:
- Bell-LaPadula "no read up" rule (simplified explanation)
- Security level hierarchy (UNOFFICIAL → SECRET)
- Operating level vs. security level
- Pipeline-wide enforcement (minimum level)
- Common scenarios (4+ examples)
- Troubleshooting validation errors

**Diagrams to Create**:
- Bell-LaPadula visual ("no read up")
- Security level hierarchy
- Pipeline enforcement flow

---

### Plugin Catalogue (2-3 hours, REFINE)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `plugins/overview.md` | `docs/architecture/plugin-catalogue.md` | REFINE | ⚡ HIGH | 30min | Clear structure | ⏸️ TODO |
| `plugins/datasources.md` | `docs/architecture/plugin-catalogue.md` | REFINE | ⚡ HIGH | 45min | Every plugin has example | ⏸️ TODO |
| `plugins/transforms.md` | `docs/architecture/plugin-catalogue.md` | REFINE | ⚡ HIGH | 45min | Every plugin has example | ⏸️ TODO |
| `plugins/sinks.md` | `docs/architecture/plugin-catalogue.md` | REFINE | ⚡ HIGH | 45min | Every plugin has example | ⏸️ TODO |

**Reorganization**:
- FROM: Plugin type → all plugins of that type (implementation-focused)
- TO: Use case → recommended plugins (user-focused)

**Example Usage Patterns to Add**:
- Datasources: CSV local, CSV blob, when to use each
- Transforms: LLM chaining, middleware patterns
- Sinks: Multi-sink, signed bundles, visual analytics

---

### Configuration Guide (2-3 hours, DISTILL)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `user-guide/configuration.md` | `docs/architecture/configuration-security.md` | DISTILL | ⚡ HIGH | 2-3h | Troubleshooting complete | ⏸️ TODO |

**Source Files**:
- `docs/architecture/configuration-security.md`
- `CLAUDE.md` (configuration examples)

**Key Content to Extract**:
- Configuration file structure (YAML)
- Merge order: suite defaults → prompt packs → experiment
- Common patterns (single sink, multi-sink, baseline)
- Schema validation (`validate-schemas`)
- Troubleshooting (≥5 common errors)

**Configuration Examples to Test**:
- Single datasource + LLM + sink
- Multi-sink experiment
- Baseline comparison
- Middleware chaining

---

### Architecture Overview (2-3 hours, DISTILL)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `architecture/overview.md` | `docs/architecture/architecture-overview.md` | DISTILL | ⚡ HIGH | 2-3h | System diagram included | ⏸️ TODO |

**Source Files**:
- `docs/architecture/architecture-overview.md`
- `docs/architecture/component-diagram.md`

**Key Content to Extract**:
- High-level system design
- Core pipeline (sources → transforms → sinks)
- ExperimentSuiteRunner, ExperimentOrchestrator
- Artifact pipeline (sink chaining)
- Security enforcement points
- Plugin registry framework
- Configuration system
- Links to detailed ADRs

**Diagrams to Create**:
- High-level system architecture
- Pipeline flow diagram

---

## Phase 2: API Reference (8-12 hours)

### Docstring Quality Audit (3-4 hours)

| Module | Source | Priority | Effort | Quality Gate | Status |
|--------|--------|----------|--------|--------------|--------|
| `elspeth.core.base.plugin` | `src/elspeth/core/base/plugin.py` | ⚡ HIGH | 1h | All methods documented | ⏸️ TODO |
| `elspeth.core.security` | `src/elspeth/core/security/` | 🔥 CRITICAL | 1h | Examples added | ⏸️ TODO |
| `elspeth.core.pipeline` | `src/elspeth/core/pipeline/` | ⚡ HIGH | 1h | Chaining explained | ⏸️ TODO |
| `elspeth.core.registries` | `src/elspeth/core/registries/` | ⚡ HIGH | 1h | Registration examples | ⏸️ TODO |

**Audit Checklist (per module)**:
- [ ] Every public class has docstring
- [ ] Every public method has Args/Returns/Raises
- [ ] Google-style formatting
- [ ] Usage examples in class docstrings
- [ ] Cross-references to related classes

---

### API Reference Pages (2-3 hours)

| Destination | Modules Covered | Priority | Effort | Quality Gate | Status |
|-------------|-----------------|----------|--------|--------------|--------|
| `api-reference/core.md` | base.plugin, base.types | ⚡ HIGH | 45min | Auto-gen working | ⏸️ TODO |
| `api-reference/security.md` | security.classified_data | 🔥 CRITICAL | 45min | Examples included | ⏸️ TODO |
| `api-reference/pipeline.md` | pipeline.artifact_pipeline | ⚡ HIGH | 45min | Chaining docs | ⏸️ TODO |
| `api-reference/registries.md` | registries.base | ⚡ HIGH | 45min | Registration docs | ⏸️ TODO |

---

### Usage Examples (3-5 hours)

| API Area | Examples Needed | Priority | Effort | Quality Gate | Status |
|----------|-----------------|----------|--------|--------------|--------|
| BasePlugin | Implement custom plugin | ⚡ HIGH | 1h | Tested, works | ⏸️ TODO |
| SecureDataFrame | create_from_datasource, uplifting | 🔥 CRITICAL | 1-2h | Tested, works | ⏸️ TODO |
| Artifact Pipeline | Multi-sink chaining | ⚡ HIGH | 1h | Tested, works | ⏸️ TODO |
| BasePluginRegistry | Register/retrieve plugins | ⚡ HIGH | 1h | Tested, works | ⏸️ TODO |

---

## Phase 3: Polish Content (Deferred - See 05-QUALITY-GATES.md)

Phase 3 focuses on quality assurance, not content creation.

---

## Compliance Documentation (Copy Strategy)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `compliance/security-controls.md` | `docs/compliance/security-controls.md` | COPY | 🔥 CRITICAL | 30min | Formatting only | ⏸️ TODO |
| `compliance/audit-logging.md` | `docs/operations/logging.md` | REFINE | ⚡ HIGH | 45min | Audit focus | ⏸️ TODO |
| `compliance/sbom.md` | `docs/operations/artifacts.md` | DISTILL | ✅ MEDIUM | 30min | SBOM section | ⏸️ TODO |

---

## Operations Documentation (Refine Strategy)

| Destination | Source | Strategy | Priority | Effort | Quality Gate | Status |
|-------------|--------|----------|----------|--------|--------------|--------|
| `operations/deployment.md` | CLAUDE.md, `docs/operations/` | DISTILL | ✅ MEDIUM | 1h | Commands tested | 📅 LATER |
| `operations/monitoring.md` | `docs/operations/healthcheck.md` | REFINE | ✅ MEDIUM | 45min | Examples included | 📅 LATER |
| `operations/troubleshooting.md` | Various | NEW | ⚡ HIGH | 1-2h | ≥10 scenarios | 📅 LATER |

---

## Deferred Content (Post-1.0)

### Additional User Guides

| Topic | Source | Strategy | Effort | Notes |
|-------|--------|----------|--------|-------|
| Advanced Configuration | None | NEW | 2-3h | Prompt packs, advanced patterns |
| Experiment Design | None | NEW | 2-3h | Best practices, statistical rigor |
| Performance Tuning | None | NEW | 1-2h | Optimization tips |

### Advanced Topics

| Topic | Source | Strategy | Effort | Notes |
|-------|--------|----------|--------|-------|
| Extending Elspeth | None | NEW | 3-4h | Custom plugins, middleware |
| Azure ML Integration | None | NEW | 2-3h | Azure-specific workflows |
| Security Hardening | ADR-002 threat model | DISTILL | 2h | Deployment security |

### Developer Guides

| Topic | Source | Strategy | Effort | Notes |
|-------|--------|----------|--------|-------|
| Contributing | None | NEW | 1-2h | PR process, code standards |
| Testing Guide | `docs/development/testing-overview.md` | REFINE | 1-2h | How to write tests |
| Refactoring Methodology | `docs/refactoring/METHODOLOGY.md` | COPY | 30min | Link to developer docs |

---

## Content Migration Checklist (Use for Each Item)

**Before Starting**:
- [ ] Read source material thoroughly
- [ ] Identify target audience (new user, active user, contributor, compliance)
- [ ] Determine appropriate depth (Level 1, 2, or 3 per progressive disclosure)

**During Writing**:
- [ ] Follow appropriate strategy (COPY, REFINE, DISTILL, NEW)
- [ ] Write for target audience (avoid jargon for new users, add detail for contributors)
- [ ] Include working code examples (test before documenting)
- [ ] Add cross-references to related pages
- [ ] Check readability (Flesch-Kincaid ≥60)

**After Writing**:
- [ ] Test all code examples
- [ ] Validate all links (internal and external)
- [ ] Run spell check, grammar check
- [ ] Technical review by stakeholder
- [ ] Mark status as COMPLETE

---

## Progress Tracking

### Phase 1 Progress

| Content Area | Files | Status | Completion % |
|--------------|-------|--------|--------------|
| Getting Started | 0/3 | ⏸️ TODO | 0% |
| Security Model | 0/1 | ⏸️ TODO | 0% |
| Plugin Catalogue | 0/4 | ⏸️ TODO | 0% |
| Configuration | 0/1 | ⏸️ TODO | 0% |
| Architecture | 0/1 | ⏸️ TODO | 0% |
| **TOTAL** | **0/10** | **⏸️ TODO** | **0%** |

### Phase 2 Progress

| Content Area | Tasks | Status | Completion % |
|--------------|-------|--------|--------------|
| Docstring Audit | 0/4 | ⏸️ TODO | 0% |
| API Pages | 0/4 | ⏸️ TODO | 0% |
| Usage Examples | 0/4 | ⏸️ TODO | 0% |
| **TOTAL** | **0/12** | **⏸️ TODO** | **0%** |

---

## Estimated Total Effort

| Phase | Content Items | Total Effort |
|-------|---------------|--------------|
| Phase 1 | 10 files | 12-16 hours |
| Phase 2 | 12 tasks | 8-12 hours |
| Compliance | 3 files | 2 hours |
| **Pre-Deployment Total** | **25 items** | **22-30 hours** |

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
