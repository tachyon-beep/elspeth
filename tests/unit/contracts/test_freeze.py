# tests/unit/contracts/test_freeze.py
"""Unit tests for deep_freeze / deep_thaw utilities.

These are foundational to the immutability sweep across the contracts layer.
Every frozen dataclass with dict/list fields depends on these functions.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType

import pytest

from elspeth.contracts.freeze import deep_freeze, deep_thaw

# =============================================================================
# deep_freeze
# =============================================================================


class TestDeepFreeze:
    """deep_freeze converts dict→MappingProxyType and list→tuple recursively."""

    # --- Scalar passthrough ---

    @pytest.mark.parametrize(
        "value",
        [None, True, False, 0, 42, 3.14, "", "hello", b"bytes"],
        ids=["None", "True", "False", "zero", "int", "float", "empty_str", "str", "bytes"],
    )
    def test_scalars_returned_unchanged(self, value: object) -> None:
        assert deep_freeze(value) is value

    def test_enum_returned_unchanged(self) -> None:
        class Color(Enum):
            RED = 1

        assert deep_freeze(Color.RED) is Color.RED

    # --- dict → MappingProxyType ---

    def test_empty_dict_becomes_empty_mapping_proxy(self) -> None:
        result = deep_freeze({})
        assert isinstance(result, MappingProxyType)
        assert len(result) == 0

    def test_flat_dict_becomes_mapping_proxy(self) -> None:
        result = deep_freeze({"a": 1, "b": "two"})
        assert isinstance(result, MappingProxyType)
        assert result["a"] == 1
        assert result["b"] == "two"

    def test_dict_is_immutable(self) -> None:
        result = deep_freeze({"a": 1})
        with pytest.raises(TypeError):
            result["a"] = 2

    # --- list → tuple ---

    def test_empty_list_becomes_empty_tuple(self) -> None:
        result = deep_freeze([])
        assert result == ()
        assert isinstance(result, tuple)

    def test_flat_list_becomes_tuple(self) -> None:
        result = deep_freeze([1, 2, 3])
        assert result == (1, 2, 3)
        assert isinstance(result, tuple)

    # --- Nested recursion ---

    def test_nested_dict_in_dict(self) -> None:
        result = deep_freeze({"outer": {"inner": 1}})
        assert isinstance(result, MappingProxyType)
        assert isinstance(result["outer"], MappingProxyType)
        assert result["outer"]["inner"] == 1

    def test_list_in_dict(self) -> None:
        result = deep_freeze({"items": [1, 2, 3]})
        assert isinstance(result, MappingProxyType)
        assert result["items"] == (1, 2, 3)
        assert isinstance(result["items"], tuple)

    def test_dict_in_list(self) -> None:
        result = deep_freeze([{"a": 1}, {"b": 2}])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], MappingProxyType)
        assert result[0]["a"] == 1

    def test_deeply_nested_structure(self) -> None:
        """Three levels deep: dict → list → dict."""
        result = deep_freeze({"a": [{"b": [1, 2]}]})
        assert isinstance(result, MappingProxyType)
        assert isinstance(result["a"], tuple)
        assert isinstance(result["a"][0], MappingProxyType)
        assert result["a"][0]["b"] == (1, 2)

    # --- Already-frozen passthrough ---

    def test_mapping_proxy_returned_as_is(self) -> None:
        already = MappingProxyType({"k": "v"})
        result = deep_freeze(already)
        assert result is already

    def test_tuple_returned_as_is(self) -> None:
        already = (1, 2, 3)
        result = deep_freeze(already)
        assert result is already

    def test_frozenset_returned_as_is(self) -> None:
        already = frozenset({1, 2, 3})
        result = deep_freeze(already)
        assert result is already

    # --- Pre-frozen containers with mutable innards ARE recursed ---

    def test_mapping_proxy_with_mutable_inner_is_recursed(self) -> None:
        """MappingProxyType wrapping a mutable list gets its contents frozen."""
        inner_list = [1, 2, 3]
        already = MappingProxyType({"items": inner_list})
        result = deep_freeze(already)
        assert result is not already
        assert isinstance(result, MappingProxyType)
        assert isinstance(result["items"], tuple)
        assert result["items"] == (1, 2, 3)

    def test_tuple_with_mutable_inner_is_recursed(self) -> None:
        """Tuples containing mutable dicts get their contents frozen."""
        inner_dict = {"a": 1}
        already = (inner_dict,)
        result = deep_freeze(already)
        assert result is not already
        assert isinstance(result, tuple)
        assert isinstance(result[0], MappingProxyType)
        assert result[0]["a"] == 1

    def test_tuple_with_nested_mutable_dict_in_list(self) -> None:
        """Tuple containing a list of dicts — full depth freezing."""
        already = ([{"x": 1}, {"y": 2}],)
        result = deep_freeze(already)
        assert isinstance(result, tuple)
        assert isinstance(result[0], tuple)
        assert isinstance(result[0][0], MappingProxyType)
        assert result[0][0]["x"] == 1

    def test_frozenset_with_mutable_inner_is_recursed(self) -> None:
        """Frozensets containing mutable lists get their contents frozen."""
        already = frozenset({(1, 2), (3, 4)})
        result = deep_freeze(already)
        # All elements are already tuples of ints — identity preserved
        assert result is already


# =============================================================================
# deep_thaw
# =============================================================================


class TestDeepThaw:
    """deep_thaw converts MappingProxyType→dict and tuple→list recursively."""

    # --- Scalar passthrough ---

    @pytest.mark.parametrize(
        "value",
        [None, True, False, 0, 42, 3.14, "", "hello"],
        ids=["None", "True", "False", "zero", "int", "float", "empty_str", "str"],
    )
    def test_scalars_returned_unchanged(self, value: object) -> None:
        assert deep_thaw(value) is value

    # --- MappingProxyType → dict ---

    def test_empty_mapping_proxy_becomes_empty_dict(self) -> None:
        result = deep_thaw(MappingProxyType({}))
        assert result == {}
        assert isinstance(result, dict)

    def test_flat_mapping_proxy_becomes_dict(self) -> None:
        result = deep_thaw(MappingProxyType({"a": 1}))
        assert result == {"a": 1}
        assert isinstance(result, dict)

    # --- tuple → list ---

    def test_empty_tuple_becomes_empty_list(self) -> None:
        result = deep_thaw(())
        assert result == []
        assert isinstance(result, list)

    def test_flat_tuple_becomes_list(self) -> None:
        result = deep_thaw((1, 2, 3))
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    # --- Nested recursion ---

    def test_nested_mapping_proxy_in_mapping_proxy(self) -> None:
        frozen = MappingProxyType({"outer": MappingProxyType({"inner": 1})})
        result = deep_thaw(frozen)
        assert result == {"outer": {"inner": 1}}
        assert isinstance(result["outer"], dict)

    def test_tuple_in_mapping_proxy(self) -> None:
        frozen = MappingProxyType({"items": (1, 2, 3)})
        result = deep_thaw(frozen)
        assert result == {"items": [1, 2, 3]}
        assert isinstance(result["items"], list)

    def test_mapping_proxy_in_tuple(self) -> None:
        frozen = (MappingProxyType({"a": 1}),)
        result = deep_thaw(frozen)
        assert result == [{"a": 1}]
        assert isinstance(result[0], dict)

    def test_deeply_nested_structure(self) -> None:
        frozen = MappingProxyType({"a": (MappingProxyType({"b": (1, 2)}),)})
        result = deep_thaw(frozen)
        assert result == {"a": [{"b": [1, 2]}]}

    # --- Mutable containers also thawed (passthrough in deep_thaw) ---

    def test_plain_dict_also_thawed(self) -> None:
        """deep_thaw handles plain dicts too (recurses into values)."""
        result = deep_thaw({"a": (1, 2)})
        assert result == {"a": [1, 2]}
        assert isinstance(result["a"], list)

    def test_plain_list_also_thawed(self) -> None:
        """deep_thaw handles plain lists too (recurses into items)."""
        result = deep_thaw([MappingProxyType({"a": 1})])
        assert result == [{"a": 1}]
        assert isinstance(result[0], dict)


# =============================================================================
# Round-trip: freeze → thaw
# =============================================================================


class TestFreezeThawRoundTrip:
    """deep_thaw(deep_freeze(x)) should produce a value equal to x for JSON-like structures."""

    @pytest.mark.parametrize(
        "original",
        [
            {},
            {"a": 1},
            {"a": [1, 2, 3]},
            {"a": {"b": {"c": 1}}},
            [1, 2, 3],
            [{"a": 1}, {"b": 2}],
            {"mixed": [1, "two", None, {"nested": [3.14]}]},
            [],
            None,
            42,
            "hello",
        ],
        ids=[
            "empty_dict",
            "flat_dict",
            "dict_with_list",
            "nested_dicts",
            "flat_list",
            "list_of_dicts",
            "mixed_types",
            "empty_list",
            "none",
            "int",
            "str",
        ],
    )
    def test_round_trip_preserves_equality(self, original: object) -> None:
        frozen = deep_freeze(original)
        thawed = deep_thaw(frozen)
        assert thawed == original

    def test_round_trip_dict_produces_dict(self) -> None:
        original = {"a": [1, {"b": 2}]}
        result = deep_thaw(deep_freeze(original))
        assert isinstance(result, dict)
        assert isinstance(result["a"], list)
        assert isinstance(result["a"][1], dict)

    def test_round_trip_list_produces_list(self) -> None:
        original = [{"x": 1}, {"y": 2}]
        result = deep_thaw(deep_freeze(original))
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_frozen_intermediate_is_immutable(self) -> None:
        """The frozen intermediate cannot be mutated."""
        original = {"a": [1, 2], "b": {"c": 3}}
        frozen = deep_freeze(original)

        with pytest.raises(TypeError):
            frozen["a"] = "mutated"

        with pytest.raises(TypeError):
            frozen["b"]["c"] = 99


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:
    """Freezing an already-frozen value should be a no-op."""

    def test_double_freeze_dict(self) -> None:
        original = {"a": [1, {"b": 2}]}
        once = deep_freeze(original)
        twice = deep_freeze(once)
        # Already-frozen MappingProxyType is returned as-is (identity check)
        assert twice is once

    def test_double_freeze_list(self) -> None:
        original = [1, 2, 3]
        once = deep_freeze(original)
        twice = deep_freeze(once)
        # Already-frozen tuple is returned as-is
        assert twice is once

    def test_double_thaw_dict(self) -> None:
        original = {"a": [1, 2]}
        thawed_once = deep_thaw(original)
        thawed_twice = deep_thaw(thawed_once)
        assert thawed_once == thawed_twice


# =============================================================================
# Shallow dict() vs deep_thaw() — checkpoint restore regression
# =============================================================================


class TestShallowDictVsDeepThaw:
    """Regression: elspeth-77602748e9, elspeth-d2f7b61d71.

    Checkpoint restore used dict() on frozen data, leaving nested
    MappingProxyType/tuple inside restored PipelineRow objects. Downstream
    transforms that mutate nested values crash with TypeError on resume.
    """

    def test_dict_leaves_nested_mapping_proxy_frozen(self) -> None:
        """dict() on a frozen mapping only unfreezes the top level."""
        frozen = deep_freeze({"outer": {"inner": [1, 2, 3]}})
        shallow = dict(frozen)

        assert isinstance(shallow, dict)  # Top level is mutable
        assert isinstance(shallow["outer"], MappingProxyType)  # Inner is STILL frozen
        with pytest.raises(TypeError):
            shallow["outer"]["new_key"] = "crash"  # This is the resume crash

    def test_deep_thaw_fully_unfreezes_nested_structure(self) -> None:
        """deep_thaw() recursively unfreezes all containers."""
        frozen = deep_freeze({"outer": {"inner": [1, 2, 3]}})
        thawed = deep_thaw(frozen)

        assert isinstance(thawed, dict)
        assert isinstance(thawed["outer"], dict)  # Inner is now mutable
        assert isinstance(thawed["outer"]["inner"], list)
        thawed["outer"]["new_key"] = "no crash"  # Must not raise

    def test_checkpoint_round_trip_with_nested_json_data(self) -> None:
        """Simulates a checkpoint save/restore cycle with JSON-origin row data."""
        original_row_data = {
            "id": 42,
            "metadata": {"source": "api", "tags": ["urgent", "review"]},
            "nested": {"deep": {"value": 99}},
        }

        # Save path: to_dict() produces plain dicts
        saved = dict(original_row_data)  # to_dict() equivalent

        # If checkpoint serialization involved freezing (e.g., via typed dataclass)
        frozen_checkpoint = deep_freeze(saved)

        # Restore path: deep_thaw instead of dict()
        restored = deep_thaw(frozen_checkpoint)

        assert restored == original_row_data
        assert isinstance(restored["metadata"], dict)
        assert isinstance(restored["metadata"]["tags"], list)
        # Can mutate nested values (downstream transform scenario)
        restored["metadata"]["tags"].append("processed")
        assert "processed" in restored["metadata"]["tags"]
