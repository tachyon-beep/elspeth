# Azure AI Tracing Silent No-Op Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire existing `_configure_azure_monitor()` into the unified LLM transform so `tracing: {provider: azure_ai}` actually enables Azure Monitor tracing instead of silently doing nothing.

**Architecture:** `LLMTransform.__init__()` stores the parsed `TracingConfig` as a typed instance field. `on_start()` calls `_configure_azure_monitor()` for `AzureAITracingConfig`. A validation check in `__init__()` rejects `azure_ai` tracing with non-Azure providers. `create_langfuse_tracer()` stops warning for Azure AI configs (tracing is active, just not via Langfuse). `_configure_azure_monitor()` gets ImportError handling and an idempotency guard.

**Tech Stack:** Azure Monitor OpenTelemetry (`azure-monitor-opentelemetry`), `AzureAITracingConfig` dataclass, `_configure_azure_monitor()` from `providers/azure.py`.

**Issue:** elspeth-rapid-cf10a5

---

### Task 0: Harden `_configure_azure_monitor()` — ImportError + idempotency

**Files:**
- Modify: `src/elspeth/plugins/llm/providers/azure.py:233-269`
- Test: `tests/unit/plugins/llm/test_transform.py`

**Step 1: Write the failing tests**

In `tests/unit/plugins/llm/test_transform.py`, add a test class `TestConfigureAzureMonitor`:

```python
class TestConfigureAzureMonitor:
    """Tests for _configure_azure_monitor hardening."""

    def test_returns_false_when_azure_monitor_sdk_not_installed(self) -> None:
        """_configure_azure_monitor returns False (not ImportError) when SDK missing."""
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch(
            "elspeth.plugins.llm.providers.azure.configure_azure_monitor",
            side_effect=ImportError("No module named 'azure.monitor.opentelemetry'"),
        ):
            from elspeth.plugins.llm.providers.azure import _configure_azure_monitor

            result = _configure_azure_monitor(config)
            assert result is False

    def test_idempotency_second_call_returns_true_without_reconfiguring(self) -> None:
        """Second call to _configure_azure_monitor returns True without calling SDK again."""
        from elspeth.plugins.llm.providers.azure import (
            _configure_azure_monitor,
            _reset_azure_monitor_state,
        )
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        _reset_azure_monitor_state()  # Ensure clean state
        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch(
            "elspeth.plugins.llm.providers.azure.configure_azure_monitor",
        ) as mock_sdk:
            # First call — configures
            result1 = _configure_azure_monitor(config)
            assert result1 is True
            assert mock_sdk.call_count == 1

            # Second call — idempotent, skips SDK
            result2 = _configure_azure_monitor(config)
            assert result2 is True
            assert mock_sdk.call_count == 1  # NOT called again

        _reset_azure_monitor_state()  # Clean up

    def test_idempotency_logs_warning_on_second_call(self) -> None:
        """Second call logs a warning about duplicate initialization."""
        from elspeth.plugins.llm.providers.azure import (
            _configure_azure_monitor,
            _reset_azure_monitor_state,
        )
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        _reset_azure_monitor_state()
        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch("elspeth.plugins.llm.providers.azure.configure_azure_monitor"):
            _configure_azure_monitor(config)

            with patch("elspeth.plugins.llm.providers.azure.logger") as mock_logger:
                _configure_azure_monitor(config)
                mock_logger.warning.assert_called_once()

        _reset_azure_monitor_state()
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestConfigureAzureMonitor -xvs`
Expected: FAIL — `_reset_azure_monitor_state` doesn't exist, ImportError not caught

**Step 3: Write minimal implementation**

In `src/elspeth/plugins/llm/providers/azure.py`, add module-level state and modify `_configure_azure_monitor()`:

```python
# Module-level idempotency guard — Azure Monitor is process-global.
_azure_monitor_configured: bool = False


def _reset_azure_monitor_state() -> None:
    """Reset module state for testing only."""
    global _azure_monitor_configured
    _azure_monitor_configured = False


def _configure_azure_monitor(config: TracingConfig) -> bool:
    """Configure Azure Monitor (module-level to allow mocking).

    Returns True on success, False on failure.
    Idempotent: second call logs a warning and returns True.
    """
    global _azure_monitor_configured

    if not isinstance(config, AzureAITracingConfig):
        return False

    if _azure_monitor_configured:
        logger.warning(
            "Azure Monitor already configured — skipping duplicate initialization",
        )
        return True

    try:
        from azure.monitor.opentelemetry import (
            configure_azure_monitor,  # type: ignore[import-not-found,import-untyped,attr-defined]  # optional dep: azure-monitor-opentelemetry
        )
    except ImportError:
        logger.warning(
            "azure-monitor-opentelemetry is not installed — Azure AI tracing inactive",
            hint="Install with: uv pip install 'elspeth[azure]'",
        )
        return False

    configure_azure_monitor(
        connection_string=config.connection_string,
        enable_live_metrics=config.enable_live_metrics,
    )

    # Wire enable_content_recording to the Azure AI Inference tracing SDK.
    # Without this, the config field is accepted and logged but never applied,
    # leaving operators with a false sense of their content recording policy.
    try:
        from azure.ai.inference.tracing import AIInferenceInstrumentor  # type: ignore[import-not-found,import-untyped]  # optional dep

        AIInferenceInstrumentor().instrument(enable_content_recording=config.enable_content_recording)
    except ImportError:
        # azure-ai-inference not installed — fall back to environment variable
        # which the OpenAI SDK instrumentor reads at trace emission time.
        import os

        logger.warning(
            "azure-ai-inference not installed — falling back to environment variable for content recording",
            hint="Install azure-ai-inference for full tracing support",
            fallback_env_var="AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        )
        os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = str(config.enable_content_recording).lower()

    _azure_monitor_configured = True
    return True
```

Key changes from original:
- Import moved inside try/except — `ImportError` returns `False` with clear message
- Module-level `_azure_monitor_configured` guard prevents duplicate initialization
- `_reset_azure_monitor_state()` for test isolation
- `_azure_monitor_configured = True` set AFTER successful configuration

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestConfigureAzureMonitor -xvs`
Expected: 3 PASS

**Step 5: Commit**

```
git add src/elspeth/plugins/llm/providers/azure.py tests/unit/plugins/llm/test_transform.py
git commit -m "fix: _configure_azure_monitor ImportError handling + idempotency guard"
```

---

### Task 1: Refine `create_langfuse_tracer()` warning

**Files:**
- Modify: `src/elspeth/plugins/llm/langfuse.py:229-236`
- Test: `tests/unit/plugins/llm/test_transform.py`

**Step 1: Write the failing test**

In `tests/unit/plugins/llm/test_transform.py`, add a test class `TestAzureAITracingSetup`:

```python
class TestAzureAITracingSetup:
    """Tests for Azure AI tracing integration in unified LLM transform."""

    def test_langfuse_factory_no_warning_for_azure_ai_config(self) -> None:
        """create_langfuse_tracer returns NoOp without warning for AzureAITracingConfig.

        Azure AI tracing is handled separately in on_start(), so the Langfuse
        factory should not warn about it being 'unrecognized'.
        """
        from elspeth.plugins.llm.langfuse import create_langfuse_tracer, NoOpLangfuseTracer
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch("elspeth.plugins.llm.langfuse.logger") as mock_logger:
            tracer = create_langfuse_tracer("test_transform", config)
            assert isinstance(tracer, NoOpLangfuseTracer)
            mock_logger.warning.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup::test_langfuse_factory_no_warning_for_azure_ai_config -xvs`
Expected: FAIL — `mock_logger.warning.assert_not_called()` fails because the current code warns for all non-Langfuse configs.

**Step 3: Write minimal implementation**

In `src/elspeth/plugins/llm/langfuse.py`, modify `create_langfuse_tracer()` to import `AzureAITracingConfig` and skip the warning for it:

```python
def create_langfuse_tracer(
    transform_name: str,
    tracing_config: TracingConfig | None,
) -> LangfuseTracer:
    if tracing_config is None:
        return NoOpLangfuseTracer()
    if not isinstance(tracing_config, LangfuseTracingConfig):
        # Azure AI tracing is handled in LLMTransform.on_start() — no warning needed.
        # Only warn for truly unrecognized providers (e.g. typo in config).
        if not isinstance(tracing_config, AzureAITracingConfig):
            logger.warning(
                "Tracing config provided but not recognized as Langfuse or Azure AI — tracing disabled",
                tracing_provider=tracing_config.provider,
            )
        return NoOpLangfuseTracer()
    # ... rest unchanged (Langfuse client creation)
```

Add import at top of file: `from elspeth.plugins.llm.tracing import AzureAITracingConfig, LangfuseTracingConfig, TracingConfig`
(already imports `LangfuseTracingConfig` and `TracingConfig`, just add `AzureAITracingConfig`)

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup -xvs`
Expected: PASS

**Step 5: Add companion test — warning preserved for unknown provider**

```python
    def test_langfuse_factory_warns_for_unknown_tracing_provider(self) -> None:
        """create_langfuse_tracer warns when tracing provider is unrecognized.

        Note: In production, parse_tracing_config() rejects unknown providers
        before this point. This tests the factory's own defensive behavior.
        """
        from elspeth.plugins.llm.langfuse import create_langfuse_tracer, NoOpLangfuseTracer
        from elspeth.plugins.llm.tracing import TracingConfig

        config = TracingConfig(provider="totally_unknown")
        with patch("elspeth.plugins.llm.langfuse.logger") as mock_logger:
            tracer = create_langfuse_tracer("test_transform", config)
            assert isinstance(tracer, NoOpLangfuseTracer)
            mock_logger.warning.assert_called_once()
```

**Step 6: Run both tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup -xvs`
Expected: 2 PASS

**Step 7: Commit**

```
git add src/elspeth/plugins/llm/langfuse.py tests/unit/plugins/llm/test_transform.py
git commit -m "fix: langfuse factory stops warning for AzureAITracingConfig"
```

---

### Task 2: Validate provider/tracing compatibility in `__init__()`

**Files:**
- Modify: `src/elspeth/plugins/llm/transform.py:816` (after `parse_tracing_config`)
- Test: `tests/unit/plugins/llm/test_transform.py`

**Step 1: Write the failing test**

```python
    def test_azure_ai_tracing_rejected_for_openrouter_provider(self) -> None:
        """azure_ai tracing with openrouter provider raises ValueError at init.

        Azure Monitor auto-instruments the OpenAI SDK. OpenRouter uses httpx
        directly, so Azure AI tracing would silently do nothing.
        """
        config = _make_config(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-key",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        with pytest.raises(ValueError, match="azure_ai tracing.*azure provider"):
            LLMTransform(config)

    def test_azure_ai_tracing_accepted_for_azure_provider(self) -> None:
        """azure_ai tracing with azure provider does not raise."""
        config = _make_config(
            provider="azure",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        # Should not raise
        transform = LLMTransform(config)
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, AzureAITracingConfig)
```

Note: the second test also validates **F5** — `_tracing_config` field is accessible after `__init__`.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup::test_azure_ai_tracing_rejected_for_openrouter_provider -xvs`
Expected: FAIL — no ValueError raised

**Step 3: Write minimal implementation**

In `src/elspeth/plugins/llm/transform.py`, after line 816 (`tracing_config = parse_tracing_config(...)`) and before line 817 (`self._tracer = create_langfuse_tracer(...)`), add:

```python
        # Validate provider/tracing compatibility — azure_ai tracing auto-instruments
        # the OpenAI SDK, which only the Azure provider uses. Fail loud, not silent.
        if isinstance(tracing_config, AzureAITracingConfig) and not isinstance(self._config, AzureOpenAIConfig):
            raise ValueError(
                "azure_ai tracing requires the azure provider. "
                "Azure Monitor auto-instruments the OpenAI SDK, which is only used by provider='azure'. "
                f"Current provider: '{self._config.provider}'"
            )
```

Also store the parsed config as a typed instance field (declare near other instance fields):

```python
        self._tracing_config: TracingConfig | None = tracing_config
```

This goes BEFORE the validation check (so it's always assigned, even on the None path), satisfying mypy that `on_start()` can always access it.

Add import at top: `from elspeth.plugins.llm.tracing import AzureAITracingConfig, parse_tracing_config`
(already imports `parse_tracing_config`, just add `AzureAITracingConfig`)

**Step 4: Run tests to verify**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup -xvs`
Expected: 4 PASS (2 from Task 1 + 2 new)

**Step 5: Commit**

```
git add src/elspeth/plugins/llm/transform.py tests/unit/plugins/llm/test_transform.py
git commit -m "fix: reject azure_ai tracing with non-Azure providers at config time"
```

---

### Task 3: Call `_configure_azure_monitor()` in `on_start()`

**Files:**
- Modify: `src/elspeth/plugins/llm/transform.py:898-908` (`on_start` method)
- Test: `tests/unit/plugins/llm/test_transform.py`

**Step 1: Write the failing tests**

All tests use the existing `_make_ctx()` helper (extended as needed) instead of raw `Mock()`.

```python
    def test_on_start_calls_configure_azure_monitor(self) -> None:
        """on_start() calls _configure_azure_monitor for AzureAITracingConfig."""
        config = _make_config(
            provider="azure",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        transform = LLMTransform(config)

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = None
        ctx.telemetry_emit = Mock()
        ctx.node_id = "node-1"
        ctx.payload_store = None
        ctx.concurrency_config = None

        with patch(
            "elspeth.plugins.llm.transform._configure_azure_monitor", return_value=True,
        ) as mock_configure:
            transform.on_start(ctx)

            mock_configure.assert_called_once()
            call_arg = mock_configure.call_args.args[0]
            assert isinstance(call_arg, AzureAITracingConfig)
            assert call_arg.connection_string == "InstrumentationKey=test"

    def test_on_start_configure_azure_monitor_failure_logs_warning(self) -> None:
        """on_start() logs warning when _configure_azure_monitor returns False."""
        config = _make_config(
            provider="azure",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        transform = LLMTransform(config)

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = None
        ctx.telemetry_emit = Mock()
        ctx.node_id = "node-1"
        ctx.payload_store = None
        ctx.concurrency_config = None

        with patch(
            "elspeth.plugins.llm.transform._configure_azure_monitor", return_value=False,
        ), patch(
            "elspeth.plugins.llm.transform.logger",
        ) as mock_logger:
            transform.on_start(ctx)
            mock_logger.warning.assert_called_once()

    def test_on_start_skips_azure_monitor_for_langfuse(self) -> None:
        """on_start() does NOT call _configure_azure_monitor for Langfuse tracing."""
        config = _make_config(
            provider="azure",
            tracing={"provider": "langfuse", "public_key": "pk", "secret_key": "sk"},
        )
        # Langfuse client creation will fail (no real server), but we mock the tracer
        with patch("elspeth.plugins.llm.transform.create_langfuse_tracer"):
            transform = LLMTransform(config)

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = None
        ctx.telemetry_emit = Mock()
        ctx.node_id = "node-1"
        ctx.payload_store = None
        ctx.concurrency_config = None

        with patch(
            "elspeth.plugins.llm.transform._configure_azure_monitor",
        ) as mock_configure:
            transform.on_start(ctx)
            mock_configure.assert_not_called()

    def test_on_start_skips_azure_monitor_when_no_tracing(self) -> None:
        """on_start() does NOT call _configure_azure_monitor when tracing is None."""
        config = _make_config(provider="azure")
        transform = LLMTransform(config)

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = None
        ctx.telemetry_emit = Mock()
        ctx.node_id = "node-1"
        ctx.payload_store = None
        ctx.concurrency_config = None

        with patch(
            "elspeth.plugins.llm.transform._configure_azure_monitor",
        ) as mock_configure:
            transform.on_start(ctx)
            mock_configure.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup::test_on_start_calls_configure_azure_monitor -xvs`
Expected: FAIL — `_configure_azure_monitor` not called / not imported in transform.py

**Step 3: Write minimal implementation**

In `src/elspeth/plugins/llm/transform.py`, add import:

```python
from elspeth.plugins.llm.providers.azure import _configure_azure_monitor
```

In `on_start()` method, after `self._provider = self._create_provider()` (line 908), add:

```python
        # Initialize Azure AI tracing (process-level OpenTelemetry auto-instrumentation).
        # Must happen after provider creation — the OpenAI SDK must be available.
        if isinstance(self._tracing_config, AzureAITracingConfig):
            success = _configure_azure_monitor(self._tracing_config)
            if success:
                logger.info(
                    "Azure AI tracing initialized",
                    provider="azure_ai",
                    content_recording=self._tracing_config.enable_content_recording,
                )
            else:
                logger.warning("Azure AI tracing setup failed — tracing inactive")
```

**Step 4: Run all TestAzureAITracingSetup tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_transform.py::TestAzureAITracingSetup tests/unit/plugins/llm/test_transform.py::TestConfigureAzureMonitor -xvs`
Expected: 10 PASS (3 from Task 0 + 2 from Task 1 + 2 from Task 2 + 3 new + 1 failure test)

**Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/ -x -q --timeout=60`
Expected: All pass

**Step 6: Run mypy, ruff, hooks**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/llm/transform.py src/elspeth/plugins/llm/langfuse.py src/elspeth/plugins/llm/providers/azure.py`
Run: `.venv/bin/python -m ruff check src/elspeth/plugins/llm/transform.py src/elspeth/plugins/llm/langfuse.py src/elspeth/plugins/llm/providers/azure.py`

**Step 7: Commit**

```
git add src/elspeth/plugins/llm/transform.py tests/unit/plugins/llm/test_transform.py
git commit -m "fix(cf10a5): wire Azure AI tracing into unified LLM transform on_start()"
```

---

### Task 4: Close issue and final verification

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x -q --timeout=120`
Expected: All 10,100+ pass

**Step 2: Run all quality gates**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/llm/transform.py src/elspeth/plugins/llm/langfuse.py src/elspeth/plugins/llm/providers/azure.py`
Run: `.venv/bin/python -m ruff check src/elspeth/plugins/llm/transform.py src/elspeth/plugins/llm/langfuse.py src/elspeth/plugins/llm/providers/azure.py`

**Step 3: Close filigree issue**

```
filigree close elspeth-rapid-cf10a5 --reason="Azure AI tracing wired into LLMTransform.on_start(), provider validation added, langfuse warning refined, _configure_azure_monitor hardened with ImportError handling and idempotency guard"
```
