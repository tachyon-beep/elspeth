# T10: LLM Plugin Consolidation Design

**Date:** 2026-02-25
**Status:** Approved
**Task:** elspeth-rapid-a6bde1
**Branch:** RC3.3-architectural-remediation

## Problem

6 separate LLM transform classes across 6 files total ~3,300 lines with severe
duplication. Two providers (Azure, OpenRouter) x three modes (single-query,
multi-query, batch) are implemented as independent classes that drift apart as
bugs are fixed in one but not others.

**Duplication inventory:**

| Category | Lines | Files |
|----------|-------|-------|
| Langfuse tracing (3 methods x 6 files) | ~600 | All 6 |
| Response parsing/validation | ~100 | OpenRouter variants |
| Template rendering error handling | ~32 | All 4 non-batch |
| Truncation detection | ~50 | Both multi-query |
| Markdown fence stripping | ~20 | Both multi-query |
| Output row construction | ~30 | Both single-query |
| **Total** | **~830** | |

Additional structural problems:
- Domain-specific terminology (`case_studies x criteria`) baked into multi-query
- Diamond config inheritance (`MultiQueryConfig(AzureOpenAIConfig, MultiQueryConfigMixin)`)
- Single-query and multi-query are separate code paths despite sharing infrastructure
- Adding a new provider requires implementing 2-3 full classes

## Solution: Strategy Pattern with Provider Protocol

### Core Pattern

A unified `LLMTransform` class delegates provider-specific transport to an
`LLMProvider` strategy object. Two internal processing strategies
(`SingleQueryStrategy`, `MultiQueryStrategy`) share the same provider,
tracing, and lifecycle infrastructure but have distinct processing logic.

```text
LLMTransform
├── LLMProvider protocol (transport layer)
│   ├── AzureLLMProvider (~120 lines)
│   └── OpenRouterLLMProvider (~300 lines)
├── Processing strategies (processing layer)
│   ├── SingleQueryStrategy (~100 lines)
│   └── MultiQueryStrategy (~100 lines)
├── LangfuseTracer (extracted tracing)
└── QuerySpec[] (domain-agnostic query model)
```

### Architecture Decisions

**D1: Two strategies, not one code path.**
Single-query and multi-query have genuinely different processing models:
- Single-query: template renders against raw row, output is `{response_field: content}`,
  contract uses `propagate_contract()`
- Multi-query: template renders against synthetic context (mapped fields), output is
  `{prefix_suffix: value}` per output mapping, contract rebuilt as OBSERVED

Forcing single-query through multi-query's path would require fake wrapper values or
hidden `if single_query:` branches — worse than explicit strategies. The strategies
are small (~100 lines each). The shared infrastructure eliminates the duplication.

**D2: Providers own audit recording.**
Each provider holds its own `Audited*Client` instance. Landscape call recording
happens inside `execute_query()`, matching the existing trust boundary pattern.
The transform never sees raw SDK/HTTP responses — only validated `LLMQueryResult`.

**D3: Provider lifecycle is per-state_id.**
Providers manage client caching with thread-safe locking, matching the existing
per-state_id pattern. The protocol does not expose this detail — it is internal
to each provider implementation.

**D4: Tracing belongs on the transform, not the provider.**
`setup_tracing()` is removed from the provider protocol. Azure AI auto-instrumentation
(which hooks the SDK) is set up during provider construction as a side effect.
Langfuse tracing is managed by `LangfuseTracer` at the transform level.

**D5: No query_groups (YAGNI).**
The arbitrary N-dimensional cross-product expansion was cut. Explicit `queries`
(list or dict) covers all current use cases. The existing two-dimensional
cross-product for evaluation matrices can be retained with renamed fields if
needed in a future task.

**D6: Keep batch transforms under llm/.**
Splitting into `llm_batch/` creates a false separation — batch transforms share
config, templates, tracing, and metadata utilities. A directory boundary makes
future consolidation psychologically harder without providing real isolation.

**D7: Two-phase implementation.**
Phase A extracts shared infrastructure (independently committable). Phase B
introduces the provider protocol and unified transform (builds on stable shared code).
This avoids Big Bang risk on a 3,300-line refactoring.

### Component Structure

```text
plugins/llm/
├── __init__.py              # Keep — shared field helpers (already good)
├── base.py                  # MODIFY — unified LLMConfig, flat hierarchy
├── validation.py            # MODIFY — expand with shared validation functions
├── tracing.py               # Keep — tracing config models
├── templates.py             # Keep — PromptTemplate
├── multi_query.py           # MODIFY — domain-agnostic QuerySpec, drop case_studies/criteria
│
├── provider.py              # NEW — LLMProvider protocol + LLMQueryResult DTO
├── providers/
│   ├── __init__.py
│   ├── azure.py             # NEW — AzureLLMProvider
│   └── openrouter.py        # NEW — OpenRouterLLMProvider
├── transform.py             # NEW — LLMTransform + SingleQueryStrategy + MultiQueryStrategy
├── langfuse.py              # NEW — extracted LangfuseTracer
│
├── azure.py                 # DELETE (replaced by providers/azure.py + transform.py)
├── openrouter.py            # DELETE (replaced by providers/openrouter.py + transform.py)
├── base_multi_query.py      # DELETE (absorbed into transform.py strategies)
├── azure_multi_query.py     # DELETE (absorbed into transform.py)
├── openrouter_multi_query.py # DELETE (absorbed into transform.py)
│
├── azure_batch.py           # KEEP (different execution model, adopts shared infra)
└── openrouter_batch.py      # KEEP (different execution model, adopts shared infra)
```

### Provider Protocol

```python
@dataclass(frozen=True, slots=True)
class LLMQueryResult:
    """Normalized, validated result from any LLM provider."""
    content: str                          # Validated, non-null
    usage: TokenUsage                     # Normalized via TokenUsage.known/unknown
    model: str                            # Actual responding model
    raw_response: RawCallPayload          # For audit (wrapped, not bare dict)
    finish_reason: FinishReason | None = None  # Validated enum, not raw string

class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"

class LLMProvider(Protocol):
    """Narrow interface — transport only. 2 methods."""
    def execute_query(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int | None,
        state_id: str,
        token_id: str,
    ) -> LLMQueryResult: ...

    def close(self) -> None: ...
```

Providers raise typed exceptions: `RateLimitError`, `ContentPolicyError`,
`NetworkError`, `ServerError`, `LLMCallError`. The transform converts these
to `TransformResult.error` or re-raises for RetryManager.

### Query Model (Domain-Agnostic)

```python
@dataclass(frozen=True, slots=True)
class QuerySpec:
    """One query to execute against an LLM for a given row."""
    name: str                          # Output field prefix, template key
    input_fields: dict[str, str]       # {template_var: row_field}
    response_format: ResponseFormat
    output_fields: list[OutputFieldConfig] | None = None
    template: str | None = None        # Per-query override
    max_tokens: int | None = None      # Per-query override
```

Config accepts list or dict forms (dict keys become names):

```yaml
# Single query (implicit — omit queries entirely)
transforms:
  - plugin: llm
    provider: azure
    options:
      model: gpt-4
      template: "Classify: {{ text }}"
      response_field: classification

# Multi-query — dict-keyed for readable names
transforms:
  - plugin: llm
    provider: openrouter
    options:
      model: anthropic/claude-sonnet
      template: "Evaluate {{ text }} for {{ dimension }}"
      queries:
        sentiment:
          input_fields: {text: feedback, dimension: "sentiment"}
        toxicity:
          input_fields: {text: feedback, dimension: "toxicity"}
```

### Config Model (Flat Hierarchy)

```python
class LLMConfig(TransformDataConfig):
    model: str | None = None              # None → provider-specific default
    template: str | TemplatePath = ...
    temperature: float = 0.0
    max_tokens: int | None = None
    response_field: str = "llm_response"  # Single-query output field
    response_format: ResponseFormat = ResponseFormat.STANDARD
    queries: list[QuerySpec] | dict[str, QuerySpecBody] | None = None
    tracing: TracingConfig | None = None
    max_concurrent_queries: int = 3

class AzureOpenAIConfig(LLMConfig):
    deployment_name: str
    endpoint: str
    api_key: str
    api_version: str = "2024-10-21"

class OpenRouterConfig(LLMConfig):
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0
```

No more `MultiQueryConfigMixin` or diamond inheritance. Multi-query fields
live in base `LLMConfig`. Pydantic validator normalizes dict→list for queries.

### Plugin Registration

5 plugin names collapse to 1:

| Before | After |
|--------|-------|
| `azure_llm` | `llm` with `provider: azure` |
| `openrouter_llm` | `llm` with `provider: openrouter` |
| `azure_multi_query_llm` | `llm` with `provider: azure` + `queries:` |
| `openrouter_multi_query_llm` | `llm` with `provider: openrouter` + `queries:` |
| `azure_batch_llm` | Unchanged |
| `openrouter_batch_llm` | Unchanged |

Provider routing is internal to `LLMTransform.__init__` via dict lookup.
Not exposed through pluggy. Old plugin names get a helpful error message,
no compatibility shim (no-legacy-code policy).

### Transform Lifecycle

```text
Row arrives at LLMTransform.process()
│
├─ Delegate to strategy (SingleQueryStrategy or MultiQueryStrategy)
│
│  SingleQueryStrategy:
│  ├─ Render template against raw row
│  ├─ provider.execute_query() → LLMQueryResult
│  ├─ Check truncation (finish_reason == LENGTH)
│  ├─ Strip markdown fences if STANDARD format
│  ├─ output[response_field] = content
│  ├─ populate_llm_metadata_fields()
│  ├─ propagate_contract()
│  └─ Return TransformResult.success
│
│  MultiQueryStrategy:
│  ├─ For each QuerySpec: build template context, render template
│  ├─ Fan out via PooledExecutor → list[LLMQueryResult]
│  ├─ For each result: truncation check, fence strip, JSON parse, field extract
│  ├─ Merge all query outputs into row
│  ├─ Build OBSERVED SchemaContract
│  └─ Return TransformResult.success
│
└─ Error handling:
   ├─ Template failure → TransformResult.error (not retryable)
   ├─ RateLimitError → re-raise (RetryManager)
   ├─ NetworkError/ServerError → re-raise (retryable)
   ├─ ContentPolicyError → TransformResult.error (not retryable)
   ├─ Truncation → TransformResult.error (not retryable)
   └─ JSON validation failure → TransformResult.error (not retryable)
```

Partial multi-query failure = full row failure (audit integrity).

### Langfuse Extraction

```python
class LangfuseTracer:
    """Manages Langfuse span recording for LLM queries. One instance per transform."""
    def __init__(self, langfuse_client, transform_name: str): ...
    def record_success(self, telemetry_emit, token_id, spec_name, prompt, result): ...
    def record_error(self, telemetry_emit, token_id, spec_name, prompt, error_msg): ...
```

Accepts `telemetry_emit` callback (not full `PluginContext`) for testability.
Replaces 3 methods x 6 files (~600 lines) with 2 methods x 1 file (~80 lines).

## Implementation Phases

### Phase A: Extract Shared Infrastructure
1. Create `langfuse.py` — extract `LangfuseTracer` from all 6 files
2. Expand `validation.py` — shared template error handling, truncation detection,
   markdown fence stripping
3. Update all 6 existing transforms to use extracted utilities
4. All existing tests pass (no behavioral change)
5. Commit

### Phase B: Provider Protocol + Unified Transform
1. Create `provider.py` — `LLMProvider`, `LLMQueryResult`, `FinishReason`
2. Create `providers/azure.py` — `AzureLLMProvider`
3. Create `providers/openrouter.py` — `OpenRouterLLMProvider`
4. Create `transform.py` — `LLMTransform`, `SingleQueryStrategy`, `MultiQueryStrategy`
5. Refactor `base.py` — flat config hierarchy
6. Refactor `multi_query.py` — domain-agnostic `QuerySpec`
7. Update plugin registration (1 plugin name)
8. Migrate tests (421 class refs across 24 files)
9. Update example YAML files
10. Delete old files (`azure.py`, `openrouter.py`, `base_multi_query.py`,
    `azure_multi_query.py`, `openrouter_multi_query.py`)
11. Commit

## Expected Impact

- ~3,400 lines deleted, ~720 lines created = **~2,700 net reduction**
- 5 plugin names → 1
- Diamond config inheritance → flat hierarchy
- Domain-specific terminology → domain-agnostic QuerySpec
- New provider = ~100-300 line class (vs 2-3 full transforms)
- ChaosLLM slots in as test provider via same protocol
- Batch transforms adopt extracted tracing/validation (not restructured)

## Review Panel

Design reviewed 2026-02-25 by three specialized agents:

- **Architecture Critic** (4/5): Core strategy pattern correct. Flagged
  single→multi-query forced unification, query_groups YAGNI, audit recording
  layer ambiguity. All addressed in revisions.
- **Systems Thinker** (Leverage Level 10): Confirmed genuine structural leverage
  breaking divergence reinforcing loop. Recommended two-phase implementation,
  two strategies over forced unification, keeping batch under llm/.
- **Python Engineering Reviewer** (3C/5W/3S): Flagged raw_response typing,
  provider lifecycle per-state_id, setup_tracing placement. Endorsed flat
  config hierarchy and LangfuseTracer extraction.

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Big Bang transition (3,300 lines) | Two-phase: extract shared (A) then restructure (B) |
| Provider-specific edge cases lost | Maintain provider-specific test cases post-consolidation |
| Test blast radius (421 refs, 24 files) | Explicit test migration in Phase B |
| Batch transforms diverge further | Adopt extracted langfuse.py + validation.py in same pass |
| Example YAML breakage | Integration test validates all examples parse |

## Dependencies

- T8 (remove dead code): CLOSED
- T9 (typed dataclasses): CLOSED — provides LLMCallRequest, LLMCallResponse, TokenUsage

## References

- Architecture analysis: `docs/arch-analysis-2026-02-22-0446/06-architect-handover.md`
- T9 contracts: `src/elspeth/contracts/call_data.py`
- Existing shared utilities: `src/elspeth/plugins/llm/__init__.py`, `validation.py`
