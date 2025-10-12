# Embeddings & RAG Plugin Design

## Purpose

- <!-- UPDATE 2025-10-12: Capture design for the new embeddings/RAG plugin family. -->
- Provide an extensible sink and row plugin pair that can persist experiment outputs as vector embeddings and offer retrieval-augmented context during subsequent runs.
- Support both an open-source (“official”) deployment profile and an Azure-managed (“protected”) variant without duplicating orchestration logic.

## Components

### EmbeddingsStoreSink (ResultSink)

- Wraps the vector database integration and produces `data/vector-index` artifacts for downstream consumers.
- Accepts batches of experiment records, generates (or receives) embeddings, and upserts them into the configured backend.
- Implements `produces()` returning a descriptor such as:
  - `name: embeddings_index`
  - `type: data/vector-index`
  - `alias: embeddings:{namespace}`
  - `persist: True`
  - `security_level: inherited from PluginContext`
- Supports optional `collect_artifacts()` to expose manifest payloads (upsert counts, checkpoint cursor).

### RAGQueryPlugin (RowExperimentPlugin)

- Executes vector similarity queries using the sink-provided configuration.
- Injects retrieved passages into the row record (`record["retrieved_context"]`, `record["retrieval_metadata"]`).
- Can operate in “prefetch-only” mode (no prompt mutation) or “context-injection” mode (append retrieved context to prompt defaults).
- Emits metrics for downstream analytics (`metrics["retrieval"] = {"hits": top_k, "min_score": ...}`).

<!-- UPDATE 2025-10-12: Promote retrieval utility for operational flows -->
### RetrievalContextUtility (Utility Plugin)

- Lives in `src/elspeth/plugins/utilities/retrieval.py` and registers via the new `elspeth.core.utilities` registry (`plugin_kind="utility"`).
- Exposes `build_payload()` rather than `process_row`, enabling day-to-day services to fetch retrieval context without depending on experiment runner hooks.
- Retains the namespace derivation (`suite.experiment.level`) using `PluginContext`, but allows explicit overrides (`namespace`, `metadata.security_level`) for operational playbooks.
- Accepts the same provider/embed configuration as the former row plugin and preserves `inject_mode` semantics (`prompt_append`, `metadata_only`, `none`).
- Default tests moved to `tests/test_retrieval_utility.py`; the legacy `RAGQueryPlugin` remains as a shim that emits a `DeprecationWarning` yet delegates to the utility.
<!-- END UPDATE -->

## Configuration Reference

### Common Options

| Field | Type | Description |
| --- | --- | --- |
| `provider` | string | Backend identifier (`pgvector`, `qdrant`, `azure_search`, `azure_cosmos`). |
| `namespace` | string | Logical collection/index name; defaults to `suite_name.experiment_name.security_level` to prevent cross-tier bleed. |
| `embedding_source` | string | Path to reuse existing embedding metrics (`response.metrics.embedding`); preferred to keep runs deterministic. |
| `embed_model` | mapping | Optional config to call a dedicated embedding model (`provider`, `model`, `api_key_env`). Disabled unless explicitly configured. |
| `batch_size` | int | Number of rows per upsert transaction (default 50). |
| `upsert_conflict` | string | `replace`, `skip`, or `merge`. |
| `metadata_fields` | list | Dot-paths to include alongside the vector (e.g., `row.APPID`, `metadata.cost_summary.total_cost`). |
| `retry` | mapping | Reuses standard retry schema (`max_attempts`, `initial_delay`, `backoff_multiplier`). |

### Official (Open Source) Profile

```yaml
sinks:
  - plugin: embeddings_store
    security_level: official
    options:
      provider: pgvector
      dsn: ${EMBEDDINGS_DSN}
      table: rag_items
      text_field: response.content
      namespace: ${SUITE_NAME}.${EXPERIMENT_NAME}.official  # default derived namespace
      batch_size: 100
      upsert_conflict: replace
      metadata_fields:
        - row.APPID
        - metadata.retry_summary.total_retries
      artifacts:
        produces:
          - name: embeddings_index
            type: data/vector-index
            alias: embeddings:official
            persist: true
```

### Protected (Azure) Profile

```yaml
sinks:
  - plugin: embeddings_store
    security_level: protected
    options:
      provider: azure_search
      endpoint: https://my-search.search.windows.net
      index: elspeth-experiments
      api_key_env: AZURE_SEARCH_KEY
      region: westeurope
      text_field: response.content
      embed_model:
        provider: azure_openai
        deployment: text-embedding-3-large
        api_version: 2024-05-13
      artifacts:
        produces:
          - name: embeddings_index
            type: data/vector-index
            alias: embeddings:protected
            persist: true
```

### RAG Query Plugin Example

```yaml
row_plugins:
  - name: rag_query
    security_level: protected
    options:
      provider: azure_search
      endpoint: https://my-search.search.windows.net
      index: elspeth-experiments
      api_key_env: AZURE_SEARCH_KEY
      top_k: 5
      min_score: 0.25
      inject_mode: prompt_append   # or metadata_only
      template: |
        Retrieved evidence:
        {{ context }}
```

<!-- UPDATE 2025-10-12: Utility registry configuration example -->
```yaml
utilities:
  - name: retrieval_context
    security_level: official
    options:
      provider: pgvector
      dsn: ${EMBEDDINGS_DSN}
      query_field: metadata.issue_summary
      inject_mode: metadata_only
      top_k: 5
      min_score: 0.2
```
<!-- END UPDATE -->

## Interfaces & Integration Points

- **ResultSink Implementation**
  - Implements `write()` to transform payloads into embedding batches.
  - Uses `prepare_artifacts()` to read upstream artifacts (e.g., signed bundle manifests) if enrichment is required.
  - Exposes `collect_artifacts()` returning manifest artifact with counts, last upserted ID, and security level.
- **Row Plugin**
  - Validates that embeddings sink configuration is available (either via shared settings or plugin options).
  - Provides hook to short-circuit when vector store unreachable (respecting `on_error: skip|abort`).
- **Suite Runner**
  - Embeddings sink may appear in suite defaults; context will propagate experiment name into namespace by default.
  - RAG plugin can be injected via prompt packs to ensure baseline and variants share retrieval config.
  - Suite reports surface embedding coverage only when `include_embedding_stats` opt-in flag is enabled (default `false`).

## Data Flow

1. Runner processes rows and aggregates metrics.
2. EmbeddingsStoreSink receives payload, determines embedding vector:
   - Use `embedding_source` if present.
   - Else invoke configured `embed_model` with rate limiter + retry.
3. Sink batches vectors, wraps each in `{id, vector, text, metadata, security_level}` and calls provider client.
4. Upsert response recorded in manifest and exposed via artifact store.
5. Future experiments include `rag_query` plugin:
   - Compose similarity query from prompt context (`row` fields).
   - Issue top-k search, filter by `min_score`.
   - Inject context into prompt or metrics for downstream sinks/LLM middleware.

## Security & Compliance

- Secrets supplied through environment variables (`EMBEDDINGS_DSN`, `AZURE_SEARCH_KEY`, etc.).
- Normalize all metadata before persistence to prevent leaking high classification values into lower-tier namespace; ship with a conservative allowlist (`row.APPID`, `row.record_id`, retry/cost summaries) and require explicit configuration for additional fields.
- For protected tier:
  - Enforce TLS/HTTPS endpoints.
  - Ensure Azure Search requests annotate `security_level` for audit logging (forward to middleware telemetry).
  - Apply default request throttling (`throttle_max_rps`) aligned with Azure Search guidance and document required key rotation cadence.
- Implement optional encryption for local pgvector via TLS (document connection string requirements).
- Provide lifecycle controls (`ttl_days`, `invalidation_strategy`) with default “retain until pruned” behaviour so retention decisions remain explicit.

## Telemetry & Observability

- Emit structured logs:
  - `embeddings.upsert` with counts, duration, retry attempts.
  - `embeddings.query` with top_k, min_score, and hit statistics (no raw content in logs unless security_level permits).
- Expose metrics hook compatible with existing analytics sink (`metrics["embeddings"] = {...}`).
- Retry exhaustion should trigger the standard runner `_notify_retry_exhausted`.

## Testing Strategy

### Unit Tests

- Validate configuration normalization (required fields per provider, security level enforcement).
- Confirm namespace resolver derives `suite.experiment.security_level` when not overridden.
- Mock provider clients to assert batching, conflict modes, and manifest contents.
- Ensure ingestion handles missing embeddings gracefully when `embed_model` configured.
- RAG plugin tests verifying prompt injection modes, score filtering, and metrics emission.
<!-- UPDATE 2025-10-12: Utility testing coverage -->
- Utility-layer tests (`tests/test_retrieval_utility.py`) now exercise `build_payload()` behaviour, namespace derivation, and the deprecation shim that forwards to the utility.
<!-- END UPDATE -->

### Integration Tests

- Use dockerized pgvector/Qdrant in CI (guarded behind `@pytest.mark.integration`).
- For Azure Search, supply mock HTTP server or use recorded responses (VCR) to validate request payloads.

### Contract Tests

- Provide stub provider classes to guarantee minimal interface (`upsert_many`, `query`) stays consistent.
- Include schema validation for returned artifacts using `ArtifactDescriptor` expectations.

## Open Questions

- When TTL pruning is enabled, should the sink run deletions per upsert batch or defer to a scheduled maintenance job?
- For detailed retrieval traces, do we persist full hit lists exclusively in sink manifests or also emit them to a governed telemetry stream?

## Update History

- 2025-10-12 – Added initial design covering interfaces, configuration profiles, security posture, and testing plan for the embeddings/RAG plugin family.
- 2025-10-12 – Finalised defaults for backend (pgvector), namespace derivation, metadata allowlist, lifecycle controls, Suite report opt-ins, and Azure-specific throttling/key-rotation requirements.
- 2025-10-12 – Implemented embeddings_store sink and rag_query plugin with pgvector/Azure Search backends, OpenAI/Azure OpenAI embedding providers, and unit coverage.
- 2025-10-12 – Transitioned rag_query into the `retrieval_context` utility plugin, documented the new registry, and captured configuration/testing updates.
