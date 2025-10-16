# Plugin System Deep Dive & Reorganization Proposal

**Date**: October 14, 2025
**Author**: Claude (Architectural Analysis)
**Status**: DRAFT for Review

---

## Executive Summary

The Elspeth plugin system has **significant organizational debt** that creates confusion and maintenance burden:

- **18 separate registry files** spread across the codebase
- **Mixed architectural patterns** (old monolithic, new base framework, facades)
- **Unclear boundaries** between plugin types and their purposes
- **Poor discoverability** - finding the right plugin type/registry is difficult

**Recommendation**: Reorganize around **functional plugin domains** rather than structural/technical boundaries.

---

## 1. Current State: What Exists

### 1.1 Plugin Type Inventory

Elspeth currently has **12 distinct plugin types**:

| Plugin Type | Protocol/Base Class | Registry Location | Purpose |
|-------------|---------------------|-------------------|---------|
| **DataSource** | `DataSource` (Protocol) | `core/datasource_registry.py` | Load experiment input data |
| **LLM Client** | `LLMClientProtocol` (Protocol) | `core/llm_registry.py` | Generate LLM responses |
| **LLM Middleware** | `LLMMiddleware` (Protocol) | `core/llm/registry.py` | Intercept LLM requests/responses |
| **Result Sink** | `ResultSink` (Protocol) | `core/sink_registry.py` | Persist experiment results |
| **Row Plugin** | `RowExperimentPlugin` (Protocol) | `core/experiments/row_plugin_registry.py` | Process single experiment rows |
| **Aggregation Plugin** | `AggregationExperimentPlugin` (Protocol) | `core/experiments/aggregation_plugin_registry.py` | Compute aggregates across rows |
| **Validation Plugin** | `ValidationPlugin` (Protocol) | `core/experiments/validation_plugin_registry.py` | Validate LLM responses |
| **Baseline Plugin** | `BaselineComparisonPlugin` (Protocol) | `core/experiments/baseline_plugin_registry.py` | Compare variants to baseline |
| **Early Stop Plugin** | `EarlyStopPlugin` (Protocol) | `core/experiments/early_stop_plugin_registry.py` | Trigger early experiment termination |
| **Rate Limiter** | `RateLimiter` (class) | `core/controls/rate_limiter_registry.py` | Control request rate |
| **Cost Tracker** | `CostTracker` (class) | `core/controls/cost_tracker_registry.py` | Track LLM costs |
| **Utility Plugin** | No formal protocol | `core/utilities/plugin_registry.py` | Cross-cutting utilities |

### 1.2 Registry File Proliferation

**Current registry files** (18 total):

```
core/registry.py                           # OLD monolithic registry (backward compat)
core/registry/                             # NEW base framework (Phase 2)
  ├── base.py                              # BasePluginRegistry infrastructure
  ├── context_utils.py                     # Security/context handling
  ├── plugin_helpers.py                    # create_plugin_with_inheritance()
  └── schemas.py                           # Reusable schemas

core/datasource_registry.py                # Datasource facade over BasePluginRegistry
core/llm_registry.py                       # LLM client facade
core/sink_registry.py                      # Sink facade
core/llm/registry.py                       # Middleware registry
core/controls/registry.py                  # Controls facade (rate_limiter + cost_tracker)
core/controls/rate_limiter_registry.py     # Rate limiter specific
core/controls/cost_tracker_registry.py     # Cost tracker specific
core/utilities/plugin_registry.py          # Utilities registry

core/experiments/plugin_registry.py        # Experiments FACADE (aggregates 5 registries)
core/experiments/row_plugin_registry.py    # Row plugins
core/experiments/aggregation_plugin_registry.py
core/experiments/validation_plugin_registry.py
core/experiments/baseline_plugin_registry.py
core/experiments/early_stop_plugin_registry.py
```

### 1.3 Plugin Implementation Organization

**Current directory structure**:

```
plugins/
├── datasources/         # 3 datasource implementations
├── llms/                # 7 files (clients + middleware MIXED!)
├── outputs/             # 14 sink implementations
├── experiments/         # 5 experiment plugin implementations
└── utilities/           # 1 utility (retrieval)
```

---

## 2. Problems: Why It's Confusing

### Problem 1: Registry Explosion

**Issue**: There are 18 registry-related files with unclear relationships.

**Impact**:
- New developers don't know where to find plugin registration code
- Adding a new plugin type requires touching 3-5 files
- Circular import issues between registries
- Duplicate code across facade files

**Example**: To add a new row plugin, you need to understand:
1. `BasePluginRegistry` (core/registry/base.py)
2. `row_plugin_registry` instance (core/experiments/row_plugin_registry.py)
3. `create_row_plugin()` facade (core/experiments/plugin_registry.py)
4. `register_row_plugin()` public API (core/experiments/plugin_registry.py)

### Problem 2: Mixed Concerns in `plugins/llms/`

**Issue**: The `plugins/llms/` directory contains BOTH:
- LLM clients (azure_openai.py, mock.py, openai_http.py)
- LLM middleware (middleware.py, middleware_azure.py)

**Impact**:
- Violates single responsibility principle
- Middleware is orthogonal to clients but grouped with them
- Confusing when looking for middleware vs clients

### Problem 3: Unclear Plugin Type Boundaries

**Issue**: What's the difference between:
- Row plugins vs utilities?
- Middleware vs controls?
- Sinks vs outputs?

**Current classification is inconsistent**:
- "Controls" (rate_limiter, cost_tracker) are really LLM lifecycle concerns
- "Utilities" (retrieval) could be row plugins or middleware
- "Experiments" (row/agg/validation) are all experiment lifecycle phases

### Problem 4: Facade Layering Overhead

**Issue**: Multiple layers of indirection:
```
User code
  → experiments/plugin_registry.py (facade)
    → experiments/row_plugin_registry.py (specific)
      → registry/base.py (BasePluginRegistry)
        → registry/plugin_helpers.py (create_plugin_with_inheritance)
          → Actual plugin factory
```

**Impact**:
- 5 layers to trace through
- Each layer adds error handling, type conversions, validation
- Debugging is painful

### Problem 5: Roadmap Misalignment

From `docs/FEATURE_ROADMAP.md`, future plugins will add:
- More LLM providers (Anthropic, Bedrock, Vertex AI, Cohere)
- More datasources (S3, GCS, databases)
- More middleware (OPA policy, multi-vendor moderation)
- Telemetry plugins (OpenTelemetry, Prometheus)

**Current structure doesn't support this growth well**:
- Where does telemetry middleware go? `plugins/llms/`? New directory?
- Where do AWS/GCP clients go? More files in `plugins/llms/`?
- Where do database datasources go? `plugins/datasources/`?

---

## 3. Functional Analysis: What Should the Groups Be?

### 3.1 Functional Plugin Domains

Instead of organizing by "type" (datasource, middleware, sink), organize by **functional domain**:

| Functional Domain | Purpose | Current Plugin Types Included |
|-------------------|---------|------------------------------|
| **Data Input** | Getting data into experiments | DataSource |
| **Data Output** | Persisting experiment results | ResultSink |
| **LLM Integration** | Interacting with LLM providers | LLM Client, LLM Middleware |
| **Experiment Lifecycle** | Controlling experiment execution | Row, Aggregation, Validation, Baseline, Early Stop, Rate Limiter, Cost Tracker |
| **Cross-Cutting** | Utilities used across domains | Utility plugins |

### 3.2 Why This Grouping Makes Sense

**Data Input Domain**:
- Clear purpose: "How do we get data in?"
- Single extension point: implement `DataSource`
- Future growth: S3, GCS, databases, streaming

**Data Output Domain**:
- Clear purpose: "Where do results go?"
- Single extension point: implement `ResultSink`
- Future growth: OpenTelemetry, Prometheus, PDF, SharePoint

**LLM Integration Domain**:
- Clear purpose: "How do we talk to LLMs?"
- Two extension points: clients (LLMClientProtocol) + middleware (LLMMiddleware)
- **Key insight**: Middleware and clients are BOTH about LLM integration
- Future growth: Many more providers, policy engines, moderation

**Experiment Lifecycle Domain**:
- Clear purpose: "What happens during an experiment run?"
- Multiple extension points for different lifecycle phases:
  - Pre-LLM: Rate limiting, cost estimation
  - Post-response: Row processing, validation
  - Post-experiment: Aggregation, baseline comparison
  - Cross-experiment: Early stopping
- Future growth: Fairness metrics, latency tracking, KPI reconciliation

**Cross-Cutting Domain**:
- Purpose: Functionality used across multiple domains
- Example: Retrieval (used in prompts, validation, aggregation)
- Future growth: Caching, logging, tracing

---

## 4. Proposal: Reorganization Plan

### 4.1 Proposed Directory Structure

```
src/elspeth/
├── core/
│   ├── registry/
│   │   ├── base.py                    # BasePluginRegistry (unchanged)
│   │   ├── context_utils.py           # Security/context (unchanged)
│   │   ├── plugin_helpers.py          # Helpers (unchanged)
│   │   └── schemas.py                 # Schemas (unchanged)
│   ├── protocols.py                   # ALL plugin protocols in ONE place
│   └── [other core modules]
│
├── plugins/
│   ├── data_input/                    # NEW: Consolidate datasources
│   │   ├── __init__.py
│   │   ├── registry.py                # Single registry for all input sources
│   │   ├── csv_local.py
│   │   ├── csv_blob.py
│   │   ├── blob.py
│   │   └── [future: s3.py, gcs.py, postgres.py]
│   │
│   ├── data_output/                   # NEW: Consolidate sinks
│   │   ├── __init__.py
│   │   ├── registry.py                # Single registry for all sinks
│   │   ├── csv_file.py
│   │   ├── excel.py
│   │   ├── blob.py
│   │   ├── signed.py
│   │   ├── analytics_report.py
│   │   ├── visual_report.py
│   │   ├── embeddings_store.py
│   │   └── [future: telemetry.py, pdf.py]
│   │
│   ├── llm_integration/               # NEW: LLM clients + middleware together
│   │   ├── __init__.py
│   │   ├── clients/
│   │   │   ├── registry.py            # Client registry
│   │   │   ├── azure_openai.py
│   │   │   ├── openai_http.py
│   │   │   ├── mock.py
│   │   │   ├── static.py
│   │   │   └── [future: anthropic.py, bedrock.py, vertex.py]
│   │   └── middleware/
│   │       ├── registry.py            # Middleware registry
│   │       ├── audit_logger.py        # Extract from middleware.py
│   │       ├── prompt_shield.py
│   │       ├── health_monitor.py
│   │       ├── azure_content_safety.py
│   │       └── [future: opa_policy.py, openai_moderation.py]
│   │
│   ├── experiment_lifecycle/          # NEW: All experiment plugins
│   │   ├── __init__.py
│   │   ├── row_processing/
│   │   │   ├── registry.py
│   │   │   ├── score_extractor.py     # Extract from metrics.py
│   │   │   └── [future: latency_tracker.py, fairness_metrics.py]
│   │   ├── aggregation/
│   │   │   ├── registry.py
│   │   │   ├── statistics.py          # Extract from metrics.py
│   │   │   ├── recommendations.py
│   │   │   └── [future: cost_summary.py]
│   │   ├── validation/
│   │   │   ├── registry.py
│   │   │   ├── regex_validator.py     # Extract from validation.py
│   │   │   ├── json_validator.py
│   │   │   └── [future: schema_validator.py]
│   │   ├── baseline/
│   │   │   ├── registry.py
│   │   │   ├── frequentist.py         # Extract from metrics.py
│   │   │   ├── bayesian.py
│   │   │   └── [future: sequential_testing.py]
│   │   ├── early_stop/
│   │   │   ├── registry.py
│   │   │   ├── threshold.py           # Extract from early_stop.py
│   │   │   └── [future: composite_policy.py]
│   │   └── controls/
│   │       ├── registry.py
│   │       ├── rate_limiter.py
│   │       ├── cost_tracker.py
│   │       └── [future: quota_manager.py]
│   │
│   └── utilities/                     # Cross-cutting utilities
│       ├── __init__.py
│       ├── registry.py
│       ├── retrieval.py
│       └── [future: caching.py, tracing.py]
```

### 4.2 Migration Plan

#### Phase 1: Consolidate Protocols (1 hour)
- [ ] Create `core/protocols.py`
- [ ] Move ALL protocols from `interfaces.py`, `experiments/plugins.py`, `llm/middleware.py`, `controls/` to ONE file
- [ ] Update imports throughout codebase

#### Phase 2: Reorganize Plugin Implementations (2-3 hours)
- [ ] Create new directory structure
- [ ] Move plugin implementations to functional domains
- [ ] Update imports in plugin files
- [ ] Split large files (metrics.py, middleware.py)

#### Phase 3: Consolidate Registries (3-4 hours)
- [ ] One registry per functional domain
- [ ] Eliminate facade layers (keep only BasePluginRegistry + domain registries)
- [ ] Update all `create_*` and `register_*` functions to point to new registries

#### Phase 4: Update Documentation (1-2 hours)
- [ ] Rewrite plugin-catalogue.md to use functional organization
- [ ] Update FEATURE_ROADMAP.md with new structure
- [ ] Add "Plugin Developer's Guide" showing how to add to each domain

#### Phase 5: Testing & Validation (2-3 hours)
- [ ] Verify all 545 tests still pass
- [ ] Update test organization to match new structure
- [ ] Add integration tests for new structure

**Total Estimated Effort**: 9-13 hours

### 4.3 Benefits of Reorganization

**1. Clearer Mental Model**
- "Where do I add a new LLM provider?" → `plugins/llm_integration/clients/`
- "Where do I add telemetry?" → `plugins/data_output/` (if sink) or `plugins/llm_integration/middleware/` (if middleware)

**2. Better Discoverability**
- Browse by functional purpose, not technical type
- Related plugins co-located

**3. Easier Extension**
- Each domain has ONE registry
- Clear extension patterns per domain

**4. Roadmap Alignment**
- New LLM providers go in `llm_integration/clients/`
- New datasources go in `data_input/`
- New metrics go in `experiment_lifecycle/row_processing/` or `.../aggregation/`

**5. Reduced Complexity**
- Eliminate facade layers
- Direct path: User code → Domain registry → BasePluginRegistry → Plugin
- 3 layers instead of 5

---

## 5. Alternative Approaches Considered

### Alternative A: Keep Current Structure, Add Better Docs
**Pros**: No code changes, less risk
**Cons**: Doesn't fix underlying confusion, doesn't scale with roadmap

### Alternative B: Flatten Everything into `plugins/`
**Pros**: Simpler directory structure
**Cons**: Loses functional organization, hard to navigate with 50+ plugins

### Alternative C: Organize by Protocol Type
**Pros**: Type-driven organization
**Cons**: Doesn't match how users think about plugins ("what does this plugin do?" vs "what type is it?")

**Recommendation**: Proceed with proposed functional reorganization (Alternative D).

---

## 6. Open Questions for Discussion

1. **Naming**: Are the functional domain names clear? (data_input, data_output, llm_integration, experiment_lifecycle, utilities)

2. **Controls Placement**: Should rate_limiter/cost_tracker go in:
   - `experiment_lifecycle/controls/` (current proposal) OR
   - `llm_integration/controls/` (since they control LLM calls)

3. **Middleware vs Utilities**: What's the distinction?
   - Current thinking: Middleware intercepts LLM calls, utilities are passive helpers
   - Should retrieval be middleware instead of utility?

4. **Backward Compatibility**: Should we keep old import paths with deprecation warnings?
   - Pro: Easier migration for existing code
   - Con: More complexity to maintain

5. **Test Organization**: Should tests mirror the new structure exactly?
   - `tests/plugins/data_input/test_csv_local.py` vs current `tests/test_datasources_csv_local.py`

---

## 7. Next Steps

**Recommendation**: Proceed with reorganization in phases.

**Immediate actions**:
1. Review this proposal with team
2. Address open questions
3. Get stakeholder approval
4. Begin Phase 1 (protocol consolidation)

**Success Criteria**:
- All tests pass
- New developer can find right place to add plugin in <5 minutes
- Plugin catalogue documentation is clear and accurate
- Roadmap items have obvious homes

---

**Appendix A: Plugin Type Cross-Reference**

| Old Location | New Location |
|--------------|--------------|
| `plugins/datasources/` | `plugins/data_input/` |
| `plugins/outputs/` | `plugins/data_output/` |
| `plugins/llms/*.py` (clients) | `plugins/llm_integration/clients/` |
| `plugins/llms/middleware*.py` | `plugins/llm_integration/middleware/` |
| `plugins/experiments/metrics.py` (row parts) | `plugins/experiment_lifecycle/row_processing/` |
| `plugins/experiments/metrics.py` (agg parts) | `plugins/experiment_lifecycle/aggregation/` |
| `plugins/experiments/metrics.py` (baseline) | `plugins/experiment_lifecycle/baseline/` |
| `plugins/experiments/validation.py` | `plugins/experiment_lifecycle/validation/` |
| `plugins/experiments/early_stop.py` | `plugins/experiment_lifecycle/early_stop/` |
| `core/controls/` | `plugins/experiment_lifecycle/controls/` |
| `plugins/utilities/` | `plugins/utilities/` (unchanged) |

**Appendix B: Registry Consolidation Mapping**

| Old Registries (18 files) | New Registries (6 files) |
|---------------------------|--------------------------|
| `core/datasource_registry.py` | `plugins/data_input/registry.py` |
| `core/sink_registry.py` | `plugins/data_output/registry.py` |
| `core/llm_registry.py` | `plugins/llm_integration/clients/registry.py` |
| `core/llm/registry.py` | `plugins/llm_integration/middleware/registry.py` |
| `core/experiments/row_plugin_registry.py`<br>`core/experiments/aggregation_plugin_registry.py`<br>`core/experiments/validation_plugin_registry.py`<br>`core/experiments/baseline_plugin_registry.py`<br>`core/experiments/early_stop_plugin_registry.py`<br>`core/controls/rate_limiter_registry.py`<br>`core/controls/cost_tracker_registry.py` | `plugins/experiment_lifecycle/registry.py`<br>(unified with sub-registries per lifecycle phase) |
| `core/utilities/plugin_registry.py` | `plugins/utilities/registry.py` |

**Reduction**: 18 → 6 registry files (67% reduction)
