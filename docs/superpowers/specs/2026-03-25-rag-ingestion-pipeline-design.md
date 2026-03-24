# RAG Ingestion Pipeline — Design Spec

**Date:** 2026-03-25
**Status:** Draft (R1)
**Target ChromaDB version:** `chromadb >= 0.4`
**Scope:** ChromaSink plugin, pipeline `depends_on` mechanism, commencement gates, RAG retrieval readiness contract

## Overview

Complete the RAG story in ELSPETH by adding the ingestion side: a ChromaDB sink plugin that writes documents into a vector store, a `depends_on` mechanism that sequences pipeline runs, commencement gates that evaluate go/no-go conditions before a pipeline starts, and a readiness contract on the RAG retrieval transform that refuses to run against an empty collection.

This is the dogfood for three new engine capabilities. The ChromaSink is the first vector store sink. The `depends_on` and commencement gate mechanisms are the first pipeline-level orchestration primitives. The readiness contract is the first plugin pre-condition check.

## Motivation

ELSPETH's RAG retrieval transform queries a pre-populated vector store, but the framework has no way to populate that store. The current workaround is a standalone `seed_collection.py` script that runs outside ELSPETH's audit model. This creates an audit gap: an auditor asking "what reference documents were available when row 42 was classified?" gets no answer from the Landscape, because the seeding happened off-book.

Bringing ingestion into ELSPETH as a proper pipeline closes this gap. Every document indexed into the vector store gets its own `token_id`, audit trail entry, and canonical content hash. The `depends_on` mechanism ensures the indexing pipeline runs before the query pipeline. Commencement gates verify the corpus is ready. The readiness contract on the RAG transform is a belt-and-suspenders guard.

### Design Principles

- **Indexing and querying are separate pipelines.** They have different schedules, failure modes, and scaling profiles. Forcing them into one pipeline creates coupling that doesn't need to exist.
- **The plugin doesn't know how the data got there.** The RAG transform's readiness check verifies the collection has data. It doesn't care whether that data came from a `depends_on` pipeline, a manual script, or an external indexer.
- **Fail loudly at the earliest possible moment.** A pipeline that would produce a run full of zero-chunk retrievals should never start.

## Architecture

### File Layout

New files:

```
src/elspeth/plugins/
├── sinks/
│   └── chroma_sink.py                          # ChromaSink plugin
└── infrastructure/
    └── clients/
        └── retrieval/
            ├── base.py                          # +check_readiness() on protocol
            ├── types.py                         # +ReadinessResult dataclass
            ├── chroma.py                        # +check_readiness() implementation
            └── azure_search.py                  # +check_readiness() implementation

src/elspeth/core/
└── config.py                                    # +DependencyConfig, +CommencementGateConfig

src/elspeth/engine/
└── orchestrator/
    └── core.py                                  # +dependency resolution phase
                                                 # +commencement gate evaluation phase

src/elspeth/contracts/
└── errors.py                                    # +DependencyFailedError
                                                 # +CommencementGateFailedError
                                                 # +RetrievalNotReadyError
```

Modified files:

```
src/elspeth/plugins/transforms/rag/transform.py  # +readiness check in on_start()
src/elspeth/plugins/infrastructure/discovery.py   # No change needed (auto-discovers sinks/)
```

### Layer Placement

All new code lives in existing layers. One cross-layer dependency requires a protocol-based injection pattern (see Commencement Gates, Collection Probing):

| Component | Layer | Rationale |
|-----------|-------|-----------|
| `ChromaSink` | L3 (plugins/sinks) | Sink plugin, same as CSV/JSON/Database sinks |
| `ReadinessResult` | L3 (plugins/infrastructure) | Provider-specific type, alongside `RetrievalChunk` |
| `check_readiness()` | L3 (plugins/infrastructure) | Provider method, alongside `search()` |
| `CollectionProbe` protocol | L0 (contracts/) | Protocol for collection readiness probes, defined in contracts so L2 can depend on it |
| `DependencyConfig` | L1 (core/config) | Pipeline config, alongside `RetrySettings` |
| `CommencementGateConfig` | L1 (core/config) | Pipeline config, alongside `RetrySettings` |
| `DependencyRunResult` | L1 (core/config) | Frozen dataclass for dependency run metadata |
| `GateResult` | L1 (core/config) | Frozen dataclass for gate evaluation metadata |
| Dependency resolution | L2 (engine/orchestrator) | Engine orchestration logic |
| Commencement gate evaluation | L2 (engine/orchestrator) | Engine orchestration logic, receives probes via injection |
| Collection probe implementations | L3 (plugins/infrastructure) | ChromaDB/Azure implementations of `CollectionProbe` |
| Error types | L0 (contracts/errors) | Shared error types |

## Component 1: ChromaSink Plugin

### Purpose

Write pipeline rows into a ChromaDB collection. Each row becomes a document. ChromaDB handles embedding internally via its configured embedding function.

### Config Model

```yaml
sinks:
  corpus_output:
    plugin: chroma_sink
    options:
      collection: science-facts
      mode: persistent                  # persistent | client
      persist_directory: ./chroma_data  # Required for persistent mode
      # OR for client mode:
      # host: chroma.internal
      # port: 8000
      distance_function: cosine         # cosine | l2 | ip

      field_mapping:
        document: text_content          # Row field -> Chroma document text
        id: doc_id                      # Row field -> Chroma document ID
        metadata:                       # Row fields -> Chroma metadata dict
          - topic
          - subtopic

      on_duplicate: overwrite           # overwrite | skip | error

      schema:
        mode: fixed
        fields:
          - "doc_id: str"
          - "text_content: str"
          - "topic: str"
          - "subtopic: str"

landscape:
  url: sqlite:///./runs/audit.db
```

### Config Class: `ChromaSinkConfig`

Extends `DataPluginConfig`. Pydantic model with:

- **`collection`** (str, required): ChromaDB collection name.
- **`mode`** (Literal["persistent", "client"], required): How to connect. Mirrors `ChromaSearchProviderConfig`.
- **`persist_directory`** (str, required if mode=persistent): Path to ChromaDB data directory. Resolved relative to the pipeline config file.
- **`host`** (str, required if mode=client): ChromaDB server hostname.
- **`port`** (int, default 8000, required if mode=client): ChromaDB server port.
- **`distance_function`** (Literal["cosine", "l2", "ip"], default "cosine"): Passed to `get_or_create_collection()` as `hnsw:space` metadata.
- **`field_mapping`** (FieldMappingConfig, required): Maps row fields to Chroma concepts. Sub-model with:
  - `document` (str): Row field containing text to embed.
  - `id` (str): Row field containing document ID.
  - `metadata` (list[str]): Row fields to include as Chroma metadata.
- **`on_duplicate`** (Literal["overwrite", "skip", "error"], default "overwrite"): Behaviour when a document ID already exists.

Field mapping is required, not optional. No convention-based defaults.

**Validation rules:**
- `persist_directory` required when `mode=persistent`, forbidden when `mode=client`.
- `host` required when `mode=client`, forbidden when `mode=persistent`.
- All `field_mapping` fields must appear in the schema's field list.
- `field_mapping.document` and `field_mapping.id` must be `str` type fields.
- Client mode: HTTPS required unless host is localhost (mirrors `ChromaSearchProviderConfig`).

### Lifecycle

**`__init__(config: dict)`:**
- Parse `ChromaSinkConfig.from_dict(config)`.
- Build input schema via `create_schema_from_config(..., allow_coercion=False)`. Sinks are Tier 2 — wrong types are an upstream bug.

**`on_start(ctx: LifecycleContext)`:**
- Construct ChromaDB client (PersistentClient or HttpClient depending on mode).
- Verify connection: `client.heartbeat()` for client mode, collection access for persistent mode.
- Get or create collection with configured `distance_function`.
- Capture `run_id`, `landscape`, `telemetry_emit` from context.
- If connection fails: raise — pipeline never starts.

**`write(rows: list[dict], ctx: SinkContext) -> ArtifactDescriptor`:**
- Extract mapped fields from each row using `field_mapping`.
- Compute canonical JSON hash of the payload before writing (proves intent).
- Execute write operation based on `on_duplicate`:
  - `overwrite`: `collection.upsert(ids, documents, metadatas)`
  - `skip`: Pre-filter via `collection.get(ids)` to identify existing IDs, then `collection.add()` only the new ones. Skipped IDs are recorded in the call audit (documents we chose not to write).
  - `error`: Pre-check via `collection.get(ids)`. If any IDs exist, raise a pipeline-level error with the duplicate IDs listed. The batch is not written. This is a pipeline-level failure, not a row-level quarantine, because ChromaDB batch operations are all-or-nothing.
- Record call via `ctx.record_call(call_type=EXTERNAL_API, provider="chromadb", ...)`.
- Return `ArtifactDescriptor` with content hash, payload size, row count.
- If audit recording fails after a successful write: raise `AuditIntegrityError` — data was written but not recorded.

**`flush()`:**
- No-op — ChromaDB writes are committed atomically by the server/engine. No explicit flush required from the client side.

**`on_complete(ctx: LifecycleContext)`:**
- Emit telemetry: total documents written, total bytes, collection name.

**`close()`:**
- Release client reference.

### Audit Trail

Every `write()` batch records via `ctx.record_call()`:

| Field | Value |
|-------|-------|
| `call_type` | `CallType.EXTERNAL_API` |
| `provider` | `"chromadb"` |
| `status` | `CallStatus.SUCCESS` or `CallStatus.ERROR` |
| `request_data` | `{operation, collection, row_count, document_ids}` |
| `response_data` | `{rows_written}` |
| `latency_ms` | Wall-clock time of the upsert/add call |

Content hash is computed from the Canonical subsystem's two-phase canonicalization of the payload before the write. This proves what was sent, regardless of what ChromaDB does internally (embedding, tokenization).

### Error Handling

| Scenario | Response |
|----------|----------|
| ChromaDB unreachable in `on_start()` | Raise — pipeline never starts |
| ChromaDB unreachable during `write()` | Raise — engine retry policy applies |
| Row missing a mapped field | Crash — Tier 2 violation, upstream bug |
| Duplicate ID with `on_duplicate: error` | Pipeline-level error — pre-check IDs via `collection.get(ids)` before write, raise if any exist. Since ChromaDB's `add()`/`upsert()` are batch operations, individual row quarantine is not possible. The entire batch fails. |
| Audit recording fails after successful write | Raise `AuditIntegrityError` — data written but unrecorded |

### Config Symmetry with Retrieval Provider

The ChromaSink config deliberately mirrors `ChromaSearchProviderConfig`:

| ChromaSink field | ChromaSearchProviderConfig field |
|-----------------|--------------------------------|
| `collection` | `collection` |
| `mode` | `mode` |
| `persist_directory` | `persist_directory` |
| `host` | `host` |
| `port` | `port` |
| `distance_function` | `distance_function` |

Same field names, same validation rules, same semantics. When an indexing pipeline and a query pipeline target the same store, the config is visually identical. Misconfiguration between the two is easy to catch by inspection.

## Component 2: Pipeline `depends_on` Mechanism

### Purpose

Declare that a pipeline requires other pipelines to run first. Dependencies are fully independent pipeline runs with their own `run_id`, Landscape records, and checkpoint streams.

### Config Shape

New top-level key in pipeline YAML:

```yaml
depends_on:
  - name: index_corpus              # Unique label within the list
    settings: ./index_pipeline.yaml # Path relative to parent config file
```

- `name` (str, required): Human-readable label. Must be unique within the `depends_on` list.
- `settings` (str, required): Path to the dependency pipeline's settings file. Resolved relative to the parent pipeline's settings file directory.

### Config Model: `DependencyConfig`

Pydantic model added to `core/config.py`:

```python
class DependencyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    settings: str
```

`ElspethSettings` gains an optional field:

```python
depends_on: list[DependencyConfig] = Field(default_factory=list)
```

### Execution Semantics

1. Dependencies run sequentially in declared order, before anything else in the main pipeline.
2. For each dependency, the orchestrator:
   a. Resolves the `settings` path relative to the parent config file.
   b. Loads the dependency's `ElspethSettings`.
   c. Creates a new `Orchestrator` instance.
   d. Calls `run()` on the child orchestrator.
   e. Records the result (run_id, status, duration).
3. If any dependency run fails (any non-success terminal state), the main pipeline aborts with `DependencyFailedError`. The error includes the dependency name, its `run_id`, and the failure reason.
4. If all dependencies succeed, execution continues to commencement gates (Component 3), then the main pipeline.

### Child Orchestrator Independence

The child orchestrator is fully independent:

- Own `run_id` — not a child of the parent's run_id.
- Own Landscape records — written to whichever database the dependency's config specifies (which may be the same database as the parent — recommended for audit correlation).
- Own checkpoint stream — the dependency can be resumed independently if it was interrupted in a previous manual run.
- No shared plugin instances, rate limiters, or telemetry sinks.

This means dependency pipelines are testable in isolation: `elspeth run --settings index_pipeline.yaml --execute` produces identical behaviour to when it runs via `depends_on`.

### Landscape Correlation

When the main pipeline's run record is created, it includes a `dependency_runs` metadata field:

```python
{
    "dependency_runs": [
        {
            "name": "index_corpus",
            "run_id": "abc-123",
            "settings_hash": "sha256:...",
            "status": "completed",
            "duration_ms": 4520
        }
    ]
}
```

- `settings_hash`: SHA-256 via the Canonical subsystem's two-phase canonicalization of the dependency's config. Enables drift detection — if the indexing pipeline config changes between runs, the hash changes.
- Stored in the existing run metadata mechanism (freeform JSON blob on the run record) — no Landscape schema migration needed.

### `DependencyRunResult`

Frozen dataclass in `core/config.py`:

```python
@dataclass(frozen=True, slots=True)
class DependencyRunResult:
    name: str
    run_id: str
    settings_hash: str
    status: str
    duration_ms: int
```

All fields are scalars — no `__post_init__` freeze guard needed.

### Engine Changes

The orchestrator's `run()` method gains a new phase inserted before database initialization:

```
[NEW]      Dependency resolution phase
[NEW]      Commencement gate evaluation phase (Component 3)
[EXISTING] Database initialization phase (run record now includes dependency metadata)
[EXISTING] Plugin instantiation and on_start() phase
[EXISTING] Row processing phase
[EXISTING] Cleanup phase
```

The dependency resolution phase:

```python
def _resolve_dependencies(self, settings: ElspethSettings) -> list[DependencyRunResult]:
    results = []
    for dep in settings.depends_on:
        dep_settings_path = self._resolve_relative_path(dep.settings)
        dep_settings = load_settings(dep_settings_path)
        dep_orchestrator = Orchestrator(dep_settings)

        run_result = dep_orchestrator.run()

        if not run_result.success:
            raise DependencyFailedError(
                dependency_name=dep.name,
                run_id=run_result.run_id,
                reason=run_result.failure_reason,
            )

        results.append(DependencyRunResult(
            name=dep.name,
            run_id=run_result.run_id,
            settings_hash=hash_settings(dep_settings),
            status="completed",
            duration_ms=run_result.duration_ms,
        ))
    return results
```

### Nested Dependencies

Dependencies can themselves have `depends_on` declarations. The engine resolves the full dependency graph recursively. If pipeline A depends on B and B depends on C, the execution order is: C → B → A.

### Circular Dependency Detection

Before running any dependencies, the engine recursively traverses the full dependency graph by loading `depends_on` from each referenced settings file (and their dependencies, transitively). It builds a directed graph of settings file paths and checks for cycles using a standard DFS cycle detector. If a cycle is detected, the pipeline fails immediately with a clear error listing the full cycle path. This check is cheap (only reads the `depends_on` key from each config, not the full pipeline) and prevents infinite recursion.

### Idempotency

Dependencies run unconditionally every time the parent pipeline is invoked. There is no "skip if already populated" logic in `depends_on` itself — that concern belongs to commencement gates (future `if_stale` conditions) or external orchestration.

For the dogfood, the recommended pairing is `on_duplicate: overwrite` on the ChromaSink. This makes the indexing pipeline idempotent: re-running it upserts the same documents, producing identical collection state. The audit trail records each re-indexing run separately, which is correct — each run is a distinct operation with its own `run_id` and timing, even if the data is identical.

Operators who want to avoid redundant re-indexing should use external orchestration (e.g., only invoke the query pipeline when the corpus has changed) rather than building conditional execution into `depends_on`. The `depends_on` mechanism is deliberately simple: declare, run, verify.

### Resume Behaviour

On `elspeth resume <run_id>`, dependencies are NOT re-run. Resume picks up the main pipeline from its checkpoint. If the dependencies need re-running (e.g., the collection was corrupted between the original run and the resume), the operator should start a fresh run instead.

### Failure Model

Hard fail only. If a dependency fails, the main pipeline does not start. The operator must fix the dependency issue and rerun. No partial-success thresholds, no automatic retry of dependencies. This is consistent with the "crash on anomaly" philosophy and can be softened later if needed.

### Path Validation

`DependencyConfig.settings` paths are validated at two points:

1. **`elspeth validate` time**: The validator resolves the path and checks that the referenced file exists and is parseable as a valid `ElspethSettings`. This catches typos and missing files before execution.
2. **Runtime**: The orchestrator re-resolves and loads the dependency settings. This is the authoritative check — the validate-time check is a convenience.

### Telemetry

The dependency resolution phase emits telemetry spans for each dependency run, including the dependency name, settings path, and outcome (success/failure with `run_id` and duration). This is operational visibility (ephemeral), not audit (the Landscape correlation is the audit record).

## Component 3: Commencement Gates

### Purpose

Evaluate go/no-go conditions after dependencies complete but before the main pipeline starts. Uses expressions evaluated against a pre-flight context.

### Config Shape

New top-level key in pipeline YAML:

```yaml
commencement_gates:
  - name: corpus_ready
    condition: "collections['science-facts']['count'] > 0"
    on_fail: abort
```

- `name` (str, required): Human-readable label. Must be unique within the list.
- `condition` (str, required): Python expression evaluated against the pre-flight context. Must return a truthy/falsy value.
- `on_fail` (Literal["abort"], default "abort"): What to do when the condition is falsy. Only `abort` is supported initially. The field exists so the config shape is forward-compatible with `warn` or other strategies.

### Config Model: `CommencementGateConfig`

Pydantic model added to `core/config.py`:

```python
class CommencementGateConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    condition: str
    on_fail: Literal["abort"] = "abort"
```

`ElspethSettings` gains an optional field:

```python
commencement_gates: list[CommencementGateConfig] = Field(default_factory=list)
```

### Pre-Flight Context

The engine assembles a context dict that gate expressions evaluate against:

```python
{
    "dependency_runs": {
        "index_corpus": {
            "status": "completed",
            "run_id": "abc-123",
            "duration_ms": 4520,
        }
    },

    "collections": {
        "science-facts": {
            "reachable": True,
            "count": 450,
        }
    },

    "env": {
        "ENVIRONMENT": "production",
        ...
    },
}
```

**`dependency_runs`**: Results from the dependency resolution phase. Keyed by dependency `name`. Empty dict if no `depends_on` declared.

**`collections`**: ChromaDB collection probes, assembled via the `CollectionProbe` protocol (see Collection Probing below).

**`env`**: `os.environ` snapshot. Available for gate expression evaluation but **excluded from the Landscape context_snapshot** to avoid recording secrets.

### Collection Probing — Layer-Safe Injection

The orchestrator (L2) cannot directly construct ChromaDB clients (L3). Collection probing uses a protocol defined in L0, implemented in L3, and injected into L2:

**Protocol** (L0, `contracts/probes.py`):

```python
@runtime_checkable
class CollectionProbe(Protocol):
    """Probes a vector store collection for readiness."""
    collection_name: str

    def probe(self) -> CollectionProbeResult: ...

@dataclass(frozen=True, slots=True)
class CollectionProbeResult:
    collection: str
    reachable: bool
    count: int
```

`CollectionProbeResult` has only scalar fields — no `__post_init__` freeze guard needed.

**Implementations** (L3, `plugins/infrastructure/clients/retrieval/`):
- `ChromaCollectionProbe`: Constructs a ChromaDB client, calls `collection.count()`.
- `AzureSearchCollectionProbe`: Calls the Azure Search count endpoint.

**Assembly** (L3, `plugins/infrastructure/`):
A factory function `build_collection_probes(settings: ElspethSettings) -> list[CollectionProbe]` scans the pipeline config for plugins referencing collections (RAG transform's `provider_config.collection`, ChromaSink's `collection`). For each unique collection, it constructs the appropriate probe using the plugin's connection config. This function lives in L3 and is called by the orchestrator before gate evaluation.

**Injection into L2:**
The orchestrator calls `build_collection_probes()` and receives a list of `CollectionProbe` protocol objects. It calls `probe.probe()` on each and assembles the `collections` context dict. The orchestrator never imports ChromaDB or any L3 client — it only knows the L0 protocol.

If a probe raises an exception (collection unreachable), the result is `CollectionProbeResult(collection=name, reachable=False, count=0)`. Probe failures do not abort the pipeline directly. However, a gate condition like `collections['science-facts']['count'] > 0` will evaluate to `False` when `count=0` (whether the collection is empty or unreachable), causing the gate to fail. The effective behaviour is that unreachable collections fail count-based gates — this is by design, not an accident.

### Expression Evaluation

Gate expressions are evaluated using Python's `eval()` in a restricted namespace containing only the pre-flight context dict keys. No builtins, no imports, no function calls beyond dict/list operations.

The restricted namespace:

```python
namespace = {
    "__builtins__": {},      # No builtins
    "dependency_runs": ...,
    "collections": ...,
    "env": ...,
}
result = eval(gate.condition, namespace)
```

**Security note:** The `__builtins__: {}` restriction is advisory, not a security sandbox. It prevents accidental use of `print()`, `open()`, etc. but is not hardened against deliberate bypass. This is acceptable because operators control their own pipeline configs — gate expressions are not a user-facing attack surface. If ELSPETH later accepts untrusted pipeline configs, this must be replaced with a proper sandbox (AST whitelist or a restricted expression language).

If the expression raises an exception, the gate fails with the exception message included in the error. This is intentional — a gate expression that can't evaluate is a configuration error, not a pass.

### Execution

Gates are evaluated sequentially in declared order, after dependency resolution, before database initialization.

```python
def _evaluate_commencement_gates(
    self,
    gates: list[CommencementGateConfig],
    context: dict[str, Any],
) -> list[GateResult]:
    results = []
    for gate in gates:
        try:
            result = eval(gate.condition, {"__builtins__": {}, **context})
            passed = bool(result)
        except Exception as exc:
            raise CommencementGateFailedError(
                gate_name=gate.name,
                condition=gate.condition,
                reason=f"Expression raised {type(exc).__name__}: {exc}",
                context_snapshot=context,
            ) from exc

        if not passed:
            raise CommencementGateFailedError(
                gate_name=gate.name,
                condition=gate.condition,
                reason="Condition evaluated to falsy",
                context_snapshot=context,
            )

        results.append(GateResult(
            name=gate.name,
            condition=gate.condition,
            result=True,
            context_snapshot=_build_audit_snapshot(context),
        ))
    return results
```

### Context Snapshot for Audit

The context snapshot recorded in the Landscape includes `dependency_runs` and `collections` but **excludes `env`** (may contain secrets). The snapshot is deep-frozen via `deep_freeze()` at the point of capture, before being passed to `CommencementGateFailedError` or stored as run metadata. This ensures the dict cannot be mutated between capture and Landscape write — it is Tier 1 data from the moment of capture.

```python
def _build_audit_snapshot(context: dict[str, Any]) -> Mapping[str, Any]:
    """Build a frozen context snapshot for audit, excluding env."""
    snapshot = {
        "dependency_runs": context.get("dependency_runs", {}),
        "collections": context.get("collections", {}),
    }
    return deep_freeze(snapshot)
```

### `GateResult`

Frozen dataclass in `core/config.py`:

```python
@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    condition: str
    result: bool
    context_snapshot: Mapping[str, Any]

    def __post_init__(self) -> None:
        freeze_fields(self, "context_snapshot")
```

### `CommencementGateFailedError`

Plain exception subclass in `contracts/errors.py` (not a dataclass). Receives `context_snapshot` as a deep-frozen `Mapping` — the caller is responsible for freezing before construction (enforced by `_build_audit_snapshot()`).

### Landscape Record

Gate results are included in the main pipeline's run metadata:

```python
{
    "commencement_gates": [
        {
            "name": "corpus_ready",
            "condition": "collections['science-facts']['count'] > 0",
            "result": true,
            "context_snapshot": {
                "dependency_runs": {"index_corpus": {"status": "completed", ...}},
                "collections": {"science-facts": {"count": 450, "reachable": true}}
            }
        }
    ]
}
```

The snapshot provides full auditability of the go/no-go decision. Environment variables are excluded to prevent secret leakage into the audit trail.

### Telemetry

The commencement gate evaluation phase emits telemetry spans for each gate, including the gate name, condition expression, and result. This is operational visibility alongside the dependency resolution telemetry spans.

## Component 4: RAG Retrieval Readiness Contract

### Purpose

The existing `RAGRetrievalTransform` gains a readiness check in `on_start()` that verifies the target collection exists and has documents. If the check fails, the pipeline crashes immediately.

### Provider Protocol Extension

`RetrievalProvider` gains a new method:

```python
@runtime_checkable
class RetrievalProvider(Protocol):
    def search(self, query: str, top_k: int, min_score: float,
               *, state_id: str, token_id: str) -> list[RetrievalChunk]: ...

    def check_readiness(self) -> ReadinessResult: ...
```

### ReadinessResult

New frozen dataclass in `plugins/infrastructure/clients/retrieval/types.py`:

```python
@dataclass(frozen=True, slots=True)
class ReadinessResult:
    ready: bool
    collection: str
    document_count: int
    message: str
```

All fields are scalars — no `__post_init__` freeze guard needed.

- `ready`: `True` if collection exists and has at least one document.
- `collection`: Collection name that was checked.
- `document_count`: Number of documents found (0 if collection doesn't exist).
- `message`: Human-readable status. Examples:
  - `"Collection 'science-facts' has 450 documents"`
  - `"Collection 'science-facts' not found"`
  - `"Collection 'science-facts' is empty"`

### Provider Implementations

**ChromaSearchProvider.check_readiness():**
- Get collection by name. If not found, return `ReadinessResult(ready=False, ..., message="Collection '...' not found")`.
- Call `collection.count()`. If 0, return not ready. Otherwise return ready with count.

**AzureSearchProvider.check_readiness():**
- `GET /indexes/{index_name}/docs/$count` via the audited HTTP client.
- If index not found (404), return not ready.
- If count is 0, return not ready.
- Otherwise return ready with count.

Both implementations wrap external calls with the same error handling as `search()` — transient errors are retryable, permanent errors are not.

`check_readiness()` is a single-attempt call — it does not go through the engine's retry machinery. It runs during `on_start()`, which is a setup phase, not a row-processing phase. If a transient network error causes the readiness check to fail, the pipeline fails to start, and the operator retries the entire run. This is acceptable for a pre-condition check — retrying silently would mask infrastructure problems that the operator should know about.

All existing `RetrievalProvider` implementations (`ChromaSearchProvider`, `AzureSearchProvider`) must be updated with `check_readiness()` in the same commit as the protocol extension.

### Transform Integration

In `RAGRetrievalTransform.on_start()`, after constructing the provider:

```python
def on_start(self, ctx: LifecycleContext) -> None:
    super().on_start(ctx)
    # ... existing provider construction ...

    result = self._provider.check_readiness()
    if not result.ready:
        raise RetrievalNotReadyError(
            f"RAG transform '{self.name}' requires a populated collection. "
            f"{result.message}"
        )
```

`RetrievalNotReadyError` inherits from the base ELSPETH error hierarchy. It is:
- Not retryable — this is a configuration/sequencing error, not a transient failure.
- Not a row-level error — it prevents the pipeline from starting.
- Includes the collection name and document count in the error message.

### Defence in Depth

Commencement gates and the readiness contract serve different purposes:

| Layer | Catches | Fires when | Configured by |
|-------|---------|-----------|--------------|
| Commencement gate | "Collection has data" | Before `on_start()`, pre-flight | Pipeline operator |
| Readiness contract | "My provider can reach the collection and it has data" | During `on_start()` | Always (built into transform) |

A commencement gate catches the problem earlier and with a better error message (includes the expression and context snapshot). The readiness contract catches it even when no commencement gate is configured.

An operator using `depends_on` + commencement gates gets the full experience. An operator who pre-populates the collection externally and skips `depends_on` still gets the readiness check.

## End-to-End Example

### File Layout

```
examples/chroma_rag_indexed/
  index_pipeline.yaml
  query_pipeline.yaml
  documents.csv
  questions.csv
  chroma_data/
  runs/
    audit.db
  output/
    results.jsonl
    quarantined.jsonl
```

### Indexing Pipeline (`index_pipeline.yaml`)

```yaml
# No transforms — documents are written directly from source to ChromaSink.
# A chunking transform would be added here for long-document corpora.
source:
  plugin: csv_source
  on_success: output
  options:
    file_path: ./documents.csv
    schema:
      mode: fixed
      fields:
        - "doc_id: str"
        - "text_content: str"
        - "topic: str"
        - "subtopic: str"

sinks:
  output:
    plugin: chroma_sink
    options:
      collection: science-facts
      mode: persistent
      persist_directory: ./chroma_data
      distance_function: cosine
      field_mapping:
        document: text_content
        id: doc_id
        metadata:
          - topic
          - subtopic
      on_duplicate: overwrite
      schema:
        mode: fixed
        fields:
          - "doc_id: str"
          - "text_content: str"
          - "topic: str"
          - "subtopic: str"

landscape:
  url: sqlite:///./runs/audit.db
```

### Query Pipeline (`query_pipeline.yaml`)

```yaml
depends_on:
  - name: index_corpus
    settings: ./index_pipeline.yaml

commencement_gates:
  - name: corpus_ready
    condition: "collections['science-facts']['count'] > 0"
    on_fail: abort

source:
  plugin: csv_source
  on_success: retrieve
  options:
    file_path: ./questions.csv
    schema:
      mode: fixed
      fields:
        - "question: str"

transforms:
  - name: retrieve
    plugin: rag_retrieval
    input: source_output
    on_success: output
    on_error: quarantine
    options:
      query_field: question
      output_prefix: sci
      provider: chroma
      provider_config:
        collection: science-facts
        mode: persistent
        persist_directory: ./chroma_data
        distance_function: cosine
      top_k: 3
      min_score: 0.0
      on_no_results: quarantine
      context_format: numbered
      schema:
        mode: flexible

sinks:
  output:
    plugin: json_sink
    options:
      file_path: ./output/results.jsonl
      format: jsonl
      schema:
        mode: flexible

  quarantine:
    plugin: json_sink
    options:
      file_path: ./output/quarantined.jsonl
      format: jsonl
      schema:
        mode: flexible

landscape:
  url: sqlite:///./runs/audit.db
```

### Execution Flow

```
$ elspeth run --settings query_pipeline.yaml --execute

1. Dependency resolution
   → Load index_pipeline.yaml
   → Create child Orchestrator, run indexing pipeline
   → CSV source emits document rows
   → ChromaSink upserts documents into 'science-facts'
   → Indexing run abc-123 completes successfully

2. Pre-flight context assembly
   → Probe collection 'science-facts': 10 documents found
   → Build context: {dependency_runs: {...}, collections: {...}, env: {...}}

3. Commencement gate evaluation
   → 'corpus_ready': collections['science-facts']['count'] > 0 → True ✓

4. Main pipeline starts (run def-456)
   → Run metadata: {dependency_runs: [...], commencement_gates: [...]}

5. RAG transform on_start()
   → Provider constructed
   → Readiness check: 'science-facts' has 10 documents ✓

6. Row processing
   → Questions retrieved, augmented with context, written to output

7. Run def-456 completes
```

### Audit Trail

For any output row, an auditor can trace:

1. **Row lineage**: `explain(recorder, "def-456", token_id)` — full DAG path
2. **Retrieved context**: RAG transform call records — which chunks, what scores
3. **Corpus state**: Commencement gate snapshot — `count=10` at pipeline start
4. **Corpus provenance**: `dependency_runs` links to indexing run `abc-123`
5. **Indexed documents**: Every document in `abc-123` has call records with canonical content hashes
6. **Go/no-go decision**: Gate expression, evaluation result, and context snapshot

## Testing Strategy

### Unit Tests

**ChromaSink:**
- Config validation (field mapping required, mode/connection validation, on_duplicate values).
- `write()` with mocked ChromaDB client — verify correct API calls, content hashing, artifact descriptor.
- `on_duplicate` modes — overwrite calls `upsert()`, skip calls `add()`, error checks existence first.
- Audit recording — verify `record_call()` invoked with correct parameters.
- Error paths — unreachable server in `on_start()`, write failure, audit recording failure.

**Dependency resolution:**
- Single dependency, success path.
- Single dependency, failure path — verify `DependencyFailedError`.
- Multiple dependencies, sequential execution order.
- Circular dependency detection.
- Relative path resolution from parent config directory.

**Commencement gates:**
- Gate passes — verify result recorded.
- Gate fails — verify `CommencementGateFailedError` with context snapshot.
- Expression error — verify error includes exception details.
- Restricted namespace — verify no builtins, no imports.
- Context assembly — verify collection probes, dependency results, env snapshot.

**Readiness contract:**
- Collection exists with documents — ready.
- Collection exists but empty — not ready, clear message.
- Collection doesn't exist — not ready, clear message.
- Provider unreachable — error propagation.

### Integration Tests

**ChromaSink lifecycle:**
- Full pipeline: CSV source → ChromaSink with real ephemeral ChromaDB.
- Verify documents written to collection with correct IDs, content, metadata.
- Verify audit trail records all calls.

**depends_on + commencement gates + readiness:**
- Full end-to-end: query pipeline with `depends_on` indexing pipeline.
- Verify indexing runs first, query pipeline uses populated collection.
- Verify Landscape correlation (dependency_runs metadata on query run).
- Verify commencement gate results recorded.

**Failure paths:**
- Dependency fails → main pipeline never starts.
- Commencement gate fails → main pipeline never starts, clear error.
- Empty collection with no depends_on, no commencement gate → readiness contract catches it.

## Future Extensions

These are explicitly out of scope for this design but inform the shape of what we're building:

- **Chunking transform**: A transform that splits long documents into overlapping segments. Would sit between the source and ChromaSink in the indexing pipeline.
- **Additional commencement gate conditions**: `warn` (log but proceed), service health probes, Landscape queries ("last successful indexing run was < 24h ago").
- **`if_stale` dependency condition**: Run the dependency only if the collection hasn't been updated since a threshold. Requires tracking last-modified metadata.
- **Multi-source DAGs (Approach C)**: Eventually, the dependency pipeline could be compiled into the main pipeline's DAG as prefix stages. This requires breaking the one-source-per-run invariant.
- **Azure Search sink**: Same pattern as ChromaSink but targeting Azure AI Search indexes.
