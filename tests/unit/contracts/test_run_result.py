"""Tests for RunResult — pipeline execution outcome contract.

Validates __post_init__ guards: empty run_id rejection, require_int on all
numeric fields (negative rejection, bool rejection, float rejection),
and freeze_fields on routed_destinations.
"""

from types import MappingProxyType

import pytest

from elspeth.contracts.enums import RunStatus
from elspeth.contracts.run_result import RunResult
from tests.fixtures.factories import make_run_result


class TestRunResultValidation:
    """__post_init__ guards on RunResult."""

    def test_empty_run_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="run_id must not be empty"):
            RunResult(
                run_id="",
                status=RunStatus.COMPLETED,
                rows_processed=0,
                rows_succeeded=0,
                rows_failed=0,
                rows_routed=0,
            )

    @pytest.mark.parametrize(
        "field",
        [
            "rows_processed",
            "rows_succeeded",
            "rows_failed",
            "rows_routed",
            "rows_quarantined",
            "rows_forked",
            "rows_coalesced",
            "rows_coalesce_failed",
            "rows_expanded",
            "rows_buffered",
            "rows_diverted",
        ],
    )
    def test_negative_value_rejected(self, field: str) -> None:
        """Every numeric field must be >= 0."""
        kwargs = {
            "run_id": "run-1",
            "status": RunStatus.COMPLETED,
            "rows_processed": 0,
            "rows_succeeded": 0,
            "rows_failed": 0,
            "rows_routed": 0,
            field: -1,
        }
        with pytest.raises(ValueError, match=field):
            RunResult(**kwargs)

    @pytest.mark.parametrize(
        "field",
        [
            "rows_processed",
            "rows_succeeded",
            "rows_failed",
            "rows_routed",
            "rows_quarantined",
            "rows_forked",
            "rows_coalesced",
            "rows_coalesce_failed",
            "rows_expanded",
            "rows_buffered",
            "rows_diverted",
        ],
    )
    def test_bool_rejected(self, field: str) -> None:
        """Bool must not be accepted as int (Python subclass trap)."""
        kwargs = {
            "run_id": "run-1",
            "status": RunStatus.COMPLETED,
            "rows_processed": 0,
            "rows_succeeded": 0,
            "rows_failed": 0,
            "rows_routed": 0,
            field: True,
        }
        with pytest.raises(TypeError):
            RunResult(**kwargs)

    @pytest.mark.parametrize(
        "field",
        [
            "rows_processed",
            "rows_succeeded",
            "rows_failed",
            "rows_routed",
        ],
    )
    def test_float_rejected(self, field: str) -> None:
        """Float must not be silently accepted for int fields."""
        kwargs = {
            "run_id": "run-1",
            "status": RunStatus.COMPLETED,
            "rows_processed": 0,
            "rows_succeeded": 0,
            "rows_failed": 0,
            "rows_routed": 0,
            field: 1.5,
        }
        with pytest.raises(TypeError):
            RunResult(**kwargs)


class TestRunResultImmutability:
    """Frozen dataclass + freeze_fields on routed_destinations."""

    def test_routed_destinations_frozen(self) -> None:
        """Dict passed to routed_destinations must be deep-frozen."""
        result = make_run_result(routed_destinations={"sink_a": 5, "sink_b": 3})
        assert isinstance(result.routed_destinations, MappingProxyType)

    def test_routed_destinations_default_is_empty_frozen(self) -> None:
        """Default routed_destinations must be an empty frozen mapping."""
        result = make_run_result()
        assert isinstance(result.routed_destinations, MappingProxyType)
        assert len(result.routed_destinations) == 0

    def test_routed_destinations_mutation_blocked(self) -> None:
        """Callers must not be able to mutate routed_destinations after creation."""
        result = make_run_result(routed_destinations={"sink_a": 5})
        with pytest.raises(TypeError):
            result.routed_destinations["sink_b"] = 10  # type: ignore[index]


class TestRunResultFactory:
    """Tests for the make_run_result factory (ensures factory is usable)."""

    def test_factory_defaults_produce_valid_result(self) -> None:
        result = make_run_result()
        assert result.status == RunStatus.COMPLETED
        assert result.rows_processed == 10

    def test_factory_accepts_all_overrides(self) -> None:
        result = make_run_result(
            run_id="custom-run",
            status=RunStatus.FAILED,
            rows_processed=100,
            rows_succeeded=90,
            rows_failed=10,
            rows_routed=5,
            rows_quarantined=2,
            rows_forked=3,
            rows_coalesced=1,
            rows_coalesce_failed=1,
            rows_expanded=4,
            rows_buffered=2,
            routed_destinations={"x": 5},
        )
        assert result.run_id == "custom-run"
        assert result.status == RunStatus.FAILED
        assert result.rows_failed == 10
        assert result.routed_destinations["x"] == 5
