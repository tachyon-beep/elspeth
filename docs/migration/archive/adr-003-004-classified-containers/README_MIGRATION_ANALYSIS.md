# Elspeth Plugin Migration Analysis - Complete Reference

## Overview

This analysis provides a comprehensive inventory and migration plan for adapting the Elspeth plugin architecture to use SecureDataFrame/ClassifiedData containers for ADR-002 security enforcement.

**Three documents are provided:**

1. **plugin_migration_analysis.md** - Comprehensive 600+ line detailed analysis
2. **MIGRATION_SUMMARY.txt** - Quick reference guide for decision makers
3. **DATA_FLOW_DIAGRAM.txt** - Detailed technical flow diagrams
4. **README_MIGRATION_ANALYSIS.md** - This index document

## Quick Facts

- **Total plugin files**: 70
- **Plugin types**: Sources (4), Sinks (16), LLM Transforms (4), Middleware (6), Experiment plugins (30+)
- **Estimated migration effort**: 18-24 hours
- **Risk level**: MEDIUM (affects core data flow)
- **Breaking changes**: Yes (protocol updates required)

## Key Findings

### What's Already Classified
- Artifact metadata (security_level field exists)
- ExecutionMetadata (security_level field exists)
- PluginContext (security_level context available)
- Artifact pipeline (already supports security metadata)

### What Needs Classification
1. **DataFrames** → SecureDataFrame (4 source plugins)
2. **Row context dicts** → ClassifiedData[dict] (in runner)
3. **LLM request metadata** → ClassifiedData[dict] (optional, in middleware)
4. **Row result dicts** → wrapped in ClassifiedData[dict] (in aggregators)

### Critical Path (High Priority)

```
Datasources (4 files)
    ↓
Orchestrator (1 file)
    ↓
Runner (1 file)
    ↓
Middleware & Row Processing (6+10 files)
```

These 6 changes form the critical path and must be completed first.

## Document Guide

### Use MIGRATION_SUMMARY.txt when you need:
- Quick overview of all 70 plugins
- Decision points with recommendations
- Files to modify by priority tier
- Effort/risk assessment table
- 2-3 page quick reference

### Use plugin_migration_analysis.md when you need:
- Detailed plugin inventory with file paths
- Current vs. target behavior specifications
- Complete data passing pattern documentation
- Interface change specifications (before/after)
- Design decision details with rationale

### Use DATA_FLOW_DIAGRAM.txt when you need:
- Visual representation of data transformations
- Middleware unwrap/wrap flow options
- Classification uplifting examples
- Tier-by-tier architecture breakdown
- Understanding specific code paths

## Migration Strategy

### Phase 1: Infrastructure (2-3 hours)
1. Create `ClassifiedData[T]` generic wrapper (if not existing)
2. Add utility functions (unwrap, wrap, uplift)
3. Add SecureDataFrame.head() support

### Phase 2: Critical Path (8-10 hours)
1. Update DataSource protocol
2. Update all 4 datasources
3. Update orchestrator.py
4. Update runner.py for SecureDataFrame input
5. Wrap row context in ClassifiedData[dict]

### Phase 3: Middleware (5-7 hours)
1. Update LLMRequest protocol (optional)
2. Update 6 middleware plugins
3. Implement unwrap/wrap pattern
4. Add security uplifting in after_response()

### Phase 4: Plugins (3-4 hours)
1. Update ~10 row plugins
2. Update 6 aggregators
3. Verify ~5 validators/early-stop (likely no changes)
4. Verify 16 sinks (likely minimal changes)

### Phase 5: Testing (4-6 hours)
1. Unit tests for ClassifiedData wrapping
2. Integration tests for classification uplifting
3. End-to-end tests through full pipeline
4. Security bypass attempt tests (runtime failsafes)

## Key Decisions

### 1. Strict vs Flexible Type Signatures?
**Recommendation: STRICT**
- `DataSource.load()` → `SecureDataFrame` (not union)
- `ExperimentRunner.run(df)` → accepts `SecureDataFrame`
- Enforces security guarantees at type level

### 2. Where to wrap row context?
**Recommendation: EARLY**
- Wrap at row extraction (runner.py:781)
- Easier to track through pipeline
- Clear ownership of classification

### 3. Middleware unwrapping strategy?
**Recommendation: RUNNER UNWRAPS**
- Runner handles ClassifiedData wrapping/unwrapping
- Middleware receives plain dict (no changes to middleware code)
- Runner re-wraps after middleware chain
- Cleaner API for middleware plugins

### 4. Nesting depth of ClassifiedData?
**Recommendation: FLAT (Phase 1), NESTED (Phase 2)**
- Phase 1: Only container-level (ClassifiedData[dict])
- Phase 2: Add field-level ClassifiedValue for sensitive fields
- Allows granular security tracking later

## File Locations

All relative to `/home/john/elspeth/src/elspeth/`

### Critical Path Files
- `core/security/secure_data.py` - Existing SecureDataFrame
- `core/orchestrator.py` - Main entry point (181 lines)
- `core/experiments/runner.py` - Core runner (950+ lines)
- `core/base/protocols.py` - Protocol definitions
- `plugins/nodes/sources/` - 4 datasource implementations

### Supporting Files
- `core/registries/middleware.py` - Middleware registry
- `core/pipeline/artifact_pipeline.py` - Artifact management
- `core/base/plugin_context.py` - Plugin context
- `core/validation/base.py` - Validation/error classes

## Code Examples

### Before: Datasource
```python
def load(self) -> pd.DataFrame:
    df = pd.read_csv(...)
    df.attrs['security_level'] = self.security_level
    return df
```

### After: Datasource
```python
def load(self) -> SecureDataFrame:
    df = pd.read_csv(...)
    return SecureDataFrame.create_from_datasource(
        df, 
        SecurityLevel(self.security_level)
    )
```

### Before: Orchestrator
```python
df = self.datasource.load()
if self.config.max_rows:
    df = df.head(self.config.max_rows)
payload = runner.run(df)
```

### After: Orchestrator
```python
classified_df = self.datasource.load()  # Returns SecureDataFrame
if self.config.max_rows:
    classified_df = classified_df.head(self.config.max_rows)  # New method
payload = runner.run(classified_df)  # Updated signature
```

### Before: Row Processing
```python
context = {field: row[field] for field in fields}
# context is plain dict[str, Any]
```

### After: Row Processing
```python
context_dict = {field: row[field] for field in fields}
context = ClassifiedData(context_dict, frame.classification)
# context is ClassifiedData[dict]
```

## Testing Strategy

### Unit Tests
- `test_classified_data_wrapping.py` - ClassifiedData[T] creation/uplifting
- `test_classified_dataframe_slicing.py` - head() method behavior
- `test_security_uplifting.py` - max() operation on classifications

### Integration Tests
- `test_datasource_to_orchestrator.py` - SecureDataFrame propagation
- `test_orchestrator_to_runner.py` - DataFrame passing
- `test_runner_row_processing.py` - Row context classification
- `test_middleware_uplifting.py` - Classification through middleware chain

### End-to-End Tests
- `test_full_pipeline_classification.py` - Complete data flow
- `test_classification_high_water_mark.py` - Verify uplifting works
- `test_runtime_failsafes.py` - validate_compatible_with() enforcement

### Security Tests
- `test_unauthorized_access_bypass.py` - Catch clearance violations
- `test_classification_downgrade_prevention.py` - Immutability enforcement
- `test_constructor_protection.py` - Datasource-only creation

## Rollback Plan

If migration encounters critical issues:

1. **Code Review**: Revert to using DataFrame.attrs for classification
2. **Keep ClassifiedData**: Even if not used in runner, keep infrastructure
3. **Partial Migration**: Migrate critical path only, defer plugins for later
4. **Feature Flag**: Make SecureDataFrame optional during transition

## Success Criteria

Migration is complete when:

1. All datasources return SecureDataFrame
2. Orchestrator handles SecureDataFrame
3. Runner processes SecureDataFrame
4. Row context is wrapped in ClassifiedData[dict]
5. Middleware chain preserves and uplifts classification
6. All 70 plugins verified (changed or confirmed no change needed)
7. Classification uplifting tested through full pipeline
8. Runtime failsafes (validate_compatible_with) tested
9. No regression in existing functionality
10. Performance impact < 5%

## Next Steps

1. **Review** MIGRATION_SUMMARY.txt (5 min read)
2. **Discuss** key decisions (sections 6 in MIGRATION_SUMMARY.txt)
3. **Plan** Phase 1 (2-3 hours) with team
4. **Implement** critical path (Phase 2)
5. **Test** thoroughly before moving to plugins
6. **Document** any deviations from this plan

## Questions?

Key decision points to clarify before starting:
1. Strict vs flexible types? → We recommend STRICT
2. Middleware unwrapping strategy? → We recommend RUNNER UNWRAPS
3. Timeline/phasing? → We recommend all 5 phases in sequence
4. Testing scope? → We recommend comprehensive (unit + integration + E2E)
5. Rollback planning? → See "Rollback Plan" section above

---

**Document Set Created**: Analysis of Elspeth plugin migration scope
**Total Lines of Analysis**: 2000+
**Time to Review**: 30-60 minutes
**Time to Implement**: 18-24 hours
**Team Size Recommended**: 1-2 engineers
