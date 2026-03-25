"""Configuration models for pipeline dependencies and commencement gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from elspeth.contracts.freeze import deep_freeze, deep_thaw, freeze_fields


class DependencyConfig(BaseModel):
    """Declares a pipeline that must run before this one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Unique label for this dependency")
    settings: str = Field(min_length=1, description="Path to dependency pipeline settings file")


class CommencementGateConfig(BaseModel):
    """Declares a go/no-go condition evaluated before the pipeline starts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Unique label for this gate")
    condition: str = Field(min_length=1, description="Expression evaluated against pre-flight context")


class CollectionProbeConfig(BaseModel):
    """Declares a vector store collection to probe before gate evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(min_length=1, description="Collection name to probe")
    provider: str = Field(min_length=1, description="Provider type (e.g., 'chroma')")
    provider_config: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific connection config",
    )

    @model_validator(mode="after")
    def _freeze_provider_config(self) -> CollectionProbeConfig:
        """Deep-freeze provider_config to enforce Pydantic frozen=True contract."""
        object.__setattr__(self, "provider_config", deep_freeze(self.provider_config))
        return self

    @field_serializer("provider_config")
    @classmethod
    def _serialize_provider_config(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        """Thaw MappingProxyType back to dict for Pydantic JSON serialization."""
        result = deep_thaw(value)
        if type(result) is not dict:
            raise TypeError(
                f"deep_thaw(provider_config) returned {type(result).__name__}, expected dict. Input type was {type(value).__name__}."
            )
        return result


@dataclass(frozen=True, slots=True)
class DependencyRunResult:
    """Result of a successful dependency pipeline run."""

    name: str
    run_id: str
    settings_hash: str
    duration_ms: int
    indexed_at: str  # ISO 8601 timestamp


@dataclass(frozen=True, slots=True)
class CommencementGateResult:
    """Result of a successful commencement gate evaluation."""

    name: str
    condition: str
    result: bool
    context_snapshot: Mapping[str, Any]

    def __post_init__(self) -> None:
        freeze_fields(self, "context_snapshot")


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Combined pre-flight results for audit recording.

    Produced by ``resolve_preflight()`` and carried through the orchestrator
    to the Landscape recorder, following the same deferred-recording pattern
    as secret resolutions. Both the CLI path and ``bootstrap_and_run()``
    (sub-pipeline execution) produce this via the shared ``resolve_preflight()``.
    """

    dependency_runs: tuple[DependencyRunResult, ...]
    gate_results: tuple[CommencementGateResult, ...]
