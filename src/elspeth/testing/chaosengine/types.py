# src/elspeth/testing/chaosengine/types.py
"""Shared types for chaos testing infrastructure.

Contains configuration models shared across all chaos plugins (ServerConfig,
MetricsConfig, LatencyConfig) and generic types for the injection engine
(ErrorSpec, BurstConfig) and metrics store (MetricsSchema).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

# =============================================================================
# Shared Configuration Models
# =============================================================================


class ServerConfig(BaseModel):
    """Server binding and worker configuration."""

    model_config = {"frozen": True, "extra": "forbid"}

    host: str = Field(
        default="127.0.0.1",
        description="Host address to bind to",
    )
    port: int = Field(
        default=8000,
        gt=0,
        le=65535,
        description="Port to listen on",
    )
    workers: int = Field(
        default=4,
        gt=0,
        description="Number of uvicorn workers",
    )


class MetricsConfig(BaseModel):
    """Metrics storage configuration."""

    model_config = {"frozen": True, "extra": "forbid"}

    database: str = Field(
        default="file:chaos-metrics?mode=memory&cache=shared",
        description="SQLite database path for metrics storage (in-memory by default)",
    )
    timeseries_bucket_sec: int = Field(
        default=1,
        gt=0,
        description="Time-series aggregation bucket size in seconds",
    )


class LatencyConfig(BaseModel):
    """Latency simulation configuration."""

    model_config = {"frozen": True, "extra": "forbid"}

    base_ms: int = Field(
        default=50,
        ge=0,
        description="Base latency in milliseconds",
    )
    jitter_ms: int = Field(
        default=30,
        ge=0,
        description="Random jitter added to base latency (+/- ms)",
    )


# =============================================================================
# Injection Engine Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """A single error specification for the injection engine.

    ErrorSpec is the currency between a chaos plugin and the InjectionEngine.
    The plugin builds a list of ErrorSpec objects (with domain-specific tags),
    and the engine selects which one fires based on weights and burst state.

    Attributes:
        tag: Opaque identifier for this error type (e.g., "rate_limit", "timeout").
             The engine doesn't interpret this — the caller uses it to map back
             to a domain-specific decision.
        weight: Probability weight for this error (0-100 scale).
    """

    tag: str
    weight: float


@dataclass(frozen=True, slots=True)
class BurstConfig:
    """Burst state machine configuration.

    Configures periodic burst windows where the injection engine reports
    elevated error rates.

    Attributes:
        enabled: Whether burst mode is active.
        interval_sec: Time between burst starts in seconds.
        duration_sec: How long each burst lasts in seconds.
    """

    enabled: bool = False
    interval_sec: float = 30.0
    duration_sec: float = 5.0


# =============================================================================
# Metrics Store Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class ColumnDef:
    """Definition of a single column in a metrics table.

    Attributes:
        name: Column name in the database.
        sql_type: SQLite column type (TEXT, INTEGER, REAL).
        nullable: Whether the column allows NULL values.
        default: Default value expression (e.g., "0", "NULL").
        primary_key: Whether this column is the primary key.
    """

    name: str
    sql_type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


@dataclass(frozen=True, slots=True)
class MetricsSchema:
    """Schema definition for a metrics database.

    Describes the structure of the requests and timeseries tables
    that a specific chaos plugin needs. The MetricsStore generates
    DDL from this schema at initialization.

    Attributes:
        request_columns: Column definitions for the requests table.
        timeseries_columns: Column definitions for the timeseries table.
        request_indexes: Additional indexes on the requests table.
            Each entry is (index_name, column_name).
    """

    request_columns: tuple[ColumnDef, ...]
    timeseries_columns: tuple[ColumnDef, ...]
    request_indexes: tuple[tuple[str, str], ...] = ()
