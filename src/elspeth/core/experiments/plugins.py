"""Experiment plugin interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from elspeth.core.schema import DataFrameSchema


class ValidationError(RuntimeError):
    """Raised when a validation plugin rejects an LLM response."""


class ValidationPlugin(Protocol):
    """Evaluates LLM responses and raises ``ValidationError`` on failure."""

    name: str

    def validate(
        self,
        response: dict[str, Any],
        *,
        context: dict[str, Any | None] | None = None,
        metadata: dict[str, Any | None] | None = None,
    ) -> None:
        """Inspect a response and raise ``ValidationError`` when criteria fail."""

    def input_schema(self) -> type["DataFrameSchema"] | None:  # pragma: no cover - optional
        """
        Return the schema of input columns this plugin requires.

        For validation plugins, this describes any DataFrame columns needed
        for validation context (if applicable).

        Returns:
            DataFrameSchema subclass describing required input columns, or None
        """
        return None


class RowExperimentPlugin(Protocol):
    """Processes a single experiment row and returns derived fields."""

    name: str

    def process_row(self, row: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]:
        """Return derived metrics or annotations for a single row result."""

    def input_schema(self) -> type["DataFrameSchema"] | None:  # pragma: no cover - optional
        """
        Return the schema of input columns this plugin requires.

        If implemented, enables config-time validation that datasource provides
        the columns this plugin expects.

        Returns:
            DataFrameSchema subclass describing required input columns, or None
        """
        return None


class AggregationExperimentPlugin(Protocol):
    """Runs after all rows to compute aggregated outputs."""

    name: str

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Produce aggregate analytics from the collected row results."""

    def input_schema(self) -> type["DataFrameSchema"] | None:  # pragma: no cover - optional
        """
        Return the schema of input columns this plugin requires.

        For aggregation plugins, this describes the columns needed from
        the original DataFrame or from row plugin outputs.

        Returns:
            DataFrameSchema subclass describing required input columns, or None
        """
        return None


class BaselineComparisonPlugin(Protocol):
    """Compares variant payloads against baseline payload."""

    name: str

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        """Compute a comparison between baseline and variant payloads."""


class EarlyStopPlugin(Protocol):
    """Observes row-level results and signals when processing should halt."""

    name: str

    def reset(self) -> None:
        """Reset any internal early-stop state."""

    def check(self, record: dict[str, Any], *, metadata: dict[str, Any | None] | None = None) -> dict[str, Any | None] | None:
        """Return a reason to trigger early stop, or ``None`` to continue."""
