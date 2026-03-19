# Source and Sink I/O Retry — Design Spec

**Date:** 2026-03-19
**Status:** Reviewed (R1 — architecture critic findings resolved: getattr→RetryableError protocol, jitter field added, lifecycle delegation documented, file inventory gaps filled, null-byte composite separator, non-keyed retry semantics specified)
**Scope:** Composition-based retry wrappers for source and sink I/O operations, with content-based key tracking for source retry skip

## Overview

Add transient failure retry to source and sink I/O operations. Currently only transforms have retry support (per-row, via `RetryManager`). Sources and sinks propagate all exceptions to the orchestrator, killing the run on any transient failure — token expiry, rate limiting, network blips.

Two composition-based wrappers (`SourceWrap`, `SinkWrap`) intercept source `load()` and sink `write()` calls, retrying on transient failures with exponential backoff. The orchestrator sees the same `SourceProtocol` / `SinkProtocol` interfaces — retry is invisible to it.

For source retry, content-based key tracking avoids re-processing rows that already entered the pipeline. The source declares which field(s) uniquely identify a row (e.g., `contactid` for Dataverse). On retry, the wrapper re-fetches all pages from the external API but skips rows whose key was already yielded to the orchestrator. This is safe for eventually-consistent APIs because it matches on content identity, not positional index.

## Motivation

Any source or sink that calls an external API faces transient failures:
- OAuth2 token expiry mid-pagination (Azure credential TTL: 60-75 minutes)
- Rate limiting (429 with `Retry-After`)
- Transient server errors (500-599)
- Network timeouts and connection resets

Without retry, a pipeline processing 50,000 Dataverse records that hits a 401 on page 47 loses all progress. The operator must manually re-run from scratch. With retry, the wrapper reconstructs the credential, re-paginates, skips the 46 pages of already-processed rows by content key, and resumes from page 47's data.

### Why Not Positional Skip?

An earlier design considered "skip to row N" — count how many rows were yielded, re-paginate, and discard the first N rows from the retry pass. Expert review rejected this for eventually-consistent APIs (Dataverse, REST endpoints):

- **Insert between passes:** A record inserted before row 200 shifts all subsequent positions. Row 488 in the retry pass is a different entity than row 488 in the original pass. Silent data loss.
- **Delete between passes:** A deleted record shifts positions backward. The engine skips past rows it never processed. Silent data loss.
- **No snapshot isolation:** OData pagination with `@odata.nextLink` does not provide snapshot isolation. Each page request is a new query. `$orderby` on an immutable key doesn't help — inserts and deletes still shift page boundaries.

Content-based key matching is immune to all three scenarios because it matches on what the row IS, not where it appears.

Positional skip IS safe for static file sources (CSV, JSON) where the file doesn't change between reads. The wrapper degrades gracefully: sources that don't declare key fields get full re-run retry (safe but slower).

## Architecture

### Wrapper Pattern

```text
Orchestrator
    │
    ├── source_iterator = source.load(ctx)     ← unchanged
    │        │
    │        └── SourceWrap.load(ctx)
    │              │
    │              ├── inner_source.load(ctx)  → yields rows
    │              ├── tracks processed keys per row
    │              ├── on transient error:
    │              │     ├── inner_source.close()
    │              │     ├── inner_source.on_start(lifecycle_ctx)
    │              │     ├── inner_source.load(ctx)  → fresh generator
    │              │     ├── skip rows with known keys
    │              │     └── resume yielding new rows
    │              └── from orchestrator's view: iterator just continues
    │
    └── sink.write(rows, ctx)                  ← unchanged
              │
              └── SinkWrap.write(rows, ctx)
                    │
                    ├── inner_sink.write(rows, ctx)
                    ├── on transient error:
                    │     ├── guard: inner_sink.idempotent must be True
                    │     ├── backoff
                    │     └── inner_sink.write(rows, ctx)  → retry same batch
                    └── return ArtifactDescriptor
```

### Layer Placement

Both wrappers live at L2 (engine) in a new `engine/retryable_io.py`. They compose L3 plugins but don't depend on any specific plugin. They satisfy `SourceProtocol` / `SinkProtocol` via delegation.

### Instantiation

The orchestrator wraps sources and sinks during run setup, after `instantiate_plugins_from_config()` returns. Wrapping is conditional:

- Source wrapped if `source.supports_retry is True` and `io_retry.enabled is True`
- Sink wrapped if `sink.supports_retry is True` and `io_retry.enabled is True`

Sources that declare `supports_retry = False` (e.g., a future destructive streaming source) are never wrapped. This is an explicit opt-out — the default is `True`.

## Wrapper Lifecycle Delegation

Both wrappers satisfy `SourceProtocol` / `SinkProtocol` by delegating all methods and properties to the inner plugin. Only `load()` (SourceWrap) and `write()` (SinkWrap) contain retry logic — everything else is pass-through.

### SourceWrap Delegation

| Member | Delegation |
|---|---|
| `name` | `self._inner.name` |
| `determinism` | `self._inner.determinism` |
| `output_schema` | `self._inner.output_schema` |
| `node_id` | `self._inner.node_id` (set by orchestrator) |
| `plugin_version` | `self._inner.plugin_version` |
| `supports_resume` | `self._inner.supports_resume` |
| `on_start(ctx)` | Delegates to `self._inner.on_start(ctx)` AND captures `ctx` for retry reconstruction |
| `on_complete(ctx)` | Delegates to `self._inner.on_complete(ctx)` |
| `close()` | Delegates to `self._inner.close()` |
| `get_field_resolution()` | `self._inner.get_field_resolution()` |
| `get_schema_contract()` | `self._inner.get_schema_contract()` |
| `set_schema_contract(c)` | `self._inner.set_schema_contract(c)` |
| `load(ctx)` | **Intercepted** — retry + key tracking logic |

### SinkWrap Delegation

| Member | Delegation |
|---|---|
| `name` | `self._inner.name` |
| `determinism` | `self._inner.determinism` |
| `input_schema` | `self._inner.input_schema` |
| `node_id` | `self._inner.node_id` |
| `plugin_version` | `self._inner.plugin_version` |
| `idempotent` | `self._inner.idempotent` (queried at retry decision time) |
| `supports_resume` | `self._inner.supports_resume` |
| `on_start(ctx)` | Delegates to `self._inner.on_start(ctx)` AND captures `ctx` |
| `on_complete(ctx)` | Delegates to `self._inner.on_complete(ctx)` |
| `close()` | Delegates to `self._inner.close()` |
| `flush()` | Delegates to `self._inner.flush()` |
| `write(rows, ctx)` | **Intercepted** — retry + idempotency guard |

The delegation is mechanical — a `__getattr__` fallback to `self._inner` could replace explicit delegation, but explicit delegation is preferred for protocol compliance visibility and mypy satisfaction.

## SourceWrap

### Normal Flow

```python
def load(self, ctx: SourceContext) -> Iterator[SourceRow]:
    gen = self._inner.load(ctx)
    for source_row in gen:
        if not source_row.is_quarantined and self._key_fields is not None:
            key = self._extract_key(source_row.row)
            self._processed_keys.add(key)
        yield source_row
```

### Retry Flow

When the generator raises a retryable exception:

1. Record retry event via `ctx.record_call()` (audit: the retry decision is recorded)
2. Backoff via `RetryManager` (exponential with jitter)
3. Close the inner source (`inner.close()`)
4. Re-initialize the inner source (`inner.on_start(lifecycle_ctx)`) — reconstructs client, credential, etc.
5. Get fresh generator (`inner.load(ctx)`)
6. Consume rows from fresh generator:
   - If `key_fields` declared: extract key, skip if key in `processed_keys`, yield if new
   - If `key_fields` is `None`: yield all rows (full re-run)
7. Continue until generator exhausts or another transient failure triggers another retry

### Python Generator Limitation

Python generators close permanently after raising an exception — `next()` returns `StopIteration` forever after. Source retry therefore requires calling `source.load()` again to get a fresh generator. This is why the wrapper calls `close()` + `on_start()` + `load()` on retry — the inner source must be fully reconstructed.

### Key Tracking

The wrapper maintains a `set[str]` of processed keys in memory during the run. Key extraction:

- **Single-field key:** `str(row[field])`
- **Composite key:** `"\x00".join(str(row[f]) for f in fields)` — null byte separator cannot appear in any field value (strings, GUIDs, integers), making collisions impossible for arbitrary key types
- **Quarantined rows:** Skipped for key tracking (may lack key fields). Always yielded regardless of retry state — they need to reach the quarantine sink.
- **Size:** For 100K rows with UUID keys (36 chars), the set is ~4MB. Acceptable for in-memory storage during a single run.

Keys are NOT checkpointed to disk. Source retry is within a single run attempt. If all retries exhaust, the run fails and `elspeth resume` handles recovery through the existing checkpoint/resume mechanism (which bypasses the source entirely, restoring rows from payload store).

### Non-Keyed Retry (Full Re-Run) Semantics

When `source_key_fields` is `None`, the wrapper retries by yielding ALL rows from the fresh generator — including rows that were already processed in the first pass. This produces duplicate rows entering the orchestrator. The duplicates are acceptable because:

1. **Static file sources** (CSV, JSON, AzureBlob) return identical data on re-read. The same rows enter the pipeline with the same content. Transforms re-execute and sinks re-write. For idempotent sinks, this is safe. For non-idempotent sinks, the SinkWrap refuses to retry — so the run fails and the operator re-runs manually.
2. **Row identity:** Each duplicate row gets a NEW `row_id` (UUID generated by the engine at token creation). The audit trail correctly shows two separate processing events for the same source content. This is auditably honest — both events happened.
3. **Transform cost:** Re-executing transforms (especially LLM transforms) on already-processed rows is the main cost. This is a performance concern, not a correctness concern. Content-based key tracking (by declaring `source_key_fields`) is the solution for sources where this cost matters.

### Lifecycle Context Capture

The wrapper captures the `LifecycleContext` from the first `on_start()` call. On retry, it passes the same context to `inner.on_start()`. The context is run-scoped (`run_id`, `rate_limit_registry`, `telemetry_emit`) — it doesn't change between retry attempts within a run.

## SinkWrap

### Normal Flow

```python
def write(self, rows: list[dict[str, Any]], ctx: SinkContext) -> ArtifactDescriptor:
    return self._inner.write(rows, ctx)
```

### Retry Flow

When `write()` raises a retryable exception:

1. **Idempotency guard:** If `inner.idempotent is False`, raise immediately. Non-idempotent sinks cannot safely re-send the same batch. The error is recorded with `"reason": "retryable_but_non_idempotent"`.
2. Record retry event via `ctx.record_call()`
3. Backoff via `RetryManager`
4. Re-call `inner.write(rows, ctx)` with the same batch

No `close()` / `on_start()` cycle needed — the sink's client connection pool handles reconnection internally. The same `rows` list reference is passed on retry.

**Executor interaction:** The `SinkExecutor` calls `sink_wrap.write(rows, ctx)`. The wrapper retries internally. If all retries fail, the wrapper raises, and THEN the executor marks states as FAILED. The executor never sees intermediate failures — only the final outcome.

### Mode-Aware Idempotency

The DataverseSink currently declares `idempotent = False` at the class level (conservative — future create/update modes are not idempotent). The `idempotent` attribute should become a property that checks the configured write mode:

```python
@property
def idempotent(self) -> bool:
    return self._mode == "upsert"
```

This allows the SinkWrap to query actual runtime idempotency. Other sinks (CSV, JSON, Database) remain `False`.

## Retry Capability Model

**Default stance: all sources and sinks are retryable.** Plugins that cannot support retry must explicitly opt out.

### Source Properties

| Property | Type | Default | Purpose |
|---|---|---|---|
| `supports_retry` | `bool` | `True` | Whether retry is possible at all. `False` for destructive/streaming sources. |
| `source_key_fields` | `tuple[str, ...] \| None` | `None` | Fields for content-based skip. `None` = full re-run on retry. |
| `classify_retryable` | method | Returns `None` | Plugin-specific error classification override. |

### Sink Properties

| Property | Type | Default | Purpose |
|---|---|---|---|
| `supports_retry` | `bool` | `True` | Whether retry is possible at all. |
| `idempotent` | `bool` or property | `False` | Whether batch re-send is safe. SinkWrap refuses to retry if `False`. |
| `classify_retryable` | method | Returns `None` | Plugin-specific error classification override. |

### Retry Behavior Matrix

| Source | `supports_retry` | `source_key_fields` | Retry Behavior |
|---|---|---|---|
| DataverseSource (structured) | `True` (default) | `("<entity>id",)` inferred | Content-based skip on retry |
| DataverseSource (FetchXML) | `True` (default) | From config or `None` | Content-based skip or full re-run |
| CSVSource | `True` (default) | `None` | Full re-run (file is static) |
| AzureBlobSource | `True` (default) | `None` | Full re-run |
| JSONSource | `True` (default) | `None` | Full re-run |
| Future streaming source | `False` (explicit) | N/A | No retry |

| Sink | `supports_retry` | `idempotent` | Retry Behavior |
|---|---|---|---|
| DataverseSink (upsert) | `True` (default) | `True` (mode-aware) | Batch re-send |
| DataverseSink (future create) | `True` (default) | `False` (mode-aware) | Retry refused |
| CSVSink | `True` (default) | `False` | Retry refused |
| JSONSink | `True` (default) | `False` | Retry refused |
| DatabaseSink | `True` (default) | `False` | Retry refused |

## Error Classification

### Default Predicate

```python
from elspeth.contracts.errors import RetryableError  # New protocol

@runtime_checkable
class RetryableError(Protocol):
    """Protocol for exceptions that carry retryability classification."""
    @property
    def retryable(self) -> bool: ...

def _default_is_retryable(exc: BaseException) -> bool:
    # Protocol: system-owned exceptions declare retryability via RetryableError
    if isinstance(exc, RetryableError):
        return exc.retryable

    # Type-based fallback for third-party exceptions without the protocol
    return isinstance(exc, (
        httpx.TimeoutException,
        httpx.ConnectError,
        ConnectionError,
        TimeoutError,
    ))
```

**Why `isinstance(exc, RetryableError)` not `getattr`:** Per CLAUDE.md, `getattr` with defaults is banned. System-owned exceptions (`DataverseClientError`, `LLMClientError`) satisfy the `RetryableError` protocol structurally — `isinstance` with `@runtime_checkable` checks protocol conformance without `getattr`. Third-party exceptions (e.g., `azure.identity` errors) that don't satisfy the protocol fall through to the type-based branch.

### Plugin Override

Sources and sinks can optionally provide their own classification:

```python
def classify_retryable(self, exc: BaseException) -> bool | None:
    """Returns True/False for definitive classification, None for default."""
    return None
```

The wrapper checks `inner.classify_retryable(exc)` first. If it returns `None`, the default predicate applies.

### Never Retried

- `FrameworkBugError`, `AuditIntegrityError` — system integrity, always re-raised immediately
- `KeyError`, `TypeError`, `AttributeError`, `NameError` — programming bugs
- `PluginConfigError` — configuration problem

The wrapper catches these before the general `Exception` handler and re-raises without consulting the predicate.

## Configuration

### Settings Model

```python
class IORetrySettings(BaseModel):
    """Retry configuration for source and sink I/O operations."""
    max_attempts: int = Field(default=3, gt=0)
    initial_delay_seconds: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=60.0, gt=0)
    exponential_base: float = Field(default=2.0, gt=1.0)
    enabled: bool = Field(default=True)
```

### Pipeline YAML

```yaml
io_retry:
  max_attempts: 3
  initial_delay_seconds: 1.0
  max_delay_seconds: 60.0

# OR disabled:
io_retry:
  enabled: false
```

Single config section applies to all sources and sinks. Per-plugin overrides deferred to a future iteration.

`IORetrySettings` nests under the top-level `PipelineSettings` alongside the existing `RetrySettings` (which governs transform retry). In `core/config.py`:

```python
class PipelineSettings(BaseModel):
    retry: RetrySettings = Field(default_factory=RetrySettings)       # transforms
    io_retry: IORetrySettings = Field(default_factory=IORetrySettings) # sources/sinks
    # ... existing fields
```

### Runtime Mapping

```python
@dataclass(frozen=True, slots=True)
class RuntimeIORetryConfig:
    max_attempts: int
    base_delay: float
    max_delay: float
    jitter: float  # Required by RuntimeRetryProtocol
    exponential_base: float
    enabled: bool

    @classmethod
    def from_settings(cls, settings: IORetrySettings) -> RuntimeIORetryConfig:
        return cls(
            max_attempts=settings.max_attempts,
            base_delay=settings.initial_delay_seconds,
            max_delay=settings.max_delay_seconds,
            jitter=INTERNAL_DEFAULTS["retry"]["jitter"],  # 1.0 — not user-configurable
            exponential_base=settings.exponential_base,
            enabled=settings.enabled,
        )
```

This satisfies `RuntimeRetryProtocol` (including the required `jitter` property) — reuses `RetryManager` internally. The `jitter` field uses the same hardcoded internal default as `RuntimeRetryConfig`.

### Config Flow

```text
YAML → IORetrySettings (Pydantic) → RuntimeIORetryConfig (frozen dataclass)
  → stored in PipelineConfig
  → passed to SourceWrap/SinkWrap constructors
  → wrappers create RetryManager(config) internally
```

## Audit Trail Recording

### Source Retry Audit

Each retry attempt produces:

1. **Retry decision record** via `ctx.record_call()`:
   - `call_type`: `CallType.HTTP` with `provider="io_retry"`
   - `status`: `CallStatus.ERROR`
   - `error`: `{"reason": "transient_auth_failure", "attempt": 2, "max_attempts": 3, "processed_keys_count": 100, "strategy": "content_key_skip"}`

2. **Inner source HTTP calls** recorded normally by the inner source's `record_call()` calls. On retry pass, pages 1-N appear again in the audit trail — each HTTP call actually happened.

3. **Skipped rows** are NOT recorded in `node_states`. They were already recorded during the first pass. The wrapper consumes them from the generator but doesn't yield them to the orchestrator, so no token is created.

4. **Row index continuity.** The orchestrator's `row_index` (from `enumerate(source_iterator)`) continues monotonically. The wrapper yielded 100 rows before failure, then yields rows 100+ after retry. No gaps.

### Sink Retry Audit

Each retry attempt produces:

1. **Retry decision record** via `ctx.record_call()`
2. **Re-sent rows** produce duplicate `record_call` entries — attempt 1 row A SUCCESS + attempt 2 row A SUCCESS. Both calls actually happened. Auditor can see retry and confirm idempotent behavior.

## Dataverse Integration

### 401 Credential Reconstruction

The tactical fix (move `reconstruct_credential()` inside `DataverseClient._execute_request()`) is now part of the strategic design. The client handles 401 retry internally as a protocol-level concern. The `SourceWrap` handles higher-level transient failures (429, 5xx, network errors).

This is two levels of retry:
- **Client level:** 401 → reconstruct credential → retry immediately (once, no backoff)
- **Wrapper level:** 429/5xx/network → backoff → close/on_start/load cycle → content-based skip

### Source Key Fields

Dataverse entities always have a GUID primary key named `<entitylogicalname>id`:

```python
# DataverseSource (structured mode)
@property
def source_key_fields(self) -> tuple[str, ...] | None:
    if self._entity is not None:
        return (f"{self._entity}id",)
    # FetchXML: use config-specified key field, or None for full re-run
    return (self._source_key_field,) if self._source_key_field else None
```

Config for FetchXML mode:

```yaml
source:
  plugin: dataverse
  options:
    fetch_xml: |
      <fetch>...</fetch>
    source_key_field: contactid   # explicit when inference isn't possible
```

### Sink Idempotency

DataverseSink changes `idempotent` from a class attribute to a mode-aware property:

```python
@property
def idempotent(self) -> bool:
    return self._mode == "upsert"
```

## File Inventory

### New Files

| File | Purpose |
|---|---|
| `engine/retryable_io.py` | `SourceWrap`, `SinkWrap`, default retryable predicate |

### Config Pipeline (5 files)

| File | Change |
|---|---|
| `core/config.py` | Add `IORetrySettings` |
| `contracts/config/protocols.py` | Add `RuntimeIORetryProtocol` |
| `contracts/config/runtime.py` | Add `RuntimeIORetryConfig` with `from_settings()` |
| `contracts/config/alignment.py` | Add field mapping documentation |
| `contracts/config/defaults.py` | Add `POLICY_DEFAULTS` for io_retry |

### Plugin Protocol + Base (3 files)

| File | Change |
|---|---|
| `contracts/plugin_protocols.py` | Add `source_key_fields`, `supports_retry`, `classify_retryable` to both protocols |
| `plugins/infrastructure/base.py` | Add default implementations to `BaseSource` and `BaseSink` |
| `plugins/sinks/dataverse.py` | Override `idempotent` as mode-aware property |

### Dataverse (3 files)

| File | Change |
|---|---|
| `plugins/sources/dataverse.py` | Declare `source_key_fields` property; add `source_key_field` to `DataverseSourceConfig` for FetchXML mode |
| `plugins/infrastructure/clients/dataverse.py` | Move 401 retry into `_execute_request`; delete public `reconstruct_credential()` |
| `contracts/errors.py` | Add `RetryableError` runtime-checkable protocol |

### Engine (2 files)

| File | Change |
|---|---|
| `engine/orchestrator/core.py` | Wrap source/sinks in `SourceWrap`/`SinkWrap` during run setup (~10 lines) |
| `engine/orchestrator/types.py` | Add `io_retry_config` to `PipelineConfig` |

### CI/Enforcement (3 files)

| File | Change |
|---|---|
| `config/cicd/enforce_tier_model/` | Allowlist entries for `retryable_io.py` |
| `config/cicd/contracts-whitelist.yaml` | Dict pattern entries for wrapper methods |
| `tests/unit/core/test_config_alignment.py` | Alignment test for new settings→runtime mapping |

### Tests (3 files)

| File | Coverage |
|---|---|
| `tests/unit/engine/test_retryable_io.py` | SourceWrap + SinkWrap unit tests |
| `tests/unit/engine/test_retryable_io_integration.py` | Wrapper + mock source/sink end-to-end |
| Update existing Dataverse test files | Key fields, idempotency property, removed reconstruct_credential |

### Unchanged

`RetryManager`, `RowProcessor`, `SinkExecutor`, `TransformExecutor`, DAG construction, Landscape schema, checkpoint schema, Alembic migrations, all existing source plugins except Dataverse.

## Testing Strategy

### Unit Tests (`test_retryable_io.py`)

- SourceWrap: normal flow (no failure, all rows yielded)
- SourceWrap: single retry with content-based skip (key match)
- SourceWrap: single retry without key fields (full re-run)
- SourceWrap: max retries exhausted → exception propagates
- SourceWrap: non-retryable exception → immediate propagation
- SourceWrap: quarantined rows always yielded (not key-tracked)
- SourceWrap: `supports_retry=False` source → not wrapped
- SourceWrap: `FrameworkBugError` never caught
- SinkWrap: normal flow
- SinkWrap: retry with idempotent sink
- SinkWrap: retry refused for non-idempotent sink
- SinkWrap: max retries exhausted
- SinkWrap: `classify_retryable` override respected
- Default predicate: `DataverseClientError(retryable=True)` → retryable
- Default predicate: `DataverseClientError(retryable=False)` → not retryable
- Default predicate: `httpx.TimeoutException` → retryable
- Default predicate: `KeyError` → not retryable

### Integration Tests (`test_retryable_io_integration.py`)

- Source: mock source that fails on page 3, retry succeeds — verify key-based skip, audit trail shows both passes
- Source: mock source that fails on every attempt — verify max retries then propagation
- Sink: mock sink that fails first write, retry succeeds — verify same batch re-sent
- Sink: mock non-idempotent sink failure — verify retry refused with audit record

## Security Considerations

- **Credential reconstruction on retry:** The SourceWrap calls `inner.on_start()` which reconstructs the credential. The old credential is discarded. Token material is never stored in the retry state.
- **Processed keys in memory:** The `set[str]` of entity IDs is held in process memory only. Not persisted to disk, not logged, not included in audit trail payloads. Entity IDs are not PII but may be considered sensitive in some contexts — the set is garbage-collected when the wrapper is collected.
- **Retry amplification:** The wrapper enforces `max_attempts` strictly. A source that returns `retryable=True` on every attempt will exhaust retries and fail, not loop infinitely. Rate limiting (`_acquire_rate_limit`) applies on every HTTP call including retries.

## Dependencies

No new dependencies. `RetryManager` (tenacity-based) is reused. `SourceWrap` and `SinkWrap` are pure Python composition with no external library requirements.
