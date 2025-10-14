"""Experiment orchestrator - DAG pattern for LLM experimentation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.plugins.orchestrators.experiment.runner import ExperimentRunner

__all__ = ["ExperimentRunner"]


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name == "ExperimentRunner":
        from elspeth.plugins.orchestrators.experiment.runner import ExperimentRunner

        return ExperimentRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
