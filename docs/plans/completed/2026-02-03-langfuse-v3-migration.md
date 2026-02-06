# Langfuse v3 Migration Plan

**Date**: 2026-02-03
**Status**: Ready for Execution
**Risk Level**: Medium (straightforward API changes across 6 plugin files)
**Review Status**: ✅ Passed (after amendments)

## Background

The Langfuse Python SDK v3 (released June 2025, now at v3.12.1) is built on OpenTelemetry standards. Our current implementation uses v2 patterns that must be updated.

**Current constraint in pyproject.toml:**
```toml
"langfuse>=2.50,<3",  # Langfuse SDK v2 - v3 migration requires code changes
```

## Prerequisites Verification ✅

### OpenTelemetry Compatibility (Verified 2026-02-03)

Langfuse v3.12.1 is compatible with our existing OpenTelemetry stack:

```bash
$ uv pip install "langfuse>=3.12,<4" "opentelemetry-api>=1.39,<2" --dry-run
Resolved 33 packages in 11ms
Would install 3 packages:
 + backoff==2.2.1
 + langfuse==3.12.1
 + wrapt==1.17.3 (downgrade from 2.1.0)
```

**No version conflicts detected.** Langfuse v3 works with `opentelemetry-api>=1.39,<2`.

### Thread Safety (Verified 2026-02-03)

Per [Langfuse upgrade documentation](https://langfuse.com/docs/observability/sdk/python/upgrade-path):

- v3 uses **OpenTelemetry context propagation** which relies on **thread-local storage**
- Each thread maintains its own context - safe for `BatchTransformMixin` thread pools
- The concern in [GitHub discussion #6993](https://github.com/orgs/langfuse/discussions/6993) is about reusing *callback handlers*, not `start_as_current_observation()` itself
- Each call to `start_as_current_observation()` creates its own isolated context

**Thread-safe for our use case.** No changes to batch plugin architecture needed.

## Breaking Change Notice ⚠️

**ELSPETH pipelines using Langfuse v2 tracing will require SDK upgrade.**

After this migration, pipelines with Langfuse tracing must use Langfuse SDK v3.12+:

```bash
# Required after ELSPETH upgrade
uv pip install 'langfuse>=3.12,<4'
```

No configuration changes required - the migration is API-internal.

## Best Practice: v3 Patterns

### Context Manager Pattern (Recommended)

v3 uses nested context managers for automatic lifecycle management:

```python
# Best practice: Nested context managers
with langfuse.start_as_current_observation(
    as_type="span",
    name="elspeth.azure_llm",
    metadata={"token_id": token_id, "plugin": self.name}
) as span:
    # Make LLM call
    response = llm_client.chat_completion(...)

    # Record generation within span
    with langfuse.start_as_current_observation(
        as_type="generation",
        name="llm_call",
        model=self._model,
        input=[{"role": "user", "content": prompt}],
    ) as generation:
        generation.update(
            output=response.content,
            usage_details={
                "input": response.usage.get("prompt_tokens", 0),
                "output": response.usage.get("completion_tokens", 0),
            },
            metadata={"latency_ms": latency_ms},
        )
# Both span and generation auto-close when context exits

langfuse.flush()  # Ensure events sent before shutdown
```

### Key v3 Changes

| v2 Pattern | v3 Best Practice |
|------------|-----------------|
| `trace = client.trace(...)` | `with client.start_as_current_observation(as_type="span") as span:` |
| `trace.generation(...)` | `with client.start_as_current_observation(as_type="generation") as gen:` then `gen.update(...)` |
| `trace.span(...)` | `with client.start_as_current_observation(as_type="span") as span:` (nested) |
| `enabled=True` | `tracing_enabled=True` |
| Implicit close | Context manager auto-close |
| `usage={"input": ..., "output": ...}` | `usage_details={"input": ..., "output": ...}` |

### Constructor Changes

**v2:**
```python
Langfuse(public_key=..., secret_key=..., host=...)
```

**v3:**
```python
Langfuse(public_key=..., secret_key=..., host=..., tracing_enabled=True)
```

### Custom IDs → Metadata

v3 enforces W3C Trace Context (no custom observation IDs). We use `metadata` for `token_id` correlation, which is still supported - **no impact**.

## Affected Files

### Plugin Files (6 files)

| File | Current Pattern | v3 Pattern |
|------|----------------|------------|
| `azure.py` | `_create_langfuse_trace` context manager + `_record_langfuse_generation` | Single nested context manager |
| `azure_batch.py` | Direct `trace()` + `span()` for job-level tracing | Nested context managers |
| `azure_multi_query.py` | `_create_langfuse_trace` + `_record_langfuse_generation` | Single nested context manager |
| `openrouter.py` | `_create_langfuse_trace` + `_record_langfuse_generation` | Single nested context manager |
| `openrouter_batch.py` | Direct `trace()` + `generation()` | Nested context managers |
| `openrouter_multi_query.py` | `_create_langfuse_trace` + `_record_langfuse_generation` | Single nested context manager |

### Configuration Files (1 file)

| File | Changes Needed |
|------|---------------|
| `tracing.py` | Add `tracing_enabled` to `LangfuseTracingConfig` |

### Test Files (4 files)

| File | Changes Needed |
|------|---------------|
| `test_tracing_integration.py` | Update mock patterns for v3 API |
| `test_openrouter_tracing.py` | Update mock patterns for v3 API |
| `test_azure_tracing.py` | Update mock patterns for v3 API |
| `test_tracing_config.py` | Test new config fields |

## Implementation Plan

### Task 1: Update pyproject.toml

**File:** `pyproject.toml`

Update version constraint to enable v3 SDK installation:

```toml
tracing-langfuse = [
    # Tier 2: Langfuse tracing for LLM plugins
    # v3 built on OpenTelemetry standards - uses context managers for lifecycle
    # Thread-safe: uses OTEL thread-local context propagation
    # Ref: https://langfuse.com/docs/observability/sdk/python/upgrade-path
    "langfuse>=3.12,<4",  # Langfuse SDK v3
]
```

Also update in `all` optional dependencies.

**Acceptance Criteria:**
- [ ] Version constraint updated to `>=3.12,<4`
- [ ] `uv pip install -e ".[tracing-langfuse]"` succeeds
- [ ] No OTEL version conflicts

### Task 2: Update LangfuseTracingConfig

**File:** `src/elspeth/plugins/llm/tracing.py`

**Changes:**
1. Add `tracing_enabled: bool = True` field to `LangfuseTracingConfig`
2. Update `parse_tracing_config()` to parse new field

```python
@dataclass(frozen=True, slots=True)
class LangfuseTracingConfig(TracingConfig):
    provider: str = "langfuse"
    public_key: str | None = None
    secret_key: str | None = None
    host: str = "https://cloud.langfuse.com"
    tracing_enabled: bool = True  # NEW: v3 parameter name
```

**Acceptance Criteria:**
- [ ] New field added with default `True`
- [ ] Parse function handles new field
- [ ] Tests verify config parsing

### Task 3: Update azure.py - Refactor to v3 Pattern

**Goal:** Replace two-method pattern with single method using v3 nested context managers.

**Current (v2):**
```python
@contextmanager
def _create_langfuse_trace(self, token_id, row_data):
    trace = self._langfuse_client.trace(name=..., metadata=...)
    yield trace

def _record_langfuse_generation(self, trace, prompt, response_content, model, usage, latency_ms):
    trace.generation(name="llm_call", model=model, input=prompt, output=response_content, usage=...)
```

**Target (v3 best practice):**
```python
def _record_langfuse_trace(
    self,
    ctx: PluginContext,
    token_id: str,
    prompt: str,
    response_content: str,
    usage: dict[str, int] | None,
    latency_ms: float | None,
) -> None:
    """Record LLM call to Langfuse using v3 nested context managers."""
    if not self._tracing_active or self._langfuse_client is None:
        return
    if not isinstance(self._tracing_config, LangfuseTracingConfig):
        return

    try:
        with self._langfuse_client.start_as_current_observation(
            as_type="span",
            name=f"elspeth.{self.name}",
            metadata={"token_id": token_id, "plugin": self.name, "deployment": self._deployment_name},
        ) as span:
            with self._langfuse_client.start_as_current_observation(
                as_type="generation",
                name="llm_call",
                model=self._model,
                input=[{"role": "user", "content": prompt}],
            ) as generation:
                update_kwargs: dict[str, Any] = {"output": response_content}

                if usage:
                    # Validate types at external boundary (Tier 3 data from LLM API)
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                        update_kwargs["usage_details"] = {
                            "input": prompt_tokens,
                            "output": completion_tokens,
                        }

                if latency_ms is not None:
                    update_kwargs["metadata"] = {"latency_ms": latency_ms}

                generation.update(**update_kwargs)
    except Exception as e:
        # No Silent Failures: emit telemetry event for trace failure
        ctx.telemetry_emit({
            "event": "langfuse_trace_failed",
            "plugin": self.name,
            "error": str(e),
        })
        import structlog
        logger = structlog.get_logger(__name__)
        logger.warning("Failed to record Langfuse trace", error=str(e))
```

**Call site change:**
```python
# Before (v2):
with self._create_langfuse_trace(token_id, row) as trace:
    response = llm_client.chat_completion(...)
    if trace is not None:
        self._record_langfuse_generation(trace, prompt, response.content, model, usage, latency_ms)

# After (v3):
response = llm_client.chat_completion(...)
self._record_langfuse_trace(ctx, token_id, prompt, response.content, response.usage, latency_ms)
```

**Acceptance Criteria:**
- [ ] Single method replaces two-method pattern
- [ ] Uses v3 nested context managers
- [ ] Error handling emits telemetry event (No Silent Failures)
- [ ] Error handling logs warning (telemetry-is-not-critical-path)
- [ ] Usage dict types validated at boundary
- [ ] Constructor uses `tracing_enabled` parameter
- [ ] All tests pass

### Task 4: Update azure_batch.py

**Current:** Direct `trace()` + `span()` calls for job-level tracing (line 325)

**Target:** Same pattern as Task 3 - nested context managers in a single method.

**Acceptance Criteria:**
- [ ] Uses v3 nested context managers
- [ ] Batch-level metadata preserved
- [ ] Error handling emits telemetry event
- [ ] Tests pass

### Task 5: Update azure_multi_query.py

Same refactor as Task 3.

**Acceptance Criteria:**
- [ ] Single method with nested context managers
- [ ] Per-query traces work correctly
- [ ] Error handling emits telemetry event
- [ ] Tests pass

### Task 6: Update openrouter.py

Same refactor as Task 3.

**Acceptance Criteria:**
- [ ] Uses v3 patterns
- [ ] OpenRouter-specific metadata preserved
- [ ] Error handling emits telemetry event
- [ ] Tests pass

### Task 7: Update openrouter_batch.py

Same pattern as Task 4.

**Acceptance Criteria:**
- [ ] Uses v3 patterns
- [ ] Error handling emits telemetry event
- [ ] Tests pass

### Task 8: Update openrouter_multi_query.py

Same refactor as Task 3.

**Acceptance Criteria:**
- [ ] Uses v3 patterns
- [ ] Error handling emits telemetry event
- [ ] Tests pass

### Task 9: Update Test Mocks

**Files:** All 4 test files in `tests/plugins/llm/`

**Changes:** Update mock to return v3-compatible context manager objects.

```python
@pytest.fixture
def mock_langfuse_client() -> MagicMock:
    """Create mock Langfuse client that captures v3 API calls."""
    captured_observations: list[dict[str, Any]] = []

    mock_client = MagicMock()

    @contextmanager
    def mock_start_observation(**kwargs):
        """Mock start_as_current_observation - called on CLIENT, not on observation."""
        obs = MagicMock()
        obs.captured_kwargs = kwargs
        obs.update_calls = []
        obs.update = lambda **uk: obs.update_calls.append(uk)
        captured_observations.append({"kwargs": kwargs, "updates": obs.update_calls})
        yield obs

    # Both span and generation use the same client method
    mock_client.start_as_current_observation = mock_start_observation
    mock_client.captured_observations = captured_observations
    mock_client.flush = MagicMock()
    return mock_client


@pytest.fixture
def mock_langfuse_client_that_raises() -> MagicMock:
    """Mock client that raises during context manager entry."""
    mock_client = MagicMock()

    @contextmanager
    def mock_start_observation_raises(**kwargs):
        raise ConnectionError("Langfuse API unavailable")
        yield  # Never reached

    mock_client.start_as_current_observation = mock_start_observation_raises
    return mock_client


@pytest.fixture
def mock_langfuse_client_update_raises() -> MagicMock:
    """Mock client where update() raises."""
    mock_client = MagicMock()

    @contextmanager
    def mock_start_observation(**kwargs):
        obs = MagicMock()
        obs.update = MagicMock(side_effect=RuntimeError("Update failed"))
        yield obs

    mock_client.start_as_current_observation = mock_start_observation
    return mock_client
```

**Acceptance Criteria:**
- [ ] Mocks support v3 context manager pattern (both span and generation use same client method)
- [ ] Tests verify correct `start_as_current_observation` calls with `as_type`
- [ ] Tests verify `update()` called with correct parameters
- [ ] Tests verify exception during context entry is handled gracefully
- [ ] Tests verify exception during `update()` is handled gracefully
- [ ] Tests verify telemetry event emitted on failure

### Task 10: Integration Testing

Verify complete tracing flow:

**Happy Paths:**
1. Azure LLM → Langfuse span + generation
2. OpenRouter → Langfuse span + generation
3. Batch transforms → Per-batch span with per-row generations
4. Multi-query → Per-row span with per-query generations
5. Flush on close → All traces sent before shutdown

**Error Recovery Paths:**
6. Langfuse API unavailable → Transform continues, telemetry event emitted
7. Exception during `start_as_current_observation` → Transform continues, warning logged
8. Exception during `generation.update()` → Span still closes, transform continues
9. Partial trace completion → Outer span closes even if inner fails
10. Network timeout during trace → Transform not blocked (non-critical path)

**Thread Safety:**
11. Concurrent rows in batch plugin → Each row gets isolated trace context

**Acceptance Criteria:**
- [ ] All happy-path integration tests pass
- [ ] All error recovery tests pass
- [ ] Thread safety test passes with 20+ concurrent rows
- [ ] Manual verification with real Langfuse (optional)

### Task 11: Documentation Update

**File:** `docs/guides/tier2-tracing.md`

Update examples to show v3 patterns and note the upgrade.

**Changes:**
1. Update code examples to v3 context manager pattern
2. Document version requirements (Langfuse SDK v3.12+)
3. Add breaking change notice
4. Update correlation workflow (W3C Trace Context IDs, use metadata.token_id for lookup)

**Acceptance Criteria:**
- [ ] Examples show v3 context manager patterns
- [ ] Version requirements documented
- [ ] Breaking change noted
- [ ] Correlation workflow updated

## Execution Order

```
Task 1 (pyproject.toml) ─────────────────────────┐
      ↓                                          │
Task 2 (config)                                  │
      ↓                                          │
  ┌───┴────────────────────────────────┐         │
  ↓                                    ↓         │
Task 3 (azure.py)              Task 9 (test mocks)
  ↓
Task 4 (azure_batch.py)
  ↓
Task 5 (azure_multi_query.py)
  ↓
Task 6 (openrouter.py)
  ↓
Task 7 (openrouter_batch.py)
  ↓
Task 8 (openrouter_multi_query.py)
  ↓
Task 10 (integration tests)
  ↓
Task 11 (documentation)
```

## Estimated Effort

| Task | Effort | Dependencies |
|------|--------|--------------|
| Task 1 | 5 min | None |
| Task 2 | 15 min | Task 1 |
| Tasks 3-8 | 20 min each (2 hours total) | Task 2 |
| Task 9 | 1 hour | Task 2 |
| Task 10 | 1.5 hours | Tasks 3-9 |
| Task 11 | 30 min | Tasks 3-9 |

**Total:** ~5-6 hours

## Rollback Procedure

If Langfuse v3 causes production issues after deployment:

### Quick Rollback (< 5 min)

```bash
# 1. Revert the commit
git revert <commit-hash>

# 2. Reinstall v2 SDK
uv pip install 'langfuse>=2.50,<3'

# 3. Verify
python -c "import langfuse; print(langfuse.__version__)"
# Should show 2.x.x
```

### Verification

After rollback, run integration tests to confirm v2 patterns work:

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py -v
```

## Behavioral Changes

### Trace Lifecycle

| Scenario | v2 Behavior | v3 Behavior |
|----------|-------------|-------------|
| LLM call succeeds | Trace created, generation recorded | Same |
| LLM call fails before trace | Trace exists but incomplete | No trace created (tracing happens after call) |
| Langfuse API unavailable | Warning logged | Warning logged + telemetry event emitted |

The v3 behavioral change (no trace on LLM failure) is acceptable because:
1. Failed LLM calls are recorded in the Landscape audit trail (source of truth)
2. Tier 2 tracing is operational visibility, not legal record
3. Telemetry event is still emitted for observability

### Correlation Workflow

v3 uses W3C Trace Context IDs instead of custom observation IDs. To correlate:

1. **Old way (v2):** Search by observation ID in Langfuse UI
2. **New way (v3):** Search by `metadata.token_id` in Langfuse UI

## Sources

- [Langfuse SDK Overview](https://langfuse.com/docs/observability/sdk/overview)
- [Python SDK v2 to v3 Migration Guide](https://langfuse.com/docs/observability/sdk/python/upgrade-path)
- [Python SDK v3 Generally Available Announcement](https://langfuse.com/changelog/2025-06-05-python-sdk-v3-generally-available)
- [OTEL-based Python SDK Discussion](https://github.com/orgs/langfuse/discussions/6993)
- [OpenTelemetry Integration Guide](https://langfuse.com/guides/cookbook/otel_integration_python_sdk)
