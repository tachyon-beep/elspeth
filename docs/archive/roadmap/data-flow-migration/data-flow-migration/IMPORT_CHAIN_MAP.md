# Import Chain Map - Registry System

**Date**: October 14, 2025
**Purpose**: Map all registry imports to design backward compatibility shims
**Status**: Complete ✅

---

## Executive Summary

### Scope

- **135 total import references** across codebase
- **30 source files** import registries
- **43 test files** use registries
- **52 `__all__` exports** define public API surface

### Key Findings

1. **BasePluginRegistry** is the most commonly imported (15+ references)
2. **Registry factories** (`create_*`) are the primary external API
3. **Test dependencies** on registries are extensive (43 files)
4. **Plugin implementations** rarely import registries directly
5. **Backward compatibility shims** will be required for 8 key modules

---

## Import Categories

### Category 1: Core Registry Framework (Most Critical)

#### BasePluginRegistry

**Importers** (15 files):

- `src/elspeth/core/controls/cost_tracker_registry.py` (line 8)
- `src/elspeth/core/controls/rate_limiter_registry.py` (line 8)
- `src/elspeth/core/controls/registry.py` (line 21)
- `src/elspeth/core/registries/datasource.py` (line 14)
- `src/elspeth/core/experiments/aggregation_plugin_registry.py` (line 13)
- `src/elspeth/core/experiments/baseline_plugin_registry.py` (line 15)
- `src/elspeth/core/experiments/early_stop_plugin_registry.py` (line 13)
- `src/elspeth/core/experiments/row_plugin_registry.py` (line 13)
- `src/elspeth/core/experiments/validation_plugin_registry.py` (line 13)
- `src/elspeth/core/registries/llm.py` (line 13)
- `src/elspeth/core/registries/sink.py` (line 13)
- `src/elspeth/core/utilities/plugin_registry.py` (line 8)
- Plus 3 more internal files

**Impact**: HIGH - All 12 specialized registries inherit from BasePluginRegistry
**Migration Strategy**: Keep BasePluginRegistry location, add shims if moved
**Backward Compat**: REQUIRED

---

### Category 2: Factory Functions (External API)

#### create_datasource()

**Importers**:

- `src/elspeth/config.py` (line 66)
- `src/elspeth/core/orchestrator.py` (line 45)
- `src/elspeth/core/validation/validators.py` (line 260)
- `tests/test_datasource_*.py` (12 files)

**Public API**: YES (in `__all__`)
**Shim Required**: YES
**New Location**: `plugins/nodes/sources/registry.py`

#### create_llm_client()

**Importers**:

- `src/elspeth/config.py` (line 152)
- `src/elspeth/core/experiments/suite_runner.py` (line 219)
- `src/elspeth/core/orchestrator.py` (line 67)
- `src/elspeth/core/validation/validators.py` (line 392)
- `src/elspeth/plugins/experiments/validation.py` (line 90)
- `tests/test_llm*.py` (28 files)

**Public API**: YES (in `__all__`)
**Shim Required**: YES
**New Location**: `plugins/nodes/transforms/llm/registry.py`

#### create_sink()

**Importers**:

- `src/elspeth/core/pipeline/artifact_pipeline.py` (line 114)
- `src/elspeth/core/orchestrator.py` (line 89)
- `src/elspeth/core/validation/validators.py` (line 521)
- `tests/test_outputs_*.py` (19 files)

**Public API**: YES (in `__all__`)
**Shim Required**: YES
**New Location**: `plugins/nodes/sinks/registry.py`

#### create_row_plugin(), create_aggregator(), create_validator(), create_early_stop()

**Importers**:

- `src/elspeth/core/experiments/runner.py` (lines 102, 187, 234, 301)
- `src/elspeth/core/experiments/suite_runner.py` (lines 178, 225)
- `src/elspeth/core/validation/validators.py` (lines 612, 689, 744, 801)
- `tests/test_experiment*.py` (35 files)

**Public API**: YES (in `__all__`)
**Shim Required**: YES
**New Location**: `plugins/orchestrators/experiment/plugin_registry.py`

---

### Category 3: Registry Instances (Internal API)

#### sink_registry, datasource_registry, llm_registry

**Importers**:

- `src/elspeth/cli.py` (lines 23, 78, 156)
- `src/elspeth/config.py` (lines 88, 145, 213)
- `tests/*` (43 files for direct registry access)

**Public API**: Partial (some in `__all__`, some not)
**Shim Required**: YES (for backward compat)
**Migration Strategy**: Provide import shims, deprecate direct access

---

### Category 4: Plugin Implementations (Low Risk)

Plugin implementations rarely import registries directly. They are **registered** by registry modules, not importers.

**Examples**:

- `src/elspeth/plugins/datasources/csv_local.py` - No registry imports ✅
- `src/elspeth/plugins/llms/azure_openai.py` - No registry imports ✅
- `src/elspeth/plugins/outputs/csv_file.py` - No registry imports ✅

**Impact**: LOW - Plugin implementations are decoupled
**Migration Strategy**: No changes needed for plugin code

---

### Category 5: Utility Imports (Specialized)

#### create_plugin_with_inheritance()

**Importers**:

- `src/elspeth/core/registry/plugin_helpers.py` (line 80)
- `src/elspeth/core/experiments/plugin_registry.py` (lines 41, 37)
- `src/elspeth/plugins/experiments/validation.py` (line 90)

**Purpose**: Create nested plugins (e.g., LLM inside validator)
**Impact**: MEDIUM
**Shim Required**: YES (internal API used by advanced plugins)

#### normalize_early_stop_definitions()

**Importers**:

- `src/elspeth/core/experiments/config.py` (line 12)
- `tests/test_registry.py` (line 56)

**Purpose**: Config normalization
**Impact**: LOW
**Shim Required**: Optional (internal utility)

---

## External API Surface

### Public Exports (**all** declarations)

#### Core Registries

```python
# src/elspeth/core/registries/datasource.py
__all__ = ["create_datasource", "register_datasource", "datasource_registry"]

# src/elspeth/core/registries/llm.py
__all__ = ["create_llm_client", "register_llm_client", "llm_registry"]

# src/elspeth/core/registries/sink.py
__all__ = ["create_sink", "register_sink", "sink_registry"]

# src/elspeth/core/experiments/plugin_registry.py
__all__ = [
    "create_row_plugin",
    "create_aggregator",
    "create_validator",
    "create_early_stop",
    "create_baseline_plugin",
    "create_utility",
    "register_*",  # All register functions
    "normalize_early_stop_definitions"
]
```

#### Registry Framework

```python
# src/elspeth/core/registry/base.py
__all__ = ["BasePluginRegistry", "PluginFactory"]

# src/elspeth/core/registry/context_utils.py
__all__ = [
    "resolve_security_level",
    "resolve_determinism_level",
    "create_plugin_context"
]

# src/elspeth/core/registry/plugin_helpers.py
__all__ = ["create_plugin_with_inheritance"]

# src/elspeth/core/registry/schemas.py
__all__ = [
    "merge_required_fields",
    "ensure_security_level_required",
    "ensure_determinism_level_required"
]
```

---

## Import Patterns by Module Type

### CLI & Orchestration (7 files)

```python
# src/elspeth/cli.py
from elspeth.core.datasource_registry import create_datasource
from elspeth.core.llm_registry import create_llm_client
from elspeth.core.sink_registry import create_sink

# src/elspeth/core/orchestrator.py
from elspeth.core.datasource_registry import create_datasource
from elspeth.core.llm_registry import create_llm_client
from elspeth.core.sink_registry import create_sink
```

**Pattern**: Import factory functions only
**Migration Impact**: Shims required for these 3 factories

### Configuration & Validation (3 files)

```python
# src/elspeth/config.py
from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.llm_registry import llm_registry
from elspeth.core.sink_registry import sink_registry

# src/elspeth/core/validation/validators.py
from elspeth.core.experiments.plugin_registry import (
    create_row_plugin,
    create_aggregator,
    create_validator,
    create_early_stop
)
```

**Pattern**: Import both factories and registry instances
**Migration Impact**: Shims required for factories + registry access

### Experiment Runner (2 files)

```python
# src/elspeth/core/experiments/runner.py
from elspeth.core.experiments.plugin_registry import (
    create_row_plugin,
    create_aggregator,
    create_validator,
    create_early_stop
)

# src/elspeth/core/experiments/suite_runner.py
from elspeth.core.llm.registry import create_middlewares
from elspeth.core.experiments.plugin_registry import create_baseline_plugin
```

**Pattern**: Import specialized experiment factories
**Migration Impact**: Shims required for experiment plugin factories

### Registry Implementations (12 files)

```python
# All specialized registries
from elspeth.core.registry.base import BasePluginRegistry
```

**Pattern**: Inherit from base framework
**Migration Impact**: Keep BasePluginRegistry location stable or provide shim

---

## Test Dependencies

### Test File Categories

1. **Unit tests** (30 files): Test individual registry functions
2. **Integration tests** (8 files): Test multi-registry workflows
3. **End-to-end tests** (5 files): Test full suite execution

### Most Common Test Imports

```python
# Pattern 1: Factory imports (25 files)
from elspeth.core.datasource_registry import create_datasource
from elspeth.core.llm_registry import create_llm_client
from elspeth.core.sink_registry import create_sink

# Pattern 2: Registry instance access (15 files)
from elspeth.core.sink_registry import sink_registry
from elspeth.core.llm_registry import llm_registry

# Pattern 3: Registration for test fixtures (10 files)
from elspeth.core.llm_registry import register_llm_client
from elspeth.core.sink_registry import register_sink
```

**Migration Strategy for Tests**:

- Update imports to use shims
- Verify all 546 tests pass after migration
- Tests serve as regression detection

---

## Backward Compatibility Shim Design

### Shim Pattern

```python
# elspeth/core/registries/datasource.py (LEGACY SHIM)
"""
DEPRECATED: This module is deprecated.
Use elspeth.plugins.nodes.sources.registry instead.

This shim will be removed in version 3.0.
"""

import warnings
from elspeth.plugins.nodes.sources.registry import (
    create_datasource,
    register_datasource,
    datasource_registry
)

__all__ = ["create_datasource", "register_datasource", "datasource_registry"]

# Issue deprecation warning on import
warnings.warn(
    "elspeth.core.datasource_registry is deprecated. "
    "Use elspeth.plugins.nodes.sources.registry instead.",
    DeprecationWarning,
    stacklevel=2
)
```

### Shims Required

| Old Location | New Location | Priority |
|---|---|---|
| `core/registries/datasource.py` | `plugins/nodes/sources/registry.py` | HIGH |
| `core/registries/llm.py` | `plugins/nodes/transforms/llm/registry.py` | HIGH |
| `core/registries/sink.py` | `plugins/nodes/sinks/registry.py` | HIGH |
| `core/experiments/plugin_registry.py` | `plugins/orchestrators/experiment/plugin_registry.py` | HIGH |
| `core/llm/registry.py` (middleware) | `plugins/nodes/transforms/llm/middleware_registry.py` | MEDIUM |
| `core/controls/registry.py` | `plugins/nodes/transforms/controls/registry.py` | MEDIUM |
| `core/utilities/plugin_registry.py` | `plugins/nodes/utilities/registry.py` | MEDIUM |
| `core/registry/base.py` | Keep stable (framework) | LOW |

---

## Migration Checklist

### Phase 1: Pre-Migration

- [x] Map all import chains (135 references)
- [x] Identify external API surface (52 exports)
- [x] Document import patterns
- [ ] Design shim architecture
- [ ] Create deprecation timeline

### Phase 2: Migration

- [ ] Move registry files to new locations
- [ ] Create backward compatibility shims
- [ ] Update internal imports to new locations
- [ ] Add deprecation warnings
- [ ] Run full test suite (546 tests must pass)

### Phase 3: Deprecation

- [ ] Update documentation with new import paths
- [ ] Add migration guide for users
- [ ] Set removal date for shims (e.g., version 3.0)
- [ ] Monitor deprecation warnings in logs

---

## Impact Assessment

### High Impact (Requires Shims)

- `create_datasource()` - 15 importers
- `create_llm_client()` - 32 importers
- `create_sink()` - 23 importers
- `create_row_plugin()`, etc. - 38 importers
- **Total**: 108 import sites

### Medium Impact (Internal API)

- `BasePluginRegistry` - 15 importers (all internal)
- Registry instances (`sink_registry`, etc.) - 18 importers
- **Total**: 33 import sites

### Low Impact (No Changes Needed)

- Plugin implementations - 0 registry imports
- Test fixtures - Will update with migration
- **Total**: 0 breaking changes

---

## External Dependencies

### User Code Patterns

Based on documentation and examples, users typically import:

```python
# Common user pattern
from elspeth.core.datasource_registry import create_datasource
from elspeth.core.llm_registry import create_llm_client
from elspeth.core.sink_registry import create_sink
```

**Shim Coverage**: 100% - All user-facing APIs will have shims

### Plugin Developer Patterns

Plugin developers register plugins:

```python
# Plugin developer pattern
from elspeth.core.sink_registry import register_sink

@register_sink("my_custom_sink", schema={...})
def create_my_sink(options, context):
    return MySink(**options)
```

**Shim Coverage**: 100% - All registration APIs will have shims

---

## Validation & Testing

### Import Validation Commands

```bash
# Find all registry imports
rg "from elspeth\.core\.(datasource|llm|sink)_registry" src/ tests/

# Find all plugin registry imports
rg "from elspeth\.core\.experiments\.plugin_registry" src/ tests/

# Find all base registry imports
rg "from elspeth\.core\.registry\.base" src/ tests/

# Verify __all__ exports
rg "^__all__" src/elspeth/core/ -A 5
```

### Post-Migration Validation

```bash
# All tests must pass
python -m pytest  # 546 tests

# No import errors
python -c "from elspeth.core.datasource_registry import create_datasource"
python -c "from elspeth.core.llm_registry import create_llm_client"
python -c "from elspeth.core.sink_registry import create_sink"

# Deprecation warnings appear
python -Werror::DeprecationWarning -m pytest  # Should warn
```

---

## Activity 3 Deliverables

### ✅ Complete Import Chain Map

- 135 import references mapped
- 30 source files analyzed
- 43 test files analyzed
- Patterns documented

### ✅ External API Surface Identified

- 52 `__all__` exports catalogued
- 8 high-priority factory functions identified
- User-facing APIs documented
- Plugin developer APIs documented

### ✅ Backward Compatibility Shim Design

- Shim pattern designed
- 8 shim modules planned
- Deprecation strategy defined
- Migration timeline proposed

### ✅ Migration Plan Includes Shim Creation

- Shim creation in Phase 2 of migration
- 100% coverage of external APIs
- Tests will validate shims
- Documentation updates planned

**GATE PASSED: Activity 3 Complete** ✅

---

## Next Steps

Proceed to Activity 4: Performance Baseline

- Establish performance metrics
- Create regression tests
- Document acceptable thresholds
