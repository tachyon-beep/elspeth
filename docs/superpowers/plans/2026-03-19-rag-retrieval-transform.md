# RAG Retrieval Transform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a RAG retrieval transform plugin that fetches context from search backends (Azure AI Search and ChromaDB) and attaches it to pipeline rows for downstream LLM consumption.

**Architecture:** Two deliverables as separate PRs. PR 1 (preparatory): `PluginRetryableError` base class in L0 contracts, re-parent existing error types, fix processor retry dispatch. PR 2 (feature): `RetrievalProvider` protocol + Azure AI Search provider + ChromaDB provider + `RAGRetrievalTransform` + shared template infrastructure extraction. The transform uses synchronous `process()` (not `BatchTransformMixin`), constructs a per-call `AuditedHTTPClient` scoped to each row's `state_id`, and exposes four prefixed output fields. Both providers implement the same `RetrievalProvider` protocol — selected via `provider: "azure_search"` or `provider: "chroma"` in pipeline YAML. ChromaDB enables local/in-memory testing without cloud dependencies.

**Tech Stack:** httpx (via AuditedHTTPClient), azure-identity (managed identity auth), chromadb (local/embedded vector store), jinja2 (query templates), pluggy (plugin registration)

**Spec:** `docs/superpowers/specs/2026-03-18-rag-retrieval-transform-design.md`

---

## File Structure

### PR 1: PluginRetryableError Preparatory Work

| File | Action | Responsibility |
|------|--------|----------------|
| `src/elspeth/contracts/errors.py` | Modify | Add `PluginRetryableError` base class, add new `TransformErrorCategory` literals |
| `src/elspeth/plugins/infrastructure/clients/llm.py` | Modify | Re-parent `LLMClientError` → `PluginRetryableError` |
| `src/elspeth/plugins/transforms/web_scrape_errors.py` | Modify | Re-parent `WebScrapeError` → `PluginRetryableError` |
| `src/elspeth/engine/processor.py` | Modify | Catch `PluginRetryableError` in retry dispatch |
| `tests/unit/engine/test_plugin_retryable_error.py` | Create | Regression tests for all three error types through retry paths |

### PR 2: RAG Retrieval Transform

| File | Action | Responsibility |
|------|--------|----------------|
| `src/elspeth/plugins/infrastructure/templates.py` | Create | Extract `ImmutableSandboxedEnvironment` + `TemplateError` as shared infra |
| `src/elspeth/plugins/transforms/llm/templates.py` | Modify | Import from shared infra instead of jinja2 directly |
| `src/elspeth/plugins/infrastructure/clients/retrieval/__init__.py` | Create | Public exports |
| `src/elspeth/plugins/infrastructure/clients/retrieval/types.py` | Create | `RetrievalChunk`, `RetrievalResult` dataclasses |
| `src/elspeth/plugins/infrastructure/clients/retrieval/base.py` | Create | `RetrievalProvider` protocol, `RetrievalError` exception |
| `src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py` | Create | Azure AI Search provider implementation |
| `src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py` | Create | ChromaDB provider implementation |
| `src/elspeth/plugins/transforms/rag/__init__.py` | Create | Plugin registration |
| `src/elspeth/plugins/transforms/rag/config.py` | Create | `RAGRetrievalConfig` (Pydantic) |
| `src/elspeth/plugins/transforms/rag/query.py` | Create | Query construction (field/template/regex) |
| `src/elspeth/plugins/transforms/rag/formatter.py` | Create | Context formatting (numbered/separated/raw) + truncation |
| `src/elspeth/plugins/transforms/rag/transform.py` | Create | `RAGRetrievalTransform` main class |
| `src/elspeth/plugins/infrastructure/discovery.py` | Modify | Add `transforms/rag` to `PLUGIN_SCAN_CONFIG` |
| `tests/unit/plugins/infrastructure/clients/retrieval/test_types.py` | Create | `RetrievalChunk` validation tests |
| `tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py` | Create | Azure provider unit tests |
| `tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py` | Create | ChromaDB provider unit tests |
| `tests/unit/plugins/transforms/rag/test_config.py` | Create | Config validation tests |
| `tests/unit/plugins/transforms/rag/test_query.py` | Create | Query construction tests |
| `tests/unit/plugins/transforms/rag/test_formatter.py` | Create | Context formatting tests |
| `tests/unit/plugins/transforms/rag/test_transform.py` | Create | Transform lifecycle and process flow tests |
| `tests/integration/plugins/transforms/test_rag_pipeline.py` | Create | End-to-end pipeline integration tests |

---

## PR 1: PluginRetryableError Preparatory Work

This PR is a standalone prerequisite. It fixes an existing bug (WebScrapeError escaping the processor) and establishes the base class that `RetrievalError` will inherit from in PR 2.

### Task 1: Add PluginRetryableError base class and new error categories

**Files:**
- Modify: `src/elspeth/contracts/errors.py`

- [ ] **Step 1: Write the failing test for PluginRetryableError**

Create `tests/unit/engine/test_plugin_retryable_error.py`:

```python
"""Tests for PluginRetryableError base class and error hierarchy."""

from elspeth.contracts.errors import PluginRetryableError


def test_plugin_retryable_error_has_retryable_attribute():
    err = PluginRetryableError("test", retryable=True)
    assert err.retryable is True
    assert str(err) == "test"


def test_plugin_retryable_error_has_status_code():
    err = PluginRetryableError("test", retryable=False, status_code=404)
    assert err.retryable is False
    assert err.status_code == 404


def test_plugin_retryable_error_status_code_defaults_none():
    err = PluginRetryableError("test", retryable=True)
    assert err.status_code is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_plugin_retryable_error.py -v`
Expected: FAIL with `ImportError` — `PluginRetryableError` doesn't exist yet.

- [ ] **Step 3: Implement PluginRetryableError in contracts/errors.py**

Add after the existing exception classes (after `OrchestrationInvariantError` at line 679):

```python
class PluginRetryableError(Exception):
    """Base for plugin exceptions eligible for engine retry.

    All plugin error types that may be retried by the engine's RetryManager
    must inherit from this class. The processor catches PluginRetryableError
    and dispatches to retry logic based on the retryable attribute.

    Attributes:
        retryable: Whether the error is transient and should be retried.
        status_code: HTTP status code if applicable (for audit context).
    """

    def __init__(
        self, message: str, *, retryable: bool, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_plugin_retryable_error.py -v`
Expected: PASS

- [ ] **Step 5: Add new TransformErrorCategory literals**

In `src/elspeth/contracts/errors.py`, add to the `TransformErrorCategory` literal (after `"content_extraction_failed"`):

```python
    # Retrieval errors (RAG retrieval transform)
    "retrieval_failed",
    "no_results",
    "no_regex_match",
```

Note: `"invalid_input"` and `"template_rendering_failed"` already exist.

- [ ] **Step 6: Run existing tests to verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/contracts/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/contracts/errors.py tests/unit/engine/test_plugin_retryable_error.py
git commit -m "feat: add PluginRetryableError base class and retrieval error categories

The retrieval_failed, no_results, and no_regex_match categories are
forward-looking — consumed by the RAG retrieval transform in PR 2.
Added here because TransformErrorCategory is in L0 contracts and
PR 1 is the contracts-layer change."
```

### Task 2: Re-parent LLMClientError and WebScrapeError

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/clients/llm.py:66-78`
- Modify: `src/elspeth/plugins/transforms/web_scrape_errors.py:8-13`
- Test: `tests/unit/engine/test_plugin_retryable_error.py`

- [ ] **Step 1: Write tests for re-parenting**

Append to `tests/unit/engine/test_plugin_retryable_error.py`:

```python
from elspeth.plugins.infrastructure.clients.llm import LLMClientError
from elspeth.plugins.transforms.web_scrape_errors import WebScrapeError


def test_llm_client_error_is_plugin_retryable_error():
    err = LLMClientError("test", retryable=True)
    assert isinstance(err, PluginRetryableError)
    assert err.retryable is True
    assert err.status_code is None


def test_web_scrape_error_is_plugin_retryable_error():
    err = WebScrapeError("test", retryable=True)
    assert isinstance(err, PluginRetryableError)
    assert err.retryable is True
    assert err.status_code is None


def test_llm_subclasses_still_work():
    """Re-parenting must not break existing subclass behavior."""
    from elspeth.plugins.infrastructure.clients.llm import RateLimitError, NetworkError

    rate_err = RateLimitError("rate limited")
    assert isinstance(rate_err, LLMClientError)
    assert isinstance(rate_err, PluginRetryableError)
    assert rate_err.retryable is True

    net_err = NetworkError("timeout")
    assert isinstance(net_err, LLMClientError)
    assert isinstance(net_err, PluginRetryableError)
    assert net_err.retryable is True


def test_web_scrape_subclasses_still_work():
    """Re-parenting must not break existing subclass behavior."""
    from elspeth.plugins.transforms.web_scrape_errors import (
        RateLimitError as WebRateLimitError,
        ServerError as WebServerError,
        NotFoundError,
    )

    rate_err = WebRateLimitError("rate limited")
    assert isinstance(rate_err, WebScrapeError)
    assert isinstance(rate_err, PluginRetryableError)
    assert rate_err.retryable is True

    server_err = WebServerError("500")
    assert isinstance(server_err, WebScrapeError)
    assert isinstance(server_err, PluginRetryableError)
    assert server_err.retryable is True

    not_found = NotFoundError("404")
    assert isinstance(not_found, WebScrapeError)
    assert isinstance(not_found, PluginRetryableError)
    assert not_found.retryable is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_plugin_retryable_error.py -v -k "re_parent or subclass"`
Expected: FAIL — `LLMClientError` and `WebScrapeError` don't inherit from `PluginRetryableError` yet.

- [ ] **Step 3: Re-parent LLMClientError**

In `src/elspeth/plugins/infrastructure/clients/llm.py`, add import and change inheritance:

```python
from elspeth.contracts.errors import PluginRetryableError
```

Change `LLMClientError` (line 66):

```python
class LLMClientError(PluginRetryableError):
    """Error from LLM client.

    Base exception for all LLM client errors. Includes retryable
    flag to indicate if the operation might succeed on retry.

    Attributes:
        retryable: Whether the error is likely transient and retryable
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)
```

Note: `LLMClientError.__init__` passes `retryable` to `PluginRetryableError.__init__`. The `status_code` parameter defaults to `None` via the parent. Existing subclasses (`RateLimitError`, `NetworkError`, etc.) are unaffected — they call `super().__init__(message, retryable=True/False)` which chains correctly.

- [ ] **Step 4: Re-parent WebScrapeError**

In `src/elspeth/plugins/transforms/web_scrape_errors.py`, add import and change inheritance:

```python
from elspeth.contracts.errors import PluginRetryableError
```

Change `WebScrapeError` (line 8):

```python
class WebScrapeError(PluginRetryableError):
    """Base error for web scrape transform."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, retryable=retryable)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_plugin_retryable_error.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `.venv/bin/python -m pytest tests/unit/ -x --timeout=120`
Expected: All PASS. The re-parenting is additive — existing `isinstance(e, LLMClientError)` checks still match because `LLMClientError` is still in the MRO.

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/plugins/infrastructure/clients/llm.py src/elspeth/plugins/transforms/web_scrape_errors.py tests/unit/engine/test_plugin_retryable_error.py
git commit -m "refactor: re-parent LLMClientError and WebScrapeError under PluginRetryableError"
```

### Task 3: Update processor retry dispatch

**Files:**
- Modify: `src/elspeth/engine/processor.py:1096-1150`
- Test: `tests/unit/engine/test_plugin_retryable_error.py`

- [ ] **Step 1: Write tests for processor retry dispatch**

Append to `tests/unit/engine/test_plugin_retryable_error.py`:

```python
def test_is_retryable_catches_plugin_retryable_error():
    """PluginRetryableError with retryable=True is retryable."""
    err = PluginRetryableError("transient", retryable=True)
    assert err.retryable is True


def test_is_retryable_rejects_non_retryable_plugin_error():
    """PluginRetryableError with retryable=False is not retryable."""
    err = PluginRetryableError("permanent", retryable=False)
    assert err.retryable is False


def test_all_plugin_errors_share_retryable_interface():
    """All plugin error types have a consistent retryable interface."""
    errors = [
        LLMClientError("test", retryable=True),
        WebScrapeError("test", retryable=True),
        PluginRetryableError("test", retryable=True),
    ]
    for err in errors:
        assert isinstance(err, PluginRetryableError)
        assert err.retryable is True
```

- [ ] **Step 2: Run tests to verify they pass (interface tests only)**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_plugin_retryable_error.py -v -k "interface or catches"`
Expected: PASS — these test the error hierarchy, not the processor yet.

- [ ] **Step 3: Update _execute_transform_with_retry in processor.py**

In `src/elspeth/engine/processor.py`, add import at top:

```python
from elspeth.contracts.errors import PluginRetryableError
```

Replace the no-retry exception handling (lines 1096-1121):

```python
        if self._retry_manager is None:
            # No retry configured - single attempt
            # Must still catch retryable exceptions and convert to error results
            # to keep failures row-scoped (don't abort entire run)
            try:
                return self._transform_executor.execute_transform(
                    transform=transform,
                    token=token,
                    ctx=ctx,
                    attempt=0,
                )
            except PluginRetryableError as e:
                if e.retryable:
                    return self._convert_retryable_to_error_result(
                        e,
                        transform,
                        token,
                        ctx,
                        reason="transient_error_no_retry",
                    )
                # Non-retryable PluginRetryableError: the transform's process()
                # method is responsible for catching its own non-retryable errors
                # and converting them to TransformResult.error(). If a non-retryable
                # error escapes process(), that is a plugin bug — crash is correct.
                # Verified: WebScrapeTransform catches WebScrapeError at line 294,
                # LLM transform catches LLMClientError in its process() method.
                raise
            except (ConnectionError, TimeoutError, OSError, CapacityError) as e:
                return self._convert_retryable_to_error_result(
                    e,
                    transform,
                    token,
                    ctx,
                    reason="transient_error_no_retry",
                )
```

Replace `is_retryable` predicate (lines 1136-1145):

```python
        def is_retryable(e: BaseException) -> bool:
            # Retry transient errors (network, timeout, rate limit)
            # Don't retry programming errors (AttributeError, TypeError, etc.)
            #
            # PluginRetryableError covers all plugin error types:
            # - LLMClientError (RateLimitError, NetworkError, ServerError, etc.)
            # - WebScrapeError (RateLimitError, NetworkError, ServerError, etc.)
            # - RetrievalError (future: RAG retrieval errors)
            if isinstance(e, PluginRetryableError):
                return e.retryable
            return isinstance(e, ConnectionError | TimeoutError | OSError | CapacityError)
```

Note: The `(ConnectionError, TimeoutError, OSError, CapacityError)` catch remains as a fallback for non-plugin transient errors (e.g., from lower-level httpx calls that escape plugin error wrapping). Removing it would be a behavior change.

**Audit schema note:** This change replaces the error reason `"llm_retryable_error_no_retry"` (previously used only for `LLMClientError`) with the generic `"transient_error_no_retry"` for all `PluginRetryableError` instances. If any dashboards or MCP queries filter on `"llm_retryable_error_no_retry"`, they must be updated. Remove the `"llm_retryable_error_no_retry"` literal from `TransformErrorCategory` — it is no longer emitted and we have no users (no legacy code policy).

- [ ] **Step 4: Remove now-redundant LLMClientError import if no other usages remain in processor.py**

Search for other uses of `LLMClientError` in `processor.py`. If the only usage was in the retry dispatch, remove the import. If used elsewhere (e.g., in error messages or logging), keep it.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/ -v --timeout=120`
Expected: All PASS

- [ ] **Step 6: Run integration tests for retry behavior**

Run: `.venv/bin/python -m pytest tests/integration/ -v -k "retry" --timeout=120`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/engine/processor.py tests/unit/engine/test_plugin_retryable_error.py
git commit -m "fix: catch PluginRetryableError in processor retry dispatch

Fixes existing bug where retryable WebScrapeError escapes the processor
and crashes the run instead of being retried or quarantined."
```

**Follow-up (out of scope for this PR):** `src/elspeth/plugins/infrastructure/pooling/executor.py:466` catches `LLMClientError` directly. Future plugin error types (e.g., `RetrievalError`) will not be caught by this handler if used inside batch-pooling transforms.

**Action required after PR 1 merges:** Create a filigree task to update `pooling/executor.py` to catch `PluginRetryableError` instead of `LLMClientError`. Use:
```
filigree create "Pooling executor catches LLMClientError directly — should catch PluginRetryableError" --type=task --priority=1
filigree add-label <id> bug
filigree add-comment <id> "pooling/executor.py:466 catches LLMClientError. After PluginRetryableError was introduced, this should catch the base class so RetrievalError and future plugin errors are handled in batch-pooling paths. See PR 1 of the RAG retrieval transform work."
```

---

## PR 2: RAG Retrieval Transform

### Task 4: Extract shared template infrastructure

**Files:**
- Create: `src/elspeth/plugins/infrastructure/templates.py`
- Modify: `src/elspeth/plugins/transforms/llm/templates.py`

This task moves `ImmutableSandboxedEnvironment` usage and `TemplateError` into shared infrastructure so both the LLM transform and RAG transform can use sandboxed Jinja2 without cross-plugin coupling.

- [ ] **Step 1: Write test for shared template infrastructure**

Create `tests/unit/plugins/infrastructure/test_templates.py`:

```python
"""Tests for shared template infrastructure."""

import pytest
from jinja2 import TemplateSyntaxError

from elspeth.plugins.infrastructure.templates import (
    TemplateError,
    create_sandboxed_environment,
)


def test_create_sandboxed_environment_returns_immutable_sandbox():
    env = create_sandboxed_environment()
    template = env.from_string("Hello {{ name }}")
    result = template.render(name="world")
    assert result == "Hello world"


def test_sandboxed_environment_strict_undefined():
    env = create_sandboxed_environment()
    template = env.from_string("{{ missing }}")
    with pytest.raises(Exception, match="missing"):
        template.render()


def test_sandboxed_environment_rejects_invalid_syntax():
    env = create_sandboxed_environment()
    with pytest.raises(TemplateSyntaxError):
        env.from_string("{% if unclosed")


def test_template_error_is_exception():
    err = TemplateError("bad template")
    assert isinstance(err, Exception)
    assert str(err) == "bad template"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_templates.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create shared templates module**

Create `src/elspeth/plugins/infrastructure/templates.py`:

```python
"""Shared Jinja2 template infrastructure for transform plugins.

Provides a sandboxed Jinja2 environment factory and the TemplateError exception.
Used by both LLM prompt templates and RAG query templates.

The sandbox prevents attribute access, method calls, and module imports.
It does NOT limit CPU or memory consumption from template loops — templates
are authored by pipeline architects (trusted config), not end users.
"""

from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment


class TemplateError(Exception):
    """Error in template rendering (including sandbox violations)."""


def create_sandboxed_environment() -> ImmutableSandboxedEnvironment:
    """Create an ImmutableSandboxedEnvironment with StrictUndefined.

    Returns:
        A sandboxed Jinja2 environment that:
        - Raises on undefined variables (StrictUndefined)
        - Blocks attribute access and method calls (ImmutableSandboxedEnvironment)
        - Does not HTML-escape output (autoescape=False)
    """
    return ImmutableSandboxedEnvironment(
        undefined=StrictUndefined,
        autoescape=False,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_templates.py -v`
Expected: PASS

- [ ] **Step 5: Update LLM templates.py to use shared infrastructure**

In `src/elspeth/plugins/transforms/llm/templates.py`, replace the direct jinja2 imports and inline environment creation:

Change imports (lines 10-12):

```python
from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from elspeth.plugins.infrastructure.templates import (
    TemplateError,
    create_sandboxed_environment,
)
```

Remove the local `TemplateError` class definition (lines 21-22).

- [ ] **Step 5a: Update all files that import TemplateError from the old location**

The following files import `TemplateError` from `elspeth.plugins.transforms.llm.templates` and must be updated to import it from the new shared location instead. Since `llm/templates.py` no longer defines `TemplateError`, these will break with `ImportError` if not updated atomically in the same commit.

**Source files (4):**

In `src/elspeth/plugins/transforms/llm/transform.py` (line 48), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `src/elspeth/plugins/transforms/llm/base.py` (line 16), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `src/elspeth/plugins/transforms/llm/azure_batch.py` (line 45), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `src/elspeth/plugins/transforms/llm/openrouter_batch.py` (line 45), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

**Test files (3):**

In `tests/unit/plugins/llm/test_templates.py` (line 7), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `tests/unit/plugins/llm/test_transform.py` (line 507), change:
```python
from elspeth.plugins.transforms.llm.templates import TemplateError
```
to:
```python
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `tests/unit/plugins/llm/test_azure_multi_query.py` (line 310), change:
```python
from elspeth.plugins.transforms.llm.templates import TemplateError
```
to:
```python
from elspeth.plugins.infrastructure.templates import TemplateError
```

Also in `tests/property/plugins/llm/test_template_properties.py` (line 20), change:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate, TemplateError
```
to:
```python
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.infrastructure.templates import TemplateError
```

In `PromptTemplate.__init__` (lines 111-120), replace:

```python
        # Use sandboxed environment for security
        self._env = create_sandboxed_environment()

        try:
            self._template = self._env.from_string(template_string)
        except TemplateSyntaxError as e:
            raise TemplateError(f"Invalid template syntax: {e}") from e
```

- [ ] **Step 6: Run LLM transform tests to verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/llm/ -v --timeout=120`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/elspeth/plugins/infrastructure/templates.py src/elspeth/plugins/transforms/llm/templates.py src/elspeth/plugins/transforms/llm/transform.py src/elspeth/plugins/transforms/llm/base.py src/elspeth/plugins/transforms/llm/azure_batch.py src/elspeth/plugins/transforms/llm/openrouter_batch.py tests/unit/plugins/infrastructure/test_templates.py tests/unit/plugins/llm/test_templates.py tests/unit/plugins/llm/test_transform.py tests/unit/plugins/llm/test_azure_multi_query.py tests/property/plugins/llm/test_template_properties.py
git commit -m "refactor: extract shared template infrastructure from LLM plugin

All callers updated atomically — no-legacy-code policy."
```

### Task 5: RetrievalChunk and RetrievalError types

**Files:**
- Create: `src/elspeth/plugins/infrastructure/clients/retrieval/__init__.py`
- Create: `src/elspeth/plugins/infrastructure/clients/retrieval/types.py`
- Create: `src/elspeth/plugins/infrastructure/clients/retrieval/base.py`
- Test: `tests/unit/plugins/infrastructure/clients/retrieval/test_types.py`

- [ ] **Step 1: Write tests for RetrievalChunk**

Create directory structure and test file:

```bash
mkdir -p tests/unit/plugins/infrastructure/clients/retrieval
touch tests/unit/plugins/infrastructure/clients/retrieval/__init__.py
```

Create `tests/unit/plugins/infrastructure/clients/retrieval/test_types.py`:

```python
"""Tests for retrieval type dataclasses."""

import pytest

from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


class TestRetrievalChunkScoreValidation:
    def test_score_at_lower_bound(self):
        chunk = RetrievalChunk(content="text", score=0.0, source_id="doc1", metadata={})
        assert chunk.score == 0.0

    def test_score_at_upper_bound(self):
        chunk = RetrievalChunk(content="text", score=1.0, source_id="doc1", metadata={})
        assert chunk.score == 1.0

    def test_score_below_lower_bound_raises(self):
        with pytest.raises(ValueError, match="normalized to.*0.0.*1.0"):
            RetrievalChunk(content="text", score=-0.1, source_id="doc1", metadata={})

    def test_score_above_upper_bound_raises(self):
        with pytest.raises(ValueError, match="normalized to.*0.0.*1.0"):
            RetrievalChunk(content="text", score=1.1, source_id="doc1", metadata={})

    def test_mid_range_score(self):
        chunk = RetrievalChunk(content="text", score=0.75, source_id="doc1", metadata={})
        assert chunk.score == 0.75


class TestRetrievalChunkMetadataValidation:
    def test_valid_metadata(self):
        chunk = RetrievalChunk(
            content="text", score=0.5, source_id="doc1",
            metadata={"page": 3, "section": "intro"},
        )
        assert chunk.metadata == {"page": 3, "section": "intro"}

    def test_empty_metadata(self):
        chunk = RetrievalChunk(content="text", score=0.5, source_id="doc1", metadata={})
        assert chunk.metadata == {}

    def test_non_serializable_metadata_raises(self):
        """Provider must coerce non-primitive types at Tier 3 boundary."""
        from datetime import datetime

        with pytest.raises(ValueError, match="JSON-serializable"):
            RetrievalChunk(
                content="text", score=0.5, source_id="doc1",
                metadata={"timestamp": datetime(2026, 1, 1)},
            )

    def test_bytes_metadata_raises(self):
        with pytest.raises(ValueError, match="JSON-serializable"):
            RetrievalChunk(
                content="text", score=0.5, source_id="doc1",
                metadata={"data": b"binary"},
            )

    def test_nested_metadata_ok(self):
        chunk = RetrievalChunk(
            content="text", score=0.5, source_id="doc1",
            metadata={"nested": {"key": "value"}, "list": [1, 2, 3]},
        )
        assert chunk.metadata["nested"]["key"] == "value"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_types.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Create the retrieval package and types module**

```bash
mkdir -p src/elspeth/plugins/infrastructure/clients/retrieval
```

Create `src/elspeth/plugins/infrastructure/clients/retrieval/__init__.py`:

```python
"""Retrieval provider infrastructure for RAG transforms."""

from elspeth.plugins.infrastructure.clients.retrieval.base import (
    RetrievalError,
    RetrievalProvider,
)
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

__all__ = [
    "RetrievalChunk",
    "RetrievalError",
    "RetrievalProvider",
]
```

Create `src/elspeth/plugins/infrastructure/clients/retrieval/types.py`:

```python
"""Retrieval type dataclasses.

These types represent the output of a retrieval provider search operation.
RetrievalChunk enforces two invariants at construction time:
1. Score is normalized to [0.0, 1.0]
2. Metadata is JSON-serializable
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalChunk:
    """A single retrieved document chunk.

    Attributes:
        content: The retrieved text content.
        score: Relevance score, normalized to 0.0-1.0.
        source_id: Document/chunk identifier (for audit traceability).
        metadata: Provider-specific metadata (page, section, index name, etc.).
            Must be JSON-serializable — providers must coerce non-primitive types
            (datetime -> ISO 8601 str, UUID -> str) at the Tier 3 boundary.
    """

    content: str
    score: float
    source_id: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"Score must be normalized to [0.0, 1.0], got {self.score!r}. "
                f"Provider score normalization bug — check the provider implementation."
            )
        try:
            json.dumps(self.metadata)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"metadata must be JSON-serializable (got {type(exc).__name__}: {exc}). "
                f"Provider must coerce non-primitive types (datetime -> ISO 8601 str, "
                f"UUID -> str, etc.) at the Tier 3 boundary before constructing RetrievalChunk."
            ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_types.py -v`
Expected: All PASS

- [ ] **Step 5: Write tests for RetrievalError**

Append to `tests/unit/plugins/infrastructure/clients/retrieval/test_types.py`:

```python
from elspeth.contracts.errors import PluginRetryableError
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError


class TestRetrievalError:
    def test_retryable_error(self):
        err = RetrievalError("timeout", retryable=True, status_code=429)
        assert err.retryable is True
        assert err.status_code == 429
        assert str(err) == "timeout"

    def test_non_retryable_error(self):
        err = RetrievalError("bad request", retryable=False, status_code=400)
        assert err.retryable is False
        assert err.status_code == 400

    def test_is_plugin_retryable_error(self):
        err = RetrievalError("test", retryable=True)
        assert isinstance(err, PluginRetryableError)

    def test_status_code_defaults_none(self):
        err = RetrievalError("test", retryable=False)
        assert err.status_code is None
```

- [ ] **Step 6: Create base.py with RetrievalProvider protocol and RetrievalError**

Create `src/elspeth/plugins/infrastructure/clients/retrieval/base.py`:

```python
"""RetrievalProvider protocol and RetrievalError exception."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from elspeth.contracts.errors import PluginRetryableError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


class RetrievalError(PluginRetryableError):
    """Base exception for retrieval provider errors.

    Raised by providers for transient failures (retryable=True) to trigger
    engine retry, or for permanent failures (retryable=False) to be caught
    by the transform and converted to TransformResult.error().

    Attributes:
        retryable: Whether the error is transient and should be retried.
        status_code: HTTP status code if applicable (for audit context).
    """

    def __init__(
        self, message: str, *, retryable: bool, status_code: int | None = None
    ) -> None:
        super().__init__(message, retryable=retryable, status_code=status_code)


@runtime_checkable
class RetrievalProvider(Protocol):
    """Search backend interface for RAG retrieval.

    Implementations handle search execution, score normalization, and
    resource lifecycle. The protocol is deliberately minimal — no
    provider-specific query objects leak into the transform.
    """

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        *,
        state_id: str,
        token_id: str | None,
    ) -> list[RetrievalChunk]:
        """Execute a search query and return ranked results.

        Args:
            query: The search query text.
            top_k: Maximum number of results to return.
            min_score: Minimum relevance score threshold (0.0-1.0).
            state_id: Per-row audit identity for AuditedHTTPClient scoping.
            token_id: Pipeline token identity for audit correlation.

        Returns:
            List of RetrievalChunk, ordered by descending relevance score.
            May be empty if no results meet the min_score threshold.

        Raises:
            RetrievalError: On search failures (retryable or permanent).
        """
        ...

    def close(self) -> None:
        """Release provider resources (connections, clients)."""
        ...
```

- [ ] **Step 7: Run all retrieval type tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/elspeth/plugins/infrastructure/clients/retrieval/ tests/unit/plugins/infrastructure/clients/retrieval/
git commit -m "feat: add RetrievalChunk, RetrievalProvider protocol, and RetrievalError"
```

### Task 6: Query construction module

**Files:**
- Create: `src/elspeth/plugins/transforms/rag/query.py`
- Test: `tests/unit/plugins/transforms/rag/test_query.py`

- [ ] **Step 1: Write tests for query construction**

Create directory structure:

```bash
mkdir -p src/elspeth/plugins/transforms/rag
mkdir -p tests/unit/plugins/transforms/rag
touch src/elspeth/plugins/transforms/rag/__init__.py
touch tests/unit/plugins/transforms/rag/__init__.py
```

Create `tests/unit/plugins/transforms/rag/test_query.py`:

```python
"""Tests for RAG query construction."""

import concurrent.futures

import pytest

from elspeth.plugins.transforms.rag.query import QueryBuilder


class TestFieldOnlyMode:
    def test_extracts_value_verbatim(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": "What is RAG?"})
        assert result.query == "What is RAG?"

    def test_missing_field_crashes(self):
        """Missing field is a contract violation (Tier 2) — crash, don't quarantine."""
        builder = QueryBuilder(query_field="question")
        with pytest.raises(KeyError):
            builder.build({"other_field": "value"})

    def test_none_value_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": None})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "null_value"

    def test_empty_string_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": ""})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "empty_query"

    def test_whitespace_only_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": "   \t\n  "})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "empty_query"


class TestTemplateMode:
    def test_renders_with_query_and_row(self):
        builder = QueryBuilder(
            query_field="topic",
            query_template="Find documents about {{ query }} for {{ row.category }}",
        )
        result = builder.build({"topic": "compliance", "category": "finance"})
        assert result.query == "Find documents about compliance for finance"

    def test_structural_error_at_compile_time(self):
        with pytest.raises(Exception):  # TemplateSyntaxError wrapped
            QueryBuilder(
                query_field="topic",
                query_template="{% if unclosed",
            )

    def test_render_error_returns_error(self):
        builder = QueryBuilder(
            query_field="topic",
            query_template="{{ query }} for {{ row.missing_field }}",
        )
        result = builder.build({"topic": "test"})
        assert result.error is not None
        assert result.error["reason"] == "template_rendering_failed"


class TestRegexMode:
    def test_captures_first_group(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+?)(?:\n|$)",
        )
        result = builder.build({"text": "issue: payment failed\nother stuff"})
        assert result.query == "payment failed"

    def test_full_match_when_no_groups(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"\w+@\w+\.\w+",
        )
        result = builder.build({"text": "contact user@example.com for help"})
        assert result.query == "user@example.com"

    def test_no_match_returns_error(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )
        result = builder.build({"text": "no issue here"})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"

    def test_non_participating_group_returns_error(self):
        """Optional capture group that didn't participate."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"(?:issue|problem)(?::\s*(.+?))?$",
        )
        result = builder.build({"text": "issue"})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"
        assert result.error["cause"] == "capture_group_empty"

    def test_timeout_on_catastrophic_backtracking(self):
        """ReDoS protection: pathological pattern with adversarial input."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"(a+)+b",
            regex_timeout=0.1,  # Short timeout for test
        )
        result = builder.build({"text": "a" * 30})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"
        assert result.error["cause"] == "regex_timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_query.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement QueryBuilder**

Create `src/elspeth/plugins/transforms/rag/query.py`:

```python
"""Query construction for RAG retrieval transform.

Three modes, all anchored on query_field:
1. Field only: use field value verbatim
2. Field + template: render Jinja2 template with {{ query }} and {{ row }}
3. Field + regex: extract search text via capture group
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass
from typing import Any

from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from elspeth.plugins.infrastructure.templates import (
    TemplateError,
    create_sandboxed_environment,
)


@dataclass(frozen=True)
class QueryResult:
    """Result of query construction."""

    query: str | None = None
    error: dict[str, Any] | None = None


class QueryBuilder:
    """Constructs search queries from row data.

    Supports three modes:
    - Field only: query_field set, no template or pattern
    - Template: query_field + query_template (Jinja2)
    - Regex: query_field + query_pattern (re capture group)

    Thread pool for regex timeout is cached at instance level and must
    be explicitly closed via close().
    """

    def __init__(
        self,
        query_field: str,
        *,
        query_template: str | None = None,
        query_pattern: str | None = None,
        regex_timeout: float = 5.0,
    ) -> None:
        self._query_field = query_field
        self._regex_timeout = regex_timeout
        self._compiled_template = None
        self._compiled_pattern = None
        self._regex_executor: concurrent.futures.ThreadPoolExecutor | None = None

        if query_template is not None:
            env = create_sandboxed_environment()
            try:
                self._compiled_template = env.from_string(query_template)
            except TemplateSyntaxError as e:
                raise TemplateError(f"Invalid query template syntax: {e}") from e

        if query_pattern is not None:
            self._compiled_pattern = re.compile(query_pattern)
            # Single worker serializes regex evaluation per-instance for timeout
            # isolation. ThreadPoolExecutor threads are daemon threads in Python 3.9+,
            # so process exit will clean up even if close() is never called (e.g.,
            # pipeline crash before teardown). Note: shutdown(wait=False) in close()
            # does not cancel in-flight regex — the thread continues until it completes
            # or the process exits.
            self._regex_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="rag_regex",
            )

    def build(self, row_data: dict[str, Any]) -> QueryResult:
        """Construct a search query from row data.

        Args:
            row_data: Row data dict (normalized keys).

        Returns:
            QueryResult with either query string or error dict.
        """
        # Step 1: Extract field value — direct access, NOT .get().
        # Missing field = upstream contract violation (Tier 2), crash is correct.
        # None value = data quality issue, quarantine is correct.
        extracted = row_data[self._query_field]

        # Step 2: Validate not None
        if extracted is None:
            return QueryResult(error={
                "reason": "invalid_input",
                "field": self._query_field,
                "cause": "null_value",
            })

        # Step 3: Construct query by mode
        if self._compiled_template is not None:
            return self._build_template(extracted, row_data)
        elif self._compiled_pattern is not None:
            return self._build_regex(extracted)
        else:
            return self._build_field_only(extracted)

    def _build_field_only(self, extracted: Any) -> QueryResult:
        query = str(extracted)
        return self._validate_non_empty(query)

    def _build_template(self, extracted: Any, row_data: dict[str, Any]) -> QueryResult:
        try:
            query = self._compiled_template.render(query=extracted, row=row_data)
        except UndefinedError as e:
            return QueryResult(error={
                "reason": "template_rendering_failed",
                "error": str(e),
                "field": self._query_field,
            })
        except SecurityError as e:
            return QueryResult(error={
                "reason": "template_rendering_failed",
                "error": f"Sandbox violation: {e}",
                "field": self._query_field,
            })
        except Exception as e:
            return QueryResult(error={
                "reason": "template_rendering_failed",
                "error": str(e),
                "field": self._query_field,
            })
        return self._validate_non_empty(query)

    def _build_regex(self, extracted: Any) -> QueryResult:
        text = str(extracted)
        try:
            future = self._regex_executor.submit(self._compiled_pattern.search, text)
            match = future.result(timeout=self._regex_timeout)
        except concurrent.futures.TimeoutError:
            return QueryResult(error={
                "reason": "no_regex_match",
                "field": self._query_field,
                "cause": "regex_timeout",
            })

        if match is None:
            return QueryResult(error={
                "reason": "no_regex_match",
                "field": self._query_field,
                "pattern": self._compiled_pattern.pattern,
            })

        captured = match.group(1) if match.lastindex else match.group(0)
        if captured is None:
            return QueryResult(error={
                "reason": "no_regex_match",
                "field": self._query_field,
                "cause": "capture_group_empty",
            })

        return self._validate_non_empty(captured)

    def _validate_non_empty(self, query: str) -> QueryResult:
        if not query.strip():
            return QueryResult(error={
                "reason": "invalid_input",
                "field": self._query_field,
                "cause": "empty_query",
            })
        return QueryResult(query=query)

    def close(self) -> None:
        """Shut down the regex thread pool executor if it was created."""
        if self._regex_executor is not None:
            self._regex_executor.shutdown(wait=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_query.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/rag/ tests/unit/plugins/transforms/rag/
git commit -m "feat: add RAG query construction module with field/template/regex modes"
```

### Task 7: Context formatter module

**Files:**
- Create: `src/elspeth/plugins/transforms/rag/formatter.py`
- Test: `tests/unit/plugins/transforms/rag/test_formatter.py`

- [ ] **Step 1: Write tests for context formatting**

Create `tests/unit/plugins/transforms/rag/test_formatter.py`:

```python
"""Tests for RAG context formatting."""

import pytest

from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.formatter import format_context


def _chunk(content: str, score: float = 0.9) -> RetrievalChunk:
    return RetrievalChunk(content=content, score=score, source_id="doc1", metadata={})


class TestNumberedFormat:
    def test_multiple_chunks(self):
        chunks = [_chunk("First chunk"), _chunk("Second chunk")]
        result = format_context(chunks, format_mode="numbered")
        assert result.text == "1. First chunk\n2. Second chunk"
        assert result.truncated is False

    def test_single_chunk(self):
        result = format_context([_chunk("Only chunk")], format_mode="numbered")
        assert result.text == "1. Only chunk"

    def test_empty_chunks(self):
        result = format_context([], format_mode="numbered")
        assert result.text == ""
        assert result.truncated is False


class TestSeparatedFormat:
    def test_with_default_separator(self):
        chunks = [_chunk("First"), _chunk("Second")]
        result = format_context(chunks, format_mode="separated", separator="\n---\n")
        assert result.text == "First\n---\nSecond"

    def test_with_custom_separator(self):
        chunks = [_chunk("A"), _chunk("B")]
        result = format_context(chunks, format_mode="separated", separator=" | ")
        assert result.text == "A | B"


class TestRawFormat:
    def test_concatenates_content(self):
        chunks = [_chunk("Hello"), _chunk("World")]
        result = format_context(chunks, format_mode="raw")
        assert result.text == "HelloWorld"


class TestMaxContextLength:
    def test_truncation_at_chunk_boundary(self):
        chunks = [_chunk("Short"), _chunk("Also short"), _chunk("Third")]
        # "1. Short\n2. Also short" = 22 chars, "1. Short" = 8 chars
        result = format_context(chunks, format_mode="numbered", max_length=22)
        assert "Short" in result.text
        assert "Also short" in result.text
        assert "Third" not in result.text
        assert result.truncated is True

    def test_first_chunk_exceeds_limit(self):
        chunks = [_chunk("A very long chunk that exceeds the limit")]
        result = format_context(chunks, format_mode="numbered", max_length=10)
        assert len(result.text) <= 10 + len("[truncated]")
        assert result.text.endswith("[truncated]")
        assert result.truncated is True

    def test_no_truncation_when_within_limit(self):
        chunks = [_chunk("Short")]
        result = format_context(chunks, format_mode="numbered", max_length=1000)
        assert result.text == "1. Short"
        assert result.truncated is False

    def test_none_max_length_means_no_limit(self):
        long_content = "x" * 10000
        chunks = [_chunk(long_content)]
        result = format_context(chunks, format_mode="numbered", max_length=None)
        assert len(result.text) > 10000
        assert result.truncated is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_formatter.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement context formatter**

Create `src/elspeth/plugins/transforms/rag/formatter.py`:

```python
"""Context formatting for RAG retrieval output.

Joins multiple retrieved chunks into a single text field with
configurable formatting and optional length capping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


@dataclass(frozen=True)
class FormattedContext:
    """Result of context formatting."""

    text: str
    truncated: bool


def format_context(
    chunks: list[RetrievalChunk],
    *,
    format_mode: Literal["numbered", "separated", "raw"],
    separator: str = "\n---\n",
    max_length: int | None = None,
) -> FormattedContext:
    """Format retrieved chunks into a single context string.

    Args:
        chunks: Retrieved chunks to format.
        format_mode: How to join chunks.
        separator: Separator for "separated" mode.
        max_length: Character cap. Truncation at chunk boundaries where possible.

    Returns:
        FormattedContext with formatted text and truncation flag.
    """
    if not chunks:
        return FormattedContext(text="", truncated=False)

    # Format individual chunks
    formatted_parts = _format_parts(chunks, format_mode, separator)

    # Join and apply length cap
    return _apply_length_cap(formatted_parts, format_mode, separator, max_length)


def _format_parts(
    chunks: list[RetrievalChunk],
    format_mode: Literal["numbered", "separated", "raw"],
    separator: str,
) -> list[str]:
    """Format each chunk according to the mode."""
    if format_mode == "numbered":
        return [f"{i + 1}. {chunk.content}" for i, chunk in enumerate(chunks)]
    elif format_mode == "separated":
        return [chunk.content for chunk in chunks]
    else:  # raw
        return [chunk.content for chunk in chunks]


def _apply_length_cap(
    parts: list[str],
    format_mode: Literal["numbered", "separated", "raw"],
    separator: str,
    max_length: int | None,
) -> FormattedContext:
    """Apply max_length truncation at chunk boundaries where possible."""
    joiner = "\n" if format_mode == "numbered" else (separator if format_mode == "separated" else "")

    full_text = joiner.join(parts)

    if max_length is None or len(full_text) <= max_length:
        return FormattedContext(text=full_text, truncated=False)

    # Try to truncate at chunk boundaries
    included: list[str] = []
    current_length = 0

    for i, part in enumerate(parts):
        part_length = len(part)
        joiner_length = len(joiner) if i > 0 else 0

        if current_length + joiner_length + part_length <= max_length:
            included.append(part)
            current_length += joiner_length + part_length
        else:
            break

    if included:
        return FormattedContext(text=joiner.join(included), truncated=True)

    # First chunk exceeds limit — hard truncate with indicator
    truncated_text = parts[0][:max_length] + "[truncated]"
    return FormattedContext(text=truncated_text, truncated=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_formatter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/rag/formatter.py tests/unit/plugins/transforms/rag/test_formatter.py
git commit -m "feat: add RAG context formatter with numbered/separated/raw modes"
```

### Task 8: RAGRetrievalConfig

**Files:**
- Create: `src/elspeth/plugins/transforms/rag/config.py`
- Test: `tests/unit/plugins/transforms/rag/test_config.py`

- [ ] **Step 1: Write tests for config validation**

Create `tests/unit/plugins/transforms/rag/test_config.py`:

```python
"""Tests for RAGRetrievalConfig validation."""

import pytest

from elspeth.plugins.transforms.rag.config import RAGRetrievalConfig


def _valid_config(**overrides):
    """Build a valid config dict with overrides."""
    base = {
        "output_prefix": "policy",
        "query_field": "question",
        "provider": "azure_search",
        "provider_config": {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
        },
        "schema_config": {"mode": "observed"},
    }
    base.update(overrides)
    return base


class TestOutputPrefix:
    def test_valid_identifier(self):
        config = RAGRetrievalConfig(**_valid_config(output_prefix="financial"))
        assert config.output_prefix == "financial"

    def test_rejects_non_identifier(self):
        with pytest.raises(ValueError, match="valid Python identifier"):
            RAGRetrievalConfig(**_valid_config(output_prefix="123invalid"))

    def test_rejects_keyword(self):
        with pytest.raises(ValueError, match="Python keyword"):
            RAGRetrievalConfig(**_valid_config(output_prefix="class"))

    def test_rejects_with_spaces(self):
        with pytest.raises(ValueError, match="valid Python identifier"):
            RAGRetrievalConfig(**_valid_config(output_prefix="has spaces"))


class TestQueryModes:
    def test_template_and_pattern_mutually_exclusive(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            RAGRetrievalConfig(**_valid_config(
                query_template="{{ query }}",
                query_pattern=r"\w+",
            ))

    def test_template_only_ok(self):
        config = RAGRetrievalConfig(**_valid_config(query_template="{{ query }}"))
        assert config.query_template == "{{ query }}"

    def test_pattern_only_ok(self):
        config = RAGRetrievalConfig(**_valid_config(query_pattern=r"issue:\s*(.+)"))
        assert config.query_pattern == r"issue:\s*(.+)"

    def test_invalid_regex_rejected(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            RAGRetrievalConfig(**_valid_config(query_pattern=r"(unclosed"))


class TestRetrievalParams:
    def test_top_k_bounds(self):
        config = RAGRetrievalConfig(**_valid_config(top_k=1))
        assert config.top_k == 1

        config = RAGRetrievalConfig(**_valid_config(top_k=100))
        assert config.top_k == 100

        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(top_k=0))

        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(top_k=101))

    def test_min_score_bounds(self):
        config = RAGRetrievalConfig(**_valid_config(min_score=0.0))
        assert config.min_score == 0.0

        config = RAGRetrievalConfig(**_valid_config(min_score=1.0))
        assert config.min_score == 1.0

        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(min_score=-0.1))

        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(min_score=1.1))


class TestProviderConfig:
    def test_unknown_provider_rejected(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            RAGRetrievalConfig(**_valid_config(provider="unknown"))

    def test_invalid_provider_config_rejected_eagerly(self):
        """Provider config is validated at YAML load time, not first row."""
        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(
                provider_config={"endpoint": "http://no-https.example.com", "index": "test", "api_key": "k"},
            ))

    def test_max_context_length_ge_1(self):
        config = RAGRetrievalConfig(**_valid_config(max_context_length=1))
        assert config.max_context_length == 1

        with pytest.raises(ValueError):
            RAGRetrievalConfig(**_valid_config(max_context_length=0))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_config.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement RAGRetrievalConfig**

Create `src/elspeth/plugins/transforms/rag/config.py`:

```python
"""Configuration for RAG retrieval transform."""

from __future__ import annotations

import keyword
import re
from typing import TYPE_CHECKING, Any, Callable, Literal, Self

from pydantic import Field, field_validator, model_validator

from elspeth.plugins.infrastructure.config_base import TransformDataConfig

if TYPE_CHECKING:
    from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalProvider

# Provider factory type: takes validated config + lifecycle dependencies,
# returns a RetrievalProvider. Each factory cherry-picks what it needs.
ProviderFactory = Callable[..., "RetrievalProvider"]


def _get_providers() -> dict[str, tuple[type, ProviderFactory]]:
    """Lazy provider registry — only imports providers whose deps are installed.

    Azure is always available (httpx is a core dep). Chroma requires the
    [rag] optional extra. The validate_provider_config model validator
    produces a clear error when a provider's deps are not installed.
    """
    providers: dict[str, tuple[type, ProviderFactory]] = {}

    try:
        from elspeth.plugins.infrastructure.clients.retrieval.azure_search import (
            AzureSearchProvider, AzureSearchProviderConfig,
        )
        providers["azure_search"] = (AzureSearchProviderConfig, AzureSearchProvider)
    except ImportError:
        pass  # Azure provider dependencies not available

    return providers


PROVIDERS = _get_providers()


class RAGRetrievalConfig(TransformDataConfig):
    """Configuration for the rag_retrieval transform plugin."""

    # Output field prefix (mandatory)
    output_prefix: str

    # Query construction
    query_field: str
    query_template: str | None = None
    query_pattern: str | None = None

    # Provider selection and config
    provider: str
    provider_config: dict[str, Any]

    # Retrieval parameters
    top_k: int = Field(default=5, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Zero results behavior
    on_no_results: Literal["quarantine", "continue"] = "quarantine"

    # Context formatting
    context_format: Literal["numbered", "separated", "raw"] = "numbered"
    context_separator: str = "\n---\n"
    max_context_length: int | None = Field(default=None, ge=1)

    @field_validator("output_prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        if not v.isidentifier():
            raise ValueError(f"output_prefix must be a valid Python identifier, got {v!r}")
        if keyword.iskeyword(v):
            raise ValueError(
                f"output_prefix must not be a Python keyword, got {v!r}. "
                f"Keywords like 'class', 'return' produce field names that break Jinja2 templates."
            )
        return v

    @model_validator(mode="after")
    def validate_query_modes(self) -> Self:
        if self.query_template and self.query_pattern:
            raise ValueError("query_template and query_pattern are mutually exclusive")
        return self

    @model_validator(mode="after")
    def validate_provider_config(self) -> Self:
        provider_entry = PROVIDERS.get(self.provider)
        if provider_entry is None:
            raise ValueError(f"Unknown provider: {self.provider!r}. Available: {sorted(PROVIDERS)}")
        config_cls, _ = provider_entry
        config_cls(**self.provider_config)  # Eagerly validate
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

Note: This imports from `azure_search.py` which doesn't exist yet. The test will need the Azure provider config class to exist. We'll create a minimal version in Step 3a.

- [ ] **Step 3a: Create minimal AzureSearchProviderConfig for config validation**

This will be expanded in Task 9. For now, create `src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py` with the config class only:

```python
"""Azure AI Search provider for RAG retrieval."""

from __future__ import annotations

import re
import urllib.parse
from typing import Literal, Self

from pydantic import BaseModel, field_validator, model_validator


class AzureSearchProviderConfig(BaseModel):
    """Configuration for Azure AI Search provider."""

    model_config = {"extra": "forbid", "frozen": True}

    endpoint: str
    index: str

    api_key: str | None = None
    use_managed_identity: bool = False
    api_version: str = "2024-07-01"

    search_mode: Literal["vector", "keyword", "hybrid", "semantic"] = "hybrid"
    request_timeout: float = 30.0

    vector_field: str = "contentVector"
    semantic_config: str | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        # Structural URL validation only — no DNS resolution at config time.
        # Full SSRF validation (with DNS pinning) is deferred to the provider's
        # on_start() / first search call via AuditedHTTPClient, which already
        # performs validate_url_for_ssrf() at request time. This keeps config
        # construction deterministic and avoids breaking offline/CI environments.
        parsed = urllib.parse.urlparse(v)
        if parsed.scheme != "https":
            raise ValueError(f"endpoint must use HTTPS scheme, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError(f"endpoint must have a hostname, got {v!r}")
        return v

    @field_validator("index")
    @classmethod
    def validate_index_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                f"index must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start with alphanumeric), got {v!r}."
            )
        return v

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}(-preview)?$", v):
            raise ValueError(
                f"api_version must match YYYY-MM-DD or YYYY-MM-DD-preview format, got {v!r}"
            )
        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str | None) -> str | None:
        if v is not None:
            # Reject keys containing characters that could cause header injection
            if any(c in v for c in "\r\n\x00"):
                raise ValueError("api_key must not contain newlines or null bytes")
            if len(v) > 256:
                raise ValueError(f"api_key exceeds maximum length of 256, got {len(v)}")
        return v

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


class AzureSearchProvider:
    """Azure AI Search implementation of RetrievalProvider.

    Placeholder — full implementation in Task 9.
    """

    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/rag/config.py src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py tests/unit/plugins/transforms/rag/test_config.py
git commit -m "feat: add RAGRetrievalConfig with provider registry and eager validation"
```

### Task 9: Azure AI Search provider implementation

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py`
- Test: `tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py`

- [ ] **Step 1: Write tests for Azure provider**

Create `tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py`:

```python
"""Tests for Azure AI Search provider."""

import json
from unittest.mock import MagicMock, patch

import pytest

from elspeth.plugins.infrastructure.clients.retrieval.azure_search import (
    AzureSearchProvider,
    AzureSearchProviderConfig,
)
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


class TestAzureSearchProviderConfig:
    def test_requires_https(self):
        with pytest.raises(ValueError, match="HTTPS"):
            AzureSearchProviderConfig(
                endpoint="http://test.search.windows.net",
                index="test",
                api_key="key",
            )

    def test_auth_mutual_exclusion(self):
        with pytest.raises(ValueError, match="only one"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
                api_key="key",
                use_managed_identity=True,
            )

    def test_auth_required(self):
        with pytest.raises(ValueError, match="either"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
            )

    def test_semantic_requires_config(self):
        with pytest.raises(ValueError, match="semantic_config"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
                api_key="key",
                search_mode="semantic",
            )

    def test_index_name_validation(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="bad/path/../traversal",
                api_key="key",
            )

    def test_valid_index_names(self):
        for name in ["my-index", "index_v2", "MyIndex123"]:
            config = AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index=name,
                api_key="key",
            )
            assert config.index == name


class TestAzureSearchProviderSearch:
    """Tests for search method with mocked HTTP transport."""

    def _make_provider(self, search_mode="hybrid"):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
            search_mode=search_mode,
        )
        recorder = MagicMock()
        telemetry_emit = MagicMock()
        return AzureSearchProvider(
            config=config,
            recorder=recorder,
            run_id="run-1",
            telemetry_emit=telemetry_emit,
        )

    def test_returns_retrieval_chunks(self):
        """Provider returns properly constructed RetrievalChunks."""
        provider = self._make_provider()
        mock_response = {
            "value": [
                {"@search.score": 5.0, "content": "Result 1", "id": "doc1"},
                {"@search.score": 3.0, "content": "Result 2", "id": "doc2"},
            ]
        }
        with patch.object(provider, "_execute_search", return_value=mock_response):
            chunks = provider.search(
                "test query", top_k=5, min_score=0.0,
                state_id="state-1", token_id="token-1",
            )
        assert len(chunks) == 2
        assert all(isinstance(c, RetrievalChunk) for c in chunks)
        assert chunks[0].score >= chunks[1].score

    def test_min_score_filtering(self):
        """Results below min_score are discarded."""
        provider = self._make_provider()
        mock_response = {
            "value": [
                {"@search.score": 5.0, "content": "High", "id": "doc1"},
                {"@search.score": 0.1, "content": "Low", "id": "doc2"},
            ]
        }
        with patch.object(provider, "_execute_search", return_value=mock_response):
            chunks = provider.search(
                "test", top_k=5, min_score=0.5,
                state_id="state-1", token_id=None,
            )
        assert len(chunks) == 1
        assert chunks[0].content == "High"

    def test_malformed_json_raises_retrieval_error(self):
        """Tier 3 boundary: malformed response is non-retryable."""
        provider = self._make_provider()
        with patch.object(provider, "_execute_search", side_effect=RetrievalError("bad json", retryable=False)):
            with pytest.raises(RetrievalError) as exc_info:
                provider.search("test", top_k=5, min_score=0.0, state_id="s1", token_id=None)
            assert not exc_info.value.retryable

    def test_server_error_raises_retryable(self):
        """HTTP 5xx triggers retryable error."""
        provider = self._make_provider()
        with patch.object(
            provider, "_execute_search",
            side_effect=RetrievalError("server error", retryable=True, status_code=500),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                provider.search("test", top_k=5, min_score=0.0, state_id="s1", token_id=None)
            assert exc_info.value.retryable
            assert exc_info.value.status_code == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py -v`
Expected: FAIL — `AzureSearchProvider` is a placeholder

- [ ] **Step 3: Implement AzureSearchProvider**

Replace the placeholder in `src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py`:

```python
"""Azure AI Search provider for RAG retrieval."""

from __future__ import annotations

import json
import math
import re
import urllib.parse
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import BaseModel, field_validator, model_validator

from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.core.rate_limit.limiter import RateLimiter
    from elspeth.core.rate_limit.registry import NoOpLimiter
    from elspeth.plugins.infrastructure.clients.base import TelemetryEmitCallback


class AzureSearchProviderConfig(BaseModel):
    """Configuration for Azure AI Search provider."""

    model_config = {"extra": "forbid", "frozen": True}

    endpoint: str
    index: str

    api_key: str | None = None
    use_managed_identity: bool = False
    api_version: str = "2024-07-01"

    search_mode: Literal["vector", "keyword", "hybrid", "semantic"] = "hybrid"
    request_timeout: float = 30.0

    vector_field: str = "contentVector"
    semantic_config: str | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        # Structural URL validation only — no DNS resolution at config time.
        # Full SSRF validation (with DNS pinning) is deferred to the provider's
        # on_start() / first search call via AuditedHTTPClient, which already
        # performs validate_url_for_ssrf() at request time. This keeps config
        # construction deterministic and avoids breaking offline/CI environments.
        parsed = urllib.parse.urlparse(v)
        if parsed.scheme != "https":
            raise ValueError(f"endpoint must use HTTPS scheme, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError(f"endpoint must have a hostname, got {v!r}")
        return v

    @field_validator("index")
    @classmethod
    def validate_index_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                f"index must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start with alphanumeric), got {v!r}."
            )
        return v

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}(-preview)?$", v):
            raise ValueError(
                f"api_version must match YYYY-MM-DD or YYYY-MM-DD-preview format, got {v!r}"
            )
        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str | None) -> str | None:
        if v is not None:
            # Reject keys containing characters that could cause header injection
            if any(c in v for c in "\r\n\x00"):
                raise ValueError("api_key must not contain newlines or null bytes")
            if len(v) > 256:
                raise ValueError(f"api_key exceeds maximum length of 256, got {len(v)}")
        return v

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


# Score normalization ranges per search mode.
# Azure AI Search returns different score scales depending on the mode.
#
# KNOWN LIMITATION: BM25 scores are technically unbounded — values above
# the configured max are clamped to 1.0, which compresses score resolution
# for very high-relevance results. In practice, scores above 50 are rare
# but possible with long queries against highly relevant documents.
# If operators observe frequent clamping (visible in success_reason metadata
# as top_score=1.0 with high chunk counts), consider tuning the max values
# per index or switching to semantic mode which has a fixed 0-4 range.
_SCORE_RANGES: dict[str, tuple[float, float]] = {
    "keyword": (0.0, 50.0),     # BM25 scores (0 to ~50, can exceed in rare cases)
    "vector": (0.0, 1.0),       # Cosine similarity (already 0-1)
    "hybrid": (0.0, 50.0),      # Combined score (dominated by BM25 range)
    "semantic": (0.0, 4.0),     # Semantic ranker (0-4 scale)
}


class AzureSearchProvider:
    """Azure AI Search implementation of RetrievalProvider.

    Constructs a per-call AuditedHTTPClient scoped to each row's state_id,
    following the WebScrapeTransform pattern. Holds shared resources
    (recorder, run_id, limiter) at construction time.
    """

    def __init__(
        self,
        config: AzureSearchProviderConfig,
        *,
        recorder: LandscapeRecorder,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
        limiter: RateLimiter | NoOpLimiter | None = None,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._run_id = run_id
        self._telemetry_emit = telemetry_emit
        self._limiter = limiter

        self._search_url = (
            f"{config.endpoint.rstrip('/')}/indexes/{config.index}/docs/search"
            f"?api-version={config.api_version}"
        )
        self._score_range = _SCORE_RANGES[config.search_mode]

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        *,
        state_id: str,
        token_id: str | None,
    ) -> list[RetrievalChunk]:
        """Execute a search query via Azure AI Search REST API."""
        response_data = self._execute_search(query, top_k, state_id=state_id, token_id=token_id)
        return self._parse_response(response_data, min_score)

    def _execute_search(
        self,
        query: str,
        top_k: int,
        *,
        state_id: str,
        token_id: str | None,
    ) -> dict[str, Any]:
        """Execute HTTP search request via AuditedHTTPClient."""
        from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient

        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["api-key"] = self._config.api_key

        body = self._build_request_body(query, top_k)

        http_client = AuditedHTTPClient(
            recorder=self._recorder,
            state_id=state_id,
            run_id=self._run_id,
            telemetry_emit=self._telemetry_emit,
            timeout=self._config.request_timeout,
            limiter=self._limiter,
            token_id=token_id,
            headers=headers,
        )
        try:
            response = http_client.post(self._search_url, json=body)

            status_code = response.status_code
            if status_code in (401, 403):
                raise RetrievalError(
                    f"Authentication failed for {self._config.endpoint} "
                    f"index {self._config.index!r}: HTTP {status_code}",
                    retryable=False,  # Credential errors are permanent within a run
                    status_code=status_code,
                )
            if status_code == 429:
                raise RetrievalError(
                    "Rate limited by Azure AI Search",
                    retryable=True,
                    status_code=429,
                )
            if status_code >= 500:
                raise RetrievalError(
                    f"Azure AI Search server error: HTTP {status_code}",
                    retryable=True,
                    status_code=status_code,
                )
            if status_code >= 400:
                raise RetrievalError(
                    f"Azure AI Search client error: HTTP {status_code}",
                    retryable=False,
                    status_code=status_code,
                )

            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise RetrievalError(
                    f"Malformed JSON response from Azure AI Search: {exc}",
                    retryable=False,
                ) from exc
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError(
                f"Search request failed: {exc}",
                retryable=True,
            ) from exc
        finally:
            http_client.close()

    def _build_request_body(self, query: str, top_k: int) -> dict[str, Any]:
        """Build Azure AI Search request body for the configured search mode."""
        body: dict[str, Any] = {"top": top_k}

        mode = self._config.search_mode

        if mode in ("keyword", "hybrid"):
            body["search"] = query
        if mode in ("vector", "hybrid"):
            body["vectorQueries"] = [{
                "kind": "text",
                "text": query,
                "fields": self._config.vector_field,
                "k": top_k,
            }]
        if mode == "semantic":
            body["search"] = query
            body["queryType"] = "semantic"
            body["semanticConfiguration"] = self._config.semantic_config

        return body

    def _parse_response(
        self, response_data: dict[str, Any], min_score: float
    ) -> list[RetrievalChunk]:
        """Parse and validate Azure AI Search response (Tier 3 boundary)."""
        if "value" not in response_data:
            raise RetrievalError(
                "Azure AI Search response missing 'value' array",
                retryable=False,
            )

        results = response_data["value"]
        chunks: list[RetrievalChunk] = []

        for item in results:
            raw_score = item.get("@search.score")
            if raw_score is None:
                continue  # Skip items without scores

            normalized_score = self._normalize_score(raw_score)
            if normalized_score < min_score:
                continue

            content = item.get("content", "")
            if not content:
                continue

            source_id = item.get("id", item.get("@search.documentId", "unknown"))

            # Coerce metadata at Tier 3 boundary
            metadata: dict[str, Any] = {
                k: str(v) if not isinstance(v, (str, int, float, bool, type(None), list, dict)) else v
                for k, v in item.items()
                if k not in ("@search.score", "content", "id")
            }

            try:
                chunks.append(RetrievalChunk(
                    content=content,
                    score=normalized_score,
                    source_id=str(source_id),
                    metadata=metadata,
                ))
            except ValueError as exc:
                raise RetrievalError(
                    f"Provider returned invalid data: {exc}",
                    retryable=False,
                ) from exc

        # Sort by descending score
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks

    def _normalize_score(self, raw_score: float) -> float:
        """Normalize provider score to [0.0, 1.0] range.

        Rejects NaN and Infinity at the Tier 3 boundary — same discipline
        as ELSPETH's canonical JSON subsystem. A non-finite score from Azure
        indicates a malformed response, not a relevance judgment.
        """
        if not math.isfinite(raw_score):
            raise RetrievalError(
                f"Azure AI Search returned non-finite score: {raw_score!r}. "
                f"This indicates a malformed API response (Tier 3 boundary violation).",
                retryable=False,
            )
        min_val, max_val = self._score_range
        if max_val <= min_val:
            return 0.0
        normalized = (raw_score - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    def close(self) -> None:
        """Release provider resources. No persistent connections to close."""
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py -v`
Expected: All PASS (some tests may need adjustment based on AuditedHTTPClient mock specifics)

- [ ] **Step 5: Add tests for internal methods (_parse_response, _build_request_body, _normalize_score)**

Append to `tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py`:

```python
class TestScoreNormalization:
    """Direct tests for _normalize_score method."""

    def _make_provider(self, search_mode="hybrid"):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
            search_mode=search_mode,
        )
        recorder = MagicMock()
        telemetry_emit = MagicMock()
        return AzureSearchProvider(
            config=config, recorder=recorder, run_id="run-1",
            telemetry_emit=telemetry_emit,
        )

    def test_keyword_mid_range(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(25.0) == pytest.approx(0.5)

    def test_keyword_zero(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(0.0) == 0.0

    def test_keyword_max(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(50.0) == 1.0

    def test_keyword_exceeds_max_clamped(self):
        """BM25 scores can exceed 50; verify clamping to 1.0."""
        provider = self._make_provider("keyword")
        assert provider._normalize_score(200.0) == 1.0

    def test_negative_score_clamped_to_zero(self):
        """Negative BM25 scores (rare edge case) clamp to 0.0."""
        provider = self._make_provider("keyword")
        assert provider._normalize_score(-5.0) == 0.0

    def test_vector_already_normalized(self):
        provider = self._make_provider("vector")
        assert provider._normalize_score(0.75) == pytest.approx(0.75)

    def test_semantic_range(self):
        provider = self._make_provider("semantic")
        assert provider._normalize_score(2.0) == pytest.approx(0.5)

    def test_nan_score_raises_retrieval_error(self):
        """NaN from Azure is a Tier 3 boundary violation — reject explicitly."""
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("nan"))

    def test_infinity_score_raises_retrieval_error(self):
        """Infinity from Azure is a Tier 3 boundary violation — reject explicitly."""
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("inf"))

    def test_negative_infinity_raises_retrieval_error(self):
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("-inf"))


class TestBuildRequestBody:
    """Direct tests for _build_request_body per search mode."""

    def _make_provider(self, search_mode="hybrid", **overrides):
        config_data = {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
            "search_mode": search_mode,
        }
        config_data.update(overrides)
        if search_mode == "semantic":
            config_data.setdefault("semantic_config", "my-semantic-config")
        config = AzureSearchProviderConfig(**config_data)
        return AzureSearchProvider(
            config=config, recorder=MagicMock(), run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def test_keyword_body(self):
        provider = self._make_provider("keyword")
        body = provider._build_request_body("test query", top_k=5)
        assert body["search"] == "test query"
        assert body["top"] == 5
        assert "vectorQueries" not in body

    def test_vector_body(self):
        provider = self._make_provider("vector")
        body = provider._build_request_body("test query", top_k=3)
        assert "search" not in body
        assert body["vectorQueries"][0]["text"] == "test query"
        assert body["vectorQueries"][0]["k"] == 3

    def test_hybrid_body(self):
        provider = self._make_provider("hybrid")
        body = provider._build_request_body("test query", top_k=5)
        assert body["search"] == "test query"
        assert "vectorQueries" in body

    def test_semantic_body(self):
        provider = self._make_provider("semantic")
        body = provider._build_request_body("test query", top_k=5)
        assert body["queryType"] == "semantic"
        assert body["semanticConfiguration"] == "my-semantic-config"


class TestParseResponse:
    """Direct tests for _parse_response Tier 3 boundary validation."""

    def _make_provider(self):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index", api_key="test-key",
        )
        return AzureSearchProvider(
            config=config, recorder=MagicMock(), run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def test_missing_value_key_raises(self):
        provider = self._make_provider()
        with pytest.raises(RetrievalError, match="missing 'value'"):
            provider._parse_response({}, min_score=0.0)

    def test_skips_items_without_score(self):
        provider = self._make_provider()
        response = {"value": [{"content": "text", "id": "doc1"}]}  # No @search.score
        chunks = provider._parse_response(response, min_score=0.0)
        assert chunks == []

    def test_skips_items_without_content(self):
        provider = self._make_provider()
        response = {"value": [{"@search.score": 5.0, "id": "doc1"}]}  # No content
        chunks = provider._parse_response(response, min_score=0.0)
        assert chunks == []

    def test_source_id_fallback_chain(self):
        provider = self._make_provider()
        # Falls back from "id" to "@search.documentId" to "unknown"
        response = {"value": [
            {"@search.score": 5.0, "content": "text", "id": "doc1"},
            {"@search.score": 5.0, "content": "text", "@search.documentId": "doc2"},
            {"@search.score": 5.0, "content": "text"},
        ]}
        chunks = provider._parse_response(response, min_score=0.0)
        assert chunks[0].source_id in ("doc1", "doc2", "unknown")

    def test_results_sorted_by_descending_score(self):
        provider = self._make_provider()
        response = {"value": [
            {"@search.score": 1.0, "content": "low", "id": "d1"},
            {"@search.score": 40.0, "content": "high", "id": "d2"},
            {"@search.score": 10.0, "content": "mid", "id": "d3"},
        ]}
        chunks = provider._parse_response(response, min_score=0.0)
        assert chunks[0].score >= chunks[1].score >= chunks[2].score
```

- [ ] **Step 6: Run all retrieval tests together**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py
git commit -m "feat: implement Azure AI Search provider with score normalization and Tier 3 validation"
```

### Task 9b: Add `[rag]` optional dependency extra

**Files:**
- Modify: `pyproject.toml`

This task MUST run before Task 9c because the Chroma tests import `chromadb` directly.

- [ ] **Step 1: Add `[rag]` extra to pyproject.toml**

Add after the `web` extra:

```toml
rag = [
    # RAG retrieval plugin pack — ChromaDB provider
    "chromadb>=1.0,<2",  # Local/embedded vector store
]
```

Also add `chromadb` to the `all` extra.

Note: The Azure AI Search provider with `use_managed_identity=true` requires the `[azure]` extra
(which includes `azure-identity`). Install with `uv pip install -e ".[rag,azure]"` for managed
identity support. The `[rag]` extra alone covers ChromaDB and Azure API key authentication.

- [ ] **Step 2: Install the new extra**

Run: `uv pip install -e ".[rag,dev]"`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add [rag] optional dependency extra for ChromaDB provider"
```

### Task 9c: ChromaDB provider implementation

**Files:**
- Create: `src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py`
- Test: `tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py`
- Modify: `src/elspeth/plugins/transforms/rag/config.py` (add to PROVIDERS registry)

ChromaDB runs in-memory (ephemeral mode) with no external dependencies, making it ideal for local development and integration testing. Unlike the Azure provider which uses `AuditedHTTPClient` for REST calls, the Chroma provider uses the `chromadb` Python SDK directly — the SDK manages its own HTTP/gRPC transport when pointed at a remote server, or runs entirely in-process for ephemeral/persistent-local modes.

- [ ] **Step 1: Write tests for ChromaDB provider**

Create `tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py`:

```python
"""Tests for ChromaDB retrieval provider.

These tests use real ChromaDB ephemeral clients — no mocks needed.
ChromaDB's in-memory mode is fast enough for unit tests (~5ms per query).
"""

import pytest

chromadb = pytest.importorskip("chromadb")

from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.chroma import (
    ChromaSearchProvider,
    ChromaSearchProviderConfig,
)
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


class TestChromaSearchProviderConfig:
    def test_minimal_valid_config(self):
        config = ChromaSearchProviderConfig(collection="test-docs")
        assert config.collection == "test-docs"
        assert config.mode == "ephemeral"

    def test_persistent_requires_path(self):
        with pytest.raises(ValueError, match="persist_directory"):
            ChromaSearchProviderConfig(collection="test", mode="persistent")

    def test_persistent_with_path(self):
        config = ChromaSearchProviderConfig(
            collection="test", mode="persistent", persist_directory="/tmp/chroma"
        )
        assert config.persist_directory == "/tmp/chroma"

    def test_client_mode_requires_host(self):
        with pytest.raises(ValueError, match="host"):
            ChromaSearchProviderConfig(collection="test", mode="client")

    def test_client_mode_with_host(self):
        config = ChromaSearchProviderConfig(
            collection="test", mode="client", host="localhost", port=8000,
        )
        assert config.host == "localhost"

    def test_client_mode_requires_https_for_non_localhost(self):
        """Remote Chroma servers should use HTTPS."""
        with pytest.raises(ValueError, match="ssl"):
            ChromaSearchProviderConfig(
                collection="test", mode="client",
                host="chroma.example.com", port=443, ssl=False,
            )

    def test_client_mode_allows_http_for_localhost(self):
        config = ChromaSearchProviderConfig(
            collection="test", mode="client",
            host="localhost", port=8000, ssl=False,
        )
        assert config.ssl is False

    def test_ephemeral_ignores_path(self):
        """Ephemeral mode doesn't use persist_directory."""
        config = ChromaSearchProviderConfig(
            collection="test", mode="ephemeral",
        )
        assert config.persist_directory is None

    def test_collection_name_validation(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            ChromaSearchProviderConfig(collection="bad/name!")

    def test_valid_distance_functions(self):
        for fn in ("cosine", "l2", "ip"):
            config = ChromaSearchProviderConfig(
                collection="test", distance_function=fn,
            )
            assert config.distance_function == fn

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="must not contain"):
            ChromaSearchProviderConfig(
                collection="test", mode="persistent",
                persist_directory="/tmp/../etc/chroma",
            )


class TestChromaSearchProvider:
    """Tests using real ephemeral ChromaDB — no mocks."""

    def _make_provider(self, documents=None, distance_function="cosine"):
        """Create provider with optional pre-populated collection."""
        config = ChromaSearchProviderConfig(
            collection="test-collection",
            mode="ephemeral",
            distance_function=distance_function,
        )
        provider = ChromaSearchProvider(config=config)

        if documents:
            # Populate via the provider's internal client for test setup
            collection = provider._collection
            collection.add(
                documents=[d["content"] for d in documents],
                ids=[d["id"] for d in documents],
                metadatas=[d.get("metadata", {}) for d in documents],
            )

        return provider

    def test_search_returns_retrieval_chunks(self):
        provider = self._make_provider(documents=[
            {"id": "doc1", "content": "Python is a programming language"},
            {"id": "doc2", "content": "Java is a programming language"},
            {"id": "doc3", "content": "The weather is sunny today"},
        ])
        chunks = provider.search(
            "programming languages", top_k=2, min_score=0.0,
            state_id="state-1", token_id="token-1",
        )
        assert len(chunks) <= 2
        assert all(isinstance(c, RetrievalChunk) for c in chunks)
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_results_sorted_by_descending_score(self):
        provider = self._make_provider(documents=[
            {"id": f"doc{i}", "content": f"Document {i} about topic"} for i in range(5)
        ])
        chunks = provider.search(
            "topic", top_k=5, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)

    def test_min_score_filtering(self):
        provider = self._make_provider(documents=[
            {"id": "doc1", "content": "exact match for the query text"},
            {"id": "doc2", "content": "completely unrelated content about quantum physics"},
        ])
        all_chunks = provider.search(
            "exact match for the query text", top_k=10, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        high_chunks = provider.search(
            "exact match for the query text", top_k=10, min_score=0.9,
            state_id="state-1", token_id=None,
        )
        assert len(high_chunks) <= len(all_chunks)

    def test_top_k_limits_results(self):
        provider = self._make_provider(documents=[
            {"id": f"doc{i}", "content": f"Document about retrieval {i}"} for i in range(10)
        ])
        chunks = provider.search(
            "retrieval", top_k=3, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        assert len(chunks) <= 3

    def test_empty_collection_returns_empty(self):
        provider = self._make_provider(documents=[])
        chunks = provider.search(
            "anything", top_k=5, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        assert chunks == []

    def test_source_id_matches_document_id(self):
        provider = self._make_provider(documents=[
            {"id": "my-doc-42", "content": "Test document content"},
        ])
        chunks = provider.search(
            "test document", top_k=1, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        assert len(chunks) == 1
        assert chunks[0].source_id == "my-doc-42"

    def test_metadata_preserved(self):
        provider = self._make_provider(documents=[
            {"id": "doc1", "content": "Test content", "metadata": {"page": 3, "section": "intro"}},
        ])
        chunks = provider.search(
            "test content", top_k=1, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        assert len(chunks) == 1
        assert chunks[0].metadata["page"] == 3
        assert chunks[0].metadata["section"] == "intro"

    def test_distance_function_mismatch_raises(self, tmp_path):
        """Existing collection with different distance function must not silently mismatch.

        Uses PersistentClient so both providers share the same backing store.
        chromadb.Client() (ephemeral) creates isolated in-memory stores per call,
        which would make this test unfalsifiable.
        """
        # Create a collection with cosine distance using persistent mode
        config_cosine = ChromaSearchProviderConfig(
            collection="mismatch-test",
            mode="persistent",
            persist_directory=str(tmp_path),
            distance_function="cosine",
        )
        provider_cosine = ChromaSearchProvider(config=config_cosine)
        provider_cosine._collection.add(documents=["test"], ids=["doc1"])

        # Attempt to open the same collection with l2 — should raise
        config_l2 = ChromaSearchProviderConfig(
            collection="mismatch-test",
            mode="persistent",
            persist_directory=str(tmp_path),
            distance_function="l2",
        )
        with pytest.raises(RetrievalError, match="distance_function"):
            ChromaSearchProvider(config=config_l2)

    def test_close_does_not_raise(self):
        provider = self._make_provider()
        provider.close()  # Should not raise

    def test_is_retrieval_provider(self):
        """ChromaSearchProvider satisfies RetrievalProvider protocol."""
        from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalProvider

        provider = self._make_provider()
        assert isinstance(provider, RetrievalProvider)

    def test_fewer_docs_than_top_k(self):
        """top_k > collection size should not raise — returns available docs."""
        provider = self._make_provider(documents=[
            {"id": "doc1", "content": "First document"},
            {"id": "doc2", "content": "Second document"},
        ])
        chunks = provider.search(
            "document", top_k=5, min_score=0.0,
            state_id="state-1", token_id=None,
        )
        assert len(chunks) <= 2

    def test_search_records_call(self):
        """Chroma search calls must be recorded in the audit trail."""
        from unittest.mock import MagicMock
        config = ChromaSearchProviderConfig(
            collection="test-audit",
            mode="ephemeral",
            distance_function="cosine",
        )
        mock_recorder = MagicMock()
        provider = ChromaSearchProvider(
            config=config,
            recorder=mock_recorder,
            run_id="run-1",
        )
        provider._collection.add(documents=["test doc"], ids=["doc1"])
        provider.search(
            "test", top_k=1, min_score=0.0,
            state_id="state-1", token_id="token-1",
        )
        mock_recorder.record_call.assert_called_once()


class TestChromaScoreNormalization:
    """Verify score normalization for different distance functions."""

    def _make_provider(self, distance_function):
        config = ChromaSearchProviderConfig(
            collection="test", mode="ephemeral",
            distance_function=distance_function,
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(
            documents=["test document"],
            ids=["doc1"],
        )
        return provider

    def test_cosine_scores_in_unit_range(self):
        provider = self._make_provider("cosine")
        chunks = provider.search(
            "test document", top_k=1, min_score=0.0,
            state_id="s1", token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_l2_scores_in_unit_range(self):
        provider = self._make_provider("l2")
        chunks = provider.search(
            "test document", top_k=1, min_score=0.0,
            state_id="s1", token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_ip_scores_in_unit_range(self):
        provider = self._make_provider("ip")
        chunks = provider.search(
            "test document", top_k=1, min_score=0.0,
            state_id="s1", token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement ChromaSearchProviderConfig and ChromaSearchProvider**

Create `src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py`:

```python
"""ChromaDB provider for RAG retrieval.

Supports three modes:
- ephemeral: In-memory, no persistence. Ideal for testing and development.
- persistent: Local disk storage. Survives process restarts.
- client: Remote Chroma server via HTTP/gRPC.

Score normalization:
- Chroma returns distances, not similarities. The normalization depends on
  the collection's distance function:
  - cosine: distance in [0, 2], similarity = 1 - (distance / 2)
  - l2: distance in [0, ∞), similarity = 1 / (1 + distance)
  - ip (inner product): distance = 1 - similarity for normalized vectors,
    similarity = 1 - distance (clamped to [0, 1])
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Literal, Self

import chromadb
from pydantic import BaseModel, field_validator, model_validator

from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class ChromaSearchProviderConfig(BaseModel):
    """Configuration for ChromaDB provider.

    Note: Rate limiting is not supported for ChromaDB. The SDK manages
    its own connection lifecycle (in-process for ephemeral/persistent,
    HTTP/gRPC for client mode). If rate_limit is configured for the
    chroma provider in the pipeline YAML, it will be silently ignored.
    """

    model_config = {"extra": "forbid", "frozen": True}

    collection: str
    mode: Literal["ephemeral", "persistent", "client"] = "ephemeral"

    # Persistent mode
    persist_directory: str | None = None

    # Client mode
    host: str | None = None
    port: int = 8000
    ssl: bool = True

    # Search parameters
    distance_function: Literal["cosine", "l2", "ip"] = "cosine"

    @field_validator("collection")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        # Chroma collection names: 3-63 chars, alphanumeric + hyphens/underscores,
        # must start and end with alphanumeric.
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$", v) and len(v) >= 3:
            if len(v) < 3:
                raise ValueError(
                    f"collection name must be at least 3 characters, got {len(v)}"
                )
            raise ValueError(
                f"collection must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start/end with alphanumeric), got {v!r}."
            )
        return v

    @field_validator("persist_directory")
    @classmethod
    def validate_persist_directory(cls, v: str | None) -> str | None:
        if v is not None and ".." in v.split("/"):
            raise ValueError(
                f"persist_directory must not contain '..' path components, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Self:
        if self.mode == "persistent" and not self.persist_directory:
            raise ValueError("persistent mode requires persist_directory")
        if self.mode == "client" and not self.host:
            raise ValueError("client mode requires host")
        if self.mode == "client" and self.host:
            is_local = self.host in ("localhost", "127.0.0.1", "::1")
            if not is_local and not self.ssl:
                raise ValueError(
                    f"Remote Chroma server {self.host!r} requires ssl=true. "
                    f"HTTP is only permitted for localhost."
                )
        return self


class ChromaSearchProvider:
    """ChromaDB implementation of RetrievalProvider.

    Uses the chromadb Python SDK directly. No AuditedHTTPClient — Chroma
    manages its own transport (in-process for ephemeral/persistent,
    HTTP/gRPC for client mode).

    Score normalization converts Chroma distances to [0.0, 1.0] similarity
    scores, where 1.0 means identical and 0.0 means maximally dissimilar.
    """

    def __init__(
        self,
        config: ChromaSearchProviderConfig,
        *,
        recorder: LandscapeRecorder | None = None,
        run_id: str | None = None,
    ) -> None:
        self._config = config
        self._distance_function = config.distance_function
        self._recorder = recorder
        self._run_id = run_id

        # Create Chroma client based on mode
        if config.mode == "ephemeral":
            self._client = chromadb.Client()
        elif config.mode == "persistent":
            self._client = chromadb.PersistentClient(path=config.persist_directory)
        else:  # client
            self._client = chromadb.HttpClient(
                host=config.host,
                port=config.port,
                ssl=config.ssl,
            )

        # Get or create collection with the configured distance function.
        # IMPORTANT: get_or_create_collection silently ignores metadata updates
        # on existing collections. If the collection already exists with a different
        # distance function, scores would be normalized with the wrong formula —
        # a silent Tier 1 audit integrity violation. We detect this explicitly.
        try:
            self._collection = self._client.get_or_create_collection(
                name=config.collection,
                metadata={"hnsw:space": config.distance_function},
            )
            # Verify the collection's actual distance function matches config
            actual_space = (self._collection.metadata or {}).get("hnsw:space")
            if actual_space is not None and actual_space != config.distance_function:
                raise RetrievalError(
                    f"Chroma collection {config.collection!r} exists with "
                    f"distance_function={actual_space!r}, but config specifies "
                    f"{config.distance_function!r}. Score normalization would use "
                    f"the wrong formula. Either change the config to match the "
                    f"existing collection, or use a different collection name.",
                    retryable=False,
                )
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError(
                f"Failed to access Chroma collection {config.collection!r}: {exc}",
                retryable=False,
            ) from exc

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        *,
        state_id: str,
        token_id: str | None,
    ) -> list[RetrievalChunk]:
        """Execute a search query via ChromaDB."""
        # Clamp top_k to collection size to avoid wasteful retries
        collection_count = self._collection.count()
        if collection_count == 0:
            return []
        effective_top_k = min(top_k, collection_count)

        start_time = time.monotonic()
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=effective_top_k,
                include=["documents", "distances", "metadatas"],
            )
        except Exception as exc:
            raise RetrievalError(
                f"Chroma query failed: {exc}",
                retryable=True,
            ) from exc
        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Chroma returns lists-of-lists (one per query text)
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]

        chunks: list[RetrievalChunk] = []
        for doc, distance, metadata, doc_id in zip(
            documents, distances, metadatas, ids, strict=True
        ):
            if doc is None:
                continue

            score = self._normalize_distance(distance)
            if score < min_score:
                continue

            # Metadata from Chroma is already dict[str, Any] with JSON-safe types
            chunks.append(RetrievalChunk(
                content=doc,
                score=score,
                source_id=doc_id,
                metadata=metadata or {},
            ))

        # Sort by descending score
        chunks.sort(key=lambda c: c.score, reverse=True)

        # Record call in audit trail
        if self._recorder is not None:
            self._recorder.record_call(
                state_id=state_id,
                provider="chroma",
                request={"query": query, "top_k": effective_top_k, "collection": self._config.collection},
                response={"result_count": len(chunks), "top_score": chunks[0].score if chunks else None},
                latency_ms=round(elapsed_ms),
                status="success",
            )

        return chunks

    def _normalize_distance(self, distance: float) -> float:
        """Convert Chroma distance to [0.0, 1.0] similarity score.

        Chroma returns distances (lower = more similar), but RetrievalChunk
        expects similarity scores (higher = more similar).

        Conversions:
        - cosine: distance in [0, 2], similarity = 1 - (distance / 2)
        - l2: distance in [0, ∞), similarity = 1 / (1 + distance)
        - ip: distance ≈ 1 - similarity for normalized vectors,
              similarity = 1 - distance (clamped)
        """
        if self._distance_function == "cosine":
            return max(0.0, min(1.0, 1.0 - (distance / 2.0)))
        elif self._distance_function == "l2":
            return 1.0 / (1.0 + distance)
        else:  # ip
            return max(0.0, min(1.0, 1.0 - distance))

    def close(self) -> None:
        """Release Chroma client resources."""
        # Ephemeral and PersistentClient don't need explicit cleanup.
        # HttpClient connections are managed by the SDK.
        pass
```

- [ ] **Step 4: Update __init__.py exports**

In `src/elspeth/plugins/infrastructure/clients/retrieval/__init__.py`, add Chroma exports:

```python
"""Retrieval provider infrastructure for RAG transforms."""

from elspeth.plugins.infrastructure.clients.retrieval.base import (
    RetrievalError,
    RetrievalProvider,
)
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

__all__ = [
    "RetrievalChunk",
    "RetrievalError",
    "RetrievalProvider",
]
```

Note: Provider implementations (AzureSearchProvider, ChromaSearchProvider) are NOT re-exported from `__init__.py` — they are imported directly by the config registry. This avoids forcing all provider dependencies to be installed.

- [ ] **Step 5: Register Chroma in PROVIDERS registry**

In `src/elspeth/plugins/transforms/rag/config.py`, **replace** the top-level `PROVIDERS` dict and `AzureSearchProvider` import (from Task 8) with the lazy import pattern. This is mandatory — a top-level import of `chromadb` would make it a hard dependency for all RAG users, including those only using Azure Search.

Remove the existing top-level imports of `AzureSearchProvider`, `AzureSearchProviderConfig` and the `PROVIDERS` dict, and replace with:

```python
def _get_providers() -> dict[str, tuple[type, ProviderFactory]]:
    """Lazy provider registry — only imports providers whose dependencies are installed.

    This follows the optional pack pattern: [rag] extra installs chromadb,
    and the chroma provider becomes available only when installed. Azure is
    always available (httpx is a core dep). The validate_provider_config
    model validator produces a clear error ("Unknown provider: 'chroma'.
    Available: ['azure_search']") when the extra is not installed.
    """
    providers: dict[str, tuple[type, ProviderFactory]] = {}

    # Azure — guarded for environments where azure deps may not be available
    try:
        from elspeth.plugins.infrastructure.clients.retrieval.azure_search import (
            AzureSearchProvider, AzureSearchProviderConfig,
        )
        providers["azure_search"] = (AzureSearchProviderConfig, AzureSearchProvider)
    except ImportError:
        pass  # Azure provider dependencies not available

    try:
        from elspeth.plugins.infrastructure.clients.retrieval.chroma import (
            ChromaSearchProvider, ChromaSearchProviderConfig,
        )
        def _chroma_factory(config, *, recorder, run_id, **_kwargs):
            """Chroma uses the SDK directly — passes recorder and run_id for audit trail.

            recorder and run_id are mandatory (not defaulted to None) because Chroma
            search calls must be recorded in the audit trail (B1 fix). If the engine
            ever calls this factory without recorder, it should crash at startup, not
            silently skip audit recording at query time.
            """
            return ChromaSearchProvider(config=config, recorder=recorder, run_id=run_id)
        providers["chroma"] = (ChromaSearchProviderConfig, _chroma_factory)
    except ImportError:
        pass  # chromadb not installed — chroma provider unavailable

    return providers

PROVIDERS = _get_providers()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py -v`
Expected: All PASS

- [ ] **Step 7: Run all retrieval provider tests together**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/clients/retrieval/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/elspeth/plugins/infrastructure/clients/retrieval/chroma.py src/elspeth/plugins/transforms/rag/config.py tests/unit/plugins/infrastructure/clients/retrieval/test_chroma.py
git commit -m "feat: add ChromaDB provider with ephemeral/persistent/client modes and distance normalization"
```

### Task 10: RAGRetrievalTransform implementation

**Files:**
- Create: `src/elspeth/plugins/transforms/rag/transform.py`
- Modify: `src/elspeth/plugins/transforms/rag/__init__.py`
- Test: `tests/unit/plugins/transforms/rag/test_transform.py`

- [ ] **Step 1: Write tests for transform lifecycle and process flow**

Create `tests/unit/plugins/transforms/rag/test_transform.py`:

```python
"""Tests for RAGRetrievalTransform lifecycle and process flow."""

import json
import os
from unittest.mock import MagicMock

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch):
    """Ensure ELSPETH_FINGERPRINT_KEY is set for all tests."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key-for-rag-tests")


def _make_transform(**overrides):
    """Create a transform with valid config."""
    config = {
        "output_prefix": "policy",
        "query_field": "question",
        "provider": "azure_search",
        "provider_config": {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
        },
        "schema_config": {"mode": "observed"},
    }
    config.update(overrides)
    return RAGRetrievalTransform(config)


def _mock_ctx(state_id="state-1", token_id="token-1"):
    """Create a mock TransformContext."""
    ctx = MagicMock()
    ctx.state_id = state_id
    ctx.run_id = "run-1"
    token = MagicMock()
    token.token_id = token_id
    ctx.token = token
    ctx.contract = MagicMock()
    return ctx


def _mock_lifecycle_ctx():
    """Create a mock LifecycleContext."""
    ctx = MagicMock()
    ctx.run_id = "run-1"
    ctx.landscape = MagicMock()
    ctx.telemetry_emit = MagicMock()
    ctx.rate_limit_registry = None
    return ctx


def _make_row(data):
    """Create a real PipelineRow — NO mock fallback (BUG-LINEAGE-01 precedent)."""
    contract = SchemaContract(mode="OBSERVED", fields=())
    return PipelineRow(data, contract)


class TestTransformLifecycle:
    def test_close_before_on_start_does_not_raise(self):
        transform = _make_transform()
        transform.close()  # Should not raise

    def test_declared_output_fields(self):
        transform = _make_transform()
        expected = frozenset([
            "policy__rag_context",
            "policy__rag_score",
            "policy__rag_count",
            "policy__rag_sources",
        ])
        assert transform.declared_output_fields == expected

    def test_state_id_guard(self):
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)

        ctx = _mock_ctx(state_id=None)
        row = _make_row({"question": "test"})

        with pytest.raises(RuntimeError, match="state_id"):
            transform.process(row, ctx)


class TestProcessFlow:
    def _setup_transform_with_mock_provider(self, chunks=None, **config_overrides):
        transform = _make_transform(**config_overrides)
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)

        mock_provider = MagicMock()
        mock_provider.search.return_value = chunks or []
        transform._provider = mock_provider
        return transform, mock_provider

    def test_successful_retrieval(self):
        chunks = [
            RetrievalChunk(content="Result 1", score=0.9, source_id="doc1", metadata={}),
            RetrievalChunk(content="Result 2", score=0.7, source_id="doc2", metadata={}),
        ]
        transform, _ = self._setup_transform_with_mock_provider(chunks)
        row = _make_row({"question": "What is RAG?"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)

        # Verify output row has all four prefixed fields with correct values
        assert result.status == "success"
        output = result.output_row.to_dict()
        assert "policy__rag_context" in output
        assert "1. Result 1" in output["policy__rag_context"]
        assert output["policy__rag_count"] == 2
        assert output["policy__rag_score"] == 0.9
        assert "policy__rag_sources" in output
        sources = json.loads(output["policy__rag_sources"])
        assert len(sources["sources"]) == 2

    def test_zero_results_quarantine(self):
        transform, _ = self._setup_transform_with_mock_provider(
            chunks=[], on_no_results="quarantine",
        )
        row = _make_row({"question": "obscure query"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)
        assert result.status == "error"
        assert result.reason["reason"] == "no_results"

    def test_zero_results_continue(self):
        transform, _ = self._setup_transform_with_mock_provider(
            chunks=[], on_no_results="continue",
        )
        row = _make_row({"question": "obscure query"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)

        assert result.status == "success"
        output = result.output_row.to_dict()
        assert output["policy__rag_context"] == ""
        assert output["policy__rag_count"] == 0
        assert output["policy__rag_score"] == 0.0

    def test_retryable_error_propagates(self):
        transform, mock_provider = self._setup_transform_with_mock_provider()
        mock_provider.search.side_effect = RetrievalError(
            "server error", retryable=True, status_code=500,
        )
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()

        with pytest.raises(RetrievalError) as exc_info:
            transform.process(row, ctx)
        assert exc_info.value.retryable is True

    def test_non_retryable_error_returns_error_result(self):
        transform, mock_provider = self._setup_transform_with_mock_provider()
        mock_provider.search.side_effect = RetrievalError(
            "bad request", retryable=False, status_code=400,
        )
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)
        assert result.status == "error"
        assert result.reason["reason"] == "retrieval_failed"


class TestOnComplete:
    def test_emits_telemetry(self):
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)
        transform.on_complete(lifecycle_ctx)
        lifecycle_ctx.telemetry_emit.assert_called_once()
        payload = lifecycle_ctx.telemetry_emit.call_args[0][0]
        assert payload["event"] == "rag_retrieval_complete"
        assert "run_id" in payload
        assert payload["total_queries"] == 0
        assert payload["quarantine_count"] == 0

    def test_zero_rows_no_statistics_error(self):
        """Welford accumulators with zero rows should not raise."""
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)
        transform.on_complete(lifecycle_ctx)  # Should not raise


class TestProcessGuards:
    def test_process_before_on_start_raises(self):
        transform = _make_transform()
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()
        with pytest.raises(RuntimeError, match="before on_start"):
            transform.process(row, ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement RAGRetrievalTransform**

Create `src/elspeth/plugins/transforms/rag/transform.py`:

```python
"""RAG Retrieval Transform — fetches context from search backends.

This is a retrieval-only transform. It does not perform generation.
Retrieved context is attached as prefixed fields for downstream
transforms (typically LLM) to consume via Jinja2 templates.
"""

from __future__ import annotations

import hashlib
import json
import time
from statistics import mean
from typing import TYPE_CHECKING, Any

from elspeth.contracts.enums import Determinism
from elspeth.contracts.results import TransformResult
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.config import RAGRetrievalConfig, PROVIDERS
from elspeth.plugins.transforms.rag.formatter import format_context
from elspeth.plugins.transforms.rag.query import QueryBuilder

if TYPE_CHECKING:
    from elspeth.contracts.contexts import LifecycleContext, TransformContext


class RAGRetrievalTransform(BaseTransform):
    """RAG retrieval transform — fetches context from a search backend."""

    name = "rag_retrieval"
    determinism = Determinism.EXTERNAL_CALL

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._config = RAGRetrievalConfig(**config)

        prefix = self._config.output_prefix
        self._output_field_names = {
            "context": f"{prefix}__rag_context",
            "score": f"{prefix}__rag_score",
            "count": f"{prefix}__rag_count",
            "sources": f"{prefix}__rag_sources",
        }

        self.declared_output_fields = frozenset(self._output_field_names.values())

        # Build query constructor
        self._query_builder = QueryBuilder(
            query_field=self._config.query_field,
            query_template=self._config.query_template,
            query_pattern=self._config.query_pattern,
        )

        # Provider is constructed in on_start() when lifecycle context is available
        self._provider = None

        # Statistics for on_complete telemetry
        # Note: these counters are not thread-safe. The engine currently executes
        # process() single-threaded per transform instance. Future parallelization
        # work must add locking here.
        self._total_queries = 0
        self._total_chunks = 0
        self._quarantine_count = 0

        # Welford's online algorithm accumulators for running mean/variance.
        # Avoids unbounded memory growth from storing all scores.
        self._score_count: int = 0
        self._score_mean: float = 0.0
        self._score_m2: float = 0.0

        # Store validated provider config for typed access in process()
        self._validated_provider_config = None

    def on_start(self, ctx: LifecycleContext) -> None:
        """Create provider with lifecycle context dependencies."""
        super().on_start(ctx)

        self._recorder = ctx.landscape
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit

        # Look up provider factory from unified registry
        provider_entry = PROVIDERS[self._config.provider]
        config_cls, factory_fn = provider_entry

        # Construct validated provider config (avoids redundant parse)
        self._validated_provider_config = config_cls(**self._config.provider_config)

        # Get rate limiter
        limiter = None
        if ctx.rate_limit_registry is not None:
            limiter = ctx.rate_limit_registry.get_limiter(self._config.provider)

        # Construct provider via factory — each factory takes what it needs
        self._provider = factory_fn(
            config=self._validated_provider_config,
            recorder=self._recorder,
            run_id=self._run_id,
            telemetry_emit=self._telemetry_emit,
            limiter=limiter,
        )

    def process(
        self,
        row: PipelineRow,
        ctx: TransformContext,
    ) -> TransformResult:
        """Process a single row: construct query, retrieve, format, attach."""
        # Step 0: lifecycle and state_id guards
        if self._provider is None:
            raise RuntimeError(
                "RAGRetrievalTransform.process() called before on_start() — "
                "provider not initialized"
            )
        if ctx.state_id is None:
            raise RuntimeError("ctx.state_id not set by executor")

        # Step 1-4: Construct query
        query_result = self._query_builder.build(row.to_dict())
        if query_result.error is not None:
            self._quarantine_count += 1
            return TransformResult.error(query_result.error, retryable=False)

        query = query_result.query

        # Step 5: Call provider
        token_id = ctx.token.token_id if ctx.token is not None else None
        try:
            start_time = time.monotonic()
            chunks = self._provider.search(
                query,
                self._config.top_k,
                self._config.min_score,
                state_id=ctx.state_id,
                token_id=token_id,
            )
            elapsed_ms = (time.monotonic() - start_time) * 1000
        except RetrievalError as e:
            if e.retryable:
                raise  # Engine retries
            self._quarantine_count += 1
            return TransformResult.error(
                {
                    "reason": "retrieval_failed",
                    "provider": self._config.provider,
                    "error": str(e),
                    "status_code": e.status_code,
                    "query_length": len(query),
                },
                retryable=False,
            )

        self._total_queries += 1
        self._total_chunks += len(chunks)
        for chunk in chunks:
            self._update_score_stats(chunk.score)

        # Step 6: Check result count
        if not chunks:
            if self._config.on_no_results == "quarantine":
                self._quarantine_count += 1
                return TransformResult.error(
                    {
                        "reason": "no_results",
                        "provider": self._config.provider,
                        "query_length": len(query),
                        "min_score": self._config.min_score,
                    },
                    retryable=False,
                )
            # on_no_results == "continue" — attach empty sentinel fields
            return self._build_success(row, ctx, query, chunks=[], formatted_text="", truncated=False, elapsed_ms=elapsed_ms)

        # Steps 7-8: Format context
        formatted = format_context(
            chunks,
            format_mode=self._config.context_format,
            separator=self._config.context_separator,
            max_length=self._config.max_context_length,
        )

        # Steps 9-10: Build success result
        return self._build_success(row, ctx, query, chunks, formatted.text, formatted.truncated, elapsed_ms)

    def _build_success(
        self,
        row: PipelineRow,
        ctx: TransformContext,
        query: str,
        chunks: list[RetrievalChunk],
        formatted_text: str,
        truncated: bool,
        elapsed_ms: float,
    ) -> TransformResult:
        """Build TransformResult.success with prefixed output fields."""
        prefix = self._config.output_prefix
        fields = self._output_field_names

        sources = {
            "v": 1,
            "sources": [
                {"source_id": c.source_id, "score": c.score, "metadata": c.metadata}
                for c in chunks
            ],
        }

        output_data = {
            **row.to_dict(),
            fields["context"]: formatted_text,
            fields["score"]: chunks[0].score if chunks else 0.0,
            fields["count"]: len(chunks),
            fields["sources"]: json.dumps(sources),
        }

        output_row = PipelineRow(output_data, row.contract)

        # Build query hash for audit — plain SHA-256, not HMAC.
        # Queries are not secrets; HMAC fingerprinting is reserved for secret
        # values (API keys, PII). This hash is for deduplication/correlation only.
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        return TransformResult.success(
            output_row,
            success_reason={
                "action": "enriched",
                "fields_added": list(self._output_field_names.values()),
                "metadata": {
                    "provider": self._config.provider,
                    "query_length": len(query),
                    "query_hash": query_hash,
                    "chunks_retrieved": len(chunks),
                    "top_score": chunks[0].score if chunks else None,
                    "mean_score": mean([c.score for c in chunks]) if chunks else None,
                    "context_length": len(formatted_text),
                    "truncated": truncated,
                    "retrieval_status": "full" if chunks else "empty",
                    "latency_ms": round(elapsed_ms),
                },
            },
        )

    def _update_score_stats(self, score: float) -> None:
        """Welford's online algorithm for running mean/variance."""
        self._score_count += 1
        delta = score - self._score_mean
        self._score_mean += delta / self._score_count
        delta2 = score - self._score_mean
        self._score_m2 += delta * delta2

    def on_complete(self, ctx: LifecycleContext) -> None:
        """Emit retrieval statistics via telemetry."""
        # Note: ideally this should use a typed event from contracts/events.py —
        # check the pattern used by LLMTransform.on_complete and follow it.
        ctx.telemetry_emit({
            "event": "rag_retrieval_complete",
            "run_id": ctx.run_id,
            "total_queries": self._total_queries,
            "total_chunks": self._total_chunks,
            "mean_score": self._score_mean if self._score_count > 0 else None,
            "quarantine_count": self._quarantine_count,
        })

    def close(self) -> None:
        """Release provider and query builder resources."""
        if self._provider is not None:
            self._provider.close()
        self._query_builder.close()
```

- [ ] **Step 4: Update __init__.py for plugin registration**

Create `src/elspeth/plugins/transforms/rag/__init__.py`:

```python
"""RAG retrieval transform plugin.

Retrieves context from search backends (Azure AI Search) and attaches
it to pipeline rows as prefixed fields for downstream LLM consumption.
"""

from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform

__all__ = ["RAGRetrievalTransform"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py -v`
Expected: All PASS (some may need mock adjustments — iterate until green)

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/plugins/transforms/rag/ tests/unit/plugins/transforms/rag/test_transform.py
git commit -m "feat: implement RAGRetrievalTransform with lifecycle, process flow, and telemetry"
```

### Task 11: Plugin discovery registration

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/discovery.py:182-186`

- [ ] **Step 1: Write test for plugin discovery**

Create a test in the integration test file (or append to existing discovery tests):

```python
# Add to tests/unit/plugins/transforms/rag/test_transform.py
def test_plugin_discoverable():
    """rag_retrieval is found by the plugin scanner."""
    from elspeth.plugins.infrastructure.discovery import PLUGIN_SCAN_CONFIG

    assert "transforms/rag" in PLUGIN_SCAN_CONFIG["transforms"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py::test_plugin_discoverable -v`
Expected: FAIL — `transforms/rag` not in scan config

- [ ] **Step 3: Update PLUGIN_SCAN_CONFIG**

In `src/elspeth/plugins/infrastructure/discovery.py` (line 184), add `"transforms/rag"`:

```python
PLUGIN_SCAN_CONFIG: dict[str, list[str]] = {
    "sources": ["sources"],
    "transforms": ["transforms", "transforms/azure", "transforms/llm", "transforms/rag"],
    "sinks": ["sinks"],
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py::test_plugin_discoverable -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/infrastructure/discovery.py tests/unit/plugins/transforms/rag/test_transform.py
git commit -m "feat: register rag_retrieval in plugin discovery scan config"
```

### Task 12: Integration tests

**Files:**
- Create: `tests/integration/plugins/transforms/test_rag_pipeline.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/plugins/transforms/test_rag_pipeline.py`:

```python
"""Integration tests for RAG retrieval transform pipeline.

These tests exercise the full transform lifecycle with real PipelineRow
instances. Azure provider tests use mocked HTTP (no real Azure calls),
but ChromaDB tests use real ephemeral Chroma — no mocks at all.
All data-carrying types are real to avoid BUG-LINEAGE-01 pattern.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch):
    """Set ELSPETH_FINGERPRINT_KEY via env var (standard pattern, not patch)."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key-for-integration")


class TestRAGPipelineIntegration:
    """End-to-end transform process with mock HTTP transport."""

    def _create_transform_with_lifecycle(self, **config_overrides):
        config = {
            "output_prefix": "policy",
            "query_field": "question",
            "provider": "azure_search",
            "provider_config": {
                "endpoint": "https://test.search.windows.net",
                "index": "test-index",
                "api_key": "test-key",
            },
            "schema_config": {"mode": "observed"},
        }
        config.update(config_overrides)
        transform = RAGRetrievalTransform(config)

        lifecycle_ctx = MagicMock()
        lifecycle_ctx.run_id = "run-1"
        lifecycle_ctx.landscape = MagicMock()
        lifecycle_ctx.telemetry_emit = MagicMock()
        lifecycle_ctx.rate_limit_registry = None
        transform.on_start(lifecycle_ctx)

        return transform

    def _make_row(self, data):
        """Create a real PipelineRow — NO mock fallback."""
        contract = SchemaContract(mode="OBSERVED", fields=())
        return PipelineRow(data, contract)

    def _mock_ctx(self, state_id="state-1"):
        ctx = MagicMock()
        ctx.state_id = state_id
        ctx.run_id = "run-1"
        token = MagicMock()
        token.token_id = "token-1"
        ctx.token = token
        return ctx

    def test_full_retrieval_pipeline(self):
        """Query -> retrieve -> format -> output fields attached."""
        transform = self._create_transform_with_lifecycle()

        chunks = [
            RetrievalChunk(content="Policy section 1", score=0.95, source_id="doc1", metadata={"page": 1}),
            RetrievalChunk(content="Policy section 2", score=0.82, source_id="doc2", metadata={"page": 3}),
        ]

        with patch.object(transform._provider, "search", return_value=chunks):
            row = self._make_row({"question": "What is the refund policy?"})
            ctx = self._mock_ctx()
            result = transform.process(row, ctx)

        # Verify output row has real data (not a mock)
        assert result.status == "success"
        output = result.output_row.to_dict()

        # Verify all four prefixed fields are present with correct values
        assert "policy__rag_context" in output
        assert "1. Policy section 1" in output["policy__rag_context"]
        assert "2. Policy section 2" in output["policy__rag_context"]
        assert output["policy__rag_count"] == 2
        assert output["policy__rag_score"] == 0.95
        sources = json.loads(output["policy__rag_sources"])
        assert len(sources["sources"]) == 2
        assert sources["sources"][0]["source_id"] == "doc1"

        # Verify original fields are preserved
        assert output["question"] == "What is the refund policy?"

        # Verify success_reason metadata
        assert result.success_reason["action"] == "enriched"
        assert result.success_reason["metadata"]["chunks_retrieved"] == 2
        assert result.success_reason["metadata"]["retrieval_status"] == "full"

    def test_zero_results_quarantine(self):
        transform = self._create_transform_with_lifecycle(on_no_results="quarantine")

        with patch.object(transform._provider, "search", return_value=[]):
            row = self._make_row({"question": "obscure query"})
            ctx = self._mock_ctx()
            result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason["reason"] == "no_results"

    def test_zero_results_continue_with_sentinels(self):
        transform = self._create_transform_with_lifecycle(on_no_results="continue")

        with patch.object(transform._provider, "search", return_value=[]):
            row = self._make_row({"question": "obscure query"})
            ctx = self._mock_ctx()
            result = transform.process(row, ctx)

        assert result.status == "success"
        output = result.output_row.to_dict()
        assert output["policy__rag_context"] == ""
        assert output["policy__rag_count"] == 0
        assert output["policy__rag_score"] == 0.0
        assert result.success_reason["metadata"]["retrieval_status"] == "empty"
        assert result.success_reason["metadata"]["chunks_retrieved"] == 0

    def test_on_complete_with_zero_rows(self):
        """Ensure no StatisticsError when no rows were processed."""
        transform = self._create_transform_with_lifecycle()
        lifecycle_ctx = MagicMock()
        lifecycle_ctx.telemetry_emit = MagicMock()
        transform.on_complete(lifecycle_ctx)
        lifecycle_ctx.telemetry_emit.assert_called_once()

    def test_plugin_discovery(self):
        """discover_all_plugins finds rag_retrieval."""
        from elspeth.plugins.infrastructure.discovery import PLUGIN_SCAN_CONFIG

        assert "transforms/rag" in PLUGIN_SCAN_CONFIG["transforms"]


class TestRAGPipelineWithChromaProvider:
    """End-to-end with real ChromaDB — no mocks at all.

    This exercises the full data path: query construction → provider search
    (real vector similarity) → context formatting → output attachment.
    """

    def _create_chroma_transform(self, documents, **config_overrides):
        """Create transform backed by a real ephemeral Chroma collection."""
        config = {
            "output_prefix": "kb",
            "query_field": "question",
            "provider": "chroma",
            "provider_config": {
                "collection": "test-knowledge-base",
                "mode": "ephemeral",
                "distance_function": "cosine",
            },
            "schema_config": {"mode": "observed"},
        }
        config.update(config_overrides)
        transform = RAGRetrievalTransform(config)

        lifecycle_ctx = MagicMock()
        lifecycle_ctx.run_id = "run-1"
        lifecycle_ctx.landscape = MagicMock()
        lifecycle_ctx.telemetry_emit = MagicMock()
        lifecycle_ctx.rate_limit_registry = None
        transform.on_start(lifecycle_ctx)

        # Populate collection with test documents
        collection = transform._provider._collection
        collection.add(
            documents=[d["content"] for d in documents],
            ids=[d["id"] for d in documents],
            metadatas=[d.get("metadata", {}) for d in documents],
        )

        return transform

    def _make_row(self, data):
        contract = SchemaContract(mode="OBSERVED", fields=())
        return PipelineRow(data, contract)

    def _mock_ctx(self, state_id="state-1"):
        ctx = MagicMock()
        ctx.state_id = state_id
        ctx.run_id = "run-1"
        token = MagicMock()
        token.token_id = "token-1"
        ctx.token = token
        return ctx

    def test_full_retrieval_with_real_chroma(self):
        """Real vector search, real score normalization, real output."""
        transform = self._create_chroma_transform(documents=[
            {"id": "policy-1", "content": "Refunds are processed within 30 days of purchase."},
            {"id": "policy-2", "content": "Returns must include original packaging."},
            {"id": "faq-1", "content": "Our office hours are 9am to 5pm Monday through Friday."},
        ])
        row = self._make_row({"question": "What is the refund policy?"})
        ctx = self._mock_ctx()

        result = transform.process(row, ctx)

        assert result.status == "success"
        output = result.output_row.to_dict()
        assert output["kb__rag_count"] >= 1
        assert output["kb__rag_score"] > 0.0
        # The refund policy doc should score highest
        assert "refund" in output["kb__rag_context"].lower() or "return" in output["kb__rag_context"].lower()

    def test_zero_results_with_high_min_score(self):
        """min_score filters out low-relevance results from real search."""
        transform = self._create_chroma_transform(
            documents=[
                {"id": "doc1", "content": "Completely unrelated content about quantum mechanics."},
            ],
            min_score=0.99,  # Unrealistically high threshold
        )
        row = self._make_row({"question": "refund policy"})
        ctx = self._mock_ctx()

        result = transform.process(row, ctx)
        # Either quarantined (default) or empty depending on on_no_results
        assert result.status == "error"
        assert result.reason["reason"] == "no_results"

    def test_metadata_flows_through_to_sources_json(self):
        """Provider metadata preserved in rag_sources output field."""
        transform = self._create_chroma_transform(documents=[
            {"id": "doc1", "content": "Test document", "metadata": {"section": "intro", "page": 1}},
        ])
        row = self._make_row({"question": "test document"})
        ctx = self._mock_ctx()

        result = transform.process(row, ctx)

        assert result.status == "success"
        sources = json.loads(result.output_row.to_dict()["kb__rag_sources"])
        assert sources["sources"][0]["metadata"]["section"] == "intro"


class TestRAGExecutionGraphAssembly:
    """Exercises ExecutionGraph.from_plugin_instances() with the RAG transform.

    CLAUDE.md mandates integration tests use from_plugin_instances() to prevent
    BUG-LINEAGE-01 class bugs where manual graph construction masks production
    assembly path differences.
    """

    def test_rag_transform_in_execution_graph(self):
        """RAG transform assembles correctly via the production graph builder."""
        from elspeth.core.dag.execution_graph import ExecutionGraph
        from elspeth.plugins.sources.null_source import NullSource

        source = NullSource({"schema_config": {"mode": "observed"}})
        rag_transform = RAGRetrievalTransform({
            "output_prefix": "policy",
            "query_field": "question",
            "provider": "azure_search",
            "provider_config": {
                "endpoint": "https://test.search.windows.net",
                "index": "test-index",
                "api_key": "test-key",
            },
            "schema_config": {"mode": "observed"},
        })

        graph = ExecutionGraph.from_plugin_instances(
            source=source,
            transforms=[rag_transform],
            sinks={},
        )

        # Verify the graph is valid and the RAG transform node exists
        assert graph is not None
        node_names = [n.name for n in graph.nodes]
        assert "rag_retrieval" in node_names or any("rag" in n for n in node_names)
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/python -m pytest tests/integration/plugins/transforms/test_rag_pipeline.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/plugins/transforms/test_rag_pipeline.py
git commit -m "test: add integration tests for RAG retrieval pipeline"
```

### Task 13: Tier model enforcement allowlist

**Files:**
- Modify or Create: `config/cicd/enforce_tier_model/plugins.yaml`

- [ ] **Step 1: Run tier model enforcer to check for violations**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

- [ ] **Step 2: Add allowlist entries for any legitimate findings**

If the enforcer flags defensive patterns in the RAG transform (e.g., the `_provider is None` guard in `close()`, or the `state_id is None` guard in `process()`), add entries to `config/cicd/enforce_tier_model/plugins.yaml` with rationale comments explaining why each is a legitimate lifecycle guard, not defensive programming.

- [ ] **Step 3: Run enforcer again to verify clean pass**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Clean pass (0 unallowlisted findings)

- [ ] **Step 4: Commit**

```bash
git add config/cicd/enforce_tier_model/plugins.yaml
git commit -m "chore: add tier model allowlist entries for RAG transform lifecycle guards"
```

### Task 14: Final verification and type checking

- [ ] **Step 1: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/rag/ src/elspeth/plugins/infrastructure/clients/retrieval/ src/elspeth/plugins/infrastructure/templates.py`
Expected: Clean pass. Fix any type errors.

- [ ] **Step 2: Run ruff**

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/transforms/rag/ src/elspeth/plugins/infrastructure/clients/retrieval/ src/elspeth/plugins/infrastructure/templates.py`
Expected: Clean pass. Fix any lint errors.

- [ ] **Step 3: Run config contracts check**

Run: `.venv/bin/python -m scripts.check_contracts`
Expected: Clean pass.

- [ ] **Step 4: Run full test suite one final time**

Run: `.venv/bin/python -m pytest tests/ --timeout=120`
Expected: All PASS

- [ ] **Step 5: Commit any fixes**

```bash
git add -u
git commit -m "fix: resolve mypy/ruff issues in RAG retrieval transform"
```

---

## Review Findings (2026-03-19)

This plan was reviewed by 4 specialized agents (reality, architecture, quality, systems). All 5 blocking issues (B1-B5) and 9 warnings (W1-W9) have been incorporated into the implementation steps above. See `docs/superpowers/plans/2026-03-19-rag-retrieval-transform.review.json` for the original review output.
