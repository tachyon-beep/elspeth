"""Unit tests for BatchCheckpointState and RowMappingEntry contracts.

P3-2026-02-19: Typed batch checkpoint state replaces dict[str, Any]
at the PluginContext/BatchPendingError boundary. These tests verify:
1. Round-trip serialization (to_dict → from_dict) preserves all fields
2. Frozen immutability prevents mutation
3. Tier 1 crash semantics — missing/corrupt checkpoint data crashes
"""

from __future__ import annotations

import pytest

from elspeth.contracts.batch_checkpoint import BatchCheckpointState, RowMappingEntry
from elspeth.contracts.errors import AuditIntegrityError

# ---------------------------------------------------------------------------
# RowMappingEntry
# ---------------------------------------------------------------------------


class TestRowMappingEntry:
    """Round-trip and crash-on-corruption tests for RowMappingEntry."""

    def test_round_trip(self) -> None:
        entry = RowMappingEntry(index=5, variables_hash="abc123")
        assert RowMappingEntry.from_dict(entry.to_dict()) == entry

    def test_to_dict_shape(self) -> None:
        entry = RowMappingEntry(index=0, variables_hash="deadbeef")
        d = entry.to_dict()
        assert d == {"index": 0, "variables_hash": "deadbeef"}

    def test_frozen(self) -> None:
        entry = RowMappingEntry(index=1, variables_hash="hash")
        with pytest.raises(AttributeError):
            entry.index = 99  # type: ignore[misc]

    def test_from_dict_missing_index_crashes(self) -> None:
        with pytest.raises(KeyError, match="index"):
            RowMappingEntry.from_dict({"variables_hash": "abc"})

    def test_from_dict_missing_hash_crashes(self) -> None:
        with pytest.raises(KeyError, match="variables_hash"):
            RowMappingEntry.from_dict({"index": 0})


# ---------------------------------------------------------------------------
# BatchCheckpointState
# ---------------------------------------------------------------------------


def _make_state(**overrides: object) -> BatchCheckpointState:
    """Build a BatchCheckpointState with sensible defaults, overriding any field."""
    defaults: dict[str, object] = {
        "batch_id": "batch-001",
        "input_file_id": "file-001",
        "row_mapping": {
            "row-0-aaa": RowMappingEntry(index=0, variables_hash="hash0"),
        },
        "template_errors": [],
        "submitted_at": "2026-02-21T10:00:00+00:00",
        "row_count": 1,
        "requests": {
            "row-0-aaa": {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "test"}],
            },
        },
    }
    defaults.update(overrides)
    return BatchCheckpointState(**defaults)  # type: ignore[arg-type]


class TestBatchCheckpointState:
    """Round-trip, immutability, and crash-on-corruption tests."""

    def test_round_trip_preserves_all_fields(self) -> None:
        state = _make_state(
            row_mapping={
                "row-0-aaa": RowMappingEntry(index=0, variables_hash="h0"),
                "row-1-bbb": RowMappingEntry(index=1, variables_hash="h1"),
            },
            template_errors=[(2, "Missing field: text")],
            row_count=3,
        )
        restored = BatchCheckpointState.from_dict(state.to_dict())
        assert restored.batch_id == state.batch_id
        assert restored.input_file_id == state.input_file_id
        assert restored.row_mapping == state.row_mapping
        assert restored.template_errors == state.template_errors
        assert restored.submitted_at == state.submitted_at
        assert restored.row_count == state.row_count
        assert restored.requests == state.requests

    def test_to_dict_wire_format(self) -> None:
        """Serialized form must be wire-compatible with the old dict format."""
        state = _make_state()
        d = state.to_dict()
        assert isinstance(d, dict)
        assert d["batch_id"] == "batch-001"
        assert d["input_file_id"] == "file-001"
        assert d["row_count"] == 1
        # row_mapping values should be plain dicts (not RowMappingEntry)
        mapping_val = d["row_mapping"]["row-0-aaa"]
        assert isinstance(mapping_val, dict)
        assert mapping_val == {"index": 0, "variables_hash": "hash0"}

    def test_frozen_immutability(self) -> None:
        state = _make_state()
        with pytest.raises(AttributeError):
            state.batch_id = "mutated"  # type: ignore[misc]

    # --- Tier 1 crash semantics: missing keys crash on deserialization ---

    def test_from_dict_missing_batch_id_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["batch_id"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_missing_input_file_id_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["input_file_id"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_missing_row_mapping_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["row_mapping"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_missing_submitted_at_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["submitted_at"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_missing_row_count_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["row_count"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_missing_requests_crashes(self) -> None:
        d = _make_state().to_dict()
        del d["requests"]
        with pytest.raises(AuditIntegrityError, match="missing required fields"):
            BatchCheckpointState.from_dict(d)

    def test_from_dict_nested_row_mapping_entry_crashes_on_corruption(self) -> None:
        """Corrupt row_mapping entry (missing 'index') crashes."""
        d = _make_state().to_dict()
        d["row_mapping"]["row-0-aaa"] = {"variables_hash": "h0"}  # missing index
        with pytest.raises(KeyError, match="index"):
            BatchCheckpointState.from_dict(d)

    def test_round_trip_through_json_preserves_tuple_types(self) -> None:
        """Round-trip through JSON serialization must restore tuples, not lists.

        json.loads produces list[list] from list[tuple] — from_dict must convert back.
        This is the real persistence path: to_dict → json.dumps → json.loads → from_dict.
        """
        import json

        state = _make_state(
            template_errors=[(0, "Missing field: text"), (3, "Invalid template")],
        )
        serialized = json.dumps(state.to_dict())
        deserialized = json.loads(serialized)
        restored = BatchCheckpointState.from_dict(deserialized)

        # Must be tuples, not lists
        for entry in restored.template_errors:
            assert isinstance(entry, tuple), f"Expected tuple, got {type(entry).__name__}: {entry}"
        assert restored.template_errors == ((0, "Missing field: text"), (3, "Invalid template"))

    def test_from_dict_template_errors_are_tuples_not_lists(self) -> None:
        """from_dict with list-of-lists (as JSON produces) must convert to tuples."""
        d = _make_state().to_dict()
        d["template_errors"] = [[0, "err0"], [1, "err1"]]  # JSON-style lists
        restored = BatchCheckpointState.from_dict(d)

        for entry in restored.template_errors:
            assert isinstance(entry, tuple), f"Expected tuple, got {type(entry).__name__}"
        assert restored.template_errors == ((0, "err0"), (1, "err1"))

    def test_from_dict_template_error_wrong_length_crashes(self) -> None:
        """Template error entries must be exactly 2-element (index, message)."""
        d = _make_state().to_dict()
        d["template_errors"] = [[0, "err", "extra"]]  # 3 elements — corrupt
        with pytest.raises((ValueError, TypeError)):
            BatchCheckpointState.from_dict(d)

    def test_empty_batch_round_trips(self) -> None:
        """Edge case: batch with no rows (e.g., all template errors)."""
        state = _make_state(
            row_mapping={},
            template_errors=[(0, "err0"), (1, "err1")],
            row_count=0,
            requests={},
        )
        restored = BatchCheckpointState.from_dict(state.to_dict())
        assert restored == state
