# Plugin Architecture & ClassifiedDataFrame Migration Analysis

## Executive Summary

The Elspeth system processes data through a plugin-based architecture with **70 plugin files** organized into:
- **3 plugin node types** (Sources, Transforms, Sinks) with **16 sink implementations**
- **LLM transform layer** with **6 middleware plugins**
- **Experiment plugins** (row, aggregator, baseline, validation, early-stop)
- **Orchestration layer** coordinating the entire flow

Currently, all plugins work with **raw pandas DataFrames** and plain **dict[str, Any]** objects. The migration to ClassifiedDataFrame/ClassifiedData containers requires updates to data passing patterns throughout the entire pipeline.

---

## 1. PLUGIN INVENTORY

### 1.1 Source Plugins (Datasources)
**Location**: `/home/john/elspeth/src/elspeth/plugins/nodes/sources/`

| Plugin | File | Pattern | Returns |
|--------|------|---------|---------|
| CSV (Base) | `_csv_base.py` | Base class | `pd.DataFrame` |
| CSV (Local) | `csv_local.py` | Factory/wrapper | `pd.DataFrame` |
| CSV (Blob) | `csv_blob.py` | Factory/wrapper | `pd.DataFrame` |
| Blob Store | `blob.py` | Azure/GCS loader | `pd.DataFrame` |

**Key Data Contract**:
```python
class DataSource(Protocol):
    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""
```

**Current Behavior**:
- Sources load raw DataFrames with no classification metadata
- Security level is stored as instance attribute: `self.security_level`
- Framework applies DataFrame-level attrs: `df.attrs['security_level']`

**Migration Impact**:
- Need to wrap DataFrame in `ClassifiedDataFrame.create_from_datasource(df, security_level)`
- Must return `ClassifiedDataFrame` instead of raw `pd.DataFrame`
- Orchestrator (`orchestrator.py` line 159) currently calls `df = self.datasource.load()`

### 1.2 Sink Plugins (Result Sinks)
**Location**: `/home/john/elspeth/src/elspeth/plugins/nodes/sinks/`

**16 Sink Implementations**:
1. `csv_file.py` - CSV output
2. `excel.py` - Excel workbooks
3. `blob.py` - Azure Blob storage (2 classes: `BlobResultSink`, `AzureBlobArtifactsSink`)
4. `analytics_report.py` - Analytics artifacts
5. `visual_report.py` - Visual analytics
6. `enhanced_visual_report.py` - Enhanced visuals
7. `embeddings_store.py` - Vector embeddings
8. `local_bundle.py` - Local zip bundles
9. `repository.py` - GitHub/Azure DevOps (3 classes: `GitHubRepoSink`, `AzureDevOpsRepoSink`, `AzureDevOpsArtifactsRepoSink`)
10. `reproducibility_bundle.py` - Reproducibility bundles
11. `signed.py` - Signed artifacts
12. `zip_bundle.py` - Zip bundles
13. `file_copy.py` - File copying
14. `_sanitize.py` - Helper for formula injection protection
15. `_visual_base.py` - Base class for visual sinks

**Key Data Contract**:
```python
class ResultSink(Protocol):
    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Persist experiment results."""
    
    def produces(self) -> list[ArtifactDescriptor]: # optional
    def consumes(self) -> list[str]: # optional
    def finalize(self, artifacts: Mapping[str, Artifact]) -> None: # optional
    def collect_artifacts(self) -> dict[str, Artifact]: # optional
```

**Current Behavior**:
- All sinks accept `results: dict[str, Any]` containing:
  - `"results"`: List of row-level result dicts
  - `"failures"`: List of failure dicts
  - `"aggregates"`: Dict of aggregation results (optional)
  - `"cost_summary"`: Cost tracking data (optional)
  - `"metadata"`: Execution metadata with security/determinism levels
- Sinks access individual row dicts via `results["results"]` iteration
- No direct access to DataFrame-level data

**Migration Impact**:
- Data at sink level is **already dict-based** (not DataFrame)
- Classification metadata flows through `metadata["security_level"]` (scalar)
- Sinks don't need direct `ClassifiedDataFrame` access
- But they need awareness of `ClassifiedData` for individual row/record fields
- Artifact pipeline (`artifact_pipeline.py`) manages security levels for artifacts

### 1.3 Transform Plugins

#### LLM Transforms
**Location**: `/home/john/elspeth/src/elspeth/plugins/nodes/transforms/llm/`

| Plugin | File | Purpose |
|--------|------|---------|
| Azure OpenAI | `azure_openai.py` | LLM client for Azure |
| OpenAI HTTP | `openai_http.py` | HTTP-based OpenAI client |
| Static | `static.py` | Test/mock LLM client |
| Mock | `mock.py` | Mock responses |

**Key Data Contract**:
```python
class LLMClientProtocol(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the model and return a response payload."""
```

**Current Behavior**:
- LLM clients receive prompts as strings
- Return dict with `"content"`, `"metrics"`, `"raw"` keys
- Prompts are built from DataFrame row context in `runner.py` lines 654-663
- Row data flows as context dict to prompt template engine

**Migration Impact**:
- Prompts themselves are already string-based (no DataFrame data directly)
- LLM clients don't need ClassifiedDataFrame access
- But middleware needs to inspect row-level ClassifiedData

#### LLM Middleware
**Location**: `/home/john/elspeth/src/elspeth/plugins/nodes/transforms/llm/middleware/`

**6 Middleware Plugins**:
1. `classified_material.py` - Detect classified markings
2. `pii_shield.py` - PII masking
3. `prompt_shield.py` - Prompt injection detection
4. `health_monitor.py` - Health monitoring
5. `audit.py` - Audit logging
6. `azure_content_safety.py` - Azure content safety

**Key Data Contract**:
```python
class LLMMiddleware(Protocol):
    name: str
    
    def before_request(self, request: LLMRequest) -> LLMRequest:
        """Process request before LLM call."""
    
    def after_response(
        self, request: LLMRequest, response: dict[str, Any]
    ) -> dict[str, Any]:
        """Process response after LLM call."""

@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any]  # Contains row context
```

**Current Behavior**:
- Middleware receives `LLMRequest` with prompts and metadata dict
- Metadata dict contains row context (e.g., `{"row_id": "...", "scores": {...}}`)
- No direct access to DataFrame

**Migration Impact**:
- Row context in `LLMRequest.metadata` could be wrapped in `ClassifiedData`
- Middleware would need to unwrap and re-wrap with uplifting
- Most critical for `classified_material.py` and `pii_shield.py`

#### Other Transforms
**Location**: `/home/john/elspeth/src/elspeth/plugins/orchestrators/experiment/`

**Row Experiment Plugins** (processes individual rows):
```python
class RowExperimentPlugin(Protocol):
    def process_row(
        self, 
        row: dict[str, Any], 
        responses: dict[str, Any]
    ) -> dict[str, Any]:
        """Return derived metrics for a single row."""
```

**Aggregation Experiment Plugins** (processes all rows):
```python
class AggregationExperimentPlugin(Protocol):
    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Produce aggregate analytics from collected row results."""
```

**Current Behavior**:
- Row plugins receive row dict and LLM responses dict
- Aggregators receive list of result dicts
- All work with dict-based data

**Migration Impact**:
- Row data dicts could be wrapped in `ClassifiedData`
- Aggregators would receive `ClassifiedData[dict]` instead of plain dicts
- 9 baseline plugins (in `plugins/experiments/baseline/`) work with aggregates
- 6 aggregator plugins (in `plugins/experiments/aggregators/`) compute aggregates

---

## 2. CURRENT DATA PASSING PATTERNS

### 2.1 End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DATASOURCE LOAD                                              │
├─────────────────────────────────────────────────────────────────┤
│ datasource.load() -> pd.DataFrame                               │
│ - Raw data from CSV/Blob                                        │
│ - Security level stored as df.attrs['security_level']           │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. ROW PROCESSING (orchestrator.py:179, runner.py:767)          │
├─────────────────────────────────────────────────────────────────┤
│ For each row:                                                   │
│   a) Extract row dict from DataFrame                            │
│   b) Build context: context = {field: row[field], ...}         │
│   c) Render prompts with context                                │
│   d) Call LLM via middleware chain                              │
│      - before_request() processes request                       │
│      - LLM generates response                                   │
│      - after_response() processes response                      │
│   e) Validate response (validation plugins)                     │
│   f) Process row with row plugins (returns derived dict)        │
│   g) Accumulate result dict with original row data              │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. AGGREGATION (runner.py:401)                                  │
├─────────────────────────────────────────────────────────────────┤
│ aggregator.finalize(list[dict]) -> dict                         │
│ - Receives all result dicts                                     │
│ - Computes statistics/aggregates                                │
│ - Returns aggregate dict                                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. PAYLOAD ASSEMBLY (runner.py:796)                             │
├─────────────────────────────────────────────────────────────────┤
│ payload = {                                                     │
│   "results": list[dict],           # Row results               │
│   "failures": list[dict],          # Failed rows               │
│   "aggregates": dict,              # Aggregate metrics          │
│   "cost_summary": dict,            # Optional: cost tracking    │
│   "early_stop": dict,              # Optional: early stop info  │
│   "metadata": {                    # Metadata dict              │
│       "security_level": SecurityLevel,                         │
│       "determinism_level": DeterminismLevel,                   │
│       "processed_rows": int,                                    │
│       "total_rows": int,                                        │
│       ...                                                       │
│   }                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. ARTIFACT PIPELINE & SINK DISPATCH (runner.py:814)            │
├─────────────────────────────────────────────────────────────────┤
│ artifact_pipeline.execute(payload, metadata)                    │
│   For each sink:                                                │
│     a) Artifact resolution (dependency ordering)                │
│     b) sink.write(payload, metadata=metadata)                   │
│     c) sink.collect_artifacts() (optional)                      │
│     d) sink.finalize(artifacts) (optional)                      │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. SINK OUTPUT                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Various output formats:                                         │
│ - CSV files                                                     │
│ - Excel spreadsheets                                            │
│ - Azure Blob storage                                            │
│ - Git repositories                                              │
│ - Vector embeddings stores                                      │
│ - Signed artifacts                                              │
│ etc.                                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 DataFrame/Dict Usage by Layer

#### Datasource Layer (Sources)
```python
# Current: csv_local.py
def load(self) -> pd.DataFrame:
    df = pd.read_csv(...)
    df.attrs['security_level'] = self.security_level
    return df

# Migration: Must change to
def load(self) -> ClassifiedDataFrame:
    df = pd.read_csv(...)
    return ClassifiedDataFrame.create_from_datasource(
        df, 
        SecurityLevel(self.security_level)
    )
```

#### Row Processing Layer (Runner)
```python
# Current: runner.py lines 654-663
for idx, row, context, row_id in rows_to_process:
    record, failure = self._process_single_row(
        engine, system_template, user_template,
        criteria_templates, row_plugins,
        context,  # dict[str, Any]
        row,      # pd.Series
        row_id,   # str
    )
    # record and failure are dict[str, Any]

# Migration: row could be ClassifiedData[pd.Series]
# context could be ClassifiedData[dict[str, Any]]
# But this requires ClassifiedData to support rows/dicts
```

#### LLM Transform Layer (Middleware)
```python
# Current: middleware receives LLMRequest
@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any]  # Contains row context

# The metadata dict contains row-level data:
# {"row_id": "...", "field1": value1, "field2": value2, ...}

# Migration: metadata could be ClassifiedData[dict]
# Middleware would need to:
# 1. Unwrap: unwrapped = request.metadata.data
# 2. Process: processed = transform(unwrapped)
# 3. Re-wrap with uplifting: 
#    request.metadata.with_uplifted_classification(plugin_level)
```

#### Aggregation Layer
```python
# Current: runner.py:401
def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
    # records is list of result dicts
    criteria_values: dict[str, dict[str, Any]] = {}
    for record in records:
        metrics = record.get("metrics") or {}
        scores = metrics.get("scores")
        # Process scores...

# Migration: records could be list[ClassifiedData[dict]]
# Would need to unwrap for processing:
for classified_record in records:
    record = classified_record.data  # or .unwrap()
    metrics = record.get("metrics") or {}
```

#### Sink Layer
```python
# Current: csv_file.py:137
def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
    rows = results.get("results", [])
    for row_result in rows:
        # Extract fields and write to CSV
        df_data.append(row_result)

# Migration: Row result dicts could contain ClassifiedData fields
# But sinks can pass metadata.security_level to artifacts
# No need to change core sink logic if we uplift at aggregation boundary
```

---

## 3. ENGINE/RUNNER FILES

### 3.1 Orchestration Layer

**File**: `/home/john/elspeth/src/elspeth/core/orchestrator.py` (181 lines)

**Responsibilities**:
- Creates datasources, LLM clients, sinks from configuration
- Applies security/determinism context to all plugins
- Manages middleware creation and registration
- Entry point: `run()` method (line 156)

**Data Flow in orchestrator.py**:
```python
def run(self) -> dict[str, Any]:
    df = self.datasource.load()  # Line 159 - CRITICAL
    if self.config.max_rows is not None:
        df = df.head(self.config.max_rows)  # Line 163
    
    # Dispatch to runner
    payload = runner.run(df)  # Line 179
    return payload
```

**Migration Points**:
1. Line 159: `datasource.load()` must return `ClassifiedDataFrame` (or still DataFrame?)
2. Line 163: If ClassifiedDataFrame, need method to handle `.head()` slicing
3. Line 179: `runner.run(df)` - runner expects DataFrame, may need to handle ClassifiedDataFrame

### 3.2 Experiment Runner

**File**: `/home/john/elspeth/src/elspeth/core/experiments/runner.py` (950+ lines)

**Key Classes**:
- `ExperimentRunner` (line 275) - Main orchestrator for experiment execution
- `CheckpointManager` (line 37) - Row-level checkpoint tracking
- `ExperimentContext` (line 206) - Internal context for row processing
- `RowBatch` (line 218) - Collection of rows
- `ProcessingResult` (line 230) - Results from processing
- `ResultHandlers` (line 238) - Callbacks for success/failure
- `ExecutionMetadata` (line 246) - Metadata about execution

**Key Methods**:
```python
def run(self, df: pd.DataFrame) -> dict[str, Any]:  # Line 767
    # Main execution entry point
    # Returns payload with results, aggregates, metadata

def _prepare_rows_to_process(self, df: pd.DataFrame, ...) -> list[tuple[...]]:  # Line 471
    # Extract rows to process from DataFrame

def _execute_row_processing(self, rows_to_process, ...) -> ProcessingResult:  # Line 687
    # Process rows (sequential or parallel)

def _process_single_row(...) -> tuple[dict, dict]:  # Line 721
    # Process one row and return (result_dict, failure_dict)

def _run_aggregation(self, results: list[dict]) -> dict:  # Line 401
    # Run aggregation plugins

def _assemble_metadata(self, results, failures, aggregates, df) -> ExecutionMetadata:  # Line 417
    # Build metadata object
```

**Data Handling**:
```python
# Line 781: Extract rows from DataFrame
rows_to_process = self._prepare_rows_to_process(df, checkpoint_manager)
# rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]]
#                       (index, row, context, row_id)

# Line 784-792: Process rows
processing_result = self._execute_row_processing(
    rows_to_process,
    engine, system_template, user_template, criteria_templates,
    row_plugins, checkpoint_manager
)

# Line 793-799: Extract results and run aggregation
results = processing_result.records  # list[dict[str, Any]]
aggregates = self._run_aggregation(results)

# Line 802: Assemble metadata
metadata_obj = self._assemble_metadata(results, failures, aggregates, df)

# Line 814: Dispatch to sinks
self._dispatch_to_sinks(payload, metadata)
```

**Migration Impact**:
- Must accept `ClassifiedDataFrame | pd.DataFrame` in `run()` method (line 767)
- `_prepare_rows_to_process()` needs to handle ClassifiedDataFrame
- Row processing chain needs to propagate ClassifiedData through row/context dicts
- Aggregation plugins need to handle ClassifiedData-wrapped dicts
- Result dicts might contain ClassifiedData fields

### 3.3 Suite Runner

**File**: `/home/john/elspeth/src/elspeth/core/experiments/suite_runner.py`

**Purpose**: Coordinates multiple experiments (not detailed here, but relevant for suite-level data flow)

### 3.4 Job Runner

**File**: `/home/john/elspeth/src/elspeth/core/experiments/job_runner.py`

**Purpose**: Manages job scheduling and execution (not detailed here)

---

## 4. MIDDLEWARE INTEGRATION

### 4.1 Middleware Architecture

**Location**: `/home/john/elspeth/src/elspeth/core/registries/middleware.py`

**Registry Functions**:
```python
def register_middleware(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], LLMMiddleware],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a middleware plugin with the registry."""

def create_middleware(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> LLMMiddleware:
    """Create a middleware instance from definition."""

def create_middlewares(
    definitions: list[dict[str, Any]] | None,
    *,
    parent_context: PluginContext | None = None,
) -> list[LLMMiddleware]:
    """Create a list of middleware instances from definitions."""
```

### 4.2 Middleware Data Flow

**Location**: `runner.py` lines 654-663 (call site), `_process_single_row()` method

**Current Middleware Chain**:
```python
# runner.py: Build LLMRequest
request = LLMRequest(
    system_prompt=system_rendered,
    user_prompt=user_rendered,
    metadata=context  # dict[str, Any] with row data
)

# Apply before_request middlewares (in order)
for middleware in self.llm_middlewares or []:
    request = middleware.before_request(request)

# Call LLM client
response = self.llm_client.generate(
    system_prompt=request.system_prompt,
    user_prompt=request.user_prompt,
    metadata=request.metadata,
)

# Apply after_response middlewares (in order)
for middleware in self.llm_middlewares or []:
    response = middleware.after_response(request, response)

# Validate response
for validator in self.validation_plugins or []:
    validator.validate(response, context=context, metadata=request.metadata)
```

**Migration Points**:

1. **request.metadata** - Currently dict, could become `ClassifiedData[dict]`
   - Middleware would need to unwrap/rewrap
   - Security uplifting would happen in after_response

2. **Middleware data access** - Example from `classified_material.py`:
   ```python
   def before_request(self, request: LLMRequest) -> LLMRequest:
       prompts = f"{request.system_prompt}\n{request.user_prompt}"
       # Scan prompts for classified markings
       # Current: No access to row metadata
       # Future: Could access classified fields from row metadata
   ```

3. **Middleware registration** - Already dynamic via plugin registry
   - No changes needed to registration mechanism
   - Changes only to middleware implementations

### 4.3 Security Context Integration

**Location**: `/home/john/elspeth/src/elspeth/core/base/plugin_context.py`

**Current Context Flow**:
```python
# orchestrator.py:79-87
experiment_context = PluginContext(
    plugin_name=name,
    plugin_kind="experiment",
    security_level=security_level,
    determinism_level=determinism_level,
    provenance=(f"orchestrator:{name}.resolved",),
    suite_root=suite_root,
    config_path=config_path,
)

# Applied to middleware, rate limiter, cost tracker
middlewares = create_middlewares(config.llm_middleware_defs, parent_context=experiment_context)
```

**Migration**: PluginContext already carries security_level, can be used to determine uplifting levels

---

## 5. COMPREHENSIVE MIGRATION SCOPE

### 5.1 Summary by Component

| Component | Type | Count | Current Pattern | Migration Requirement |
|-----------|------|-------|-----------------|----------------------|
| Sources | Plugins | 4 | Return `pd.DataFrame` | Return `ClassifiedDataFrame` |
| Sinks | Plugins | 16 | Accept `dict[str, Any]` | Accept dict, manage artifact security |
| LLM Transforms | Plugins | 4 | Accept prompts (str) | No change to interface |
| LLM Middleware | Plugins | 6 | Process `LLMRequest` | Unwrap/rewrap `metadata` |
| Row Plugins | Plugins | ~10+ | Accept `dict[str, Any]` | Unwrap/rewrap `ClassifiedData[dict]` |
| Aggregator Plugins | Plugins | 6 | Accept `list[dict]` | Unwrap/rewrap `ClassifiedData` |
| Baseline Plugins | Plugins | 9 | Accept `dict[str, Any]` | No direct data handling |
| Validation Plugins | Plugins | ~5+ | Accept `dict[str, Any]` | No change (validation at schema level) |
| Orchestrator | Core | 1 | Calls datasource.load() | Handle `ClassifiedDataFrame` |
| Runner | Core | 1 | Processes `pd.DataFrame` | Accept `ClassifiedDataFrame` |
| Artifact Pipeline | Core | 1 | Manages artifacts | Already has security_level metadata |

### 5.2 Interfaces Needing Updates

**1. DataSource Protocol** (`protocols.py` line 115-132)
```python
# BEFORE
class DataSource(Protocol):
    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""

# AFTER (Option A: Strict - always ClassifiedDataFrame)
class DataSource(Protocol):
    def load(self) -> ClassifiedDataFrame:
        """Return the experiment dataset."""

# AFTER (Option B: Flexible - Union type)
class DataSource(Protocol):
    def load(self) -> pd.DataFrame | ClassifiedDataFrame:
        """Return the experiment dataset."""
```

**2. ExperimentRunner.run()** (`runner.py` line 767)
```python
# BEFORE
def run(self, df: pd.DataFrame) -> dict[str, Any]:

# AFTER (Option A: Strict)
def run(self, df: ClassifiedDataFrame) -> dict[str, Any]:

# AFTER (Option B: Flexible)
def run(self, df: pd.DataFrame | ClassifiedDataFrame) -> dict[str, Any]:
```

**3. LLMRequest** (`protocols.py` line 207-227)
```python
# BEFORE
@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any]

# AFTER (Option A: Strict - always ClassifiedData)
@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: ClassifiedData[dict[str, Any]]

# AFTER (Option B: Flexible)
@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any] | ClassifiedData[dict[str, Any]]
```

**4. Row Plugin Data** - No protocol change needed, but implementations change:
```python
# BEFORE: process_row receives plain dicts
def process_row(self, row: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]:

# AFTER: Could receive ClassifiedData[dict]
def process_row(
    self, 
    row: ClassifiedData[dict[str, Any]], 
    responses: dict[str, Any]
) -> dict[str, Any]:
```

### 5.3 Plugin Count Details

**Exact Plugin Breakdown** (70 total .py files):

**Sources**: 4 files
- `_csv_base.py`, `csv_local.py`, `csv_blob.py`, `blob.py`

**Sinks**: 16 files
- Direct: `csv_file.py`, `excel.py`, `analytics_report.py`, `visual_report.py`, `enhanced_visual_report.py`, `embeddings_store.py`, `local_bundle.py`, `reproducibility_bundle.py`, `signed.py`, `zip_bundle.py`, `file_copy.py`
- Repo-based: `repository.py` (contains 3 classes)
- Blob-based: `blob.py` (contains 2 classes)
- Support: `_sanitize.py`, `_visual_base.py`

**Transforms - LLM**: 4 files
- `azure_openai.py`, `openai_http.py`, `static.py`, `mock.py`

**Transforms - Middleware**: 6 files
- `classified_material.py`, `pii_shield.py`, `prompt_shield.py`, `health_monitor.py`, `audit.py`, `azure_content_safety.py`

**Experiment Plugins - Row**: ~10 files (inferred from protocol usage)

**Experiment Plugins - Baseline**: 14 files
- `score_flip_analysis.py`, `score_distribution.py`, `score_delta.py`, `score_cliffs_delta.py`, `score_bayesian.py`, `score_assumptions.py`, `referee_alignment.py`, `criteria_effects.py`, `outlier_detection.py`, `category_effects.py`, `score_significance.py`, `score_practical.py`, `score_flip_analysis.py`

**Experiment Plugins - Aggregator**: 6 files
- `score_variant_ranking.py`, `score_stats.py`, `score_recommendation.py`, `score_power.py`, `rationale_analysis.py`, `latency_summary.py`, `cost_summary.py`

**Core/Support**: ~15 files
- `runner.py`, `suite_runner.py`, `job_runner.py`, `orchestrator.py`, `artifact_pipeline.py`, various registries, etc.

**Other**: ~5 files
- Various utilities and early stop plugins

---

## 6. DATA STRUCTURE MAPPINGS

### 6.1 DataFrame → ClassifiedDataFrame

**Current State**:
```python
df: pd.DataFrame
df.attrs = {'security_level': SecurityLevel.OFFICIAL}
```

**Migration Target**:
```python
frame: ClassifiedDataFrame
frame.data: pd.DataFrame  # Underlying data
frame.classification: SecurityLevel  # Immutable classification
```

**Operations**:
```python
# Creation (only in datasources)
frame = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)

# Uplifting (in plugins)
if plugin_security_level > frame.classification:
    frame = frame.with_uplifted_classification(plugin_security_level)

# Data access
df = frame.data
col = frame.data['column_name']
```

### 6.2 dict[str, Any] → ClassifiedData[dict]

**Problem**: ClassifiedData doesn't exist yet (ClassifiedDataFrame exists)

**Solution Options**:
1. Create `ClassifiedData[T]` generic wrapper (parallel to ClassifiedDataFrame)
2. Extend ClassifiedDataFrame to support dict wrapping
3. Keep dicts as-is, embed ClassifiedData only at schema field level
4. Create field-level `ClassifiedValue` for individual sensitive fields

**Recommended Approach**: Option 1 + Option 4
- Use `ClassifiedData[dict[str, Any]]` for row/context dicts
- Use `ClassifiedValue[T]` for individual sensitive fields
- Allows granular security at field and container level

---

## 7. MIGRATION COMPLEXITY ASSESSMENT

### 7.1 High-Impact Changes (Breaking changes)

1. **DataSource return type** - ALL 4 sources must change
   - Effort: 4 small changes
   - Risk: HIGH (orchestrator depends on this)

2. **Orchestrator datasource.load() call** - Must handle ClassifiedDataFrame
   - Effort: 1 change in orchestrator.py
   - Risk: HIGH (critical path)

3. **Runner.run() input type** - Must accept ClassifiedDataFrame
   - Effort: 1 change but impacts many internal methods
   - Risk: MEDIUM (internal refactoring)

4. **Row context/metadata propagation** - Through entire pipeline
   - Effort: Multiple changes in runner.py
   - Risk: MEDIUM (affects row processing)

### 7.2 Medium-Impact Changes (API adjustments)

5. **LLM Middleware** - 6 plugins need to unwrap/rewrap metadata
   - Effort: 6 plugin updates
   - Risk: MEDIUM (test coverage needed)

6. **Row Plugins** - ~10 plugins need to handle ClassifiedData[dict]
   - Effort: 10 plugin updates
   - Risk: MEDIUM (depends on ClassifiedData design)

7. **Aggregator Plugins** - 6 plugins need to unwrap/rewrap
   - Effort: 6 plugin updates
   - Risk: LOW (lower security sensitivity)

### 7.3 Low-Impact Changes (Metadata handling)

8. **Sinks** - 16 plugins need to be aware of security metadata
   - Effort: Minimal (metadata already in payload)
   - Risk: LOW (read-only operations)

9. **Validation/Early-stop** - Handle ClassifiedData
   - Effort: ~5 plugins
   - Risk: LOW (non-critical path)

10. **Artifact Pipeline** - Already has security level metadata
    - Effort: Minimal
    - Risk: LOW (already designed for security)

### 7.4 New Code Needed

- `ClassifiedData[T]` generic wrapper (if not already existing)
- Test infrastructure for ClassifiedDataFrame propagation
- Test infrastructure for ClassifiedData[dict] propagation
- Utilities for unwrap/rewrap in middleware
- Utilities for uplifting in plugins

**Estimated LOC**: 500-1000 lines of new infrastructure + tests

---

## 8. KEY DISCOVERY FINDINGS

### 8.1 Already Classified

✓ **Artifact metadata** - Already carries `security_level` in `ArtifactDescriptor` and `Artifact`
✓ **PluginContext** - Already carries `security_level` for all plugins
✓ **ExecutionMetadata** - Already carries `security_level` for results
✓ **Sink artifacts** - Already managed through artifact pipeline with security levels

### 8.2 Not Yet Classified

✗ **Row-level data dicts** - Currently plain dict, need ClassifiedData wrapper
✗ **LLM request metadata** - Currently dict, need ClassifiedData wrapper
✗ **Intermediate row processing results** - Plain dicts throughout
✗ **Field-level classifications** - No per-field security markings

### 8.3 Critical Paths

**Path 1: Datasource → Runner → Sinks**
```
datasource.load() [CHANGE: return ClassifiedDataFrame]
    ↓
orchestrator.run() [CHANGE: handle ClassifiedDataFrame]
    ↓
runner.run(df) [CHANGE: accept ClassifiedDataFrame]
    ↓
runner._dispatch_to_sinks() [CHANGE: propagate classification]
```

**Path 2: Row Processing → Middleware → Aggregation**
```
Extract row dict from ClassifiedDataFrame [CHANGE: wrap in ClassifiedData]
    ↓
Build context dict [CHANGE: wrap in ClassifiedData]
    ↓
Middleware processes LLMRequest.metadata [CHANGE: unwrap/rewrap]
    ↓
Row plugins process dict [CHANGE: handle ClassifiedData[dict]]
    ↓
Aggregators process list[dict] [CHANGE: handle ClassifiedData]
```

### 8.4 Design Decisions Needed

1. **ClassifiedDataFrame handling**: 
   - Should orchestrator.run(df) require strict ClassifiedDataFrame or accept pd.DataFrame?
   - Answer: Accept both for backward compat, prefer ClassifiedDataFrame

2. **Row dict classification**:
   - Should every row dict become ClassifiedData[dict]?
   - Or only dicts with sensitive fields?
   - Answer: Depends on schema - if row has classified columns, wrap row dict

3. **Middleware responsibility**:
   - Should middleware unwrap/rewrap automatically?
   - Or should runner handle it?
   - Answer: Runner should handle, middleware sees already-unwrapped LLMRequest

4. **Aggregator aggregation**:
   - Do aggregators need to see ClassifiedData[dict] or plain dicts?
   - Answer: Could see plain dicts, but metadata tells them classification level

---

## 9. SUMMARY TABLE: MIGRATION CHECKLIST

| Layer | Component | Plugins | Status | Effort | Risk |
|-------|-----------|---------|--------|--------|------|
| **Datasource** | CSV/Blob sources | 4 | ✗ Not started | 1-2 hrs | HIGH |
| **Orchestration** | Orchestrator | 1 | ✗ Not started | 1-2 hrs | HIGH |
| **Runner** | ExperimentRunner | 1 | ✗ Not started | 4-6 hrs | MEDIUM |
| **Transforms** | LLM clients | 4 | ✓ No changes needed | 0 | LOW |
| **Middleware** | LLM middleware | 6 | ✗ Not started | 2-3 hrs | MEDIUM |
| **Row Plugins** | Row experiment | ~10 | ✗ Not started | 3-4 hrs | MEDIUM |
| **Aggregators** | Aggregation | 6 | ✗ Not started | 2-3 hrs | LOW |
| **Baseline** | Baseline analysis | 9 | ✓ No changes needed | 0 | LOW |
| **Sinks** | Result sinks | 16 | ✓ Minor changes | 1-2 hrs | LOW |
| **Support** | Artifact pipeline, etc. | ~5 | ✓ Minimal changes | 1 hr | LOW |
| **New** | ClassifiedData wrapper | N/A | ✗ Not started | 2-3 hrs | MEDIUM |

**Total Estimated Effort**: 17-28 hours
**Total Plugins Affected**: ~60-70 (most are minimal changes)
**Critical Path**: Datasource → Orchestrator → Runner (8-10 hours)

