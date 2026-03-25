"""Shared ChromaDB connection configuration.

Used by ChromaSinkConfig, ChromaSearchProviderConfig, and CollectionProbeConfig.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChromaConnectionConfig(BaseModel):
    """Shared ChromaDB connection fields with cross-field validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(description="ChromaDB collection name")
    mode: Literal["persistent", "client"] = Field(description="Connection mode: persistent (local disk) or client (remote HTTP)")
    persist_directory: str | None = Field(
        default=None,
        description="Path to ChromaDB data directory (persistent mode only)",
    )
    host: str | None = Field(
        default=None,
        description="ChromaDB server hostname (client mode only)",
    )
    port: int = Field(default=8000, description="ChromaDB server port")
    ssl: bool = Field(default=True, description="Use HTTPS for client connections")
    distance_function: Literal["cosine", "l2", "ip"] = Field(
        default="cosine",
        description="Distance function for collection creation",
    )

    @model_validator(mode="after")
    def validate_mode_fields(self) -> ChromaConnectionConfig:
        if self.mode == "persistent":
            if self.persist_directory is None:
                raise ValueError("persist_directory is required when mode='persistent'")
            if self.host is not None:
                raise ValueError("host must not be set when mode='persistent'")
        elif self.mode == "client":
            if self.host is None:
                raise ValueError("host is required when mode='client'")
            if self.persist_directory is not None:
                raise ValueError("persist_directory must not be set when mode='client'")
            if not self.ssl and self.host not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError(
                    f"HTTPS (ssl=True) is required for remote ChromaDB hosts, "
                    f"got host={self.host!r} with ssl=False. "
                    f"Non-SSL connections are only permitted for localhost."
                )
        return self
