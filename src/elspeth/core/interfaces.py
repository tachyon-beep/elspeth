"""Interfaces defining key plugin contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

import pandas as pd

if TYPE_CHECKING:
    from elspeth.core.schema import DataFrameSchema


@runtime_checkable
class DataSource(Protocol):
    """Loads experiment input data as a pandas DataFrame."""

    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""

        raise NotImplementedError

    def output_schema(self) -> type["DataFrameSchema"] | None:  # pragma: no cover - optional
        """
        Return the schema of the DataFrame this datasource produces.

        If implemented, enables config-time validation of schema compatibility
        between datasources and plugins.

        Returns:
            DataFrameSchema subclass describing output columns, or None if unknown
        """
        return None


@runtime_checkable
class LLMClientProtocol(Protocol):  # pylint: disable=too-few-public-methods
    """Normalized interface for LLM interactions."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the model and return a response payload."""

        raise NotImplementedError


@runtime_checkable
class ResultSink(Protocol):  # pylint: disable=too-few-public-methods
    """Receives experiment results and persists them externally."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Persist experiment results."""

        raise NotImplementedError

    def produces(self) -> list["ArtifactDescriptor"]:  # pragma: no cover - optional
        """Describe artifacts the sink emits, enabling chaining."""

        return []

    def consumes(self) -> list[str]:  # pragma: no cover - optional
        """Return artifact names the sink depends on."""

        return []

    def finalize(
        self, artifacts: Mapping[str, "Artifact"], *, metadata: dict[str, Any] | None = None
    ) -> None:  # pragma: no cover - optional
        """Perform cleanup or post-processing once artifacts are available."""

        return None

    def prepare_artifacts(self, artifacts: Mapping[str, list["Artifact"]]) -> None:  # pragma: no cover - optional
        """Allow the sink to modify artifacts before finalization."""

        return None

    def collect_artifacts(self) -> dict[str, "Artifact"]:  # pragma: no cover - optional
        """Expose artifacts generated during `write` for downstream consumers."""

        return {}


@dataclass
class ExperimentContext:
    """Data structure passed to orchestrator containing runtime info."""

    data: pd.DataFrame
    config: dict[str, Any]


@dataclass
class ArtifactDescriptor:  # pylint: disable=too-many-instance-attributes
    """Describes an artifact produced by a sink for dependency resolution."""

    name: str
    type: str
    schema_id: str | None = None
    persist: bool = False
    alias: str | None = None
    security_level: str | None = None
    determinism_level: str | None = None


@dataclass
class Artifact:  # pylint: disable=too-many-instance-attributes
    """Concrete artifact emitted by a sink during execution."""

    id: str
    type: str
    path: str | None = None
    payload: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_id: str | None = None
    produced_by: str | None = None
    persist: bool = False
    security_level: str | None = None
    determinism_level: str | None = None


__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "ResultSink",
    "ExperimentContext",
    "ArtifactDescriptor",
    "Artifact",
]
