# Display Header Module Extraction — Unified Sink Header Infrastructure

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate ~310 lines of copy-pasted display header logic across CSV, JSON, and Azure Blob sinks by extracting a shared `display_headers` module with typed free functions. Also fix a latent bug where the CLI resume guard uses a stringly-typed YAML key lookup and a flag-before-work race in lazy header resolution.

**Architecture:** Extract shared display header state and methods into a `display_headers.py` module of free functions in `plugins/infrastructure/`. Free functions (not a mixin class) to avoid MRO complexity — each takes the sink instance as an explicit first argument. A `DisplayHeaderHost` protocol added to `contracts/plugin_protocols.py` provides type safety. CSV and JSON sinks already use identical code; Azure Blob uses a variant with `restore_source_headers: bool` instead of `HeaderMode`. Unify Azure Blob to use `HeaderMode` (no legacy compat — per CLAUDE.md No Legacy Code policy). Remove redundant `set_output_contract`/`get_output_contract` overrides that duplicate `BaseSink`.

**Tech Stack:** Python dataclasses, Pydantic config models, pluggy plugin infrastructure.

**Filigree issue:** `elspeth-839ac5d8a5`

---

## Scope and Risk

**What changes:**
- New file: `src/elspeth/plugins/infrastructure/display_headers.py` (shared functions)
- Modified: `src/elspeth/contracts/plugin_protocols.py` — add `DisplayHeaderHost` protocol (type safety for sink parameter)
- Modified: `csv_sink.py` — remove 6 methods (~140 lines), call module functions directly from `write()`/callers, wire `__init__`
- Modified: `json_sink.py` — remove 7 methods (~170 lines), call module functions directly from `write()`/callers, wire `__init__`
- Modified: `azure_blob_sink.py` — replace `restore_source_headers`/`display_headers` config with `headers` (HeaderMode), remove 4 methods, call module functions directly
- Modified: `azure_blob_sink.py` config — `AzureBlobSinkConfig` gets `headers` field directly (not via `SinkPathConfig` — Azure Blob has no local `path`); delete `validate_display_options` model validator (line 193) that cross-validates the removed fields
- Modified: `cli.py` (lines 1835-1845) — fix stringly-typed resume guard that reads raw YAML `restore_source_headers` key; replace with typed sink property check
- Modified: `plugins/infrastructure/base.py` — update `set_resume_field_resolution` docstring (references old `restore_source_headers` name)
- Modified: `contracts/plugin_protocols.py` — update `set_resume_field_resolution` docstring (references old `restore_source_headers` name)
- Modified: `engine/orchestrator/export.py` — update comment (line 87) referencing old `restore_source_headers` name
- Modified: Azure Blob tests — update config to use `headers: original` instead of `restore_source_headers: true`
- Checked: example YAML files, docs, README.md, and `*.py` files for old config keys
- Cleaned: stale entries in `config/cicd/contracts-whitelist.yaml` for deleted methods

**What does NOT change:**
- `BaseSink` method signatures — already has correct `set_output_contract`/`get_output_contract`
- `HeaderMode` enum and `resolve_headers()` in `contracts/header_modes.py`
- Any engine code — sinks are L3, engine is L2
- Existing test assertions — only config keys change for Azure Blob
- CSV's `_get_field_names_and_display()` — CSV handles display mapping via DictWriter fieldnames, not row-key remapping (see design note below)

**Risk:** Medium. The 60+ existing header tests provide strong regression coverage. The CSV/JSON extraction is mechanical (identical code → module). Azure Blob config surface change is the only semantic change.

### Review findings applied (2026-03-09)

This plan was reviewed by 4 specialized agents (reality, architecture, quality, systems). All symbols, paths, and line numbers were confirmed accurate. The following changes were applied based on review findings:

- **[B1 → fixed]** Task 4 contract-priority test now asserts actual written output headers, not just that Landscape wasn't called
- **[W1 → fixed]** Task 5 adds `needs_resume_field_resolution` property to `BaseSink` — eliminates stringly-typed YAML key lookup
- **[W2 → fixed]** Task 4 extracts `_validate_headers` to shared function in `config_base.py` instead of duplicating
- **[W3 → fixed]** Task 4 adds Azure Blob resume path test with `headers: original`
- **[W5 → fixed]** `set_resume_field_resolution` now validates for duplicate values in reverse mapping
- **[W6 → fixed]** Added test for passthrough-key vs mapped-display-name collision
- **[W7 → fixed]** Dropped `@runtime_checkable` from `DisplayHeaderHost` — unreliable for private-attribute protocols

Full review report: `docs/plans/2026-03-09-display-header-mixin-extraction.review.json`

### Design Note: CSV vs JSON display header asymmetry

CSV and JSON apply display headers differently:
- **JSON** uses `_apply_display_headers()` to remap row dict keys before serialization
- **CSV** uses `_get_field_names_and_display()` to build DictWriter `fieldnames` — it never remaps row keys, it maps column positions

The shared `apply_display_headers()` function handles JSON-style key remapping. CSV's `_get_field_names_and_display()` stays as a CSV-specific method since its logic is fundamentally different (it queries field names + display names for DictWriter, not row-key substitution).

### Design Note: Collision detection scope

The `apply_display_headers()` collision check is **display-name collisions** (two normalized fields mapping to the same output column name). This is distinct from the engine-level transform executor's collision detection (`engine/executors/transform.py` lines 212-229), which checks **transform output field collisions** (a transform declaring a field that already exists). Both are needed at different layers.

### Design Note: Azure Blob behaviour expansion

Task 4 adds `resolve_contract_from_context_if_needed()` to Azure Blob's `write()` path. This is **new functionality**, not just a refactor — Azure Blob previously had no contract-based header resolution. After this change, if a SchemaContract is available via `ctx.contract`, it will take precedence over the Landscape field resolution query. This matches the priority order already used by CSV and JSON sinks. A test must verify this priority ordering in the Azure Blob test file.

---

## Task 1: Create display_headers module and DisplayHeaderHost protocol

**Files:**
- Create: `src/elspeth/plugins/infrastructure/display_headers.py`
- Modify: `src/elspeth/contracts/plugin_protocols.py` — add `DisplayHeaderHost` protocol
- Create: `tests/unit/plugins/infrastructure/test_display_headers.py`

**Note:** The `tests/unit/plugins/infrastructure/` directory does not exist yet. Create it along with an `__init__.py` if required by the project's pytest configuration.

### Step 1: Write failing tests for the module

The module functions need to be testable in isolation. Create a minimal concrete class that satisfies the protocol.

**Ordering note:** The `_StubSink` must set `_output_contract = None` **before** calling `init_display_headers()`, matching the real sink ordering where `BaseSink.__init__` sets `_output_contract` before the subclass `__init__` calls `init_display_headers()`. The ordering matters for `get_effective_display_headers()` (which reads `_output_contract`), not for `init_display_headers()` itself (which doesn't read it).

```python
"""Tests for display_headers module."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from elspeth.contracts.header_modes import HeaderMode


class _StubSink:
    """Minimal sink that satisfies DisplayHeaderHost protocol for testing."""

    def __init__(
        self,
        headers_mode: HeaderMode,
        headers_custom_mapping: dict[str, str] | None = None,
    ) -> None:
        # BaseSink.__init__ sets _output_contract BEFORE subclass init.
        # Must match this ordering — get_effective_display_headers reads _output_contract.
        self._output_contract = None

        from elspeth.plugins.infrastructure.display_headers import init_display_headers

        init_display_headers(self, headers_mode, headers_custom_mapping)

    def set_output_contract(self, contract: Any) -> None:
        self._output_contract = contract


class TestGetEffectiveDisplayHeaders:
    """Test get_effective_display_headers priority logic."""

    def test_normalized_mode_returns_none(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )

        sink = _StubSink(HeaderMode.NORMALIZED)
        assert get_effective_display_headers(sink) is None

    def test_custom_mode_returns_mapping(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )

        mapping = {"field_a": "Field A", "field_b": "Field B"}
        sink = _StubSink(HeaderMode.CUSTOM, mapping)
        assert get_effective_display_headers(sink) == mapping

    def test_custom_mode_with_none_mapping_returns_none(self) -> None:
        """CUSTOM mode with None mapping is a no-op — returns None, same as NORMALIZED."""
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, None)
        assert get_effective_display_headers(sink) is None

    def test_original_mode_with_contract(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )
        from elspeth.contracts.schema_contract import FieldContract, SchemaContract

        sink = _StubSink(HeaderMode.ORIGINAL)
        contract = SchemaContract(
            fields=[
                FieldContract(normalized_name="amount", original_name="Amount USD"),
            ]
        )
        sink.set_output_contract(contract)
        result = get_effective_display_headers(sink)
        assert result is not None
        assert result["amount"] == "Amount USD"

    def test_original_mode_with_resolved_headers_fallback(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        sink._resolved_display_headers = {"amount": "Amount USD"}
        assert get_effective_display_headers(sink) == {"amount": "Amount USD"}

    def test_original_mode_no_contract_no_resolved_returns_none(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            get_effective_display_headers,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        assert get_effective_display_headers(sink) is None


class TestResolveContractFromContext:
    """Test resolve_contract_from_context_if_needed."""

    def test_captures_context_contract_in_original_mode(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_contract_from_context_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        ctx = MagicMock()
        ctx.contract = MagicMock()
        resolve_contract_from_context_if_needed(sink, ctx)
        assert sink._output_contract is ctx.contract

    def test_skips_if_not_original_mode(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_contract_from_context_if_needed,
        )

        sink = _StubSink(HeaderMode.NORMALIZED)
        ctx = MagicMock()
        ctx.contract = MagicMock()
        resolve_contract_from_context_if_needed(sink, ctx)
        assert sink._output_contract is None

    def test_skips_if_contract_already_set(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_contract_from_context_if_needed,
        )

        existing = MagicMock()
        sink = _StubSink(HeaderMode.ORIGINAL)
        sink._output_contract = existing
        ctx = MagicMock()
        ctx.contract = MagicMock()
        resolve_contract_from_context_if_needed(sink, ctx)
        assert sink._output_contract is existing


class TestResolveDisplayHeadersIfNeeded:
    """Test resolve_display_headers_if_needed."""

    def test_resolves_from_landscape(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_display_headers_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        ctx = MagicMock()
        # Landscape returns original -> normalized mapping
        ctx.landscape.get_source_field_resolution.return_value = {
            "Amount USD": "amount_usd",
            "Customer ID": "customer_id",
        }
        ctx.run_id = "run-1"
        resolve_display_headers_if_needed(sink, ctx)
        # Should build reverse: normalized -> original
        assert sink._resolved_display_headers == {
            "amount_usd": "Amount USD",
            "customer_id": "Customer ID",
        }
        assert sink._display_headers_resolved is True

    def test_skips_when_already_resolved(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_display_headers_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        sink._display_headers_resolved = True
        ctx = MagicMock()
        resolve_display_headers_if_needed(sink, ctx)
        # Should not call landscape
        ctx.landscape.get_source_field_resolution.assert_not_called()

    def test_errors_if_no_landscape(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_display_headers_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        ctx = MagicMock()
        ctx.landscape = None
        with pytest.raises(ValueError, match="requires Landscape"):
            resolve_display_headers_if_needed(sink, ctx)

    def test_errors_if_no_field_resolution(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_display_headers_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        ctx = MagicMock()
        ctx.landscape.get_source_field_resolution.return_value = None
        ctx.run_id = "run-1"
        with pytest.raises(ValueError, match="did not record field resolution"):
            resolve_display_headers_if_needed(sink, ctx)

    def test_landscape_failure_does_not_permanently_trip_guard(self) -> None:
        """If the Landscape query raises, the next write() must retry resolution.

        This tests the fix for a pre-existing bug where _display_headers_resolved
        was set True BEFORE the query, permanently blocking retry on failure.
        """
        from elspeth.plugins.infrastructure.display_headers import (
            resolve_display_headers_if_needed,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)

        # First call: Landscape query raises
        ctx = MagicMock()
        ctx.landscape.get_source_field_resolution.side_effect = RuntimeError("DB locked")
        ctx.run_id = "run-1"
        with pytest.raises(RuntimeError, match="DB locked"):
            resolve_display_headers_if_needed(sink, ctx)

        # Guard must NOT be tripped — next call should retry
        assert sink._display_headers_resolved is False

        # Second call: Landscape query succeeds
        ctx.landscape.get_source_field_resolution.side_effect = None
        ctx.landscape.get_source_field_resolution.return_value = {
            "Amount USD": "amount_usd",
        }
        resolve_display_headers_if_needed(sink, ctx)
        assert sink._resolved_display_headers == {"amount_usd": "Amount USD"}
        assert sink._display_headers_resolved is True


class TestSetResumeFieldResolution:
    """Test set_resume_field_resolution."""

    def test_builds_reverse_mapping_in_original_mode(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            set_resume_field_resolution,
        )

        sink = _StubSink(HeaderMode.ORIGINAL)
        set_resume_field_resolution(sink, {"Amount USD": "amount_usd"})
        assert sink._resolved_display_headers == {"amount_usd": "Amount USD"}
        assert sink._display_headers_resolved is True

    def test_noop_in_normalized_mode(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            set_resume_field_resolution,
        )

        sink = _StubSink(HeaderMode.NORMALIZED)
        set_resume_field_resolution(sink, {"Amount USD": "amount_usd"})
        assert sink._resolved_display_headers is None


class TestApplyDisplayHeaders:
    """Test apply_display_headers."""

    def test_maps_keys(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {"a": "Alpha", "b": "Beta"})
        rows = [{"a": 1, "b": 2}]
        result = apply_display_headers(sink, rows)
        assert result == [{"Alpha": 1, "Beta": 2}]

    def test_unmapped_keys_pass_through(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {"a": "Alpha"})
        rows = [{"a": 1, "extra": 99}]
        result = apply_display_headers(sink, rows)
        assert result == [{"Alpha": 1, "extra": 99}]

    def test_collision_raises(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {"a": "Same", "b": "Same"})
        with pytest.raises(ValueError, match="Header collision"):
            apply_display_headers(sink, [{"a": 1, "b": 2}])

    def test_no_mapping_returns_original(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.NORMALIZED)
        rows = [{"a": 1}]
        assert apply_display_headers(sink, rows) is rows

    def test_empty_rows_returns_empty(self) -> None:
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {"a": "Alpha"})
        result = apply_display_headers(sink, [])
        assert result == []

    def test_empty_mapping_passes_through(self) -> None:
        """CUSTOM mode with empty mapping dict — all keys pass through unchanged."""
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {})
        rows = [{"a": 1, "b": 2}]
        result = apply_display_headers(sink, rows)
        assert result == [{"a": 1, "b": 2}]

    def test_passthrough_collides_with_mapped_name(self) -> None:
        """Row has field 'Alpha' and mapping maps 'a' → 'Alpha' — collision detected."""
        from elspeth.plugins.infrastructure.display_headers import (
            apply_display_headers,
        )

        sink = _StubSink(HeaderMode.CUSTOM, {"a": "Alpha"})
        with pytest.raises(ValueError, match="Header collision"):
            apply_display_headers(sink, [{"a": 1, "Alpha": 2}])


class TestInitDisplayHeaders:
    """Test init_display_headers precondition."""

    def test_raises_if_output_contract_not_set(self) -> None:
        """Sinks must call super().__init__() before init_display_headers()."""
        from elspeth.plugins.infrastructure.display_headers import init_display_headers

        class _BadSink:
            pass  # No _output_contract — forgot super().__init__()

        with pytest.raises(RuntimeError, match="super\\(\\).__init__\\(\\)"):
            init_display_headers(_BadSink(), HeaderMode.NORMALIZED)
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_display_headers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'elspeth.plugins.infrastructure.display_headers'`

### Step 3: Add the DisplayHeaderHost protocol to plugin_protocols.py

Add `DisplayHeaderHost` to the existing `src/elspeth/contracts/plugin_protocols.py` file, near `SinkProtocol` where the relationship is visible. **Do not create a standalone file** — every other protocol in `contracts/` is consolidated, and `DisplayHeaderHost` is an internal implementation detail used only by the `display_headers` module.

```python
# Add near SinkProtocol in plugin_protocols.py:

class DisplayHeaderHost(Protocol):
    """Structural type for sinks that use display header functions.

    Any sink that calls init_display_headers() will satisfy this protocol.
    Provides type safety for the display_headers module functions instead
    of using Any. This is an internal protocol — engine and CLI code should
    use SinkProtocol, not this.

    NOT @runtime_checkable — the protocol's members are private attributes,
    and isinstance() only checks method signatures, not attribute presence.
    Use mypy structural checking instead.
    """

    _headers_mode: HeaderMode
    _headers_custom_mapping: dict[str, str] | None
    _resolved_display_headers: dict[str, str] | None
    _display_headers_resolved: bool
    _output_contract: Any  # SchemaContract | None — Any to avoid circular import
```

Ensure the necessary imports are present at the top of `plugin_protocols.py`:
```python
from elspeth.contracts.header_modes import HeaderMode
```

### Step 4: Implement the display_headers module

Create `src/elspeth/plugins/infrastructure/display_headers.py`:

```python
"""Display header resolution for sink plugins.

Provides shared display header infrastructure used by CSV, JSON, and Azure Blob
sinks. The functions in this module operate on sink instances that have been
initialized with init_display_headers().

Design: Functions rather than mixin class. This avoids MRO complexity and makes
the dependency on sink state explicit. Each function takes the sink instance as
its first argument, typed via DisplayHeaderHost protocol.

Ordering requirement: The host sink MUST have _output_contract already
initialized (by BaseSink.__init__) BEFORE calling init_display_headers().
init_display_headers() asserts this precondition.

State attributes set by init_display_headers():
    _headers_mode: HeaderMode — which header mode is active
    _headers_custom_mapping: dict | None — explicit field→display mapping (CUSTOM mode)
    _resolved_display_headers: dict | None — lazily populated from Landscape (ORIGINAL mode)
    _display_headers_resolved: bool — guard flag for lazy resolution
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from elspeth.contracts.header_modes import HeaderMode, resolve_headers
from elspeth.contracts.plugin_protocols import DisplayHeaderHost

if TYPE_CHECKING:
    from elspeth.contracts.contexts import SinkContext


def init_display_headers(
    sink: DisplayHeaderHost,
    headers_mode: HeaderMode,
    headers_custom_mapping: dict[str, str] | None = None,
) -> None:
    """Initialize display header state on a sink instance.

    Called from sink __init__ to set up the attributes that the other
    functions in this module depend on.

    Args:
        sink: The sink instance to initialize.
        headers_mode: The resolved HeaderMode (NORMALIZED, ORIGINAL, CUSTOM).
        headers_custom_mapping: Explicit mapping for CUSTOM mode.

    Raises:
        RuntimeError: If _output_contract is not set on the sink (forgot super().__init__()).
    """
    # Offensive assertion: _output_contract must already be set by BaseSink.__init__().
    # Without this, get_effective_display_headers() will AttributeError at first write().
    try:
        _ = sink._output_contract
    except AttributeError:
        raise RuntimeError(
            "sink._output_contract not set — call super().__init__() before "
            "init_display_headers(). BaseSink.__init__ sets _output_contract."
        )

    sink._headers_mode = headers_mode
    sink._headers_custom_mapping = headers_custom_mapping
    sink._resolved_display_headers = None
    sink._display_headers_resolved = False


def get_effective_display_headers(sink: DisplayHeaderHost) -> dict[str, str] | None:
    """Get the effective display header mapping.

    Priority order:
    1. NORMALIZED mode — no mapping
    2. CUSTOM mode — use custom mapping from 'headers' config
    3. ORIGINAL mode with contract — use resolve_headers()
    4. ORIGINAL mode with resolved headers (from Landscape query)
    5. None (fallback to normalized names)

    Args:
        sink: Sink instance with display header state.

    Returns:
        Dict mapping normalized field name → display name, or None if no
        display headers are configured or if using NORMALIZED mode.
    """
    if sink._headers_mode == HeaderMode.NORMALIZED:
        return None

    if sink._headers_mode == HeaderMode.CUSTOM:
        return sink._headers_custom_mapping

    # ORIGINAL mode — use contract to resolve headers
    if sink._output_contract is not None:
        return resolve_headers(
            contract=sink._output_contract,
            mode=HeaderMode.ORIGINAL,
            custom_mapping=None,
        )
    # Fallback to lazily-resolved display headers from Landscape
    if sink._resolved_display_headers is not None:
        return sink._resolved_display_headers
    return None


def resolve_contract_from_context_if_needed(sink: DisplayHeaderHost, ctx: SinkContext) -> None:
    """Lazily resolve output contract from context for headers: original mode.

    Called on first write() to capture ctx.contract if _output_contract is not
    already set. This allows headers: original mode to work without explicit
    orchestrator wiring of set_output_contract().

    Args:
        sink: Sink instance with display header state.
        ctx: Plugin context with potential contract from orchestrator.
    """
    if sink._headers_mode != HeaderMode.ORIGINAL:
        return
    if sink._output_contract is not None:
        return  # Already set explicitly
    if ctx.contract is not None:
        sink._output_contract = ctx.contract


def set_resume_field_resolution(
    sink: DisplayHeaderHost, resolution_mapping: dict[str, str]
) -> None:
    """Set field resolution mapping for resume validation.

    Called by CLI during `elspeth resume` to provide the source field resolution
    mapping BEFORE calling validate_output_target(). This allows validation to
    correctly compare expected display names against existing output when
    headers mode is ORIGINAL.

    Args:
        sink: Sink instance with display header state.
        resolution_mapping: Dict mapping original header name → normalized field name.
            This is the same format returned by Landscape.get_source_field_resolution().
    """
    if sink._headers_mode != HeaderMode.ORIGINAL:
        return  # Only needed for ORIGINAL mode

    # Build reverse mapping: normalized → original (display name)
    reverse = {v: k for k, v in resolution_mapping.items()}
    if len(reverse) != len(resolution_mapping):
        # Duplicate normalized names in the mapping — two original names collapsed
        # to the same normalized name. This is Tier 1 data (from Landscape), so crash.
        duplicates = [
            k for k, count in Counter(resolution_mapping.values()).items() if count > 1
        ]
        raise ValueError(
            f"Field resolution mapping has duplicate normalized names: {duplicates}. "
            f"Multiple original names map to the same normalized name — data integrity issue."
        )
    sink._resolved_display_headers = reverse
    sink._display_headers_resolved = True


def resolve_display_headers_if_needed(sink: DisplayHeaderHost, ctx: SinkContext) -> None:
    """Lazily resolve display headers from Landscape if headers mode is ORIGINAL.

    Called on first write() to fetch field resolution mapping. This MUST be lazy
    because the orchestrator calls sink.on_start() BEFORE source.load() iterates,
    and record_source_field_resolution() only happens after the first source row.

    The _display_headers_resolved flag is set AFTER successful resolution (not
    before) so that if the Landscape query raises, the next write() call retries.

    Args:
        sink: Sink instance with display header state.
        ctx: Plugin context with Landscape access.

    Raises:
        ValueError: If Landscape is unavailable or source didn't record resolution.
    """
    if sink._display_headers_resolved:
        return  # Already resolved (or not needed)

    if sink._headers_mode != HeaderMode.ORIGINAL:
        sink._display_headers_resolved = True  # Nothing to resolve — mark done
        return

    # Skip if contract already provides header resolution (takes precedence)
    if sink._output_contract is not None:
        sink._display_headers_resolved = True
        return

    # Fetch source field resolution from Landscape
    if ctx.landscape is None:
        raise ValueError(
            "headers: original requires Landscape to be available. "
            "This is a framework bug - context should have landscape set."
        )

    resolution_mapping = ctx.landscape.get_source_field_resolution(ctx.run_id)
    if resolution_mapping is None:
        raise ValueError(
            "headers: original but source did not record field resolution. "
            "Ensure source uses normalize_fields: true to enable header restoration."
        )

    # Build reverse mapping: final (normalized) → original
    reverse = {v: k for k, v in resolution_mapping.items()}
    if len(reverse) != len(resolution_mapping):
        duplicates = [
            k for k, count in Counter(resolution_mapping.values()).items() if count > 1
        ]
        raise ValueError(
            f"Field resolution mapping has duplicate normalized names: {duplicates}. "
            f"Multiple original names map to the same normalized name — data integrity issue."
        )
    sink._resolved_display_headers = reverse
    # Flag set AFTER success — if the query raised, next write() retries
    sink._display_headers_resolved = True


def apply_display_headers(
    sink: DisplayHeaderHost, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Apply display header mapping to row keys.

    Args:
        sink: Sink instance with display header state.
        rows: List of row dicts with normalized field names.

    Returns:
        List of row dicts with display names as keys. If no display headers
        are configured, returns the original rows unchanged.

    Raises:
        ValueError: If multiple fields map to the same output key (collision).
    """
    display_map = get_effective_display_headers(sink)
    if display_map is None:
        return rows

    # Transform each row's keys to display names
    # Fields not in the mapping keep their original names (transform-added fields)
    result_rows = []
    for row in rows:
        mapped: dict[str, Any] = {}
        for k, v in row.items():
            display_key = display_map[k] if k in display_map else k  # noqa: SIM401 — .get() banned by tier model
            if display_key in mapped:
                raise ValueError(
                    f"Header collision: multiple fields map to output key '{display_key}'. "
                    f"Check display_headers mapping for duplicate targets."
                )
            mapped[display_key] = v
        result_rows.append(mapped)
    return result_rows
```

### Step 5: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_display_headers.py -v`
Expected: All PASS

### Step 6: Commit

```bash
git add src/elspeth/contracts/plugin_protocols.py src/elspeth/plugins/infrastructure/display_headers.py tests/unit/plugins/infrastructure/test_display_headers.py
git commit -m "feat: add display_headers module — shared sink header resolution functions with protocol"
```

---

## Task 2: Wire CSVSink to use display_headers module

**Files:**
- Modify: `src/elspeth/plugins/sinks/csv_sink.py`
- Test: existing tests in `tests/unit/plugins/sinks/test_sink_display_headers.py` and `tests/unit/plugins/sinks/test_csv_sink_headers.py`

### Step 1: Run existing CSV header tests to establish baseline

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/test_sink_display_headers.py::TestCSVSinkHeaders tests/unit/plugins/sinks/test_csv_sink_headers.py -v`
Expected: All PASS (baseline)

### Step 2: Add top-level imports and modify CSVSink `__init__`

Add imports at the top of `csv_sink.py`:

```python
from elspeth.plugins.infrastructure.display_headers import (
    init_display_headers,
    get_effective_display_headers,
    resolve_contract_from_context_if_needed,
    resolve_display_headers_if_needed,
    set_resume_field_resolution,
)
```

Replace the header state initialization block (lines 194-204):

```python
# BEFORE (lines 194-204):
        self._headers_mode: HeaderMode = cfg.headers_mode
        self._headers_custom_mapping: dict[str, str] | None = cfg.headers_mapping
        self._resolved_display_headers: dict[str, str] | None = None
        self._display_headers_resolved: bool = False
        self._output_contract: SchemaContract | None = None

# AFTER:
        init_display_headers(self, cfg.headers_mode, cfg.headers_mapping)
```

Note: `_output_contract` is already initialized by `BaseSink.__init__` (which `super().__init__` calls at line 185). Remove the duplicate initialization.

### Step 3: Replace method implementations with direct module calls

**Delete entirely** — all 6 display header methods (lines 474-615):
- `_get_effective_display_headers()` (lines 474-504)
- `set_output_contract()` (lines 508-517) — redundant override of `BaseSink`
- `get_output_contract()` (lines 519-525) — redundant override of `BaseSink`
- `_resolve_contract_from_context_if_needed()` (lines 527-555)
- `set_resume_field_resolution()` (lines 557-574)
- `_resolve_display_headers_if_needed()` (lines 576-615)

**Update callers to call module functions directly:**

In `write()` (line ~263), replace:
```python
# BEFORE:
        self._resolve_contract_from_context_if_needed(ctx)
        self._resolve_display_headers_if_needed(ctx)

# AFTER:
        resolve_contract_from_context_if_needed(self, ctx)
        resolve_display_headers_if_needed(self, ctx)
```

In `_get_field_names_and_display()` and `_open_file()`, replace `self._get_effective_display_headers()` with `get_effective_display_headers(self)`.

**Keep as a thin public method** — `set_resume_field_resolution()` is part of the sink public interface (called by CLI resume code via `SinkProtocol`), so keep it as a one-line delegator:

```python
    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        set_resume_field_resolution(self, resolution_mapping)
```

### Step 4: Remove unused imports

Remove `resolve_headers` from the `header_modes` import — no longer used directly in csv_sink.py. Keep `HeaderMode` if referenced elsewhere in the file (e.g., type hints). Check whether `SchemaContract` TYPE_CHECKING import is still needed (it is — used in `validate_output_target`).

### Step 5: Run existing tests to verify no regressions

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/test_sink_display_headers.py::TestCSVSinkHeaders tests/unit/plugins/sinks/test_csv_sink_headers.py tests/unit/plugins/sinks/test_csv_sink.py -v`
Expected: All PASS (identical behavior)

### Step 6: Commit

```bash
git add src/elspeth/plugins/sinks/csv_sink.py
git commit -m "refactor: CSVSink delegates display header logic to shared module"
```

---

## Task 3: Wire JSONSink to use display_headers module

**Files:**
- Modify: `src/elspeth/plugins/sinks/json_sink.py`
- Test: existing tests in `tests/unit/plugins/sinks/test_sink_display_headers.py` and `tests/unit/plugins/sinks/test_json_sink.py`

### Step 1: Run existing JSON header tests to establish baseline

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/test_sink_display_headers.py::TestJSONSinkHeaders tests/unit/plugins/sinks/test_json_sink.py -v`
Expected: All PASS (baseline)

### Step 2: Add top-level imports and modify JSONSink `__init__`

Add imports at the top of `json_sink.py`:

```python
from elspeth.plugins.infrastructure.display_headers import (
    init_display_headers,
    apply_display_headers,
    get_effective_display_headers,
    resolve_contract_from_context_if_needed,
    resolve_display_headers_if_needed,
    set_resume_field_resolution,
)
```

Replace header state initialization (lines 204-214):

```python
# BEFORE (lines 204-214):
        self._headers_mode: HeaderMode = cfg.headers_mode
        self._headers_custom_mapping: dict[str, str] | None = cfg.headers_mapping
        self._resolved_display_headers: dict[str, str] | None = None
        self._display_headers_resolved: bool = False
        self._output_contract: SchemaContract | None = None

# AFTER:
        init_display_headers(self, cfg.headers_mode, cfg.headers_mapping)
```

### Step 3: Replace method implementations with direct module calls

**Delete entirely** — all 7 display header methods (lines 403-574):
- `_get_effective_display_headers()` (lines 403-433)
- `set_resume_field_resolution()` (lines 435-452)
- `set_output_contract()` (lines 456-465) — redundant override of `BaseSink`
- `get_output_contract()` (lines 467-473) — redundant override of `BaseSink`
- `_resolve_contract_from_context_if_needed()` (lines 475-503)
- `_resolve_display_headers_if_needed()` (lines 505-544)
- `_apply_display_headers()` (lines 546-574)

**Update callers to call module functions directly:**

In `write()`, replace:
```python
# BEFORE:
        self._resolve_contract_from_context_if_needed(ctx)
        self._resolve_display_headers_if_needed(ctx)
        ...
        rows = self._apply_display_headers(rows)

# AFTER:
        resolve_contract_from_context_if_needed(self, ctx)
        resolve_display_headers_if_needed(self, ctx)
        ...
        rows = apply_display_headers(self, rows)
```

Any other internal callers of `self._get_effective_display_headers()` → `get_effective_display_headers(self)`.

**Keep as a thin public method** — `set_resume_field_resolution()`:

```python
    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        set_resume_field_resolution(self, resolution_mapping)
```

### Step 4: Remove unused imports

Remove `resolve_headers` from the `header_modes` import. Keep `HeaderMode` if still used in type hints. Check `SchemaContract` TYPE_CHECKING import (needed for `validate_output_target`).

### Step 5: Run existing tests

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/test_sink_display_headers.py::TestJSONSinkHeaders tests/unit/plugins/sinks/test_json_sink.py -v`
Expected: All PASS

### Step 6: Commit

```bash
git add src/elspeth/plugins/sinks/json_sink.py
git commit -m "refactor: JSONSink delegates display header logic to shared module"
```

---

## Task 4: Unify AzureBlobSink config to use HeaderMode

**Files:**
- Modify: `src/elspeth/plugins/sinks/azure_blob_sink.py`
- Modify: `tests/unit/plugins/transforms/azure/test_blob_sink.py`

This is the only task with a semantic change. Azure Blob's `restore_source_headers: bool` + `display_headers: dict` becomes the standard `headers` field from `SinkPathConfig`.

**Behaviour expansion:** Azure Blob also gains contract-based header resolution via `resolve_contract_from_context_if_needed()` in its `write()` path (see Design Note in Scope section). This means if a SchemaContract is available via `ctx.contract`, it will take precedence over the Landscape field resolution query — matching CSV/JSON behaviour.

### Step 1: Run existing Azure Blob tests to establish baseline

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_blob_sink.py -v`
Expected: All PASS (baseline)

### Step 2: Modify AzureBlobSinkConfig

The config class currently extends `DataPluginConfig` directly. It needs to gain the `headers` field.

Add `headers` field directly to `AzureBlobSinkConfig` with the same validator as `SinkPathConfig`. Don't change the base class — Azure Blob isn't a `PathConfig` (it doesn't have a local `path`).

**REMOVE these fields:**
- `display_headers: dict[str, str] | None = Field(...)` (line 164)
- `restore_source_headers: bool = Field(...)` (line 168)

**REMOVE the `validate_display_options` model validator** (lines 193-202) — it cross-validates `display_headers` and `restore_source_headers`, both of which no longer exist. If left intact, it will `AttributeError` at config load time.

**FIRST:** Extract the `_validate_headers` logic from `SinkPathConfig` into a shared module-level function in `config_base.py` (W2 review finding — avoids duplicating the validator between `SinkPathConfig` and `AzureBlobSinkConfig`):

In `src/elspeth/plugins/infrastructure/config_base.py`, add a module-level function:

```python
def validate_headers_value(v: str | dict[str, str] | None) -> str | dict[str, str] | None:
    """Validate a headers config value — shared by SinkPathConfig and AzureBlobSinkConfig.

    Returns the validated value unchanged. Raises ValueError for invalid inputs.
    """
    if v is None:
        return v
    if isinstance(v, dict):
        targets = list(v.values())
        duplicates = [t for t in targets if targets.count(t) > 1]
        if duplicates:
            raise ValueError(f"Duplicate header mapping targets: {sorted(set(duplicates))}")
        return v
    if isinstance(v, str):
        if v not in ("normalized", "original"):
            raise ValueError(f"Invalid header mode '{v}'. Expected 'normalized', 'original', or mapping dict.")
        return v
    raise ValueError(f"headers must be 'normalized', 'original', or a dict mapping, got {type(v).__name__}")
```

Then update `SinkPathConfig._validate_headers` to delegate:

```python
    @field_validator("headers")
    @classmethod
    def _validate_headers(cls, v: str | dict[str, str] | None) -> str | dict[str, str] | None:
        return validate_headers_value(v)
```

**THEN ADD** the `headers` field, validator, and properties to `AzureBlobSinkConfig`:

```python
    headers: str | dict[str, str] | None = Field(
        default=None,
        description="Header output mode: 'normalized', 'original', or {field: header} mapping",
    )

    @field_validator("headers")
    @classmethod
    def _validate_headers(cls, v: str | dict[str, str] | None) -> str | dict[str, str] | None:
        return validate_headers_value(v)  # Shared with SinkPathConfig

    @property
    def headers_mode(self) -> HeaderMode:
        if self.headers is not None:
            return parse_header_mode(self.headers)
        return HeaderMode.NORMALIZED

    @property
    def headers_mapping(self) -> dict[str, str] | None:
        if isinstance(self.headers, dict):
            return self.headers
        return None
```

Also add the necessary imports at the top of `azure_blob_sink.py`:
```python
from elspeth.contracts.header_modes import HeaderMode, parse_header_mode
from elspeth.plugins.infrastructure.config_base import validate_headers_value
```

**Note on `extra="forbid"`:** `AzureBlobSinkConfig` already inherits `model_config = {"extra": "forbid", "frozen": True}` from `PluginConfig` (via `DataPluginConfig`) at `config_base.py:42`. Once the old fields are removed from the class, Pydantic will automatically reject any config YAML that still uses `restore_source_headers` or `display_headers` with a clear validation error. **Do not add a redundant `model_config` override** — it could shadow the `frozen=True` setting.

### Step 3: Add top-level imports and modify AzureBlobSink `__init__`

Add imports at the top of `azure_blob_sink.py`:

```python
from elspeth.contracts.header_modes import HeaderMode, parse_header_mode
from elspeth.plugins.infrastructure.display_headers import (
    init_display_headers,
    apply_display_headers,
    get_effective_display_headers,
    resolve_contract_from_context_if_needed,
    resolve_display_headers_if_needed,
    set_resume_field_resolution,
)
```

Replace the display header initialization (lines 317-321):

```python
# BEFORE:
        self._display_headers = cfg.display_headers
        self._restore_source_headers = cfg.restore_source_headers
        self._resolved_display_headers: dict[str, str] | None = None
        self._display_headers_resolved: bool = False

# AFTER:
        init_display_headers(self, cfg.headers_mode, cfg.headers_mapping)
```

### Step 4: Delete display header methods, update callers to direct calls

**Delete entirely** — all 4 display header methods (lines 523-570):
- `_get_effective_display_headers()` (lines 523-529)
- `set_resume_field_resolution()` (lines 531-537)
- `_resolve_display_headers_if_needed()` (lines 539-562)
- `_apply_display_headers()` (lines 564-570)

**Update `write()` method** (line ~597) to call module functions directly. Azure Blob now gains contract support that it didn't have before:

```python
# BEFORE:
        self._resolve_display_headers_if_needed(ctx)
        ...
        rows = self._apply_display_headers(rows)

# AFTER:
        resolve_contract_from_context_if_needed(self, ctx)   # NEW — contract support (see Design Note)
        resolve_display_headers_if_needed(self, ctx)
        ...
        rows = apply_display_headers(self, rows)
```

Any other internal callers of `self._get_effective_display_headers()` → `get_effective_display_headers(self)`.

**Keep as a thin public method** — `set_resume_field_resolution()`:

```python
    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        set_resume_field_resolution(self, resolution_mapping)
```

### Step 5: Update Azure Blob tests and check for old config keys everywhere

In `tests/unit/plugins/transforms/azure/test_blob_sink.py`, update the `make_config()` helper:

```python
# BEFORE:
    "display_headers": display_headers,
    "restore_source_headers": restore_source_headers,

# AFTER:
    "headers": headers,  # "original", "normalized", or {mapping}
```

Update any test that passed `restore_source_headers=True` → `headers="original"` and `display_headers={...}` → `headers={...}`.

**Add a test for contract-based header resolution on Azure Blob** — this is new behaviour. Test that when `ctx.contract` is set and mode is ORIGINAL, the contract takes precedence over the Landscape field resolution query. **IMPORTANT (B1 review finding):** The test must assert the actual written output headers, not just that Landscape wasn't called — a silently broken `resolve_contract_from_context_if_needed` would pass a Landscape-only assertion:

```python
def test_write_uses_contract_headers_over_landscape(self) -> None:
    """Contract-based header resolution takes precedence over Landscape query.

    Must verify BOTH that Landscape is not queried AND that the output
    actually uses the contract's original_name values as headers.
    """
    # Set up sink with headers: original
    sink = make_sink(headers="original")
    ctx = make_context()
    ctx.contract = SchemaContract(fields=[
        FieldContract(normalized_name="amount", original_name="Amount USD"),
    ])
    # write() should use contract, not call landscape.get_source_field_resolution()
    sink.write([{"amount": 42}], ctx)
    ctx.landscape.get_source_field_resolution.assert_not_called()

    # Verify the actual output uses contract-derived display headers.
    # Capture the blob content from the mock upload call and check keys.
    uploaded_content = _get_uploaded_blob_content(ctx)  # helper: deserialize mock upload args
    assert "Amount USD" in uploaded_content[0], (
        "Output should use contract original_name 'Amount USD', not normalized 'amount'"
    )
    assert "amount" not in uploaded_content[0], (
        "Normalized key 'amount' should have been replaced by display header"
    )
```

**Add a test for Azure Blob resume path with `headers: original`** (W3 review finding) — verifies `set_resume_field_resolution` works correctly with the new config:

```python
def test_resume_field_resolution_with_headers_original(self) -> None:
    """Resume path correctly builds reverse mapping for headers: original."""
    sink = make_sink(headers="original")
    sink.set_resume_field_resolution({"Amount USD": "amount_usd"})
    assert sink._resolved_display_headers == {"amount_usd": "Amount USD"}
    assert sink._display_headers_resolved is True
```

**Search for old config keys across the entire codebase:**

```bash
grep -r "restore_source_headers\|display_headers" . --include="*.yaml" --include="*.yml" --include="*.md" --include="*.py" --exclude-dir=.git --exclude-dir=.venv
```

This will catch:
- `cli.py` (lines 1835-1845) — handled in Task 5
- `base.py` (lines 419-425) — handled in Task 6
- `plugin_protocols.py` (lines 528-538) — handled in Task 6
- `engine/orchestrator/export.py` (line 87) — handled in Task 6
- `README.md` (lines 386-397) — update to use `headers:` key
- `CHANGELOG-RC2.md` — lower priority, update if appropriate
- `core/landscape/run_lifecycle_repository.py` — check if it references old key names in comments

Update all hits to use `headers: original` terminology.

### Step 6: Run all tests

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_blob_sink.py tests/unit/plugins/sinks/ -v`
Expected: All PASS

### Step 7: Commit

```bash
git add src/elspeth/plugins/sinks/azure_blob_sink.py tests/unit/plugins/transforms/azure/test_blob_sink.py README.md
git commit -m "refactor: AzureBlobSink uses HeaderMode — unifies with CSV/JSON header config"
```

---

## Task 5: Fix CLI resume guard — add typed `needs_resume_field_resolution` property

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/base.py` — add `needs_resume_field_resolution` property
- Modify: `src/elspeth/plugins/infrastructure/display_headers.py` — set property during init
- Modify: `src/elspeth/cli.py` (lines 1835-1845)

**Why this is needed:** The CLI resume code at `cli.py:1835-1845` reads the raw YAML options dict and looks for a key named `restore_source_headers`. After Task 4, Azure Blob no longer has this key — it has `headers`. So any Azure Blob sink configured with `headers: original` will silently skip the `set_resume_field_resolution()` call, and resume validation will compare normalized headers against a file written with original headers.

This is also a latent bug for CSV/JSON sinks — the guard only fires for the old `restore_source_headers: true` key, not for `headers: original` via `SinkPathConfig`.

### Step 1: Add `needs_resume_field_resolution` property to `BaseSink`

In `src/elspeth/plugins/infrastructure/base.py`, add to `BaseSink.__init__`:

```python
        self._needs_resume_field_resolution: bool = False
```

And add a property:

```python
    @property
    def needs_resume_field_resolution(self) -> bool:
        """Whether this sink needs field resolution during resume.

        Set to True by init_display_headers() when headers mode is ORIGINAL.
        Used by CLI resume guard to determine whether to call
        set_resume_field_resolution() before validate_output_target().
        """
        return self._needs_resume_field_resolution
```

### Step 2: Set the property in `init_display_headers()`

In `display_headers.py`, update `init_display_headers()` to set the flag:

```python
    sink._headers_mode = headers_mode
    sink._headers_custom_mapping = headers_custom_mapping
    sink._resolved_display_headers = None
    sink._display_headers_resolved = False
    sink._needs_resume_field_resolution = (headers_mode == HeaderMode.ORIGINAL)
```

Also add `_needs_resume_field_resolution: bool` to the `DisplayHeaderHost` protocol in `plugin_protocols.py`.

### Step 3: Replace the stringly-typed CLI guard with a typed property check

```python
# BEFORE (lines 1835-1845):
            # For sinks with restore_source_headers=True, provide field resolution
            # mapping BEFORE validation so they can correctly compare display names
            sink_opts = dict(settings_config.sinks[sink_name].options)
            restore_source_headers = sink_opts.get("restore_source_headers", False)
            if restore_source_headers:
                from elspeth.core.landscape import LandscapeRecorder

                recorder = LandscapeRecorder(db)
                field_resolution = recorder.get_source_field_resolution(run_id)
                if field_resolution is not None:
                    sink.set_resume_field_resolution(field_resolution)

# AFTER:
            # For sinks with headers: original, provide field resolution mapping
            # BEFORE validation so they can correctly compare display names.
            if sink.needs_resume_field_resolution:
                from elspeth.core.landscape import LandscapeRecorder

                recorder = LandscapeRecorder(db)
                field_resolution = recorder.get_source_field_resolution(run_id)
                if field_resolution is not None:
                    sink.set_resume_field_resolution(field_resolution)
```

This eliminates the stringly-typed YAML key lookup entirely. The sink itself knows whether it needs field resolution — the CLI doesn't need to reparse config.

### Step 4: Run existing resume tests

Run: `.venv/bin/python -m pytest tests/ -k "resume" -v`
Expected: All PASS

### Step 5: Commit

```bash
git add src/elspeth/plugins/infrastructure/base.py src/elspeth/plugins/infrastructure/display_headers.py src/elspeth/contracts/plugin_protocols.py src/elspeth/cli.py
git commit -m "fix: CLI resume guard uses typed sink property — eliminates stringly-typed YAML key lookup"
```

---

## Task 6: Full regression, docstring updates, and cleanup

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/base.py` — update `set_resume_field_resolution` docstring
- Modify: `src/elspeth/contracts/plugin_protocols.py` — update `set_resume_field_resolution` docstring
- Modify: `src/elspeth/engine/orchestrator/export.py` — update comment (line 87)
- Clean: `config/cicd/contracts-whitelist.yaml` — remove stale entries for deleted methods
- Possibly modify: `src/elspeth/plugins/infrastructure/__init__.py` (export new module if needed)
- Test: ALL existing tests

### Step 1: Update stale `restore_source_headers` references in docstrings

In `src/elspeth/plugins/infrastructure/base.py` (lines 416-426), update the docstring:

```python
# BEFORE:
    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        """Set field resolution mapping for resume validation.

        Default is a no-op. Only sinks that support restore_source_headers
        (CSVSink, JSONSink) override this to use the mapping for validation.
        ...
        """
        # Intentional no-op - most sinks don't use restore_source_headers

# AFTER:
    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        """Set field resolution mapping for resume validation.

        Default is a no-op. Only sinks configured with headers: original
        override this to use the mapping for validation.
        ...
        """
        # Intentional no-op - most sinks don't use headers: original
```

In `src/elspeth/contracts/plugin_protocols.py` (lines 524-539), update the docstring similarly:

```python
# BEFORE:
        """...This allows sinks using restore_source_headers=True to correctly compare...
        ...Only sinks that support restore_source_headers need to override this (CSVSink, JSONSink)."""

# AFTER:
        """...This allows sinks using headers: original to correctly compare...
        ...Only sinks configured with headers: original need to override this."""
```

In `src/elspeth/engine/orchestrator/export.py` (line 87), update the comment:

```python
# BEFORE:
    # (restore_source_headers=True calls ctx.landscape.get_source_field_resolution).

# AFTER:
    # (headers: original calls ctx.landscape.get_source_field_resolution).
```

### Step 2: Clean stale contracts-whitelist.yaml entries

Check `config/cicd/contracts-whitelist.yaml` for entries referencing methods that were deleted from the sinks (e.g., `_apply_display_headers`, `_get_effective_display_headers`, `set_output_contract`, `get_output_contract`). Remove any stale entries.

### Step 3: Run the full test suite

Run: `.venv/bin/python -m pytest tests/ -x -q`
Expected: All PASS

### Step 4: Run type checker

Run: `.venv/bin/python -m mypy src/elspeth/plugins/sinks/csv_sink.py src/elspeth/plugins/sinks/json_sink.py src/elspeth/plugins/sinks/azure_blob_sink.py src/elspeth/plugins/infrastructure/display_headers.py src/elspeth/contracts/plugin_protocols.py`
Expected: No errors

### Step 5: Run linter

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/sinks/ src/elspeth/plugins/infrastructure/display_headers.py src/elspeth/contracts/plugin_protocols.py`
Expected: No errors

### Step 6: Run tier model enforcer

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: No new violations (display_headers.py is L3→L0 imports only)

### Step 7: Verify line count reduction

Run a quick count of removed lines vs. added lines. The shared module should be ~180 lines. The three sinks should have lost ~140 lines (CSV), ~170 lines (JSON), and ~50 lines (Azure Blob). Net reduction should be ~180+ lines.

### Step 8: Final commit (if any cleanup was needed)

Stage only the specific files that needed cleanup (avoid `git add -A` per project git safety conventions), then commit:

```bash
git add src/elspeth/plugins/infrastructure/base.py src/elspeth/contracts/plugin_protocols.py src/elspeth/engine/orchestrator/export.py config/cicd/contracts-whitelist.yaml
git commit -m "chore: update stale restore_source_headers references and clean whitelist after extraction"
```

---

## Verification Checklist

Before closing the filigree issue, verify:

- [ ] `DisplayHeaderHost` protocol added to `contracts/plugin_protocols.py` (not a standalone file, NOT `@runtime_checkable`)
- [ ] All module functions typed with `DisplayHeaderHost`, not `Any`
- [ ] `init_display_headers()` has offensive assertion for missing `_output_contract`
- [ ] `init_display_headers()` sets `_needs_resume_field_resolution = (headers_mode == HeaderMode.ORIGINAL)`
- [ ] `resolve_display_headers_if_needed()` sets `_display_headers_resolved = True` AFTER successful resolution (not before)
- [ ] `set_resume_field_resolution()` and `resolve_display_headers_if_needed()` validate for duplicate values in reverse mapping
- [ ] `_get_effective_display_headers()` removed from all 3 sinks — callers use `get_effective_display_headers(self)` directly
- [ ] `set_output_contract()` / `get_output_contract()` removed from CSV/JSON (inherited from BaseSink)
- [ ] `_resolve_contract_from_context_if_needed()` removed from CSV/JSON — `write()` calls module function directly
- [ ] `set_resume_field_resolution()` kept as thin public method on all 3 sinks (public interface for CLI resume)
- [ ] `_resolve_display_headers_if_needed()` removed from all 3 sinks — `write()` calls module function directly
- [ ] `_apply_display_headers()` removed from JSON/Azure — `write()` calls module function directly
- [ ] CSV's `_get_field_names_and_display()` remains unchanged (CSV-specific DictWriter logic)
- [ ] Azure Blob uses `headers: original` instead of `restore_source_headers: true`
- [ ] Azure Blob uses `headers: {mapping}` instead of `display_headers: {mapping}`
- [ ] `AzureBlobSinkConfig.validate_display_options` model validator deleted (line 194)
- [ ] `AzureBlobSinkConfig._validate_headers` delegates to shared `validate_headers_value()` in `config_base.py`
- [ ] `SinkPathConfig._validate_headers` also delegates to shared `validate_headers_value()` in `config_base.py`
- [ ] `AzureBlobSinkConfig` rejects old keys via inherited `extra="forbid"` (no override needed)
- [ ] Azure Blob contract-priority test asserts actual written output headers (not just `assert_not_called`)
- [ ] Azure Blob resume path test with `headers: original` exists
- [ ] Passthrough-key vs mapped-display-name collision test exists
- [ ] CLI resume guard (`cli.py:1835-1845`) uses `sink.needs_resume_field_resolution` property
- [ ] `BaseSink` has `needs_resume_field_resolution` property (default `False`)
- [ ] `BaseSink.set_resume_field_resolution` docstring updated to reference `headers: original`
- [ ] `SinkProtocol.set_resume_field_resolution` docstring updated to reference `headers: original`
- [ ] `engine/orchestrator/export.py` comment updated to reference `headers: original`
- [ ] No example YAMLs, docs, README.md, or Python files reference old `restore_source_headers` key
- [ ] Stale `contracts-whitelist.yaml` entries cleaned for deleted methods
- [ ] All 60+ existing header tests pass
- [ ] mypy clean
- [ ] ruff clean
- [ ] tier model enforcer clean
