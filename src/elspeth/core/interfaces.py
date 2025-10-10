"""Interfaces defining key plugin contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Any, Dict, Iterable, List, Mapping

import pandas as pd


@runtime_checkable
class DataSource(Protocol):
    """Loads experiment input data as a pandas DataFrame."""

    def load(self) -> pd.DataFrame:
        ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Normalized interface for LLM interactions."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        ...


@runtime_checkable
class ResultSink(Protocol):
    """Receives experiment results and persists them externally."""

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
        ...

    def produces(self) -> List["ArtifactDescriptor"]:  # pragma: no cover - optional
        return []

    def consumes(self) -> List[str]:  # pragma: no cover - optional
        return []

    def finalize(self, artifacts: Mapping[str, "Artifact"], *, metadata: Dict[str, Any] | None = None) -> None:  # pragma: no cover - optional
        return None

    def prepare_artifacts(self, artifacts: Mapping[str, List["Artifact"]]) -> None:  # pragma: no cover - optional
        return None

    def collect_artifacts(self) -> Dict[str, "Artifact"]:  # pragma: no cover - optional
        return {}


@dataclass
class ExperimentContext:
    """Data structure passed to orchestrator containing runtime info."""

    data: pd.DataFrame
    config: Dict[str, Any]


@dataclass
class ArtifactDescriptor:
    """Describes an artifact produced by a sink for dependency resolution."""

    name: str
    type: str
    schema_id: str | None = None
    persist: bool = False
    alias: str | None = None
    security_level: str | None = None


@dataclass
class Artifact:
    """Concrete artifact emitted by a sink during execution."""

    id: str
    type: str
    path: str | None = None
    payload: Any | None = None
    metadata: Dict[str, Any] = None  # type: ignore[assignment]
    schema_id: str | None = None
    produced_by: str | None = None
    persist: bool = False
    security_level: str | None = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "ResultSink",
    "ExperimentContext",
    "ArtifactDescriptor",
    "Artifact",
]
