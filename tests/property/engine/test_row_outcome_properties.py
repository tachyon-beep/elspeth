# tests/property/engine/test_row_outcome_properties.py
"""Property-based tests for RowOutcome enum invariants.

These tests verify the fundamental properties of ELSPETH's token outcome
classification system:

Terminal State Properties:
- BUFFERED is the only non-terminal outcome
- All other outcomes represent final states
- is_terminal property is consistent

Enum Integrity Properties:
- Enum round-trip through name and value
- String serialization for database storage
- No duplicate values

These invariants are critical for the audit trail - incorrect outcome
classification would break lineage queries and compliance reporting.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import RowOutcome

# =============================================================================
# Strategies for RowOutcome
# =============================================================================

# All possible RowOutcome values
all_outcomes = st.sampled_from(list(RowOutcome))

# Terminal outcomes only (excluding BUFFERED)
terminal_outcomes = st.sampled_from([o for o in RowOutcome if o != RowOutcome.BUFFERED])


# =============================================================================
# Terminal State Invariant Tests
# =============================================================================


class TestRowOutcomeTerminalProperties:
    """Property tests for terminal/non-terminal classification."""

    @given(outcome=terminal_outcomes)
    @settings(max_examples=50)
    def test_all_non_buffered_outcomes_are_terminal(self, outcome: RowOutcome) -> None:
        """Property: Every outcome except BUFFERED is terminal.

        This is the fundamental invariant of the outcome system. Terminal
        outcomes mean the token's journey is complete - it won't appear
        again in the pipeline. BUFFERED is special: tokens can be buffered
        temporarily and then receive a final outcome later.
        """
        assert outcome.is_terminal is True, f"{outcome.name} should be terminal but is_terminal={outcome.is_terminal}"

    def test_buffered_is_non_terminal(self) -> None:
        """Property: BUFFERED is the only non-terminal outcome.

        BUFFERED tokens are held for batch processing in passthrough mode
        and will eventually receive a terminal outcome when the batch fires.
        """
        assert RowOutcome.BUFFERED.is_terminal is False

    def test_terminal_count_matches_expected(self) -> None:
        """Property: Exactly 8 terminal outcomes exist.

        If this test fails after adding a new outcome, you need to decide:
        1. Is it terminal? Add to the terminal list and update count.
        2. Is it non-terminal? Update is_terminal property implementation.

        This is a canary test - it catches accidental changes to the enum.
        """
        terminal_outcomes_list = [o for o in RowOutcome if o.is_terminal]
        non_terminal_outcomes = [o for o in RowOutcome if not o.is_terminal]

        # 8 terminal: COMPLETED, ROUTED, FORKED, FAILED, QUARANTINED,
        #             CONSUMED_IN_BATCH, COALESCED, EXPANDED
        assert len(terminal_outcomes_list) == 8, (
            f"Expected 8 terminal outcomes, got {len(terminal_outcomes_list)}: {[o.name for o in terminal_outcomes_list]}"
        )

        # 1 non-terminal: BUFFERED
        assert len(non_terminal_outcomes) == 1, (
            f"Expected 1 non-terminal outcome, got {len(non_terminal_outcomes)}: {[o.name for o in non_terminal_outcomes]}"
        )
        assert non_terminal_outcomes[0] == RowOutcome.BUFFERED


# =============================================================================
# Enum Integrity Property Tests
# =============================================================================


class TestRowOutcomeEnumIntegrity:
    """Property tests for enum serialization and integrity."""

    @given(outcome=all_outcomes)
    @settings(max_examples=50)
    def test_name_to_value_round_trip(self, outcome: RowOutcome) -> None:
        """Property: RowOutcome[name].value == original.value for all outcomes.

        This verifies that looking up by name returns the same enum member,
        which is critical for deserialization paths that use names.
        """
        # Round-trip through name
        recovered = RowOutcome[outcome.name]
        assert recovered.value == outcome.value
        assert recovered is outcome  # Same object (enum identity)

    @given(outcome=all_outcomes)
    @settings(max_examples=50)
    def test_value_to_enum_round_trip(self, outcome: RowOutcome) -> None:
        """Property: RowOutcome(value).name == original.name for all outcomes.

        This verifies that looking up by value returns the same enum member,
        which is critical for database deserialization that stores values.
        """
        # Round-trip through value
        recovered = RowOutcome(outcome.value)
        assert recovered.name == outcome.name
        assert recovered is outcome  # Same object (enum identity)

    @given(outcome=all_outcomes)
    @settings(max_examples=50)
    def test_value_is_lowercase_name(self, outcome: RowOutcome) -> None:
        """Property: For (str, Enum), value equals lowercase name.

        ELSPETH convention: enum values are lowercase versions of names.
        This enables predictable database serialization and human-readable
        audit trail entries.
        """
        assert outcome.value == outcome.name.lower(), f"{outcome.name}.value = '{outcome.value}', expected '{outcome.name.lower()}'"

    @given(outcome=all_outcomes)
    @settings(max_examples=50)
    def test_enum_is_string_subclass(self, outcome: RowOutcome) -> None:
        """Property: RowOutcome instances ARE strings for (str, Enum).

        Since RowOutcome inherits from (str, Enum), the enum member IS a
        string and can be compared directly to string values. This enables
        direct use in database queries and comparisons without .value access.

        Note: str(outcome) returns 'RowOutcome.NAME' (debug repr), but the
        enum itself IS the string value when used in comparisons.
        """
        # The enum IS a string (subclass of str)
        assert isinstance(outcome, str)
        # Can compare directly to string value
        assert outcome == outcome.value
        # Works in string contexts that don't call str()
        assert f"{outcome.value}" == outcome.value

    def test_no_duplicate_values(self) -> None:
        """Property: All RowOutcome values are unique.

        Duplicate values would cause ambiguous deserialization and break
        the audit trail's ability to uniquely identify token states.
        """
        values = [o.value for o in RowOutcome]
        assert len(values) == len(set(values)), f"Duplicate values found in RowOutcome: {values}"

    def test_no_duplicate_names(self) -> None:
        """Property: All RowOutcome names are unique.

        This is enforced by Python's enum, but we test explicitly
        to document the requirement.
        """
        names = [o.name for o in RowOutcome]
        assert len(names) == len(set(names)), f"Duplicate names found in RowOutcome: {names}"


# =============================================================================
# Semantic Invariant Tests
# =============================================================================


class TestRowOutcomeSemanticProperties:
    """Property tests for semantic correctness of outcome classification."""

    def test_sink_related_outcomes_are_terminal(self) -> None:
        """Property: Outcomes that represent reaching a sink are terminal.

        COMPLETED and ROUTED both mean the token reached a destination sink.
        These MUST be terminal - the token's data has been emitted.
        """
        assert RowOutcome.COMPLETED.is_terminal
        assert RowOutcome.ROUTED.is_terminal

    def test_error_outcomes_are_terminal(self) -> None:
        """Property: Error-related outcomes are terminal.

        FAILED and QUARANTINED both represent unrecoverable states.
        The token won't be processed further - it's recorded and done.
        """
        assert RowOutcome.FAILED.is_terminal
        assert RowOutcome.QUARANTINED.is_terminal

    def test_fork_join_outcomes_are_terminal_for_parent(self) -> None:
        """Property: Fork/join outcomes mark parent token as terminal.

        FORKED: Parent token splits into children - parent is done
        COALESCED: Multiple tokens merge into one - sources are done
        EXPANDED: Aggregated batch deaggregates - batch token is done
        CONSUMED_IN_BATCH: Token absorbed into aggregate - token is done
        """
        assert RowOutcome.FORKED.is_terminal
        assert RowOutcome.COALESCED.is_terminal
        assert RowOutcome.EXPANDED.is_terminal
        assert RowOutcome.CONSUMED_IN_BATCH.is_terminal

    @given(outcome=all_outcomes)
    @settings(max_examples=50)
    def test_is_terminal_is_boolean(self, outcome: RowOutcome) -> None:
        """Property: is_terminal always returns a boolean, never None.

        This ensures consistent behavior in boolean contexts and prevents
        subtle bugs from None propagation.
        """
        result = outcome.is_terminal
        assert isinstance(result, bool), f"{outcome.name}.is_terminal returned {type(result)}, expected bool"
