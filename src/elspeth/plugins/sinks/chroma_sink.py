"""ChromaDB vector store sink plugin.

Writes pipeline rows into a ChromaDB collection. Each row becomes a document.
ChromaDB handles embedding internally via its configured embedding function.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from elspeth.plugins.infrastructure.clients.retrieval.connection import (
    ChromaConnectionConfig,
)
from elspeth.plugins.infrastructure.config_base import DataPluginConfig


class FieldMappingConfig(BaseModel):
    """Maps row fields to ChromaDB document concepts."""

    model_config = {"frozen": True, "extra": "forbid"}

    document: str = Field(description="Row field containing text to embed")
    id: str = Field(description="Row field containing document ID")
    metadata: list[str] = Field(
        default_factory=list,
        description="Row fields to include as ChromaDB metadata",
    )


class ChromaSinkConfig(DataPluginConfig):
    """Configuration for ChromaDB vector store sink.

    Connection fields are flat (matching YAML config convention for sinks)
    and validated by constructing a ChromaConnectionConfig in the model
    validator. This is the same delegation pattern used by
    ChromaSearchProviderConfig.
    """

    collection: str = Field(description="ChromaDB collection name")
    mode: Literal["persistent", "client"] = Field(description="Connection mode")
    persist_directory: str | None = Field(default=None)
    host: str | None = Field(default=None)
    port: int = Field(default=8000)
    ssl: bool = Field(default=True)
    distance_function: Literal["cosine", "l2", "ip"] = Field(default="cosine")

    field_mapping: FieldMappingConfig = Field(description="Maps row fields to ChromaDB document/id/metadata")
    on_duplicate: Literal["overwrite", "skip", "error"] = Field(
        default="overwrite",
        description="Behaviour when a document ID already exists",
    )

    @model_validator(mode="after")
    def validate_connection(self) -> ChromaSinkConfig:
        """Delegate connection validation to ChromaConnectionConfig."""
        ChromaConnectionConfig(
            collection=self.collection,
            mode=self.mode,
            persist_directory=self.persist_directory,
            host=self.host,
            port=self.port,
            ssl=self.ssl,
            distance_function=self.distance_function,
        )
        return self
