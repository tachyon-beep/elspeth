"""ChromaDB vector store sink plugin.

Writes pipeline rows into a ChromaDB collection. Each row becomes a document.
ChromaDB handles embedding internally via its configured embedding function.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING, Any, Literal

import chromadb
import chromadb.api
import chromadb.errors
from pydantic import BaseModel, Field, model_validator

from elspeth.contracts.enums import CallStatus, CallType
from elspeth.contracts.errors import AuditIntegrityError, DuplicateDocumentError
from elspeth.contracts.results import ArtifactDescriptor
from elspeth.contracts.url import SanitizedDatabaseUrl
from elspeth.core.canonical import canonical_json
from elspeth.plugins.infrastructure.base import BaseSink
from elspeth.plugins.infrastructure.clients.retrieval.connection import (
    ChromaConnectionConfig,
)
from elspeth.plugins.infrastructure.config_base import DataPluginConfig
from elspeth.plugins.infrastructure.schema_factory import create_schema_from_config

if TYPE_CHECKING:
    from elspeth.contracts.contexts import LifecycleContext, SinkContext
    from elspeth.contracts.data import PluginSchema


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


class ChromaSink(BaseSink):
    """Write pipeline rows into a ChromaDB collection.

    Each row maps to a ChromaDB document via the configured field_mapping.
    Content is hashed (canonical JSON) before write for audit integrity.
    """

    name = "chroma_sink"
    plugin_version = "1.0.0"
    supports_resume = False

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._config = ChromaSinkConfig.from_dict(config)
        self._schema_class: type[PluginSchema] = create_schema_from_config(
            self._config.schema_config,
            "ChromaSinkRowSchema",
            allow_coercion=False,
        )
        self.input_schema = self._schema_class
        self.declared_required_fields = self._config.schema_config.get_effective_required_fields()

        self._client: chromadb.api.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._run_id: str | None = None
        self._telemetry_emit: Any = None
        self._total_written = 0
        self._total_bytes = 0

    def on_start(self, ctx: LifecycleContext) -> None:
        super().on_start(ctx)
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit

        if self._config.mode == "persistent":
            # Validated by ChromaConnectionConfig: persist_directory is not None
            assert self._config.persist_directory is not None
            self._client = chromadb.PersistentClient(
                path=self._config.persist_directory,
            )
        else:
            # Validated by ChromaConnectionConfig: host is not None
            assert self._config.host is not None
            self._client = chromadb.HttpClient(
                host=self._config.host,
                port=self._config.port,
                ssl=self._config.ssl,
            )

        self._collection = self._client.get_or_create_collection(
            name=self._config.collection,
            metadata={"hnsw:space": self._config.distance_function},
        )

    def write(self, rows: list[dict[str, Any]], ctx: SinkContext) -> ArtifactDescriptor:
        assert self._collection is not None, "write() called before on_start()"
        collection = self._collection

        chroma_url = SanitizedDatabaseUrl.from_raw_url(f"chromadb://{self._config.collection}")

        if not rows:
            return ArtifactDescriptor.for_database(
                url=chroma_url,
                table=self._config.collection,
                content_hash=hashlib.sha256(b"").hexdigest(),
                payload_size=0,
                row_count=0,
            )

        fm = self._config.field_mapping
        ids = [row[fm.id] for row in rows]
        documents = [row[fm.document] for row in rows]
        metadatas = [{field: row[field] for field in fm.metadata} for row in rows]

        payload = canonical_json({"ids": ids, "documents": documents, "metadatas": metadatas})
        payload_bytes = payload.encode("utf-8")
        content_hash = hashlib.sha256(payload_bytes).hexdigest()
        payload_size = len(payload_bytes)

        start_time = time.perf_counter()
        try:
            if self._config.on_duplicate == "overwrite":
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,  # type: ignore[arg-type]  # Tier 2 row values
                )
            elif self._config.on_duplicate == "skip":
                existing = collection.get(ids=ids)
                existing_ids = set(existing["ids"])
                new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
                if new_indices:
                    collection.add(
                        ids=[ids[i] for i in new_indices],
                        documents=[documents[i] for i in new_indices],
                        metadatas=[metadatas[i] for i in new_indices],
                    )
            elif self._config.on_duplicate == "error":
                existing = collection.get(ids=ids)
                existing_ids = set(existing["ids"])
                duplicates = [id_ for id_ in ids if id_ in existing_ids]
                if duplicates:
                    raise DuplicateDocumentError(
                        collection=self._config.collection,
                        duplicate_ids=duplicates,
                    )
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,  # type: ignore[arg-type]
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
        except (chromadb.errors.ChromaError, DuplicateDocumentError):
            latency_ms = (time.perf_counter() - start_time) * 1000
            ctx.record_call(
                call_type=CallType.VECTOR,
                status=CallStatus.ERROR,
                request_data={
                    "operation": self._config.on_duplicate.upper(),
                    "collection": self._config.collection,
                    "row_count": len(rows),
                },
                error={"type": "write_error"},
                latency_ms=latency_ms,
                provider="chromadb",
            )
            raise

        try:
            ctx.record_call(
                call_type=CallType.VECTOR,
                status=CallStatus.SUCCESS,
                request_data={
                    "operation": self._config.on_duplicate.upper(),
                    "collection": self._config.collection,
                    "row_count": len(rows),
                    "document_ids": ids,
                },
                response_data={"rows_written": len(rows)},
                latency_ms=latency_ms,
                provider="chromadb",
            )
        except Exception as exc:
            raise AuditIntegrityError(
                f"Failed to record successful ChromaDB write to audit trail "
                f"(collection={self._config.collection!r}, row_count={len(rows)}). "
                f"Write completed but audit record is missing."
            ) from exc

        self._total_written += len(rows)
        self._total_bytes += payload_size

        return ArtifactDescriptor.for_database(
            url=chroma_url,
            table=self._config.collection,
            content_hash=content_hash,
            payload_size=payload_size,
            row_count=len(rows),
        )

    def flush(self) -> None:
        pass

    def on_complete(self, ctx: LifecycleContext) -> None:
        if self._telemetry_emit is not None:
            self._telemetry_emit(
                {
                    "event": "chroma_sink_complete",
                    "collection": self._config.collection,
                    "total_written": self._total_written,
                    "total_bytes": self._total_bytes,
                }
            )

    def close(self) -> None:
        self._client = None
        self._collection = None
