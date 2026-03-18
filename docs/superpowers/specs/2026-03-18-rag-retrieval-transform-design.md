# RAG Retrieval Transform Plugin — Design Spec

**Date:** 2026-03-18
**Status:** Draft
**Scope:** New `rag_retrieval` transform plugin, `RetrievalProvider` protocol, Azure AI Search provider implementation

## Overview

Add a Retrieval-Augmented Generation (RAG) retrieval transform to ELSPETH. This plugin retrieves relevant context from a vector/search backend and attaches it to the pipeline row as prefixed fields. A downstream LLM transform then references the retrieved context in its prompt template.

This is a **retrieval-only** transform — it does not perform generation. The separation follows ELSPETH's composability model: retrieval and generation are distinct operations with different error modes, retry semantics, and audit requirements. They compose naturally as separate DAG steps.

## Motivation

LLM transforms in ELSPETH currently operate on row data alone. For many use cases — classification, summarization, Q&A — the LLM needs domain-specific context that isn't in the row. RAG provides this by retrieving relevant documents/chunks at query time and injecting them into the prompt.

Building RAG as a separate retrieval transform (rather than bolting it onto the LLM transform) provides:
- **Independent auditability** — "what context was retrieved" and "what the LLM did with it" are separate Landscape entries
- **Composability** — gates between retrieval and generation (e.g., filter low-relevance results), multiple retrieval steps with different knowledge bases, retrieval without generation (similarity search pipelines)
- **Reuse** — the retrieval transform is useful beyond LLM augmentation (deduplication, nearest-neighbor lookup, document matching)

## Architecture

### File Layout

```
src/elspeth/plugins/
├── infrastructure/
│   └── clients/
│       └── retrieval/
│           ├── __init__.py        # Public exports
│           ├── base.py            # RetrievalProvider protocol
│           ├── azure_search.py    # Azure AI Search implementation
│           └── types.py           # RetrievalChunk, RetrievalResult dataclasses
└── transforms/
    └── rag/
        ├── __init__.py            # Plugin registration
        ├── transform.py           # RAGRetrievalTransform
        ├── config.py              # RAGRetrievalConfig (Pydantic)
        ├── query.py               # Query construction strategies
        └── formatter.py           # Context output formatting
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| `RetrievalProvider` | Protocol for search backends — search interface + lifecycle |
| `AzureSearchProvider` | Azure AI Search implementation of `RetrievalProvider` |
| `RAGRetrievalTransform` | Pipeline integration — query construction, retrieval orchestration, output attachment |
| `query.py` | Query construction from row data (field, template, regex modes) |
| `formatter.py` | Context formatting (numbered, separated, raw) with length capping |

### Layer Placement

- `RetrievalProvider` protocol and types: `plugins/infrastructure/clients/retrieval/` (L3)
- `AzureSearchProvider`: `plugins/infrastructure/clients/retrieval/` (L3)
- `RAGRetrievalTransform`: `plugins/transforms/rag/` (L3)

No cross-layer violations. The retrieval provider lives alongside `AuditedHTTPClient` and `AuditedLLMClient` in the client infrastructure.

### Relationship to Existing LLM Transform

The RAG retrieval transform and LLM transform are **independent plugins** with no code-level coupling. They compose via the pipeline DAG:

```
Source → RAGRetrievalTransform → LLMTransform → Sink
                |                       |
         attaches context        references context
         as row fields           via {{ row.prefix__rag_context }}
```

The LLM transform doesn't know or care where `prefix__rag_context` came from — it's just a row field available in the template. This is the same composition model as any other transform chain.

## RetrievalProvider Protocol

```python
@runtime_checkable
class RetrievalProvider(Protocol):
    """Search backend interface for RAG retrieval."""

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
    ) -> list[RetrievalChunk]:
        """Execute a search query and return ranked results.

        Args:
            query: The search query text.
            top_k: Maximum number of results to return.
            min_score: Minimum relevance score threshold (0.0-1.0).
                Results below this score are discarded.

        Returns:
            List of RetrievalChunk, ordered by descending relevance score.
            May be empty if no results meet the min_score threshold.
        """
        ...

    def close(self) -> None:
        """Release provider resources (connections, clients)."""
        ...
```

### RetrievalChunk

```python
@dataclass(frozen=True)
class RetrievalChunk:
    """A single retrieved document chunk."""

    content: str           # The retrieved text content
    score: float           # Relevance score, normalized to 0.0-1.0
    source_id: str         # Document/chunk identifier (for audit traceability)
    metadata: dict[str, Any]  # Provider-specific metadata (page, section, index name, etc.)
```

### Design Rationale

The protocol is deliberately minimal:
- **`search()` takes primitives** — no provider-specific query objects leak into the transform
- **Scores are normalized to 0.0-1.0** — each provider handles its own score normalization internally (Azure AI Search returns different scales for different search modes)
- **`metadata` is opaque** — provider-specific details (page numbers, section headers, chunk IDs) travel through without the protocol needing to enumerate them
- **No embedding method on the protocol** — the provider handles embedding internally. Some backends (Azure AI Search with integrated vectorization) handle embedding server-side; others need client-side embedding. This is a provider concern, not a protocol concern.

## Azure AI Search Provider

### Day-One Implementation

```python
class AzureSearchProvider:
    """Azure AI Search implementation of RetrievalProvider."""

    def __init__(
        self,
        config: AzureSearchProviderConfig,
        http_client: AuditedHTTPClient,
    ) -> None:
        ...
```

The `http_client` is passed in by the transform's `on_start()` hook (constructed with recorder/run_id/state_id from the lifecycle context). The provider does NOT construct its own HTTP client.

### Features

- **Search modes:** `vector`, `keyword`, `hybrid` (vector + keyword), `semantic` (semantic ranking)
- **Integrated vectorization:** When `search_mode` is `vector` or `hybrid`, the provider uses Azure AI Search's built-in vectorizer (configured on the search index). No client-side embedding needed.
- **Score normalization:** Azure returns different score ranges per search mode. The provider normalizes all scores to 0.0-1.0.
- **Auth:** API key or managed identity (via `azure-identity`)
- **Audit trail:** All search API calls go through `AuditedHTTPClient` — automatically recorded in Landscape

### Configuration

```python
class AzureSearchProviderConfig(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    endpoint: str              # https://<service>.search.windows.net
    index: str                 # Search index name
    api_key: str | None = None # API key (alternative to managed identity)
    use_managed_identity: bool = False
    api_version: str = "2024-07-01"

    search_mode: Literal["vector", "keyword", "hybrid", "semantic"] = "hybrid"

    # Vector search options (when search_mode is vector or hybrid)
    vector_field: str = "contentVector"   # Name of the vector field in the index
    semantic_config: str | None = None    # Semantic configuration name (for semantic mode)

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        if not self.api_key and not self.use_managed_identity:
            raise ValueError("Specify either api_key or use_managed_identity=true")
        if self.api_key and self.use_managed_identity:
            raise ValueError("Specify only one of api_key or use_managed_identity")
        return self

    @model_validator(mode="after")
    def validate_semantic_config(self) -> Self:
        if self.search_mode == "semantic" and not self.semantic_config:
            raise ValueError("semantic search_mode requires semantic_config")
        return self
```

### Tier 3 Boundary

Azure AI Search responses are Tier 3 (external data). Validation at the boundary:

1. **JSON parse** — reject malformed responses
2. **Response structure** — `value` array present, each item has `@search.score` and expected content fields
3. **Score normalization** — map provider-specific scores to 0.0-1.0 range
4. **Content extraction** — extract text content from configured field, reject items with missing content

Once validated, `RetrievalChunk` objects are Tier 2 — trusted by the transform.

## RAGRetrievalTransform

### Extends BaseTransform (Synchronous)

```python
class RAGRetrievalTransform(BaseTransform):
    name = "rag_retrieval"
    determinism = Determinism.EXTERNAL_CALL
```

This transform uses the synchronous `process()` model, NOT `BatchTransformMixin`. `BatchTransformMixin` provides *within-row* concurrency (multiple sub-tasks per row, e.g., multi-query LLM calls), not across-row concurrency. A single retrieval query per row gains nothing from the mixin — it would add OutputPort wiring, reorder buffer, and worker pool overhead for zero benefit.

If a future use case requires multiple concurrent retrievals per row (e.g., querying multiple indexes simultaneously for a single row), the transform can be upgraded to `BatchTransformMixin` at that point. For the day-one single-query-per-row design, synchronous `process()` is correct and simpler.

### Configuration

```python
# Provider registry — maps provider names to config classes for eager validation
_PROVIDER_CONFIGS: dict[str, type[BaseModel]] = {
    "azure_search": AzureSearchProviderConfig,
}

class RAGRetrievalConfig(TransformDataConfig):
    # Output field prefix (mandatory)
    output_prefix: str                # e.g., "financial" → "financial__rag_context"

    # Query construction (query_field is always required)
    query_field: str                  # Row field to use as search query source
    query_template: str | None = None # Jinja2 template ({{ query }} = extracted field value)
    query_pattern: str | None = None  # Regex to extract search text from field value

    # Provider selection and config
    provider: str                     # Provider name (e.g., "azure_search")
    provider_config: dict[str, Any]   # Validated eagerly against provider's config class

    # Retrieval parameters
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Zero results behavior
    on_no_results: Literal["quarantine", "continue"] = "quarantine"

    # Context formatting
    context_format: Literal["numbered", "separated", "raw"] = "numbered"
    context_separator: str = "\n---\n"  # Used when context_format="separated"
    max_context_length: int | None = None  # Character cap (None = no limit)

    @field_validator("output_prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        if not v.isidentifier():
            raise ValueError(f"output_prefix must be a valid Python identifier, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_query_modes(self) -> Self:
        if self.query_template and self.query_pattern:
            raise ValueError("query_template and query_pattern are mutually exclusive")
        return self

    @model_validator(mode="after")
    def validate_provider_config(self) -> Self:
        config_cls = _PROVIDER_CONFIGS.get(self.provider)
        if config_cls is None:
            raise ValueError(f"Unknown provider: {self.provider!r}. Available: {sorted(_PROVIDER_CONFIGS)}")
        config_cls(**self.provider_config)  # Eagerly validate provider config at YAML load time
        return self

    @field_validator("query_pattern")
    @classmethod
    def validate_regex(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}") from e
        return v
```

Note: `TransformDataConfig` extends `DataPluginConfig`, which requires `schema_config`. Rate limiting uses the settings-level `RateLimitRegistry`, not a per-plugin config field. The provider registry eagerly validates `provider_config` against the correct Pydantic model at YAML load time (fail-fast, not deferred to first row).

### Query Construction

Three modes, all anchored on `query_field`:

**1. Field only** (`query_field` set, no template/regex):
```python
query = row[query_field]  # Use field value verbatim
```

**2. Field + template** (`query_field` + `query_template`):
```python
extracted = row[query_field]
query = compiled_template.render(query=extracted)
# Template has access to {{ query }} (the extracted value) and {{ row }} (full row)
```

Template is pre-compiled at `__init__` time (structural errors fail the run at setup). Render errors at row time produce `TransformResult.error()` (quarantine the row).

**3. Field + regex** (`query_field` + `query_pattern`):
```python
extracted = row[query_field]
match = compiled_pattern.search(str(extracted))
if match is None:
    return TransformResult.error({"reason": "no_regex_match", ...}, retryable=False)
query = match.group(1) if match.lastindex else match.group(0)
```

Regex is pre-compiled at `__init__` time. No match → row-level error (quarantine). If the regex has capture groups, the first group is used; otherwise the full match.

### Plugin Lifecycle

```
__init__(config)
  → Validate config (Pydantic, including eager provider_config validation)
  → Pre-compile query_template (if provided) — TemplateSyntaxError fails the run at setup
  → Pre-compile query_pattern (if provided) — already validated by Pydantic
  → Compute declared_output_fields from output_prefix
  → NOTE: Provider is NOT constructed here (needs recorder/run_id from context)

on_start(ctx)
  → Construct AuditedHTTPClient with recorder, run_id, state_id, telemetry_emit from ctx
  → Construct RetrievalProvider with validated provider_config and HTTP client
  → Provider performs any connection validation (e.g., index exists check)

process(row, ctx)
  → See Process Flow below

on_complete(ctx)
  → (Optional) Log retrieval statistics

close()
  → Call provider.close() to release HTTP connections
```

### Process Flow (per row)

```
1. Extract query field value from row
2. Construct search query (field / template / regex)
   → On regex no-match: TransformResult.error(retryable=False) (quarantine)
   → On template render error: TransformResult.error(retryable=False) (quarantine)
3. Call provider.search(query, top_k, min_score)  [Tier 3 boundary]
   → On provider error (retryable): TransformResult.error(retryable=True)
   → On provider error (non-retryable): TransformResult.error(retryable=False)
4. Check result count
   → Zero results + on_no_results="quarantine": TransformResult.error(retryable=False)
   → Zero results + on_no_results="continue": empty context, continue
5. Format context (numbered / separated / raw)
6. Apply max_context_length truncation (if configured)
7. Attach prefixed output fields to row
8. Return TransformResult.success()
```

**Error handling note:** Retryable errors use `TransformResult.error(retryable=True)`, NOT raised exceptions. Raising an exception from `process()` would be treated as a plugin bug (system code crash). The engine's retry logic reads the `retryable` flag on the error result. This matches the pattern used by the LLM transform.

### Output Fields

All output fields are prefixed with the mandatory `output_prefix`:

| Field | Type | Content |
|-------|------|---------|
| `{prefix}__rag_context` | `str` | Formatted retrieved text (the field the LLM template references) |
| `{prefix}__rag_score` | `float` | Top result's relevance score |
| `{prefix}__rag_count` | `int` | Number of chunks retrieved above threshold |
| `{prefix}__rag_sources` | `str` | JSON-serialized list of `{"source_id": ..., "score": ..., "metadata": ...}` |

The transform declares these as `declared_output_fields` for the engine's field collision detection.

### Context Formatting

Three modes for joining multiple retrieved chunks into `{prefix}__rag_context`:

**Numbered** (default):
```
1. First retrieved chunk text here...
2. Second retrieved chunk text here...
3. Third retrieved chunk text here...
```

**Separated** (with configurable separator):
```
First retrieved chunk text here...
---
Second retrieved chunk text here...
---
Third retrieved chunk text here...
```

**Raw** (simple concatenation):
```
First retrieved chunk text here...Second retrieved chunk text here...Third retrieved chunk text here...
```

### Max Context Length

When `max_context_length` is set, the formatted context is truncated to that character limit. Truncation happens at chunk boundaries where possible — whole chunks are included or excluded, not mid-sentence cuts. If even the first chunk exceeds the limit, it is hard-truncated with a `[truncated]` indicator.

### Success Reason Metadata

```python
TransformResult.success(
    output_row,
    success_reason={
        "action": "rag_retrieved",
        "provider": "azure_search",
        "query_length": len(query),
        "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16],
        "chunks_retrieved": len(chunks),
        "top_score": chunks[0].score if chunks else None,
        "mean_score": mean([c.score for c in chunks]) if chunks else None,
        "context_length": len(formatted_context),
        "truncated": was_truncated,
    },
)
```

This metadata is recorded in `node_states.success_reason_json` in the Landscape — fully auditable.

### Error Reason Metadata

Each error path produces a distinct reason dict for audit traceability:

```python
# Regex no-match
TransformResult.error(
    {"reason": "no_regex_match", "field": query_field, "pattern": query_pattern},
    retryable=False,
)

# Template render error
TransformResult.error(
    {"reason": "query_template_render_failed", "error": str(e), "field": query_field},
    retryable=False,
)

# Provider error (retryable — transient network/server failure)
TransformResult.error(
    {"reason": "retrieval_failed", "provider": provider_name, "error": str(e), "query_length": len(query)},
    retryable=True,
)

# Provider error (non-retryable — auth, bad request, etc.)
TransformResult.error(
    {"reason": "retrieval_failed", "provider": provider_name, "error": str(e), "query_length": len(query)},
    retryable=False,
)

# Zero results
TransformResult.error(
    {"reason": "no_results", "provider": provider_name, "query_length": len(query), "min_score": min_score},
    retryable=False,
)
```

### Note on `{prefix}__rag_sources` Field Type

The `__rag_sources` field is stored as a JSON-serialized string because `PipelineRow` field values are primitives (str, int, float, bool, None). Storing a `list[dict]` directly would violate the row contract. This is a deliberate constraint — the field's primary consumer is the Landscape audit trail (where it's recorded as-is in `success_reason_json`), not downstream transforms. If a downstream transform needs to parse source metadata, it operates at a Tier 2 boundary on data we serialized — parse errors would indicate a bug in the RAG transform, not bad external data.

## Pipeline Composition Examples

### Single retrieval + LLM

```yaml
transforms:
  - plugin: rag_retrieval
    options:
      output_prefix: "policy"
      query_field: "customer_question"
      provider: azure_search
      provider_config:
        endpoint: "https://my-search.search.windows.net"
        index: "policy-documents"
        api_key: "${AZURE_SEARCH_API_KEY}"
        search_mode: hybrid
      top_k: 5
      min_score: 0.7
      on_no_results: quarantine
      context_format: numbered
      max_context_length: 4000
      schema:
        fields: dynamic

  - plugin: llm
    options:
      template: |
        Answer the customer's question using the provided policy context.

        Question: {{ row.customer_question }}

        Relevant policies:
        {{ row.policy__rag_context }}

        Answer:
```

### Multi-source retrieval + LLM

```yaml
transforms:
  - plugin: rag_retrieval
    options:
      output_prefix: "financial"
      query_field: "complaint_text"
      provider: azure_search
      provider_config:
        endpoint: "https://my-search.search.windows.net"
        index: "financial-policies"
        api_key: "${AZURE_SEARCH_API_KEY}"
      top_k: 5
      min_score: 0.7
      schema:
        fields: dynamic

  - plugin: rag_retrieval
    options:
      output_prefix: "regulatory"
      query_field: "product_category"
      query_template: "Regulations for product type: {{ query }}"
      provider: azure_search
      provider_config:
        endpoint: "https://my-search.search.windows.net"
        index: "regulatory-docs"
        api_key: "${AZURE_SEARCH_API_KEY}"
      top_k: 3
      min_score: 0.8
      schema:
        fields: dynamic

  - plugin: llm
    options:
      template: |
        Classify the customer complaint considering both financial policies
        and regulatory requirements.

        Complaint: {{ row.complaint_text }}

        Financial policies:
        {{ row.financial__rag_context }}

        Regulatory context:
        {{ row.regulatory__rag_context }}

        Classification:
```

### Retrieval with regex extraction

```yaml
transforms:
  - plugin: rag_retrieval
    options:
      output_prefix: "context"
      query_field: "raw_email_body"
      query_pattern: "(?:issue|problem|complaint):\\s*(.+?)(?:\\n|$)"
      provider: azure_search
      provider_config:
        endpoint: "https://my-search.search.windows.net"
        index: "knowledge-base"
        api_key: "${AZURE_SEARCH_API_KEY}"
      top_k: 3
      on_no_results: continue  # LLM can try without context
      schema:
        fields: dynamic
```

## Dependencies

| Dependency | Extra | Purpose |
|-----------|-------|---------|
| `httpx` | base | HTTP client (via `AuditedHTTPClient`) |
| `azure-identity` | `[azure]` | Managed identity auth for Azure AI Search |

No new dependencies required for the day-one implementation. Azure AI Search is a REST API — no dedicated SDK needed.

When non-Azure providers are added later, their dependencies would go into a new `[rag]` extra (e.g., `chromadb`, `pinecone-client`). The `[azure]` extra remains sufficient for the Azure AI Search provider.

## Plugin Discovery

The transform lives in `plugins/transforms/rag/`. The plugin scanner's `PLUGIN_SCAN_CONFIG` must be updated to include `transforms/rag` as a scanned subdirectory (similar to `transforms/llm` and `transforms/azure`).

The retrieval client infrastructure (`plugins/infrastructure/clients/retrieval/`) does not need scanner registration — it's imported directly by the transform, not discovered.

## Testing Strategy

### Unit Tests

**Query construction (`query.py`):**
- Field-only mode: extracts value verbatim
- Template mode: renders query with `{{ query }}` and `{{ row }}` context
- Template mode: structural error at compile time (not row time)
- Template mode: render error produces `TransformResult.error()`
- Regex mode: captures first group
- Regex mode: uses full match when no capture groups
- Regex mode: no match produces `TransformResult.error()`
- Regex mode: invalid pattern rejected at config validation

**Context formatting (`formatter.py`):**
- Numbered format with multiple chunks
- Separated format with custom separator
- Raw format (concatenation)
- Max length truncation at chunk boundaries
- Max length truncation mid-chunk (with `[truncated]` indicator)
- Empty chunk list handling

**Config validation (`config.py`):**
- `output_prefix` must be valid Python identifier
- `query_template` and `query_pattern` mutually exclusive
- `query_pattern` regex compilation validation
- `top_k` bounds (1-100)
- `min_score` bounds (0.0-1.0)
- Provider config passthrough

**Provider protocol:**
- Azure search config validation (auth mutual exclusion, semantic config requirement)
- Score normalization per search mode
- Tier 3 boundary: malformed JSON response
- Tier 3 boundary: missing `value` array
- Tier 3 boundary: missing content field in result items

### Integration Tests

- Full transform process: query → retrieve → format → output (mock HTTP transport)
- Zero results with `on_no_results: quarantine` → `TransformResult.error()`
- Zero results with `on_no_results: continue` → empty context, success
- Multiple chunks → correct output field population
- Output field prefix applied correctly
- Declared output fields match actual output (collision detection compatibility)
- Pipeline composition: RAG transform → LLM transform (mock both external calls)
- Plugin discovery: `discover_all_plugins()` finds `rag_retrieval` after `PLUGIN_SCAN_CONFIG` update

### Tier Model Compliance

Tests use production code paths. The `AzureSearchProvider` is tested via mock HTTP transport on `AuditedHTTPClient`, not by mocking the provider itself. Integration tests use `instantiate_plugins_from_config()` for plugin construction.

## Security Considerations

- **API key handling:** Azure AI Search API keys are resolved via ELSPETH's secret management. HMAC fingerprints in audit trail, never raw keys.
- **Query injection:** OData/search query construction does not use string interpolation of user data into filter expressions. The search query is passed as a request body parameter, not interpolated into a URL or filter string.
- **Context size:** `max_context_length` prevents prompt injection via excessively large retrieved context that could push the LLM's context window beyond limits or dilute the instruction prompt.
- **Source attribution:** `{prefix}__rag_sources` provides full traceability from LLM output back to the specific documents that informed it — critical for audit.

## Future Extensibility

The `RetrievalProvider` protocol is the extensibility boundary. Adding a new backend requires:

1. Implement `RetrievalProvider` (search + close methods)
2. Add a config model for the provider
3. Register the provider name in the transform's provider dispatch

No changes to the transform, query construction, or formatting code. This is the lesson learned from the LLM transform refactor — the protocol boundary prevents vendor-specific code from becoming load-bearing in the core transform logic.

When non-Azure providers are added, the `[azure]` extra constraint relaxes to a new `[rag]` extra that includes the appropriate client libraries.
