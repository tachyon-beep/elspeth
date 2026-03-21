# Freeze/Serialize Coherence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `contracts/hashing.py` handle frozen container types (`MappingProxyType`, `tuple`) natively, fixing the impedance mismatch between `deep_freeze` and canonical JSON serialization at L0.

**Architecture:** A single recursive traversal function in `contracts/hashing.py` normalizes frozen containers to their mutable equivalents before passing to `rfc8785.dumps()`. This makes L0's hashing module coherent with L0's freeze module. Two ancillary fixes: ArtifactDescriptor shallow→deep freeze, and plugin_context.py thaw-refreeze elimination.

**Tech Stack:** Python stdlib (`types.MappingProxyType`, `collections.abc.Mapping`), `rfc8785`, Hypothesis (property tests), pytest.

**Spec:** `docs/superpowers/specs/2026-03-21-freeze-serialize-coherence-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/elspeth/contracts/hashing.py` | Combined normalize + reject traversal |
| Modify | `src/elspeth/contracts/results.py` | ArtifactDescriptor deep freeze |
| Modify | `src/elspeth/contracts/plugin_context.py` | Eliminate thaw-refreeze cycle |
| Create | `tests/property/canonical/test_freeze_hash_equivalence.py` | T1: Hash equivalence property test |
| Modify | `tests/unit/contracts/test_hashing.py` | T2: Frozen-type unit tests, T3: Cross-module parity |
| Modify | `tests/unit/plugins/test_context.py` | T5: Plugin context thaw-refreeze tests |

---

## Task 1: Frozen-Type Unit Tests (T2)

Write the failing tests first — these define the contract for the hashing.py change.

**Files:**
- Modify: `tests/unit/contracts/test_hashing.py`

**Note:** The existing `TestRejectNonFiniteMappingProxyType` class (line 175) already covers NaN/Infinity rejection inside `MappingProxyType` — the `_reject_non_finite` function was already updated to use `isinstance(obj, Mapping)`. Those tests pass today. Our new tests focus on the *serialization* path: can `canonical_json` produce output from frozen containers (not just validate them)?

- [ ] **Step 1: Write failing tests for frozen-type serialization**

Add a new test class after the existing `TestRejectNonFiniteMappingProxyType` class (after line 219):

```python
from types import MappingProxyType


class TestFrozenTypeHandling:
    """contracts/hashing must serialize frozen container types from deep_freeze.

    NaN/Infinity rejection inside MappingProxyType is already covered by
    TestRejectNonFiniteMappingProxyType above. These tests verify the
    serialization path: canonical_json must produce correct output from
    frozen containers, not just validate them.
    """

    def test_mapping_proxy_simple(self) -> None:
        frozen = MappingProxyType({"a": 1, "b": "hello"})
        assert canonical_json(frozen) == canonical_json({"a": 1, "b": "hello"})

    def test_mapping_proxy_nested(self) -> None:
        frozen = MappingProxyType({"a": MappingProxyType({"b": 2})})
        assert canonical_json(frozen) == canonical_json({"a": {"b": 2}})

    def test_mapping_proxy_with_tuple(self) -> None:
        frozen = MappingProxyType({"items": (1, 2, 3)})
        assert canonical_json(frozen) == canonical_json({"items": [1, 2, 3]})

    def test_deeply_nested_frozen(self) -> None:
        frozen = MappingProxyType({
            "level1": MappingProxyType({
                "level2": (
                    MappingProxyType({"level3": "deep"}),
                ),
            }),
        })
        expected = {"level1": {"level2": [{"level3": "deep"}]}}
        assert canonical_json(frozen) == canonical_json(expected)

    def test_stable_hash_frozen_equals_unfrozen(self) -> None:
        data = {"key": "value", "nested": {"inner": [1, 2]}}
        frozen = MappingProxyType({
            "key": "value",
            "nested": MappingProxyType({"inner": (1, 2)}),
        })
        assert stable_hash(frozen) == stable_hash(data)

    def test_rejects_frozenset_with_type_error(self) -> None:
        with pytest.raises(TypeError, match="frozenset"):
            canonical_json({"s": frozenset({1, 2})})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_hashing.py::TestFrozenTypeHandling -v`

Expected: 5 FAILs on the serialization tests (`CanonicalizationError: unsupported type: <class 'mappingproxy'>`). The `frozenset` test may fail differently (rfc8785 may reject it with a different error, or the new `TypeError` guard catches it first after the fix).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/unit/contracts/test_hashing.py
git commit -m "test: add failing frozen-type serialization tests for contracts/hashing (T2)"
```

---

## Task 2: Cross-Module Parity Tests (T3)

**Files:**
- Modify: `tests/unit/contracts/test_hashing.py`

- [ ] **Step 1: Write failing parity tests for frozen inputs**

Extend the existing `TestCanonicalJsonConsistency` class (after line 130):

```python
    def test_matches_core_canonical_for_mapping_proxy(self) -> None:
        from types import MappingProxyType

        frozen = MappingProxyType({"str": "hello", "int": 42, "nested": MappingProxyType({"x": 1})})
        assert contracts_hashing.canonical_json(frozen) == core_canonical.canonical_json(frozen)

    def test_stable_hash_matches_core_for_frozen(self) -> None:
        from types import MappingProxyType

        frozen = MappingProxyType({"key": "value", "list": (1, 2, 3)})
        assert contracts_hashing.stable_hash(frozen) == core_canonical.stable_hash(frozen)

    def test_matches_core_canonical_for_deeply_nested_frozen(self) -> None:
        from types import MappingProxyType

        frozen = MappingProxyType({
            "a": MappingProxyType({"b": (MappingProxyType({"c": 3}),)}),
        })
        assert contracts_hashing.canonical_json(frozen) == core_canonical.canonical_json(frozen)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_hashing.py::TestCanonicalJsonConsistency -v`

Expected: The new tests FAIL with `CanonicalizationError` from contracts hashing (core canonical already works).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/unit/contracts/test_hashing.py
git commit -m "test: add failing cross-module parity tests for frozen inputs (T3)"
```

---

## Task 3: Implement `contracts/hashing.py` — Combined Normalize + Reject

This is the core fix. Replace the validate-only `_reject_non_finite()` with a normalize-and-validate function that returns the normalized structure.

**Files:**
- Modify: `src/elspeth/contracts/hashing.py`

- [ ] **Step 1: Implement the combined traversal**

Replace the entire `_reject_non_finite` function and update `canonical_json` to use the returned value. The file already imports `Mapping` from `collections.abc` (line 20). Add the `MappingProxyType` import from `types`.

The full updated `hashing.py` content (lines 1-68, everything above `stable_hash`):

```python
"""Canonical hashing for the contracts layer.

Provides canonical JSON serialization (RFC 8785/JCS) and stable hashing
for data that contains JSON-safe primitives and their frozen equivalents.
Frozen container types produced by ``deep_freeze`` (``MappingProxyType``,
``tuple``) are normalized to their mutable equivalents before serialization.

This module exists to break the circular dependency between contracts/
and core/canonical.py. For data containing pandas/numpy types or
PipelineRow, use elspeth.core.canonical instead — it adds a normalization
phase for domain-specific types before delegating to rfc8785.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import rfc8785

# Version string stored with every run for hash verification.
# Single source of truth — core/canonical.py imports this constant.
CANONICAL_VERSION = "sha256-rfc8785-v1"


def _normalize_frozen_and_reject_non_finite(obj: Any) -> Any:
    """Normalize frozen containers and reject non-finite floats.

    Single recursive traversal that:
    - Converts ``MappingProxyType`` → ``dict`` (recurse into values)
    - Rejects ``frozenset`` with ``TypeError`` (no canonical JSON ordering)
    - Rejects NaN/Infinity with ``ValueError``
    - Returns the normalized structure ready for ``rfc8785.dumps()``

    ORDERING CONSTRAINT: The ``MappingProxyType`` check must come before
    the general ``Mapping`` check, because ``MappingProxyType`` is a
    subtype of ``Mapping``. Checking ``Mapping`` first would recurse
    without converting to ``dict``.
    """
    if isinstance(obj, float):
        if math.isnan(obj):
            raise ValueError(f"Cannot canonicalize NaN. Use None for missing values, not NaN. Got: {obj!r}")
        if math.isinf(obj):
            raise ValueError(f"Cannot canonicalize Infinity. Use None for missing values, not Infinity. Got: {obj!r}")
        return obj
    if isinstance(obj, frozenset):
        raise TypeError(
            f"frozenset is not JSON-serializable and has no canonical ordering. "
            f"Use list or tuple for ordered collections. Got: {obj!r}"
        )
    # MappingProxyType before Mapping — MappingProxyType IS-A Mapping,
    # so checking Mapping first would skip the dict conversion.
    if isinstance(obj, MappingProxyType):
        return {k: _normalize_frozen_and_reject_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, Mapping):
        return {k: _normalize_frozen_and_reject_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_frozen_and_reject_non_finite(item) for item in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Produce canonical JSON per RFC 8785/JCS.

    Handles JSON-safe primitives and their frozen equivalents
    (``MappingProxyType`` → ``dict``, ``tuple`` → ``list``).
    For data containing pandas/numpy types or PipelineRow, use
    ``elspeth.core.canonical.canonical_json()`` instead.

    Args:
        obj: JSON-safe data structure, optionally containing frozen containers

    Returns:
        Canonical JSON string (deterministic key order, no whitespace)

    Raises:
        ValueError: If data contains NaN or Infinity
        TypeError: If data contains frozenset or other non-serializable types
    """
    normalized = _normalize_frozen_and_reject_non_finite(obj)
    result: bytes = rfc8785.dumps(normalized)
    return result.decode("utf-8")
```

Leave `stable_hash()` and `repr_hash()` unchanged — they delegate to `canonical_json()` which now normalizes.

**Note — behavioral expansion:** The old `_reject_non_finite` recursed into `Mapping` values but did NOT convert them to `dict`. The new function converts ALL `Mapping` subclasses to `dict` during normalization. This is correct — `rfc8785.dumps()` needs plain dicts — but it's a subtle behavioral change for any code passing custom `Mapping` subclasses. In practice, no ELSPETH code does this (only `dict` and `MappingProxyType` appear), so the risk is negligible.

- [ ] **Step 2: Run T2 and T3 tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_hashing.py::TestFrozenTypeHandling tests/unit/contracts/test_hashing.py::TestCanonicalJsonConsistency -v`

Expected: ALL PASS.

- [ ] **Step 3: Run ALL existing hashing tests to verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_hashing.py -v`

Expected: ALL PASS — existing NaN rejection, type rejection, parity, and version tests must still work.

- [ ] **Step 4: Commit**

```bash
git add src/elspeth/contracts/hashing.py
git commit -m "feat: make contracts/hashing handle frozen container types (MappingProxyType, tuple)"
```

---

## Task 4: Hash Equivalence Property Test (T1)

**Files:**
- Create: `tests/property/canonical/test_freeze_hash_equivalence.py`

- [ ] **Step 1: Write the property test**

```python
"""Property test: frozen and unfrozen data produce identical hashes.

This is the core invariant for freeze/serialize coherence:
canonical_json(deep_freeze(x)) == canonical_json(x) for all JSON-like x.

Uses contracts.hashing (not core.canonical) because that's the module
we fixed. Core.canonical already passed via the Mapping ABC.
"""

from __future__ import annotations

from hypothesis import given, settings

from elspeth.contracts.freeze import deep_freeze
from elspeth.contracts.hashing import canonical_json, stable_hash
from tests.strategies.json import json_values


@given(data=json_values)
@settings(max_examples=200)
def test_canonical_json_frozen_equals_unfrozen(data: object) -> None:
    """canonical_json(deep_freeze(x)) must equal canonical_json(x)."""
    frozen = deep_freeze(data)
    assert canonical_json(frozen) == canonical_json(data)


@given(data=json_values)
@settings(max_examples=200)
def test_stable_hash_frozen_equals_unfrozen(data: object) -> None:
    """stable_hash(deep_freeze(x)) must equal stable_hash(x)."""
    frozen = deep_freeze(data)
    assert stable_hash(frozen) == stable_hash(data)
```

- [ ] **Step 2: Run the property test**

Run: `.venv/bin/python -m pytest tests/property/canonical/test_freeze_hash_equivalence.py -v`

Expected: PASS (200 examples each, exercising dicts, lists, nested structures, primitives — all frozen and hashed identically).

- [ ] **Step 3: Commit**

```bash
git add tests/property/canonical/test_freeze_hash_equivalence.py
git commit -m "test: add hash equivalence property test — frozen equals unfrozen (T1)"
```

---

## Task 5: ArtifactDescriptor Deep Freeze

**Files:**
- Modify: `src/elspeth/contracts/results.py`

- [ ] **Step 1: Write a failing test**

Find the existing test file for ArtifactDescriptor. If no test exists for metadata immutability, add one to `tests/unit/contracts/test_results.py` (or the file where ArtifactDescriptor tests live):

```python
from types import MappingProxyType

from elspeth.contracts.results import ArtifactDescriptor


class TestArtifactDescriptorDeepFreeze:
    """ArtifactDescriptor.metadata must be deeply frozen."""

    def test_nested_metadata_is_frozen(self) -> None:
        """Nested dicts in metadata must become MappingProxyType."""
        descriptor = ArtifactDescriptor(
            artifact_type="file",
            path_or_uri="/tmp/test.csv",
            content_hash="abc123",
            size_bytes=100,
            metadata={"nested": {"inner_key": "inner_value"}},
        )
        assert isinstance(descriptor.metadata, MappingProxyType)
        # The nested dict must also be frozen
        assert isinstance(descriptor.metadata["nested"], MappingProxyType)

    def test_nested_list_in_metadata_is_frozen(self) -> None:
        """Nested lists in metadata must become tuples."""
        descriptor = ArtifactDescriptor(
            artifact_type="file",
            path_or_uri="/tmp/test.csv",
            content_hash="abc123",
            size_bytes=100,
            metadata={"tags": ["a", "b"]},
        )
        assert isinstance(descriptor.metadata["tags"], tuple)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_results.py::TestArtifactDescriptorDeepFreeze -v`

Expected: FAIL — nested dict is still a plain `dict` (shallow freeze only wraps the top level).

- [ ] **Step 3: Fix ArtifactDescriptor**

In `src/elspeth/contracts/results.py`, add the import and replace the shallow wrap:

Add to imports (near the top of file, alongside existing `MappingProxyType` import). This is an intra-L0 import (`contracts.results` → `contracts.freeze`) with no circular dependency risk — `freeze.py` imports nothing from the contracts layer:
```python
from elspeth.contracts.freeze import deep_freeze
```

Replace line 394:
```python
# Before:
object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

# After:
object.__setattr__(self, "metadata", deep_freeze(self.metadata))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_results.py::TestArtifactDescriptorDeepFreeze -v`

Expected: PASS.

- [ ] **Step 5: Run all results tests for regression**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_results.py -v`

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/contracts/results.py tests/unit/contracts/test_results.py
git commit -m "fix: ArtifactDescriptor uses deep_freeze instead of shallow MappingProxyType wrap"
```

---

## Task 6: Plugin Context Thaw-Refreeze Elimination (T5)

**Files:**
- Modify: `src/elspeth/contracts/plugin_context.py`
- Modify: `tests/unit/plugins/test_context.py`

- [ ] **Step 1: Write failing tests for frozen-data handling**

Add tests to `tests/unit/plugins/test_context.py`. Use the same fixture pattern as the existing `TestRecordCallPayloadImmutability` class (line 635) — `MagicMock` landscape, capture function for telemetry, `PluginContext` construction.

```python
from types import MappingProxyType


class TestRecordCallFrozenData:
    """record_call must work with frozen container data (no thaw-refreeze).

    After removing deep_thaw from record_call, request_data/response_data
    may contain MappingProxyType values. RawCallPayload must receive and
    freeze them correctly, and token usage extraction must use Mapping ABC.
    """

    def test_token_usage_extracted_from_mapping_proxy(self) -> None:
        """Token usage extraction must work when raw_usage is MappingProxyType.

        This is the critical regression guard for the isinstance(Mapping)
        widening. If this check reverts to isinstance(dict), frozen LLM
        responses silently lose token usage data.
        """
        from typing import Any
        from unittest.mock import MagicMock

        from elspeth.contracts.enums import CallStatus, CallType
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.contracts.token_usage import TokenUsage
        from elspeth.core.canonical import stable_hash

        emitted_events: list[Any] = []

        mock_landscape = MagicMock()
        mock_landscape.record_call.return_value = MagicMock(
            call_id="call-001",
            request_hash=stable_hash({"prompt": "hi"}),
            response_hash=stable_hash({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
        )

        ctx = PluginContext(
            run_id="test-run",
            config={},
            landscape=mock_landscape,
            state_id="state-001",
            telemetry_emit=emitted_events.append,
        )

        # Response with frozen usage dict (MappingProxyType, not plain dict)
        frozen_response = {
            "content": "hello",
            "usage": MappingProxyType({
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }),
        }

        ctx.record_call(
            call_type=CallType.LLM,
            provider="openrouter",
            request_data={"prompt": "hi"},
            response_data=frozen_response,
            latency_ms=12.0,
            status=CallStatus.SUCCESS,
        )

        assert len(emitted_events) == 1
        event = emitted_events[0]
        # Token usage must be extracted despite usage being MappingProxyType
        assert event.token_usage is not None
        assert event.token_usage == TokenUsage(prompt_tokens=10, completion_tokens=5)

    def test_raw_call_payload_freezes_data_without_intermediate_thaw(self) -> None:
        """RawCallPayload must receive frozen data and freeze it correctly.

        Verifies the spec requirement: 'RawCallPayload receives and freezes
        the data correctly without intermediate thaw.'
        """
        from typing import Any
        from unittest.mock import MagicMock

        from elspeth.contracts.call_data import RawCallPayload
        from elspeth.contracts.enums import CallStatus, CallType
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.core.canonical import stable_hash

        emitted_events: list[Any] = []

        expected_request = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        mock_landscape = MagicMock()
        mock_landscape.record_call.return_value = MagicMock(
            call_id="call-001",
            request_hash=stable_hash(expected_request),
            response_hash=stable_hash({"ok": True}),
        )

        ctx = PluginContext(
            run_id="test-run",
            config={},
            landscape=mock_landscape,
            state_id="state-001",
            telemetry_emit=emitted_events.append,
        )

        # Request data with nested frozen containers
        frozen_request = {
            "model": "gpt-4",
            "messages": (MappingProxyType({"role": "user", "content": "hi"}),),
        }

        ctx.record_call(
            call_type=CallType.HTTP,
            provider="api.example.com",
            request_data=frozen_request,
            response_data={"ok": True},
            latency_ms=5.0,
            status=CallStatus.SUCCESS,
        )

        assert len(emitted_events) == 1
        event = emitted_events[0]
        # RawCallPayload must contain the data (frozen internally by deep_freeze)
        assert isinstance(event.request_payload, RawCallPayload)
        # to_dict() must produce the equivalent unfrozen structure
        assert event.request_payload.to_dict() == expected_request
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/test_context.py::TestRecordCallFrozenData -v`

Expected: FAIL — the `isinstance(raw_usage, dict)` check at line 334 rejects `MappingProxyType`, so token usage is `None` when it should have data.

- [ ] **Step 3: Implement the plugin_context.py changes**

In `src/elspeth/contracts/plugin_context.py`:

**3a.** Remove the `deep_thaw` import and calls. Replace lines 317-324:

```python
# Before:
            # Snapshot payloads so async telemetry exports can't drift from call-time values.
            # Use deep_thaw instead of deepcopy — frozen checkpoint data contains
            # MappingProxyType which can't be pickled/deepcopied. deep_thaw creates
            # the mutable copy we need and handles frozen containers correctly.
            from elspeth.contracts.freeze import deep_thaw

            request_snapshot = deep_thaw(request_data)
            response_snapshot = deep_thaw(response_data) if response_data is not None else None

# After:
            # Pass data directly to RawCallPayload. No defensive copy needed:
            # RawCallPayload.__init__ calls deep_freeze(), which creates an
            # independent frozen copy. Callers mutating the original dict after
            # record_call() won't affect the telemetry payload.
            # (Existing test: test_request_payload_snapshot_is_immutable_after_call)
            request_snapshot = request_data
            response_snapshot = response_data
```

**Snapshot safety note:** The original `deep_thaw` created a mutable copy to prevent caller mutation from affecting telemetry. Removing it is safe because `RawCallPayload.__init__` calls `deep_freeze()`, which creates new container objects via dict comprehension (`{k: deep_freeze(v) for k, v in value.items()}`). This is an independent copy — the caller's original dict and the frozen payload share no mutable state. The existing test `test_request_payload_snapshot_is_immutable_after_call` (line 645) verifies this invariant.

**3b.** Widen the `isinstance` check at line 334. Add `Mapping` import:

```python
# At the top of the function (or module-level):
from collections.abc import Mapping

# Replace line 334:
# Before:
                if isinstance(raw_usage, dict):

# After:
                if isinstance(raw_usage, Mapping):
```

Also update the comment at line 327 to reflect that response_snapshot may contain frozen containers:

```python
            # Extract token usage for LLM calls if available.
            # response_snapshot may contain frozen containers (MappingProxyType) —
            # use Mapping ABC for isinstance checks, not dict.
```

- [ ] **Step 4: Run T5 tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/test_context.py::TestRecordCallFrozenData -v`

Expected: PASS.

- [ ] **Step 5: Run all plugin context tests for regression**

Run: `.venv/bin/python -m pytest tests/unit/plugins/test_context.py -v`

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/contracts/plugin_context.py tests/unit/plugins/test_context.py
git commit -m "fix: eliminate thaw-refreeze cycle in plugin_context.record_call"
```

---

## Task 7: Round-Trip Contract Tests (T4)

These tests verify that hashing a thawed dict equals hashing its frozen equivalent — the coherence guarantee that justifies both paths coexisting.

**Files:**
- Modify: `tests/unit/contracts/test_hashing.py`

- [ ] **Step 1: Write round-trip contract tests**

Add a new class after `TestFrozenTypeHandling`:

```python
from elspeth.contracts.freeze import deep_freeze


class TestFrozenRoundTripContracts:
    """Hashing thawed output must equal hashing the frozen equivalent.

    This guarantees that to_dict() (which thaws) and direct frozen access
    produce identical hashes — the coherence invariant.
    """

    def test_simple_dict_round_trip(self) -> None:
        original = {"key": "value", "num": 42}
        frozen = deep_freeze(original)
        assert canonical_json(original) == canonical_json(frozen)

    def test_nested_dict_round_trip(self) -> None:
        original = {"outer": {"inner": [1, 2, {"deep": True}]}}
        frozen = deep_freeze(original)
        assert canonical_json(original) == canonical_json(frozen)

    def test_list_of_dicts_round_trip(self) -> None:
        original = [{"a": 1}, {"b": 2}, {"c": [3, 4]}]
        frozen = deep_freeze(original)
        assert canonical_json(original) == canonical_json(frozen)

    def test_stable_hash_round_trip(self) -> None:
        original = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        frozen = deep_freeze(original)
        assert stable_hash(original) == stable_hash(frozen)

    def test_empty_containers_round_trip(self) -> None:
        original = {"empty_dict": {}, "empty_list": []}
        frozen = deep_freeze(original)
        assert canonical_json(original) == canonical_json(frozen)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_hashing.py::TestFrozenRoundTripContracts -v`

Expected: ALL PASS (the hashing fix from Task 3 handles the frozen types).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/contracts/test_hashing.py
git commit -m "test: add frozen round-trip contract tests (T4)"
```

---

## Task 8: Full Regression Check

Run the complete test suite to verify nothing is broken.

**Files:** None (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `.venv/bin/python -m pytest tests/unit/ -x -q`

Expected: ALL PASS.

- [ ] **Step 2: Run all property tests**

Run: `.venv/bin/python -m pytest tests/property/ -x -q`

Expected: ALL PASS.

- [ ] **Step 3: Run type checking**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/hashing.py src/elspeth/contracts/results.py src/elspeth/contracts/plugin_context.py`

Expected: No new errors.

- [ ] **Step 4: Run linting**

Run: `.venv/bin/python -m ruff check src/elspeth/contracts/hashing.py src/elspeth/contracts/results.py src/elspeth/contracts/plugin_context.py`

Expected: No errors.

- [ ] **Step 5: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

Expected: PASS (no new violations — `isinstance(Mapping)` uses the ABC, not a defensive pattern).
