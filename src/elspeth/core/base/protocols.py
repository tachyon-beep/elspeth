"""Universal plugin protocols for Elspeth.

This module consolidates all universal protocols that define plugin contracts
across the entire system. Protocols are organized by responsibility:

- **Orchestrators**: Define data flow topology
- **Nodes**: Processing vertices (sources, sinks, transforms, aggregators)
- **LLM Components**: Transform-specific protocols for LLM operations
- **Supporting Types**: Data structures used across protocols

Experiment-specific protocols live in `plugins/orchestrators/experiment/protocols.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import pandas as pd

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema
    from elspeth.core.base.types import DeterminismLevel, SecurityLevel


# ============================================================================
# Orchestrator Protocols
# ============================================================================


@runtime_checkable
class OrchestratorPlugin(Protocol):
    """Define the topology of data flow through processing nodes.

    Orchestrators are 'engines' that define HOW data flows through the system,
    while nodes (sources, sinks, transforms) define WHAT happens at each vertex.

    Example: ExperimentOrchestrator defines a DAG pattern where data flows from
    a source through LLM transforms and experiment plugins to multiple sinks.
    """

    def run(self, context: ExperimentContext) -> dict[str, Any]:
        """Execute the orchestrated data flow.

        Args:
            context: Contains data, configuration, and runtime info

        Returns:
            Results dictionary containing outputs and metadata
        """
        raise NotImplementedError


# ============================================================================
# Node Protocols (Universal)
# ============================================================================


@runtime_checkable
class DataSource(Protocol):
    """Source node: where data comes from."""

    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""
        raise NotImplementedError

    def output_schema(self) -> type[DataFrameSchema] | None:  # pragma: no cover - optional
        """Return the schema of the DataFrame this datasource produces.

        If implemented, enables config-time validation of schema compatibility
        between datasources and plugins.

        Returns:
            DataFrameSchema subclass describing output columns, or None if unknown
        """
        return None


@runtime_checkable
class ResultSink(Protocol):  # pylint: disable=too-few-public-methods
    """Sink node: where results go."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Persist experiment results."""
        raise NotImplementedError

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - optional
        """Describe artifacts the sink emits, enabling chaining."""
        return []

    def consumes(self) -> list[str]:  # pragma: no cover - optional
        """Return artifact names the sink depends on."""
        return []

    def finalize(self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None) -> None:  # pragma: no cover - optional
        """Perform cleanup or post-processing once artifacts are available."""
        return None

    def prepare_artifacts(self, artifacts: Mapping[str, list[Artifact]]) -> None:  # pragma: no cover - optional
        """Allow the sink to modify artifacts before finalization."""
        return None

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover - optional
        """Expose artifacts generated during `write` for downstream consumers."""
        return {}


@runtime_checkable
class TransformNode(Protocol):
    """Transform node: process data at a vertex."""

    name: str

    def transform(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Apply transformation to data."""
        raise NotImplementedError


@runtime_checkable
class AggregatorNode(Protocol):
    """Aggregator node: compute multi-row aggregates."""

    name: str

    def aggregate(self, records: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Compute aggregate from multiple records."""
        raise NotImplementedError


# ============================================================================
# LLM Transform Protocols (Specific to LLM transforms)
# ============================================================================


@runtime_checkable
class LLMClientProtocol(Protocol):  # pylint: disable=too-few-public-methods
    """LLM client for LLM transform nodes."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the model and return a response payload."""
        raise NotImplementedError


@dataclass
class LLMRequest:
    """Request payload for LLM middleware processing."""

    system_prompt: str
    user_prompt: str
    metadata: dict[str, Any]

    def clone(
        self,
        *,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMRequest:
        """Create a modified copy of the request."""
        return replace(
            self,
            system_prompt=system_prompt if system_prompt is not None else self.system_prompt,
            user_prompt=user_prompt if user_prompt is not None else self.user_prompt,
            metadata=metadata if metadata is not None else dict(self.metadata),
        )


class LLMMiddleware(Protocol):
    """Middleware for LLM transform nodes."""

    name: str

    def before_request(self, request: LLMRequest) -> LLMRequest:
        """Process request before LLM call."""
        return request

    def after_response(self, request: LLMRequest, response: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - optional
        """Process response after LLM call."""
        return response


class RateLimiter:
    """Rate limiting for LLM transforms (base class, not protocol)."""

    def acquire(self, metadata: dict[str, object | None] | None = None) -> AbstractContextManager[None]:
        """Return a context manager that enforces the rate limit."""
        del metadata  # Unused in base implementation.
        raise NotImplementedError

    def utilization(self) -> float:  # pragma: no cover - default no usage
        """Return a utilization ratio in the range [0, 1]."""
        return 0.0

    def update_usage(
        self, response: dict[str, Any], metadata: dict[str, object | None] | None = None
    ) -> None:  # pragma: no cover - optional override
        """Record response metadata to refine future rate limiting."""
        del response, metadata  # Unused in base implementation.


class CostTracker:
    """Cost tracking for LLM transforms (base class, not protocol)."""

    def record(self, response: dict[str, Any], metadata: dict[str, object | None] | None = None) -> dict[str, Any]:
        """Record billing information for a single response."""
        raise NotImplementedError

    def summary(self) -> dict[str, Any]:
        """Return aggregate totals accumulated so far."""
        raise NotImplementedError


# ============================================================================
# Supporting Data Types
# ============================================================================


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
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None


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
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None


__all__ = [
    # Orchestrator protocols
    "OrchestratorPlugin",
    # Node protocols
    "DataSource",
    "ResultSink",
    "TransformNode",
    "AggregatorNode",
    # LLM transform protocols
    "LLMClientProtocol",
    "LLMMiddleware",
    "LLMRequest",
    "RateLimiter",
    "CostTracker",
    # Supporting types
    "ExperimentContext",
    "ArtifactDescriptor",
    "Artifact",
]
