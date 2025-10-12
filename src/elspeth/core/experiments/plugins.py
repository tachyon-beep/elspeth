"""Experiment plugin interfaces."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ValidationError(RuntimeError):
    """Raised when a validation plugin rejects an LLM response."""


class ValidationPlugin(Protocol):
    """Evaluates LLM responses and raises ``ValidationError`` on failure."""

    name: str

    def validate(
        self,
        response: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Inspect a response and raise ``ValidationError`` when criteria fail."""


class RowExperimentPlugin(Protocol):
    """Processes a single experiment row and returns derived fields."""

    name: str

    def process_row(self, row: Dict[str, Any], responses: Dict[str, Any]) -> Dict[str, Any]:
        """Return derived metrics or annotations for a single row result."""


class AggregationExperimentPlugin(Protocol):
    """Runs after all rows to compute aggregated outputs."""

    name: str

    def finalize(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce aggregate analytics from the collected row results."""


class BaselineComparisonPlugin(Protocol):
    """Compares variant payloads against baseline payload."""

    name: str

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        """Compute a comparison between baseline and variant payloads."""


class EarlyStopPlugin(Protocol):
    """Observes row-level results and signals when processing should halt."""

    name: str

    def reset(self) -> None:
        """Reset any internal early-stop state."""

    def check(self, record: Dict[str, Any], *, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Return a reason to trigger early stop, or ``None`` to continue."""
