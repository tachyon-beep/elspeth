# tests/property/contracts/test_serialization_properties.py
"""Property-based tests for contract dataclass serialization.

These tests verify that ELSPETH's core contract dataclasses serialize
correctly for audit storage - a critical requirement for the audit trail.

Serialization Properties:
- TokenInfo preserves identity fields through construction
- TransformResult JSON round-trips preserve data correctly
- RoutingAction JSON round-trips preserve routing decisions
- Frozen dataclasses serialize to valid JSON

IMPORTANT: These tests complement test_results_properties.py and
test_routing_properties.py by focusing on serialization aspects.
Factory method invariants are tested in those other modules.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import RoutingKind, RoutingMode
from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.results import TransformResult
from elspeth.contracts.routing import RoutingAction
from tests.property.conftest import id_strings, row_data

# =============================================================================
# Strategies for serialization testing
# =============================================================================

# Branch names for TokenInfo
token_branch_names = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
)

# Group IDs for TokenInfo
token_group_ids = st.one_of(
    st.none(),
    id_strings,
)

# Non-empty ID strings (required fields)
non_empty_ids = st.text(min_size=1, max_size=40, alphabet="0123456789abcdef")

# Path names for routing
path_names = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_0123456789",
).filter(lambda s: s[0].isalpha())

# Unique path lists for fork
unique_path_lists = st.lists(path_names, min_size=1, max_size=5, unique=True)

# Reason dictionaries (JSON-safe)
reason_dicts = st.dictionaries(
    keys=st.sampled_from(["condition", "threshold", "rule", "match", "reason"]),
    values=st.one_of(st.text(max_size=50), st.integers(min_value=-1000, max_value=1000), st.booleans()),
    min_size=0,
    max_size=3,
)


# =============================================================================
# TokenInfo Construction and Serialization Properties
# =============================================================================


class TestTokenInfoConstructionProperties:
    """Property tests for TokenInfo construction preserving identity."""

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
    )
    @settings(max_examples=100)
    def test_token_info_preserves_row_id(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
    ) -> None:
        """Property: TokenInfo preserves row_id through construction."""
        token = TokenInfo(row_id=row_id, token_id=token_id, row_data=data)
        assert token.row_id == row_id

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
    )
    @settings(max_examples=100)
    def test_token_info_preserves_token_id(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
    ) -> None:
        """Property: TokenInfo preserves token_id through construction."""
        token = TokenInfo(row_id=row_id, token_id=token_id, row_data=data)
        assert token.token_id == token_id

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
    )
    @settings(max_examples=100)
    def test_token_info_preserves_row_data(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
    ) -> None:
        """Property: TokenInfo preserves row_data through construction."""
        token = TokenInfo(row_id=row_id, token_id=token_id, row_data=data)
        assert token.row_data == data

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
        branch_name=token_branch_names,
        fork_group_id=token_group_ids,
        join_group_id=token_group_ids,
        expand_group_id=token_group_ids,
    )
    @settings(max_examples=100)
    def test_token_info_preserves_optional_fields(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
        branch_name: str | None,
        fork_group_id: str | None,
        join_group_id: str | None,
        expand_group_id: str | None,
    ) -> None:
        """Property: TokenInfo preserves all optional fields."""
        token = TokenInfo(
            row_id=row_id,
            token_id=token_id,
            row_data=data,
            branch_name=branch_name,
            fork_group_id=fork_group_id,
            join_group_id=join_group_id,
            expand_group_id=expand_group_id,
        )
        assert token.branch_name == branch_name
        assert token.fork_group_id == fork_group_id
        assert token.join_group_id == join_group_id
        assert token.expand_group_id == expand_group_id


class TestTokenInfoJsonSerializationProperties:
    """Property tests for TokenInfo JSON serialization."""

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
    )
    @settings(max_examples=100)
    def test_token_info_serializes_to_valid_json(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
    ) -> None:
        """Property: TokenInfo serializes to valid JSON."""
        token = TokenInfo(row_id=row_id, token_id=token_id, row_data=data)

        # asdict + json.dumps should not raise
        serialized = json.dumps(asdict(token))

        # Result should be valid JSON
        parsed = json.loads(serialized)
        assert isinstance(parsed, dict)

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
    )
    @settings(max_examples=100)
    def test_token_info_json_round_trip_preserves_identity(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
    ) -> None:
        """Property: TokenInfo JSON round-trip preserves identity fields."""
        token = TokenInfo(row_id=row_id, token_id=token_id, row_data=data)

        serialized = json.dumps(asdict(token))
        parsed = json.loads(serialized)

        assert parsed["row_id"] == row_id
        assert parsed["token_id"] == token_id
        assert parsed["row_data"] == data

    @given(
        row_id=non_empty_ids,
        token_id=non_empty_ids,
        data=row_data,
        branch_name=token_branch_names,
        fork_group_id=token_group_ids,
    )
    @settings(max_examples=100)
    def test_token_info_json_round_trip_preserves_optional_fields(
        self,
        row_id: str,
        token_id: str,
        data: dict[str, Any],
        branch_name: str | None,
        fork_group_id: str | None,
    ) -> None:
        """Property: TokenInfo JSON round-trip preserves optional fields."""
        token = TokenInfo(
            row_id=row_id,
            token_id=token_id,
            row_data=data,
            branch_name=branch_name,
            fork_group_id=fork_group_id,
        )

        serialized = json.dumps(asdict(token))
        parsed = json.loads(serialized)

        assert parsed["branch_name"] == branch_name
        assert parsed["fork_group_id"] == fork_group_id


# =============================================================================
# TransformResult JSON Serialization Properties
# =============================================================================


class TestTransformResultJsonSerializationProperties:
    """Property tests for TransformResult JSON serialization."""

    @given(data=row_data)
    @settings(max_examples=100)
    def test_transform_result_success_serializes_to_valid_json(
        self,
        data: dict[str, Any],
    ) -> None:
        """Property: TransformResult.success() serializes to valid JSON."""
        result = TransformResult.success(data)

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        assert isinstance(parsed, dict)
        assert parsed["status"] == "success"

    @given(data=row_data)
    @settings(max_examples=100)
    def test_transform_result_success_json_round_trip_preserves_row(
        self,
        data: dict[str, Any],
    ) -> None:
        """Property: TransformResult.success() JSON round-trip preserves row."""
        result = TransformResult.success(data)

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        assert parsed["status"] == "success"
        assert parsed["row"] == data
        assert parsed["reason"] is None

    @given(reason=reason_dicts)
    @settings(max_examples=100)
    def test_transform_result_error_json_round_trip_preserves_reason(
        self,
        reason: dict[str, Any],
    ) -> None:
        """Property: TransformResult.error() JSON round-trip preserves reason."""
        result = TransformResult.error(reason)

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        assert parsed["status"] == "error"
        assert parsed["reason"] == reason
        assert parsed["row"] is None

    @given(data=row_data, retryable=st.booleans())
    @settings(max_examples=50)
    def test_transform_result_error_json_round_trip_preserves_retryable(
        self,
        data: dict[str, Any],
        retryable: bool,
    ) -> None:
        """Property: TransformResult.error() JSON round-trip preserves retryable flag."""
        result = TransformResult.error({"reason": "test"}, retryable=retryable)

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        assert parsed["retryable"] is retryable

    @given(rows=st.lists(row_data, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_transform_result_success_multi_json_round_trip_preserves_rows(
        self,
        rows: list[dict[str, Any]],
    ) -> None:
        """Property: TransformResult.success_multi() JSON round-trip preserves rows."""
        result = TransformResult.success_multi(rows)

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        assert parsed["status"] == "success"
        assert parsed["rows"] == rows
        assert parsed["row"] is None


# =============================================================================
# RoutingAction JSON Serialization Properties
# =============================================================================


class TestRoutingActionJsonSerializationProperties:
    """Property tests for RoutingAction JSON serialization."""

    @given(reason=st.one_of(st.none(), reason_dicts))
    @settings(max_examples=100)
    def test_routing_action_continue_serializes_to_valid_json(
        self,
        reason: dict[str, Any] | None,
    ) -> None:
        """Property: RoutingAction.continue_() serializes to valid JSON."""
        action = RoutingAction.continue_(reason=reason)

        # Custom serialization needed for frozen dataclass with MappingProxyType
        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert isinstance(parsed, dict)
        assert parsed["kind"] == RoutingKind.CONTINUE.value

    @given(reason=st.one_of(st.none(), reason_dicts))
    @settings(max_examples=100)
    def test_routing_action_continue_json_round_trip_preserves_invariants(
        self,
        reason: dict[str, Any] | None,
    ) -> None:
        """Property: RoutingAction.continue_() JSON round-trip preserves invariants."""
        action = RoutingAction.continue_(reason=reason)

        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert parsed["kind"] == RoutingKind.CONTINUE.value
        assert parsed["destinations"] == []
        assert parsed["mode"] == RoutingMode.MOVE.value

    @given(label=path_names, reason=st.one_of(st.none(), reason_dicts))
    @settings(max_examples=100)
    def test_routing_action_route_json_round_trip_preserves_destination(
        self,
        label: str,
        reason: dict[str, Any] | None,
    ) -> None:
        """Property: RoutingAction.route() JSON round-trip preserves destination."""
        action = RoutingAction.route(label, reason=reason)

        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert parsed["kind"] == RoutingKind.ROUTE.value
        assert parsed["destinations"] == [label]
        assert parsed["mode"] == RoutingMode.MOVE.value

    @given(paths=unique_path_lists, reason=st.one_of(st.none(), reason_dicts))
    @settings(max_examples=100)
    def test_routing_action_fork_json_round_trip_preserves_paths(
        self,
        paths: list[str],
        reason: dict[str, Any] | None,
    ) -> None:
        """Property: RoutingAction.fork_to_paths() JSON round-trip preserves paths."""
        action = RoutingAction.fork_to_paths(paths, reason=reason)

        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert parsed["kind"] == RoutingKind.FORK_TO_PATHS.value
        assert parsed["destinations"] == paths
        assert parsed["mode"] == RoutingMode.COPY.value


class TestRoutingActionReasonSerializationProperties:
    """Property tests for RoutingAction reason field serialization."""

    @given(reason=reason_dicts)
    @settings(max_examples=100)
    def test_routing_action_reason_json_round_trip(
        self,
        reason: dict[str, Any],
    ) -> None:
        """Property: RoutingAction reason field JSON round-trips correctly."""
        action = RoutingAction.continue_(reason=reason)

        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert parsed["reason"] == reason

    def test_routing_action_empty_reason_serializes(self) -> None:
        """Property: Empty reason serializes to empty dict."""
        action = RoutingAction.continue_()

        serialized = json.dumps(_routing_action_to_dict(action))
        parsed = json.loads(serialized)

        assert parsed["reason"] == {}


# =============================================================================
# Helper Functions
# =============================================================================


def _routing_action_to_dict(action: RoutingAction) -> dict[str, Any]:
    """Convert RoutingAction to JSON-serializable dict.

    RoutingAction uses MappingProxyType for reason and tuple for destinations,
    which need conversion for standard JSON serialization.
    """
    return {
        "kind": action.kind.value,
        "destinations": list(action.destinations),
        "mode": action.mode.value,
        "reason": dict(action.reason),
    }
