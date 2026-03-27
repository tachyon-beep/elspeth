"""ChromaDB vector store sink plugin.

Writes pipeline rows into a ChromaDB collection. Each row becomes a
document with ChromaDB's default embedding function.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

import chromadb
import chromadb.api
import chromadb.errors
import structlog
from pydantic import BaseModel, Field, model_validator

from elspeth.contracts.diversion import SinkWriteResult
from elspeth.contracts.enums import CallStatus, CallType
from elspeth.contracts.errors import (
    AuditIntegrityError,
    DuplicateDocumentError,
    FrameworkBugError,
)
from elspeth.contracts.results import ArtifactDescriptor
from elspeth.contracts.url import SanitizedDatabaseUrl
from elspeth.core.canonical import canonical_json
from elspeth.plugins.infrastructure.base import BaseSink
from elspeth.plugins.infrastructure.clients.retrieval.connection import (
    ChromaConnectionConfig,
)
from elspeth.plugins.infrastructure.config_base import DataPluginConfig
from elspeth.plugins.infrastructure.schema_factory import create_schema_from_config

slog = structlog.get_logger(__name__)


class _ChromaPayloadRejection(Exception):
    """Chroma API rejected the payload with ValueError.

    Wraps ValueError from Chroma write calls (upsert/add) so the error handler
    can distinguish "Chroma rejected our data" (Tier 3) from "bug in our code"
    (framework error). Without this, a broad ValueError catch would suppress
    framework bugs in the surrounding code.
    """


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
    port: int = Field(default=8000, ge=1, le=65535)
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

    Trust boundary: Row data arriving at this sink is Tier 2 (types validated
    upstream). ChromaDB itself is an external system — SDK errors
    (chromadb.errors.ChromaError) are caught as infrastructure failures;
    other exceptions crash through as plugin bugs per CLAUDE.md plugin
    ownership rules.
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
            if self._config.persist_directory is None:
                raise FrameworkBugError(
                    "ChromaSinkConfig.persist_directory is None in 'persistent' mode "
                    "— ChromaConnectionConfig validation should have rejected this"
                )
            self._client = chromadb.PersistentClient(
                path=self._config.persist_directory,
            )
        else:
            # Validated by ChromaConnectionConfig: host is not None
            if self._config.host is None:
                raise FrameworkBugError(
                    "ChromaSinkConfig.host is None in 'client' mode — ChromaConnectionConfig validation should have rejected this"
                )
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

    def write(self, rows: list[dict[str, Any]], ctx: SinkContext) -> SinkWriteResult:
        if self._collection is None:
            raise FrameworkBugError("ChromaSink._collection is None — on_start() was not called before write()")
        collection = self._collection

        chroma_url = SanitizedDatabaseUrl.from_raw_url(f"chromadb://{self._config.collection}")

        if not rows:
            return SinkWriteResult(
                artifact=ArtifactDescriptor.for_database(
                    url=chroma_url,
                    table=self._config.collection,
                    content_hash=hashlib.sha256(b"").hexdigest(),
                    payload_size=0,
                    row_count=0,
                )
            )

        fm = self._config.field_mapping

        # Per-row extraction of required fields (id, document) and optional metadata.
        # Missing or non-string required fields are per-row data problems — divert
        # the row rather than aborting the entire batch.
        ids: list[str] = []
        documents: list[str] = []
        metadatas_list: list[dict[str, Any]] = []
        valid_indices: list[int] = []

        for i, row in enumerate(rows):
            # Required fields: id and document must be present and string-typed.
            try:
                raw_id = row[fm.id_field]
                raw_doc = row[fm.document_field]
            except KeyError as exc:
                self._divert_row(
                    row,
                    row_index=i,
                    reason=f"Missing required field: {exc}",
                )
                continue

            if not isinstance(raw_id, str):
                self._divert_row(
                    row,
                    row_index=i,
                    reason=f"Field '{fm.id_field}' must be str, got {type(raw_id).__name__}",
                )
                continue
            if not isinstance(raw_doc, str):
                self._divert_row(
                    row,
                    row_index=i,
                    reason=f"Field '{fm.document_field}' must be str, got {type(raw_doc).__name__}",
                )
                continue

            # Optional metadata fields — extract if configured, validate types.
            # ChromaDB accepts str|int|float|bool|None — anything else is a per-row
            # data problem, not a plugin bug.
            if fm.metadata_fields:
                meta = {}
                bad_fields: dict[str, str] = {}
                for field in fm.metadata_fields:
                    try:
                        value = row[field]
                    except KeyError:
                        # Missing metadata field — skip it (metadata is optional per-field)
                        continue
                    if value is not None and not isinstance(value, (str, int, float, bool)):
                        bad_fields[field] = type(value).__name__
                    else:
                        meta[field] = value
                if bad_fields:
                    self._divert_row(
                        row,
                        row_index=i,
                        reason=f"Invalid ChromaDB metadata types: {bad_fields}",
                    )
                    continue
                metadatas_list.append(meta)

            ids.append(raw_id)
            documents.append(raw_doc)
            valid_indices.append(i)

        # ChromaDB rejects empty metadata dicts — pass None when no metadata fields configured
        metadatas: list[dict[str, Any]] | None = metadatas_list if fm.metadata_fields else None

        # Handle all-rejected case: nothing to write, return zero-write artifact
        if not ids:
            content_hash, payload_size = self._compute_payload_hash([], [], None)
            try:
                ctx.record_call(
                    call_type=CallType.VECTOR,
                    status=CallStatus.SUCCESS,
                    request_data={
                        "operation": self._config.on_duplicate.upper(),
                        "collection": self._config.collection,
                        "row_count": 0,
                        "batch_size": len(rows),
                    },
                    response_data={
                        "rows_written": 0,
                    },
                    latency_ms=0.0,
                    provider="chromadb",
                )
            except Exception as exc:
                raise AuditIntegrityError(
                    f"Failed to record metadata-rejected ChromaDB write to audit trail (collection={self._config.collection!r})."
                ) from exc
            return SinkWriteResult(
                artifact=ArtifactDescriptor.for_database(
                    url=chroma_url,
                    table=self._config.collection,
                    content_hash=content_hash,
                    payload_size=payload_size,
                    row_count=0,
                ),
                diversions=self._get_diversions(),
            )

        # These will be updated for skip/error mode to reflect actual payload sent
        write_ids = ids
        write_documents = documents
        write_metadatas = metadatas
        rows_written = len(ids)
        rows_skipped = 0
        skipped_ids: list[str] = []

        start_time = time.perf_counter()
        try:
            if self._config.on_duplicate == "overwrite":
                try:
                    collection.upsert(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                    )
                except ValueError as ve:
                    raise _ChromaPayloadRejection(str(ve)) from ve
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
                    try:
                        collection.add(
                            ids=write_ids,
                            documents=write_documents,
                            metadatas=write_metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                        )
                    except ValueError as ve:
                        raise _ChromaPayloadRejection(str(ve)) from ve
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
                try:
                    collection.add(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas,  # type: ignore[arg-type]  # chromadb stub Metadata vs dict[str, Any]
                    )
                except ValueError as ve:
                    raise _ChromaPayloadRejection(str(ve)) from ve

            latency_ms = (time.perf_counter() - start_time) * 1000
        except (chromadb.errors.ChromaError, DuplicateDocumentError, _ChromaPayloadRejection) as write_exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            try:
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
            except Exception as audit_exc:
                raise AuditIntegrityError(
                    f"Failed to record failed ChromaDB write to audit trail "
                    f"(collection={self._config.collection!r}, original_error={type(write_exc).__name__}). "
                    f"Write failed AND audit record is missing."
                ) from audit_exc
            raise

        # Hash the actual payload sent, not the full batch (critical for skip mode)
        content_hash, payload_size = self._compute_payload_hash(write_ids, write_documents, write_metadatas)

        diversions = self._get_diversions()

        try:
            response_data: dict[str, Any] = {"rows_written": rows_written}
            if rows_skipped > 0:
                response_data["rows_skipped"] = rows_skipped
                response_data["skipped_ids"] = skipped_ids

            request_data: dict[str, Any] = {
                "operation": self._config.on_duplicate.upper(),
                "collection": self._config.collection,
                "row_count": rows_written,
                "document_ids": write_ids,
            }
            if rows_skipped > 0 or diversions:
                request_data["batch_size"] = len(rows)

            ctx.record_call(
                call_type=CallType.VECTOR,
                status=CallStatus.SUCCESS,
                request_data=request_data,
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

        return SinkWriteResult(
            artifact=ArtifactDescriptor.for_database(
                url=chroma_url,
                table=self._config.collection,
                content_hash=content_hash,
                payload_size=payload_size,
                row_count=rows_written,
            ),
            diversions=diversions,
        )

    def flush(self) -> None:
        """ChromaDB writes are synchronous in write() — no pending data to flush."""

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
