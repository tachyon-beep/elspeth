"""Azure AI Search provider for RAG retrieval."""

from __future__ import annotations

import re
import urllib.parse
from typing import Literal, Self

from pydantic import BaseModel, field_validator, model_validator


class AzureSearchProviderConfig(BaseModel):
    """Configuration for Azure AI Search provider."""

    model_config = {"extra": "forbid", "frozen": True}

    endpoint: str
    index: str

    api_key: str | None = None
    use_managed_identity: bool = False
    api_version: str = "2024-07-01"

    search_mode: Literal["vector", "keyword", "hybrid", "semantic"] = "hybrid"
    request_timeout: float = 30.0

    vector_field: str = "contentVector"
    semantic_config: str | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        parsed = urllib.parse.urlparse(v)
        if parsed.scheme != "https":
            raise ValueError(f"endpoint must use HTTPS scheme, got {parsed.scheme!r}")
        if not parsed.hostname:
            raise ValueError(f"endpoint must have a hostname, got {v!r}")
        return v

    @field_validator("index")
    @classmethod
    def validate_index_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                f"index must contain only alphanumeric characters, hyphens, and underscores (and start with alphanumeric), got {v!r}."
            )
        return v

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}(-preview)?$", v):
            raise ValueError(f"api_version must match YYYY-MM-DD or YYYY-MM-DD-preview format, got {v!r}")
        return v

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str | None) -> str | None:
        if v is not None:
            if any(c in v for c in "\r\n\x00"):
                raise ValueError("api_key must not contain newlines or null bytes")
            if len(v) > 256:
                raise ValueError(f"api_key exceeds maximum length of 256, got {len(v)}")
        return v

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        if not self.api_key and not self.use_managed_identity:
            raise ValueError("Specify either api_key or use_managed_identity=true")
        if self.api_key and self.use_managed_identity:
            raise ValueError("Specify only one of api_key or use_managed_identity")
        return self

    @model_validator(mode="after")
    def validate_semantic_config(self) -> Self:
        if self.search_mode == "semantic" and not self.semantic_config:
            raise ValueError("semantic search_mode requires semantic_config")
        return self


class AzureSearchProvider:
    """Azure AI Search implementation of RetrievalProvider.

    Placeholder — full implementation in Task 9.
    """

    pass
