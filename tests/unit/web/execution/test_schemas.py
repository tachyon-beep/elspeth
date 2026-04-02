"""Tests for execution response models."""

from __future__ import annotations

from datetime import UTC, datetime

import pydantic
import pytest

from elspeth.web.execution.schemas import (
    RunEvent,
    ValidationCheck,
    ValidationError,
    ValidationResult,
)


class TestValidationResult:
    def test_invalid_result_with_attributed_error(self) -> None:
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(name="settings_load", passed=True, detail="OK"),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Graph validation failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id="gate_1",
                    component_type="gate",
                    message="Route destination 'nonexistent_sink' not found",
                    suggestion="Check sink names in gate configuration",
                ),
            ],
        )
        assert result.is_valid is False
        assert result.errors[0].component_id == "gate_1"
        assert result.errors[0].component_type == "gate"

    def test_structural_error_has_null_component(self) -> None:
        err = ValidationError(
            component_id=None,
            component_type=None,
            message="Graph contains a cycle",
            suggestion=None,
        )
        assert err.component_id is None
        assert err.component_type is None

    def test_skipped_check_recorded(self) -> None:
        """When settings_load fails, downstream checks are skipped but recorded."""
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=False,
                    detail="Invalid YAML syntax",
                ),
                ValidationCheck(
                    name="plugin_instantiation",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="schema_compatibility",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id=None,
                    component_type=None,
                    message="Invalid YAML syntax",
                    suggestion=None,
                ),
            ],
        )
        assert result.is_valid is False
        skipped = [c for c in result.checks if "Skipped" in c.detail]
        assert len(skipped) == 3


class TestRunEvent:
    def test_invalid_event_type_rejected(self) -> None:
        """event_type is a Literal — Pydantic rejects unknown values."""
        with pytest.raises(pydantic.ValidationError):
            RunEvent(
                run_id="run-123",
                timestamp=datetime.now(tz=UTC),
                event_type="unknown",
                data={},
            )
