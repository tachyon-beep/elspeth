# Registry Consolidation Refactoring

**Comprehensive plan to consolidate duplicate registry code in Elspeth**

---

## 📚 Documentation Index

This directory contains all documentation for the registry consolidation refactoring initiative.

### Core Documents

1. **[REGISTRY_CONSOLIDATION_PLAN.md](REGISTRY_CONSOLIDATION_PLAN.md)** (MAIN DOCUMENT)
   - **Purpose:** Complete technical specification and implementation plan
   - **Audience:** Development team, technical leads
   - **Contents:**
     - Executive summary
     - 4-phase implementation plan (20+ days)
     - Detailed technical designs for all components
     - Test strategies and success criteria
     - Risk assessment and mitigation
     - Rollback procedures
   - **When to use:** Primary reference for understanding scope, design, and execution

2. **[MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md)** (DAILY REFERENCE)
   - **Purpose:** Day-by-day task list with specific action items
   - **Audience:** Engineers implementing the refactoring
   - **Contents:**
     - Pre-flight checklist
     - Daily task breakdowns for 20 days
     - Testing requirements per phase
     - Emergency rollback procedures
     - Quick command reference
     - Metrics tracking templates
   - **When to use:** Daily standup planning, task completion tracking

3. **[ARCHITECTURE_COMPARISON.md](ARCHITECTURE_COMPARISON.md)** (VISUAL REFERENCE)
   - **Purpose:** Before/after architecture visualization
   - **Audience:** Stakeholders, code reviewers, team members
   - **Contents:**
     - Current registry architecture diagrams
     - Proposed unified framework diagrams
     - Code duplication maps
     - Side-by-side code examples
     - Metrics comparison table
     - Benefits summary
   - **When to use:** Architecture reviews, stakeholder presentations, onboarding

---

## 🎯 Quick Start Guide

### For Team Leads
1. Read: [REGISTRY_CONSOLIDATION_PLAN.md](REGISTRY_CONSOLIDATION_PLAN.md) (Executive Summary + Phase summaries)
2. Review: [ARCHITECTURE_COMPARISON.md](ARCHITECTURE_COMPARISON.md) (Benefits + Risk Assessment)
3. Approve: Sign off on Phase 1 to begin implementation

### For Developers
1. Read: [REGISTRY_CONSOLIDATION_PLAN.md](REGISTRY_CONSOLIDATION_PLAN.md) (Full document)
2. Use: [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) (Daily reference)
3. Reference: [ARCHITECTURE_COMPARISON.md](ARCHITECTURE_COMPARISON.md) (When confused about design)

### For Stakeholders
1. Read: [ARCHITECTURE_COMPARISON.md](ARCHITECTURE_COMPARISON.md) (Full document)
2. Skim: [REGISTRY_CONSOLIDATION_PLAN.md](REGISTRY_CONSOLIDATION_PLAN.md) (Executive Summary + Timeline)
3. Monitor: Metrics tracking section in checklist

---

## 📊 Project Overview

### The Problem
- **5 separate registry implementations** with duplicate code
- **2,087 total lines** of registry code
- **~900 lines of duplication** (43% duplicate)
- Confusing folder structure (`datasources/` vs `plugins/datasources/`)
- Difficult to add new plugin types
- Inconsistent error handling

### The Solution
- **Unified base registry framework** with shared utilities
- **1,270 total lines** after refactoring
- **~0 lines of duplication** (0% duplicate)
- Clear folder structure (`adapters/` vs `plugins/datasources/`)
- Easy to add new plugin types (extend base class)
- Consistent error messages and behavior

### The Impact
- **-817 lines of code** (-39% reduction)
- **Easier maintenance** (single source of truth)
- **Faster development** (reusable patterns)
- **Better testing** (centralized test coverage)
- **Clearer architecture** (easier onboarding)

---

## 🗓️ Timeline

| Phase | Duration | Deliverable | Status |
|-------|----------|-------------|--------|
| **Phase 1: Foundation** | Days 1-5 | Base registry framework | ⬜ Not Started |
| **Phase 2: Migration** | Days 6-15 | All registries migrated | ⬜ Not Started |
| **Phase 3: Cleanup** | Days 16-20 | Code cleaned, docs updated | ⬜ Not Started |
| **Phase 4: Validation** | Days 21+ | Release ready | ⬜ Not Started |

**Total Estimated Time:** 4 weeks (20+ working days)

---

## 🎯 Success Metrics

### Code Quality
- [ ] **Reduce LOC by 800+** lines
- [ ] **Eliminate 43% duplication** (current) → 0%
- [ ] **Maintain test coverage** at >85%
- [ ] **No performance regression** (±5% tolerance)

### Development Experience
- [ ] **Add new plugin type in <2 hours** (vs current ~4 hours)
- [ ] **Reduce onboarding time** for new developers
- [ ] **Consistent error messages** across all plugin types
- [ ] **Clear architecture documentation**

### Project Goals
- [ ] **100% backward compatibility** (no breaking changes)
- [ ] **All existing tests pass** unchanged
- [ ] **Sample suite runs** without modification
- [ ] **Zero security regressions**

---

## 🚦 Current Status

**Phase:** Planning Complete ✅
**Next Step:** Await approval to begin Phase 1
**Blockers:** None
**Risks:** Medium (manageable with testing)

### Approval Checklist
- [ ] Technical Lead Review
- [ ] Security Team Review
- [ ] QA Testing Plan Approved
- [ ] Timeline Approved
- [ ] Budget Approved (if applicable)

---

## 📋 Implementation Phases

### Phase 1: Foundation (Days 1-5)
**Goal:** Create base registry framework without breaking anything

**Key Deliverables:**
- `src/elspeth/core/registry/base.py` - BasePluginFactory, BasePluginRegistry
- `src/elspeth/core/registry/context_utils.py` - Shared context logic
- `src/elspeth/core/registry/schemas.py` - Common schema definitions
- Complete test suite (>90% coverage)

**Success Criteria:**
- ✅ All new tests pass
- ✅ All existing tests still pass (100%)
- ✅ No regressions
- ✅ Code reviews approved

### Phase 2: Migration (Days 6-15)
**Goal:** Migrate all 5 registries to use base framework

**Migration Order:**
1. Utilities Registry (simplest)
2. Controls Registry
3. LLM Middleware Registry
4. Experiment Plugins Registry (most complex)
5. Main Registry (most critical)

**Success Criteria:**
- ✅ All 5 registries migrated
- ✅ 100% existing tests pass
- ✅ No behavior changes
- ✅ Performance within ±5%

### Phase 3: Cleanup (Days 16-20)
**Goal:** Remove duplication and improve clarity

**Key Tasks:**
- Remove old factory classes
- Rename `datasources/` → `adapters/`
- Update all documentation
- Validate performance

**Success Criteria:**
- ✅ ~900 lines removed
- ✅ Folder structure clearer
- ✅ Documentation complete
- ✅ Performance validated

### Phase 4: Validation (Days 21+)
**Goal:** Ensure production-ready quality

**Key Tasks:**
- Integration testing
- Security review
- Backward compatibility verification
- Release preparation

**Success Criteria:**
- ✅ Sample suite runs perfectly
- ✅ Security review passed
- ✅ No breaking changes
- ✅ Release tagged

---

## 🛠️ Technical Highlights

### Base Registry Framework

The core abstraction that eliminates duplication:

```python
from elspeth.core.registries.base import BasePluginRegistry

# Create a type-safe registry for any plugin type
_my_registry = BasePluginRegistry[MyPluginType]("my_plugin_type")

# Register plugins
_my_registry.register("plugin_name", factory_function, schema=validation_schema)

# Create instances with full context handling
plugin = _my_registry.create(
    name="plugin_name",
    options={...},
    parent_context=parent_context,
)
```

### Context Utilities

Consolidates 30-40 line pattern into single function:

```python
from elspeth.core.registries.context_utils import extract_security_levels, create_plugin_context

# Extract and normalize security levels with provenance tracking
security_level, determinism_level, sources = extract_security_levels(
    definition, options, plugin_type="my_type", plugin_name="my_plugin"
)

# Create consistent plugin context
context = create_plugin_context(
    plugin_name, plugin_kind, security_level, determinism_level, sources
)
```

### Schema Builders

Reusable schema composition:

```python
from elspeth.core.registries.schemas import with_security_properties, with_error_handling

schema = {
    "type": "object",
    "properties": {"foo": {"type": "string"}},
}

# Add standard properties
schema = with_security_properties(schema, require_security=True)
schema = with_error_handling(schema)
```

---

## 🔒 Security Considerations

### Context Propagation
- ✅ Security levels flow correctly through all plugin types
- ✅ Provenance tracking maintains audit trail
- ✅ No privilege escalation possible
- ✅ Artifact pipeline security enforced

### Testing
- ✅ Comprehensive context propagation tests
- ✅ Security level validation tests
- ✅ Clearance compatibility tests
- ✅ Security review before each phase gate

---

## 📈 Benefits

### For Developers
- **Faster plugin development** - Extend base class instead of copying patterns
- **Consistent APIs** - All registries work the same way
- **Better error messages** - Standardized error handling
- **Easier debugging** - Single source of truth
- **Clear patterns** - One pattern to learn, not five

### For Maintainers
- **Less code to maintain** - 39% reduction in LOC
- **Easier refactoring** - Change once, affects all registries
- **Better test coverage** - Centralized tests
- **Clearer architecture** - Documentation reflects reality

### For Users
- **No breaking changes** - Transparent refactoring
- **Better performance** - Optimized shared code
- **More reliable** - Better tested code
- **Easier to extend** - Custom plugins easier to add

---

## ⚠️ Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking changes | Medium | High | Extensive testing, backward compat layer |
| Performance regression | Low | Medium | Benchmarking at each phase |
| Security issues | Low | High | Security review, context tests |
| Timeline overrun | Medium | Low | Buffer time, incremental approach |

---

## 🔄 Rollback Plan

### Phase-by-Phase Rollback
Each phase is committed separately, allowing surgical rollback:

```bash
# Rollback specific phase
git revert <phase-start-commit>..<phase-end-commit>
```

### Complete Rollback
```bash
# Revert entire refactoring
git revert <refactor-start>..<refactor-end>
git push origin main
```

### Risk Mitigation
- ✅ Commit each registry migration separately
- ✅ Tag each phase completion
- ✅ Maintain backup branches
- ✅ Extensive testing before merging

---

## 📞 Contacts & Resources

### Team
- **Technical Lead:** TBD
- **Security Reviewer:** TBD
- **QA Lead:** TBD

### Resources
- **Slack Channel:** #elspeth-refactoring (example)
- **Project Board:** TBD
- **Documentation:** This directory
- **Codebase:** [src/elspeth/core/](../../src/elspeth/core/)

### Meetings
- **Daily Standup:** TBD (during active development)
- **Weekly Review:** TBD
- **Phase Gates:** As needed

---

## 🎓 Additional Reading

### Elspeth Architecture
- [CLAUDE.md](../../CLAUDE.md) - Project instructions for AI assistants
- [docs/architecture/README.md](../architecture/README.md) - Architecture overview
- [docs/architecture/plugin-catalogue.md](../architecture/plugin-catalogue.md) - Current plugin docs

### Best Practices
- Follow existing code style (PEP 8)
- Write tests first (TDD encouraged)
- Commit frequently with clear messages
- Request code review for each phase

---

## 📝 Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-10-14 | Initial plan created | Architecture Review |
| | | |
| | | |

---

## ✅ Next Actions

### Immediate (This Week)
1. [ ] Review all three documents
2. [ ] Schedule kickoff meeting
3. [ ] Assign roles and responsibilities
4. [ ] Get Phase 1 approval
5. [ ] Set up monitoring/tracking

### Short-term (Week 1)
1. [ ] Begin Phase 1 implementation
2. [ ] Daily standups
3. [ ] Phase 1 completion and review

### Long-term (Weeks 2-4)
1. [ ] Complete Phase 2 migration
2. [ ] Complete Phase 3 cleanup
3. [ ] Complete Phase 4 validation
4. [ ] Release!

---

**Document Version:** 1.0
**Status:** Ready for Review
**Last Updated:** 2025-10-14
**Next Review:** After Phase 1 completion
