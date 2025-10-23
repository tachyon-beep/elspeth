# Complexity Refactoring Plan: Production Blockers AUD-0007 & AUD-0008

**Repository:** elspeth
**Branch:** remediation
**Document Version:** 1.0
**Date:** 2025-10-23
**Status:** APPROVED FOR IMPLEMENTATION

---

## Executive Summary

This document provides a detailed refactoring plan to address the **2 production blocker findings** from the AIS audit:

| ID | Function | File | Complexity | Target | Status |
|----|----------|------|------------|--------|--------|
| **AUD-0007** | `ExperimentRunner.run()` | `runner.py:75` | **70** | ≤15 | **PRODUCTION BLOCKER** |
| **AUD-0008** | `ExperimentSuiteRunner.build_runner()` | `suite_runner.py:47` | **69** | ≤15 | **PRODUCTION BLOCKER** |

**Goal**: Reduce cognitive complexity from 70/69 to ≤15 per function through systematic decomposition while maintaining 100% backward compatibility and test coverage.

**Timeline**: 3-4 weeks (2 sprints)
**Risk Level**: HIGH (mission-critical orchestration code)
**Testing Strategy**: Test-driven refactoring with parallel execution validation

---

## Table of Contents

1. [Complexity Analysis](#complexity-analysis)
2. [AUD-0007: ExperimentRunner.run() Refactoring](#aud-0007-experimentrunnerrun-refactoring)
3. [AUD-0008: ExperimentSuiteRunner.build_runner() Refactoring](#aud-0008-experimentsuiterunnerbuild_runner-refactoring)
4. [Implementation Phases](#implementation-phases)
5. [Testing Strategy](#testing-strategy)
6. [Success Criteria](#success-criteria)
7. [Risk Mitigation](#risk-mitigation)
8. [Rollback Plan](#rollback-plan)

---

## Complexity Analysis

### AUD-0007: ExperimentRunner.run()

**Current State** (`src/elspeth/core/experiments/runner.py:75-245`)

**Cognitive Complexity**: 70 (4.7x over threshold of 15)

**Responsibilities** (11 distinct concerns):
1. Checkpoint loading and tracking
2. Prompt template compilation (system, user, criteria)
3. Schema validation
4. Row iteration and filtering
5. Parallel vs sequential execution coordination
6. Single row processing orchestration
7. Success/failure handling and callbacks
8. Result aggregation and sorting
9. Retry metadata collection
10. Cost/security/determinism metadata resolution
11. Artifact pipeline execution

**Complexity Sources**:
- **Nested conditionals**: Early stop checks (3 levels), checkpoint logic (2 levels), parallel execution branching
- **Loop complexity**: Row iteration with state management
- **Multiple callback patterns**: `handle_success`, `handle_failure`, early stop evaluation
- **Cross-cutting concerns**: Retry tracking, cost accumulation, security level resolution
- **Error handling**: Try-except blocks with multiple exception types

**Current Line Count**: ~170 lines in single method

---

### AUD-0008: ExperimentSuiteRunner.build_runner()

**Current State** (`src/elspeth/core/experiments/suite_runner.py:47-233`)

**Cognitive Complexity**: 69 (4.6x over threshold of 15)

**Responsibilities** (12 distinct concerns):
1. Prompt pack resolution
2. Three-layer configuration merging (defaults → pack → experiment)
3. Prompt configuration merge (system, user, fields, criteria)
4. Middleware definition merging
5. Concurrency configuration merge
6. Early stop configuration normalization
7. Plugin definition merging (row, aggregator, validation, early stop)
8. Security level resolution (most restrictive wins)
9. Plugin context creation and derivation
10. Plugin instantiation (7 plugin types)
11. Middleware caching by fingerprint
12. Validation and error handling

**Complexity Sources**:
- **Deeply nested configuration logic**: 3-layer merge with special rules for each field type
- **Conditional plugin creation**: Different instantiation paths for each plugin type
- **Context propagation**: Manual context derivation for sinks, rate limiters, cost trackers
- **Middleware caching**: Fingerprint-based deduplication with shared state
- **Validation interleaving**: Prompt validation, security level checks, plugin schema validation

**Current Line Count**: ~186 lines in single method

---

## AUD-0007: ExperimentRunner.run() Refactoring

### Proposed Architecture: Pipeline Pattern

**Design Pattern**: Chain of Responsibility with Pipeline Stages

**Target Complexity**: ≤15 per function (total: 11 functions)

### Decomposition Strategy

#### 1. **ExperimentExecutionPipeline** (New Coordinator Class)

**Purpose**: Replace monolithic `run()` with orchestrated pipeline

**Responsibilities**:
- Initialize pipeline stages
- Coordinate stage execution order
- Aggregate stage outputs
- Handle pipeline-level errors

**Complexity Target**: ≤10

```python
class ExperimentExecutionPipeline:
    """Orchestrates experiment execution through composable stages."""

    def __init__(self, runner: ExperimentRunner):
        self.runner = runner
        self.stages = self._build_pipeline_stages()

    def execute(self, df: pd.DataFrame) -> dict[str, Any]:
        """Execute pipeline and return results payload.

        Complexity: ~8 (linear stage execution)
        """
        context = PipelineContext(df, runner=self.runner)

        for stage in self.stages:
            context = stage.execute(context)
            if context.should_stop:
                break

        return context.build_payload()
```

#### 2. **CheckpointManager** (New Class)

**Purpose**: Isolate checkpoint loading/saving logic

**Complexity Target**: ≤8

```python
class CheckpointManager:
    """Manages row processing checkpoints for resumability."""

    def __init__(self, config: dict[str, Any] | None):
        self.checkpoint_path = Path(config.get("path")) if config else None
        self.checkpoint_field = config.get("field", "APPID") if config else None
        self.processed_ids: set[str] = set()

    def load(self) -> None:
        """Load processed row IDs from checkpoint file.

        Complexity: ~5 (file I/O with error handling)
        """
        if not self.checkpoint_path or not self.checkpoint_path.exists():
            return

        with open(self.checkpoint_path) as f:
            for line in f:
                record = json.loads(line)
                self.processed_ids.add(record["id"])

    def is_processed(self, row_id: str | None) -> bool:
        """Check if row ID has been processed."""
        return row_id in self.processed_ids if row_id else False

    def mark_processed(self, row_id: str) -> None:
        """Record row as processed and append to checkpoint file."""
        # Complexity: ~3
```

#### 3. **PromptCompilationStage** (Pipeline Stage)

**Purpose**: Compile all prompt templates

**Complexity Target**: ≤10

```python
class PromptCompilationStage:
    """Compiles system, user, and criteria prompt templates."""

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Compile templates and attach to context.

        Complexity: ~8 (template compilation loops)
        """
        engine = context.runner.prompt_engine or PromptEngine()

        context.system_template = self._compile_template(
            engine, context.runner.prompt_system, "system"
        )
        context.user_template = self._compile_template(
            engine, context.runner.prompt_template, "user"
        )
        context.criteria_templates = self._compile_criteria(engine)

        return context

    def _compile_template(self, engine, text, name) -> PromptTemplate:
        """Compile single template (complexity ~3)."""
        # ...
```

#### 4. **RowProcessingCoordinator** (Pipeline Stage)

**Purpose**: Coordinate row processing (parallel or sequential)

**Complexity Target**: ≤12

```python
class RowProcessingCoordinator:
    """Coordinates parallel or sequential row processing."""

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Process all rows and collect results.

        Complexity: ~10 (branching logic for parallel vs sequential)
        """
        rows_to_process = self._filter_rows(context)

        if self._should_run_parallel(context, len(rows_to_process)):
            self._execute_parallel(context, rows_to_process)
        else:
            self._execute_sequential(context, rows_to_process)

        return context
```

#### 5. **ConcurrencyManager** (New Class)

**Purpose**: Abstract semaphore and thread pool management

**Complexity Target**: ≤10

```python
class ConcurrencyManager:
    """Manages concurrent row processing with semaphore limits."""

    def __init__(self, config: dict[str, Any]):
        self.max_workers = config.get("max_workers", 10)
        self.semaphore_limit = config.get("limit", self.max_workers)
        self.enabled = config.get("enabled", True)

    def execute_parallel(
        self,
        items: list,
        process_func: Callable,
        callback: Callable,
    ) -> None:
        """Execute items in parallel with semaphore limiting.

        Complexity: ~8 (thread pool + semaphore coordination)
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            semaphore = threading.Semaphore(self.semaphore_limit)

            def wrapped_func(item):
                with semaphore:
                    return process_func(item)

            futures = [executor.submit(wrapped_func, item) for item in items]
            for future in as_completed(futures):
                callback(future.result())
```

#### 6. **AggregationStage** (Pipeline Stage)

**Purpose**: Run aggregator plugins and collect results

**Complexity Target**: ≤8

```python
class AggregationStage:
    """Runs aggregator plugins over experiment results."""

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute all aggregator plugins.

        Complexity: ~6 (simple loop with plugin calls)
        """
        aggregates = {}
        for plugin in context.runner.aggregator_plugins or []:
            derived = plugin.finalize(context.results)
            if derived:
                if isinstance(derived, dict) and "failures" not in derived:
                    derived["failures"] = []
                aggregates[plugin.name] = derived

        context.aggregates = aggregates
        return context
```

#### 7. **MetadataBuilder** (New Class)

**Purpose**: Collect and structure experiment metadata

**Complexity Target**: ≤12

```python
class MetadataBuilder:
    """Builds experiment metadata from execution context."""

    def build(self, context: PipelineContext) -> dict[str, Any]:
        """Build complete metadata dictionary.

        Complexity: ~10 (conditional field collection)
        """
        metadata = {
            "rows": len(context.results),
            "row_count": len(context.results),
        }

        self._add_retry_summary(metadata, context)
        self._add_cost_summary(metadata, context)
        self._add_security_metadata(metadata, context)
        self._add_early_stop_metadata(metadata, context)

        return metadata
```

#### 8. **EarlyStopEvaluator** (New Class)

**Purpose**: Centralize early stop logic and state management

**Complexity Target**: ≤10

```python
class EarlyStopEvaluator:
    """Evaluates early stop conditions and manages event state."""

    def __init__(self, plugins: list[EarlyStopPlugin]):
        self.plugins = plugins
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.reason: dict[str, Any] | None = None

    def check(self, record: dict[str, Any], metadata: dict | None = None) -> None:
        """Check early stop conditions (thread-safe).

        Complexity: ~8 (lock management + plugin loop)
        """
        if self.event.is_set():
            return

        with self.lock:
            if self.event.is_set():  # Double-check after lock
                return

            for plugin in self.plugins:
                reason = plugin.check(record, metadata=metadata)
                if reason:
                    self._trigger_stop(reason, plugin.name, metadata)
                    break
```

#### 9. **ValidationOrchestrator** (New Class)

**Purpose**: Coordinate schema and plugin validation

**Complexity Target**: ≤8

```python
class ValidationOrchestrator:
    """Orchestrates schema validation and plugin compatibility checks."""

    def validate_schema(self, df: pd.DataFrame, plugins: list) -> None:
        """Validate datasource schema against plugin requirements.

        Complexity: ~6 (schema extraction + plugin loop)
        """
        schema = df.attrs.get("schema") if hasattr(df, "attrs") else None
        if not schema:
            return

        for plugin in plugins:
            if hasattr(plugin, "validate_schema"):
                plugin.validate_schema(schema)
```

#### 10. **ResultCollector** (New Class)

**Purpose**: Aggregate results and failures with sorting

**Complexity Target**: ≤6

```python
class ResultCollector:
    """Collects and sorts experiment results."""

    def __init__(self):
        self.records_with_index: list[tuple[int, dict]] = []
        self.failures: list[dict] = []

    def add_success(self, idx: int, record: dict) -> None:
        """Add successful result (complexity ~2)."""
        self.records_with_index.append((idx, record))

    def add_failure(self, failure: dict) -> None:
        """Add failed result (complexity ~1)."""
        self.failures.append(failure)

    def get_sorted_results(self) -> list[dict]:
        """Return results sorted by original row index (complexity ~3)."""
        self.records_with_index.sort(key=lambda item: item[0])
        return [record for _, record in self.records_with_index]
```

#### 11. **PipelineContext** (Data Class)

**Purpose**: Shared state container for pipeline stages

```python
@dataclass
class PipelineContext:
    """Shared context passed between pipeline stages."""

    df: pd.DataFrame
    runner: ExperimentRunner

    # Compiled templates (set by PromptCompilationStage)
    system_template: PromptTemplate | None = None
    user_template: PromptTemplate | None = None
    criteria_templates: dict[str, PromptTemplate] = field(default_factory=dict)

    # Processing state (set by RowProcessingCoordinator)
    results: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    # Aggregation results (set by AggregationStage)
    aggregates: dict[str, Any] = field(default_factory=dict)

    # Control flags
    should_stop: bool = False
    early_stop_reason: dict | None = None

    def build_payload(self) -> dict[str, Any]:
        """Build final experiment payload (complexity ~5)."""
        # ...
```

### Refactored run() Method

**New Complexity**: ≤10

```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:
    """Execute experiment using pipeline orchestration.

    Complexity: ~8 (pipeline initialization + error handling)
    """
    pipeline = ExperimentExecutionPipeline(self)

    try:
        payload = pipeline.execute(df)
        return payload
    except (PromptRenderingError, PromptValidationError) as exc:
        logger.error("Experiment execution failed: %s", exc)
        raise
    finally:
        self._active_security_level = None
```

### File Organization

```
src/elspeth/core/experiments/
├── runner.py                    # ExperimentRunner (simplified)
├── execution/
│   ├── __init__.py
│   ├── pipeline.py              # ExperimentExecutionPipeline, PipelineContext
│   ├── stages.py                # Pipeline stage implementations
│   ├── checkpoint.py            # CheckpointManager
│   ├── concurrency.py           # ConcurrencyManager
│   ├── early_stop.py            # EarlyStopEvaluator
│   ├── aggregation.py           # AggregationStage
│   ├── metadata.py              # MetadataBuilder
│   ├── validation.py            # ValidationOrchestrator
│   └── result_collector.py      # ResultCollector
```

---

## AUD-0008: ExperimentSuiteRunner.build_runner() Refactoring

### Proposed Architecture: Builder Pattern with Specialized Mergers

**Design Pattern**: Builder + Strategy (for merge operations)

**Target Complexity**: ≤15 per function (total: 9 functions)

### Decomposition Strategy

#### 1. **ExperimentRunnerBuilder** (New Coordinator Class)

**Purpose**: Replace monolithic `build_runner()` with fluent builder

**Complexity Target**: ≤12

```python
class ExperimentRunnerBuilder:
    """Fluent builder for constructing ExperimentRunner instances."""

    def __init__(
        self,
        config: ExperimentConfig,
        defaults: dict[str, Any],
        sinks: list[ResultSink],
        llm_client: LLMClientProtocol,
        suite_root: Any,
        config_path: Any,
    ):
        self.config = config
        self.defaults = defaults
        self.sinks = sinks
        self.llm_client = llm_client
        self.suite_root = suite_root
        self.config_path = config_path

        # Initialize helpers
        self.config_merger = ConfigurationMerger(defaults, config)
        self.plugin_factory = PluginFactory()
        self.context_builder = SecurityContextBuilder()

    def build(self) -> ExperimentRunner:
        """Build ExperimentRunner with merged configuration.

        Complexity: ~10 (linear method calls)
        """
        merged_config = self.config_merger.merge_all()
        experiment_context = self.context_builder.build_experiment_context(
            self.config, merged_config, self.suite_root, self.config_path
        )

        plugins = self.plugin_factory.create_all(
            merged_config, experiment_context
        )

        self._apply_context_to_sinks(self.sinks, experiment_context)
        self._validate_prompts(merged_config)

        return self._construct_runner(merged_config, plugins, experiment_context)
```

#### 2. **ConfigurationMerger** (New Class)

**Purpose**: Encapsulate three-layer configuration merge logic

**Complexity Target**: ≤12

```python
class ConfigurationMerger:
    """Merges configuration from defaults → pack → experiment."""

    def __init__(self, defaults: dict[str, Any], config: ExperimentConfig):
        self.defaults = defaults
        self.config = config
        self.pack = self._resolve_pack()

    def _resolve_pack(self) -> dict[str, Any] | None:
        """Resolve prompt pack from defaults (complexity ~5)."""
        prompt_packs = self.defaults.get("prompt_packs", {})
        pack_name = self.config.prompt_pack or self.defaults.get("prompt_pack")
        return prompt_packs.get(pack_name) if pack_name else None

    def merge_all(self) -> MergedConfiguration:
        """Merge all configuration sections.

        Complexity: ~8 (method delegation)
        """
        return MergedConfiguration(
            prompts=self._merge_prompts(),
            plugins=self._merge_plugin_defs(),
            controls=self._merge_controls(),
            concurrency=self._merge_concurrency(),
            early_stop=self._merge_early_stop(),
            security=self._merge_security(),
        )

    def _merge_prompts(self) -> PromptConfiguration:
        """Merge prompt-related config (complexity ~8)."""
        # ...

    def _merge_plugin_defs(self) -> PluginDefinitions:
        """Merge plugin definition lists (complexity ~6)."""
        # ...
```

#### 3. **PluginFactory** (New Class)

**Purpose**: Centralize plugin instantiation logic

**Complexity Target**: ≤10

```python
class PluginFactory:
    """Creates plugin instances from definitions."""

    def create_all(
        self,
        config: MergedConfiguration,
        context: PluginContext,
    ) -> PluginCollection:
        """Instantiate all plugin types.

        Complexity: ~8 (simple delegation to specialized methods)
        """
        return PluginCollection(
            row_plugins=self._create_row_plugins(config.plugins.row_defs, context),
            aggregator_plugins=self._create_aggregators(config.plugins.agg_defs, context),
            validation_plugins=self._create_validators(config.plugins.validation_defs, context),
            early_stop_plugins=self._create_early_stop(config.plugins.early_stop_defs, context),
            rate_limiter=self._create_rate_limiter(config.controls.rate_limiter_def, context),
            cost_tracker=self._create_cost_tracker(config.controls.cost_tracker_def, context),
        )

    def _create_row_plugins(self, defs, context) -> list | None:
        """Create row plugin instances (complexity ~4)."""
        return [create_row_plugin(d, parent_context=context) for d in defs] if defs else None
```

#### 4. **MiddlewareCache** (New Class)

**Purpose**: Abstract middleware caching and fingerprinting

**Complexity Target**: ≤8

```python
class MiddlewareCache:
    """Caches middleware instances by configuration fingerprint."""

    def __init__(self):
        self._cache: dict[str, Any] = {}

    def get_or_create(
        self,
        definition: dict[str, Any],
        context: PluginContext,
    ) -> Any:
        """Get cached middleware or create new instance.

        Complexity: ~6 (fingerprint computation + cache lookup)
        """
        fingerprint = self._compute_fingerprint(definition, context)

        if fingerprint not in self._cache:
            self._cache[fingerprint] = create_middleware(
                definition, parent_context=context
            )

        return self._cache[fingerprint]

    def _compute_fingerprint(self, definition, context) -> str:
        """Compute cache key from definition + context (complexity ~3)."""
        name = definition.get("name") or definition.get("plugin")
        options_json = json.dumps(definition.get("options", {}), sort_keys=True)
        return f"{name}:{options_json}:{context.security_level}"
```

#### 5. **SecurityContextBuilder** (New Class)

**Purpose**: Build and derive security contexts

**Complexity Target**: ≤10

```python
class SecurityContextBuilder:
    """Builds PluginContext instances with security level resolution."""

    def build_experiment_context(
        self,
        config: ExperimentConfig,
        merged: MergedConfiguration,
        suite_root: Any,
        config_path: Any,
    ) -> PluginContext:
        """Build experiment-level context.

        Complexity: ~6 (context construction)
        """
        return PluginContext(
            plugin_name=config.name,
            plugin_kind="experiment",
            security_level=merged.security.security_level,
            determinism_level=merged.security.determinism_level,
            provenance=(f"experiment:{config.name}.resolved",),
            suite_root=suite_root,
            config_path=config_path,
        )

    def derive_sink_context(
        self,
        sink: ResultSink,
        parent_context: PluginContext,
    ) -> PluginContext:
        """Derive context for sink plugin (complexity ~5)."""
        sink_name = getattr(sink, "_elspeth_sink_name", sink.__class__.__name__)
        sink_level = getattr(sink, "security_level", parent_context.security_level)

        return parent_context.derive(
            plugin_name=str(sink_name),
            plugin_kind="sink",
            security_level=sink_level,
            provenance=(f"sink:{sink_name}.resolved",),
        )
```

#### 6. **PromptValidator** (New Class)

**Purpose**: Validate prompt configuration

**Complexity Target**: ≤6

```python
class PromptValidator:
    """Validates prompt configuration completeness."""

    def validate(self, config: PromptConfiguration, experiment_name: str) -> None:
        """Ensure required prompts are present.

        Complexity: ~4 (simple validation checks)
        """
        if not (config.prompt_system or "").strip():
            raise ConfigurationError(
                f"Experiment '{experiment_name}' has no system prompt defined"
            )

        if not (config.prompt_template or "").strip():
            raise ConfigurationError(
                f"Experiment '{experiment_name}' has no user prompt defined"
            )
```

#### 7. **MergedConfiguration** (Data Class)

**Purpose**: Structured container for merged configuration

```python
@dataclass
class MergedConfiguration:
    """Complete merged configuration for an experiment."""

    prompts: PromptConfiguration
    plugins: PluginDefinitions
    controls: ControlConfiguration
    concurrency: dict[str, Any] | None
    early_stop: EarlyStopConfiguration
    security: SecurityConfiguration


@dataclass
class PromptConfiguration:
    prompt_system: str
    prompt_template: str
    prompt_fields: list | None
    prompt_defaults: dict[str, Any] | None
    criteria: list | None


@dataclass
class PluginDefinitions:
    row_defs: list[dict] | None
    agg_defs: list[dict] | None
    validation_defs: list[dict] | None
    early_stop_defs: list[dict] | None
    middleware_defs: list[dict] | None


@dataclass
class PluginCollection:
    row_plugins: list | None
    aggregator_plugins: list | None
    validation_plugins: list | None
    early_stop_plugins: list | None
    rate_limiter: Any | None
    cost_tracker: Any | None
```

### Refactored build_runner() Method

**New Complexity**: ≤8

```python
def build_runner(
    self,
    config: ExperimentConfig,
    defaults: dict[str, Any],
    sinks: list[ResultSink],
) -> ExperimentRunner:
    """Build ExperimentRunner using builder pattern.

    Complexity: ~6 (simple delegation to builder)
    """
    builder = ExperimentRunnerBuilder(
        config=config,
        defaults=defaults,
        sinks=sinks,
        llm_client=self.llm_client,
        suite_root=self.suite_root,
        config_path=self.config_path,
    )

    return builder.build()
```

### File Organization

```
src/elspeth/core/experiments/
├── suite_runner.py              # ExperimentSuiteRunner (simplified)
├── building/
│   ├── __init__.py
│   ├── builder.py               # ExperimentRunnerBuilder
│   ├── config_merger.py         # ConfigurationMerger
│   ├── plugin_factory.py        # PluginFactory
│   ├── middleware_cache.py      # MiddlewareCache
│   ├── context_builder.py       # SecurityContextBuilder
│   ├── validator.py             # PromptValidator
│   └── models.py                # Data classes (MergedConfiguration, etc.)
```

---

## Implementation Phases

### Phase 1: Infrastructure Setup (Week 1, Days 1-2)

**Goal**: Create new modules without breaking existing code

**Tasks**:
1. Create new directory structures:
   - `src/elspeth/core/experiments/execution/`
   - `src/elspeth/core/experiments/building/`
2. Implement data classes:
   - `PipelineContext`
   - `MergedConfiguration` and related models
   - `PluginCollection`
3. Write initial unit tests for data classes
4. **Success Criteria**: All existing tests still pass, new modules importable

### Phase 2: AUD-0007 - ExperimentRunner Refactoring (Week 1-2, Days 3-10)

**Goal**: Decompose `runner.py:run()` into pipeline stages

#### Sprint 1.1: Core Pipeline Classes (Days 3-4)

**Tasks**:
1. Implement `ExperimentExecutionPipeline`
2. Implement `PipelineContext`
3. Implement `CheckpointManager`
4. Write unit tests for checkpoint loading/saving
5. **Checkpoint**: Checkpoint tests pass with 100% coverage

#### Sprint 1.2: Pipeline Stages (Days 5-7)

**Tasks**:
1. Implement `PromptCompilationStage`
2. Implement `RowProcessingCoordinator`
3. Implement `ConcurrencyManager`
4. Implement `AggregationStage`
5. Write unit tests for each stage
6. **Checkpoint**: Stage tests pass, can execute empty pipeline

#### Sprint 1.3: Supporting Classes (Days 8-9)

**Tasks**:
1. Implement `EarlyStopEvaluator`
2. Implement `MetadataBuilder`
3. Implement `ValidationOrchestrator`
4. Implement `ResultCollector`
5. Write comprehensive unit tests
6. **Checkpoint**: All supporting classes tested

#### Sprint 1.4: Integration & Validation (Day 10)

**Tasks**:
1. Update `ExperimentRunner.run()` to use pipeline
2. Run full test suite (1,260 tests)
3. Run sample suite end-to-end
4. Compare outputs byte-for-byte with original
5. **Checkpoint**: 100% test pass rate, identical outputs

### Phase 3: AUD-0008 - ExperimentSuiteRunner Refactoring (Week 3, Days 11-17)

**Goal**: Decompose `suite_runner.py:build_runner()` into builder components

#### Sprint 2.1: Configuration Merging (Days 11-12)

**Tasks**:
1. Implement `ConfigurationMerger`
2. Implement merge methods for each config section
3. Write unit tests for merge logic (3-layer hierarchy)
4. Test edge cases (missing pack, override precedence)
5. **Checkpoint**: Config merge tests pass

#### Sprint 2.2: Plugin Creation (Days 13-14)

**Tasks**:
1. Implement `PluginFactory`
2. Implement `MiddlewareCache`
3. Implement `SecurityContextBuilder`
4. Write unit tests for plugin instantiation
5. Test middleware caching and deduplication
6. **Checkpoint**: Plugin factory tests pass

#### Sprint 2.3: Builder Integration (Days 15-16)

**Tasks**:
1. Implement `ExperimentRunnerBuilder`
2. Implement `PromptValidator`
3. Wire all components together
4. Write integration tests for builder
5. **Checkpoint**: Builder produces valid runners

#### Sprint 2.4: Integration & Validation (Day 17)

**Tasks**:
1. Update `ExperimentSuiteRunner.build_runner()` to use builder
2. Run full test suite (1,260 tests)
3. Run multi-experiment suite end-to-end
4. Validate configuration merge semantics
5. **Checkpoint**: 100% test pass rate, identical behavior

### Phase 4: SonarQube Verification (Week 4, Days 18-20)

**Goal**: Confirm complexity reduction and identify remaining issues

**Tasks**:
1. Run SonarQube analysis on refactored code
2. Verify complexity metrics:
   - `runner.py:run()` ≤15 (target: ~8)
   - `suite_runner.py:build_runner()` ≤15 (target: ~6)
3. Address any new code smells introduced
4. Document complexity improvements
5. **Success Criteria**:
   - AUD-0007: RESOLVED (complexity ≤15)
   - AUD-0008: RESOLVED (complexity ≤15)
   - No new HIGH severity issues

### Phase 5: Documentation & Review (Week 4, Days 21-22)

**Goal**: Update documentation and conduct code review

**Tasks**:
1. Update architecture docs:
   - `docs/architecture/CORE_STRUCTURE_CURRENT.md`
   - `docs/architecture/plugin-catalogue.md`
2. Update CLAUDE.md with new structure
3. Create migration guide for external users
4. Conduct peer code review
5. Update audit deliverables:
   - Mark AUD-0007, AUD-0008 as RESOLVED
   - Update `findings.json`
   - Update `executive_summary.md`

---

## Testing Strategy

### Test-Driven Refactoring Approach

**Principle**: Write tests before refactoring, maintain 100% pass rate throughout

### 1. Pre-Refactoring Test Suite

**Baseline Establishment** (Before any refactoring):

```bash
# Capture current behavior as golden reference
python -m pytest -m "not slow" --cov=elspeth --cov-report=json -o json_report_file=baseline_report.json

# Run sample suite and capture outputs
python -m elspeth.cli --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite --reports-dir outputs/baseline_reports \
  --head 0 --live-outputs

# Capture output checksums
find outputs/baseline_reports -type f -exec sha256sum {} \; > baseline_checksums.txt
```

### 2. Unit Tests for New Components

**Coverage Target**: 100% for new modules

**Test Files**:
```
tests/core/experiments/execution/
├── test_pipeline.py                 # ExperimentExecutionPipeline
├── test_pipeline_context.py         # PipelineContext
├── test_checkpoint.py               # CheckpointManager
├── test_concurrency.py              # ConcurrencyManager
├── test_stages.py                   # Pipeline stages
├── test_early_stop.py               # EarlyStopEvaluator
├── test_metadata.py                 # MetadataBuilder
└── test_result_collector.py         # ResultCollector

tests/core/experiments/building/
├── test_builder.py                  # ExperimentRunnerBuilder
├── test_config_merger.py            # ConfigurationMerger
├── test_plugin_factory.py           # PluginFactory
├── test_middleware_cache.py         # MiddlewareCache
├── test_context_builder.py          # SecurityContextBuilder
└── test_validator.py                # PromptValidator
```

**Test Patterns**:
- **Isolation**: Mock dependencies, test single responsibility
- **Edge cases**: Empty configs, missing fields, invalid inputs
- **Error handling**: Exception paths, validation failures
- **Thread safety**: Concurrent access to shared state (early stop, middleware cache)

### 3. Integration Tests

**Scope**: End-to-end experiment execution with refactored code

**Test Cases**:
1. **Single experiment with pipeline**:
   ```python
   def test_experiment_runner_pipeline_integration():
       runner = ExperimentRunner(...)
       result = runner.run(df)
       assert result["metadata"]["rows"] == len(df)
       assert "aggregates" in result
   ```

2. **Multi-experiment suite with builder**:
   ```python
   def test_suite_runner_builder_integration():
       suite_runner = ExperimentSuiteRunner(...)
       results = suite_runner.run(df, defaults)
       assert len(results) == 3  # baseline + 2 experiments
   ```

3. **Parallel execution**:
   ```python
   def test_concurrency_manager_parallel_execution():
       # Verify semaphore limiting works
       # Verify results match sequential execution
   ```

4. **Early stop across threads**:
   ```python
   def test_early_stop_thread_safety():
       # Concurrent row processing with early stop
       # Verify only one trigger event
   ```

### 4. Regression Tests

**Goal**: Ensure refactored code produces identical outputs

**Validation Strategy**:
```python
def test_refactored_output_matches_baseline():
    """Byte-for-byte comparison of experiment outputs."""
    baseline_payload = run_baseline_experiment(df)
    refactored_payload = run_refactored_experiment(df)

    # Deep equality check (ignoring timestamps)
    assert_payloads_equal(baseline_payload, refactored_payload)

def assert_payloads_equal(baseline, refactored):
    # Compare results (order-sensitive)
    assert baseline["results"] == refactored["results"]

    # Compare aggregates
    assert baseline.get("aggregates") == refactored.get("aggregates")

    # Compare metadata (excluding timestamps, run IDs)
    baseline_meta = {k: v for k, v in baseline["metadata"].items() if k not in ["timestamp", "run_id"]}
    refactored_meta = {k: v for k, v in refactored["metadata"].items() if k not in ["timestamp", "run_id"]}
    assert baseline_meta == refactored_meta
```

### 5. Performance Tests

**Goal**: Ensure refactoring doesn't degrade performance

**Benchmarks**:
```python
@pytest.mark.benchmark
def test_pipeline_execution_performance(benchmark):
    """Baseline: ~13.49s for 1260 tests."""
    result = benchmark(lambda: runner.run(df))
    assert benchmark.stats.mean < 15.0  # Allow 10% overhead
```

### 6. Continuous Validation

**CI Integration**:
```yaml
# .github/workflows/refactoring-validation.yml
name: Refactoring Validation

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run baseline tests
        run: pytest -m "not slow"

      - name: Run refactoring tests
        run: pytest tests/core/experiments/

      - name: Verify no new complexity violations
        run: |
          sonar-scanner \
            -Dsonar.qualitygate.wait=true \
            -Dsonar.qualitygate.timeout=300
```

---

## Success Criteria

### Functional Requirements

| Criterion | Measurement | Target | Verification Method |
|-----------|-------------|--------|---------------------|
| **Backward Compatibility** | Test pass rate | 100% (1,260 tests) | `pytest -m "not slow"` |
| **Output Equivalence** | Payload byte comparison | 100% match | Regression test suite |
| **Coverage Maintenance** | Line/branch coverage | ≥89%/85% | `pytest --cov` |
| **Performance** | Test execution time | ≤15s (10% overhead) | Benchmark tests |

### Complexity Reduction

| Function | Current | Target | Method | Status |
|----------|---------|--------|--------|--------|
| `runner.py:run()` | 70 | ≤15 | Pipeline decomposition | **PENDING** |
| `suite_runner.py:build_runner()` | 69 | ≤15 | Builder + Strategy | **PENDING** |

**SonarQube Validation**:
```bash
# Run SonarQube analysis
sonar-scanner \
  -Dsonar.projectKey=elspeth \
  -Dsonar.sources=src \
  -Dsonar.python.coverage.reportPaths=coverage.xml

# Expected outcome:
# - AUD-0007: RESOLVED (complexity ≤15)
# - AUD-0008: RESOLVED (complexity ≤15)
# - No new HIGH severity issues
```

### Code Quality

| Metric | Target | Verification |
|--------|--------|--------------|
| New module coverage | 100% | Per-module coverage report |
| Pylint score | ≥9.5/10 | `pylint src/elspeth/core/experiments/` |
| Type coverage | 100% | `mypy --strict src/elspeth/core/experiments/` |
| Cyclomatic complexity | ≤10 per function | Radon/SonarQube |

### Documentation

| Deliverable | Status | Location |
|-------------|--------|----------|
| Architecture update | **PENDING** | `docs/architecture/CORE_STRUCTURE_CURRENT.md` |
| Migration guide | **PENDING** | `docs/migration/v3-complexity-refactoring.md` |
| API documentation | **PENDING** | Module docstrings |
| Audit resolution | **PENDING** | `audit_data/findings.json` |

---

## Risk Mitigation

### High-Risk Areas

#### 1. **Parallel Execution Thread Safety**

**Risk**: Race conditions in early stop evaluation or middleware caching

**Mitigation**:
- Use thread-safe primitives (`threading.Lock`, `threading.Event`)
- Write comprehensive concurrency tests
- Stress test with high parallelism (`max_workers=100`)
- Add deadlock detection timeouts

**Validation**:
```python
def test_early_stop_race_condition():
    # 100 concurrent rows, all trigger early stop
    # Verify exactly 1 event is set
    # Verify all other rows are skipped
```

#### 2. **Configuration Merge Regression**

**Risk**: Three-layer merge semantics broken (defaults → pack → experiment)

**Mitigation**:
- Preserve `ConfigMerger` helper (already exists)
- Write exhaustive merge tests for each field type
- Test pack override precedence
- Validate special cases (middleware prepending, security level "most restrictive")

**Validation**:
```python
def test_config_merge_precedence():
    defaults = {"prompt_system": "default system"}
    pack = {"prompt_system": "pack system"}
    experiment = ExperimentConfig(prompt_system="experiment system")

    merged = ConfigurationMerger(defaults, experiment).merge_all()
    assert merged.prompts.prompt_system == "experiment system"  # Highest priority
```

#### 3. **Middleware Caching Behavior**

**Risk**: Shared middleware state leaks between experiments

**Mitigation**:
- Preserve existing fingerprint logic
- Test cache hit/miss scenarios
- Verify middleware isolation (different contexts = different instances)
- Document caching semantics

**Validation**:
```python
def test_middleware_cache_isolation():
    cache = MiddlewareCache()

    # Same definition, different security levels
    defn = {"name": "audit_logger", "options": {}}
    ctx1 = PluginContext(security_level="public")
    ctx2 = PluginContext(security_level="confidential")

    mw1 = cache.get_or_create(defn, ctx1)
    mw2 = cache.get_or_create(defn, ctx2)

    assert mw1 is not mw2  # Different instances for different security levels
```

#### 4. **Checkpoint Resume Logic**

**Risk**: Checkpoint loading/saving broken, lose resumability

**Mitigation**:
- Extract `CheckpointManager` early in refactoring
- Test checkpoint file corruption scenarios
- Verify `processed_ids` set behavior
- Test incremental append pattern

**Validation**:
```python
def test_checkpoint_resume():
    # Run experiment with checkpoint, process 10 rows
    # Simulate failure
    # Resume from checkpoint
    # Verify rows 1-10 skipped, rows 11-20 processed
```

### Medium-Risk Areas

#### 5. **Artifact Pipeline Integration**

**Risk**: Pipeline execution breaks sink dependency resolution

**Mitigation**:
- Keep `ArtifactPipeline` instantiation in final payload stage
- Test artifact `produces`/`consumes` flow
- Verify sink execution order

#### 6. **Retry Metadata Collection**

**Risk**: Retry summary calculation broken

**Mitigation**:
- Preserve retry metadata extraction logic in `MetadataBuilder`
- Test with mocked LLM client that returns retry info
- Verify summary fields (`total_retries`, `exhausted`)

### Low-Risk Areas

#### 7. **Prompt Template Compilation**

**Risk**: Template compilation broken (unlikely - isolated logic)

**Mitigation**:
- Preserve existing `PromptEngine` usage
- Test criteria template loop

#### 8. **Cost Tracker Integration**

**Risk**: Cost summary not attached to payload

**Mitigation**:
- Keep cost tracker finalization in `MetadataBuilder`
- Test cost accumulation

---

## Rollback Plan

### Scenario: Refactoring Causes Regression

**Trigger Conditions**:
1. Test pass rate drops below 99% (>12 failing tests)
2. SonarQube introduces new HIGH severity issues
3. Performance degradation >20% (test execution >16s)
4. Production deployment fails smoke tests

### Rollback Procedure

#### Option 1: Feature Flag Rollback

**Implementation**:
```python
# In runner.py
USE_PIPELINE = os.getenv("ELSPETH_USE_PIPELINE", "true").lower() == "true"

def run(self, df: pd.DataFrame) -> dict[str, Any]:
    if USE_PIPELINE:
        return self._run_pipeline(df)
    else:
        return self._run_legacy(df)  # Original implementation preserved
```

**Activation**:
```bash
# Disable pipeline in production
export ELSPETH_USE_PIPELINE=false
```

#### Option 2: Git Revert

**Preparation**:
1. Tag pre-refactoring commit: `git tag refactoring-baseline`
2. Create refactoring branch: `git checkout -b refactoring/complexity-reduction`
3. Keep baseline branch for comparison

**Execution**:
```bash
# Revert to baseline
git checkout remediation
git revert <refactoring-merge-commit>

# Or hard reset if no production deployments
git reset --hard refactoring-baseline
```

#### Option 3: Parallel Implementation

**Strategy**: Keep both implementations during transition period

**Structure**:
```
src/elspeth/core/experiments/
├── runner.py              # Original (preserved as runner_legacy.py)
├── runner_v2.py           # Refactored pipeline version
├── suite_runner.py        # Original (preserved as suite_runner_legacy.py)
├── suite_runner_v2.py     # Refactored builder version
```

**Transition**:
```python
# Week 1: Run both, compare outputs
runner_legacy = ExperimentRunner(...)
runner_v2 = ExperimentRunnerV2(...)

payload_legacy = runner_legacy.run(df)
payload_v2 = runner_v2.run(df)

assert_payloads_equal(payload_legacy, payload_v2)

# Week 2-3: Monitor v2 in staging
# Week 4: Switch production to v2
# Week 5: Remove legacy code
```

### Recovery Time Objective (RTO)

| Rollback Method | RTO | Risk | Recommended For |
|-----------------|-----|------|-----------------|
| Feature Flag | **<1 min** | Low | Production incidents |
| Git Revert | **<30 min** | Medium | Staging failures |
| Parallel Impl | **N/A** | Low | Phased rollout |

---

## Appendix A: Complexity Metrics

### Pre-Refactoring Baseline

| Function | File | Lines | Complexity | Nested Loops | Nested Ifs | Branches |
|----------|------|-------|------------|--------------|------------|----------|
| `run()` | `runner.py:75` | 170 | **70** | 3 | 5 | 42 |
| `build_runner()` | `suite_runner.py:47` | 186 | **69** | 2 | 4 | 38 |

### Post-Refactoring Target

#### runner.py Decomposition

| Function | Module | Complexity | Notes |
|----------|--------|------------|-------|
| `run()` (refactored) | `runner.py` | **8** | Delegates to pipeline |
| `ExperimentExecutionPipeline.execute()` | `execution/pipeline.py` | **10** | Linear stage execution |
| `CheckpointManager.load()` | `execution/checkpoint.py` | **5** | File I/O + iteration |
| `PromptCompilationStage.execute()` | `execution/stages.py` | **8** | Template compilation loop |
| `RowProcessingCoordinator.execute()` | `execution/stages.py` | **10** | Parallel vs sequential branch |
| `ConcurrencyManager.execute_parallel()` | `execution/concurrency.py` | **8** | Thread pool + semaphore |
| `AggregationStage.execute()` | `execution/aggregation.py` | **6** | Plugin loop |
| `MetadataBuilder.build()` | `execution/metadata.py` | **10** | Conditional field collection |
| `EarlyStopEvaluator.check()` | `execution/early_stop.py` | **8** | Lock + plugin loop |
| `ValidationOrchestrator.validate_schema()` | `execution/validation.py` | **6** | Schema check loop |
| `ResultCollector.get_sorted_results()` | `execution/result_collector.py` | **3** | Sort + map |

**Total Functions**: 11
**Average Complexity**: ~7.5
**Max Complexity**: 10

#### suite_runner.py Decomposition

| Function | Module | Complexity | Notes |
|----------|--------|------------|-------|
| `build_runner()` (refactored) | `suite_runner.py` | **6** | Delegates to builder |
| `ExperimentRunnerBuilder.build()` | `building/builder.py` | **10** | Linear component assembly |
| `ConfigurationMerger.merge_all()` | `building/config_merger.py` | **8** | Method delegation |
| `ConfigurationMerger._merge_prompts()` | `building/config_merger.py` | **8** | 3-layer merge with pack shorthand |
| `PluginFactory.create_all()` | `building/plugin_factory.py` | **8** | Delegation to specialized methods |
| `MiddlewareCache.get_or_create()` | `building/middleware_cache.py` | **6** | Cache lookup + creation |
| `SecurityContextBuilder.build_experiment_context()` | `building/context_builder.py` | **6** | Context construction |
| `PromptValidator.validate()` | `building/validator.py` | **4** | Simple validation checks |

**Total Functions**: 8
**Average Complexity**: ~7
**Max Complexity**: 10

---

## Appendix B: Code Examples

### Before: ExperimentRunner.run()

```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:
    """Execute the run, returning a structured payload for sinks and reports."""
    # COMPLEXITY: 70 (4.7x over threshold)

    self._init_early_stop()
    processed_ids: set[str] | None = None
    checkpoint_field = None
    checkpoint_path = None
    if self.checkpoint_config:
        checkpoint_path = Path(self.checkpoint_config.get("path", "checkpoint.jsonl"))
        checkpoint_field = self.checkpoint_config.get("field", "APPID")
        processed_ids = self._load_checkpoint(checkpoint_path)

    row_plugins = self.row_plugins or []
    engine = self.prompt_engine or PromptEngine()
    system_template = engine.compile(
        self.prompt_system or "",
        name=f"{self.experiment_name or 'experiment'}:system",
        defaults=self.prompt_defaults or {},
    )
    user_template = engine.compile(
        self.prompt_template or "",
        name=f"{self.experiment_name or 'experiment'}:user",
        defaults=self.prompt_defaults or {},
    )
    # ... 140 more lines with nested logic ...
```

### After: ExperimentRunner.run()

```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:
    """Execute experiment using pipeline orchestration.

    COMPLEXITY: ~8 (pipeline initialization + error handling)
    """
    pipeline = ExperimentExecutionPipeline(self)

    try:
        payload = pipeline.execute(df)
        return payload
    except (PromptRenderingError, PromptValidationError) as exc:
        logger.error("Experiment execution failed: %s", exc)
        raise
    finally:
        self._active_security_level = None
```

---

**END OF REFACTORING PLAN**

**Approval**: Ready for Sprint Planning
**Next Step**: Schedule Phase 1 kickoff meeting
**Owner**: Development Team Lead
**Reviewers**: Security Team, QA Team, Architecture Review Board
