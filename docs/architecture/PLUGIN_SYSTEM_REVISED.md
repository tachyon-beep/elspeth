# Plugin System Architecture (REVISED)
## Orchestration-First Design

**Date**: October 14, 2025
**Status**: DRAFT - Incorporates orchestration-as-plugin feedback

---

## Core Principle

**Elspeth is an orchestrator that can run in different modes.**

Experimentation is ONE orchestration mode. The architecture should support:
- Experiment orchestration (current)
- Batch processing orchestration (future)
- Streaming orchestration (future)
- Validation-only orchestration (future)

---

## Top-Level Plugin Domains

```
src/elspeth/
├── core/
│   ├── protocols.py              # ALL plugin protocols
│   ├── orchestration/            # Base orchestration framework
│   │   ├── base.py               # BaseOrchestrator protocol
│   │   ├── runner.py             # Generic runner
│   │   └── context.py            # Orchestration context
│   └── registry/
│       ├── base.py               # BasePluginRegistry
│       └── ...
│
└── plugins/
    ├── orchestrators/            # ★ NEW: First-class orchestration modes
    │   ├── experiment/           # Experiment orchestration (current)
    │   ├── batch_processing/     # Future: Simple batch LLM calls
    │   ├── validation/           # Future: Validation pipeline
    │   └── streaming/            # Future: Real-time processing
    │
    ├── data_input/               # Universal: Where data comes from
    ├── data_output/              # Universal: Where results go
    ├── llm_integration/          # Universal: How to talk to LLMs
    ├── processing/               # ★ NEW: Orchestrator-agnostic transforms
    └── utilities/                # Universal: Cross-cutting helpers
```

---

## 1. Orchestrators Domain (NEW)

**Purpose**: Define different modes of orchestration

**Protocol**:
```python
# core/orchestration/base.py
class Orchestrator(Protocol):
    """Base protocol for all orchestration modes."""

    def run(
        self,
        data: Any,
        config: dict[str, Any],
        *,
        context: OrchestrationContext,
    ) -> dict[str, Any]:
        """Execute orchestration and return results."""
```

### 1.1 Experiment Orchestrator (Current Mode)

**Location**: `plugins/orchestrators/experiment/`

**Structure**:
```
plugins/orchestrators/experiment/
├── __init__.py
├── registry.py                   # Registers experiment orchestrator
├── runner.py                     # ExperimentRunner (current logic)
├── suite_runner.py               # ExperimentSuiteRunner
│
├── row_processing/               # Row-level plugins
│   ├── registry.py
│   ├── score_extractor.py
│   └── [future: latency_tracker.py]
│
├── aggregation/                  # Aggregate-level plugins
│   ├── registry.py
│   ├── statistics.py
│   └── recommendations.py
│
├── validation/                   # Response validation
│   ├── registry.py
│   ├── regex_validator.py
│   └── json_validator.py
│
├── baseline/                     # Baseline comparison
│   ├── registry.py
│   ├── frequentist.py
│   └── bayesian.py
│
└── early_stop/                   # Early stopping
    ├── registry.py
    └── threshold.py
```

**Key Point**: These plugins are **experiment-specific**. Other orchestrators don't need them.

### 1.2 Future Orchestrators

**Batch Processing Orchestrator**:
```python
# plugins/orchestrators/batch_processing/runner.py
class BatchProcessingOrchestrator:
    """Simple batch LLM processing without experiment semantics.

    Use case: "Process 10,000 customer reviews through GPT-4"
    No baselines, no aggregation, just bulk processing.
    """

    def run(self, data: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
        # Simpler than experiments: just call LLM for each row
        # Uses: data_input, llm_integration, data_output
        # Doesn't use: experiment-specific plugins
```

**Validation Orchestrator**:
```python
# plugins/orchestrators/validation/runner.py
class ValidationOrchestrator:
    """Validate data or responses without LLM calls.

    Use case: "Validate 1M records against schema before uploading"
    No LLM involved, just validation logic.
    """

    def run(self, data: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
        # Uses: data_input, processing (validators), data_output
        # Doesn't use: llm_integration
```

---

## 2. Data Input Domain (Universal)

**Purpose**: Load data into any orchestrator

**Location**: `plugins/data_input/`

**Protocol**: `DataSource` (unchanged)

```
plugins/data_input/
├── __init__.py
├── registry.py                   # Single registry
├── csv_local.py
├── csv_blob.py
├── blob.py
└── [future: s3.py, postgres.py, kafka_stream.py]
```

**Used by**: ALL orchestrators (experiment, batch, validation, streaming)

---

## 3. Data Output Domain (Universal)

**Purpose**: Persist results from any orchestrator

**Location**: `plugins/data_output/`

**Protocol**: `ResultSink` (unchanged)

```
plugins/data_output/
├── __init__.py
├── registry.py                   # Single registry
├── csv_file.py
├── excel.py
├── blob.py
├── signed.py
├── analytics_report.py           # Experiment-aware, but usable by any orchestrator
├── visual_report.py
└── [future: telemetry.py, prometheus.py]
```

**Used by**: ALL orchestrators

**Note**: Some sinks are experiment-aware (analytics_report) but still universal - they just render differently for non-experiment data.

---

## 4. LLM Integration Domain (Universal)

**Purpose**: Interact with LLM providers

**Location**: `plugins/llm_integration/`

**Protocols**: `LLMClientProtocol`, `LLMMiddleware`

```
plugins/llm_integration/
├── __init__.py
│
├── clients/
│   ├── registry.py
│   ├── azure_openai.py
│   ├── openai_http.py
│   ├── mock.py
│   ├── static.py
│   └── [future: anthropic.py, bedrock.py, vertex.py]
│
├── middleware/
│   ├── registry.py
│   ├── audit_logger.py
│   ├── prompt_shield.py
│   ├── health_monitor.py
│   ├── content_safety_azure.py
│   └── [future: opa_policy.py, openai_moderation.py]
│
└── controls/                     # ★ Moved here from experiment_lifecycle
    ├── registry.py
    ├── rate_limiter.py           # Universal to ANY LLM usage
    └── cost_tracker.py           # Universal to ANY LLM usage
```

**Used by**: Any orchestrator that calls LLMs (experiment, batch, streaming)

**Key Decision**: Controls (rate_limiter, cost_tracker) moved here because they're universal to LLM interaction, not experiment-specific.

---

## 5. Processing Domain (NEW)

**Purpose**: Orchestrator-agnostic data transformations

**Location**: `plugins/processing/`

**Protocol**: `ProcessingPlugin` (new)

```python
# core/protocols.py
class ProcessingPlugin(Protocol):
    """Transform data during orchestration."""

    name: str

    def process(
        self,
        data: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transform input data and return enriched/modified data."""
```

```
plugins/processing/
├── __init__.py
├── registry.py
├── text_cleaning.py              # Normalize text
├── schema_validation.py          # Validate against schemas
├── pii_redaction.py              # Remove PII
└── [future: translation.py, sentiment.py]
```

**Used by**: ANY orchestrator (experiment row plugins, batch transforms, streaming filters)

**Example**: The current "score extraction" logic could be:
- An experiment row plugin (experiment-specific) OR
- A generic processing plugin (reusable across modes)

---

## 6. Utilities Domain (Universal)

**Purpose**: Cross-cutting helpers

**Location**: `plugins/utilities/`

```
plugins/utilities/
├── __init__.py
├── registry.py
├── retrieval.py                  # Context retrieval for RAG
├── caching.py                    # Cache results
└── [future: tracing.py, monitoring.py]
```

**Used by**: ANY component (orchestrators, plugins, middleware)

---

## Protocol Consolidation

**New file**: `core/protocols.py` (ALL protocols in ONE place)

```python
# core/protocols.py
"""All plugin protocols for Elspeth."""

from typing import Protocol, Any
import pandas as pd

# Universal protocols
class DataSource(Protocol):
    """Load data for orchestration."""
    def load(self) -> pd.DataFrame: ...

class ResultSink(Protocol):
    """Persist orchestration results."""
    def write(self, results: dict[str, Any], **kwargs) -> None: ...

class LLMClientProtocol(Protocol):
    """Interact with LLM providers."""
    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs) -> dict[str, Any]: ...

class LLMMiddleware(Protocol):
    """Intercept LLM requests/responses."""
    name: str
    def before_request(self, request: Any) -> Any: ...
    def after_response(self, response: Any) -> Any: ...

class RateLimiter(Protocol):
    """Control request rate."""
    def acquire(self, **kwargs) -> ContextManager[None]: ...

class CostTracker(Protocol):
    """Track LLM costs."""
    def record(self, response: dict[str, Any], **kwargs) -> dict[str, Any]: ...
    def summary(self) -> dict[str, Any]: ...

# Orchestrator protocol
class Orchestrator(Protocol):
    """Base for all orchestration modes."""
    def run(self, data: Any, config: dict[str, Any], **kwargs) -> dict[str, Any]: ...

# Experiment-specific protocols (move to plugins/orchestrators/experiment/protocols.py)
class RowExperimentPlugin(Protocol):
    """Experiment row processing."""
    name: str
    def process_row(self, row: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]: ...

class AggregationExperimentPlugin(Protocol):
    """Experiment aggregation."""
    name: str
    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]: ...

class ValidationPlugin(Protocol):
    """Experiment validation."""
    name: str
    def validate(self, response: dict[str, Any], **kwargs) -> None: ...

class BaselineComparisonPlugin(Protocol):
    """Experiment baseline comparison."""
    name: str
    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]: ...

class EarlyStopPlugin(Protocol):
    """Experiment early stopping."""
    name: str
    def check(self, record: dict[str, Any], **kwargs) -> dict[str, Any] | None: ...

# New protocols
class ProcessingPlugin(Protocol):
    """Orchestrator-agnostic processing."""
    name: str
    def process(self, data: dict[str, Any], **kwargs) -> dict[str, Any]: ...
```

**Alternative**: Split into:
- `core/protocols.py` - Universal protocols
- `plugins/orchestrators/experiment/protocols.py` - Experiment-specific protocols

---

## Registry Consolidation

**Before**: 18 registry files
**After**: 8 registry files (56% reduction)

| Domain | Registry File | Purpose |
|--------|--------------|---------|
| Orchestrators | `plugins/orchestrators/registry.py` | Register orchestration modes |
| Experiment (sub) | `plugins/orchestrators/experiment/registry.py` | Experiment-specific plugins (consolidates 5 registries) |
| Data Input | `plugins/data_input/registry.py` | Datasources |
| Data Output | `plugins/data_output/registry.py` | Sinks |
| LLM Clients | `plugins/llm_integration/clients/registry.py` | LLM clients |
| LLM Middleware | `plugins/llm_integration/middleware/registry.py` | LLM middleware |
| LLM Controls | `plugins/llm_integration/controls/registry.py` | Rate limiting, cost tracking |
| Processing | `plugins/processing/registry.py` | Processing plugins |
| Utilities | `plugins/utilities/registry.py` | Utilities |

**Note**: Experiment orchestrator has internal sub-registries for its 5 plugin types (row, agg, validation, baseline, early-stop) but these are implementation details, not top-level.

---

## Migration Strategy

### Phase 1: Add Orchestration Abstraction (3-4 hours)
1. Create `core/orchestration/base.py` with `Orchestrator` protocol
2. Create `core/protocols.py` with all protocols
3. Move current `ExperimentRunner` to `plugins/orchestrators/experiment/runner.py`
4. Implement `ExperimentOrchestrator` that wraps `ExperimentRunner`
5. Update `core/orchestrator.py` to use the new abstraction

### Phase 2: Reorganize Universal Plugins (2-3 hours)
1. Move datasources to `plugins/data_input/`
2. Move sinks to `plugins/data_output/`
3. Split `plugins/llms/` into clients + middleware in `plugins/llm_integration/`
4. Move controls to `plugins/llm_integration/controls/`

### Phase 3: Reorganize Experiment Plugins (2-3 hours)
1. Move experiment plugins to `plugins/orchestrators/experiment/`
2. Split `metrics.py` into row_processing/, aggregation/, baseline/
3. Update imports with backward compatibility

### Phase 4: Add Processing Domain (1-2 hours)
1. Create `plugins/processing/` structure
2. Extract reusable logic from experiment row plugins
3. Register in new domain

### Phase 5: Update Documentation & Tests (2-3 hours)
1. Update plugin catalogue
2. Update architecture docs
3. Reorganize tests to mirror structure
4. Add orchestrator developer guide

**Total**: 10-15 hours

---

## Benefits of This Architecture

### 1. Conceptual Clarity
- **"What is Elspeth?"** → An orchestrator
- **"What can it do?"** → Multiple modes (experimentation, batch, validation, streaming)
- **"How do I extend it?"** → Add plugins to domains OR add new orchestrator modes

### 2. True Modularity
- Want batch processing without experiments? Use batch orchestrator + universal plugins
- Want validation without LLMs? Use validation orchestrator + data_input + data_output
- Experiment orchestrator becomes ONE way to use Elspeth, not THE way

### 3. Roadmap Alignment
- New LLM providers → `llm_integration/clients/`
- New datasources → `data_input/`
- New orchestration modes → `orchestrators/`
- New processing logic → `processing/` (if universal) OR `orchestrators/<mode>/` (if mode-specific)

### 4. Reduced Coupling
- Universal plugins don't depend on experiment semantics
- Orchestrators can mix-and-match plugins
- Controls are LLM-specific, not experiment-specific

---

## Open Design Questions

### Q1: Should controls be in llm_integration or stay experiment-specific?

**Option A**: `llm_integration/controls/` (proposed)
- **Pro**: Rate limiting applies to ANY LLM usage
- **Pro**: Batch orchestrator would also want rate limiting
- **Con**: Currently tightly coupled to experiment runner

**Option B**: `orchestrators/experiment/controls/`
- **Pro**: Currently only used by experiments
- **Pro**: Easier migration (less movement)
- **Con**: Hard to reuse in future orchestrators

**Recommendation**: Option A - make controls universal from the start

### Q2: Should we have a Processing domain or fold it into orchestrators?

**Option A**: `plugins/processing/` (proposed)
- **Pro**: Reusable across orchestrators
- **Pro**: Clear separation of concerns
- **Con**: More top-level domains

**Option B**: No processing domain, put in orchestrators
- **Pro**: Fewer domains
- **Con**: Can't reuse logic across orchestrators
- **Con**: Forces duplication

**Recommendation**: Option A - processing is universal

### Q3: How do we handle experiment-aware sinks?

Example: `analytics_report.py` generates experiment-specific analytics. Where does it go?

**Option A**: `plugins/data_output/` but make it experiment-aware
- Sink checks if results have experiment structure
- If yes, render experiment analytics
- If no, render generic report
- **Pro**: One sink, works for all orchestrators
- **Con**: Sink has mode-specific logic

**Option B**: `plugins/orchestrators/experiment/sinks/`
- Experiment-specific sinks live with experiment orchestrator
- Generic sinks in `data_output/`
- **Pro**: Clear separation
- **Con**: Two sink locations

**Recommendation**: Option A - universal sinks with mode awareness

---

## Comparison to Current Architecture

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Mental Model** | "Elspeth is an experiment runner" | "Elspeth is an orchestrator" |
| **Extensibility** | Add experiment plugins | Add orchestrators OR plugins |
| **Top-level domains** | 5 (datasources, llms, outputs, experiments, utilities) | 6 (orchestrators, data_input, data_output, llm_integration, processing, utilities) |
| **Registry files** | 18 | 8 |
| **Layers of indirection** | 5 | 3 |
| **Experiment coupling** | High - experiment concepts everywhere | Low - experiment is one mode |

---

## Next Steps

1. **Review this proposal** - Does the orchestration-first view make sense?
2. **Answer design questions** - Finalize domain boundaries
3. **Approve migration plan** - Get stakeholder buy-in
4. **Begin Phase 1** - Add orchestration abstraction

**Success Criteria**:
- [ ] Can add a batch processing orchestrator in <4 hours
- [ ] Can reuse llm_integration and data plugins across modes
- [ ] New developers understand "orchestrators" as the core concept
- [ ] All 545 tests still pass
