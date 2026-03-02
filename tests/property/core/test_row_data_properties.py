# tests/property/core/test_row_data_properties.py
"""Property-based tests for row data retrieval contracts.

These tests verify the invariants of RowDataResult - ELSPETH's
discriminated union for audit data retrieval:

State-Data Invariants:
- AVAILABLE and REPR_FALLBACK states require dict data
- All other states require None data
- No other state-data combinations are valid

Immutability Invariants:
- Frozen dataclass cannot be mutated after construction

Enum Integrity:
- All RowDataState values are handled consistently

These invariants are critical for Tier 1 audit data - callers can
pattern match on state without null-checking ambiguity.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.core.landscape.row_data import RowDataResult, RowDataState

# =============================================================================
# Strategies for generating row data
# =============================================================================

# States that carry data (require non-None dict)
data_carrying_states = st.sampled_from(
    [
        RowDataState.AVAILABLE,
        RowDataState.REPR_FALLBACK,
    ]
)

# States that require None data
non_data_states = st.sampled_from(
    [
        RowDataState.PURGED,
        RowDataState.NEVER_STORED,
        RowDataState.STORE_NOT_CONFIGURED,
        RowDataState.ROW_NOT_FOUND,
    ]
)

# All states
all_states = st.sampled_from(list(RowDataState))

# Row data dictionaries (for AVAILABLE state)
row_data_dicts = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    values=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=100),
    ),
    min_size=0,
    max_size=10,
)

# Non-dict payloads that are invalid for AVAILABLE state
non_dict_data = st.one_of(
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=100),
    st.lists(st.integers(), max_size=10),
)


# =============================================================================
# State-Data Invariant Property Tests
# =============================================================================


class TestRowDataInvariantProperties:
    """Property tests for state-data invariants."""

    @given(data=row_data_dicts)
    @settings(max_examples=100)
    def test_available_with_data_succeeds(self, data: dict[str, Any]) -> None:
        """Property: AVAILABLE state with non-None data constructs successfully."""
        result = RowDataResult(state=RowDataState.AVAILABLE, data=data)

        assert result.state == RowDataState.AVAILABLE
        assert result.data == data

    @given(state=data_carrying_states)
    @settings(max_examples=10)
    def test_data_carrying_with_none_fails(self, state: RowDataState) -> None:
        """Property: Data-carrying states with None data raise ValueError."""
        with pytest.raises(ValueError, match=f"{state.value} state requires non-None data"):
            RowDataResult(state=state, data=None)

    @given(state=data_carrying_states, data=non_dict_data)
    @settings(max_examples=100)
    def test_data_carrying_with_non_dict_fails(self, state: RowDataState, data: Any) -> None:
        """Property: Data-carrying states with non-dict data raise TypeError."""
        with pytest.raises(TypeError, match=f"{state.value} state requires dict data"):
            RowDataResult(state=state, data=data)

    @given(state=non_data_states)
    @settings(max_examples=50)
    def test_non_data_with_none_succeeds(self, state: RowDataState) -> None:
        """Property: Non-data states with None data construct successfully."""
        result = RowDataResult(state=state, data=None)

        assert result.state == state
        assert result.data is None

    @given(state=non_data_states, data=row_data_dicts)
    @settings(max_examples=100)
    def test_non_data_with_data_fails(self, state: RowDataState, data: dict[str, Any]) -> None:
        """Property: Non-data states with non-None data raise ValueError."""
        with pytest.raises(ValueError, match="requires None data"):
            RowDataResult(state=state, data=data)

    @given(state=all_states, data=st.one_of(st.none(), row_data_dicts))
    @settings(max_examples=200)
    def test_invariant_holds_for_all_combinations(self, state: RowDataState, data: dict[str, Any] | None) -> None:
        """Property: Only valid state-data combinations construct successfully.

        Valid combinations:
        - Data-carrying states (AVAILABLE, REPR_FALLBACK) + non-None data
        - Non-data states + None data

        All other combinations raise ValueError.
        """
        is_data_state = state in (RowDataState.AVAILABLE, RowDataState.REPR_FALLBACK)
        should_succeed = (is_data_state and data is not None) or (not is_data_state and data is None)

        if should_succeed:
            result = RowDataResult(state=state, data=data)
            assert result.state == state
            assert result.data == data
        else:
            with pytest.raises((ValueError, TypeError)):
                RowDataResult(state=state, data=data)


# =============================================================================
# Immutability Property Tests
# =============================================================================


class TestRowDataImmutabilityProperties:
    """Property tests for frozen dataclass behavior."""

    @given(data=row_data_dicts)
    @settings(max_examples=50)
    def test_available_result_is_immutable(self, data: dict[str, Any]) -> None:
        """Property: Cannot modify state or data after construction."""
        result = RowDataResult(state=RowDataState.AVAILABLE, data=data)

        with pytest.raises(AttributeError):
            result.state = RowDataState.PURGED  # type: ignore[misc]

        with pytest.raises(AttributeError):
            result.data = None  # type: ignore[misc]

    @given(state=non_data_states)
    @settings(max_examples=50)
    def test_non_data_result_is_immutable(self, state: RowDataState) -> None:
        """Property: Non-data results are also immutable."""
        result = RowDataResult(state=state, data=None)

        with pytest.raises(AttributeError):
            result.state = RowDataState.AVAILABLE  # type: ignore[misc]

        with pytest.raises(AttributeError):
            result.data = {"new": "data"}  # type: ignore[misc]


# =============================================================================
# Enum Integrity Property Tests
# =============================================================================


class TestRowDataStateEnumProperties:
    """Property tests for RowDataState enum."""

    @given(state=all_states)
    @settings(max_examples=50)
    def test_state_round_trip_through_value(self, state: RowDataState) -> None:
        """Property: RowDataState round-trips through string value."""
        recovered = RowDataState(state.value)
        assert recovered is state

    @given(state=all_states)
    @settings(max_examples=50)
    def test_state_value_is_lowercase(self, state: RowDataState) -> None:
        """Property: State values are lowercase (ELSPETH convention)."""
        assert state.value == state.value.lower()

    def test_exactly_six_states_exist(self) -> None:
        """Property: Exactly 6 states are defined.

        Canary test - adding a new state should update this test.
        """
        states = list(RowDataState)
        assert len(states) == 6, f"Expected 6 states, got {len(states)}: {[s.name for s in states]}"

    def test_data_carrying_states(self) -> None:
        """Property: AVAILABLE and REPR_FALLBACK carry data; all others require None.

        This is documented behavior - if we add another data-carrying state,
        this test and the invariant validation need updating.
        """
        data_states = {RowDataState.AVAILABLE, RowDataState.REPR_FALLBACK}
        for state in RowDataState:
            if state in data_states:
                # Data-carrying states require data
                with pytest.raises(ValueError):
                    RowDataResult(state=state, data=None)
            else:
                # All others require None
                with pytest.raises(ValueError):
                    RowDataResult(state=state, data={"any": "data"})


# =============================================================================
# Factory Pattern Property Tests
# =============================================================================


class TestRowDataResultCreationProperties:
    """Property tests for result creation patterns."""

    @given(data=row_data_dicts)
    @settings(max_examples=50)
    def test_available_result_creation_deterministic(self, data: dict[str, Any]) -> None:
        """Property: Creating same AVAILABLE result twice gives equal results."""
        result1 = RowDataResult(state=RowDataState.AVAILABLE, data=data)
        result2 = RowDataResult(state=RowDataState.AVAILABLE, data=data)

        assert result1 == result2

    @given(state=non_data_states)
    @settings(max_examples=50)
    def test_non_data_result_creation_deterministic(self, state: RowDataState) -> None:
        """Property: Creating same non-data result twice gives equal results."""
        result1 = RowDataResult(state=state, data=None)
        result2 = RowDataResult(state=state, data=None)

        assert result1 == result2

    @given(state1=all_states, state2=all_states)
    @settings(max_examples=50)
    def test_different_states_not_equal(self, state1: RowDataState, state2: RowDataState) -> None:
        """Property: Results with different states are not equal."""
        if state1 == state2:
            return  # Skip same-state comparison

        data_states = {RowDataState.AVAILABLE, RowDataState.REPR_FALLBACK}
        # Create valid results for each state
        data1 = {"test": "data"} if state1 in data_states else None
        data2 = {"test": "data"} if state2 in data_states else None

        result1 = RowDataResult(state=state1, data=data1)
        result2 = RowDataResult(state=state2, data=data2)

        assert result1 != result2


# =============================================================================
# Error Message Property Tests
# =============================================================================


class TestRowDataErrorMessageProperties:
    """Property tests for error message quality."""

    def test_available_none_error_is_clear(self) -> None:
        """Property: AVAILABLE + None error message is descriptive."""
        with pytest.raises(ValueError) as exc_info:
            RowDataResult(state=RowDataState.AVAILABLE, data=None)

        error_msg = str(exc_info.value)
        assert "available" in error_msg
        assert "non-None" in error_msg or "requires" in error_msg

    @given(state=non_data_states)
    @settings(max_examples=20)
    def test_non_data_error_includes_state(self, state: RowDataState) -> None:
        """Property: Non-data state + data error message includes state name."""
        with pytest.raises(ValueError) as exc_info:
            RowDataResult(state=state, data={"some": "data"})

        error_msg = str(exc_info.value)
        # Error should mention the specific state
        assert state.name in error_msg or state.value in error_msg
