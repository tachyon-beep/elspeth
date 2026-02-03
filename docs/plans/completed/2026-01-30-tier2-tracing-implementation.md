# Tier 2 Plugin Tracing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement plugin-internal tracing support for Azure AI (Application Insights) and Langfuse, enabling deep LLM observability beyond Tier 1 framework telemetry.

**Architecture:** Plugins optionally configure their own tracing providers. The framework provides configuration patterns and lifecycle hooks, but no abstraction over provider SDKs. Plugins bring their own dependencies and initialize in `on_start()`.

**Tech Stack:** Python, Pydantic (config), azure-monitor-opentelemetry (Azure AI distro), langfuse (Langfuse), structlog (logging)

**Status:** Ready for implementation (reviewed 2026-02-03, gaps addressed)

**Plugins in Scope:**
| Plugin | Tracing Support | Notes |
|--------|----------------|-------|
| `AzureLLMTransform` | ✅ Full | Azure AI + Langfuse |
| `AzureMultiQueryLLMTransform` | ✅ Full | Azure AI + Langfuse |
| `OpenRouterLLMTransform` | ✅ Langfuse only | Azure AI auto-instrumentation requires OpenAI SDK |
| `OpenRouterMultiQueryLLMTransform` | ✅ Langfuse only | Azure AI auto-instrumentation requires OpenAI SDK |
| `AzureBatchLLMTransform` | ⚠️ Limited | Batch API - per-call tracing not possible (see Task 8) |
| `OpenRouterBatchLLMTransform` | ✅ Langfuse only | Synchronous parallel calls (see Task 8) |

---

## Design Philosophy

From the telemetry design document:

> The framework provides **nothing** for plugin-internal tracing. Plugins are T1 code and handle their own integrations.

This means:
- **No framework abstraction** over provider SDKs
- **No framework configuration** for plugin telemetry (it lives in plugin `options:`)
- **Plugins are autonomous** — they bring their own dependencies and config
- **Convention, not enforcement** — we document patterns, not mandate them

---

## Tier 1 vs Tier 2 Comparison

| Aspect | Tier 1 (Framework) | Tier 2 (Plugin) |
|--------|-------------------|-----------------|
| **Scope** | All external calls | LLM calls only |
| **Data captured** | Hashes, latency, status | Full prompts, responses, token details |
| **Destination** | Generic observability (Datadog, etc.) | LLM-specific platforms (Langfuse, Azure AI) |
| **Configuration** | `telemetry:` section | Plugin's `options.tracing:` section |
| **Who implements** | Framework | Each plugin individually |

Users can enable both:
- Tier 1 → Datadog/Grafana for ops visibility
- Tier 2 → Langfuse for prompt engineering analytics

---

## ⚠️ Important: Tier 1 / Tier 2 Interaction

### Potential Conflicts

When BOTH `telemetry:` (Tier 1) and `tracing:` (Tier 2) are enabled:

| Scenario | Conflict? | Resolution |
|----------|-----------|------------|
| Tier 1 OTLP + Tier 2 Azure AI | ⚠️ YES | Azure Monitor calls `configure_azure_monitor()` which may modify global OTEL config |
| Tier 1 Datadog + Tier 2 Azure AI | ⚠️ POSSIBLE | Both may install global tracers |
| Tier 1 ANY + Tier 2 Langfuse | ✅ NO | Langfuse uses its own client, no OTEL interaction |
| Tier 1 disabled + Tier 2 Azure AI | ✅ NO | Azure Monitor has full control |

### Implementation Strategy

1. **Check for existing OTEL configuration before calling `configure_azure_monitor()`**
2. **Log a warning if both Tier 1 OTLP and Tier 2 Azure AI are active**
3. **Recommend Langfuse for users who need both tiers** (no conflict)

### Multi-Plugin Scenario

When multiple LLM transforms in the same pipeline have different tracing configs:

| Transform A | Transform B | Behavior |
|-------------|-------------|----------|
| `azure_ai` | `azure_ai` | First one wins (Azure Monitor is process-level) |
| `azure_ai` | `langfuse` | Both work independently |
| `langfuse` | `langfuse` (different host) | Both work independently (separate clients) |
| `none` | `azure_ai` | Only Transform B traces |

**Rule:** Azure Monitor is process-global; Langfuse is per-instance. Plan accordingly.

---

## Task 1: Create Tracing Config Models

**Files:**
- Create: `src/elspeth/plugins/llm/tracing.py`
- Create: `tests/plugins/llm/test_tracing_config.py`

### Step 1.1: Write failing test for TracingConfig parsing

**File:** `tests/plugins/llm/test_tracing_config.py`

```python
# tests/plugins/llm/test_tracing_config.py
"""Tests for Tier 2 tracing configuration models."""

import pytest

from elspeth.plugins.llm.tracing import (
    AzureAITracingConfig,
    LangfuseTracingConfig,
    TracingConfig,
    parse_tracing_config,
    validate_tracing_config,
)


class TestTracingConfigParsing:
    """Tests for parse_tracing_config function."""

    def test_none_config_returns_none(self) -> None:
        """None input returns None."""
        result = parse_tracing_config(None)
        assert result is None

    def test_empty_dict_returns_base_config(self) -> None:
        """Empty dict returns base TracingConfig with provider='none'."""
        result = parse_tracing_config({})
        assert isinstance(result, TracingConfig)
        assert result.provider == "none"

    def test_azure_ai_provider_returns_azure_config(self) -> None:
        """Provider 'azure_ai' returns AzureAITracingConfig."""
        config = {
            "provider": "azure_ai",
            "connection_string": "InstrumentationKey=xxx",
            "enable_content_recording": True,
            "enable_live_metrics": False,
        }
        result = parse_tracing_config(config)

        assert isinstance(result, AzureAITracingConfig)
        assert result.provider == "azure_ai"
        assert result.connection_string == "InstrumentationKey=xxx"
        assert result.enable_content_recording is True
        assert result.enable_live_metrics is False

    def test_azure_ai_defaults(self) -> None:
        """AzureAITracingConfig has sensible defaults."""
        config = {"provider": "azure_ai"}
        result = parse_tracing_config(config)

        assert isinstance(result, AzureAITracingConfig)
        assert result.connection_string is None
        assert result.enable_content_recording is True  # Default: capture prompts
        assert result.enable_live_metrics is False  # Default: off

    def test_langfuse_provider_returns_langfuse_config(self) -> None:
        """Provider 'langfuse' returns LangfuseTracingConfig."""
        config = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
            "host": "https://self-hosted.example.com",
        }
        result = parse_tracing_config(config)

        assert isinstance(result, LangfuseTracingConfig)
        assert result.provider == "langfuse"
        assert result.public_key == "pk-xxx"
        assert result.secret_key == "sk-xxx"
        assert result.host == "https://self-hosted.example.com"

    def test_langfuse_defaults(self) -> None:
        """LangfuseTracingConfig has sensible defaults."""
        config = {"provider": "langfuse"}
        result = parse_tracing_config(config)

        assert isinstance(result, LangfuseTracingConfig)
        assert result.public_key is None
        assert result.secret_key is None
        assert result.host == "https://cloud.langfuse.com"  # Default: cloud

    def test_unknown_provider_returns_base_config(self) -> None:
        """Unknown provider returns base TracingConfig."""
        config = {"provider": "unknown_provider"}
        result = parse_tracing_config(config)

        assert isinstance(result, TracingConfig)
        assert result.provider == "unknown_provider"

    def test_none_provider_returns_base_config(self) -> None:
        """Provider 'none' returns base TracingConfig."""
        config = {"provider": "none"}
        result = parse_tracing_config(config)

        assert isinstance(result, TracingConfig)
        assert result.provider == "none"


class TestTracingConfigValidation:
    """Tests for validate_tracing_config function."""

    def test_azure_ai_without_connection_string_returns_error(self) -> None:
        """Azure AI without connection_string returns validation error."""
        config = AzureAITracingConfig(connection_string=None)
        errors = validate_tracing_config(config)
        assert len(errors) == 1
        assert "connection_string" in errors[0]

    def test_azure_ai_with_connection_string_returns_no_errors(self) -> None:
        """Azure AI with connection_string returns no errors."""
        config = AzureAITracingConfig(connection_string="InstrumentationKey=xxx")
        errors = validate_tracing_config(config)
        assert len(errors) == 0

    def test_langfuse_without_keys_returns_error(self) -> None:
        """Langfuse without public_key and secret_key returns validation error."""
        config = LangfuseTracingConfig(public_key=None, secret_key=None)
        errors = validate_tracing_config(config)
        assert len(errors) == 2
        assert any("public_key" in e for e in errors)
        assert any("secret_key" in e for e in errors)

    def test_langfuse_with_keys_returns_no_errors(self) -> None:
        """Langfuse with keys returns no errors."""
        config = LangfuseTracingConfig(public_key="pk-xxx", secret_key="sk-xxx")
        errors = validate_tracing_config(config)
        assert len(errors) == 0

    def test_none_provider_returns_no_errors(self) -> None:
        """Provider 'none' always valid."""
        config = TracingConfig(provider="none")
        errors = validate_tracing_config(config)
        assert len(errors) == 0
```

### Step 1.2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_tracing_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.plugins.llm.tracing'`

### Step 1.3: Create tracing config module

**File:** `src/elspeth/plugins/llm/tracing.py`

```python
# src/elspeth/plugins/llm/tracing.py
"""Tier 2 tracing configuration models for LLM plugins.

This module provides configuration dataclasses for plugin-internal tracing.
Each plugin that wants Tier 2 telemetry uses these to parse its tracing config.

Design Philosophy:
    The framework provides NOTHING for plugin-internal tracing. Plugins are
    autonomous - they bring their own SDK dependencies and configure their
    own observability. This module provides CONVENTIONS, not enforcement.

Supported Providers:
    - azure_ai: Azure Monitor / Application Insights (auto-instruments OpenAI SDK)
    - langfuse: Langfuse LLM observability platform (manual spans)
    - none: No tracing (default)

Example YAML Configuration:
    transforms:
      - plugin: azure_llm
        options:
          deployment_name: gpt-4
          endpoint: ${AZURE_OPENAI_ENDPOINT}
          api_key: ${AZURE_OPENAI_KEY}

          # Tier 2: Plugin-specific tracing (optional)
          # Use environment variables for secrets!
          tracing:
            provider: azure_ai
            connection_string: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
            enable_content_recording: true
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TracingConfig:
    """Base tracing configuration.

    Attributes:
        provider: Tracing provider identifier ('azure_ai', 'langfuse', 'none')
    """

    provider: str = "none"


@dataclass(frozen=True, slots=True)
class AzureAITracingConfig(TracingConfig):
    """Azure AI / Application Insights tracing configuration.

    Azure Monitor OpenTelemetry auto-instruments the OpenAI SDK, capturing:
    - Full prompts and responses (if enable_content_recording=True)
    - Token usage metrics
    - Latency and error rates
    - Custom dimensions for filtering

    WARNING: Azure Monitor is process-level. If multiple plugins configure
    azure_ai tracing, the first one to initialize wins.

    Attributes:
        provider: Always 'azure_ai'
        connection_string: Application Insights connection string
            (REQUIRED - use ${APPLICATIONINSIGHTS_CONNECTION_STRING} in YAML)
        enable_content_recording: Whether to capture full prompts/responses
            (default: True - enables prompt debugging)
        enable_live_metrics: Whether to enable Live Metrics Stream
            (default: False - adds overhead)
    """

    provider: str = "azure_ai"
    connection_string: str | None = None
    enable_content_recording: bool = True
    enable_live_metrics: bool = False


@dataclass(frozen=True, slots=True)
class LangfuseTracingConfig(TracingConfig):
    """Langfuse tracing configuration.

    Langfuse provides LLM-specific observability:
    - Prompt engineering analytics
    - Cost tracking and attribution
    - Evaluation scores and feedback
    - A/B testing for prompts

    Langfuse uses per-instance clients, so multiple plugins can have
    different Langfuse configurations (e.g., different hosts).

    Attributes:
        provider: Always 'langfuse'
        public_key: Langfuse public API key (REQUIRED - use ${LANGFUSE_PUBLIC_KEY})
        secret_key: Langfuse secret API key (REQUIRED - use ${LANGFUSE_SECRET_KEY})
        host: Langfuse host URL (default: cloud.langfuse.com)
    """

    provider: str = "langfuse"
    public_key: str | None = None
    secret_key: str | None = None
    host: str = "https://cloud.langfuse.com"


def parse_tracing_config(config: dict[str, Any] | None) -> TracingConfig | None:
    """Parse tracing configuration from dict.

    Args:
        config: Tracing configuration dict from plugin options,
            or None if tracing is not configured.

    Returns:
        Appropriate TracingConfig subclass based on provider,
        or None if config is None.

    Example:
        >>> config = {"provider": "langfuse", "host": "https://my.langfuse.com"}
        >>> result = parse_tracing_config(config)
        >>> isinstance(result, LangfuseTracingConfig)
        True
    """
    if config is None:
        return None

    provider = config.get("provider", "none")

    match provider:
        case "azure_ai":
            return AzureAITracingConfig(
                connection_string=config.get("connection_string"),
                enable_content_recording=config.get("enable_content_recording", True),
                enable_live_metrics=config.get("enable_live_metrics", False),
            )
        case "langfuse":
            return LangfuseTracingConfig(
                public_key=config.get("public_key"),
                secret_key=config.get("secret_key"),
                host=config.get("host", "https://cloud.langfuse.com"),
            )
        case _:
            return TracingConfig(provider=provider)


def validate_tracing_config(config: TracingConfig) -> list[str]:
    """Validate tracing configuration completeness.

    Args:
        config: Parsed tracing configuration

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    if isinstance(config, AzureAITracingConfig):
        if config.connection_string is None:
            errors.append(
                "azure_ai tracing requires connection_string. "
                "Use ${APPLICATIONINSIGHTS_CONNECTION_STRING} in YAML."
            )

    elif isinstance(config, LangfuseTracingConfig):
        if config.public_key is None:
            errors.append(
                "langfuse tracing requires public_key. "
                "Use ${LANGFUSE_PUBLIC_KEY} in YAML."
            )
        if config.secret_key is None:
            errors.append(
                "langfuse tracing requires secret_key. "
                "Use ${LANGFUSE_SECRET_KEY} in YAML."
            )

    return errors
```

### Step 1.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_tracing_config.py -v`

Expected: All PASS

### Step 1.5: Commit

```bash
git add src/elspeth/plugins/llm/tracing.py tests/plugins/llm/test_tracing_config.py
git commit -m "$(cat <<'EOF'
feat(telemetry): add Tier 2 tracing config models

- TracingConfig base class
- AzureAITracingConfig for Azure Monitor integration
- LangfuseTracingConfig for Langfuse integration
- parse_tracing_config() factory function
- validate_tracing_config() for completeness checking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Optional Dependencies

**Files:**
- Modify: `pyproject.toml`

### Step 2.1: Add tracing optional dependencies

**File:** `pyproject.toml`

Add after the `azure = [...]` section (around line 101):

```toml
tracing-azure = [
    # Tier 2: Azure AI tracing for LLM plugins
    # Uses the "distro" package which bundles OpenTelemetry instrumentations
    # Note: May conflict with Tier 1 OTLP telemetry - see docs/guides/tier2-tracing.md
    # Ref: https://pypi.org/project/azure-monitor-opentelemetry/
    "azure-monitor-opentelemetry>=1.6,<2",  # Azure Monitor OpenTelemetry Distro
]

tracing-langfuse = [
    # Tier 2: Langfuse tracing for LLM plugins
    # No conflicts with Tier 1 telemetry - recommended for dual-tier setups
    # Version 2.50+ required for stable trace() context manager API
    # Ref: https://langfuse.com/docs/sdk/python
    "langfuse>=2.50,<3",  # Langfuse SDK - v2.50+ has stable trace/generation API
]

tracing = [
    # All Tier 2 tracing providers
    "elspeth[tracing-azure,tracing-langfuse]",
]
```

### Step 2.2: Update the `all` optional dependency

Update the `all` section to include tracing:

```toml
all = [
    "elspeth[dev,llm,azure,mcp,tracing]",
]
```

### Step 2.3: Verify dependencies can be resolved

Run: `uv pip install -e ".[tracing-azure]" --dry-run`

Expected: Shows packages that would be installed (no errors)

Run: `uv pip install -e ".[tracing-langfuse]" --dry-run`

Expected: Shows packages that would be installed (no errors)

### Step 2.4: Commit

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
feat(deps): add optional dependencies for Tier 2 tracing

- tracing-azure: azure-monitor-opentelemetry
- tracing-langfuse: langfuse SDK
- tracing: all tracing providers

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add Tracing Config to AzureOpenAIConfig

**Files:**
- Modify: `src/elspeth/plugins/llm/azure.py`
- Create: `tests/plugins/llm/test_azure_tracing.py`

### Step 3.1: Write failing test for tracing config in AzureOpenAIConfig

**File:** `tests/plugins/llm/test_azure_tracing.py`

```python
# tests/plugins/llm/test_azure_tracing.py
"""Tests for Tier 2 tracing in AzureLLMTransform."""

import pytest

from elspeth.plugins.llm.azure import AzureOpenAIConfig


class TestAzureOpenAIConfigTracing:
    """Tests for tracing configuration in AzureOpenAIConfig."""

    def test_tracing_field_accepts_none(self) -> None:
        """Tracing field defaults to None (no tracing)."""
        config = AzureOpenAIConfig(
            deployment_name="gpt-4",
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            prompt_template="Hello",
        )
        assert config.tracing is None

    def test_tracing_field_accepts_azure_ai_config(self) -> None:
        """Tracing field accepts Azure AI configuration dict."""
        config = AzureOpenAIConfig(
            deployment_name="gpt-4",
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            prompt_template="Hello",
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
                "enable_content_recording": True,
            },
        )
        assert config.tracing is not None
        assert config.tracing["provider"] == "azure_ai"

    def test_tracing_field_accepts_langfuse_config(self) -> None:
        """Tracing field accepts Langfuse configuration dict."""
        config = AzureOpenAIConfig(
            deployment_name="gpt-4",
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            prompt_template="Hello",
            tracing={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            },
        )
        assert config.tracing is not None
        assert config.tracing["provider"] == "langfuse"
```

### Step 3.2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py::TestAzureOpenAIConfigTracing::test_tracing_field_accepts_none -v`

Expected: FAIL with `pydantic_core._pydantic_core.ValidationError: ... Extra inputs are not permitted` (tracing field not defined)

### Step 3.3: Add tracing field to AzureOpenAIConfig

**File:** `src/elspeth/plugins/llm/azure.py`

Add to imports (around line 14):

```python
from typing import TYPE_CHECKING, Any, Self
```

Add to `AzureOpenAIConfig` class (after `api_version` field, around line 57):

```python
    # Tier 2: Plugin-internal tracing (optional)
    # Use environment variables for secrets: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
    tracing: dict[str, Any] | None = Field(
        default=None,
        description="Tier 2 tracing configuration (azure_ai, langfuse, or none)",
    )
```

### Step 3.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py -v`

Expected: All PASS

### Step 3.5: Commit

```bash
git add src/elspeth/plugins/llm/azure.py tests/plugins/llm/test_azure_tracing.py
git commit -m "$(cat <<'EOF'
feat(azure): add tracing config field to AzureOpenAIConfig

Tier 2 plugin tracing configuration for Azure AI / Langfuse integration.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement Tracing Lifecycle in AzureLLMTransform

**Files:**
- Modify: `src/elspeth/plugins/llm/azure.py`
- Modify: `tests/plugins/llm/test_azure_tracing.py`

### Step 4.1: Write failing test for tracing initialization

**File:** `tests/plugins/llm/test_azure_tracing.py`

Add to the file:

```python
from unittest.mock import MagicMock, patch


class TestAzureLLMTransformTracing:
    """Tests for tracing lifecycle in AzureLLMTransform."""

    def _create_transform(self, tracing_config: dict | None = None) -> "AzureLLMTransform":
        """Create a transform with optional tracing config."""
        from elspeth.plugins.llm.azure import AzureLLMTransform

        config = {
            "deployment_name": "gpt-4",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "prompt_template": "Hello {{ name }}",
        }
        if tracing_config is not None:
            config["tracing"] = tracing_config

        return AzureLLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert transform._tracing_config is None
        assert transform._tracing_active is False

    def test_tracing_config_is_parsed(self) -> None:
        """Tracing config dict is parsed into TracingConfig."""
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, AzureAITracingConfig)

    def test_tracing_config_validation_errors_logged(self) -> None:
        """Missing required fields log warning during on_start."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                # Missing connection_string
            }
        )

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = MagicMock()
            ctx.landscape = MagicMock()

            transform.on_start(ctx)

            # Should have logged a warning about missing connection_string
            mock_logger.warning.assert_called()
            assert transform._tracing_active is False

    def test_azure_ai_tracing_setup_logs_warning_when_package_missing(self) -> None:
        """Azure AI tracing logs warning when package not installed."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )

        # Simulate ImportError by patching the import
        with patch.dict("sys.modules", {"azure.monitor.opentelemetry": None}):
            with patch("structlog.get_logger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                ctx = MagicMock()
                ctx.landscape = MagicMock()

                transform.on_start(ctx)

                # Should have logged a warning
                mock_logger.warning.assert_called()

    def test_tracing_active_flag_set_on_successful_setup(self) -> None:
        """_tracing_active is True after successful tracing setup."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )

        # Mock successful import and configure
        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True  # Success

            ctx = MagicMock()
            ctx.landscape = MagicMock()

            transform.on_start(ctx)

            # Verify configure was called
            mock_configure.assert_called_once()
            assert transform._tracing_active is True

    def test_langfuse_client_stored_on_successful_setup(self) -> None:
        """Langfuse client is stored for use in LLM calls."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )

        mock_langfuse = MagicMock()
        with patch("elspeth.plugins.llm.azure.Langfuse", return_value=mock_langfuse):
            ctx = MagicMock()
            ctx.landscape = MagicMock()

            transform.on_start(ctx)

            assert transform._tracing_active is True
            assert transform._langfuse_client is mock_langfuse
```

### Step 4.2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py::TestAzureLLMTransformTracing::test_no_tracing_when_config_is_none -v`

Expected: FAIL with `AttributeError: 'AzureLLMTransform' object has no attribute '_tracing_config'`

### Step 4.3: Add tracing initialization to AzureLLMTransform.__init__

**File:** `src/elspeth/plugins/llm/azure.py`

Add imports at top (add to existing imports section):

```python
from contextlib import contextmanager
from collections.abc import Generator

from elspeth.plugins.llm.tracing import (
    TracingConfig,
    LangfuseTracingConfig,
    AzureAITracingConfig,
    parse_tracing_config,
    validate_tracing_config,
)
```

Add to `__init__` method (after existing initialization, around line 175):

```python
        # Tier 2: Plugin-internal tracing
        self._tracing_config: TracingConfig | None = parse_tracing_config(
            cfg.tracing
        )
        self._tracing_active: bool = False
        self._langfuse_client: Any = None  # Langfuse client if configured
```

### Step 4.4: Add tracing setup to on_start

**File:** `src/elspeth/plugins/llm/azure.py`

Update the `on_start` method:

```python
    def on_start(self, ctx: PluginContext) -> None:
        """Capture recorder reference and initialize tracing.

        Called by the engine at pipeline start. Captures the landscape
        recorder reference and sets up Tier 2 tracing if configured.
        """
        self._recorder = ctx.landscape

        # Initialize Tier 2 tracing if configured
        if self._tracing_config is not None:
            self._setup_tracing()

    def _setup_tracing(self) -> None:
        """Initialize Tier 2 tracing based on provider.

        Tracing is optional - if the required SDK is not installed,
        we log a warning and continue without tracing.
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Validate configuration completeness
        errors = validate_tracing_config(self._tracing_config)
        if errors:
            for error in errors:
                logger.warning("Tracing configuration error", error=error)
            return  # Don't attempt setup with incomplete config

        match self._tracing_config.provider:
            case "azure_ai":
                self._setup_azure_ai_tracing(logger)
            case "langfuse":
                self._setup_langfuse_tracing(logger)
            case "none" | _:
                pass  # No tracing

    def _setup_azure_ai_tracing(self, logger: Any) -> None:
        """Initialize Azure AI / Application Insights tracing.

        Azure Monitor OpenTelemetry auto-instruments the OpenAI SDK.
        No manual instrumentation needed after configure_azure_monitor().

        WARNING: This is process-level configuration. Multiple plugins
        with azure_ai tracing will share the same configuration.
        """
        try:
            # Check for existing OTEL configuration that might conflict
            from opentelemetry import trace as otel_trace
            if otel_trace.get_tracer_provider().__class__.__name__ != "ProxyTracerProvider":
                logger.warning(
                    "Existing OpenTelemetry tracer detected - Azure AI tracing may conflict with Tier 1 telemetry",
                    existing_provider=otel_trace.get_tracer_provider().__class__.__name__,
                )

            success = _configure_azure_monitor(self._tracing_config)
            if success:
                self._tracing_active = True
                cfg = self._tracing_config
                logger.info(
                    "Azure AI tracing initialized",
                    provider="azure_ai",
                    content_recording=cfg.enable_content_recording if isinstance(cfg, AzureAITracingConfig) else None,
                    live_metrics=cfg.enable_live_metrics if isinstance(cfg, AzureAITracingConfig) else None,
                )

        except ImportError:
            logger.warning(
                "Azure AI tracing requested but package not installed",
                provider="azure_ai",
                hint="Install with: uv pip install elspeth[tracing-azure]",
            )

    def _setup_langfuse_tracing(self, logger: Any) -> None:
        """Initialize Langfuse tracing.

        Langfuse requires manual span creation around LLM calls.
        The Langfuse client is stored for use in _execute_llm_call().
        """
        try:
            from langfuse import Langfuse

            cfg = self._tracing_config
            if not isinstance(cfg, LangfuseTracingConfig):
                return

            self._langfuse_client = Langfuse(
                public_key=cfg.public_key,
                secret_key=cfg.secret_key,
                host=cfg.host,
            )
            self._tracing_active = True

            logger.info(
                "Langfuse tracing initialized",
                provider="langfuse",
                host=cfg.host,
            )

        except ImportError:
            logger.warning(
                "Langfuse tracing requested but package not installed",
                provider="langfuse",
                hint="Install with: uv pip install elspeth[tracing-langfuse]",
            )


def _configure_azure_monitor(config: TracingConfig) -> bool:
    """Configure Azure Monitor (module-level to allow mocking).

    Returns True on success, False on failure.
    """
    from azure.monitor.opentelemetry import configure_azure_monitor

    if not isinstance(config, AzureAITracingConfig):
        return False

    configure_azure_monitor(
        connection_string=config.connection_string,
        enable_live_metrics=config.enable_live_metrics,
    )
    return True
```

### Step 4.5: Add tracing cleanup to close()

**File:** `src/elspeth/plugins/llm/azure.py`

Update the `close` method to flush tracing:

```python
    def close(self) -> None:
        """Release resources and flush tracing."""
        # Flush Tier 2 tracing if active
        if self._tracing_active:
            self._flush_tracing()

        # Shutdown batch processing infrastructure
        if self._batch_initialized:
            self.shutdown_batch_processing()

        self._recorder = None
        # Clear cached LLM clients
        with self._llm_clients_lock:
            self._llm_clients.clear()
        self._underlying_client = None
        self._langfuse_client = None

    def _flush_tracing(self) -> None:
        """Flush any pending tracing data."""
        import structlog

        logger = structlog.get_logger(__name__)

        # Langfuse needs explicit flush
        if self._langfuse_client is not None:
            try:
                self._langfuse_client.flush()
                logger.debug("Langfuse tracing flushed")
            except Exception as e:
                logger.warning("Failed to flush Langfuse tracing", error=str(e))

        # Azure Monitor handles its own batching/flushing
        # No explicit flush needed
```

### Step 4.6: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py -v`

Expected: All PASS

### Step 4.7: Run existing Azure LLM tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure.py -v`

Expected: All PASS (no regression)

### Step 4.8: Commit

```bash
git add src/elspeth/plugins/llm/azure.py tests/plugins/llm/test_azure_tracing.py
git commit -m "$(cat <<'EOF'
feat(azure): implement Tier 2 tracing lifecycle

- Parse tracing config in __init__
- Validate config completeness before setup
- Initialize tracing in on_start() (Azure AI or Langfuse)
- Check for Tier 1 OTEL conflicts before Azure AI setup
- Graceful degradation when SDK not installed
- Flush tracing in close()

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement Langfuse Span Creation for LLM Calls

**CRITICAL:** This task implements the actual tracing instrumentation that provides value.

**Files:**
- Modify: `src/elspeth/plugins/llm/azure.py`
- Modify: `tests/plugins/llm/test_azure_tracing.py`

### Step 5.1: Write failing test for Langfuse span creation

**File:** `tests/plugins/llm/test_azure_tracing.py`

Add to the file:

```python
class TestLangfuseSpanCreation:
    """Tests for Langfuse span creation around LLM calls."""

    def _create_transform_with_langfuse(self) -> tuple["AzureLLMTransform", MagicMock]:
        """Create transform with mocked Langfuse client."""
        from elspeth.plugins.llm.azure import AzureLLMTransform

        config = {
            "deployment_name": "gpt-4",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "prompt_template": "Hello {{ name }}",
            "tracing": {
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            },
        }
        transform = AzureLLMTransform(config)

        # Mock Langfuse client
        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value.__enter__ = MagicMock(return_value=mock_trace)
        mock_langfuse.trace.return_value.__exit__ = MagicMock(return_value=False)
        mock_trace.generation.return_value = mock_generation

        transform._langfuse_client = mock_langfuse
        transform._tracing_active = True

        return transform, mock_langfuse

    def test_langfuse_trace_created_for_llm_call(self) -> None:
        """Langfuse trace is created when making LLM call."""
        transform, mock_langfuse = self._create_transform_with_langfuse()

        # Simulate an LLM call with tracing
        with transform._create_langfuse_trace("test-token", {"name": "world"}) as trace:
            assert trace is not None

        # Verify trace was created
        mock_langfuse.trace.assert_called_once()

    def test_langfuse_generation_records_input_output(self) -> None:
        """Langfuse generation records prompt and response."""
        transform, mock_langfuse = self._create_transform_with_langfuse()

        mock_trace = MagicMock()
        mock_generation = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        mock_trace.generation.return_value = mock_generation

        # Record a generation
        transform._record_langfuse_generation(
            trace=mock_trace,
            prompt="Hello world",
            response_content="Hi there!",
            model="gpt-4",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

        # Verify generation was recorded with correct data
        mock_trace.generation.assert_called_once()
        call_kwargs = mock_trace.generation.call_args.kwargs
        assert call_kwargs["input"] == "Hello world"
        assert call_kwargs["output"] == "Hi there!"
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["usage"]["input"] == 10
        assert call_kwargs["usage"]["output"] == 5
```

### Step 5.2: Add Langfuse span creation methods

**File:** `src/elspeth/plugins/llm/azure.py`

Add these methods to the class:

```python
    @contextmanager
    def _create_langfuse_trace(
        self,
        token_id: str,
        row_data: dict[str, Any],
    ) -> Generator[Any, None, None]:
        """Create a Langfuse trace context for an LLM call.

        Args:
            token_id: Token ID for correlation
            row_data: Input row data (for metadata)

        Yields:
            Langfuse trace object, or None if tracing not active

        Example:
            with self._create_langfuse_trace(token_id, row) as trace:
                response = await self._call_llm(...)
                if trace:
                    self._record_langfuse_generation(trace, prompt, response, ...)
        """
        if not self._tracing_active or self._langfuse_client is None:
            yield None
            return

        if not isinstance(self._tracing_config, LangfuseTracingConfig):
            yield None
            return

        trace = self._langfuse_client.trace(
            name=f"elspeth.{self.name}",
            metadata={
                "token_id": token_id,
                "plugin": self.name,
                "deployment": self._config.deployment_name,
            },
        )
        try:
            yield trace
        finally:
            # Trace auto-closes, but we ensure it's ended
            pass

    def _record_langfuse_generation(
        self,
        trace: Any,
        prompt: str,
        response_content: str,
        model: str,
        usage: dict[str, int] | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Record an LLM generation in Langfuse.

        Args:
            trace: Langfuse trace object from _create_langfuse_trace
            prompt: The prompt sent to the LLM
            response_content: The response received
            model: Model/deployment name
            usage: Token usage dict with prompt_tokens/completion_tokens
            latency_ms: Call latency in milliseconds
        """
        if trace is None:
            return

        generation_kwargs: dict[str, Any] = {
            "name": "llm_call",
            "model": model,
            "input": prompt,
            "output": response_content,
        }

        if usage:
            generation_kwargs["usage"] = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

        if latency_ms is not None:
            generation_kwargs["metadata"] = {"latency_ms": latency_ms}

        trace.generation(**generation_kwargs)
```

### Step 5.3: Integrate Langfuse tracing into LLM call path

Find the method that makes the actual LLM call (likely `_execute_llm_call` or similar) and wrap it:

```python
    async def _execute_llm_call_with_tracing(
        self,
        token_id: str,
        row_data: dict[str, Any],
        prompt: str,
    ) -> LLMResponse:
        """Execute LLM call with Tier 2 tracing if configured.

        This wraps the actual LLM call with Langfuse instrumentation.
        Azure AI auto-instruments via OpenTelemetry, so no manual wrapping needed.
        """
        import time

        start_time = time.monotonic()

        with self._create_langfuse_trace(token_id, row_data) as trace:
            # Make the actual LLM call
            response = await self._execute_llm_call(prompt)

            # Record in Langfuse if tracing is active
            if trace is not None:
                latency_ms = (time.monotonic() - start_time) * 1000
                self._record_langfuse_generation(
                    trace=trace,
                    prompt=prompt,
                    response_content=response.content,
                    model=self._config.deployment_name,
                    usage=response.usage,
                    latency_ms=latency_ms,
                )

        return response
```

### Step 5.4: Run tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_tracing.py -v`

Expected: All PASS

### Step 5.5: Commit

```bash
git add src/elspeth/plugins/llm/azure.py tests/plugins/llm/test_azure_tracing.py
git commit -m "$(cat <<'EOF'
feat(azure): add Langfuse span creation for LLM calls

- _create_langfuse_trace() context manager
- _record_langfuse_generation() for recording prompt/response
- _execute_llm_call_with_tracing() integration wrapper
- Records token usage and latency in Langfuse

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add Tracing to AzureMultiQueryLLMTransform

**Files:**
- Modify: `src/elspeth/plugins/llm/azure_multi_query.py`

### Step 6.1: Add tracing field to config

Find the config class (likely `AzureMultiQueryConfig` or similar) and add:

```python
    # Tier 2: Plugin-internal tracing (optional)
    tracing: dict[str, Any] | None = Field(
        default=None,
        description="Tier 2 tracing configuration (azure_ai, langfuse, or none)",
    )
```

### Step 6.2: Add tracing initialization (same pattern as Task 4)

Copy the tracing initialization pattern from `AzureLLMTransform`:
- Parse config in `__init__`
- Validate in `on_start()`
- Setup tracing providers
- Add Langfuse span creation (Task 5 pattern)
- Flush in `close()`

### Step 6.3: Run existing tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_multi_query.py -v`

Expected: All PASS

### Step 6.4: Commit

```bash
git add src/elspeth/plugins/llm/azure_multi_query.py
git commit -m "$(cat <<'EOF'
feat(azure_multi_query): add Tier 2 tracing support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add Tracing to OpenRouter Plugins

**NOTE:** This task is REQUIRED (not optional). OpenRouter uses HTTP directly, so only Langfuse is supported (Azure AI auto-instrumentation requires the OpenAI SDK).

**Files:**
- Modify: `src/elspeth/plugins/llm/openrouter.py`
- Modify: `src/elspeth/plugins/llm/openrouter_multi_query.py`
- Create: `tests/plugins/llm/test_openrouter_tracing.py`

### Step 7.1: Write failing test for OpenRouter tracing config

**File:** `tests/plugins/llm/test_openrouter_tracing.py`

```python
# tests/plugins/llm/test_openrouter_tracing.py
"""Tests for Tier 2 tracing in OpenRouterLLMTransform."""

import pytest
from unittest.mock import MagicMock, patch

from elspeth.plugins.llm.openrouter import OpenRouterConfig, OpenRouterLLMTransform
from elspeth.plugins.llm.tracing import LangfuseTracingConfig


class TestOpenRouterConfigTracing:
    """Tests for tracing configuration in OpenRouterConfig."""

    def test_tracing_field_accepts_none(self) -> None:
        """Tracing field defaults to None (no tracing)."""
        config = OpenRouterConfig(
            model="anthropic/claude-3-opus",
            api_key="test-key",
            prompt_template="Hello {{ name }}",
        )
        assert config.tracing is None

    def test_tracing_field_accepts_langfuse_config(self) -> None:
        """Tracing field accepts Langfuse configuration dict."""
        config = OpenRouterConfig(
            model="anthropic/claude-3-opus",
            api_key="test-key",
            prompt_template="Hello {{ name }}",
            tracing={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            },
        )
        assert config.tracing is not None
        assert config.tracing["provider"] == "langfuse"


class TestOpenRouterLLMTransformTracing:
    """Tests for tracing lifecycle in OpenRouterLLMTransform."""

    def _create_transform(self, tracing_config: dict | None = None) -> OpenRouterLLMTransform:
        """Create a transform with optional tracing config."""
        config = {
            "model": "anthropic/claude-3-opus",
            "api_key": "test-key",
            "prompt_template": "Hello {{ name }}",
            "schema": {"mode": "observed"},
        }
        if tracing_config is not None:
            config["tracing"] = tracing_config

        return OpenRouterLLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert transform._tracing_config is None
        assert transform._tracing_active is False

    def test_azure_ai_tracing_rejected_with_warning(self) -> None:
        """Azure AI tracing logs warning and is not activated for OpenRouter."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = MagicMock()
            ctx.landscape = MagicMock()

            transform.on_start(ctx)

            # Should have logged a warning about unsupported provider
            mock_logger.warning.assert_called()
            assert transform._tracing_active is False

    def test_langfuse_tracing_initialized(self) -> None:
        """Langfuse tracing is properly initialized for OpenRouter."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )

        mock_langfuse = MagicMock()
        with patch("elspeth.plugins.llm.openrouter.Langfuse", return_value=mock_langfuse):
            ctx = MagicMock()
            ctx.landscape = MagicMock()

            transform.on_start(ctx)

            assert transform._tracing_active is True
            assert transform._langfuse_client is mock_langfuse
```

### Step 7.2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_openrouter_tracing.py::TestOpenRouterConfigTracing::test_tracing_field_accepts_none -v`

Expected: FAIL with `pydantic_core._pydantic_core.ValidationError: ... Extra inputs are not permitted`

### Step 7.3: Add tracing field to OpenRouterConfig

**File:** `src/elspeth/plugins/llm/openrouter.py`

Add to imports (at top):

```python
from elspeth.plugins.llm.tracing import (
    TracingConfig,
    LangfuseTracingConfig,
    parse_tracing_config,
    validate_tracing_config,
)
```

Add to `OpenRouterConfig` class (after `timeout_seconds` field):

```python
    # Tier 2: Plugin-internal tracing (optional)
    # NOTE: Only Langfuse is supported for OpenRouter.
    # Azure AI auto-instrumentation requires the OpenAI SDK, which OpenRouter doesn't use.
    tracing: dict[str, Any] | None = Field(
        default=None,
        description="Tier 2 tracing configuration (langfuse only - azure_ai not supported)",
    )
```

### Step 7.4: Add tracing initialization to OpenRouterLLMTransform.__init__

Add to `__init__` method (after existing initialization, around line 165):

```python
        # Tier 2: Plugin-internal tracing (Langfuse only for OpenRouter)
        self._tracing_config: TracingConfig | None = parse_tracing_config(
            cfg.tracing
        )
        self._tracing_active: bool = False
        self._langfuse_client: Any = None  # Langfuse client if configured
```

### Step 7.5: Add tracing setup to on_start

**File:** `src/elspeth/plugins/llm/openrouter.py`

Update the `on_start` method:

```python
    def on_start(self, ctx: PluginContext) -> None:
        """Capture recorder reference and initialize tracing.

        Called by the engine at pipeline start. Captures the landscape
        recorder reference and sets up Tier 2 tracing if configured.
        """
        self._recorder = ctx.landscape
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit
        self._limiter = ctx.limiter

        # Initialize Tier 2 tracing if configured
        if self._tracing_config is not None:
            self._setup_tracing()

    def _setup_tracing(self) -> None:
        """Initialize Tier 2 tracing (Langfuse only for OpenRouter).

        Azure AI auto-instrumentation is NOT supported because it requires
        the OpenAI SDK. OpenRouter uses direct HTTP calls via httpx.
        """
        import structlog

        logger = structlog.get_logger(__name__)

        # Validate configuration completeness
        errors = validate_tracing_config(self._tracing_config)
        if errors:
            for error in errors:
                logger.warning("Tracing configuration error", error=error)
            return  # Don't attempt setup with incomplete config

        match self._tracing_config.provider:
            case "azure_ai":
                logger.warning(
                    "Azure AI tracing not supported for OpenRouter - use Langfuse instead",
                    provider="azure_ai",
                    hint="Azure AI auto-instruments the OpenAI SDK; OpenRouter uses HTTP directly",
                )
                return
            case "langfuse":
                self._setup_langfuse_tracing(logger)
            case "none" | _:
                pass  # No tracing

    def _setup_langfuse_tracing(self, logger: Any) -> None:
        """Initialize Langfuse tracing.

        Langfuse requires manual span creation around HTTP calls.
        The Langfuse client is stored for use in _process_row().
        """
        try:
            from langfuse import Langfuse

            cfg = self._tracing_config
            if not isinstance(cfg, LangfuseTracingConfig):
                return

            self._langfuse_client = Langfuse(
                public_key=cfg.public_key,
                secret_key=cfg.secret_key,
                host=cfg.host,
            )
            self._tracing_active = True

            logger.info(
                "Langfuse tracing initialized",
                provider="langfuse",
                host=cfg.host,
            )

        except ImportError:
            logger.warning(
                "Langfuse tracing requested but package not installed",
                provider="langfuse",
                hint="Install with: uv pip install elspeth[tracing-langfuse]",
            )
```

### Step 7.6: Add Langfuse span creation methods

**File:** `src/elspeth/plugins/llm/openrouter.py`

Add these methods to the class:

```python
    @contextmanager
    def _create_langfuse_trace(
        self,
        token_id: str,
        row_data: dict[str, Any],
    ) -> Generator[Any, None, None]:
        """Create a Langfuse trace context for an HTTP call.

        Args:
            token_id: Token ID for correlation
            row_data: Input row data (for metadata)

        Yields:
            Langfuse trace object, or None if tracing not active
        """
        if not self._tracing_active or self._langfuse_client is None:
            yield None
            return

        if not isinstance(self._tracing_config, LangfuseTracingConfig):
            yield None
            return

        trace = self._langfuse_client.trace(
            name=f"elspeth.{self.name}",
            metadata={
                "token_id": token_id,
                "plugin": self.name,
                "model": self._model,
            },
        )
        try:
            yield trace
        finally:
            # Trace auto-closes, but we ensure it's ended
            pass

    def _record_langfuse_generation(
        self,
        trace: Any,
        prompt: str,
        response_content: str,
        model: str,
        usage: dict[str, int] | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Record an HTTP/LLM generation in Langfuse.

        Args:
            trace: Langfuse trace object from _create_langfuse_trace
            prompt: The prompt sent to the API
            response_content: The response received
            model: Model identifier
            usage: Token usage dict with prompt_tokens/completion_tokens
            latency_ms: Call latency in milliseconds
        """
        if trace is None:
            return

        generation_kwargs: dict[str, Any] = {
            "name": "llm_call",
            "model": model,
            "input": prompt,
            "output": response_content,
        }

        if usage:
            generation_kwargs["usage"] = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

        if latency_ms is not None:
            generation_kwargs["metadata"] = {"latency_ms": latency_ms}

        trace.generation(**generation_kwargs)
```

### Step 7.7: Integrate tracing into _process_row

**File:** `src/elspeth/plugins/llm/openrouter.py`

Modify `_process_row` to wrap the HTTP call with tracing. Add timing and span creation:

```python
    def _process_row(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        """Process a single row through OpenRouter API.

        Now includes Tier 2 tracing via Langfuse if configured.
        """
        import time

        # 1. Render template with row data (THEIR DATA - wrap)
        try:
            rendered = self._template.render_with_metadata(row)
        except TemplateError as e:
            # ... existing error handling ...
            return TransformResult.error(error_reason)

        # 2. Build request (existing code)
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": rendered.prompt})

        request_body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens:
            request_body["max_tokens"] = self._max_tokens

        # ... existing state_id check ...

        try:
            http_client = self._get_http_client(ctx.state_id)

            # === TRACING INTEGRATION START ===
            start_time = time.monotonic()
            token_id = ctx.token_id or "unknown"

            with self._create_langfuse_trace(token_id, row) as trace:
                # 4. Call OpenRouter API (EXTERNAL - wrap)
                try:
                    response = http_client.post(
                        "/chat/completions",
                        json=request_body,
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    # ... existing HTTP error handling ...
                    pass
                except httpx.RequestError as e:
                    raise NetworkError(f"Network error: {e}") from e

                # 5. Parse JSON response (EXTERNAL DATA - wrap)
                try:
                    data = response.json()
                except (ValueError, TypeError) as e:
                    # ... existing JSON error handling ...
                    pass

                # 6. Extract content from response (EXTERNAL DATA - wrap)
                try:
                    choices = data["choices"]
                    if not choices:
                        return TransformResult.error(...)
                    content = choices[0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    return TransformResult.error(...)

                usage = data.get("usage") or {}

                # Record in Langfuse if tracing is active
                if trace is not None:
                    latency_ms = (time.monotonic() - start_time) * 1000
                    self._record_langfuse_generation(
                        trace=trace,
                        prompt=rendered.prompt,
                        response_content=content,
                        model=data.get("model", self._model),
                        usage=usage,
                        latency_ms=latency_ms,
                    )
            # === TRACING INTEGRATION END ===

            # 7. Build output row (existing code)
            output = dict(row)
            # ... rest of existing code ...
            return TransformResult.success(output, ...)
        finally:
            # ... existing cleanup ...
```

### Step 7.8: Add tracing cleanup to close()

```python
    def close(self) -> None:
        """Release resources and flush tracing."""
        # Flush Tier 2 tracing if active
        if self._tracing_active and self._langfuse_client is not None:
            try:
                self._langfuse_client.flush()
            except Exception as e:
                import structlog
                structlog.get_logger(__name__).warning(
                    "Failed to flush Langfuse tracing", error=str(e)
                )

        # ... existing cleanup code ...
        self._langfuse_client = None
```

### Step 7.9: Apply same pattern to OpenRouterMultiQueryLLMTransform

**File:** `src/elspeth/plugins/llm/openrouter_multi_query.py`

Apply the same changes:
1. Add `tracing` field to config class
2. Add tracing initialization in `__init__`
3. Add `_setup_tracing()`, `_setup_langfuse_tracing()` methods
4. Add `_create_langfuse_trace()`, `_record_langfuse_generation()` methods
5. Wrap HTTP calls with tracing in the appropriate method
6. Flush in `close()`

### Step 7.10: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_openrouter_tracing.py -v`

Expected: All PASS

### Step 7.11: Run existing OpenRouter tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_openrouter*.py -v`

Expected: All PASS (no regression)

### Step 7.12: Commit

```bash
git add src/elspeth/plugins/llm/openrouter.py src/elspeth/plugins/llm/openrouter_multi_query.py tests/plugins/llm/test_openrouter_tracing.py
git commit -m "$(cat <<'EOF'
feat(openrouter): add Tier 2 tracing support (Langfuse only)

OpenRouter uses HTTP directly via httpx, so Azure AI auto-instrumentation
doesn't apply (it requires the OpenAI SDK). Langfuse manual spans provide
LLM observability with full prompt/response capture.

- Add tracing config field to OpenRouterConfig
- Reject azure_ai provider with helpful warning
- Implement Langfuse trace/generation recording
- Wrap _process_row HTTP calls with timing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add Tracing to Batch Plugins (Limited Scope)

**NOTE:** Batch plugins have fundamentally different execution models that limit tracing capabilities.

**Files:**
- Modify: `src/elspeth/plugins/llm/azure_batch.py`
- Modify: `src/elspeth/plugins/llm/openrouter_batch.py`

### Background: Why Batch Plugins Have Limited Tracing

| Plugin | Execution Model | Tracing Capability |
|--------|----------------|-------------------|
| `AzureBatchLLMTransform` | Async batch API (submit job → poll → download) | ⚠️ **Job-level only** - individual row tracing impossible |
| `OpenRouterBatchLLMTransform` | Synchronous parallel HTTP calls | ✅ **Per-call tracing** - Langfuse supported |

**AzureBatchLLMTransform limitation:** Azure's Batch API submits all requests in a JSONL file and processes them asynchronously. The actual LLM calls happen in Azure's infrastructure, not in our code. We can only trace:
- Batch job submission
- Batch job completion
- Result download

We CANNOT trace individual row processing because we don't control those calls.

### Step 8.1: Add job-level tracing to AzureBatchLLMTransform

**File:** `src/elspeth/plugins/llm/azure_batch.py`

Add tracing field to config:

```python
    # Tier 2: Plugin-internal tracing (optional)
    # NOTE: Azure Batch API only supports JOB-LEVEL tracing, not per-row tracing.
    # The actual LLM calls happen asynchronously in Azure's infrastructure.
    tracing: dict[str, Any] | None = Field(
        default=None,
        description="Tier 2 tracing configuration (job-level only for batch API)",
    )
```

Add job-level span in process():

```python
    def process(self, rows: list[dict[str, Any]], ctx: PluginContext) -> TransformResult:
        """Process batch of rows via Azure Batch API with job-level tracing."""
        import time

        start_time = time.monotonic()
        token_id = ctx.token_id or "batch"

        with self._create_langfuse_trace(token_id, {"row_count": len(rows)}) as trace:
            # ... existing batch processing code ...

            # On success, record the batch job as a single "generation"
            if trace is not None:
                latency_ms = (time.monotonic() - start_time) * 1000
                self._record_langfuse_batch_job(
                    trace=trace,
                    row_count=len(rows),
                    batch_id=batch_id,
                    latency_ms=latency_ms,
                )
```

Add batch-specific recording method:

```python
    def _record_langfuse_batch_job(
        self,
        trace: Any,
        row_count: int,
        batch_id: str,
        latency_ms: float,
    ) -> None:
        """Record a batch job completion in Langfuse.

        Unlike per-call tracing, this records the entire batch as one span.
        Individual row prompts/responses are NOT captured (they happen in Azure).
        """
        if trace is None:
            return

        trace.span(
            name="azure_batch_job",
            metadata={
                "batch_id": batch_id,
                "row_count": row_count,
                "latency_ms": latency_ms,
                "note": "Individual row tracing not available for Azure Batch API",
            },
        )
```

### Step 8.2: Add per-call tracing to OpenRouterBatchLLMTransform

**File:** `src/elspeth/plugins/llm/openrouter_batch.py`

OpenRouterBatchLLMTransform uses `ThreadPoolExecutor` to make parallel HTTP calls synchronously. Each call CAN be traced individually.

Add full Langfuse tracing (same pattern as OpenRouterLLMTransform):

```python
    # In _process_single_row() method - wrap each HTTP call
    def _process_single_row(
        self,
        row: dict[str, Any],
        row_index: int,
        ctx: PluginContext,
    ) -> tuple[int, dict[str, Any] | TransformErrorReason]:
        """Process a single row with Langfuse tracing."""
        import time

        start_time = time.monotonic()
        token_id = f"{ctx.token_id or 'batch'}_{row_index}"

        with self._create_langfuse_trace(token_id, row) as trace:
            # ... existing HTTP call code ...

            if trace is not None:
                latency_ms = (time.monotonic() - start_time) * 1000
                self._record_langfuse_generation(
                    trace=trace,
                    prompt=rendered.prompt,
                    response_content=content,
                    model=data.get("model", self._model),
                    usage=usage,
                    latency_ms=latency_ms,
                )
```

### Step 8.3: Run existing batch plugin tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_batch*.py tests/plugins/llm/test_openrouter_batch*.py -v`

Expected: All PASS

### Step 8.4: Commit

```bash
git add src/elspeth/plugins/llm/azure_batch.py src/elspeth/plugins/llm/openrouter_batch.py
git commit -m "$(cat <<'EOF'
feat(batch): add Tier 2 tracing to batch LLM plugins

- AzureBatchLLMTransform: Job-level tracing only (per-row not possible)
- OpenRouterBatchLLMTransform: Per-call Langfuse tracing

Note: Azure Batch API processes rows asynchronously in Azure's infrastructure,
so individual row tracing is not possible. OpenRouter batch uses synchronous
parallel HTTP calls, so full per-call tracing is supported.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Write Integration Tests (Renumbered from Task 8)

**Files:**
- Create: `tests/plugins/llm/test_tracing_integration.py`

### Step 8.1: Create integration test with mocked endpoints

```python
# tests/plugins/llm/test_tracing_integration.py
"""Integration tests for Tier 2 tracing with mocked endpoints."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import contextmanager


class TestLangfuseIntegration:
    """Integration tests for Langfuse tracing."""

    @pytest.fixture
    def mock_langfuse_client(self):
        """Create a mock Langfuse client that captures traces."""
        captured_traces = []
        captured_generations = []

        mock_client = MagicMock()

        def capture_trace(**kwargs):
            trace = MagicMock()
            captured_traces.append(kwargs)

            def capture_generation(**gen_kwargs):
                captured_generations.append(gen_kwargs)
                return MagicMock()

            trace.generation = capture_generation
            return trace

        mock_client.trace = capture_trace
        mock_client.captured_traces = captured_traces
        mock_client.captured_generations = captured_generations

        return mock_client

    def test_langfuse_captures_llm_call_end_to_end(self, mock_langfuse_client) -> None:
        """Langfuse captures complete LLM call with prompt, response, and usage."""
        from elspeth.plugins.llm.azure import AzureLLMTransform

        config = {
            "deployment_name": "gpt-4",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "prompt_template": "Classify: {{ text }}",
            "tracing": {
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            },
        }

        with patch("elspeth.plugins.llm.azure.Langfuse", return_value=mock_langfuse_client):
            transform = AzureLLMTransform(config)

            ctx = MagicMock()
            ctx.landscape = MagicMock()
            transform.on_start(ctx)

            # Simulate a trace
            with transform._create_langfuse_trace("token-123", {"text": "hello"}) as trace:
                transform._record_langfuse_generation(
                    trace=trace,
                    prompt="Classify: hello",
                    response_content="positive",
                    model="gpt-4",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    latency_ms=150.0,
                )

            # Verify trace was captured
            assert len(mock_langfuse_client.captured_traces) == 1
            assert mock_langfuse_client.captured_traces[0]["name"] == f"elspeth.{transform.name}"

            # Verify generation was captured
            assert len(mock_langfuse_client.captured_generations) == 1
            gen = mock_langfuse_client.captured_generations[0]
            assert gen["input"] == "Classify: hello"
            assert gen["output"] == "positive"
            assert gen["model"] == "gpt-4"
            assert gen["usage"]["input"] == 10
            assert gen["usage"]["output"] == 5


class TestAzureAIAutoInstrumentation:
    """Tests for Azure AI auto-instrumentation verification."""

    def test_azure_ai_configures_opentelemetry(self) -> None:
        """Azure AI calls configure_azure_monitor with correct parameters."""
        from elspeth.plugins.llm.azure import AzureLLMTransform

        config = {
            "deployment_name": "gpt-4",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "prompt_template": "Hello",
            "tracing": {
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=test-key",
                "enable_live_metrics": True,
            },
        }

        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True

            with patch("opentelemetry.trace.get_tracer_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.__class__.__name__ = "ProxyTracerProvider"
                mock_get_provider.return_value = mock_provider

                transform = AzureLLMTransform(config)
                ctx = MagicMock()
                ctx.landscape = MagicMock()
                transform.on_start(ctx)

                # Verify configure was called
                mock_configure.assert_called_once()
                assert transform._tracing_active is True

    def test_azure_ai_warns_on_existing_otel_provider(self) -> None:
        """Azure AI logs warning when OTEL already configured (Tier 1 conflict)."""
        from elspeth.plugins.llm.azure import AzureLLMTransform

        config = {
            "deployment_name": "gpt-4",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "prompt_template": "Hello",
            "tracing": {
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=test-key",
            },
        }

        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True

            with patch("opentelemetry.trace.get_tracer_provider") as mock_get_provider:
                # Simulate existing non-proxy provider (Tier 1 configured)
                mock_provider = MagicMock()
                mock_provider.__class__.__name__ = "TracerProvider"
                mock_get_provider.return_value = mock_provider

                with patch("structlog.get_logger") as mock_get_logger:
                    mock_logger = MagicMock()
                    mock_get_logger.return_value = mock_logger

                    transform = AzureLLMTransform(config)
                    ctx = MagicMock()
                    ctx.landscape = MagicMock()
                    transform.on_start(ctx)

                    # Verify warning was logged about conflict
                    mock_logger.warning.assert_called()
```

### Step 8.2: Run integration tests

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_tracing_integration.py -v`

Expected: All PASS

### Step 8.3: Commit

```bash
git add tests/plugins/llm/test_tracing_integration.py
git commit -m "$(cat <<'EOF'
test(tracing): add integration tests for Tier 2 tracing

- Langfuse end-to-end capture verification
- Azure AI configuration verification
- Tier 1/Tier 2 conflict detection test

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Write Documentation (Renumbered from Task 9)

**Files:**
- Create: `docs/guides/tier2-tracing.md`

### Step 10.1: Create documentation guide

**File:** `docs/guides/tier2-tracing.md`

```markdown
# Tier 2 Plugin Tracing Guide

Tier 2 tracing provides deep LLM observability beyond the framework's Tier 1 telemetry.
While Tier 1 captures latency, status, and content hashes for ALL external calls,
Tier 2 captures full prompts, responses, and token-level metrics for LLM calls specifically.

## Overview

| Aspect | Tier 1 (Framework) | Tier 2 (Plugin) |
|--------|-------------------|-----------------|
| Scope | All external calls | LLM calls only |
| Data | Hashes, latency, status | Full prompts, responses, tokens |
| Destination | Generic observability | LLM-specific platforms |
| Configuration | `telemetry:` section | Plugin `options.tracing:` |

## Supported Providers

### Real-Time Plugins

| Provider | Azure LLM | Azure MultiQuery | OpenRouter | OpenRouter MultiQuery |
|----------|-----------|------------------|------------|----------------------|
| Azure AI (App Insights) | ✅ | ✅ | ❌ | ❌ |
| Langfuse | ✅ | ✅ | ✅ | ✅ |

### Batch Plugins

| Provider | Azure Batch | OpenRouter Batch | Notes |
|----------|-------------|------------------|-------|
| Azure AI | ❌ | ❌ | Batch API doesn't use OpenAI SDK |
| Langfuse | ⚠️ Job-level | ✅ Per-call | Azure Batch = async in Azure infrastructure |

**Azure Batch Limitation:** The Azure Batch API submits requests as a JSONL file and processes them asynchronously in Azure's infrastructure. Individual row tracing is not possible because we don't control those calls. Only job-level spans (submit/complete) are recorded.

### Azure AI (Application Insights)

Azure Monitor OpenTelemetry auto-instruments the OpenAI SDK, capturing:
- Full prompts and responses
- Token usage metrics
- Latency and error rates

**Installation:**
```bash
uv pip install elspeth[tracing-azure]
```

**Configuration:**
```yaml
transforms:
  - plugin: azure_llm
    options:
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}
      prompt_template: "Classify: {{ text }}"

      # Tier 2 tracing - use env vars for secrets!
      tracing:
        provider: azure_ai
        connection_string: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
        enable_content_recording: true  # Capture full prompts
        enable_live_metrics: false       # Disable for lower overhead
```

### Langfuse

Langfuse provides LLM-specific observability:
- Prompt engineering analytics
- Cost tracking and attribution
- Evaluation scores

**Installation:**
```bash
uv pip install elspeth[tracing-langfuse]
```

**Configuration:**
```yaml
transforms:
  - plugin: azure_llm  # or openrouter
    options:
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}
      prompt_template: "Classify: {{ text }}"

      # Tier 2 tracing - use env vars for secrets!
      tracing:
        provider: langfuse
        public_key: ${LANGFUSE_PUBLIC_KEY}
        secret_key: ${LANGFUSE_SECRET_KEY}
        host: https://cloud.langfuse.com  # Or self-hosted URL
```

## Using Both Tiers Together

Tier 1 and Tier 2 are complementary. A typical production setup:

```yaml
# Tier 1: Framework telemetry → Datadog for ops
telemetry:
  enabled: true
  granularity: full
  exporters:
    - name: datadog
      options:
        service_name: "elspeth-pipeline"

# Tier 2: Plugin tracing → Langfuse for ML team
transforms:
  - plugin: azure_llm
    options:
      # ... LLM config ...
      tracing:
        provider: langfuse
        public_key: ${LANGFUSE_PUBLIC_KEY}
        secret_key: ${LANGFUSE_SECRET_KEY}
```

**Result:**
- Datadog shows all external call metrics (LLM + HTTP + DB)
- Langfuse shows detailed prompt/response data for LLM calls

### ⚠️ Tier 1 + Tier 2 Azure AI Conflict

If you use **both** Tier 1 OTLP telemetry AND Tier 2 Azure AI tracing, there may be conflicts:

| Tier 1 Exporter | Tier 2 Provider | Conflict? |
|-----------------|-----------------|-----------|
| Datadog | Azure AI | Possible |
| OTLP | Azure AI | **Yes** - both configure OpenTelemetry |
| Any | Langfuse | **No** - Langfuse is independent |

**Recommendation:** Use Langfuse for Tier 2 if you need both tiers.

## Multi-Plugin Scenarios

| Transform A | Transform B | Behavior |
|-------------|-------------|----------|
| `azure_ai` | `azure_ai` | First one wins (process-level) |
| `azure_ai` | `langfuse` | Both work |
| `langfuse` | `langfuse` | Both work (separate clients) |

## Graceful Degradation

If the tracing SDK is not installed, plugins log a warning and continue:

```
WARNING: Langfuse tracing requested but package not installed
         hint: Install with: uv pip install elspeth[tracing-langfuse]
```

If configuration is incomplete, plugins log the specific error:

```
WARNING: Tracing configuration error
         error: langfuse tracing requires secret_key. Use ${LANGFUSE_SECRET_KEY} in YAML.
```

## Privacy Considerations

Tier 2 tracing captures full prompts and responses. Consider:

1. **PII in prompts**: Use `enable_content_recording: false` for Azure AI
2. **Data residency**: Self-host Langfuse for sensitive data
3. **Compliance**: Review your organization's data handling policies

## Troubleshooting

### No traces appearing

1. Check connection string / API keys are set (use env vars!)
2. Verify the tracing SDK is installed
3. Check logs for initialization warnings
4. Verify `_tracing_active` is True after `on_start()`

### Azure AI traces missing token counts

Azure Monitor may not capture token usage for all API versions.
Ensure `api_version: 2024-10-21` or later.

### Langfuse traces delayed

Langfuse batches traces for efficiency. Traces are flushed when:
- `transform.close()` is called
- Pipeline completes
- Buffer fills (internal batching)

### "Existing OpenTelemetry tracer detected" warning

This warning appears when both Tier 1 and Tier 2 Azure AI are active.
Options:
1. Use Langfuse for Tier 2 instead (recommended)
2. Disable Tier 1 telemetry
3. Accept potential conflicts
```

### Step 10.2: Commit

```bash
git add docs/guides/tier2-tracing.md
git commit -m "$(cat <<'EOF'
docs: add Tier 2 tracing guide

Covers Azure AI and Langfuse configuration, Tier 1/Tier 2 interaction,
multi-plugin scenarios, and privacy considerations.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Run Full Test Suite and Type Checks (Renumbered from Task 10)

### Step 11.1: Run mypy on all tracing files

Run: `.venv/bin/python -m mypy src/elspeth/plugins/llm/tracing.py src/elspeth/plugins/llm/azure.py src/elspeth/plugins/llm/azure_multi_query.py src/elspeth/plugins/llm/azure_batch.py src/elspeth/plugins/llm/openrouter.py src/elspeth/plugins/llm/openrouter_multi_query.py src/elspeth/plugins/llm/openrouter_batch.py`

Expected: No errors

### Step 11.2: Run ruff on all tracing files

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/llm/`

Expected: No errors

### Step 11.3: Run full test suite

Run: `.venv/bin/python -m pytest tests/ -v --tb=short`

Expected: All PASS

### Step 11.4: Final commit (if any fixes needed)

```bash
git add -A
git commit -m "$(cat <<'EOF'
fix: address lint/type issues from Tier 2 tracing

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Checklist

### Core Infrastructure (Tasks 1-2)
- [ ] `TracingConfig` base class created
- [ ] `AzureAITracingConfig` with connection_string, enable_content_recording, enable_live_metrics
- [ ] `LangfuseTracingConfig` with public_key, secret_key, host
- [ ] `parse_tracing_config()` function handles all cases
- [ ] `validate_tracing_config()` checks required fields
- [ ] Optional dependencies in pyproject.toml (tracing-azure, tracing-langfuse)
- [ ] Package name verified: `azure-monitor-opentelemetry` (distro, not exporter)

### Azure Plugins (Tasks 3-6)
- [ ] `AzureOpenAIConfig.tracing` field added
- [ ] `AzureLLMTransform` initializes tracing in `on_start()`
- [ ] `AzureLLMTransform` validates config before setup
- [ ] `AzureLLMTransform` checks for Tier 1 OTEL conflicts
- [ ] `AzureLLMTransform` creates Langfuse spans for LLM calls
- [ ] `AzureLLMTransform` flushes tracing in `close()`
- [ ] Graceful degradation when SDK not installed (warning, not crash)
- [ ] `AzureMultiQueryLLMTransform` has same tracing support

### OpenRouter Plugins (Task 7)
- [ ] `OpenRouterConfig.tracing` field added
- [ ] `OpenRouterLLMTransform` has Langfuse support
- [ ] `OpenRouterLLMTransform` rejects Azure AI with warning
- [ ] `OpenRouterMultiQueryLLMTransform` has Langfuse support

### Batch Plugins (Task 8)
- [ ] `AzureBatchLLMTransform` has job-level tracing (per-row not possible)
- [ ] `OpenRouterBatchLLMTransform` has per-call Langfuse tracing
- [ ] Batch plugin limitations documented in code comments

### Testing & Documentation (Tasks 9-11)
- [ ] Integration tests verify end-to-end tracing
- [ ] OpenRouter-specific tracing tests created
- [ ] Documentation covers Tier 1/Tier 2 interaction
- [ ] Documentation covers multi-plugin scenarios
- [ ] Documentation covers batch plugin limitations
- [ ] All existing tests pass
- [ ] mypy clean
- [ ] ruff clean

---

## Summary of Changes

| File | Change |
|------|--------|
| `src/elspeth/plugins/llm/tracing.py` | New - config models + validation |
| `src/elspeth/plugins/llm/azure.py` | Add tracing field, lifecycle, and Langfuse spans |
| `src/elspeth/plugins/llm/azure_multi_query.py` | Add tracing field and lifecycle |
| `src/elspeth/plugins/llm/azure_batch.py` | Add job-level tracing (limited) |
| `src/elspeth/plugins/llm/openrouter.py` | Add Langfuse tracing support |
| `src/elspeth/plugins/llm/openrouter_multi_query.py` | Add Langfuse tracing support |
| `src/elspeth/plugins/llm/openrouter_batch.py` | Add per-call Langfuse tracing |
| `pyproject.toml` | Add tracing optional dependencies |
| `tests/plugins/llm/test_tracing_config.py` | New - config + validation tests |
| `tests/plugins/llm/test_azure_tracing.py` | New - lifecycle + span tests |
| `tests/plugins/llm/test_openrouter_tracing.py` | New - OpenRouter tracing tests |
| `tests/plugins/llm/test_tracing_integration.py` | New - integration tests |
| `docs/guides/tier2-tracing.md` | New - user documentation |

---

## Effort Estimate

| Task | Effort |
|------|--------|
| Task 1: Config models | 0.5 days |
| Task 2: Dependencies | 0.25 days |
| Task 3: Config field | 0.25 days |
| Task 4: Lifecycle | 0.5 days |
| Task 5: Langfuse spans (CRITICAL) | 0.5 days |
| Task 6: Multi-query | 0.5 days |
| Task 7: OpenRouter (expanded) | 0.75 days |
| Task 8: Batch plugins (new) | 0.5 days |
| Task 9: Integration tests | 0.5 days |
| Task 10: Documentation | 0.25 days |
| Task 11: Final checks | 0.25 days |
| **Total** | **4.75 days** |
