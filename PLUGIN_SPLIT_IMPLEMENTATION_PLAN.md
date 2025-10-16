# Plugin Architecture Refactoring - Implementation Plan

## Problem Statement

Two monolithic plugin files violate the core principle of the plugin architecture:
- **metrics.py** - 3,008 lines, 21 plugin classes
- **middleware.py** - 1,429 lines, 6 middleware classes

The entire point of the plugin system is **one file per plugin**.

---

## Scope

### Phase 1: Experiment Plugins (metrics.py → 21 files)

**Current State:** `src/elspeth/plugins/experiments/metrics.py` (3,008 lines, 21 classes)

**Target Structure:**
```
src/elspeth/plugins/experiments/
├── __init__.py                          # Re-export all plugins
├── row/                                 # Row-level plugins (1 file)
│   ├── __init__.py
│   └── score_extractor.py               # ScoreExtractorPlugin
├── aggregators/                         # Aggregator plugins (13 files)
│   ├── __init__.py
│   ├── score_stats.py                   # ScoreStatsAggregator
│   ├── score_recommendation.py          # ScoreRecommendationAggregator
│   ├── score_variant_ranking.py         # ScoreVariantRankingAggregator
│   ├── score_agreement.py               # ScoreAgreementAggregator
│   ├── score_power.py                   # ScorePowerAggregator
│   ├── score_distribution.py            # ScoreDistributionAggregator
│   ├── cost_summary.py                  # CostSummaryAggregator
│   ├── latency_summary.py               # LatencySummaryAggregator
│   ├── rationale_analysis.py            # RationaleAnalysisAggregator
│   ├── outlier_detection.py             # OutlierDetectionAggregator
│   ├── score_flip_analysis.py           # ScoreFlipAnalysisAggregator
│   ├── category_effects.py              # CategoryEffectsAggregator
│   └── criteria_effects.py              # CriteriaEffectsBaselinePlugin (NOTE: misnamed, actually aggregator)
└── baseline/                            # Baseline comparison plugins (7 files)
    ├── __init__.py
    ├── score_delta.py                   # ScoreDeltaBaselinePlugin
    ├── score_cliffs_delta.py            # ScoreCliffsDeltaPlugin
    ├── score_assumptions.py             # ScoreAssumptionsBaselinePlugin
    ├── score_practical.py               # ScorePracticalBaselinePlugin
    ├── score_significance.py            # ScoreSignificanceBaselinePlugin
    ├── score_bayesian.py                # ScoreBayesianBaselinePlugin
    └── referee_alignment.py             # RefereeAlignmentBaselinePlugin
```

**Registry Updates:**
- Each plugin file contains its own `@register_*_plugin` decorator call
- `src/elspeth/plugins/experiments/__init__.py` imports all plugin modules to trigger registration
- **No changes to registry API** - plugins self-register on import

### Phase 2: Middleware Plugins (middleware.py → 6 files)

**Current State:** `src/elspeth/plugins/nodes/transforms/llm/middleware.py` (1,429 lines, 6 classes)

**Target Structure:**
```
src/elspeth/plugins/nodes/transforms/llm/
├── __init__.py                          # Re-export all middleware
├── middleware/                          # NEW directory for middleware plugins
│   ├── __init__.py
│   ├── audit.py                         # AuditMiddleware
│   ├── prompt_shield.py                 # PromptShieldMiddleware
│   ├── health_monitor.py                # HealthMonitorMiddleware
│   ├── azure_content_safety.py          # AzureContentSafetyMiddleware (NOTE: already exists in middleware_azure.py)
│   ├── pii_shield.py                    # PIIShieldMiddleware
│   └── classified_material.py           # ClassifiedMaterialMiddleware
└── middleware_azure.py                  # KEEP - may have different implementation
```

**Note:** `middleware_azure.py` already exists (12KB). Need to check if `AzureContentSafetyMiddleware` is duplicated.

**Registry Updates:**
- Each middleware file contains its own `register_middleware()` call
- `src/elspeth/plugins/nodes/transforms/llm/__init__.py` imports all middleware modules
- **No changes to registry API**

---

## Implementation Strategy

### Step 1: Create Directory Structure
```bash
# Phase 1 - Experiment plugins
mkdir -p src/elspeth/plugins/experiments/row
mkdir -p src/elspeth/plugins/experiments/aggregators
mkdir -p src/elspeth/plugins/experiments/baseline

# Phase 2 - Middleware plugins
mkdir -p src/elspeth/plugins/nodes/transforms/llm/middleware
```

### Step 2: Extract Plugins

**For each plugin:**
1. Create new file in appropriate subdirectory
2. Copy imports from metrics.py/middleware.py (minimal set)
3. Copy schema constants (e.g., `_ROW_SCHEMA`, `_AUDIT_SCHEMA`)
4. Copy class implementation
5. Copy registration call (`register_*_plugin()` or `register_middleware()`)
6. Add to `__all__` export list

**File Template (Experiment Plugin):**
```python
"""<Plugin Name> - <brief description>."""

from __future__ import annotations

import <required_imports>

from elspeth.core.experiments.plugin_registry import register_<type>_plugin
from elspeth.core.plugin_context import PluginContext

logger = logging.getLogger(__name__)

_SCHEMA = {
    # Schema definition
}


class PluginClass:
    """Plugin implementation."""
    # ... implementation ...


register_<type>_plugin(
    "plugin_name",
    lambda options, context: PluginClass(**options),
    schema=_SCHEMA,
)


__all__ = ["PluginClass"]
```

**File Template (Middleware):**
```python
"""<Middleware Name> - <brief description>."""

from __future__ import annotations

import <required_imports>

from elspeth.core.llm_middleware_registry import register_middleware
from elspeth.core.protocols import LLMMiddleware, LLMRequest

logger = logging.getLogger(__name__)

_SCHEMA = {
    # Schema definition
}


class MiddlewareClass(LLMMiddleware):
    """Middleware implementation."""
    name = "middleware_name"
    # ... implementation ...


register_middleware(
    "middleware_name",
    lambda options, context: MiddlewareClass(**options),
    schema=_SCHEMA,
)


__all__ = ["MiddlewareClass"]
```

### Step 3: Update Package `__init__.py` Files

**`src/elspeth/plugins/experiments/__init__.py`:**
```python
"""Experiment plugins for row-level, aggregation, and baseline comparison."""

# Import all plugin modules to trigger registration
from elspeth.plugins.experiments import early_stop, prompt_variants, validation
from elspeth.plugins.experiments.aggregators import (
    category_effects,
    cost_summary,
    criteria_effects,
    latency_summary,
    outlier_detection,
    rationale_analysis,
    score_agreement,
    score_distribution,
    score_flip_analysis,
    score_power,
    score_recommendation,
    score_stats,
    score_variant_ranking,
)
from elspeth.plugins.experiments.baseline import (
    referee_alignment,
    score_assumptions,
    score_bayesian,
    score_cliffs_delta,
    score_delta,
    score_practical,
    score_significance,
)
from elspeth.plugins.experiments.row import score_extractor

__all__ = [
    # Keep existing exports for backward compatibility
    # but everything now comes from submodules
]
```

**`src/elspeth/plugins/nodes/transforms/llm/__init__.py`:**
```python
"""LLM transform plugins including middleware."""

from elspeth.plugins.nodes.transforms.llm import azure_openai, mock, openai_http, static
from elspeth.plugins.nodes.transforms.llm.middleware import (
    audit,
    azure_content_safety,
    classified_material,
    health_monitor,
    pii_shield,
    prompt_shield,
)

__all__ = [
    # Exports
]
```

### Step 4: Deprecate Old Files

**DO NOT DELETE** `metrics.py` and `middleware.py` immediately. Instead:

1. **Empty implementation, re-export from new locations:**
```python
"""DEPRECATED: Use individual plugin modules instead.

This module is kept for backward compatibility only.
All plugins have been moved to subdirectories.
"""

from elspeth.plugins.experiments.aggregators.score_stats import ScoreStatsAggregator
from elspeth.plugins.experiments.baseline.score_delta import ScoreDeltaBaselinePlugin
from elspeth.plugins.experiments.row.score_extractor import ScoreExtractorPlugin
# ... (re-export all 21 classes)

__all__ = [
    "ScoreStatsAggregator",
    "ScoreDeltaBaselinePlugin",
    "ScoreExtractorPlugin",
    # ... all 21 classes
]
```

2. **Add deprecation warning at top of file:**
```python
import warnings

warnings.warn(
    "elspeth.plugins.experiments.metrics is deprecated. "
    "Import individual plugins from their subdirectories instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

3. **Mark for removal in future version:**
```python
# TODO(v2.0): Remove this compatibility module
```

### Step 5: Update Tests

**No test changes required** if:
- Tests use registry factory methods (`create_row_plugin("score_extractor")`)
- Tests import from main package (`from elspeth.plugins.experiments import ...`)

**Test changes required** if:
- Direct imports from `metrics.py`: `from elspeth.plugins.experiments.metrics import ScoreExtractorPlugin`
- Update to: `from elspeth.plugins.experiments.row.score_extractor import ScoreExtractorPlugin`
- Or better: Use registry factory

**Search for direct imports:**
```bash
grep -r "from elspeth.plugins.experiments.metrics import" tests/
grep -r "from elspeth.plugins.nodes.transforms.llm.middleware import" tests/
```

### Step 6: Verify Registration

After extraction, verify all plugins are still registered:

```python
# Test script: verify_plugin_registration.py
from elspeth.core.experiments.plugin_registry import _row_plugins, _aggregation_plugins, _baseline_plugins
from elspeth.core.llm_middleware_registry import _middleware_registry

# Force import all plugin modules
import elspeth.plugins.experiments
import elspeth.plugins.nodes.transforms.llm

print("Row plugins:", sorted(_row_plugins.keys()))
print("Aggregation plugins:", sorted(_aggregation_plugins.keys()))
print("Baseline plugins:", sorted(_baseline_plugins.keys()))
print("Middleware:", sorted(_middleware_registry.keys()))
```

Expected output:
```
Row plugins: ['noop', 'rag_query', 'score_extractor']
Aggregation plugins: ['category_effects', 'cost_summary', 'latency_summary', 'outlier_detection', 'rationale_analysis', 'score_agreement', 'score_distribution', 'score_flip_analysis', 'score_power', 'score_recommendation', 'score_stats', 'score_variant_ranking']
Baseline plugins: ['criteria_effects', 'referee_alignment', 'row_count_comparison', 'score_assumptions', 'score_bayesian', 'score_cliffs_delta', 'score_delta', 'score_practical', 'score_significance']
Middleware: ['audit_logger', 'azure_content_safety', 'classified_material', 'health_monitor', 'pii_shield', 'prompt_shield']
```

---

## Execution Order

### Phase 1: Experiment Plugins (21 files)

**Priority Order:**
1. **Row plugins** (1 file) - simplest, single class
2. **Aggregators** (13 files) - medium complexity
3. **Baseline** (7 files) - most complex (statistical tests)

**Per-plugin checklist:**
- [ ] Create file in correct subdirectory
- [ ] Copy minimal imports (remove unused)
- [ ] Copy schema constant
- [ ] Copy class implementation
- [ ] Copy registration call
- [ ] Add to `__all__`
- [ ] Update subdirectory `__init__.py`
- [ ] Run tests for that plugin type

### Phase 2: Middleware Plugins (6 files)

**Priority Order:**
1. **audit.py** - simplest, logging only
2. **prompt_shield.py** - simple text matching
3. **health_monitor.py** - metrics collection
4. **pii_shield.py** - complex patterns + validation (largest, ~570 lines)
5. **classified_material.py** - complex fuzzy matching (~520 lines)
6. **azure_content_safety.py** - external API call (check duplication with middleware_azure.py)

**Per-middleware checklist:**
- [ ] Check if already exists in `middleware_azure.py` (avoid duplication)
- [ ] Create file in `middleware/` subdirectory
- [ ] Copy minimal imports
- [ ] Copy schema constant
- [ ] Copy class implementation
- [ ] Copy registration call
- [ ] Add to `__all__`
- [ ] Update `middleware/__init__.py`
- [ ] Run middleware tests

### Phase 3: Cleanup & Verification

- [ ] Update main package `__init__.py` files
- [ ] Convert `metrics.py` to re-export module with deprecation warning
- [ ] Convert `middleware.py` to re-export module with deprecation warning
- [ ] Run full test suite: `python -m pytest`
- [ ] Verify registration script shows all plugins
- [ ] Update `docs/architecture/plugin-catalogue.md` with new file paths
- [ ] Commit changes

---

## Risk Mitigation

### Import Cycle Prevention

**Risk:** Circular imports between plugin modules and registry

**Mitigation:**
- Keep registration in each plugin file (not centralized)
- Import registry functions, not plugin classes
- Use `TYPE_CHECKING` guard for protocol imports

### Shared Utilities

**Risk:** Multiple plugins share utility functions from metrics.py

**Current shared code to identify:**
```bash
grep -E "^def _" src/elspeth/plugins/experiments/metrics.py
```

**Mitigation:**
- Extract shared utilities to `src/elspeth/plugins/experiments/_utils.py`
- Import from utils in each plugin
- Prefix with `_` to mark as internal

### Test Breakage

**Risk:** Direct imports from `metrics.py` in tests

**Mitigation:**
- Search for direct imports before starting
- Update imports to use registry or new locations
- Keep backward-compatibility re-exports

### Registration Timing

**Risk:** Plugins not registered if module not imported

**Mitigation:**
- Ensure all plugin modules imported in package `__init__.py`
- Verify with registration check script
- Add test that checks all expected plugins are registered

---

## Rollback Plan

If issues discovered after merge:

1. **Immediate:** Revert the commit that split plugins
2. **Investigation:** Identify which plugin(s) caused issues
3. **Incremental Fix:** Re-split plugins in smaller batches
4. **Verification:** Enhanced registration tests before merge

---

## Dependencies to Extract

### metrics.py Shared Code

```bash
# Search for module-level helper functions
grep -E "^def [^_]" src/elspeth/plugins/experiments/metrics.py

# Search for private helper functions (may be shared)
grep -E "^def _" src/elspeth/plugins/experiments/metrics.py
```

**Action:** If shared functions exist, extract to `_utils.py` or `_stats_helpers.py`

### middleware.py Shared Code

```bash
# Search for shared patterns, validators, regex
grep -E "^[A-Z_]+\s*=" src/elspeth/plugins/nodes/transforms/llm/middleware.py | head -20
```

**PIIShieldMiddleware** has:
- `STRONG_TOKENS` (class variable)
- `SUPPRESSION_PATTERNS` (class variable)
- `DEFAULT_PATTERNS` (class variable)

**ClassifiedMaterialMiddleware** has:
- `DEFAULT_MARKINGS` (class variable)
- `OPTIONAL_LOW_SIGNAL` (class variable)
- `HOMOGLYPHS` (dict)
- `REL_TO_CANON` (dict)
- `REGEX_PATTERNS` (dict)

**Action:** These are class variables, so they move with their classes (no extraction needed).

---

## Testing Strategy

### Unit Tests
- Existing tests should pass unchanged (use registry)
- Add test to verify all plugins registered

### Integration Tests
- Run sample suite: `make sample-suite`
- Verify outputs match baseline

### Import Tests
```python
def test_all_experiment_plugins_registered():
    """Verify all 21 experiment plugins are registered."""
    from elspeth.core.experiments.plugin_registry import (
        _row_plugins,
        _aggregation_plugins,
        _baseline_plugins,
    )

    # Force import to trigger registration
    import elspeth.plugins.experiments

    assert "score_extractor" in _row_plugins
    assert "score_stats" in _aggregation_plugins
    assert "score_delta" in _baseline_plugins
    # ... check all 21
```

---

## Success Criteria

- [ ] All 21 experiment plugins in separate files
- [ ] All 6 middleware in separate files
- [ ] Full test suite passes (696 tests)
- [ ] Sample suite runs without errors
- [ ] Backward compatibility maintained (old imports still work with deprecation warnings)
- [ ] Documentation updated with new file paths
- [ ] No performance regression (registration timing)

---

## Estimated Effort

**Phase 1 (Experiment Plugins):**
- File creation: 21 files × 5 min = 105 minutes
- Testing: 30 minutes
- **Total: ~2.5 hours**

**Phase 2 (Middleware):**
- File creation: 6 files × 10 min = 60 minutes (larger files)
- Duplication check: 15 minutes
- Testing: 20 minutes
- **Total: ~1.5 hours**

**Phase 3 (Cleanup):**
- Package updates: 20 minutes
- Deprecation warnings: 15 minutes
- Full test suite: 10 minutes
- Documentation: 30 minutes
- **Total: ~1.5 hours**

**Grand Total: ~5.5 hours**

---

## Open Questions

1. **CriteriaEffectsBaselinePlugin misnamed?**
   - Located in metrics.py with baseline plugins
   - Name suggests baseline comparison
   - Need to verify: Is this actually an aggregator or baseline plugin?
   - **Action:** Check usage in tests/configs before placement

2. **Azure Content Safety duplication?**
   - `middleware.py` has `AzureContentSafetyMiddleware` (1,429 lines file)
   - `middleware_azure.py` exists (12KB)
   - **Action:** Check if implementations differ or are duplicates
   - If duplicates: Keep one, remove other
   - If different: Rename for clarity

3. **Shared dependencies extraction timing?**
   - Should `_utils.py` be created before or during plugin extraction?
   - **Recommendation:** During - extract when second plugin needs same function

4. **Backward compatibility period?**
   - How long to keep deprecated re-export modules?
   - **Recommendation:** Until v2.0 (based on TODO pattern in codebase)

---

## Next Steps After Approval

1. Create feature branch: `refactor/plugin-architecture-split`
2. Execute Phase 1 (experiment plugins)
3. Commit after each subdirectory (row, aggregators, baseline)
4. Execute Phase 2 (middleware)
5. Execute Phase 3 (cleanup)
6. Run full test suite
7. Create PR with detailed testing notes
8. After merge: Monitor for issues, update docs site

---

**Ready for Review**
