# Core Directory Restructure Proposal

**Status:** In Progress (Phase 1 cleanup complete; full restructure deferred)
**Created:** 2025-10-17
**Last Reviewed:** 2025-10-20
**Context:** Post plugin-split refactoring
**Decision:** Defer full restructure until follow-up roadmap slot; continue incremental cleanup

> **2025-10-20 Status Update:** The minimal cleanup recommended in this proposal has been delivered:
> - Empty `core/plugins/` and `core/llm/` directories were removed.
> - Canonical registries now live in `core/registries/`, with legacy modules reissued as compatibility shims.
> - Downstream imports in plugins now target the new registry package.
>
> The comprehensive re-org (moving validation, pipeline, utilities, etc. into new subpackages) remains outstanding. The sections marked “Historical Snapshot (2025-10-17)” below capture the original analysis and are preserved for context.

## Executive Summary

The `src/elspeth/core/` directory still places a large number of modules at the package root, which hinders discoverability. This proposal documents the historical state, the cleanup already performed, and the remaining steps required to complete the restructure.

**Phase 1 Outcomes (Shipped 2025-10-20):**
- Registry infrastructure consolidated under `core/registries/`
- Legacy `*_registry.py` modules replaced with compatibility shims
- Deprecated `core/plugins/` and `core/llm/` folders deleted

**Outstanding Work (Phase 2 Candidates):**
- Move validation, pipeline, configuration, and utility code into dedicated subpackages (`validation/`, `pipeline/`, `config/`, `utils/`)
- Retire compatibility shims once downstream imports are updated
- Introduce meaningful content (or remove) the placeholder `core/utilities/` package
- Reduce oversized modules (`validation.py`, `schema.py`, `logging.py`) via logical splits

**Recommendation:** Schedule the remaining migrations as a dedicated refactor window once current roadmap priorities allow.

---

## Current Structure Snapshot (2025-10-20)

```
src/elspeth/core/
├── registries/                # Canonical registry implementations (Phase 1)
├── registry/                  # Compatibility shim package (to remove post-migration)
├── controls/, experiments/, prompts/, security/
├── artifact_pipeline.py, validation.py, ...
├── logging.py, env_helpers.py
├── utilities/                 # Empty placeholder introduced for future helpers
└── *_registry.py              # Compatibility shims mirroring `registries/`
```

### Quick Progress Checklist

| Area                           | Status | Notes |
| ----------------------------- | ------ | ----- |
| Remove empty `core/plugins/` and `core/llm/` dirs | ✅ | Completed in Phase 1 cleanup |
| Consolidate registry implementations | ✅ | `core/registries/` now authoritative |
| Update downstream imports (`prompt_variants`, `validation`, etc.) | ✅ | Imports target `core.registries.*` |
| Document current structure    | ✅ | `docs/architecture/CORE_STRUCTURE_CURRENT.md` refreshed |
| Introduce new subpackages (`validation/`, `pipeline/`, `config/`, `utils/`) | ⬜ | Pending |
| Split oversized modules       | ⬜ | Pending (identify cut points) |
| Remove registry compatibility shims | ⬜ | Pending downstream adoption |

---

## Historical Snapshot (2025-10-17)

> The following sections preserve the original analysis prior to the 2025-10-20 cleanup. Figures and file counts reflect that earlier state and are retained for traceability.

### Current State Analysis (Historical)

### Directory Statistics

```
Total files at core/ root:     21 Python files (~185KB)
Total subdirectories:          8 (2 empty, 6 with content)
Empty directories:             core/plugins/, core/llm/
Files per category:            Registry(6), Validation(2), Orchestration(4),
                               Config(2), Base/Protocol(4), Utils(2), Other(1)
```

### Files at Core Root Level

#### REGISTRY FILES (6 files, ~50KB)
```
datasource_registry.py       6.2K  - Datasource plugin registry
llm_registry.py              8.5K  - LLM client plugin registry
llm_middleware_registry.py   3.7K  - Middleware plugin registry
sink_registry.py              18K  - Sink plugin registry
utility_plugin_registry.py   2.2K  - Utility plugin registry
registry.py                   11K  - Facade (barely used, only 2 real imports)
```

**Import Impact:** 44 imports total across codebase
- `llm_registry`: 15 imports
- `sink_registry`: 9 imports
- `llm_middleware_registry`: 10 imports
- `datasource_registry`: 7 imports
- `utility_plugin_registry`: 3 imports

#### VALIDATION FILES (2 files, ~39KB)
```
validation.py                 31K  - Main validation logic
validation_base.py           7.6K  - Base validation classes
```

**Import Impact:** 54 imports total
- `validation`: 17 imports
- `validation_base`: 37 imports

#### ORCHESTRATION FILES (4 files, ~24KB)
```
orchestrator.py              6.9K  - Main orchestrator
artifact_pipeline.py          15K  - Artifact dependency resolution
artifacts.py                 1.4K  - Artifact types
processing.py                1.1K  - Processing utilities
```

**Import Impact:** 6 imports (artifact_pipeline)

#### CONFIG FILES (2 files, ~11KB)
```
config_schema.py             1.8K  - Configuration schemas
config_validation.py         9.3K  - Configuration validation
```

**Import Impact:** 2 imports total

#### BASE/PROTOCOL FILES (4 files, ~45KB)
```
protocols.py                 8.9K  - Core protocol definitions
types.py                      13K  - Core type definitions
schema.py                     18K  - Schema utilities
plugin_context.py            5.3K  - Plugin context system
```

**Import Impact:** 98 imports total
- `protocols`: 50 imports (HIGHEST)
- `plugin_context`: 34 imports
- `schema`: 13 imports
- `types`: 1 import

#### UTILITY FILES (2 files, ~16KB)
```
logging.py                    14K  - Logging infrastructure
env_helpers.py               2.0K  - Environment variable helpers
```

**Import Impact:** 1 import (logging)

#### OTHER
```
__init__.py                  0.3K  - Package init
```

### Existing Subdirectories

#### With Content (Good)
```
experiments/  - Experiment runner, suite runner, plugin registry (7 files)
controls/     - Rate limiters, cost trackers (6 files)
security/     - Security controls, PII validators, signing (5 files)
prompts/      - Prompt rendering (3 files)
registry/     - Base registry infrastructure (5 files)
              ❌ BUT actual *_registry.py implementations are at ROOT!
utilities/    - Miscellaneous utilities (proposal to introduce; placeholder added in Phase 1)
```

#### Empty (Should Delete)
```
llm/         - ❌ EMPTY (only __pycache__)
             - Previously contained LLM-related code, now moved
             - Leftover from refactoring

plugins/     - ❌ EMPTY (only __pycache__)
             - Previously contained context.py (moved to plugin_context.py)
             - Leftover from commit 170a118 (Oct 16, 2025)
```

### Git History of Empty Directories

```bash
$ git log --oneline --all -- src/elspeth/core/plugins/
170a118 Refactor plugin imports and registry structure  # context.py moved out
192bd4a Complete registry migration
...

$ git show 192bd4a:src/elspeth/core/plugins/
__init__.py
context.py  # This file was moved to core/plugin_context.py
```

**Root Cause:** Empty directories created during "Refactor plugin imports and registry structure" (Oct 16) when `core/plugins/context.py` was moved to `core/plugin_context.py`.

---

## Problems Identified

### 1. Empty Directories with No Purpose
- (Resolved 2025-10-20) `core/plugins/` and `core/llm/` no longer exist
- Original issue retained here for historical context

### 2. Registry Organization Inconsistency
- **Infrastructure** lives in `core/registry/` subdirectory:
  - `base.py` - BasePluginRegistry framework
  - `context_utils.py` - Context utilities
  - `plugin_helpers.py` - Helper functions
  - `schemas.py` - Schema definitions

- **Implementations** live at root level:
  - `datasource_registry.py`
  - `llm_registry.py`
  - `llm_middleware_registry.py`
  - `sink_registry.py`
  - `utility_plugin_registry.py`

- **Facade** barely used:
  - `registry.py` - Only 2 real imports, mostly re-exports

**Why This is Confusing:**
- Not obvious where to find registry code
- Split suggests there's a meaningful separation, but implementations should be with infrastructure
- Facade adds layer of indirection without clear benefit

### 3. Too Many Files at Root Level
- **21 Python files** makes navigation difficult
- No logical grouping visible from file listing
- Hard to understand subsystem boundaries
- Cognitive overhead when searching for code

### 4. Utilities Scattered
- Utility files (`env_helpers.py`, `logging.py`) at root
- No `utilities/` subdirectory to group them
- Inconsistent with other subsystems (experiments/, controls/, security/)

### 5. Validation Split Oddly
- `validation.py` and `validation_base.py` at root
- Could be in `validation/` subdirectory for consistency
- Base and implementation logically belong together

### 6. Inconsistent Naming
- Some subdirectories plural (`experiments/`, `prompts/`, `controls/`)
- Some singular (`security/`, `registry/`)
- Root-level files use different naming pattern (`*_registry.py` vs `registry/`)

---

## Proposed Structure

### Option A: Full Restructure (Deferred)

```
src/elspeth/core/
├── __init__.py                        # Package init with convenience re-exports
├── orchestrator.py                    # Keep at root - main entry point
│
├── registries/                        # UNIFIED registry code
│   ├── __init__.py                   # Re-export all registries
│   ├── base.py                       # FROM core/registry/base.py
│   ├── context_utils.py              # FROM core/registry/context_utils.py
│   ├── plugin_helpers.py             # FROM core/registry/plugin_helpers.py
│   ├── schemas.py                    # FROM core/registry/schemas.py
│   ├── datasource.py                 # MOVE datasource_registry.py → datasource.py
│   ├── llm.py                        # MOVE llm_registry.py → llm.py
│   ├── middleware.py                 # MOVE llm_middleware_registry.py → middleware.py
│   ├── sink.py                       # MOVE sink_registry.py → sink.py
│   └── utility.py                    # MOVE utility_plugin_registry.py → utility.py
│   # DELETE core/registry.py facade
│
├── validation/                        # NEW - unified validation code
│   ├── __init__.py
│   ├── base.py                       # MOVE validation_base.py
│   └── validators.py                 # MOVE validation.py
│
├── pipeline/                          # NEW - orchestration pipeline
│   ├── __init__.py
│   ├── artifacts.py                  # MOVE artifacts.py
│   ├── artifact_pipeline.py          # MOVE artifact_pipeline.py
│   └── processing.py                 # MOVE processing.py
│
├── base/                              # NEW - core abstractions
│   ├── __init__.py
│   ├── protocols.py                  # MOVE protocols.py
│   ├── types.py                      # MOVE types.py
│   ├── schema.py                     # MOVE schema.py
│   └── plugin_context.py             # MOVE plugin_context.py
│
├── config/                            # NEW - configuration handling
│   ├── __init__.py
│   ├── schema.py                     # MOVE config_schema.py
│   └── validation.py                 # MOVE config_validation.py
│
├── utils/                             # NEW - utilities
│   ├── __init__.py
│   ├── logging.py                    # MOVE logging.py
│   └── env_helpers.py                # MOVE env_helpers.py
│
├── experiments/                       # KEEP - already well organized
│   ├── __init__.py
│   ├── config.py
│   ├── config_merger.py
│   ├── experiment_registries.py
│   ├── plugin_registry.py
│   ├── runner.py
│   ├── suite_runner.py
│   └── tools.py
│
├── controls/                          # KEEP - already well organized
│   ├── __init__.py
│   ├── cost_tracker.py
│   ├── cost_tracker_registry.py
│   ├── rate_limit.py
│   ├── rate_limiter_registry.py
│   └── registry.py
│
├── security/                          # KEEP - already well organized
│   ├── __init__.py
│   ├── approved_endpoints.py
│   ├── pii_validators.py
│   ├── secure_mode.py
│   └── signing.py
│
└── prompts/                           # KEEP - already well organized
    ├── __init__.py
    ├── jinja_renderer.py
    └── sanitization.py

# DELETE these empty directories:
# - core/llm/
# - core/plugins/
# - core/registry/ (merged into registries/)
```

### Option B: Minimal Cleanup (Immediate)

**Actions:**
1. Delete `core/llm/` directory (empty)
2. Delete `core/plugins/` directory (empty)
3. Delete `core/registry.py` facade (barely used - only 2 imports)
4. Update those 2 imports to use specific registries directly
5. Add comments to top-level files explaining grouping

**Files to Update:**
```python
# src/elspeth/plugins/experiments/prompt_variants.py
# Change:
from elspeth.core.registry import create_llm_from_definition
# To:
from elspeth.core.llm_registry import create_llm_from_definition

# src/elspeth/plugins/experiments/validation.py
# Same change
```

**Result:**
- Removes confusion from empty directories
- Removes unused facade layer
- Minimal disruption (2 imports)
- Defers major restructure

---

## Benefits of Full Restructure

### 1. Clear Logical Grouping
- Related files together in subdirectories
- Easier to understand subsystem boundaries
- Reduced cognitive load when navigating code

### 2. Registries Unified
- All registry code in one place (`registries/`)
- Infrastructure and implementations together
- No confusing split

### 3. Consistent Organization
- All major subsystems in subdirectories
- Follows established patterns (experiments/, controls/, security/)
- Root level only for `__init__.py` and main entry point

### 4. Easier Navigation
- Subdirectories reduce visual clutter
- Clear hierarchy shows relationships
- Easier to find code by subsystem

### 5. Better Documentation Structure
- Directory structure self-documents architecture
- New developers can navigate more intuitively
- Aligns with documentation diagrams

### 6. Future-Proof
- Easier to add new files to existing subsystems
- Clear place for new utilities/validators/etc.
- Reduces likelihood of root-level sprawl

---

## Import Migration Analysis

### Total Impact: 205 Import Statements

#### High-Impact Modules (>30 imports each)
```
protocols.py        50 imports  →  core/base/protocols.py
validation_base.py  37 imports  →  core/validation/base.py
plugin_context.py   34 imports  →  core/base/plugin_context.py
```

#### Medium-Impact Modules (10-30 imports)
```
validation.py               17 imports  →  core/validation/validators.py
llm_registry.py             15 imports  →  core/registries/llm.py
schema.py                   13 imports  →  core/base/schema.py
llm_middleware_registry.py  10 imports  →  core/registries/middleware.py
sink_registry.py             9 imports  →  core/registries/sink.py
```

#### Low-Impact Modules (<10 imports)
```
datasource_registry.py      7 imports  →  core/registries/datasource.py
artifact_pipeline.py        6 imports  →  core/pipeline/artifact_pipeline.py
utility_plugin_registry.py  3 imports  →  core/registries/utility.py
config_validation.py        1 import   →  core/config/validation.py
config_schema.py            1 import   →  core/config/schema.py
logging.py                  1 import   →  core/utils/logging.py
types.py                    1 import   →  core/base/types.py
env_helpers.py              0 imports  →  core/utils/env_helpers.py
```

### Affected Files Breakdown

```bash
# Commands used for analysis:
grep -r "from elspeth.core.protocols import" src/ tests/ --include="*.py" | wc -l
# Repeat for each module...

# Total across all moved modules:
205 import statements require updates
```

### Import Update Examples

#### Before (Current)
```python
from elspeth.core.llm_registry import llm_registry
from elspeth.core.sink_registry import sink_registry
from elspeth.core.protocols import DataSource, ResultSink
from elspeth.core.validation_base import ConfigurationError
from elspeth.core.plugin_context import PluginContext
```

#### After (Proposed)
```python
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.sink import sink_registry
from elspeth.core.base.protocols import DataSource, ResultSink
from elspeth.core.validation.base import ConfigurationError
from elspeth.core.base.plugin_context import PluginContext
```

#### With Backward Compatibility (Migration Period)
```python
# In core/__init__.py during migration:
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.sink import sink_registry
from elspeth.core.base.protocols import DataSource, ResultSink
from elspeth.core.validation.base import ConfigurationError
from elspeth.core.base.plugin_context import PluginContext

# Re-export at old locations
import sys
sys.modules['elspeth.core.llm_registry'] = sys.modules['elspeth.core.registries.llm']
sys.modules['elspeth.core.sink_registry'] = sys.modules['elspeth.core.registries.sink']
# ... etc for all moved modules

# Or use simpler approach:
# Create stub files that import and re-export from new locations
```

---

## Migration Strategy

### Phase 1: Preparation
1. **Document current structure** (this document) ✅
2. **Freeze new feature development** in core/
3. **Ensure all tests pass** and CI is green
4. **Create feature branch** `refactor/core-directory-restructure`
5. **Communicate to team** - no concurrent core/ changes

### Phase 2: Create New Structure
1. **Create new subdirectories:**
   ```bash
   mkdir -p src/elspeth/core/{registries,validation,pipeline,base,config,utils}
   ```

2. **Copy files to new locations** (don't delete originals yet)
   ```bash
   # Example:
   cp src/elspeth/core/llm_registry.py src/elspeth/core/registries/llm.py
   cp src/elspeth/core/protocols.py src/elspeth/core/base/protocols.py
   # ... etc
   ```

3. **Create `__init__.py` files** for each new subdirectory

4. **Merge registry/ subdirectory** into registries/
   ```bash
   cp src/elspeth/core/registry/*.py src/elspeth/core/registries/
   ```

### Phase 3: Backward Compatibility Layer
1. **Update new files** with correct internal imports

2. **Create compatibility shims** in old locations:
   ```python
   # src/elspeth/core/llm_registry.py (temporary compatibility shim)
   """
   DEPRECATED: This module has moved to elspeth.core.registries.llm
   This compatibility shim will be removed in v2.0.0
   """
   import warnings
   from elspeth.core.registries.llm import *  # noqa: F401, F403

   warnings.warn(
       "elspeth.core.llm_registry is deprecated, "
       "use elspeth.core.registries.llm instead",
       DeprecationWarning,
       stacklevel=2
   )
   ```

3. **Verify all tests pass** with compatibility layer

### Phase 4: Gradual Import Migration
1. **Update imports in batches** by subsystem:
   - Day 1: Update core/ internal imports
   - Day 2: Update plugins/ imports
   - Day 3: Update tests/ imports
   - Day 4: Update config.py and top-level files

2. **Run tests after each batch**

3. **Track progress** with grep:
   ```bash
   grep -r "from elspeth.core.llm_registry import" src/ tests/ --include="*.py"
   # Should show decreasing count
   ```

### Phase 5: Remove Compatibility Layer
1. **Verify all imports updated:**
   ```bash
   # Should return 0 results:
   grep -r "from elspeth.core.llm_registry import" src/ tests/ --include="*.py"
   ```

2. **Delete old files and compatibility shims**
   ```bash
   git rm src/elspeth/core/llm_registry.py
   git rm src/elspeth/core/sink_registry.py
   # ... etc
   ```

3. **Delete empty directories:**
   ```bash
   git rm -r src/elspeth/core/llm/
   git rm -r src/elspeth/core/plugins/
   git rm -r src/elspeth/core/registry/  # merged into registries/
   ```

4. **Final test suite run**

5. **Update documentation** to reflect new structure

### Phase 6: Commit and Review
1. **Create atomic commits** for each phase
2. **Write comprehensive PR description** with:
   - Rationale for restructure
   - Migration strategy used
   - Impact summary
   - Before/after structure diagrams
3. **Request review** from team
4. **Address feedback**
5. **Merge to main**

---

## Alternative: Incremental Migration

Instead of all-at-once, migrate one subsystem at a time:

### Iteration 1: Registries
- Move all `*_registry.py` to `registries/`
- Merge `registry/` infrastructure
- Update ~44 imports
- Test and stabilize

### Iteration 2: Validation
- Move validation files to `validation/`
- Update ~54 imports
- Test and stabilize

### Iteration 3: Base Protocols
- Move protocols, types, schema, plugin_context to `base/`
- Update ~98 imports
- Test and stabilize

### Iteration 4: Pipeline
- Move orchestration files to `pipeline/`
- Update ~6 imports
- Test and stabilize

### Iteration 5: Config & Utils
- Move config and utility files
- Update ~4 imports
- Test and stabilize

**Benefits:**
- Lower risk per iteration
- Easier to rollback if problems
- Can pause between iterations
- Smaller code reviews

**Drawbacks:**
- Longer overall timeline
- Temporary inconsistency
- More PRs to manage

---

## Risks and Mitigations

### Risk 1: Breaking Changes
**Impact:** Import errors, test failures, production issues
**Probability:** Medium-High (205 imports to update)
**Mitigation:**
- Use backward compatibility layer during migration
- Comprehensive test suite verification at each step
- Automated grep-based verification of import updates
- Deprecation warnings to catch missed imports

### Risk 2: Git History Disruption
**Impact:** Harder to track file history with `git blame`
**Probability:** High (files will move)
**Mitigation:**
- Use `git mv` for moves (preserves history)
- Document moves in commit messages
- Use `git log --follow` to track renamed files
- Create mapping document: old path → new path

### Risk 3: Merge Conflicts
**Impact:** Difficult merges if other work in progress
**Probability:** High (touches many files)
**Mitigation:**
- Coordinate with team - freeze core/ changes during migration
- Do migration on dedicated branch
- Minimize time window between start and merge
- Communicate clearly about migration timeline

### Risk 4: Documentation Lag
**Impact:** Docs out of sync with code
**Probability:** Medium
**Mitigation:**
- Update docs as part of migration (not after)
- Include doc updates in PR checklist
- Review docs specifically in PR review
- Auto-generate structure diagrams if possible

### Risk 5: Incomplete Migration
**Impact:** Mixed old/new imports, inconsistent structure
**Probability:** Medium
**Mitigation:**
- Automated grep-based verification
- CI check for deprecated imports
- Comprehensive checklist
- Don't remove compatibility layer until 100% verified

### Risk 6: Performance Impact
**Impact:** Import overhead from additional nesting
**Probability:** Very Low (Python caches imports)
**Mitigation:**
- Measure import times before/after
- Profile if concerns arise
- Python import caching makes this negligible

---

## Decision: Defer Until Post-PR#4

### Rationale

1. **Recent Major Refactoring:**
   - Just completed plugin split (29 new files, 44 files changed)
   - PR #4 currently in CI/CD pipeline
   - Need to stabilize before next major change

2. **Risk Accumulation:**
   - Stacking refactorings increases merge conflict risk
   - Harder to isolate issues if problems arise
   - Team bandwidth for reviews

3. **Timing:**
   - Better to wait for clean main branch
   - Allow PR #4 to merge and soak
   - Verify no regressions from plugin split

4. **Minimal Cleanup Sufficient:**
   - Deleting empty dirs addresses immediate confusion
   - Full restructure is quality-of-life, not critical
   - Can proceed with current structure

### Immediate Actions (Minimal Cleanup)

**To be done after PR #4 merges:**

1. Delete `src/elspeth/core/llm/` (empty directory)
2. Delete `src/elspeth/core/plugins/` (empty directory)
3. Delete `src/elspeth/core/registry.py` facade
4. Update 2 imports that use the facade
5. Add comments to core-level files explaining grouping
6. Document current structure in architecture docs

**Commands:**
```bash
# After PR #4 merges:
git checkout main
git pull
git checkout -b cleanup/remove-empty-core-dirs

rm -rf src/elspeth/core/llm/
rm -rf src/elspeth/core/plugins/
git rm src/elspeth/core/registry.py

# Update imports in:
# - src/elspeth/plugins/experiments/prompt_variants.py
# - src/elspeth/plugins/experiments/validation.py

git add -A
git commit -m "cleanup: Remove empty core/ directories and unused registry facade"
pytest
git push
```

### Future Actions (Full Restructure)

**When to revisit:**
- After PR #4 is merged and stable (1-2 weeks)
- No other major refactorings in progress
- Team has bandwidth for large code review
- Consider for v2.0.0 milestone as breaking change window

**Prerequisites:**
- Green CI/CD on main
- No pending core/ changes
- Team alignment on timing
- Dedicated sprint/milestone for refactoring

---

## Appendix A: File Inventory

### Complete File Listing with Sizes

```
src/elspeth/core/
├── __init__.py                      304 bytes
├── artifact_pipeline.py              15K
├── artifacts.py                     1.4K
├── config_schema.py                 1.8K
├── config_validation.py             9.3K
├── datasource_registry.py           6.2K
├── env_helpers.py                   2.0K
├── llm_middleware_registry.py       3.7K
├── llm_registry.py                  8.5K
├── logging.py                        14K
├── orchestrator.py                  6.9K
├── plugin_context.py                5.3K
├── processing.py                    1.1K
├── protocols.py                     8.9K
├── registry.py                       11K
├── schema.py                         18K
├── sink_registry.py                  18K
├── types.py                          13K
├── utility_plugin_registry.py       2.2K
├── validation_base.py               7.6K
└── validation.py                     31K

Total: 21 files, ~185KB
```

### Subdirectory Inventory

```
controls/
├── __init__.py
├── cost_tracker.py
├── cost_tracker_registry.py
├── rate_limit.py
├── rate_limiter_registry.py
└── registry.py
Total: 6 files

experiments/
├── __init__.py
├── config.py
├── config_merger.py
├── experiment_registries.py
├── plugin_registry.py
├── runner.py
├── suite_runner.py
└── tools.py
Total: 8 files

llm/
└── __pycache__/
Total: 0 files (EMPTY)

plugins/
└── __pycache__/
Total: 0 files (EMPTY)

prompts/
├── __init__.py
├── jinja_renderer.py
└── sanitization.py
Total: 3 files

registry/
├── __init__.py
├── base.py
├── context_utils.py
├── plugin_helpers.py
└── schemas.py
Total: 5 files

security/
├── __init__.py
├── approved_endpoints.py
├── pii_validators.py
├── secure_mode.py
└── signing.py
Total: 5 files
```

---

## Appendix B: Import Pattern Analysis

### Grep Commands Used

```bash
# Count imports for each module
for module in llm_registry sink_registry llm_middleware_registry \
              datasource_registry utility_plugin_registry protocols \
              types validation validation_base artifact_pipeline \
              plugin_context schema logging env_helpers \
              config_schema config_validation; do
    count=$(grep -r "from elspeth.core.$module import" src/ tests/ \
            --include="*.py" 2>/dev/null | wc -l)
    echo "$module: $count imports"
done

# Find files importing from facade
grep -r "from elspeth.core.registry import" src/ tests/ \
     --include="*.py" | grep -v "^src/elspeth/core/registry"

# Results:
# src/elspeth/plugins/experiments/prompt_variants.py
# src/elspeth/plugins/experiments/validation.py
```

### Most-Imported Modules

```
1. protocols.py         - 50 imports (cross-cutting concern)
2. validation_base.py   - 37 imports (error handling)
3. plugin_context.py    - 34 imports (plugin system)
4. validation.py        - 17 imports (config validation)
5. llm_registry.py      - 15 imports (LLM client creation)
```

**Insight:** These high-impact modules require careful migration planning and comprehensive testing.

---

## Appendix C: Related Documentation

### Documents to Update

1. **Architecture Diagrams:**
   - `docs/architecture/README.md` - Update component diagrams
   - `docs/architecture/plugin-catalogue.md` - Update import examples
   - `docs/architecture/data-flow-orchestration.md` - Update flow diagrams

2. **Developer Guides:**
   - `CLAUDE.md` - Update import patterns in examples
   - `CONTRIBUTING.md` - Update project structure overview
   - `docs/development/` - Update any import examples

3. **API Documentation:**
   - Module docstrings for moved files
   - Cross-references between old and new locations
   - Migration guide for external consumers (if any)

### New Documentation to Create

1. **Migration Guide:**
   - Old import → New import mapping table
   - Common migration patterns
   - Troubleshooting import errors

2. **Architecture Decision Record (ADR):**
   - Why we restructured
   - Alternatives considered
   - Trade-offs made
   - Expected benefits

3. **Structure Map:**
   - Visual diagram of new structure
   - Responsibility of each subdirectory
   - Cross-cutting concerns diagram

---

## Appendix D: Validation Checklist

### Pre-Migration Checklist
- [ ] All tests passing on main branch
- [ ] No pending PRs touching core/
- [ ] Team notified of upcoming migration
- [ ] Backup branch created
- [ ] This proposal reviewed and approved
- [ ] Migration timeline agreed
- [ ] Rollback plan documented

### During Migration Checklist
- [ ] New directories created
- [ ] Files copied to new locations
- [ ] `__init__.py` files created
- [ ] Backward compatibility shims created
- [ ] Internal imports updated in new files
- [ ] Tests pass with compatibility layer
- [ ] Imports updated in batches
- [ ] Tests pass after each batch
- [ ] All old imports eliminated
- [ ] Compatibility layer removed
- [ ] Old files deleted
- [ ] Empty directories deleted

### Post-Migration Checklist
- [ ] All tests passing
- [ ] No deprecation warnings
- [ ] Documentation updated
- [ ] Architecture diagrams updated
- [ ] Example code updated
- [ ] PR description complete
- [ ] Code review completed
- [ ] CI/CD green
- [ ] Merged to main
- [ ] Post-merge verification

---

## Appendix E: Team Communication Template

### Initial Announcement

```
Subject: Proposal: Core Directory Restructure (Feedback Requested)

Team,

I've completed an analysis of our core/ directory structure and identified
opportunities for improvement. The full proposal is in:
docs/roadmap/CORE_DIRECTORY_RESTRUCTURE_PROPOSAL.md

TL;DR:
- Current state: 21 files at core/ root, 2 empty directories
- Impact: 205 import statements would need updates
- Proposal: Reorganize into logical subdirectories
- Recommendation: Defer until after PR #4 stabilizes

I'd like feedback on:
1. Is the proposed structure an improvement?
2. Are there alternative groupings to consider?
3. What's the right timing for this work?
4. Should we do incremental or all-at-once migration?

Please review and provide feedback by [DATE].

Thanks!
```

### Migration Kickoff

```
Subject: Starting Core Directory Restructure Migration

Team,

We're beginning the core directory restructure as discussed.

Timeline:
- Week 1: Create new structure + compatibility layer
- Week 2: Update imports in batches
- Week 3: Remove compatibility layer, finalize
- Target merge: [DATE]

⚠️ Important: Please avoid making changes to core/ during this period
to minimize merge conflicts.

If you have urgent core/ changes:
1. Coordinate with me first
2. We can pause migration to accommodate
3. Or apply changes to migration branch

Progress updates: Daily standup + Slack #engineering

Migration branch: refactor/core-directory-restructure
Tracking doc: [LINK]

Questions? Ping me anytime.
```

---

## Conclusion

This proposal documents a comprehensive plan to reorganize the `src/elspeth/core/` directory from 21 root-level files into a logical subdirectory structure. While the full restructure would improve code organization and navigability, it carries significant risk (205 import updates) and should be deferred until after the current plugin-split refactoring (PR #4) stabilizes.

**Immediate action:** Minimal cleanup (delete empty directories) after PR #4 merges.

**Future consideration:** Full restructure as part of v2.0.0 or during a dedicated refactoring sprint.

This document serves as the reference for that future work, eliminating the need to reinvent the wheel when we're ready to proceed.

---

**Document Metadata:**
- **Author:** Analysis generated 2025-10-17
- **Status:** Proposal (Deferred)
- **Related PRs:** #4 (plugin-split)
- **Related Issues:** N/A
- **Next Review:** After PR #4 merges + 2 weeks stabilization
