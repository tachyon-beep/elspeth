# Semi-Autonomous Platform - Revised Architecture Design

**Status:** Revised Draft
**Date:** 2026-03-03
**Epic:** `elspeth-rapid-ea33f5`
**Branch:** TBD (pre-implementation)

This document is the authoritative architecture design for the Semi-Autonomous
Platform. Supporting documents in this folder record review history, critique,
and design evolution; this document captures the current intended design.

---

## Overview

The Semi-Autonomous Platform wraps ELSPETH with an LLM-assisted design and
governance layer. A user describes a task in natural language, reviews a
generated pipeline in a summary-first interface, inspects trial evidence,
obtains any required approvals, and then executes the pipeline through the
standard ELSPETH engine.

The platform does **not** relax ELSPETH's guarantees. It is a configuration,
review, and orchestration system around ELSPETH. Once a pipeline artifact is
sealed for execution, the standard engine runs it with the same audit, trust,
lineage, and failure semantics as a hand-authored pipeline.

The system composes only from the existing plugin library. It does not generate
plugin code, ad hoc Python, or arbitrary executable logic.

---

## Core Invariants

1. **ELSPETH remains the execution authority.** The semi-autonomous layer may
   generate, refine, summarize, validate, and govern. ELSPETH executes.
2. **The user approves a sealed artifact, not a chat transcript.** Execution
   binds to an immutable `PipelineArtifact` with cryptographic hashes.
3. **Governance is platform-enforced, not model-suggested.** The model can
   explain policy but cannot lower, override, or bypass it.
4. **Preview evidence is real execution evidence.** Previews run through the
   real engine, with real Landscape records, under explicit preview semantics.
5. **Approvals are approvals of dataflow, not just node settings.** Upstream
   changes invalidate downstream approvals when the approved result contract has
   changed.
6. **Deterministic review evidence outranks AI explanation.** The legal review
   artifact is a deterministic spec plus preview evidence. AI summaries are
   contextual only.
7. **No hidden translation layer.** User-intent configuration, derived YAML,
   tier computation inputs, and policy hashes are all stored and inspectable.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Key Design Decisions](#key-design-decisions)
- [Service Decomposition](#service-decomposition)
  - [API Gateway](#api-gateway)
  - [Conversation Service](#conversation-service)
  - [Policy and Artifact Services](#policy-and-artifact-services)
  - [Workflow Orchestration (Temporal)](#workflow-orchestration-temporal)
  - [Preview Workers](#preview-workers)
  - [Execution Workers](#execution-workers)
  - [Shared Storage](#shared-storage)
- [Pipeline Artifact and Governance](#pipeline-artifact-and-governance)
  - [Sealed PipelineArtifact](#sealed-pipelineartifact)
  - [Approval Records and Approval Scope](#approval-records-and-approval-scope)
  - [Three-Tier Enforcement Model](#three-tier-enforcement-model)
  - [Tier Computation](#tier-computation)
  - [Classification Config Governance](#classification-config-governance)
- [Preview and Validation Model](#preview-and-validation-model)
  - [Preview Modes](#preview-modes)
  - [Preview Row Selection](#preview-row-selection)
  - [Source Preview Capabilities](#source-preview-capabilities)
  - [Validation Case Libraries](#validation-case-libraries)
- [User Experience](#user-experience)
  - [Summary-First Interaction Model](#summary-first-interaction-model)
  - [Graph Editor Role](#graph-editor-role)
  - [Pipeline-Level Review UX](#pipeline-level-review-ux)
  - [Refinement Diff and Selective Re-Approval](#refinement-diff-and-selective-re-approval)
- [Config Generation Layer](#config-generation-layer)
  - [Declarative Composition State](#declarative-composition-state)
  - [Composition API](#composition-api)
  - [LLM Composer Loop](#llm-composer-loop)
  - [Deterministic Mapping to ELSPETH YAML](#deterministic-mapping-to-elspeth-yaml)
- [Execution and Orchestration](#execution-and-orchestration)
  - [Temporal Responsibilities](#temporal-responsibilities)
  - [ELSPETH Responsibilities](#elspeth-responsibilities)
  - [Retry, Checkpoint, and Resume Ownership](#retry-checkpoint-and-resume-ownership)
  - [Preview Latency Strategy](#preview-latency-strategy)
- [Telemetry and Real-Time Progress](#telemetry-and-real-time-progress)
- [Audit Trail and Meta-Level Provenance](#audit-trail-and-meta-level-provenance)
- [Security, Isolation, and Data Governance](#security-isolation-and-data-governance)
  - [Static Security Policy Enforcement](#static-security-policy-enforcement)
  - [Tenant Isolation](#tenant-isolation)
  - [Reference Data Versioning](#reference-data-versioning)
  - [Data Sensitivity Declaration](#data-sensitivity-declaration)
- [User-Facing Accountability Features](#user-facing-accountability-features)
- [Technology Choices](#technology-choices)
- [Non-Functional Targets](#non-functional-targets)
- [What Exists vs What Needs Building](#what-exists-vs-what-needs-building)
- [Open Questions](#open-questions)

---

## Architecture Overview

```text
                            +----------------------+
                            |      API Gateway     |
                            | auth, rate limit, WS |
                            +----+------------+----+
                                 |            |
                    +------------+            +-------------+
                    |                                         |
          +---------v----------+                    +---------v----------+
          | Conversation       |                    | Temporal           |
          | Service            |                    | Workflow Service   |
          |                    |<------------------>|                    |
          | - composition API  |  start / signal    | - durable state    |
          | - deterministic    |                    | - approval waits   |
          |   spec generation  |                    | - dispatch         |
          | - AI explanation   |                    | - visibility       |
          +----+-----------+---+                    +----+-----------+---+
               |           |                             |           |
   +-----------v--+    +---v---------------+      +------v--+   +---v---------------+
   | Policy        |    | Artifact Service  |      | Preview |   | Execution         |
   | Service       |    |                   |      | Workers |   | Workers           |
   | - plugin tier |    | - sealed artifact |      | warm    |   | isolated long-run |
   |   policy      |    |   storage         |      | pool    |   | workers           |
   | - security    |    | - approval refs   |      +----+----+   +----+--------------+
   |   rules       |    | - lineage chain   |           |              |
   +---------------+    +-------------------+           |              |
                                                         \            /
                                                          \          /
                                                 +---------v--------v---------+
                                                 | Shared Storage             |
                                                 | - Postgres task DB         |
                                                 | - Landscape DB(s)          |
                                                 | - Object store             |
                                                 | - Redis Streams            |
                                                 +----------------------------+
```

### Request lifecycle

```text
Prompt -> Compose -> Static policy check -> Tier compute
       -> Preview eligibility / preview execution
       -> Human approval gate (if required)
       -> ELSPETH execution
       -> Results + audit outputs + methodology artifacts
```

---

## Key Design Decisions

1. **Use a sealed `PipelineArtifact`, not "frozen YAML".** YAML alone is not a
   sufficient execution boundary because behavior also depends on plugin catalog
   version, policy versions, input identities, and preview evidence.
2. **Use a 3-tier, pipeline-level enforcement model.** There is no checkbox
   tier. The platform computes a single execution tier for the whole pipeline.
3. **Keep enforcement outside the model.** The model cannot propose a lower
   tier, cannot mark review complete, and cannot inspect approval state.
4. **Store user-intent config and derived YAML together.** Users review the
   deterministic spec created from declarative composition state; auditors can
   inspect both the reviewed intent and the executed YAML.
5. **Treat preview as a governed execution mode.** Preview is not a mock or a
   UI simulation. It is a constrained ELSPETH run with explicit semantics.
6. **Use declarative composition tools, not imperative "knobs".** The model
   proposes desired state and receives full updated state after each mutation.
7. **Split preview workers from execution workers.** Low-latency previews and
   isolated long-running execution have different operational requirements.
8. **Use Redis Streams, not Redis pub/sub, for operational telemetry.** The
   platform needs reconnect-safe streaming for live progress views.
9. **Let ELSPETH own row-level execution recovery.** Temporal owns task
   lifecycle, approval waiting, and coarse orchestration. ELSPETH owns row
   retries, checkpoints, and resume semantics.
10. **Adopt schema-per-tenant for standard deployments and database-per-tenant
    for regulated deployments.** For regulated financial and healthcare use,
    database-per-tenant is the recommended baseline.

---

## Service Decomposition

### API Gateway

Standard API gateway (Kong, Envoy, or cloud-native equivalent):

- OAuth2/OIDC authentication
- Per-user and per-workspace rate limiting
- HTTP routing
- WebSocket upgrade for progress streaming
- Audit-friendly request correlation IDs

Routes:

- `/api/conversations/*` -> Conversation Service
- `/api/tasks/*` -> Temporal visibility facade
- `/api/artifacts/*` -> Artifact Service
- `/api/policy/*` -> Policy Service

### Conversation Service

The Conversation Service owns user interaction, composition state, deterministic
review material generation, and AI interpretation.

Responsibilities:

- Accept natural language task descriptions
- Bind uploaded data or external data references to the task
- Drive the composition API via an LLM composer
- Apply user edits and refinements
- Generate deterministic technical specs from composition state
- Generate labeled AI explanations for usability
- Request preview or full execution through Temporal

It does **not** run the pipeline itself.

### Policy and Artifact Services

#### Policy Service

Owns platform-level security and governance rules:

- Plugin tier policy
- Data sensitivity floor policy
- Workspace-level tier floors
- Static security rules (allowlists, destination policies, secret reference
  rules, prohibited config patterns)
- Plugin allow/deny controls (when enabled)

#### Artifact Service

Owns write-once storage and retrieval for:

- `PipelineArtifact` versions
- approval records
- preview records
- deterministic specs
- methodology/citation exports
- lineage chains between refined versions

### Workflow Orchestration (Temporal)

Temporal owns durable task state, not ELSPETH's internal row-processing logic.

High-level workflow phases:

```python
@workflow.defn
class PipelineTaskWorkflow:
    @workflow.run
    async def run(self, request: StartTaskRequest) -> TaskResult:
        artifact = await workflow.execute_activity(create_artifact, args=[request])
        await workflow.execute_activity(run_static_policy_check, args=[artifact.hash])
        tier = await workflow.execute_activity(compute_tier, args=[artifact.hash])

        if tier == ExecutionTier.NO_REVIEW_REQUIRED and artifact.preview_plan.auto_run:
            await workflow.execute_activity(run_preview, args=[artifact.hash, None])

        if tier != ExecutionTier.NO_REVIEW_REQUIRED:
            await workflow.wait_condition(self._approval_satisfied)

        if self._requested_validation_preview:
            await workflow.execute_activity(
                run_preview,
                args=[artifact.hash, self._validation_plan],
            )

        return await workflow.execute_activity(
            execute_artifact,
            args=[artifact.hash, self._checkpoint_id],
            retry_policy=NO_AUTOMATIC_RETRY,
        )
```

Temporal responsibilities:

- durable task and approval state
- approval waiting and signaling
- dispatch to preview and execution workers
- coarse cancellation and visibility
- orchestration around checkpoint resume

Temporal does **not** replace ELSPETH retry logic with its own generic activity
retry behavior.

### Preview Workers

Preview workers are a warm pool optimized for low-latency validation runs.

Characteristics:

- preloaded Python environment and plugin catalog
- short-lived, constrained preview executions
- preview-specific sink substitution and source capability enforcement
- low-latency dispatch path

Preview workers run in a Deployment-style pool, not one fresh pod per preview.

### Execution Workers

Execution workers run full pipeline executions with stricter isolation.

Characteristics:

- one artifact execution per worker
- resource limits sized for real workloads
- direct ELSPETH orchestration
- checkpoint-aware resume behavior
- strong isolation for failures, OOMs, and long-running jobs

Execution workers may be Kubernetes Jobs or Deployment replicas dedicated to the
Temporal task queue for full executions.

### Shared Storage

| Store | Purpose | Technology |
|---|---|---|
| Task DB | tasks, composition state, typed task events, approval records | PostgreSQL |
| Artifact Store | sealed artifacts, previews, methodology exports | object store + indexed metadata |
| Landscape DB | ELSPETH audit trail | PostgreSQL |
| Payload Store | payloads, snapshots, reference data snapshots | S3 / Azure Blob |
| Telemetry Stream | operational events for live UI | Redis Streams |

---

## Pipeline Artifact and Governance

### Sealed PipelineArtifact

The artifact boundary is a write-once `PipelineArtifact`.

```python
@dataclass(frozen=True)
class PipelineArtifact:
    artifact_id: str
    parent_artifact_id: str | None
    version: int
    created_at: datetime
    created_by: str

    # User-reviewed state
    composition_state: CompositionState
    graph_descriptor: GraphDescriptor
    deterministic_spec: DeterministicSpec

    # Executable state
    pipeline_yaml: str

    # Input identity
    data_inputs: list[DataReference]
    reference_datasets: list[ReferenceDatasetBinding]

    # Governance and runtime identity
    plugin_catalog_hash: str
    classification_policy_hash: str
    workspace_policy_hash: str
    elspeth_version: str
    pipeline_tier: ExecutionTier
    tier_reasons: list[TierReason]
    data_sensitivity: DataSensitivityDeclaration | None

    # Preview plan
    preview_plan: PreviewPlan

    # Integrity
    canonical_hash: str
```

**Why this shape exists:**

- `composition_state` preserves the exact user-intent config
- `graph_descriptor` drives deterministic review rendering
- `pipeline_yaml` is what ELSPETH executes
- policy and catalog hashes capture hidden execution dependencies
- preview plan captures row selection and preview semantics

Any refinement creates a new artifact version linked to its parent.

### Approval Records and Approval Scope

Approvals are stored as immutable records that reference an artifact. They are
not mutable fields inside the artifact.

```python
@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    artifact_hash: str
    actor: str
    action: ApprovalAction  # approve | reject
    execution_tier: ExecutionTier
    preview_run_ids: list[str]
    approval_scope_hashes: list[str]
    comment: str | None
    created_at: datetime
```

#### Approval scope hashing

Selective re-approval is permitted only when the approved scope is unchanged.

For each gated node or gated execution boundary, compute:

```text
approval_scope_hash =
  hash(
    artifact_hash,
    gated_boundary_id,
    upstream_subgraph_hash(gated_boundary_id),
    sink_contract_hash(gated_boundary_id)
  )
```

Implication:

- changing a prompt upstream of a gated sink invalidates the sink approval
- changing the destination or sink settings invalidates the sink approval
- purely cosmetic graph layout changes do not invalidate approvals

This avoids the unsafe "unchanged node means unchanged approval" shortcut.

### Three-Tier Enforcement Model

| Tier | Enforcement | Typical meaning |
|---|---|---|
| `no_review_required` | no human gate; automatic preview when eligible | low-risk operations |
| `approval_required` | one authenticated signature required | medium-risk operations |
| `two_approval_required` | two distinct authenticated signatures required | high-risk or externally consequential operations |

There is no checkbox acknowledgment tier.

### Tier Computation

The platform computes tier server-side using only policy and artifact facts.

```text
pipeline_tier =
  max(
    max(plugin_floor(plugin) for plugin in pipeline_plugins),
    sensitivity_floor(data_sensitivity),
    workspace_floor(workspace_policy)
  )
```

Rules:

- the model cannot influence tier computation
- unclassified plugins default to `approval_required`
- workspace or data sensitivity can only raise the tier
- the computed tier and all contributing reasons are recorded in audit events

### Classification Config Governance

The plugin classification config is itself a security-critical artifact.

Requirements:

- versioned and immutable in production
- two-administrator authorization for policy changes
- full event logging of old value, new value, actors, timestamp, justification
- referenced by every artifact and execution via `classification_policy_hash`

This is the "who governs the governors" control. Without it, structural
enforcement can be silently eroded by policy edits.

---

## Preview and Validation Model

Preview is a governed execution mode, not a UI convenience feature.

### Preview Modes

#### 1. Automatic preview

Used only when:

- pipeline tier is `no_review_required`
- all sources support safe preview
- static security policy check has passed

Behavior:

- platform selects sample rows deterministically
- preview runs automatically before the user is asked to execute
- preview evidence is shown alongside the deterministic spec

#### 2. Validation preview

Used for `approval_required` and `two_approval_required` flows, or when the user
explicitly requests validation.

Behavior:

- initiated under explicit platform policy
- may require the same approval gate as the full run, depending on source and
  data policy
- never performs approval-required external writes during preview
- uses preview-safe sink substitution for write sinks

#### 3. No live preview

Used when source semantics make live preview unsafe or impractical.

Behavior:

- user must provide a design-time sample or validation case library
- platform validates artifact structure and may run preview on supplied sample
- no live read is performed against the original source

### Preview row selection

Preview row selection is platform-determined and audit-recorded.

Supported strategies:

- `first_n`
- `seeded_stratified_sample`
- `validation_case_library`
- `explicit_user_case_set` (for governed validation flows)

Recorded with every preview:

- selection policy
- seed, if used
- selected row identifiers
- preview run ID
- source capability mode used

The model does not choose preview rows.

### Source preview capabilities

Every source classifies preview support explicitly.

```python
class PreviewCapability(Enum):
    LIVE_SAMPLE_OK = "live_sample_ok"
    DESIGN_TIME_SAMPLE_REQUIRED = "design_time_sample_required"
    NO_PREVIEW = "no_preview"
```

Examples:

- CSV file on object storage -> `LIVE_SAMPLE_OK`
- message queue / Kafka / SQS -> `DESIGN_TIME_SAMPLE_REQUIRED`
- expensive, full-scan API -> `DESIGN_TIME_SAMPLE_REQUIRED`
- destructive or legally prohibited source -> `NO_PREVIEW`

This prevents preview from consuming production queue items or forcing
unexpected full-source scans.

### Validation case libraries

For regulated and high-stakes deployments, preview may use a governed validation
case library instead of a generic sample.

Use cases:

- sanctions screening near-misses
- threshold boundary cases
- known false positive / false negative examples
- organization-specific "must-pass" scenarios

Validation case selection and results are recorded in the approval evidence.

### Preview sink behavior

Preview never performs destructive approval-tier writes.

Rules:

- approval-required sinks are replaced with `PreviewCaptureSink`
- preview may stop at the last non-destructive boundary when substitution would
  misrepresent behavior
- preview output must be clearly labeled as preview-only

This lets reviewers inspect evidence without accidentally committing data to
external systems.

---

## User Experience

### Summary-First Interaction Model

The primary interface is a summary-first review experience, not a graph-first
builder. This is both a usability decision and an accessibility decision.

Users first see:

1. task title and business purpose
2. deterministic technical specification
3. AI explanation labeled as contextual
4. preview evidence, if available
5. pipeline-level governance banner
6. outputs and expected artifacts

### Graph Editor Role

The graph editor is available for users who want structural inspection, but it
is not the only way to understand or approve a pipeline.

Rules:

- summary view must offer functional parity for review and approval
- graph is secondary, not required
- graph layout changes are non-semantic
- node indicators are explanatory, not approval gates

### Pipeline-Level Review UX

The user approves the pipeline as a whole.

Example banner:

```text
APPROVAL REQUIRED
Reason: this pipeline includes database_sink and processes declared PII.

Evidence shown below:
- deterministic technical spec
- preview results from run preview-123
- destination summary

Actions:
[Refine Pipeline] [Submit for Approval]
```

Per-node indicators still show which components drive the tier, but they are
not separate interactive gates.

### Dual-layer summaries

Every review surface includes three layers:

1. **Deterministic technical specification**
   - plugin list
   - field mappings
   - routing rules
   - model choice and configurable parameters
   - destination summary
2. **AI explanation**
   - plain-language explanation
   - explicitly labeled as AI-generated and non-authoritative
3. **Trial evidence**
   - preview outputs or validation-case outputs

Approvals bind to the deterministic spec and preview evidence, not the AI text.

### Refinement Diff and Selective Re-Approval

Refinement creates a new artifact version with a structural diff against the
prior version.

The diff view shows:

- added nodes and edges
- removed nodes and edges
- changed settings
- changed tier drivers
- changed approval scopes

Carry-forward rule:

- prior approvals carry forward only where approval scope hashes are unchanged
- any changed upstream contract invalidates downstream approvals
- if pipeline tier increases, approval restarts from zero

This supports iteration without sacrificing approval integrity.

---

## Config Generation Layer

The platform uses a declarative composition model. The LLM does not emit raw
YAML and should not drive the system through brittle imperative "set one field"
knobs.

### Declarative Composition State

`CompositionState` is the canonical user-intent config.

```python
@dataclass(frozen=True)
class CompositionState:
    source: SourceSpec
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    outputs: list[OutputSpec]
    metadata: PipelineMetadata
```

Every state mutation is validated and versioned.

### Composition API

#### Discovery tools

- `list_sources`
- `list_transforms`
- `list_sinks`
- `get_plugin_schema`
- `infer_data_schema`
- `get_expression_grammar`
- `list_templates`

#### Mutation tools

Mutation tools are declarative and state-reflecting.

```python
tools = [
    "set_source_spec(source_spec)",
    "upsert_node_spec(node_id, partial_node_spec)",
    "upsert_edge_spec(edge_id, edge_spec)",
    "remove_node(node_id)",
    "set_pipeline_metadata(metadata_patch)",
]
```

Each call returns:

- validation result
- full updated state of affected object
- affected pipeline summary
- current tier estimate
- any approval scope changes

This keeps model context synchronized with actual platform state.

#### Review tools

- `validate_pipeline_state`
- `generate_deterministic_spec`
- `compute_pipeline_tier`
- `plan_preview`
- `run_preview`
- `finalize_artifact`

### LLM Composer Loop

The LLM composer operates over tools and current state.

```python
async def compose_pipeline(prompt: str, context: CompositionContext) -> PipelineArtifactDraft:
    state = context.initial_state
    for turn in range(MAX_TURNS):
        response = await llm.chat(
            messages=context.messages_for(state),
            tools=COMPOSITION_TOOLS,
        )
        for call in response.tool_calls:
            result = composition_api.execute(call)
            state = result.current_state
        if response.requests_finalization:
            return composition_api.finalize_draft(state)
    raise CompositionError("Composer did not converge")
```

The reviewable object is the finalized draft state and its derived spec, not the
raw model response stream.

### Deterministic Mapping to ELSPETH YAML

`CompositionState -> GraphDescriptor -> DeterministicSpec -> pipeline_yaml`
must be deterministic and reversible enough for audit.

Rules:

- mapping logic is pure and versioned
- defaults injected during derivation are explicit in the deterministic spec
- artifact stores both composition state and YAML
- auditors can inspect "what the user approved" and "what ELSPETH executed"

This closes the audit visibility gap between UI state and executable contract.

---

## Execution and Orchestration

### Temporal Responsibilities

Temporal owns:

- task lifecycle state
- approval wait states
- preview dispatch
- execution dispatch
- timeout at the task-orchestration level
- cancellation requests
- visibility and operational status

It does **not** own fine-grained execution retry policy inside ELSPETH.

### ELSPETH Responsibilities

ELSPETH owns:

- graph validation at execution time
- row processing
- plugin execution
- row-level retries and backoff
- checkpoint creation
- deterministic audit recording in Landscape
- sink semantics

### Retry, Checkpoint, and Resume Ownership

This boundary must be explicit to avoid duplicate work and replay confusion.

Rules:

1. `execute_artifact` activity retries are disabled except for narrow
   infrastructure failures before ELSPETH has begun work.
2. Once ELSPETH has started, retry and backoff are ELSPETH concerns.
3. Workers emit checkpoint identifiers to Temporal as workflow-visible progress.
4. On worker crash, Temporal schedules a `resume_artifact(checkpoint_id)`
   activity, not a blind fresh rerun.
5. Sinks used in resumable flows must be idempotent or protected by ELSPETH's
   checkpoint and sink contract.

This prevents Temporal and ELSPETH from acting as competing state machines.

### Cancellation

Cancellation must be real, not a dead signal.

Behavior:

- Temporal records cancellation request
- execution worker receives cancellation signal
- ELSPETH transitions to a controlled stop at the next safe checkpoint boundary
- Landscape and task audit both record a cancelled terminal outcome

### Preview Latency Strategy

Interactive refinement requires low-latency previews.

Strategy:

- warm preview worker pool
- preloaded plugin catalog and dependencies
- preview-specific queue
- bounded preview data volume
- fast-fail capability checks before dispatch

Full executions continue to use heavier isolation.

---

## Telemetry and Real-Time Progress

Telemetry is operational visibility, not the legal audit record.

Use Redis Streams instead of pub/sub:

```python
class RedisStreamsTelemetryExporter(TelemetryExporter):
    def export(self, events: list[TelemetryEvent]) -> None:
        for event in events:
            self._redis.xadd(
                f"task:{self._task_id}:telemetry",
                event.to_stream_fields(),
                maxlen=STREAM_RETENTION,
                approximate=True,
            )
```

Why Streams:

- reconnect-safe consumer model
- cursor-based replay after transient disconnect
- bounded retention
- suitable for WebSocket fanout

UI views consume the telemetry stream for:

- step progress
- row counts
- quarantine counts
- cost estimates
- preview completion
- full-run completion

---

## Audit Trail and Meta-Level Provenance

ELSPETH Landscape remains the source of truth for execution lineage. The
semi-autonomous platform adds a typed task event log for design and governance.

```python
@dataclass(frozen=True)
class PromptSubmitted:
    task_id: str
    actor: str
    prompt_text: str
    data_inputs: list[DataReference]

@dataclass(frozen=True)
class ArtifactCreated:
    task_id: str
    actor: str
    artifact_hash: str
    pipeline_tier: ExecutionTier
    classification_policy_hash: str

@dataclass(frozen=True)
class PreviewExecuted:
    task_id: str
    actor: str
    artifact_hash: str
    preview_run_id: str
    selection_policy: str
    row_identifiers: list[str]

TaskEvent = PromptSubmitted | ArtifactCreated | PreviewExecuted | ...
```

Key event types:

- prompt submitted
- composition state updated
- static policy check passed/failed
- tier computed
- artifact created
- preview planned
- preview executed
- approval requested
- approval granted/rejected
- execution started
- execution resumed from checkpoint
- execution completed/cancelled/failed
- methodology export generated
- research finding promotion recorded

Each full execution links task audit to Landscape via `run_id`. Each preview does
the same via `preview_run_id`.

---

## Security, Isolation, and Data Governance

### Static Security Policy Enforcement

Before any artifact is presented for review, and again before execution, the
platform performs deterministic policy validation.

Examples:

- HTTP-capable plugins may only target allowlisted domains or registered named
  destinations
- external write sinks may only target approved destinations
- no `@env_var` interpolation in model-generated fields
- no raw secrets in composition state
- no prohibited plugin combinations for the workspace

This is the primary technical control for `no_review_required` flows.

### Tenant Isolation

Recommended deployment modes:

| Deployment type | Isolation model |
|---|---|
| standard internal deployment | schema-per-tenant |
| regulated financial services | database-per-tenant |
| healthcare / HIPAA-sensitive | database-per-tenant |
| any physical separation requirement | database-per-tenant |

Schema-per-tenant is acceptable for standard deployments but shares
infrastructure-level concerns such as WAL, autovacuum, and superuser control.

### Reference Data Versioning

Reference data used for classification is versioned like any other critical
input.

Recorded per run:

- dataset name
- declared version
- content hash
- immutable snapshot location

This is required for sanctions lists, jurisdiction tables, risk taxonomies,
threshold tables, and similar dynamic inputs.

### Data Sensitivity Declaration

Users or platform policy may declare data sensitivity at submission time.

Examples:

- contains PII
- regulated financial records
- HIPAA-covered data
- privileged internal documents

Effects:

- sensitivity can raise tier, never lower it
- declaration is immutable once artifact is created
- elevation reason is recorded in audit events

---

## User-Facing Accountability Features

These are part of the platform design, not optional polish.

### Template library

Templates support:

- onboarding
- few-shot guidance for generation
- predictable tier expectations
- organizational reuse

Template types:

- personal
- workspace-shared
- platform-curated

### Methodology citation export

Every completed run may generate a citation-ready methodology artifact with:

- pipeline name
- run date
- run ID
- model version and parameters
- prompt text
- row counts
- quarantine counts and reasons
- representative input/output samples

This is derived from the deterministic spec and execution records.

### Quarantine explanation

Quarantined rows must be presented in user-accessible terms:

- plain-English reason
- suggested remediation
- impact on result validity

This is essential for research and compliance users, not just debugging.

### Screening aid vs research finding mode

Default mode is screening aid / preliminary result.

Optional promotion to research finding requires:

- methodology attachment
- explicit user confirmation
- audit event recording the promotion

This supports both compliance and research personas without conflating the two.

---

## Technology Choices

### Backend

| Component | Technology | Rationale |
|---|---|---|
| API Gateway | Kong / Envoy / cloud-native | standard edge routing |
| Conversation Service | FastAPI | typed async service, stack alignment |
| Workflow Engine | Temporal | durable approval and task state |
| Preview workers | Kubernetes Deployment | warm pool, low-latency dispatch |
| Execution workers | Kubernetes Job / dedicated Deployment | isolation for full runs |
| Task DB | PostgreSQL | relational task and governance state |
| Landscape DB | PostgreSQL | native ELSPETH backend |
| Telemetry channel | Redis Streams | reconnect-safe progress streaming |
| Object storage | S3 / Azure Blob | artifacts, payloads, snapshots |

### Frontend

| Component | Technology | Rationale |
|---|---|---|
| Summary UI | React + TypeScript | primary review experience |
| Graph editor | React Flow | secondary structural visualization |
| State management | Zustand or Jotai | local composition/view state |
| Streaming | native WebSocket + stream cursors | live progress and replay |

### LLM for composition

Requirements for the composition model:

- strong tool-use behavior
- good long-horizon state tracking
- reliable schema-driven reasoning
- stable incremental refinement

The model used for composition is separate from any model invoked by the
pipeline itself.

---

## Non-Functional Targets

These targets are preliminary but should be treated as architecture-shaping.

### Reliability

- no duplicate sink writes during checkpoint-based resume for supported sinks
- every preview and full execution produces a typed task audit trail
- policy hashes and artifact hashes are verified at execution time

### Performance

- warm-pool preview target: P50 under 2s, P95 under 5s for
  `LIVE_SAMPLE_OK` sources and small sample previews
- approval notification dispatch under 60s
- full-run startup target under 30s after approval for warm cluster conditions

### Quality

- benchmark suite for composition tasks must reach >= 90% structural accuracy
  before production rollout
- deterministic spec generation must be reproducible from artifact state

### Security and governance

- classification policy changes require two-admin authorization
- unclassified plugins fail closed to `approval_required`
- tenant isolation model must be explicit per deployment type

---

## What Exists vs What Needs Building

| Component | Status | Work Required |
|---|---|---|
| `Orchestrator.run()` programmatic execution path | Exists | extract clean service-facing API if needed |
| `instantiate_plugins_from_config()` | Exists | reuse |
| `ExecutionGraph.from_plugin_instances()` | Exists | reuse |
| validation logic in ELSPETH | Exists | expose as service/library surface |
| PostgreSQL Landscape backend | Exists | reuse |
| telemetry framework | Exists | add Redis Streams exporter |
| plugin catalog discovery | Exists | serialize for composition/policy use |
| Pydantic config schemas | Exists | expose through composition API |
| expression parser | Exists | expose grammar and validation tools |
| sealed artifact store | New | immutable artifact persistence and hashing |
| classification policy service | New | versioned governance config |
| declarative composition API | New | state model, tools, validation |
| deterministic spec generator | New | audit-grade review rendering |
| preview planning and source capability layer | New | source preview modes, sink substitution |
| warm preview worker pool | New | low-latency preview execution |
| approval workflow service | New | one- and two-signature flows, notifications |
| typed task event schema | New | meta-audit persistence |
| methodology citation export | New | user-facing attestation artifacts |
| template library | New | onboarding and reuse |
| quarantine explanation layer | New | user-facing remediation output |

---

## Open Questions

These questions remain open after incorporating the current review feedback.

1. **Data upload flow.** Pre-upload to object storage is the preferred path, but
   exact UX for large uploads, resumable uploads, and references to external
   storage needs product design.
2. **LLM cost attribution and quotas.** Composition-model cost and pipeline-model
   cost need a shared metering story.
3. **Plugin allow/deny policy surface.** Workspace-level controls are desirable,
   but exact admin UX and policy granularity remain open.
4. **Validation case authoring UX.** The architecture supports validation case
   libraries, but the authoring workflow needs product design.
5. **Citation format targets.** PDF/plain text is sufficient for v1, but APA,
   Chicago, and BibTeX support may matter for research adoption.
6. **Jurisdiction-specific legal overlays.** Data residency, AML notification,
   and formal model validation obligations vary by jurisdiction and must be
   resolved with legal/compliance partners rather than architecture alone.

---

Built for systems where pipeline generation must be **auditable, governable,
reviewable, and operationally credible** rather than merely convenient.
