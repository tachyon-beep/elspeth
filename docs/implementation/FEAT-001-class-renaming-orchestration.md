# FEAT-001: Class Renaming for Generic Orchestration Model

**Priority**: P3 (NICE-TO-HAVE)
**Effort**: 8-12 hours (1 week)
**Sprint**: Sprint 4 (post-security)
**Status**: NOT STARTED
**Depends On**: VULN-001/002, VULN-003, VULN-004 complete

---

## Context

**User Feedback**: "this system started as an experiment runner but has become a more generic sense decide act orchestrator"

**Problem**: Class names throughout the codebase reflect the original "experiment runner" framing:
- `ExperimentRunner` → Generic orchestration engine
- `ExperimentSuiteRunner` → Multi-workflow orchestrator
- `ExperimentOrchestrator` → Already uses "orchestrator" term
- `experiment_*` module names → Should reflect generic pipeline model
- Plugin type names (`RowExperimentPlugin`, `AggregationExperimentPlugin`) → Should be generic

**Impact**: Naming mismatch creates cognitive dissonance and misleads new contributors about system architecture.

---

## Design Philosophy: Sense-Decide-Act Model

**From README (lines 8-11)**:
> Extensible Layered Secure Pipeline Engine for Transformation and Handling
> Core pipeline: **Sources → Transforms → Sinks**

**Generic Orchestration Pattern**:
```
SENSE (Sources)    → DECIDE (Transforms)     → ACT (Sinks)
DataSource         → LLM + Middleware        → ResultSink
CSV, Azure Blob    → OpenAI, Prompt Shield   → Excel, JSON, Signed Bundle
```

**Experiment Running is ONE Use Case**:
- Sense: Load test dataset
- Decide: Generate LLM responses
- Act: Write results, compare baselines

**Other Use Cases** (future):
- **Data Pipeline**: Sense (SQL) → Decide (Validation) → Act (Transform, Load)
- **Security Monitoring**: Sense (Logs) → Decide (Anomaly Detection) → Act (Alert, Block)
- **Document Processing**: Sense (PDF) → Decide (Classification, Extraction) → Act (Archive, Route)

---

## Proposed Renaming Strategy

### Phase 1: Core Orchestration Classes (3-4 hours)

**Runner → Orchestrator Pattern**:

| Current Name | Proposed Name | Justification |
|--------------|---------------|---------------|
| `ExperimentRunner` | `WorkflowOrchestrator` | Generic workflow execution |
| `ExperimentSuiteRunner` | `SuiteOrchestrator` | Multi-workflow orchestration |
| `ExperimentOrchestrator` | `PipelineOrchestrator` | Manages pipeline construction |

**Rationale**:
- "Workflow" captures generic sense-decide-act pattern
- "Suite" remains clear (collection of workflows)
- "Pipeline" focuses on source→transform→sink chain

### Phase 2: Module Names (2-3 hours)

**Directory Structure Changes**:

```bash
# Before:
src/elspeth/core/experiments/
  ├── runner.py                    # ExperimentRunner
  ├── suite_runner.py              # ExperimentSuiteRunner
  ├── experiment_registries.py     # Plugin registries
  └── plugin_registry.py           # Plugin registration helpers

# After:
src/elspeth/core/orchestration/
  ├── workflow_orchestrator.py     # WorkflowOrchestrator
  ├── suite_orchestrator.py        # SuiteOrchestrator
  ├── plugin_registries.py         # Plugin registries (same)
  └── plugin_registry.py           # Registration helpers (same)
```

**Files to Rename**:
- `src/elspeth/core/experiments/` → `src/elspeth/core/orchestration/`
- `runner.py` → `workflow_orchestrator.py`
- `suite_runner.py` → `suite_orchestrator.py`
- Keep `experiment_registries.py` (plugin types remain experiment-focused for now)

### Phase 3: Plugin Protocol Names (2-3 hours)

**Experiment-Specific → Generic Transform Pattern**:

| Current Name | Proposed Name | Justification |
|--------------|---------------|---------------|
| `RowExperimentPlugin` | `RowTransformPlugin` | Generic row-level transformation |
| `AggregationExperimentPlugin` | `AggregationPlugin` | Generic aggregation (drop "Experiment") |
| `ValidationPlugin` | ✅ KEEP | Already generic |
| `EarlyStopPlugin` | `HaltConditionPlugin` | Generic halt/stop logic |
| `BaselinePlugin` | `ComparisonPlugin` | Generic comparison, not just baselines |

**Rationale**:
- "Transform" reflects Sense-Decide-Act model
- Remove "Experiment" qualifier where not needed
- Focus on plugin BEHAVIOR (transform, aggregate, compare) not USE CASE (experiments)

### Phase 4: Configuration Schema Updates (1-2 hours)

**YAML Configuration Keys**:

```yaml
# Before (experiment-centric):
experiments:
  - name: baseline
    experiment_runner:
      row_plugins: [...]
      aggregation_plugins: [...]

# After (workflow-centric):
workflows:
  - name: baseline
    orchestrator:
      row_transforms: [...]
      aggregators: [...]
```

**Note**: Configuration changes can break existing YAML files, but pre-1.0 status means this is acceptable.

---

## Implementation Approach (Pre-1.0 Aggressive)

### No Backwards Compatibility

**User Requirement**: Zero tolerance for backwards compatibility

**Implications**:
- ❌ NO import aliases (`ExperimentRunner = WorkflowOrchestrator`)
- ❌ NO deprecation warnings
- ❌ NO gradual migration path
- ✅ Direct rename (change everywhere at once)
- ✅ Update ALL imports in single commit
- ✅ Update ALL YAML configs in codebase

### Phase-by-Phase Rollout

**Phase 1** (3-4 hours): Core class renames
1. Rename classes in source files
2. Update all imports throughout codebase
3. Run tests (expect ~50-100 failures from hardcoded strings)
4. Fix test failures
5. Commit

**Phase 2** (2-3 hours): Module renames
1. Rename directories/files
2. Update all imports
3. Run tests
4. Fix path-based test failures
5. Commit

**Phase 3** (2-3 hours): Plugin protocol renames
1. Rename plugin base classes
2. Update all plugin implementations
3. Update registry definitions
4. Run tests
5. Commit

**Phase 4** (1-2 hours): Configuration schema
1. Update schema definitions
2. Update sample YAML files in `config/`
3. Update documentation examples
4. Run validation tests
5. Commit

**Total: 8-12 hours** (aggressive timeline, no backwards compat overhead)

---

## Risk Assessment

### High Risks

**Risk 1: Breaking User Configurations**
- **Impact**: All user YAML files with `experiments:` key will fail validation
- **Mitigation**: Pre-1.0 status means breaking changes acceptable
- **Migration**: Document new schema in CHANGELOG
- **Rollback**: Revert all 4 commits

**Risk 2: Test Failures from String Literals**
- **Impact**: Tests with hardcoded class names (e.g., `assert "ExperimentRunner" in str(obj)`) will fail
- **Mitigation**: Grep for hardcoded strings, update systematically
- **Rollback**: Revert commits

### Medium Risks

**Risk 3: Documentation Lag**
- **Impact**: Docs reference old class names
- **Mitigation**: Update docs in Phase 4 commit
- **Rollback**: None needed (docs can lag briefly)

**Risk 4: External Plugin Authors**
- **Impact**: Third-party plugins importing `ExperimentRunner` will break
- **Mitigation**: Pre-1.0 status means API instability expected
- **Rollback**: None needed (external authors track main branch at own risk)

### Low Risks

**Risk 5: Muscle Memory**
- **Impact**: Developers type old class names from habit
- **Mitigation**: MyPy catches import errors immediately
- **Rollback**: None needed

---

## Acceptance Criteria

### Functional
- [ ] All classes renamed per Phase 1-3 tables
- [ ] All imports updated throughout codebase
- [ ] All tests passing (1445+ tests)
- [ ] Sample YAML configs use new schema

### Documentation
- [ ] README.md updated with new terminology
- [ ] CLAUDE.md updated with new class names
- [ ] Architecture docs (`docs/architecture/`) updated
- [ ] Plugin authoring guide updated

### Quality
- [ ] MyPy passes (no import errors)
- [ ] No references to old names (grep verification)
- [ ] Configuration validation passes

---

## Grep Audit Checklist

Before marking complete, verify no old names remain:

```bash
# Phase 1: Class names
grep -r "ExperimentRunner" src/ tests/ --exclude-dir=.git
grep -r "ExperimentSuiteRunner" src/ tests/ --exclude-dir=.git
grep -r "ExperimentOrchestrator" src/ tests/ --exclude-dir=.git

# Phase 2: Module paths
grep -r "from elspeth.core.experiments" src/ tests/
grep -r "import elspeth.core.experiments" src/ tests/

# Phase 3: Plugin protocols
grep -r "RowExperimentPlugin" src/ tests/
grep -r "AggregationExperimentPlugin" src/ tests/
grep -r "EarlyStopPlugin" src/ tests/

# Phase 4: YAML keys
grep -r "experiment_runner:" config/ tests/
grep -r "experiments:" config/ tests/ --include="*.yaml"
```

**Success Criteria**: All greps return ZERO results (except in historical docs like CHANGELOGs)

---

## Rollback Plan

### If Renaming Causes Issues

**Option 1: Revert All Commits** (Recommended)
```bash
# Revert Phase 4
git revert HEAD

# Revert Phase 3
git revert HEAD~1

# Revert Phase 2
git revert HEAD~2

# Revert Phase 1
git revert HEAD~3

# Verify tests pass
pytest
```

**Option 2: Emergency Hotfix**
- Fix immediate issue (e.g., critical test failure)
- Continue with remaining phases
- Document known issues

**No Feature Flags**: Pre-1.0 status means clean revert only (no flag-based rollback)

---

## Excluded from Scope

**Not Renaming** (keep as-is):
- `BaselinePlugin` → Generic enough, "baseline" is industry term
- `ValidationPlugin` → Already generic
- Package name `elspeth` → Too high-level to change
- CLI commands (`elspeth experiment`, `elspeth suite`) → Can rename later

**Rationale**: Focus on highest-impact names (core classes, modules). Peripheral names can evolve over time.

---

## Documentation Updates Required

### Architecture Docs
- [ ] `docs/architecture/architecture-overview.md` - Update class diagrams
- [ ] `docs/architecture/component-diagram.md` - Update component names
- [ ] `docs/architecture/decisions/README.md` - Update ADR references

### Development Docs
- [ ] `docs/development/plugin-authoring.md` - Update class references
- [ ] `docs/development/lifecycle.md` - Update orchestration flow
- [ ] `README.md` - Update "Core Structure" section
- [ ] `CLAUDE.md` - Update class names in examples

### Configuration Docs
- [ ] `docs/architecture/configuration-security.md` - Update YAML examples
- [ ] `config/sample_suite/settings.yaml` - Update schema
- [ ] All example YAMLs in `config/` - Update keys

---

## Post-Completion Tasks

1. **Create ADR**: Document naming change rationale
2. **Update CHANGELOG**: Breaking change section for v1.0-alpha
3. **Blog Post** (optional): Explain sense-decide-act model
4. **Plugin Author Notice**: Announce breaking change on main branch

---

## Next Steps After Completion

1. **Consider additional renames** (P4 priority):
   - `experiment` CLI command → `workflow`
   - `BaselinePlugin` → `ComparisonPlugin`
   - Test file names (`test_experiments.py` → `test_orchestration.py`)

2. **Refactor documentation** to consistently use sense-decide-act terminology

3. **Add generic use case examples** beyond LLM experimentation

---

## Summary

This feature brings class names in line with the system's evolved architecture as a generic sense-decide-act orchestrator. The aggressive pre-1.0 approach (no backwards compatibility) enables clean, fast renaming without technical debt.

**Effort**: 8-12 hours over 4 phases
**Priority**: P3 (after security work complete)
**Breaking Change**: Yes (pre-1.0 acceptable)
**Rollback**: Clean revert (no feature flags)
