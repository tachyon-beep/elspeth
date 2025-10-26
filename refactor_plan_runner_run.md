# Refactoring Plan: `runner.py:75` - `ExperimentRunner.run()`

**Target:** `src/elspeth/core/experiments/runner.py:75-245`
**Current Complexity:** 73 (SonarQube Cognitive Complexity)
**Target Complexity:** < 15
**Lines:** 171 lines → Target ~30-40 lines (orchestrator pattern)

---

## Current State Analysis

### Responsibilities (14 distinct concerns)

The `run()` method is a **God Method** that handles:

1. ✅ **Early stop initialization** (line 77)
2. 🔄 **Checkpoint management** (lines 78-84)
3. 🎨 **Prompt compilation** (lines 86-112)
4. ✔️ **Schema validation** (lines 114-117)
5. 🔢 **Row preparation** (lines 119-130)
6. ⚡ **Execution orchestration** (lines 132-176)
7. 🔌 **Plugin aggregation** (lines 182-191)
8. 📊 **Retry summary** (lines 193-216)
9. 💰 **Cost tracking** (lines 220-224)
10. 🔒 **Security resolution** (lines 228-234)
11. 🛑 **Early stop finalization** (lines 236-238)
12. 📦 **Payload assembly** (lines 181-240)
13. 🚀 **Sink dispatch** (lines 242-243)
14. 🧹 **Cleanup** (line 244)

### Complexity Sources

| Source | Line Range | Impact |
|--------|------------|--------|
| **Nested conditionals** | 81-84, 99-109, 126-129, 147-176 | Deep nesting (+20) |
| **Multiple loops** | 100-109, 123-130, 160-176, 183-189, 203-214 | Iteration complexity (+15) |
| **Embedded callbacks** | 135-144 | Hidden control flow (+8) |
| **State mutations** | Throughout | Hard to track (+10) |
| **Mixed abstraction levels** | Throughout | Low-level + high-level (+10) |
| **Long method** | 171 lines | Comprehension difficulty (+10) |

**Total Estimated Complexity:** ~73 ✅ (matches SonarQube)

---

## Refactoring Strategy: Extract Method + Template Method Pattern

### Phase 1: Extract Configuration Setup (Lines 77-117)

**Create:**
```python
@dataclass
class ExperimentContext:
    """Encapsulates compiled configuration for an experiment run."""
    engine: PromptEngine
    system_template: PromptTemplate
    user_template: PromptTemplate
    criteria_templates: dict[str, PromptTemplate]
    checkpoint_manager: CheckpointManager | None
    row_plugins: list[RowExperimentPlugin]

def _setup_experiment_context(
    self, df: pd.DataFrame
) -> ExperimentContext:
    """Initialize and compile all experiment configuration.

    Complexity: ~8 (target: < 10)
    """
    self._init_early_stop()

    checkpoint_mgr = None
    if self.checkpoint_config:
        checkpoint_mgr = CheckpointManager(
            path=Path(self.checkpoint_config.get("path", "checkpoint.jsonl")),
            field=self.checkpoint_config.get("field", "APPID")
        )

    engine = self.prompt_engine or PromptEngine()
    system_template = self._compile_system_prompt(engine)
    user_template = self._compile_user_prompt(engine)
    criteria_templates = self._compile_criteria_prompts(engine)

    # Schema validation
    datasource_schema = df.attrs.get("schema") if hasattr(df, "attrs") else None
    if datasource_schema:
        self._validate_plugin_schemas(datasource_schema)

    return ExperimentContext(
        engine=engine,
        system_template=system_template,
        user_template=user_template,
        criteria_templates=criteria_templates,
        checkpoint_manager=checkpoint_mgr,
        row_plugins=self.row_plugins or [],
    )
```

**Benefits:**
- Reduces main method complexity by ~15
- Groups related configuration logic
- Returns immutable context object
- Clear separation of concerns

---

### Phase 2: Extract Checkpoint Management (New Class)

**Create:**
```python
@dataclass
class CheckpointManager:
    """Manages checkpoint loading, tracking, and persistence."""
    path: Path
    field: str
    _processed_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Load existing checkpoint on initialization."""
        if self.path.exists():
            self._processed_ids = self._load_checkpoint()

    def _load_checkpoint(self) -> set[str]:
        """Load processed IDs from checkpoint file."""
        processed: set[str] = set()
        with self.path.open("r") as f:
            for line in f:
                data = json.loads(line)
                processed.add(data["id"])
        return processed

    def is_processed(self, row_id: str) -> bool:
        """Check if a row has already been processed."""
        return row_id in self._processed_ids

    def mark_processed(self, row_id: str) -> None:
        """Mark a row as processed and persist to checkpoint."""
        if row_id not in self._processed_ids:
            self._processed_ids.add(row_id)
            self._append_checkpoint(row_id)

    def _append_checkpoint(self, row_id: str) -> None:
        """Append a single checkpoint entry."""
        with self.path.open("a") as f:
            f.write(json.dumps({"id": row_id}) + "\n")
```

**Benefits:**
- Encapsulates checkpoint state
- Self-contained persistence logic
- Testable in isolation
- Clear API: `is_processed()`, `mark_processed()`

---

### Phase 3: Extract Row Preparation (Lines 119-130)

**Create:**
```python
@dataclass
class RowBatch:
    """Collection of rows ready for processing."""
    rows: list[tuple[int, pd.Series, dict[str, Any], str | None]]

    @property
    def count(self) -> int:
        return len(self.rows)

def _prepare_row_batch(
    self,
    df: pd.DataFrame,
    checkpoint_mgr: CheckpointManager | None,
) -> RowBatch:
    """Filter and prepare rows for processing.

    Complexity: ~6 (target: < 10)
    """
    self._malformed_rows = []
    rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        # Early stop check
        if self._early_stop_event and self._early_stop_event.is_set():
            break

        # Prepare row context
        context = prepare_prompt_context(row, include_fields=self.prompt_fields)
        row_id = context.get(checkpoint_mgr.field) if checkpoint_mgr else None

        # Skip checkpointed rows
        if checkpoint_mgr and row_id and checkpoint_mgr.is_processed(row_id):
            continue

        rows_to_process.append((idx, row, context, row_id))

    return RowBatch(rows=rows_to_process)
```

**Benefits:**
- Single responsibility: row filtering
- Clear early returns
- Encapsulated batch as return value
- Complexity ~6

---

### Phase 4: Extract Execution Orchestration (Lines 132-179)

**Create:**
```python
@dataclass
class ProcessingResult:
    """Results from row processing execution."""
    records: list[dict[str, Any]]
    failures: list[dict[str, Any]]

def _execute_row_processing(
    self,
    batch: RowBatch,
    context: ExperimentContext,
    checkpoint_mgr: CheckpointManager | None,
) -> ProcessingResult:
    """Execute row processing (parallel or sequential).

    Complexity: ~10 (target: < 15)
    """
    records_with_index: list[tuple[int, dict[str, Any]]] = []
    failures: list[dict[str, Any]] = []

    # Create result handlers
    handlers = self._create_result_handlers(
        records_with_index,
        failures,
        checkpoint_mgr,
    )

    # Execute
    concurrency_cfg = self.concurrency_config or {}
    if batch.count > 0 and self._should_run_parallel(concurrency_cfg, batch.count):
        self._run_parallel(
            batch.rows,
            context.engine,
            context.system_template,
            context.user_template,
            context.criteria_templates,
            context.row_plugins,
            handlers.on_success,
            handlers.on_failure,
            concurrency_cfg,
        )
    else:
        self._run_sequential(
            batch.rows,
            context,
            handlers,
        )

    # Sort and extract results
    records_with_index.sort(key=lambda item: item[0])
    results = [record for _, record in records_with_index]

    return ProcessingResult(records=results, failures=failures)
```

**Supporting Classes:**
```python
@dataclass
class ResultHandlers:
    """Callback handlers for row processing results."""
    on_success: Callable[[int, dict[str, Any], str | None], None]
    on_failure: Callable[[dict[str, Any]], None]

def _create_result_handlers(
    self,
    records_storage: list[tuple[int, dict[str, Any]]],
    failures_storage: list[dict[str, Any]],
    checkpoint_mgr: CheckpointManager | None,
) -> ResultHandlers:
    """Create success and failure handlers for row processing."""

    def handle_success(idx: int, record: dict[str, Any], row_id: str | None) -> None:
        records_storage.append((idx, record))
        if checkpoint_mgr and row_id:
            checkpoint_mgr.mark_processed(row_id)
        self._maybe_trigger_early_stop(record, row_index=idx)

    def handle_failure(failure: dict[str, Any]) -> None:
        failures_storage.append(failure)

    return ResultHandlers(
        on_success=handle_success,
        on_failure=handle_failure,
    )

def _run_sequential(
    self,
    rows: list[tuple[int, pd.Series, dict[str, Any], str | None]],
    context: ExperimentContext,
    handlers: ResultHandlers,
) -> None:
    """Execute row processing sequentially."""
    for idx, row, row_context, row_id in rows:
        if self._early_stop_event and self._early_stop_event.is_set():
            break

        record, failure = self._process_single_row(
            context.engine,
            context.system_template,
            context.user_template,
            context.criteria_templates,
            context.row_plugins,
            row_context,
            row,
            row_id,
        )

        if record:
            handlers.on_success(idx, record, row_id)
        if failure:
            handlers.on_failure(failure)
```

**Benefits:**
- Parallel vs sequential logic isolated
- Handlers encapsulated in dataclass
- Clear sequential execution flow
- Complexity ~10

---

### Phase 5: Extract Metadata Assembly (Lines 193-238)

**Create:**
```python
@dataclass
class ExecutionMetadata:
    """Metadata about experiment execution."""
    rows: int
    row_count: int
    retry_summary: dict[str, int] | None = None
    cost_summary: dict[str, Any] | None = None
    failures: list[dict[str, Any]] | None = None
    aggregates: dict[str, Any] | None = None
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None
    early_stop: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

def _build_execution_metadata(
    self,
    df: pd.DataFrame,
    results: ProcessingResult,
    aggregates: dict[str, Any],
) -> ExecutionMetadata:
    """Assemble metadata from execution results.

    Complexity: ~8 (target: < 10)
    """
    metadata = ExecutionMetadata(
        rows=len(results.records),
        row_count=len(results.records),
    )

    # Retry summary
    retry_summary = self._calculate_retry_summary(results)
    if retry_summary:
        metadata.retry_summary = retry_summary

    # Cost tracking
    if self.cost_tracker:
        summary = self.cost_tracker.summary()
        if summary:
            metadata.cost_summary = summary

    # Failures
    if results.failures:
        metadata.failures = results.failures

    # Aggregates
    if aggregates:
        metadata.aggregates = aggregates

    # Security/determinism levels
    metadata.security_level = self._resolve_security_level(df)
    metadata.determinism_level = self._resolve_determinism_level(df)

    # Early stop
    if self._early_stop_reason:
        metadata.early_stop = dict(self._early_stop_reason)

    return metadata

def _calculate_retry_summary(self, results: ProcessingResult) -> dict[str, int] | None:
    """Calculate retry statistics from results."""
    retry_summary: dict[str, int] = {
        "total_requests": len(results.records) + len(results.failures),
        "total_retries": 0,
        "exhausted": len(results.failures),
    }

    retry_present = False

    # Count retries in successful results
    for record in results.records:
        info = record.get("retry")
        if info:
            retry_present = True
            attempts = int(info.get("attempts", 1))
            retry_summary["total_retries"] += max(attempts - 1, 0)

    # Count retries in failures
    for failure in results.failures:
        info = failure.get("retry")
        if info:
            retry_present = True
            attempts = int(info.get("attempts", 0))
            retry_summary["total_retries"] += max(attempts - 1, 0)

    return retry_summary if retry_present else None

def _resolve_security_level(self, df: pd.DataFrame) -> SecurityLevel:
    """Resolve final security level from DataFrame and config."""
    df_security_level = getattr(df, "attrs", {}).get("security_level") if hasattr(df, "attrs") else None
    self._active_security_level = resolve_security_level(self.security_level, df_security_level)
    return self._active_security_level

def _resolve_determinism_level(self, df: pd.DataFrame) -> DeterminismLevel:
    """Resolve final determinism level from DataFrame and config."""
    df_determinism_level = getattr(df, "attrs", {}).get("determinism_level") if hasattr(df, "attrs") else None
    self._active_determinism_level = resolve_determinism_level(self.determinism_level, df_determinism_level)
    return self._active_determinism_level
```

**Benefits:**
- Metadata construction isolated
- Each component independently testable
- Clear data flow
- Type-safe with dataclass

---

### Phase 6: Extract Aggregation (Lines 182-191)

**Create:**
```python
def _run_aggregators(
    self, results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Execute aggregation plugins on results.

    Complexity: ~5 (target: < 10)
    """
    aggregates: dict[str, Any] = {}

    for plugin in self.aggregator_plugins or []:
        derived = plugin.finalize(results)
        if not derived:
            continue

        # Standardize: ensure failures key exists
        if isinstance(derived, dict) and "failures" not in derived:
            derived["failures"] = []

        aggregates[plugin.name] = derived

    return aggregates
```

**Benefits:**
- Single responsibility
- Clear loop logic
- Complexity ~5

---

## Final Refactored Method

After all extractions, the main `run()` method becomes:

```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:
    """Execute the experiment run, returning a structured payload for sinks.

    This orchestrator method coordinates the experiment execution pipeline:
    1. Setup: Initialize configuration and compile prompts
    2. Prepare: Filter and prepare rows for processing
    3. Execute: Process rows (parallel or sequential)
    4. Aggregate: Run aggregation plugins
    5. Finalize: Assemble metadata and dispatch to sinks

    Complexity: ~8 (down from 73)
    """
    # 1. Setup
    context = self._setup_experiment_context(df)

    # 2. Prepare
    batch = self._prepare_row_batch(df, context.checkpoint_manager)

    # 3. Execute
    results = self._execute_row_processing(batch, context, context.checkpoint_manager)

    # 4. Aggregate
    aggregates = self._run_aggregators(results.records)

    # 5. Finalize
    metadata = self._build_execution_metadata(df, results, aggregates)
    payload = self._assemble_payload(results, aggregates, metadata)

    # 6. Dispatch
    self._dispatch_to_sinks(payload, metadata.to_dict())

    # 7. Cleanup
    self._active_security_level = None

    return payload

def _assemble_payload(
    self,
    results: ProcessingResult,
    aggregates: dict[str, Any],
    metadata: ExecutionMetadata,
) -> dict[str, Any]:
    """Assemble final payload structure."""
    payload: dict[str, Any] = {
        "results": results.records,
        "failures": results.failures,
        "metadata": metadata.to_dict(),
    }

    if aggregates:
        payload["aggregates"] = aggregates

    if self.cost_tracker:
        summary = self.cost_tracker.summary()
        if summary:
            payload["cost_summary"] = summary

    if self._early_stop_reason:
        payload["early_stop"] = dict(self._early_stop_reason)

    return payload

def _dispatch_to_sinks(self, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
    """Execute the artifact pipeline to dispatch results to sinks."""
    pipeline = ArtifactPipeline(self._build_sink_bindings())
    pipeline.execute(payload, metadata)
```

---

## Refactoring Steps (Implementation Order)

### Step 1: Create Supporting Classes
- [ ] Create `CheckpointManager` class
- [ ] Create `ExperimentContext` dataclass
- [ ] Create `RowBatch` dataclass
- [ ] Create `ProcessingResult` dataclass
- [ ] Create `ResultHandlers` dataclass
- [ ] Create `ExecutionMetadata` dataclass

**Estimated Time:** 2 hours
**Risk:** Low (new code, no changes to existing)

---

### Step 2: Extract Helper Methods (Bottom-Up)
- [ ] Extract `_calculate_retry_summary()`
- [ ] Extract `_resolve_security_level()`
- [ ] Extract `_resolve_determinism_level()`
- [ ] Extract `_run_aggregators()`
- [ ] Extract `_compile_system_prompt()`
- [ ] Extract `_compile_user_prompt()`
- [ ] Extract `_compile_criteria_prompts()`

**Estimated Time:** 3 hours
**Risk:** Low (simple extractions)

---

### Step 3: Extract Complex Methods
- [ ] Extract `_setup_experiment_context()`
- [ ] Extract `_prepare_row_batch()`
- [ ] Extract `_create_result_handlers()`
- [ ] Extract `_run_sequential()`
- [ ] Extract `_execute_row_processing()`
- [ ] Extract `_build_execution_metadata()`
- [ ] Extract `_assemble_payload()`
- [ ] Extract `_dispatch_to_sinks()`

**Estimated Time:** 4 hours
**Risk:** Medium (logic restructuring)

---

### Step 4: Refactor Main Method
- [ ] Replace `run()` body with orchestrator calls
- [ ] Verify all paths covered
- [ ] Update docstring

**Estimated Time:** 1 hour
**Risk:** Medium (integration point)

---

### Step 5: Testing & Validation
- [ ] Run existing test suite (`pytest tests/test_experiments.py -v`)
- [ ] Add tests for new helper methods
- [ ] Verify complexity reduction in SonarQube
- [ ] Run full test suite (`make test`)
- [ ] Check mypy type coverage

**Estimated Time:** 3 hours
**Risk:** Low (existing tests should pass)

---

## Complexity Reduction Estimate

| Method | Before | After | Reduction |
|--------|--------|-------|-----------|
| `run()` | 73 | **~8** | -65 (-89%) |
| `_setup_experiment_context()` | - | ~8 | New |
| `_prepare_row_batch()` | - | ~6 | New |
| `_execute_row_processing()` | - | ~10 | New |
| `_build_execution_metadata()` | - | ~8 | New |
| `_run_aggregators()` | - | ~5 | New |
| Other helpers | - | ~3 each | New |

**Total Complexity:** Distributed across 12 small, focused methods

---

## Testing Strategy

### Unit Tests for New Methods
```python
def test_checkpoint_manager_tracks_processed_ids():
    mgr = CheckpointManager(path=Path("test.jsonl"), field="id")
    assert not mgr.is_processed("row1")
    mgr.mark_processed("row1")
    assert mgr.is_processed("row1")

def test_calculate_retry_summary_with_retries():
    results = ProcessingResult(
        records=[{"retry": {"attempts": 3}}],
        failures=[{"retry": {"attempts": 2}}],
    )
    summary = runner._calculate_retry_summary(results)
    assert summary["total_retries"] == 3  # (3-1) + (2-1)

def test_run_aggregators_standardizes_failures():
    class TestAgg:
        name = "test"
        def finalize(self, results):
            return {"data": [1, 2, 3]}

    runner.aggregator_plugins = [TestAgg()]
    aggregates = runner._run_aggregators([])
    assert "failures" in aggregates["test"]
```

### Integration Tests
```python
def test_run_with_checkpointing(tmp_path):
    """Verify checkpointing works end-to-end after refactor."""
    checkpoint_path = tmp_path / "checkpoint.jsonl"
    runner = ExperimentRunner(
        llm_client=mock_llm,
        sinks=[],
        prompt_system="Test",
        prompt_template="Test {{ field }}",
        checkpoint_config={"path": str(checkpoint_path), "field": "id"},
    )

    df = pd.DataFrame([{"id": "1", "field": "A"}, {"id": "2", "field": "B"}])
    result = runner.run(df)

    assert len(result["results"]) == 2
    assert checkpoint_path.exists()

    # Second run should skip already processed
    result2 = runner.run(df)
    assert len(result2["results"]) == 0
```

---

## Benefits

### Code Quality
- ✅ **Cognitive Complexity:** 73 → 8 (-89%)
- ✅ **Method Length:** 171 lines → ~35 lines (-80%)
- ✅ **Single Responsibility:** Each method has one clear purpose
- ✅ **Testability:** Each component testable in isolation
- ✅ **Readability:** High-level orchestration logic clear

### Maintainability
- ✅ **Easier to understand:** Clear step-by-step flow
- ✅ **Easier to modify:** Change one aspect without affecting others
- ✅ **Easier to test:** Small, focused tests
- ✅ **Easier to debug:** Clear boundaries between phases

### Performance
- ✅ **No performance impact:** Same logic, just reorganized
- ✅ **Potential improvement:** Easier to optimize individual methods

---

## Risk Mitigation

### Risk 1: Breaking Existing Behavior
**Mitigation:**
- Extract methods one at a time
- Run tests after each extraction
- Use identical logic in extracted methods
- Comprehensive integration tests

### Risk 2: Missing Edge Cases
**Mitigation:**
- Careful code review of conditionals
- Run test suite with coverage
- Test with real experiment configurations
- Verify checkpoint, early-stop, retry paths

### Risk 3: Performance Regression
**Mitigation:**
- Benchmark before and after
- Profile critical paths
- Ensure no unnecessary object creation
- Dataclasses are efficient

---

## Success Criteria

- [ ] SonarQube cognitive complexity < 15 for `run()`
- [ ] All existing tests pass
- [ ] No performance regression (< 5% overhead)
- [ ] MyPy type checking passes
- [ ] Code coverage maintained or improved
- [ ] Peer review approval

---

**Total Estimated Effort:** 13 hours (2 days)
**Priority:** CRITICAL
**Impact:** Very High (core orchestration code)

---

**Next Steps:**
1. Review this plan with team
2. Create feature branch: `refactor/runner-run-method`
3. Implement Step 1 (supporting classes)
4. Incremental commits with tests
5. Submit PR for review

---

*Generated by Claude Code - Refactoring Analysis*
