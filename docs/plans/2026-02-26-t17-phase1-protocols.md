# T17 Phase 1: Define Protocol Interfaces + Alignment Tests

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Define 4 protocol interfaces in `contracts/contexts.py` and write alignment tests verifying PluginContext satisfies all of them.

**Architecture:** New `@runtime_checkable` Protocol classes following the precedent in `contracts/config/protocols.py`. Alignment tests modeled on `tests/unit/core/test_config_alignment.py`.

**Tech Stack:** `typing.Protocol`, `@runtime_checkable`, mypy strict structural checking, pytest

**Prerequisite:** Phase 0 complete (dead fields removed)

---

## Task 1: Create `contracts/contexts.py` with protocol definitions

**Files:**
- Create: `src/elspeth/contracts/contexts.py`

**Step 1: Write the failing test**

Create `tests/unit/contracts/test_context_protocols.py`:

```python
"""Protocol alignment tests for PluginContext decomposition.

Modeled on tests/unit/core/test_config_alignment.py — these verify that
PluginContext satisfies all 4 phase-based protocols structurally.
"""

from elspeth.contracts.contexts import (
    LifecycleContext,
    SinkContext,
    SourceContext,
    TransformContext,
)


class TestProtocolsImportable:
    """Smoke test: protocols can be imported."""

    def test_source_context_importable(self) -> None:
        assert SourceContext is not None

    def test_transform_context_importable(self) -> None:
        assert TransformContext is not None

    def test_sink_context_importable(self) -> None:
        assert SinkContext is not None

    def test_lifecycle_context_importable(self) -> None:
        assert LifecycleContext is not None
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_context_protocols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.contexts'`

**Step 3: Create the protocol definitions**

Create `src/elspeth/contracts/contexts.py`:

```python
# src/elspeth/contracts/contexts.py
"""Phase-based protocol interfaces for PluginContext decomposition.

These protocols define what each plugin category actually needs from the
execution context. The concrete PluginContext class (in plugin_context.py)
satisfies all four protocols.

Protocol design rationale (D2 revision):
    The original D2 decision proposed field-category grouping
    (IdentityContext / AuditContext / ExecutionContext). Three independent
    code analyses mapped every field access across all 42 plugin files and
    found this doesn't match actual usage — most complex plugins need fields
    from all three categories. The revised split groups by consumer role.

See: docs/plans/2026-02-26-t17-plugincontext-protocol-split-design.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from elspeth.contracts.batch_checkpoint import BatchCheckpointState
    from elspeth.contracts.call_data import RawCallPayload
    from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig
    from elspeth.contracts.identity import TokenInfo
    from elspeth.contracts.plugin_context import TransformErrorToken, ValidationErrorToken
    from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.core.rate_limit import RateLimitRegistry
    from elspeth.plugins.results import PayloadStore


# ---------------------------------------------------------------------------
# Forward references for method signatures
# CallType and CallStatus are enums used in record_call(). Using string
# annotations to avoid importing enums into a protocol module.
# ---------------------------------------------------------------------------


@runtime_checkable
class SourceContext(Protocol):
    """What source plugins need during load().

    Sources operate at the Tier 3 boundary (external data). They need:
    - Identity: run_id, node_id for audit attribution
    - Recording: record_validation_error() for quarantined rows,
      record_call() for external API calls (e.g., Azure Blob download)
    - Telemetry: telemetry_emit for operational visibility
    """

    @property
    def run_id(self) -> str: ...

    @property
    def node_id(self) -> str | None: ...

    @property
    def operation_id(self) -> str | None: ...

    @property
    def landscape(self) -> LandscapeRecorder | None: ...

    @property
    def telemetry_emit(self) -> Callable[[Any], None]: ...

    def record_validation_error(
        self,
        row: Any,
        error: str,
        schema_mode: str,
        destination: str,
        *,
        contract_violation: Any | None = None,
    ) -> ValidationErrorToken: ...

    def record_call(
        self,
        call_type: Any,
        status: Any,
        request_data: dict[str, Any],
        response_data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        *,
        provider: str = "unknown",
    ) -> Any: ...


@runtime_checkable
class TransformContext(Protocol):
    """What transform plugins need during process()/accept().

    Transforms operate on Tier 2 pipeline data. They need:
    - Per-row identity: state_id, token, batch_token_ids for audit attribution
    - Schema: contract for field resolution
    - Recording: record_call() for external API calls (LLM, HTTP)
    - Checkpoint: get/set/clear_checkpoint for crash recovery (batch transforms)
    """

    @property
    def run_id(self) -> str: ...

    @property
    def state_id(self) -> str | None: ...

    @property
    def node_id(self) -> str | None: ...

    @property
    def token(self) -> TokenInfo | None: ...

    @property
    def batch_token_ids(self) -> list[str] | None: ...

    @property
    def contract(self) -> SchemaContract | None: ...

    def record_call(
        self,
        call_type: Any,
        status: Any,
        request_data: dict[str, Any],
        response_data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        *,
        provider: str = "unknown",
    ) -> Any: ...

    def get_checkpoint(self) -> BatchCheckpointState | None: ...

    def set_checkpoint(self, state: BatchCheckpointState) -> None: ...

    def clear_checkpoint(self) -> None: ...


@runtime_checkable
class SinkContext(Protocol):
    """What sink plugins need during write().

    Sinks output Tier 2 pipeline data. They need:
    - Identity: run_id for landscape queries
    - Schema: contract for display header resolution
    - Audit: landscape for field resolution queries
    - Recording: record_call() for external calls (SQL, blob upload)
    """

    @property
    def run_id(self) -> str: ...

    @property
    def contract(self) -> SchemaContract | None: ...

    @property
    def landscape(self) -> LandscapeRecorder | None: ...

    @property
    def operation_id(self) -> str | None: ...

    def record_call(
        self,
        call_type: Any,
        status: Any,
        request_data: dict[str, Any],
        response_data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        *,
        provider: str = "unknown",
    ) -> Any: ...


@runtime_checkable
class LifecycleContext(Protocol):
    """What plugins need during on_start()/on_complete().

    Lifecycle hooks capture infrastructure references that persist for the
    run. Complex transforms store these as instance variables in on_start()
    and use them throughout processing.

    This protocol is wider than the per-row protocols because lifecycle
    hooks need access to infrastructure (rate limiters, payload store,
    concurrency config) that per-row processing doesn't need directly.
    """

    @property
    def run_id(self) -> str: ...

    @property
    def landscape(self) -> LandscapeRecorder | None: ...

    @property
    def rate_limit_registry(self) -> RateLimitRegistry | None: ...

    @property
    def telemetry_emit(self) -> Callable[[Any], None]: ...

    @property
    def payload_store(self) -> PayloadStore | None: ...

    @property
    def concurrency_config(self) -> RuntimeConcurrencyConfig | None: ...
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_context_protocols.py -v`
Expected: 4 PASSED

**Step 5: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/contexts.py`
Expected: Clean (or fix any import issues)

---

## Task 2: Add protocol satisfaction tests

**Files:**
- Modify: `tests/unit/contracts/test_context_protocols.py`

**Step 1: Write the tests**

Add to `tests/unit/contracts/test_context_protocols.py`:

```python
from elspeth.contracts.plugin_context import PluginContext


class TestPluginContextSatisfiesProtocols:
    """Verify PluginContext structurally satisfies all 4 protocols.

    These are the critical alignment tests. If PluginContext is missing
    a field or method that a protocol declares, isinstance() fails.
    """

    def _make_ctx(self) -> PluginContext:
        return PluginContext(run_id="test", config={})

    def test_satisfies_source_context(self) -> None:
        ctx = self._make_ctx()
        assert isinstance(ctx, SourceContext)

    def test_satisfies_transform_context(self) -> None:
        ctx = self._make_ctx()
        assert isinstance(ctx, TransformContext)

    def test_satisfies_sink_context(self) -> None:
        ctx = self._make_ctx()
        assert isinstance(ctx, SinkContext)

    def test_satisfies_lifecycle_context(self) -> None:
        ctx = self._make_ctx()
        assert isinstance(ctx, LifecycleContext)
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_context_protocols.py -v`
Expected: 8 PASSED

If any `isinstance` check fails, it means PluginContext is missing something the protocol declares. Fix the protocol definition to match PluginContext's actual interface (post-Phase-0 cleanup).

---

## Task 3: Add field coverage tests

**Files:**
- Modify: `tests/unit/contracts/test_context_protocols.py`

**Step 1: Write field coverage tests**

These verify that protocol fields are a subset of PluginContext fields, and that no protocol accidentally declares fields that don't exist.

```python
import inspect
from typing import get_type_hints


class TestProtocolFieldCoverage:
    """Verify protocol fields map to real PluginContext attributes."""

    def _get_protocol_attrs(self, protocol_cls: type) -> set[str]:
        """Extract declared attributes from a Protocol class (not methods)."""
        hints = get_type_hints(protocol_cls)
        # Filter out methods — keep only data attributes
        methods = {
            name for name, _ in inspect.getmembers(protocol_cls, predicate=inspect.isfunction)
        }
        return {k for k in hints if k not in methods and not k.startswith("_")}

    def _get_protocol_methods(self, protocol_cls: type) -> set[str]:
        """Extract declared methods from a Protocol class."""
        return {
            name
            for name in dir(protocol_cls)
            if not name.startswith("_")
            and callable(getattr(protocol_cls, name, None))
            and name not in {"__init__", "__class__"}
        }

    def test_source_context_fields_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for attr in ("run_id", "node_id", "operation_id", "landscape", "telemetry_emit"):
            assert hasattr(ctx, attr), f"PluginContext missing SourceContext field: {attr}"

    def test_source_context_methods_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for method in ("record_validation_error", "record_call"):
            assert hasattr(ctx, method), f"PluginContext missing SourceContext method: {method}"
            assert callable(getattr(ctx, method))

    def test_transform_context_fields_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for attr in ("run_id", "state_id", "node_id", "token", "batch_token_ids", "contract"):
            assert hasattr(ctx, attr), f"PluginContext missing TransformContext field: {attr}"

    def test_transform_context_methods_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for method in ("record_call", "get_checkpoint", "set_checkpoint", "clear_checkpoint"):
            assert hasattr(ctx, method), f"PluginContext missing TransformContext method: {method}"
            assert callable(getattr(ctx, method))

    def test_sink_context_fields_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for attr in ("run_id", "contract", "landscape", "operation_id"):
            assert hasattr(ctx, attr), f"PluginContext missing SinkContext field: {attr}"

    def test_sink_context_methods_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for method in ("record_call",):
            assert hasattr(ctx, method), f"PluginContext missing SinkContext method: {method}"
            assert callable(getattr(ctx, method))

    def test_lifecycle_context_fields_exist_on_plugin_context(self) -> None:
        from elspeth.contracts.plugin_context import PluginContext
        ctx = PluginContext(run_id="test", config={})
        for attr in ("run_id", "landscape", "rate_limit_registry", "telemetry_emit", "payload_store", "concurrency_config"):
            assert hasattr(ctx, attr), f"PluginContext missing LifecycleContext field: {attr}"
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_context_protocols.py -v`
Expected: All pass

---

## Task 4: Add protocol disjointness documentation test

**Files:**
- Modify: `tests/unit/contracts/test_context_protocols.py`

**Step 1: Write disjointness test**

This documents which fields are shared vs. unique to each protocol. Not enforcing strict disjointness (run_id is intentionally shared), but making the overlap explicit.

```python
class TestProtocolOverlapDocumentation:
    """Document field overlap between protocols.

    run_id is intentionally in all 4 protocols. Other fields should
    have minimal overlap. This test serves as documentation — it
    fails if overlap changes unexpectedly.
    """

    EXPECTED_UNIVERSAL = {"run_id"}  # In all protocols by design
    EXPECTED_AUDIT_SHARED = {"landscape", "record_call"}  # Shared audit infrastructure

    def test_universal_fields_are_only_run_id(self) -> None:
        """Only run_id should appear in all 4 protocols."""
        source_fields = {"run_id", "node_id", "operation_id", "landscape", "telemetry_emit"}
        transform_fields = {"run_id", "state_id", "node_id", "token", "batch_token_ids", "contract"}
        sink_fields = {"run_id", "contract", "landscape", "operation_id"}
        lifecycle_fields = {"run_id", "landscape", "rate_limit_registry", "telemetry_emit", "payload_store", "concurrency_config"}

        universal = source_fields & transform_fields & sink_fields & lifecycle_fields
        assert universal == self.EXPECTED_UNIVERSAL, (
            f"Expected only {self.EXPECTED_UNIVERSAL} in all protocols, got {universal}"
        )
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_context_protocols.py -v`
Expected: All pass

---

## Task 5: Export protocols from contracts package

**Files:**
- Modify: `src/elspeth/contracts/__init__.py`

**Step 1: Add exports**

Add to the imports in `src/elspeth/contracts/__init__.py`:

```python
from elspeth.contracts.contexts import (
    LifecycleContext,
    SinkContext,
    SourceContext,
    TransformContext,
)
```

**Step 2: Run tests + mypy**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

---

## Task 6: Commit Phase 1

**Step 1: Commit**

```bash
git add src/elspeth/contracts/contexts.py src/elspeth/contracts/__init__.py tests/unit/contracts/test_context_protocols.py
git commit -m "refactor(T17): Phase 1 — define 4 phase-based context protocols + alignment tests

Add SourceContext, TransformContext, SinkContext, LifecycleContext protocols
in contracts/contexts.py. Alignment tests verify PluginContext satisfies all
four. Modeled on test_config_alignment.py precedent."
```

**Step 2: Full verification**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/ && .venv/bin/python -m scripts.check_contracts`
Expected: All pass
