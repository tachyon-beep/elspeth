# Data Flow Migration Project

**Status**: Design Complete - Risk Reduction Phase
**Target Completion**: 20-29 total hours (8-12 risk reduction + 12-17 migration)

---

## Project Overview

This project restructures Elspeth from an **LLM-centric experiment runner** to a **general-purpose data flow orchestrator**.

**Core Insight**:
> "The core feature is pumping data between nodes. LLM is just one of those nodes."

**Key Changes**:
- Orchestrators define **topology** (how data flows) - the engine
- Nodes define **transformations** (what happens at vertices) - the components
- LLM moves from special domain to `plugins/nodes/transforms/llm/` - just another transform
- Explicit configuration required everywhere (no silent defaults)
- Single configuration snapshot per run (attributability)
- Registry consolidation: 18 files → 7 files (61% reduction)

---

## Project Documents

### 1. Read First

**[`ARCHITECTURE_EVOLUTION.md`](ARCHITECTURE_EVOLUTION.md)** - START HERE
- Traces architectural journey through 4 stages
- Documents key breakthrough: engine vs components separation
- Shows how LLM went from special to just another node
- Includes car analogy (engine, wheels, steering, fuel tank)

### 2. Target Architecture

**[`PLUGIN_SYSTEM_DATA_FLOW.md`](PLUGIN_SYSTEM_DATA_FLOW.md)** - Target Design
- Complete specification of data flow model
- Orchestrators = engines (topology definition)
- Nodes = components (transformation logic)
- Security requirement: explicit configuration only
- Final structure and protocols

### 3. Implementation Plan

**[`MIGRATION_TO_DATA_FLOW.md`](MIGRATION_TO_DATA_FLOW.md)** - How to Execute
- 5-phase migration guide (12-17 hours)
- Detailed step-by-step instructions
- Backward compatibility approach
- Verification checklist
- Rollback procedures

### 4. Risk Reduction

**[`RISK_REDUCTION_PLAN.md`](RISK_REDUCTION_PLAN.md)** - ⚠️ READ BEFORE STARTING
- 6 critical risks identified
- Risk mitigation activities (8-12 hours)
- Must complete BEFORE migration starts
- Testing strategy
- Success criteria gate

### 5. Configuration Design

**[`CONFIGURATION_ATTRIBUTABILITY.md`](CONFIGURATION_ATTRIBUTABILITY.md)** - Config Snapshot
- Single `ResolvedConfiguration` per run
- Provenance tracking
- Reproducibility support
- Compliance requirements

### 6. Historical Analysis

**[`PLUGIN_SYSTEM_ANALYSIS.md`](PLUGIN_SYSTEM_ANALYSIS.md)** - Initial Analysis
- Identified organizational debt
- 18 registries documented
- Proposed functional grouping

**[`PLUGIN_SYSTEM_REVISED.md`](PLUGIN_SYSTEM_REVISED.md)** - Intermediate Design
- Orchestration-first thinking
- Superseded by data flow model

---

## Project Status

### ✅ Complete

- [x] Architectural design
- [x] Target architecture specification
- [x] Migration guide created
- [x] Risk reduction plan created
- [x] All design documents written
- [x] Documentation organized

### 🔄 Current Phase: Risk Reduction (Week 1)

**Before migration can start**, complete these activities:

1. **Silent Default Audit** (2-3 hours) - CRITICAL
   - Find all silent defaults in codebase
   - Categorize by severity (CRITICAL, HIGH, MEDIUM, LOW)
   - Create enforcement tests
   - Document and remove P0/P1 defaults

2. **Test Coverage Audit** (2-3 hours) - HIGH
   - Generate coverage report
   - Identify gaps in critical paths
   - Create characterization tests for all 18 registries
   - Ensure all 545 tests pass

3. **Import Chain Mapping** (2-3 hours) - HIGH
   - Map all registry imports
   - Identify external API surface
   - Design backward compatibility shims

4. **Performance Baseline** (1-2 hours) - MEDIUM
   - Run performance tests
   - Profile critical paths
   - Document acceptable thresholds

5. **Configuration Audit** (1-2 hours) - MEDIUM
   - Inventory all configs
   - Test parsing
   - Design compatibility layer

**Total**: 8-12 hours

### ⏸️ Blocked: Migration (Week 2)

Migration is **BLOCKED** until all risk reduction activities complete successfully.

**Gates**:
- [ ] Silent default audit complete (zero P0/P1 defaults)
- [ ] Test coverage >85%, all tests passing
- [ ] Import chain map complete
- [ ] Backward compatibility design approved
- [ ] Performance baseline established
- [ ] Configuration compatibility layer designed

**Only proceed when all gates pass.**

---

## Architecture Comparison

| Aspect | Before | After |
|--------|--------|-------|
| **Mental Model** | "LLM experiment runner" | "Data flow orchestrator" |
| **LLM Status** | Special domain `plugins/llms/` | Transform node `plugins/nodes/transforms/llm/` |
| **Structure** | 5 mixed domains | 2 clear domains (orchestrators + nodes) |
| **Registries** | 18 files | 7 files (61% reduction) |
| **Configuration** | Some silent defaults | ❌ NO DEFAULTS (explicit required) |
| **Attributability** | Scattered across files | ✅ Single snapshot per run |
| **Extensibility** | Add experiment plugins | Add orchestrators OR nodes |

---

## Key Principles

### 1. Separation of Concerns
- **Orchestrators** define topology (how data flows through graph)
- **Nodes** define transformations (what happens at each vertex)

### 2. Universal Reusability
- Any orchestrator can use any node type
- Nodes work across experiment, batch, streaming, validation modes

### 3. No Special Cases
- LLM is just another transform (not special)
- All nodes follow clear protocols
- Simpler mental model

### 4. Configuration as Code
- No silent defaults anywhere
- All critical fields required in schemas
- Factory functions raise errors for missing config
- Security, auditability, reproducibility

---

## Final Structure

```
plugins/
├── orchestrators/              # Engines (define topology)
│   ├── registry.py
│   ├── experiment/             # DAG: source → transforms → llm → validate → aggregate → sinks
│   ├── batch/                  # Pipeline: source → transforms → sink
│   └── streaming/              # Stream: source → buffer → transforms → filter → sink
│
└── nodes/                      # Components (define transformations)
    ├── sources/                # Input nodes
    │   └── registry.py
    ├── sinks/                  # Output nodes
    │   └── registry.py
    ├── transforms/             # Processing nodes
    │   ├── registry.py
    │   ├── llm/                # ★ LLM is just ONE transform type
    │   │   ├── clients/
    │   │   ├── middleware/
    │   │   └── controls/
    │   ├── text/               # Text processing
    │   ├── numeric/            # Numeric transforms
    │   └── structural/         # Schema validation, filtering
    ├── aggregators/            # Multi-row processing
    │   └── registry.py
    └── utilities/              # Cross-cutting helpers
        └── registry.py
```

**Registry reduction**: 18 → 7 files (61% decrease)

---

## Timeline

### Week 1: Risk Reduction (8-12 hours)
- **Day 1-2**: Security & testing baseline (4-6 hours)
- **Day 3**: Dependency mapping (2-3 hours)
- **Day 4**: Performance & configuration (2-3 hours)

**Gate review**: All success criteria must pass

### Week 2: Migration (12-17 hours)
- **Phase 1**: Orchestration abstraction (3-4 hours)
- **Phase 2**: Node reorganization (3-4 hours)
- **Phase 3**: Security hardening (2-3 hours)
- **Phase 4**: Protocol consolidation (2-3 hours)
- **Phase 5**: Documentation & tests (2-3 hours)

**Total**: 20-29 hours

---

## Success Criteria

### Risk Reduction Phase
- [ ] Zero P0/P1 silent defaults remain
- [ ] Test coverage >85%
- [ ] All 545 tests passing
- [ ] Characterization tests for all registries
- [ ] Import chain map complete
- [ ] Backward compatibility design approved

### Migration Phase
- [ ] All 545+ tests pass
- [ ] Mypy: 0 errors
- [ ] Ruff: passing
- [ ] LLM in `plugins/nodes/transforms/llm/`
- [ ] 7 registry files (down from 18)
- [ ] Sample suite runs: `make sample-suite`
- [ ] Configuration snapshot implemented
- [ ] No silent defaults anywhere

---

## How to Use This Project

### If you're reviewing the design:
1. Read [`ARCHITECTURE_EVOLUTION.md`](ARCHITECTURE_EVOLUTION.md) - understand the journey
2. Read [`PLUGIN_SYSTEM_DATA_FLOW.md`](PLUGIN_SYSTEM_DATA_FLOW.md) - review target architecture
3. Provide feedback on design decisions

### If you're implementing the migration:
1. **FIRST**: Read [`RISK_REDUCTION_PLAN.md`](RISK_REDUCTION_PLAN.md) - understand risks
2. **COMPLETE**: All Week 1 risk reduction activities
3. **VERIFY**: All gates pass (checklist in risk reduction plan)
4. **THEN**: Follow [`MIGRATION_TO_DATA_FLOW.md`](MIGRATION_TO_DATA_FLOW.md) step-by-step
5. **VERIFY**: Success criteria after each phase

### If you're tracking progress:
- Check **Project Status** section above
- Review gate criteria in risk reduction plan
- Monitor test coverage and performance metrics

---

## Rollback Strategy

**If anything goes wrong**:
1. All changes in version control (git)
2. Backward compatibility shims protect external code
3. Each phase leaves system in working state
4. Can rollback per-phase: `git revert <phase-commits>`
5. Feature flags allow gradual rollout (optional)

**Safety**: 545 tests + new tests must pass after each phase

---

## Questions & Answers

**Q: Why 8-12 hours of risk reduction before migration?**
A: "Measure twice, cut once." Risk reduction prevents 20+ hours of debugging and rollback.

**Q: Can we skip the risk reduction phase?**
A: No. Security audit and testing baseline are CRITICAL to detect breakage.

**Q: What if we find issues during risk reduction?**
A: Fix them before migration. Much easier to fix in current architecture.

**Q: How do we know migration is complete?**
A: All success criteria pass, including "can add batch orchestrator in <2 hours"

**Q: What's the biggest risk?**
A: Silent defaults creating security holes. That's why it's the first activity.

---

## Contact & Escalation

**Project Lead**: [TBD]
**Architecture Review**: [TBD]
**Security Review**: [TBD]

**Escalation Path**:
1. Review gate criteria not met → Review design decisions
2. Migration blocked → Consult rollback procedures
3. Uncertain about risk → Pause and consult project lead

---

## References

- Main architecture docs: [`docs/architecture/`](../../)
- Current plugin catalogue: [`docs/architecture/plugin-catalogue.md`](../../plugin-catalogue.md)
- Configuration docs: [`docs/architecture/configuration-merge.md`](../../configuration-merge.md)
- Main README: [`/README.md`](../../../../README.md)

---

**Remember**: This is a significant architectural shift. The risk reduction activities are not optional - they're essential to ensure a safe, successful migration.

**Key Principle**: **No silent defaults, no hidden behavior, no surprises.**
