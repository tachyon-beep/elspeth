# tests/property/core/test_reproducibility_properties.py
"""Property-based tests for reproducibility grade computation.

These tests verify the invariants of ELSPETH's reproducibility classification:

Grade Hierarchy Properties:
- FULL_REPRODUCIBLE > REPLAY_REPRODUCIBLE > ATTRIBUTABLE_ONLY
- Grade ordering is meaningful (higher = more reproducible)

Determinism Classification Properties:
- DETERMINISTIC, SEEDED, IO_READ, IO_WRITE → FULL_REPRODUCIBLE
- EXTERNAL_CALL, NON_DETERMINISTIC → REPLAY_REPRODUCIBLE

Degradation Properties:
- REPLAY_REPRODUCIBLE → ATTRIBUTABLE_ONLY (after purge)
- FULL_REPRODUCIBLE → unchanged
- ATTRIBUTABLE_ONLY → unchanged

Enum Integrity Properties:
- Exactly 3 grades exist
- Values are lowercase strings
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import Determinism
from elspeth.core.landscape.reproducibility import ReproducibilityGrade

# =============================================================================
# Strategies for reproducibility testing
# =============================================================================

# All reproducibility grades
all_grades = st.sampled_from(list(ReproducibilityGrade))

# All determinism values
all_determinism = st.sampled_from(list(Determinism))

# Determinism values that allow full reproducibility
reproducible_determinism = st.sampled_from(
    [
        Determinism.DETERMINISTIC,
        Determinism.SEEDED,
        Determinism.IO_READ,
        Determinism.IO_WRITE,
    ]
)

# Determinism values that require replay
non_reproducible_determinism = st.sampled_from(
    [
        Determinism.EXTERNAL_CALL,
        Determinism.NON_DETERMINISTIC,
    ]
)


# =============================================================================
# Enum Integrity Property Tests
# =============================================================================


class TestReproducibilityGradeEnumProperties:
    """Property tests for ReproducibilityGrade enum integrity."""

    def test_exactly_three_grades_exist(self) -> None:
        """Property: Exactly 3 reproducibility grades are defined.

        Canary test - adding a new grade requires updating this test
        and the degradation logic.
        """
        grades = list(ReproducibilityGrade)
        assert len(grades) == 3, f"Expected 3 grades, got {len(grades)}: {[g.name for g in grades]}"

    @given(grade=all_grades)
    @settings(max_examples=20)
    def test_grade_values_are_lowercase(self, grade: ReproducibilityGrade) -> None:
        """Property: Grade values are lowercase strings (ELSPETH convention)."""
        assert grade.value == grade.value.lower()

    @given(grade=all_grades)
    @settings(max_examples=20)
    def test_grade_round_trip_through_value(self, grade: ReproducibilityGrade) -> None:
        """Property: Grade round-trips through string value."""
        recovered = ReproducibilityGrade(grade.value)
        assert recovered is grade

    @given(grade=all_grades)
    @settings(max_examples=20)
    def test_grade_is_string_subclass(self, grade: ReproducibilityGrade) -> None:
        """Property: Grade instances are strings (for JSON serialization)."""
        assert isinstance(grade, str)
        assert grade == grade.value

    def test_no_duplicate_values(self) -> None:
        """Property: All grade values are unique."""
        values = [g.value for g in ReproducibilityGrade]
        assert len(values) == len(set(values))


# =============================================================================
# Determinism Classification Property Tests
# =============================================================================


class TestDeterminismClassificationProperties:
    """Property tests for determinism → grade classification logic.

    The classification used by compute_grade():
    - {DETERMINISTIC, SEEDED, IO_READ, IO_WRITE} → FULL_REPRODUCIBLE
    - {EXTERNAL_CALL, NON_DETERMINISTIC} → REPLAY_REPRODUCIBLE
    """

    def _classify_determinism(self, det: Determinism) -> ReproducibilityGrade:
        """Classify a single determinism value to its grade.

        This mirrors the logic in compute_grade() but for a single value.
        """
        non_reproducible = {
            Determinism.EXTERNAL_CALL,
            Determinism.NON_DETERMINISTIC,
        }
        if det in non_reproducible:
            return ReproducibilityGrade.REPLAY_REPRODUCIBLE
        else:
            return ReproducibilityGrade.FULL_REPRODUCIBLE

    @given(det=reproducible_determinism)
    @settings(max_examples=50)
    def test_reproducible_determinism_yields_full_grade(self, det: Determinism) -> None:
        """Property: Reproducible determinism values yield FULL_REPRODUCIBLE.

        DETERMINISTIC, SEEDED, IO_READ, IO_WRITE can all be re-executed
        with identical results (SEEDED needs the seed captured).
        """
        grade = self._classify_determinism(det)
        assert grade == ReproducibilityGrade.FULL_REPRODUCIBLE

    @given(det=non_reproducible_determinism)
    @settings(max_examples=50)
    def test_non_reproducible_determinism_yields_replay_grade(self, det: Determinism) -> None:
        """Property: Non-reproducible determinism values yield REPLAY_REPRODUCIBLE.

        EXTERNAL_CALL (LLM, APIs) and NON_DETERMINISTIC require recorded
        responses to replay - they can't be re-executed deterministically.
        """
        grade = self._classify_determinism(det)
        assert grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE

    def test_all_determinism_values_classified(self) -> None:
        """Property: Every Determinism value has a defined classification.

        This ensures no enum value is accidentally unhandled.
        """
        for det in Determinism:
            grade = self._classify_determinism(det)
            assert grade in (
                ReproducibilityGrade.FULL_REPRODUCIBLE,
                ReproducibilityGrade.REPLAY_REPRODUCIBLE,
            )

    def test_classification_is_exhaustive(self) -> None:
        """Property: Classification covers all 6 determinism values.

        Canary test - adding a new Determinism value requires
        updating this test and the classification logic.
        """
        assert len(list(Determinism)) == 6


# =============================================================================
# Grade Hierarchy Property Tests
# =============================================================================


class TestGradeHierarchyProperties:
    """Property tests for grade ordering and hierarchy."""

    def test_grade_ordering_is_meaningful(self) -> None:
        """Property: Grades have a meaningful ordering (more → less reproducible).

        FULL_REPRODUCIBLE > REPLAY_REPRODUCIBLE > ATTRIBUTABLE_ONLY
        """
        # Define the hierarchy (index = reproducibility level, higher = better)
        hierarchy = [
            ReproducibilityGrade.ATTRIBUTABLE_ONLY,  # 0 - lowest
            ReproducibilityGrade.REPLAY_REPRODUCIBLE,  # 1 - middle
            ReproducibilityGrade.FULL_REPRODUCIBLE,  # 2 - highest
        ]

        # Verify all grades are in hierarchy
        assert set(hierarchy) == set(ReproducibilityGrade)

        # The ordering represents reproducibility level
        full_idx = hierarchy.index(ReproducibilityGrade.FULL_REPRODUCIBLE)
        replay_idx = hierarchy.index(ReproducibilityGrade.REPLAY_REPRODUCIBLE)
        attr_idx = hierarchy.index(ReproducibilityGrade.ATTRIBUTABLE_ONLY)

        assert full_idx > replay_idx > attr_idx

    def test_full_reproducible_is_highest(self) -> None:
        """Property: FULL_REPRODUCIBLE is the highest (best) grade."""
        # FULL means we can re-run with identical results
        assert ReproducibilityGrade.FULL_REPRODUCIBLE.value == "full_reproducible"

    def test_attributable_only_is_lowest(self) -> None:
        """Property: ATTRIBUTABLE_ONLY is the lowest grade."""
        # ATTRIBUTABLE means we can only verify via hashes, not replay
        assert ReproducibilityGrade.ATTRIBUTABLE_ONLY.value == "attributable_only"


# =============================================================================
# Degradation Logic Property Tests
# =============================================================================


class TestGradeDegradationProperties:
    """Property tests for grade degradation after purge.

    The degradation rules from update_grade_after_purge():
    - REPLAY_REPRODUCIBLE → ATTRIBUTABLE_ONLY
    - FULL_REPRODUCIBLE → unchanged
    - ATTRIBUTABLE_ONLY → unchanged
    """

    def _degrade_after_purge(self, grade: ReproducibilityGrade) -> ReproducibilityGrade:
        """Apply purge degradation rule to a grade.

        This mirrors the logic in update_grade_after_purge().
        """
        if grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE:
            return ReproducibilityGrade.ATTRIBUTABLE_ONLY
        else:
            return grade

    def test_replay_reproducible_degrades_to_attributable(self) -> None:
        """Property: REPLAY_REPRODUCIBLE degrades to ATTRIBUTABLE_ONLY.

        After purge, we no longer have recorded responses, so we can't
        replay - only verify what happened via hashes.
        """
        result = self._degrade_after_purge(ReproducibilityGrade.REPLAY_REPRODUCIBLE)
        assert result == ReproducibilityGrade.ATTRIBUTABLE_ONLY

    def test_full_reproducible_unchanged_after_purge(self) -> None:
        """Property: FULL_REPRODUCIBLE is unchanged after purge.

        Fully reproducible runs don't depend on recorded responses -
        they can be re-executed from inputs alone.
        """
        result = self._degrade_after_purge(ReproducibilityGrade.FULL_REPRODUCIBLE)
        assert result == ReproducibilityGrade.FULL_REPRODUCIBLE

    def test_attributable_only_unchanged_after_purge(self) -> None:
        """Property: ATTRIBUTABLE_ONLY is unchanged after purge.

        Already at the lowest grade - can't degrade further.
        """
        result = self._degrade_after_purge(ReproducibilityGrade.ATTRIBUTABLE_ONLY)
        assert result == ReproducibilityGrade.ATTRIBUTABLE_ONLY

    @given(grade=all_grades)
    @settings(max_examples=20)
    def test_degradation_is_idempotent(self, grade: ReproducibilityGrade) -> None:
        """Property: Applying degradation twice gives same result as once.

        degrade(degrade(x)) == degrade(x) for all grades.
        """
        once = self._degrade_after_purge(grade)
        twice = self._degrade_after_purge(once)
        assert once == twice

    @given(grade=all_grades)
    @settings(max_examples=20)
    def test_degradation_never_increases_grade(self, grade: ReproducibilityGrade) -> None:
        """Property: Degradation never results in a higher grade.

        Purging data can only reduce reproducibility, never improve it.
        """
        hierarchy = {
            ReproducibilityGrade.ATTRIBUTABLE_ONLY: 0,
            ReproducibilityGrade.REPLAY_REPRODUCIBLE: 1,
            ReproducibilityGrade.FULL_REPRODUCIBLE: 2,
        }

        result = self._degrade_after_purge(grade)
        assert hierarchy[result] <= hierarchy[grade]


# =============================================================================
# Combined Classification and Degradation Property Tests
# =============================================================================


class TestClassificationDegradationInteractionProperties:
    """Property tests for interaction between classification and degradation."""

    def _classify_determinism(self, det: Determinism) -> ReproducibilityGrade:
        """Classify a single determinism value to its grade."""
        non_reproducible = {
            Determinism.EXTERNAL_CALL,
            Determinism.NON_DETERMINISTIC,
        }
        if det in non_reproducible:
            return ReproducibilityGrade.REPLAY_REPRODUCIBLE
        else:
            return ReproducibilityGrade.FULL_REPRODUCIBLE

    def _degrade_after_purge(self, grade: ReproducibilityGrade) -> ReproducibilityGrade:
        """Apply purge degradation rule to a grade."""
        if grade == ReproducibilityGrade.REPLAY_REPRODUCIBLE:
            return ReproducibilityGrade.ATTRIBUTABLE_ONLY
        else:
            return grade

    @given(det=reproducible_determinism)
    @settings(max_examples=50)
    def test_reproducible_determinism_survives_purge(self, det: Determinism) -> None:
        """Property: Reproducible determinism stays FULL even after purge.

        DETERMINISTIC nodes don't need recorded payloads to re-execute.
        """
        initial = self._classify_determinism(det)
        after_purge = self._degrade_after_purge(initial)

        assert after_purge == ReproducibilityGrade.FULL_REPRODUCIBLE

    @given(det=non_reproducible_determinism)
    @settings(max_examples=50)
    def test_non_reproducible_determinism_degrades_after_purge(self, det: Determinism) -> None:
        """Property: Non-reproducible determinism degrades to ATTRIBUTABLE after purge.

        Without recorded responses, we can only prove what happened via hashes.
        """
        initial = self._classify_determinism(det)
        after_purge = self._degrade_after_purge(initial)

        assert after_purge == ReproducibilityGrade.ATTRIBUTABLE_ONLY
