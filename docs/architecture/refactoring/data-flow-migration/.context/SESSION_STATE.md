# Session State: Data Flow Migration Project

**Date**: October 14, 2025
**Status**: Design Complete - Ready for Risk Reduction Phase
**Current Working Directory**: `/home/john/elspeth/docs/architecture`

---

## What We've Accomplished

### 1. Fixed Critical P0 Issues

**Issue 1: Module-level @property decorators** (`src/elspeth/core/controls/registry.py:189-204`)
- **Problem**: `@property` decorators at module level created property objects instead of returning dicts
- **Error**: `'property' object is not subscriptable`
- **Fix**: Changed to direct module-level references
  ```python
  # Lines 188-191 - FIXED
  _rate_limiters: dict[str, Any] = rate_limiter_registry._plugins
  _cost_trackers: dict[str, Any] = cost_tracker_registry._plugins
  ```
- **Verification**: All 545 tests pass

**Issue 2: P0 Security Regression** (`src/elspeth/core/registry/plugin_helpers.py:198`)
- **Problem**: Silent default to "OFFICIAL" security level bypassed security requirements
- **User Flag**: "create_row_plugin({'name': 'score_extractor'}) now succeeds instead of raising ConfigurationError"
- **Fix**: Removed silent default, now raises ConfigurationError when security_level missing
  ```python
  # Lines 197-205 - FIXED
  if level is None:
      raise ConfigurationError(
          f"{plugin_kind}:{name}: security_level is required but not provided "
          f"(no explicit level in definition or options, and no parent context to inherit from)"
      )
  ```
- **Verification**: All 545 tests still pass (no tests relied on silent default)

### 2. Cleaned Up All Mypy Errors

**Before**: 27 mypy errors
**After**: 0 mypy errors

**Categories Fixed**:
- Return type mismatches (6 errors) - Added assertions with `allow_none=False` pattern
- Argument type mismatches (9 errors) - Added null/type checks before validation
- Unreachable code (3 errors) - Fixed exception handling, added documented type ignores
- Dynamic import issues (3 errors) - Added None checks for importlib
- Any return types (3 errors) - Added documented type ignores in ConfigMerger

**Files Modified**:
- `src/elspeth/core/llm/registry.py`
- `src/elspeth/core/experiments/plugin_registry.py`
- `src/elspeth/core/experiments/suite_runner.py`
- `src/elspeth/core/registry/context_utils.py`
- `src/elspeth/core/registry/__init__.py`
- `src/elspeth/core/experiments/config_merger.py`
- `src/elspeth/core/controls/registry.py`

### 3. Architectural Design Complete

Created comprehensive data flow architecture based on user insights:

**Key Insight**: "LLM connection is a **function** that any job should be able to do. The core feature is **pumping data between nodes**."

**Architectural Documents Created** (in `docs/architecture/refactoring/data-flow-migration/`):
1. `README.md` - Project overview and navigation
2. `ARCHITECTURE_EVOLUTION.md` - Journey through 4 design stages
3. `PLUGIN_SYSTEM_DATA_FLOW.md` - Target architecture specification
4. `MIGRATION_TO_DATA_FLOW.md` - 5-phase implementation guide (12-17 hours)
5. `RISK_REDUCTION_PLAN.md` - Pre-migration risk mitigation (8-12 hours)
6. `CONFIGURATION_ATTRIBUTABILITY.md` - Config snapshot design
7. `PLUGIN_SYSTEM_ANALYSIS.md` - Initial analysis (historical)
8. `PLUGIN_SYSTEM_REVISED.md` - Intermediate design (historical)

---

## Current Architecture vs Target

### Current Structure (LLM-Centric)
```
plugins/
├── datasources/              # 3 files
├── llms/                     # 6 files (LLM special-cased)
├── outputs/                  # 12 files
├── experiments/              # 5 files
└── utilities/                # 1 file

Registry files: 18 total
```

### Target Structure (Data Flow)
```
plugins/
├── orchestrators/            # Engines (define topology)
│   ├── experiment/           # DAG pattern
│   ├── batch/                # Pipeline pattern
│   └── streaming/            # Stream pattern
└── nodes/                    # Components (transformations)
    ├── sources/              # Input nodes
    ├── sinks/                # Output nodes
    ├── transforms/           # Processing nodes
    │   ├── llm/              # ★ Just ONE transform type
    │   ├── text/
    │   ├── numeric/
    │   └── structural/
    ├── aggregators/          # Multi-row
    └── utilities/            # Cross-cutting

Registry files: 7 total (61% reduction)
```

---

## Key Architectural Principles

1. **Separation of Concerns**
   - **Orchestrators** = Engines that define topology (how nodes connect)
   - **Nodes** = Components that define transformations (what happens at vertices)

2. **LLM is Not Special**
   - Before: `plugins/llms/` (special domain)
   - After: `plugins/nodes/transforms/llm/` (just another transform)

3. **Explicit Configuration Only** (Security)
   - NO silent defaults anywhere
   - All critical fields marked `required` in schemas
   - Factory functions raise ConfigurationError for missing config
   - User requirement: "every plugin must be fully specified each time or it won't run"

4. **Configuration Attributability**
   - Single `ResolvedConfiguration` snapshot per run
   - Complete and self-contained
   - Provenance tracking (where each value came from)
   - User requirement: "all configuration for a run must be colocated"

---

## What Needs to Happen Next

### CURRENT PHASE: Risk Reduction (8-12 hours)

**CRITICAL: Must complete BEFORE migration starts**

#### Activity 1: Silent Default Audit (2-3 hours) - PRIORITY 1
**Why**: Security vulnerability - silent defaults hide configuration and bypass requirements

**Tasks**:
```bash
# Search for .get() with defaults
rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/ > silent_defaults_audit.txt

# Search for "or" fallbacks
rg "\|\|\s*['\"]" src/elspeth/ >> silent_defaults_audit.txt

# Search for default parameter values
rg "def create_.*\(.*=.*\):" src/elspeth/ >> silent_defaults_audit.txt
```

**Categorize**:
- CRITICAL: security_level, authentication, validation
- HIGH: model, endpoint, temperature, timeout
- MEDIUM: retry_count, buffer_size
- LOW: display_name, formatting

**Deliverables**:
- [ ] Complete audit file with all defaults found
- [ ] Categorization by severity
- [ ] Security enforcement tests created
- [ ] All CRITICAL/HIGH defaults removed or documented

#### Activity 2: Test Coverage Audit (2-3 hours) - PRIORITY 1
**Why**: Need baseline to detect any breakage during migration

**Tasks**:
```bash
# Generate coverage report
python -m pytest --cov=elspeth --cov-report=html --cov-report=term-missing --cov-report=json

# Target: >85% coverage
```

**Create Characterization Tests**:
- Test current registry lookup behavior (all 18 registries)
- Test plugin creation patterns
- Test configuration merge behavior
- Test security level resolution
- Document expected behavior (golden output tests)

**Deliverables**:
- [ ] Coverage report generated and reviewed
- [ ] Characterization tests for all 18 registries
- [ ] 5+ end-to-end smoke tests created
- [ ] All 545+ tests passing

#### Activity 3: Import Chain Mapping (2-3 hours) - PRIORITY 2
**Why**: Moving files will break imports - need to know where everything is used

**Tasks**:
```bash
# Find all registry imports
rg "from elspeth\.core\.registry" src/ tests/ > registry_imports.txt
rg "from elspeth\.core\.datasource_registry" src/ tests/ >> registry_imports.txt
rg "from elspeth\.core\.llm_registry" src/ tests/ >> registry_imports.txt
rg "from elspeth\.plugins\.llms" src/ tests/ >> registry_imports.txt
rg "from elspeth\.plugins\.datasources" src/ tests/ >> registry_imports.txt
rg "from elspeth\.plugins\.outputs" src/ tests/ >> registry_imports.txt
rg "from elspeth\.plugins\.experiments" src/ tests/ >> registry_imports.txt
```

**Identify**:
- What do users import directly? (external API surface)
- What do tests import? (indicates API dependencies)
- What's in `__all__` exports? (public API contract)

**Deliverables**:
- [ ] Complete import chain map
- [ ] External API surface identified
- [ ] Backward compatibility shim design
- [ ] Migration plan includes shim creation

#### Activity 4: Performance Baseline (1-2 hours) - PRIORITY 3
**Why**: Need to detect performance regressions

**Tasks**:
```bash
# Run sample suite with timing
time python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/perf_baseline \
  --head 100

# Profile critical paths
python -m cProfile -o registry_profile.prof -m elspeth.cli ...
```

**Create regression tests**:
- Registry lookups should be <1ms
- Plugin creation should be <10ms
- Config merge should be <50ms
- Artifact pipeline should be <100ms

**Deliverables**:
- [ ] Performance baseline metrics documented
- [ ] Critical path timings recorded
- [ ] Regression tests created
- [ ] Acceptable thresholds defined

#### Activity 5: Configuration Audit (1-2 hours) - PRIORITY 3
**Why**: Migration might change config structure - need compatibility

**Tasks**:
```bash
# Find all configs
find . -name "*.yaml" -o -name "*.yml" | grep -v ".venv" > configs_inventory.txt

# Check plugin references
rg "plugin:\s*" config/ tests/ >> plugin_references.txt
```

**Deliverables**:
- [ ] All existing configs inventoried
- [ ] All sample configs parse successfully
- [ ] Configuration compatibility layer designed
- [ ] Old config formats will still work

#### Activity 6: Migration Safety (2-3 hours) - PRIORITY 3
**Why**: Need safe rollback and phase checkpoints

**Tasks**:
- Design phase checkpoints (each phase leaves system working)
- Create detailed migration checklist
- Optional: Implement feature flags for gradual rollout
- Document rollback procedures

**Deliverables**:
- [ ] Phase checkpoints defined
- [ ] Migration checklist created
- [ ] Rollback procedures documented
- [ ] (Optional) Feature flags implemented

### GATES: Must Pass Before Migration

All of these must be ✅ before proceeding to migration:

- [ ] Silent default audit complete (zero P0/P1 defaults)
- [ ] Test coverage >85%
- [ ] All 545+ tests passing
- [ ] Characterization tests for all 18 registries
- [ ] 5+ end-to-end smoke tests
- [ ] Import chain map complete
- [ ] External API surface identified
- [ ] Backward compatibility shims designed
- [ ] Performance baseline established
- [ ] Configuration compatibility layer designed
- [ ] Migration checklist created
- [ ] Rollback procedures documented

### BLOCKED: Migration (Week 2 - 12-17 hours)

**Cannot start until ALL gates pass**

Migration phases (from `MIGRATION_TO_DATA_FLOW.md`):
1. Orchestration abstraction (3-4h)
2. Node reorganization (3-4h)
3. Security hardening (2-3h)
4. Protocol consolidation (2-3h)
5. Documentation & tests (2-3h)

---

## Critical Files to Know

### Recently Modified (mypy/security fixes)
- `src/elspeth/core/controls/registry.py:188-191` - Fixed module-level properties
- `src/elspeth/core/registry/plugin_helpers.py:197-205` - P0 security fix (no silent default)
- `src/elspeth/core/llm/registry.py:31-54` - Fixed return type with assertions
- `src/elspeth/core/experiments/plugin_registry.py` - Fixed 5 return type + 5 argument type errors
- `src/elspeth/core/experiments/suite_runner.py` - Fixed unreachable code warnings
- `src/elspeth/core/registry/context_utils.py:91-110` - Fixed exception handling
- `src/elspeth/core/registry/__init__.py:31-41` - Fixed dynamic import checks
- `src/elspeth/core/experiments/config_merger.py:195-212` - Fixed Any return types

### New Architecture Docs
- `docs/architecture/refactoring/data-flow-migration/README.md` - START HERE
- `docs/architecture/refactoring/data-flow-migration/RISK_REDUCTION_PLAN.md` - DO FIRST
- `docs/architecture/refactoring/data-flow-migration/ARCHITECTURE_EVOLUTION.md` - Understanding
- `docs/architecture/refactoring/data-flow-migration/PLUGIN_SYSTEM_DATA_FLOW.md` - Target
- `docs/architecture/refactoring/data-flow-migration/MIGRATION_TO_DATA_FLOW.md` - How-to

### Updated Docs
- `docs/architecture/README.md` - Updated with link to refactoring project

---

## Key Technical Context

### Test Status
- **Total tests**: 545
- **All passing**: ✅
- **Mypy errors**: 0
- **Ruff status**: Clean
- **Coverage**: ~84% (need to verify and push >85%)

### Git Status
```
M coverage.xml
M src/elspeth/core/controls/registry.py
M src/elspeth/core/experiments/config_merger.py
M src/elspeth/core/experiments/plugin_registry.py
M src/elspeth/core/experiments/suite_runner.py
M src/elspeth/core/llm/registry.py
M src/elspeth/core/registry/__init__.py
M src/elspeth/core/registry/plugin_helpers.py
M src/elspeth/core/registry/context_utils.py
M docs/architecture/README.md
?? docs/architecture/refactoring/
```

### Current Branch
- `main` (on latest commit)

### Environment
- Python 3.x
- Virtual env: `.venv/`
- All dependencies installed
- Commands work: `make bootstrap`, `make sample-suite`, `python -m pytest`

---

## User's Key Insights (Direct Quotes)

1. **On orchestration**: "this is an orchestrator that can do experimentation, experimentation is just one thing it can do - it should have an 'orchestrator' plugin which defines its 'basic functionality' and can be swapped out"

2. **On configuration**: "a key point that has to be drawn out is that all the configuration for a particular orchestration run has to be colocated for attributability - we can't have a dozen config files scattered across the system each run"

3. **On LLM's role**: "llm connection is a -function- that any job should be able to do, the underlying orchestration (pump data around between plugins, sinks and sources) is the orchestration plugin - think of separating the engine from the wheels and steering wheel and fuel tank - the core feature is 'pumping data between nodes', the LLM can be one of those nodes"

4. **On security**: "for security purposes, I think we want to enforce 'always run from config' - i.e. never fall back to a default mode inside the plugin, every plugin must be fully specified each time or it won't run"

---

## Immediate Next Steps (When Session Resumes)

1. **Start with Activity 1**: Silent default audit
   - Run the regex searches
   - Create audit file
   - Categorize findings
   - Create security enforcement tests

2. **Then Activity 2**: Test coverage audit
   - Generate coverage report
   - Create characterization tests
   - Document expected behavior

3. **Continue through Activities 3-6** in priority order

4. **Gate Check**: Verify all gates pass before migration

5. **Only then**: Begin migration Phase 1

---

## Important Reminders

- **No silent defaults allowed** - this is a security requirement
- **All 545+ tests must pass** after every change
- **Backward compatibility is critical** - external code depends on current structure
- **Each migration phase must leave system working** - can commit after each phase
- **Risk reduction is NOT optional** - it prevents 20+ hours of debugging

---

## Success Criteria (Final)

### Risk Reduction Complete
- [ ] Zero P0/P1 silent defaults
- [ ] Coverage >85%, all tests passing
- [ ] Characterization tests for all registries
- [ ] Import map and shim design complete
- [ ] Performance baseline and regression tests
- [ ] Config compatibility layer designed

### Migration Complete
- [ ] All 545+ tests pass
- [ ] Mypy: 0 errors
- [ ] Ruff: passing
- [ ] LLM in `plugins/nodes/transforms/llm/`
- [ ] 7 registry files (down from 18)
- [ ] Sample suite runs: `make sample-suite`
- [ ] No silent defaults anywhere
- [ ] Can add batch orchestrator in <2 hours (proof of extensibility)
