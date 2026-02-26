# Azure AI Tracing Silent No-Op Fix

**Date:** 2026-02-27
**Issue:** elspeth-rapid-cf10a5
**Status:** Approved

## Problem

`LLMTransform` accepts `tracing: {provider: azure_ai}` config, parses it into
`AzureAITracingConfig`, then silently discards it. `create_langfuse_tracer()`
returns `NoOpLangfuseTracer` for non-Langfuse configs. Users configure Azure AI
tracing, validation passes, but no traces are emitted. Violates No Silent
Failures.

## Solution

Wire `_configure_azure_monitor()` (already exists at `providers/azure.py:233`)
into the unified transform's `on_start()` lifecycle. Add provider validation so
`azure_ai` tracing is rejected for non-Azure LLM providers at config time.

## Changes

### 1. `LLMTransform.on_start()` — Azure Monitor setup

Call `_configure_azure_monitor()` when tracing config is `AzureAITracingConfig`.
Process-level setup (auto-instruments OpenAI SDK via OpenTelemetry). Goes in
`on_start()` not `__init__()` to keep init side-effect-free.

### 2. `LLMTransform.__init__()` — provider/tracing compatibility validation

Raise `ValueError` if tracing provider is `azure_ai` but LLM provider is not
`azure`. Azure Monitor auto-instrumentation only captures OpenAI SDK calls —
useless with OpenRouter's httpx client.

### 3. `langfuse.py:create_langfuse_tracer()` — refine warning

Currently warns "tracing disabled" for `AzureAITracingConfig`. Wrong — tracing
IS active via Azure Monitor, just not through Langfuse. Only warn for truly
unrecognized configs.

### 4. Tests

- `on_start()` calls `_configure_azure_monitor()` for `AzureAITracingConfig`
- `_configure_azure_monitor()` NOT called for Langfuse/no-tracing configs
- `azure_ai` tracing with `provider: openrouter` raises `ValueError`
- Warning gone for Azure AI, preserved for unknown providers

## Files

| File | Change |
|------|--------|
| `src/elspeth/plugins/llm/transform.py` | `on_start()` setup + `__init__()` validation |
| `src/elspeth/plugins/llm/langfuse.py` | Refine warning scope |
| `tests/unit/plugins/llm/test_transform.py` | 4-5 new tests |

## Not Changing

- `_configure_azure_monitor()` — already correct
- `tracing.py` config parsing — already works
- `AzureAITracingConfig` dataclass — already complete
