"""ChromaDB vector store sink plugin.

Writes pipeline rows into a ChromaDB collection. Each row becomes a
document with ChromaDB's default embedding function.
"""

from __future__ import annotations

import contextlib
import hashlib
import time
from collections.abc import Callable
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
    """Maps row field names to ChromaDB document concepts.

    Field values are names of row fields, not literal content.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    document_field: str = Field(description="Row field containing text to embed")
    id_field: str = Field(description="Row field containing document ID")
    metadata_fields: tuple[str, ...] = Field(
        default_factory=tuple,
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
    Content is hashed (canonical JSON of the actual payload sent) before
    write for audit integrity.

    Trust boundary: ChromaDB is our infrastructure (Tier 2 — types are
    trustworthy from upstream validation). ChromaDB SDK errors are caught
    as chromadb.errors.ChromaError; other exceptions crash through as
    plugin bugs per CLAUDE.md plugin ownership rules.
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
        self._telemetry_emit: Callable[[Any], None] | None = None
        self._total_written = 0
        self._total_bytes = 0

    def on_start(self, ctx: LifecycleContext) -> None:
        super().on_start(ctx)
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
            self._client.heartbeat()

        self._collection = self._client.get_or_create_collection(
            name=self._config.collection,
            metadata={"hnsw:space": self._config.distance_function},
        )

    @staticmethod
    def _compute_payload_hash(
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None,
    ) -> tuple[str, int]:
        """Compute canonical hash and size for the actual payload being sent."""
        payload = canonical_json({"ids": ids, "documents": documents, "metadatas": metadatas})
        payload_bytes = payload.encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest(), len(payload_bytes)

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
        ids = [row[fm.id_field] for row in rows]
        documents = [row[fm.document_field] for row in rows]
        # ChromaDB rejects empty metadata dicts — pass None when no metadata fields configured
        metadatas: list[dict[str, Any]] | None = (
            [{field: row[field] for field in fm.metadata_fields} for row in rows] if fm.metadata_fields else None
        )

        # These will be updated for skip mode to reflect actual payload sent
        write_ids = ids
        write_documents = documents
        write_metadatas = metadatas
        rows_written = len(rows)
        rows_skipped = 0
        skipped_ids: list[str] = []

        start_time = time.perf_counter()
        try:
            if self._config.on_duplicate == "overwrite":
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                )
            elif self._config.on_duplicate == "skip":
                existing = collection.get(ids=ids)
                existing_ids = set(existing["ids"])
                new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]

                skipped_ids = [id_ for id_ in ids if id_ in existing_ids]
                rows_skipped = len(skipped_ids)

                if new_indices:
                    write_ids = [ids[i] for i in new_indices]
                    write_documents = [documents[i] for i in new_indices]
                    write_metadatas = [metadatas[i] for i in new_indices] if metadatas is not None else None
                    rows_written = len(new_indices)
                    collection.add(
                        ids=write_ids,
                        documents=write_documents,
                        metadatas=write_metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                    )
                else:
                    write_ids = []
                    write_documents = []
                    write_metadatas = None
                    rows_written = 0
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
                    metadatas=metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
        except (chromadb.errors.ChromaError, DuplicateDocumentError) as write_exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            with contextlib.suppress(Exception):  # Preserve original — audit failure is secondary
                ctx.record_call(
                    call_type=CallType.VECTOR,
                    status=CallStatus.ERROR,
                    request_data={
                        "operation": self._config.on_duplicate.upper(),
                        "collection": self._config.collection,
                        "row_count": len(rows),
                    },
                    error={
                        "type": type(write_exc).__name__,
                        "message": str(write_exc),
                    },
                    latency_ms=latency_ms,
                    provider="chromadb",
                )
            raise

        # Hash the actual payload sent, not the full batch (critical for skip mode)
        content_hash, payload_size = self._compute_payload_hash(write_ids, write_documents, write_metadatas)

        try:
            response_data: dict[str, Any] = {"rows_written": rows_written}
            if rows_skipped > 0:
                response_data["rows_skipped"] = rows_skipped
                response_data["skipped_ids"] = skipped_ids

            ctx.record_call(
                call_type=CallType.VECTOR,
                status=CallStatus.SUCCESS,
                request_data={
                    "operation": self._config.on_duplicate.upper(),
                    "collection": self._config.collection,
                    "row_count": len(rows),
                    "document_ids": write_ids,
                },
                response_data=response_data,
                latency_ms=latency_ms,
                provider="chromadb",
            )
        except Exception as exc:
            raise AuditIntegrityError(
                f"Failed to record successful ChromaDB write to audit trail "
                f"(collection={self._config.collection!r}, row_count={rows_written}). "
                f"Write completed but audit record is missing."
            ) from exc

        self._total_written += rows_written
        self._total_bytes += payload_size

        return ArtifactDescriptor.for_database(
            url=chroma_url,
            table=self._config.collection,
            content_hash=content_hash,
            payload_size=payload_size,
            row_count=rows_written,
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
        if self._client is not None:
            self._client.clear_system_cache()
        self._client = None
        self._collection = None
