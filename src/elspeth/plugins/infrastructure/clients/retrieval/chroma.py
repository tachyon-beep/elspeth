"""ChromaDB provider for RAG retrieval.

Supports three modes:
- ephemeral: In-memory, no persistence. Ideal for testing and development.
- persistent: Local disk storage. Survives process restarts.
- client: Remote Chroma server via HTTP/gRPC.

Score normalization:
- Chroma returns distances, not similarities. The normalization depends on
  the collection's distance function:
  - cosine: distance in [0, 2], similarity = 1 - (distance / 2)
  - l2: distance in [0, inf), similarity = 1 / (1 + distance)
  - ip (inner product): distance = 1 - similarity for normalized vectors,
    similarity = 1 - distance (clamped to [0, 1])
"""

from __future__ import annotations

import math
import re
import time
from typing import TYPE_CHECKING, Literal, Self

import chromadb
from pydantic import BaseModel, field_validator, model_validator

from elspeth.contracts.call_data import RawCallPayload
from elspeth.contracts.enums import CallStatus, CallType
from elspeth.contracts.probes import CollectionReadinessResult
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.connection import ChromaConnectionConfig
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class ChromaSearchProviderConfig(BaseModel):
    """Configuration for ChromaDB provider."""

    model_config = {"extra": "forbid", "frozen": True}

    collection: str
    mode: Literal["ephemeral", "persistent", "client"] = "ephemeral"

    persist_directory: str | None = None

    host: str | None = None
    port: int = 8000
    ssl: bool = True

    distance_function: Literal["cosine", "l2", "ip"] = "cosine"

    @field_validator("collection")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError(f"collection name must be at least 3 characters, got {len(v)}")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$", v):
            raise ValueError(
                f"collection must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start/end with alphanumeric), got {v!r}."
            )
        return v

    @field_validator("persist_directory")
    @classmethod
    def validate_persist_directory(cls, v: str | None) -> str | None:
        if v is not None and ".." in v.split("/"):
            raise ValueError(f"persist_directory must not contain '..' path components, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Self:
        if self.mode in ("persistent", "client"):
            # Delegate cross-field validation to ChromaConnectionConfig.
            # Construction triggers its model_validator; we discard the
            # instance — the provider config keeps its own flat fields.
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

    def to_connection_config(self) -> ChromaConnectionConfig:
        """Build a ChromaConnectionConfig from this provider config.

        Only valid when mode is 'persistent' or 'client'. Raises
        ValueError for ephemeral mode (no shared connection to configure).
        """
        if self.mode == "ephemeral":
            raise ValueError(
                "Cannot create ChromaConnectionConfig from ephemeral mode — ephemeral clients have no shared connection parameters"
            )
        return ChromaConnectionConfig(
            collection=self.collection,
            mode=self.mode,
            persist_directory=self.persist_directory,
            host=self.host,
            port=self.port,
            ssl=self.ssl,
            distance_function=self.distance_function,
        )


class ChromaSearchProvider:
    """ChromaDB implementation of RetrievalProvider.

    Uses the chromadb Python SDK directly. No AuditedHTTPClient.
    Score normalization converts Chroma distances to [0.0, 1.0] similarity scores.
    """

    def __init__(
        self,
        config: ChromaSearchProviderConfig,
        *,
        recorder: LandscapeRecorder | None = None,
        run_id: str | None = None,
    ) -> None:
        self._config = config
        self._distance_function = config.distance_function
        self._recorder = recorder
        self._run_id = run_id

        if config.mode == "ephemeral":
            self._client = chromadb.Client()
        elif config.mode == "persistent":
            # persist_directory is guaranteed non-None by validate_mode_requirements
            assert config.persist_directory is not None
            self._client = chromadb.PersistentClient(path=config.persist_directory)
        else:
            # host is guaranteed non-None by validate_mode_requirements
            assert config.host is not None
            self._client = chromadb.HttpClient(
                host=config.host,
                port=config.port,
                ssl=config.ssl,
            )

        try:
            self._collection = self._client.get_or_create_collection(
                name=config.collection,
                metadata={"hnsw:space": config.distance_function},
            )
            # Chroma collection metadata is Tier 3 (external/persisted data) — use .get()
            # to safely detect mismatch rather than crashing on missing key.
            collection_metadata = self._collection.metadata or {}
            actual_space = collection_metadata.get("hnsw:space")
            if actual_space is not None and actual_space != config.distance_function:
                raise RetrievalError(
                    f"Chroma collection {config.collection!r} exists with "
                    f"distance_function={actual_space!r}, but config specifies "
                    f"{config.distance_function!r}. Score normalization would use "
                    f"the wrong formula. Either change the config to match the "
                    f"existing collection, or use a different collection name.",
                    retryable=False,
                )
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError(
                f"Failed to access Chroma collection {config.collection!r}: {exc}",
                retryable=False,
            ) from exc

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        *,
        state_id: str,
        token_id: str | None,
    ) -> list[RetrievalChunk]:
        collection_count = self._collection.count()
        if collection_count == 0:
            return []
        effective_top_k = min(top_k, collection_count)

        start_time = time.monotonic()
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=effective_top_k,
                include=["documents", "distances", "metadatas"],
            )
        except Exception as exc:
            raise RetrievalError(f"Chroma query failed: {exc}", retryable=True) from exc
        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Tier 3 boundary: ChromaDB SDK response structure is external data.
        # Wrap access to guard against malformed/unexpected SDK responses.
        try:
            raw_documents = results["documents"]
            raw_distances = results["distances"]
            raw_metadatas = results["metadatas"]
            if raw_documents is None or raw_distances is None or raw_metadatas is None:
                raise RetrievalError(
                    "Chroma query returned None for documents/distances/metadatas",
                    retryable=False,
                )
            documents = raw_documents[0]
            distances = raw_distances[0]
            metadatas = raw_metadatas[0]
            ids = results["ids"][0]
        except (KeyError, TypeError, IndexError) as exc:
            raise RetrievalError(
                f"Chroma query returned unexpected result structure: {exc}",
                retryable=False,
            ) from exc

        chunks: list[RetrievalChunk] = []
        skipped = 0
        for doc, distance, metadata, doc_id in zip(documents, distances, metadatas, ids, strict=True):
            if not isinstance(doc, str):  # Tier 3: SDK may return non-str from corrupt index
                skipped += 1  # type: ignore[unreachable]
                continue

            # ChromaDB is our infrastructure, not an external API — corrupt
            # distances indicate index corruption or SDK bug.  Crash rather
            # than silently skipping: a run that completes with missing
            # retrieval chunks is worse than a crash (silent wrong result).
            if isinstance(distance, bool) or not isinstance(distance, (int, float)):
                raise RetrievalError(
                    f"ChromaDB collection {self._config.collection!r} returned "
                    f"non-numeric distance {distance!r} (type={type(distance).__name__}) "
                    f"for document {doc_id!r}. This indicates index corruption or a "
                    f"ChromaDB SDK bug — the collection may need to be rebuilt.",
                    retryable=False,
                )

            score = self._normalize_distance(distance)
            if score < min_score:
                continue

            chunks.append(
                RetrievalChunk(
                    content=doc,
                    score=score,
                    source_id=doc_id,
                    metadata=dict(metadata) if metadata else {},
                )
            )

        chunks.sort(key=lambda c: c.score, reverse=True)

        if self._recorder is not None:
            call_index = self._recorder.allocate_call_index(state_id)
            self._recorder.record_call(
                state_id=state_id,
                call_index=call_index,
                call_type=CallType.VECTOR,
                status=CallStatus.SUCCESS,
                request_data=RawCallPayload({"query": query, "top_k": effective_top_k, "collection": self._config.collection}),
                response_data=RawCallPayload(
                    {"result_count": len(chunks), "skipped_count": skipped, "top_score": chunks[0].score if chunks else None}
                ),
                latency_ms=round(elapsed_ms),
            )

        return chunks

    def _normalize_distance(self, distance: float) -> float:
        if not math.isfinite(distance):
            raise RetrievalError(
                f"Chroma returned non-finite distance {distance!r} — possible index corruption",
                retryable=False,
            )
        if self._distance_function == "cosine":
            return max(0.0, min(1.0, 1.0 - (distance / 2.0)))
        elif self._distance_function == "l2":
            return 1.0 / (1.0 + distance)
        else:  # ip
            return max(0.0, min(1.0, 1.0 - distance))

    def check_readiness(self) -> CollectionReadinessResult:
        """Check that the ChromaDB collection exists and has documents.

        Called during on_start() AFTER provider construction. self._collection
        is always set by __init__ (which calls get_or_create_collection).
        If __init__ fails, the provider doesn't exist and this method is
        never called.
        """
        collection_name = self._config.collection

        try:
            count = self._collection.count()
            return CollectionReadinessResult(
                collection=collection_name,
                reachable=True,
                count=count,
                message=(
                    f"Collection '{collection_name}' has {count} documents" if count > 0 else f"Collection '{collection_name}' is empty"
                ),
            )
        except Exception as exc:
            return CollectionReadinessResult(
                collection=collection_name,
                reachable=False,
                count=0,
                message=f"Collection '{collection_name}' unreachable: {type(exc).__name__}: {exc}",
            )

    def close(self) -> None:
        pass
