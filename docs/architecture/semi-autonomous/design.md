# Semi-Autonomous Platform — Architecture Design

**Status:** Draft
**Date:** 2026-03-02
**Epic:** `elspeth-rapid-ea33f5`
**Branch:** TBD (pre-implementation)

---

## Overview

The Semi-Autonomous Platform wraps ELSPETH with an LLM-driven configuration layer, allowing non-technical users to describe data processing tasks in natural language and receive fully auditable pipeline results. The user interacts with a visual graph editor (ComfyUI-inspired), reviews AI-generated pipeline designs, and approves execution with a single action.

**Core Invariant:** Generated pipelines execute with the FULL rigour of any hand-written ELSPETH pipeline. Every audit trail guarantee, every Landscape record, every trust tier boundary applies identically. The semi-autonomous layer is a configuration generator — once the config is produced, the standard ELSPETH engine executes it with zero relaxation of guarantees.

**Plugin Exploitation, Not Generation:** The system composes pipelines exclusively from the existing plugin library. It does NOT generate new plugin code, custom transforms, or ad-hoc Python. The LLM's job is to understand user intent and map it onto the existing plugin vocabulary.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Service Decomposition](#service-decomposition)
  - [API Gateway](#api-gateway)
  - [Conversation Service](#conversation-service)
  - [Workflow Orchestration (Temporal)](#workflow-orchestration-temporal)
  - [Worker Pods](#worker-pods)
  - [Shared Storage](#shared-storage)
- [User Interface: Visual Graph Editor](#user-interface-visual-graph-editor)
  - [Interaction Flow](#interaction-flow)
  - [Node Types and User-Visible Settings](#node-types-and-user-visible-settings)
  - [Plugin Review Classification](#plugin-review-classification)
  - [Summary Report Mode](#summary-report-mode)
  - [Live Execution Visualization](#live-execution-visualization)
- [Config Generation Layer](#config-generation-layer)
  - [Pipeline Design Artifact](#pipeline-design-artifact)
  - [LLM Context Requirements](#llm-context-requirements)
  - [Validation and Refinement Loop](#validation-and-refinement-loop)
- [Telemetry and Real-Time Progress](#telemetry-and-real-time-progress)
- [Audit Trail: Meta-Level Provenance](#audit-trail-meta-level-provenance)
- [Plugin Review Classification System](#plugin-review-classification-system)
- [Synchronous Loop Considerations](#synchronous-loop-considerations)
- [Technology Choices](#technology-choices)
- [What Exists vs What Needs Building](#what-exists-vs-what-needs-building)
- [Open Design Questions](#open-design-questions)

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────┐
│                    API GATEWAY                        │
│            (Auth, rate limit, routing)                │
└─────────┬────────────────────────┬───────────────────┘
          │                        │
  ┌───────┴────────┐      ┌───────┴────────┐
  │ Conversation   │      │ Temporal       │
  │ Service        │      │ Server         │
  │ (FastAPI)      │      │ (workflow      │
  │                │      │  orchestration)│
  │ • Chat/prompt  │      │                │
  │ • LLM calls    │─────►│ • Durably runs │
  │ • Refinement   │start │   workflows    │
  │ • Config store │wflow │ • Retries      │
  └────────────────┘      │ • Timeouts     │
                          │ • Visibility   │
                          └───────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
              ┌─────┴───┐  ┌─────┴───┐  ┌─────┴───┐
              │ Worker  │  │ Worker  │  │ Worker  │
              │ Pod     │  │ Pod     │  │ Pod     │
              │         │  │         │  │         │
              │ ELSPETH │  │ ELSPETH │  │ ELSPETH │
              │ Engine  │  │ Engine  │  │ Engine  │
              └────┬────┘  └────┬────┘  └────┬────┘
                   │            │            │
              ┌────┴────────────┴────────────┴────┐
              │         Shared Storage             │
              │  PostgreSQL (Landscape + events)   │
              │  Object Store (payloads, results)  │
              └────────────────────────────────────┘
```

### Key Design Decisions

1. **Conversation and execution are separate services** with an artifact boundary (the generated YAML). Different scaling profiles, different lifecycles.
2. **Temporal for workflow orchestration** instead of custom job queue. Provides durable execution, crash recovery, approval gates, cancellation, and visibility for free.
3. **Worker pod isolation** — each pipeline runs in its own pod. Bad pipelines die with their pod, not the service. Kubernetes HPA scales based on queue depth.
4. **Shared PostgreSQL Landscape** — multi-tenancy via `run_id` scoping. ELSPETH already supports PostgreSQL.
5. **Event-sourced meta-audit** — the task lifecycle (prompt → generation → review → execution) is an event log that links to the Landscape `run_id`.

---

## Service Decomposition

### API Gateway

Standard API gateway (e.g., Kong, Envoy, or cloud-native):

- **Auth:** OAuth2/OIDC (corporate SSO integration)
- **Rate limiting:** Per-user request limits (separate from ELSPETH's per-service rate limiting)
- **Routing:** `/api/conversations/*` → Conversation Service, `/api/tasks/*` → Temporal visibility API
- **WebSocket upgrade:** For real-time telemetry streaming

### Conversation Service

**Stateful, long-lived.** Manages the LLM interaction, config generation, and user refinement loop.

Responsibilities:
- Accept natural language task descriptions
- Infer data schema from uploaded/referenced data
- Call LLM to generate pipeline configurations
- Handle iterative refinement ("also extract dates")
- Serve graph descriptors to the frontend
- Apply user edits from the canvas back to the pipeline design
- Start Temporal workflows when user approves execution

**Does NOT** execute pipelines. The artifact boundary between Conversation Service and Worker Pods is a frozen YAML config.

### Workflow Orchestration (Temporal)

Temporal replaces a custom job queue + status tracking system. A single workflow type handles the full task lifecycle:

```python
@workflow.defn
class PipelineTaskWorkflow:

    def __init__(self):
        self._status = "pending"
        self._telemetry_events = []

    @workflow.run
    async def run(self, request: TaskRequest) -> TaskResult:
        # Phase 1: Validate config (local activity, fast)
        self._status = "validating"
        validation = await workflow.execute_local_activity(
            validate_config, args=[request.config_yaml],
            start_to_close_timeout=timedelta(seconds=10),
        )

        if not validation.valid:
            return TaskResult(status="validation_failed", errors=validation.errors)

        # Phase 2: Execute pipeline (long-running activity)
        self._status = "executing"
        result = await workflow.execute_activity(
            execute_pipeline,
            args=[request.config_yaml, request.data_ref],
            start_to_close_timeout=timedelta(hours=4),
            heartbeat_timeout=timedelta(seconds=30),
        )

        return TaskResult(status="completed", result=result)

    @workflow.query
    def get_status(self) -> str:
        return self._status

    @workflow.signal
    def cancel_execution(self):
        self._cancelled = True
```

**Why Temporal over custom queue:**

| Capability | Custom (Redis + workers) | Temporal |
|---|---|---|
| Crash recovery | Build checkpoint/retry logic | Free (workflow replay) |
| Approval gates | Custom polling/WebSocket | `workflow.wait_condition()` |
| Cancellation | Custom signal propagation | `workflow.cancel()` |
| Long-running tasks | Timeout management | Per-activity timeouts |
| Observability | Build status API | Temporal UI + query handlers |
| Exactly-once semantics | Hard to guarantee | Built-in |

### Worker Pods

Each worker pod is a Kubernetes Job or Deployment replica that:

1. Registers as a Temporal activity worker
2. Receives pipeline execution tasks from Temporal
3. Drives the ELSPETH `Orchestrator.run()` API directly (no CLI)
4. Streams telemetry via a Redis pub/sub exporter
5. Sends Temporal heartbeats during execution (crash detection)

```python
@activity.defn
async def execute_pipeline(config_yaml: str, data_ref: str) -> ExecutionResult:
    """Temporal activity: execute an ELSPETH pipeline."""

    settings = load_settings_from_string(config_yaml)
    plugins = instantiate_plugins_from_config(settings)
    graph = ExecutionGraph.from_plugin_instances(
        source=plugins.source,
        source_settings=plugins.source_settings,
        transforms=plugins.transforms,
        sinks=plugins.sinks,
        aggregations=plugins.aggregations,
        gates=list(settings.gates),
        coalesce_settings=list(settings.coalesce) if settings.coalesce else None,
    )
    graph.validate()

    db = LandscapeDB.from_url(SHARED_LANDSCAPE_URL)
    telemetry_mgr = create_telemetry_manager(
        exporters=[RedisTelemetryExporter(redis, task_id=activity.info().workflow_id)]
    )

    orchestrator = Orchestrator(db, telemetry_manager=telemetry_mgr)
    result = orchestrator.run(
        config=build_pipeline_config(plugins, settings),
        graph=graph,
        payload_store=S3PayloadStore(bucket=PAYLOAD_BUCKET),
    )

    return result
```

**Pod isolation benefits:**
- Bad pipeline (OOM, infinite loop) → pod dies → Temporal retries on fresh pod
- CPU/memory limits per pod prevent one user starving others
- Kubernetes HPA scales pod count based on Temporal task queue depth
- No shared mutable state between concurrent pipelines

### Shared Storage

| Store | Purpose | Technology |
|---|---|---|
| **Task DB** | Task records, user sessions, generated configs, event log | PostgreSQL |
| **Landscape DB** | ELSPETH audit trail (shared across all worker pods) | PostgreSQL (ELSPETH native support) |
| **Payload Store** | Source row payloads, large blobs | S3 / Azure Blob Storage |
| **Result Store** | Sink outputs (CSVs, JSONs) | S3 / Azure Blob Storage |
| **Telemetry Channel** | Real-time event streaming to frontend | Redis pub/sub |

---

## User Interface: Visual Graph Editor

### Interaction Flow

The user interaction follows an **AI-generated, human-reviewed** model — fundamentally different from typical low-code builders where the user constructs the graph manually.

```text
  User types prompt ──► LLM generates graph ──► Graph appears on canvas
                                                      │
                                              User reviews:
                                              • Summary report (always)
                                              • Node details (optional)
                                              • Prompted for review on
                                                classified plugins
                                                      │
                                              Hits ▶ Play
                                                      │
                                              Validation runs
                                              (green/red per node)
                                                      │
                                              Execution starts
                                              (nodes animate with
                                               progress/telemetry)
                                                      │
                                              Results available
                                              (click sink to
                                               preview/download)
```

### Node Types and User-Visible Settings

Each ELSPETH plugin type maps to a visual node with curated, user-facing controls. The raw YAML is an internal artifact — users see settings, not configuration.

| Node Type | User Sees | Hidden from User |
|---|---|---|
| **Source** | Filename, row count, field names, data preview | `plugin: csv`, schema mode, `on_success` wiring |
| **LLM Transform** | Prompt text, output field names/types, model picker, temperature | Provider config, API keys, retry settings, `state_id` |
| **Gate** | Human-readable rule ("If urgency is critical or high → Review"), route labels | Expression syntax, AST internals |
| **Aggregation** | Grouping description ("Group every 100 rows", "Group by theme") | Trigger config, buffer mechanics, flush internals |
| **Field Mapper** | Rename/select operations in plain English | Schema mode, config internals |
| **Sink** | Output name ("Results", "Review Queue"), format, download link | File paths, `on_error` wiring, artifact hashing |
| **Safety Transform** | "Content safety check enabled", sensitivity level | Azure API config, field mappings |

**What the user CAN do on the canvas:**
- Edit prompt text, output field definitions, routing rules
- Change model selection (dropdown of available/permitted models)
- Adjust aggregation grouping parameters
- Add/remove routing branches on gates
- Rearrange visual layout (doesn't change DAG topology)
- Click any node to preview sample input/output

**What the user CANNOT do:**
- Add arbitrary nodes (topology changes go through LLM refinement)
- Wire connections manually (LLM determines dataflow)
- Edit raw YAML or expression syntax
- Access API keys, internal paths, engine settings

**Boundary rule:** Parameter tweaks are direct edits on the canvas. Structural changes (add a step, restructure paths) go back through the LLM via natural language refinement.

### Plugin Review Classification

Plugins are classified into review tiers that determine what level of user attention is required before execution. This is a **platform configuration**, not per-user — administrators define the classification.

#### Review Tiers

| Tier | Behavior | User Experience | Example Plugins |
|---|---|---|---|
| **Transparent** | No review required. Executes as part of the pipeline without user interaction. | Node appears dimmed/collapsed on canvas. User can expand to inspect but isn't prompted to. | `passthrough`, `field_mapper`, `truncate`, `batch_stats` |
| **Visible** | Shown in summary report. User sees it but isn't blocked from proceeding. | Node appears normally on canvas. Summary report includes a line item. | `csv_source`, `json_source`, `csv_sink`, `json_sink`, `keyword_filter` |
| **Review Required** | User must positively acknowledge this node before execution proceeds. The Play button is disabled until all review-required nodes are acknowledged. | Node has a yellow border and a checkbox: "I've reviewed this step." Summary report highlights it with an explanation of what it does and why review matters. | `llm` (any LLM transform), `web_scrape`, `content_safety`, `prompt_shield` |
| **Approval Required** | Requires explicit approval with a reason. For destructive or high-cost operations. | Node has a red border. User must type a justification or select a predefined reason before the checkbox enables. | `database_sink` (writes to external DB), `azure_blob_sink` (writes to cloud storage) |

#### Classification Configuration

```yaml
# Platform-level configuration (not per-pipeline)
plugin_review_classification:
  # Tier 1: Transparent — no review needed
  transparent:
    - passthrough
    - field_mapper
    - truncate
    - batch_stats
    - batch_replicate
    - json_explode
    - null_source

  # Tier 2: Visible — shown in summary, not blocking
  visible:
    - csv_source
    - json_source
    - csv_sink
    - json_sink
    - keyword_filter

  # Tier 3: Review Required — must acknowledge before execution
  review_required:
    - llm            # Any LLM call (cost, prompt content, model choice)
    - web_scrape     # External HTTP calls (SSRF surface, data exfiltration)
    - content_safety # Safety classification (false positive/negative impact)
    - prompt_shield  # Prompt injection detection (security decision)

  # Tier 4: Approval Required — must justify before execution
  approval_required:
    - database_sink     # Writes to external database
    - azure_blob_sink   # Writes to cloud storage
    - azure_blob_source # Reads from cloud storage (data access scope)

  # Default tier for unclassified plugins
  default_tier: review_required
```

**Default is `review_required`** — new plugins are conservatively classified until an administrator explicitly assigns them to a lower tier. This is fail-closed design.

#### Audit Trail for Review Actions

Every review action is recorded in the meta-audit event log:

```python
# User acknowledges a review-required node
TaskEvent("task-1", t3, "node_reviewed", {
    "node_id": "llm_classify",
    "plugin": "llm",
    "review_tier": "review_required",
    "user_action": "acknowledged",
    "settings_hash": "abc123",  # Hash of user-visible settings at review time
}, "user:john")

# User approves an approval-required node with justification
TaskEvent("task-1", t4, "node_approved", {
    "node_id": "db_output",
    "plugin": "database_sink",
    "review_tier": "approval_required",
    "user_action": "approved",
    "justification": "Writing to staging database for QA review",
    "settings_hash": "def456",
}, "user:john")
```

### Summary Report Mode

For users who don't want to interact with the graph canvas at all, the system generates an **LLM-authored summary report** that describes the pipeline in plain English. This is the default view — the graph canvas is available but secondary.

#### Summary Report Structure

```text
┌─────────────────────────────────────────────────────────────┐
│  📋 Pipeline Summary                                        │
│                                                             │
│  "Classify 2,847 support tickets by urgency level"          │
│                                                             │
│  WHAT THIS WILL DO:                                         │
│  1. Read your file tickets.csv (2,847 rows, 4 fields)       │
│  2. Send each ticket to GPT-4o with the prompt:             │
│     "Classify this support ticket by urgency:                │
│      critical / high / medium / low"                         │
│  3. Route critical and high urgency tickets to a             │
│     separate Review file                                     │
│  4. Write all results to Results.csv with the                │
│     original fields plus urgency and confidence              │
│                                                             │
│  ⚠️  REQUIRES YOUR REVIEW:                                  │
│  • LLM Classification — uses GPT-4o ($0.01/1K tokens,       │
│    estimated cost: ~$4.20 for 2,847 rows)                    │
│    [Review details ▾]                                        │
│                                                             │
│  OUTPUTS:                                                   │
│  • Results.csv — all 2,847 rows with classifications         │
│  • Review.csv — critical/high urgency tickets only           │
│                                                             │
│  ┌────────────┐  ┌──────────────────┐                       │
│  │ View Graph │  │ ▶ Run Pipeline   │  (disabled until       │
│  └────────────┘  └──────────────────┘   review complete)     │
└─────────────────────────────────────────────────────────────┘
```

The summary report is **generated by the same LLM** that created the pipeline config — it understands what it built and can explain it in context. The report includes:

1. **Plain English description** of each pipeline step
2. **Review-required items** highlighted with expand-to-review controls
3. **Cost estimate** for LLM calls (token count × model pricing)
4. **Output description** — what files/data the user will receive
5. **Data preview** — first few rows of input, expected output shape

#### Configuration: Summary vs Graph Default

```yaml
# Platform-level UI configuration
ui_defaults:
  # Which view users see first
  default_view: summary  # "summary" | "graph" | "both"

  # Whether the graph canvas is available at all
  graph_canvas_enabled: true

  # Whether to show cost estimates for LLM transforms
  show_cost_estimates: true

  # Whether to show data previews in the summary
  show_data_previews: true
  preview_row_count: 5
```

Users who prefer the graph can switch to it. Users who just want to read a summary and hit Play never need to see the DAG at all.

### Live Execution Visualization

During execution, both the summary report and graph canvas show real-time progress:

**Summary Report (live):**
```text
  ✅ Step 1: Read tickets.csv — 2,847 rows loaded
  ⏳ Step 2: LLM Classification — 1,204 / 2,847 (42%, ~12 min remaining)
     💰 API cost so far: $2.34
     ⚠️ 3 rows quarantined (click to view)
  ⏸ Step 3: Route by urgency — waiting
  ⏸ Step 4: Write results — waiting
```

**Graph Canvas (live):**
```text
┌────────────────┐     ┌───────────────────────┐     ┌────────────┐
│ 📥 Source       │     │ 🤖 LLM Classify        │     │ 📊 Results  │
│ ✅ 2,847/2,847 │────►│ ⏳ 1,204/2,847  42%   │────►│ ⏸ 0 rows   │
│ ████████ 100%  │     │ ██████░░░░░░          │     └────────────┘
└────────────────┘     │ ⏱ ~12 min │ 💰 $2.34 │
                       │ ⚠️ 3 quarantined       │     ┌────────────┐
                       └───────────┬────────────┘     │ ⚠️ Review   │
                                   │                  │ ⏸ 0 rows   │
                       ┌───────────┴────────────┐     └────────────┘
                       │ 🚦 Route: urgency       │───►
                       │ ⏸ waiting               │
                       └─────────────────────────┘
```

Progress data comes from the telemetry exporter (see [Telemetry](#telemetry-and-real-time-progress)).

---

## Config Generation Layer

### Pipeline Design Artifact

The LLM produces a `PipelineDesign` that contains both the user-facing representation and the executable config:

```python
@dataclass(frozen=True)
class PipelineDesign:
    """The LLM's output — visual and executable representations."""

    # What the user sees
    graph_descriptor: GraphDescriptor  # Nodes, edges, user-visible settings

    # What ELSPETH executes (derived from above + system defaults)
    pipeline_yaml: str

    # LLM-generated summary for the summary report view
    summary_report: SummaryReport

    # Review classification per node
    review_requirements: dict[str, ReviewTier]  # node_id → tier

    # Provenance
    generation_prompt: str
    llm_model: str
    llm_response_hash: str
```

The `GraphDescriptor` and `pipeline_yaml` are derived from the same internal representation. A user edit on the canvas updates the descriptor, which re-derives the YAML.

### LLM Context Requirements

The config generation LLM needs:

1. **Plugin catalog** — every available plugin with its config schema, input/output requirements, and plain English description of what it does
2. **Expression grammar** — what gate conditions can look like (`row['field'] > 0.8`, `row['field'] in ('a', 'b')`)
3. **Wiring rules** — `input`/`on_success`/`on_error` connection semantics, namespace separation
4. **Data schema** — column names, types, and sample rows from the user's data
5. **Few-shot examples** — common pipeline shapes for classification, extraction, aggregation, etc.
6. **Review classification** — which plugins require review, so the summary report can highlight them

### Validation and Refinement Loop

Generated configs are validated before presentation to the user. If validation fails, the error is fed back to the LLM for correction (up to 3 rounds):

```python
async def generate_config(prompt: str, data_ref: str) -> PipelineDesign:
    """Generate and validate pipeline config from natural language."""

    context = build_generation_context(
        plugin_catalog=get_plugin_catalog(),
        data_sample=sample_data(data_ref, n=5),
        data_schema=infer_schema(data_ref),
    )

    config_yaml = await llm.generate(
        system=PIPELINE_GENERATION_SYSTEM_PROMPT,
        user=f"Task: {prompt}\n\nSchema: {context.schema}\nSample: {context.sample}",
    )

    for attempt in range(3):
        try:
            settings = load_settings_from_string(config_yaml)
            plugins = instantiate_plugins_from_config(settings)
            graph = ExecutionGraph.from_plugin_instances(...)
            graph.validate()
            return build_pipeline_design(config_yaml, settings, graph)
        except (ValidationError, GraphValidationError) as e:
            config_yaml = await llm.refine(
                original=config_yaml,
                error=str(e),
            )

    raise ConfigGenerationError("Failed after 3 validation attempts")
```

---

## Telemetry and Real-Time Progress

ELSPETH's existing `TelemetryManager` supports multiple exporters. The platform adds a `RedisTelemetryExporter` that publishes events to a pub/sub channel keyed by task ID:

```python
class RedisTelemetryExporter(TelemetryExporter):
    """Publishes telemetry events to Redis pub/sub for real-time streaming."""

    def __init__(self, redis_client: Redis, task_id: str):
        self._redis = redis_client
        self._channel = f"task:{task_id}:telemetry"

    def export(self, events: list[TelemetryEvent]) -> None:
        for event in events:
            self._redis.publish(self._channel, event.to_json())
```

The frontend connects via WebSocket. The API Gateway subscribes to the Redis channel and pushes events to the WebSocket:

```text
Worker Pod                              Frontend
┌──────────────────┐                   ┌──────────────┐
│ Orchestrator     │                   │ WebSocket GW │
│   │              │                   │              │
│   ├─ Landscape   │  (audit trail)    │              │
│   │  (PostgreSQL)│──────────────────►│ /lineage     │
│   │              │                   │              │
│   └─ Telemetry   │                   │              │
│      Manager     │                   │              │
│      │           │                   │              │
│      └─ Redis    │  (real-time)      │              │
│        Exporter  │──────────────────►│ /tasks/{id}  │
│                  │  pub/sub channel  │  WebSocket   │
└──────────────────┘  task:{task_id}   └──────────────┘
```

**Telemetry events mapped to UI updates:**

| ELSPETH Event | UI Update |
|---|---|
| `RunStarted` | Pipeline execution begins, nodes activate |
| `RowCreated` | Source node row counter increments |
| `TransformCompleted` | Transform node progress bar advances |
| `RoutingDecision` | Gate node split counters update |
| `ArtifactRegistered` | Sink node row count updates |
| `RunFinished` | All nodes show final state, results available |

---

## Audit Trail: Meta-Level Provenance

ELSPETH's Landscape audit trail covers pipeline execution. The semi-autonomous platform adds a **meta-level event log** that covers the task lifecycle — from prompt to result:

```python
@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]
    actor: str  # "user:john" or "system:config-gen" or "system:elspeth"
```

**Event sequence for a typical task:**

| Event | Actor | Payload |
|---|---|---|
| `prompt_submitted` | `user:john` | Prompt text, data reference |
| `schema_inferred` | `system:config-gen` | Field names, types, row count |
| `config_generated` | `system:config-gen` | YAML hash, LLM model, token usage |
| `summary_generated` | `system:config-gen` | Summary text hash |
| `graph_presented` | `system:ui` | Nodes visible, review requirements |
| `node_reviewed` | `user:john` | Node ID, plugin, settings hash |
| `node_approved` | `user:john` | Node ID, justification (if approval tier) |
| `user_approved_execution` | `user:john` | Config hash, time on canvas |
| `validation_passed` | `system:config-gen` | Node count, edge count |
| `execution_started` | `system:elspeth` | Landscape `run_id` |
| `execution_completed` | `system:elspeth` | `run_id`, status, row count |

The `run_id` field links the meta-level event log to the Landscape audit trail. An auditor can trace from "Run X was produced by task Y, which was generated from prompt Z by user W."

---

## Plugin Review Classification System

### Design Rationale

Not all pipeline operations carry equal risk. A `field_mapper` that renames columns is fundamentally different from an `llm` transform that sends data to an external API or a `database_sink` that writes to a production database. The review classification system ensures users pay attention to the operations that matter while not being burdened by routine transformations.

### Classification Principles

1. **Default is conservative.** Unclassified plugins default to `review_required`. New plugins must be explicitly assigned to a lower tier by an administrator.
2. **Classification is platform-level.** Individual users cannot lower the review tier of a plugin. They can optionally raise it for themselves (personal stricter settings).
3. **The LLM doesn't control classification.** The LLM generates the pipeline; the platform determines review requirements based on which plugins were used. This prevents the LLM from downplaying the significance of a step.
4. **Review state is audited.** Every acknowledgement and approval is recorded with timestamp, settings hash, and (for approval tier) justification text.

### Enforcement

The Play button is disabled until all review/approval requirements are satisfied:

```python
def can_execute(design: PipelineDesign, reviews: list[ReviewAction]) -> bool:
    """Check if all review requirements are satisfied."""
    for node_id, tier in design.review_requirements.items():
        if tier == ReviewTier.TRANSPARENT or tier == ReviewTier.VISIBLE:
            continue  # No review needed

        matching_review = find_review(reviews, node_id)

        if tier == ReviewTier.REVIEW_REQUIRED:
            if matching_review is None or matching_review.action != "acknowledged":
                return False

        if tier == ReviewTier.APPROVAL_REQUIRED:
            if matching_review is None or matching_review.action != "approved":
                return False
            if not matching_review.justification:
                return False

    return True
```

### Review Tier Descriptions (for UI)

Each tier has a standard explanation shown to the user:

| Tier | UI Label | Explanation |
|---|---|---|
| **Transparent** | *(not shown)* | *(node dimmed/collapsed)* |
| **Visible** | "Included in pipeline" | "This step is part of your pipeline. No action needed." |
| **Review Required** | "⚠️ Please review" | "This step involves [external API calls / data transformation / ...]. Please review the settings before proceeding." |
| **Approval Required** | "🔴 Approval needed" | "This step [writes to an external system / accesses sensitive data / ...]. Please review and provide a reason for proceeding." |

---

## Synchronous Loop Considerations

### Current State

ELSPETH's main processing loop is fully synchronous — timeout evaluation is driven by row arrival, not background timers. This is documented as a known limitation (see `elspeth-rapid-2a9f69`).

### Impact on Semi-Autonomous Platform

For **this use case**, the synchronous loop is acceptable because:

- Semi-autonomous generates **finite-source** pipelines (CSV, JSON, API batch)
- Each pod runs one pipeline at a time — no multiplexing
- End-of-source flush guarantees all buffers drain
- The telemetry exporter streams progress in real-time regardless of loop timing

### Future: Heartbeat Source Wrapper

When streaming/server mode is needed, the solution is **synthetic heartbeat rows** injected at the source level. This preserves the single-threaded loop invariant while giving the engine regular "nudges" to check timeouts:

```python
class HeartbeatSourceWrapper:
    """Wraps any source with periodic heartbeat rows for timeout evaluation."""

    def load(self, ctx):
        for row in self._inner.load(ctx):
            yield row
            self._last_yield = clock.monotonic()

        # After source exhaustion, yield heartbeats (streaming mode only)
        while not shutdown.is_set():
            if clock.monotonic() - self._last_yield >= self._interval:
                yield SourceRow.valid({"_heartbeat": True})
                self._last_yield = clock.monotonic()
            time.sleep(0.1)
```

Heartbeats are filtered out before reaching sinks via a gate: `row.get('_heartbeat') == True → discard`. The engine processes them normally, triggering all timeout checks as a side effect.

This work belongs to the server mode epic (`elspeth-rapid-319f4a`), not the semi-autonomous platform.

---

## Technology Choices

### Backend

| Component | Technology | Rationale |
|---|---|---|
| **API Gateway** | Kong / Envoy / cloud-native | Standard, proven, SSO integration |
| **Conversation Service** | FastAPI | Async, typed, ELSPETH stack alignment |
| **Workflow Engine** | Temporal | Durable execution, crash recovery, approval gates |
| **Worker Runtime** | Kubernetes Jobs/Deployments | Isolation, scaling, resource limits |
| **Task Database** | PostgreSQL | Same as Landscape, operational simplicity |
| **Real-time Channel** | Redis pub/sub | Low-latency, ephemeral (telemetry is operational, not audit) |
| **Object Storage** | S3 / Azure Blob | Payloads, results, generated configs |

### Frontend

| Component | Technology | Rationale |
|---|---|---|
| **Graph Editor** | React Flow | Most mature node graph library, typed, active ecosystem |
| **UI Framework** | React + TypeScript | React Flow requirement, broad ecosystem |
| **State Management** | Zustand or Jotai | Lightweight, fits graph editor pattern |
| **WebSocket Client** | Native WebSocket API | Real-time telemetry streaming |
| **Styling** | Tailwind CSS | Rapid iteration, consistent design |

### LLM for Config Generation

The config generation LLM is **separate from** any LLM used within pipelines. It needs strong structured output (YAML generation with schema adherence).

Recommended: Claude Opus or Sonnet class models — strong at structured output, good at following schema constraints, handles the plugin catalog context well.

---

## What Exists vs What Needs Building

| Component | Status | Work Required |
|---|---|---|
| `Orchestrator.run()` programmatic API | **Exists** | Minor: extract from CLI coupling |
| `instantiate_plugins_from_config()` | **Exists** | None |
| `ExecutionGraph.from_plugin_instances()` | **Exists** | None |
| `elspeth validate` equivalent | **Exists** | Extract from CLI into library function |
| `TelemetryManager` + exporters | **Exists** | Add Redis exporter |
| Plugin catalog discovery | **Exists** (`PluginManager`) | Serialize to LLM-consumable format |
| PostgreSQL Landscape backend | **Exists** | None |
| `load_settings()` from string | **Exists** | Verify works without file path |
| **Config generation LLM wrapper** | **New** | Prompt engineering + validation loop |
| **Conversation Service (FastAPI)** | **New** | Chat API, config store, refinement |
| **Temporal workflow definitions** | **New** | Task workflow, activity definitions |
| **Redis telemetry exporter** | **New** | Implements existing `TelemetryExporter` protocol |
| **S3/Blob PayloadStore** | **New** | Implements existing `PayloadStore` protocol |
| **React Flow graph editor** | **New** | Custom node components per plugin type |
| **Summary report generator** | **New** | LLM-authored pipeline explanation |
| **Review classification system** | **New** | Config + enforcement + audit |
| **Meta-level event log** | **New** | Task lifecycle audit trail |
| **WebSocket telemetry gateway** | **New** | Redis sub → WebSocket push |
| **Task database schema** | **New** | Tasks, configs, reviews, events |

---

## Open Design Questions

1. **Multi-tenancy model.** Shared Landscape DB with `run_id` scoping, or per-tenant databases? Shared is simpler but limits isolation. Per-tenant is more complex but enables independent retention policies.

2. **Data upload flow.** How does user data reach the worker pod? Options: (a) pre-upload to object store with reference, (b) direct upload through API gateway with size limits, (c) reference to existing data in user's storage.

3. **LLM cost attribution.** The config generation LLM has a cost. The pipeline LLM transforms have a cost. How are these attributed and billed? Per-task metering? Per-user quotas?

4. **Iterative refinement scope.** "Make it also extract dates" — does this re-generate from scratch or patch the existing config? Patching is faster but risks drift from the original intent.

5. **Template library.** Should common pipeline patterns be pre-built templates that the LLM can reference? ("This looks like a classification task — starting from the classification template.") This would improve generation quality and speed.

6. **Offline/async execution.** Should users be able to submit a task, close their browser, and come back later for results? Temporal naturally supports this, but the UI needs notification (email, webhook, push notification).

7. **Collaborative review.** Can multiple users review the same pipeline design? ("Alice generated it, Bob reviews the LLM prompts, Charlie approves the database sink.") This adds role-based review but increases complexity.

8. **Plugin allow/deny lists per user/org.** Beyond review classification, should certain plugins be unavailable to certain users? ("Interns can't use database_sink at all, not just approval-required.")
