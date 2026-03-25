"""Configuration models for pipeline dependencies and commencement gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from elspeth.contracts.freeze import freeze_fields


class DependencyConfig(BaseModel):
    """Declares a pipeline that must run before this one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Unique label for this dependency")
    settings: str = Field(description="Path to dependency pipeline settings file")


class CommencementGateConfig(BaseModel):
    """Declares a go/no-go condition evaluated before the pipeline starts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="Unique label for this gate")
    condition: str = Field(description="Expression evaluated against pre-flight context")
    on_fail: Literal["abort"] = Field(
        default="abort",
        description="Action on failure (only 'abort' supported initially)",
    )


class CollectionProbeConfig(BaseModel):
    """Declares a vector store collection to probe before gate evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(description="Collection name to probe")
    provider: str = Field(description="Provider type (e.g., 'chroma')")
    provider_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific connection config",
    )


@dataclass(frozen=True, slots=True)
class DependencyRunResult:
    """Result of a successful dependency pipeline run."""

    name: str
    run_id: str
    settings_hash: str
    duration_ms: int
    indexed_at: str  # ISO 8601 timestamp


@dataclass(frozen=True, slots=True)
class GateResult:
    """Result of a successful commencement gate evaluation."""

    name: str
    condition: str
    result: bool
    context_snapshot: Mapping[str, Any]

    def __post_init__(self) -> None:
        freeze_fields(self, "context_snapshot")
