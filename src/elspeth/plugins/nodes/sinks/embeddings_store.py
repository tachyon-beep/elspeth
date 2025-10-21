"""Sink plugin that persists experiment outputs as vector embeddings."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.validation.base import ConfigurationError
from elspeth.retrieval.embedding import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder

logger = logging.getLogger(__name__)


DEFAULT_TEXT_FIELD = "response.content"
DEFAULT_EMBEDDING_FIELD = "response.metrics.embedding"
DEFAULT_ID_FIELD = "row.APPID"
DEFAULT_METADATA_FIELDS = (
    "row.APPID",
    "row.record_id",
    "metadata.retry_summary",
    "metadata.cost_summary",
    "metadata.security_level",
)


@dataclass
class VectorRecord:
    """Container representing a single vector upsert operation."""

    document_id: str
    vector: Sequence[float]
    text: str
    metadata: dict[str, Any]
    security_level: str


@dataclass
class UpsertResponse:
    """Capture provider response metadata for auditing."""

    count: int
    took: float
    namespace: str
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class VectorStoreClient:
    """Abstract vector store client interface."""

    def upsert_many(self, namespace: str, records: Iterable[VectorRecord]) -> UpsertResponse:  # pragma: no cover - interface
        """Upsert vector records into the store.

        Args:
            namespace: Namespace for the records
            records: Iterable of VectorRecord objects to upsert

        Returns:
            UpsertResponse with count and timing metadata
        """
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - optional
        """Close the client connection and release resources."""
        return None


class PgVectorClient(VectorStoreClient):
    """pgvector-backed implementation using psycopg."""

    def __init__(
        self,
        *,
        dsn: str,
        table: str,
        upsert_conflict: str = "replace",
    ) -> None:
        try:
            import psycopg as _psycopg  # local import to avoid hard dependency at module import time
            from psycopg import sql as _sql
        except Exception as exc:  # pragma: no cover - exercised in integration
            raise ImportError(
                (
                    "pgvector provider requires psycopg and safe SQL identifier quoting; "
                    "install 'psycopg[binary]' or 'psycopg[c]' and ensure libpq is available."
                )
            ) from exc
        self._psycopg = _psycopg
        self._sql = _sql
        self._dsn = dsn
        self._table = table
        self._conflict_policy = upsert_conflict

    def _ensure_table(self, conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            # Use sql.Identifier to safely quote table name and prevent SQL injection
            # Safe: table name via sql.Identifier; values are parameterized placeholders
            cur.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                self._sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    namespace TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    embedding VECTOR(1536),
                    contents TEXT,
                    metadata JSONB,
                    security_level TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, document_id)
                )
                """).format(self._sql.Identifier(self._table))
            )

    def upsert_many(self, namespace: str, records: Iterable[VectorRecord]) -> UpsertResponse:
        start = time.time()
        items = list(records)
        if not items:
            return UpsertResponse(count=0, took=0.0, namespace=namespace)

        with self._psycopg.connect(self._dsn, autocommit=True) as conn:
            pg_conn = conn
            self._ensure_table(pg_conn)
            # Use sql.SQL and sql.Identifier to safely construct queries and prevent SQL injection
            query = self._build_insert_query()
            with pg_conn.cursor() as cur:
                for record in items:
                    vector_literal = self._vector_literal(record.vector)
                    metadata = json.dumps(record.metadata or {})
                    # Safe: table name via sql.Identifier; values provided as parameters
                    cur.execute(  # nosemgrep: parameterized psycopg with sql.Identifier and placeholders
                        query,
                        (
                            namespace,
                            record.document_id,
                            vector_literal,
                            record.text,
                            metadata,
                            record.security_level,
                        ),
                    )

        took = max(time.time() - start, 0.0)
        return UpsertResponse(count=len(items), took=took, namespace=namespace)

    def _vector_literal(self, vector: Sequence[float]) -> str:
        values = ",".join(f"{float(value):.12g}" for value in vector)
        return f"[{values}]"

    def _build_insert_query(self) -> Any:
        """Build the INSERT query with safe identifier quoting for table name.

        Returns SQL composed object with parameterized table name to prevent SQL injection.
        """
        policy = self._conflict_policy.lower()
        if policy not in {"replace", "skip"}:
            policy = "replace"

        if policy == "skip":
            conflict_clause = self._sql.SQL("NOTHING")
        else:
            conflict_clause = self._sql.SQL("""
            UPDATE SET embedding = EXCLUDED.embedding,
                        contents = EXCLUDED.contents,
                        metadata = EXCLUDED.metadata,
                        security_level = EXCLUDED.security_level,
                        updated_at = NOW()
            """)

        return self._sql.SQL("""
            INSERT INTO {} (namespace, document_id, embedding, contents, metadata, security_level, updated_at)
            VALUES (%s, %s, %s::vector, %s, %s::jsonb, %s, NOW())
            ON CONFLICT (namespace, document_id) DO {}
        """).format(self._sql.Identifier(self._table), conflict_clause)


class AzureSearchVectorClient(VectorStoreClient):
    """Azure Cognitive Search vector store implementation."""

    def __init__(
        self,
        *,
        endpoint: str,
        index: str,
        api_key: str,
        vector_field: str = "embedding",
        document_id_field: str = "document_id",
        namespace_field: str = "namespace",
    ) -> None:
        # Local imports to avoid hard dependency at module import time
        try:
            from azure.core.credentials import AzureKeyCredential as _AzureKeyCredential
            from azure.search.documents import SearchClient as _SearchClient
        except Exception as exc:  # pragma: no cover - exercised in integration
            raise ImportError("azure_search provider requires 'azure-search-documents' and 'azure-core' packages") from exc
        self._search_client_class = _SearchClient
        self._azure_key_credential_class = _AzureKeyCredential
        self._client = self._search_client_class(endpoint=endpoint, index_name=index, credential=self._azure_key_credential_class(api_key))
        self._vector_field = vector_field
        self._id_field = document_id_field
        self._namespace_field = namespace_field

    def upsert_many(self, namespace: str, records: Iterable[VectorRecord]) -> UpsertResponse:
        docs = []
        count = 0
        for record in records:
            docs.append(
                {
                    self._id_field: record.document_id,
                    self._namespace_field: namespace,
                    self._vector_field: list(record.vector),
                    "contents": record.text,
                    "metadata": record.metadata,
                    "security_level": record.security_level,
                }
            )
            count += 1
        if docs:
            self._client.upload_documents(documents=docs)
        return UpsertResponse(count=count, took=0.0, namespace=namespace)


class EmbeddingsStoreSink(ResultSink):
    """Persist experiment outputs into a vector store for RAG workflows."""

    def __init__(
        self,
        *,
        provider: str,
        namespace: str | None = None,
        dsn: str | None = None,
        table: str = "elspeth_rag",
        text_field: str = DEFAULT_TEXT_FIELD,
        embedding_source: str = DEFAULT_EMBEDDING_FIELD,
        embed_model: Mapping[str, Any] | None = None,
        metadata_fields: Sequence[str] | None = None,
        id_field: str = DEFAULT_ID_FIELD,
        batch_size: int = 50,
        upsert_conflict: str = "replace",
        provider_factory: Callable[[str, Mapping[str, Any]], VectorStoreClient] | None = None,
        embedder_factory: Callable[[Mapping[str, Any]], Embedder] | None = None,
        provider_options: Mapping[str, Any] | None = None,
    ) -> None:
        self.provider_name = provider
        self._namespace_override = namespace
        self._dsn = dsn
        self._table = table
        self._text_field = text_field
        self._embedding_field = embedding_source
        self._embed_model = dict(embed_model or {})
        self._metadata_fields = list(metadata_fields or DEFAULT_METADATA_FIELDS)
        self._id_field = id_field
        self._batch_size = max(int(batch_size), 1)
        self._upsert_conflict = upsert_conflict
        self._provider_factory = provider_factory or self._default_provider_factory
        self._embedder_factory = embedder_factory or self._default_embedder_factory
        provider_payload = {
            "dsn": dsn,
            "table": table,
            "upsert_conflict": upsert_conflict,
        }
        if provider_options:
            provider_payload.update(provider_options)
        self._client = self._provider_factory(
            provider,
            provider_payload,
        )
        self._embedder: Embedder | None = None
        self._last_manifest: dict[str, Any] | None = None

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        namespace = self._resolve_namespace(metadata)
        context: PluginContext | None = getattr(self, "plugin_context", None)
        security_level = metadata.get("security_level", getattr(context, "security_level", "unofficial"))
        determinism_level = metadata.get("determinism_level", getattr(context, "determinism_level", "none"))
        embeddings: list[VectorRecord] = []

        for index, record in enumerate(results.get("results") or []):
            vector = self._extract_embedding(record)
            text_value = self._extract_value(record, self._text_field) or ""
            if vector is None:
                if not self._embed_model:
                    raise ConfigurationError("embeddings_store requires embed_model configuration when payload lacks embeddings")
                vector = self._embed_text(str(text_value))

            document_id = self._extract_value(record, self._id_field) or f"{metadata.get('run_id', 'run')}-{index}"
            record_metadata = self._extract_metadata(record, metadata)
            # Persist classification as canonical text for storage
            if isinstance(security_level, str):
                sec_text = security_level
            else:
                try:
                    from elspeth.core.base.types import SecurityLevel as _SL

                    sec_text = security_level.value if isinstance(security_level, _SL) else str(security_level)
                except Exception:
                    sec_text = str(security_level)

            embeddings.append(
                VectorRecord(
                    document_id=str(document_id),
                    vector=vector,
                    text=str(text_value),
                    metadata=record_metadata,
                    security_level=sec_text,
                )
            )

        plugin_logger = getattr(self, "plugin_logger", None)
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write_attempt",
                message=f"Embeddings upsert attempt: provider={self.provider_name}, namespace={namespace}",
                metrics={"rows": len(embeddings)},
                metadata={"namespace": namespace, "provider": self.provider_name},
            )

        batches = [embeddings[i : i + self._batch_size] for i in range(0, len(embeddings), self._batch_size)]
        upsert_total = 0
        took_total = 0.0
        for batch in batches:
            response = self._client.upsert_many(namespace=namespace, records=batch)
            upsert_total += response.count
            took_total += response.took

        if upsert_total:
            self._last_manifest = {
                "namespace": namespace,
                "count": upsert_total,
                "batch_count": len(batches),
                "duration_seconds": took_total,
                "security_level": security_level,
                "determinism_level": determinism_level,
                "provider": self.provider_name,
            }
        else:
            self._last_manifest = None
        if plugin_logger:
            plugin_logger.log_event(
                "sink_write",
                message=f"Embeddings upserted: provider={self.provider_name}, namespace={namespace}",
                metrics={"count": upsert_total, "duration_seconds": took_total, "batches": len(batches)},
                metadata={"namespace": namespace, "provider": self.provider_name},
            )

    def collect_artifacts(self) -> dict[str, Artifact]:
        if not self._last_manifest:
            return {}
        payload = Artifact(
            id="",
            type="application/json",
            path=None,
            payload=dict(self._last_manifest),
            metadata=dict(self._last_manifest),
            persist=True,
            security_level=self._last_manifest.get("security_level"),
            determinism_level=self._last_manifest.get("determinism_level"),
        )
        self._last_manifest = None
        return {"embeddings_manifest": payload}

    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - metadata
        context: PluginContext | None = getattr(self, "plugin_context", None)
        return [
            ArtifactDescriptor(
                name="embeddings_index",
                type="data/vector-index",
                alias="embeddings:index",
                persist=True,
                security_level=getattr(context, "security_level", None),
            )
        ]

    def finalize(self, artifacts: Mapping[str, Artifact], *, metadata: dict[str, Any] | None = None) -> None:
        self._client.close()

    # ---------------------------------------------------------------- helpers
    def _resolve_namespace(self, metadata: Mapping[str, Any]) -> str:
        if self._namespace_override:
            return self._namespace_override
        context: PluginContext | None = getattr(self, "plugin_context", None)
        experiment_context = getattr(context, "parent", None)
        suite_context = getattr(experiment_context, "parent", None)
        suite = getattr(suite_context, "plugin_name", metadata.get("suite_name", "suite"))
        experiment = getattr(experiment_context, "plugin_name", metadata.get("experiment", "experiment"))
        level = metadata.get("security_level", getattr(context, "security_level", "unofficial"))
        level = str(level).lower()
        return f"{str(suite).lower()}.{str(experiment).lower()}.{level}"

    def _extract_embedding(self, record: Mapping[str, Any]) -> Sequence[float] | None:
        value = self._extract_value(record, self._embedding_field)
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(item) for item in value]
        raise TypeError(f"Embedding at '{self._embedding_field}' must be a list of floats, got {type(value).__name__}")

    def _extract_metadata(self, record: Mapping[str, Any], run_metadata: Mapping[str, Any]) -> dict[str, Any]:
        extracted: dict[str, Any] = {}
        for field_name in self._metadata_fields:
            value = self._extract_value(record, field_name)
            if value is None:
                lookup_path = field_name
                if field_name.startswith("metadata."):
                    lookup_path = field_name[len("metadata.") :]
                value = self._extract_value(run_metadata, lookup_path)
            if value is not None:
                extracted[field_name] = value
        return extracted

    def _extract_value(self, payload: Mapping[str, Any], path: str) -> Any:
        if not path:
            return None
        parts = path.split(".")
        current: Any = payload
        for part in parts:
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _default_provider_factory(self, provider: str, options: Mapping[str, Any]) -> VectorStoreClient:
        provider = (provider or "").lower()
        if provider == "pgvector":
            dsn = options.get("dsn")
            if not dsn:
                raise ConfigurationError("pgvector provider requires 'dsn' option")
            table = options.get("table")
            if not table:
                raise ConfigurationError("pgvector provider requires 'table' option (e.g., 'elspeth_rag')")
            return PgVectorClient(dsn=dsn, table=table, upsert_conflict=options.get("upsert_conflict", "replace"))
        if provider == "azure_search":
            endpoint = options.get("endpoint")
            index = options.get("index")
            api_key = options.get("api_key")
            if not api_key:
                api_key_env = options.get("api_key_env")
                if not api_key_env:
                    raise ConfigurationError(
                        "azure_search provider requires 'api_key' or 'api_key_env'. "
                        "Provide explicit 'api_key_env' (e.g., 'AZURE_SEARCH_KEY') in configuration."
                    )
                api_key = os.getenv(api_key_env)
            if not endpoint or not index or not api_key:
                raise ConfigurationError("azure_search provider requires 'endpoint', 'index', and API key (via 'api_key' or environment)")

            # Require explicit field configuration for security/audit purposes
            vector_field = options.get("vector_field")
            if not vector_field:
                raise ConfigurationError("azure_search provider requires 'vector_field' (e.g., 'embedding')")
            document_id_field = options.get("id_field")
            if not document_id_field:
                raise ConfigurationError("azure_search provider requires 'id_field' (e.g., 'document_id')")
            namespace_field = options.get("namespace_field")
            if not namespace_field:
                raise ConfigurationError("azure_search provider requires 'namespace_field' (e.g., 'namespace')")

            return AzureSearchVectorClient(
                endpoint=endpoint,
                index=index,
                api_key=api_key,
                vector_field=vector_field,
                document_id_field=document_id_field,
                namespace_field=namespace_field,
            )
        raise ValueError(f"Unsupported embeddings provider '{provider}'")

    def _embed_text(self, text: str) -> Sequence[float]:
        if not self._embed_model:
            raise ConfigurationError("embed_model configuration is required when embeddings are not present in the payload")
        if self._embedder is None:
            self._embedder = self._embedder_factory(self._embed_model)
        return self._embedder.embed(text)

    def _default_embedder_factory(self, config: Mapping[str, Any]) -> Embedder:
        provider = (config.get("provider") or "").lower()
        if provider == "openai":
            return OpenAIEmbedder(model=config.get("model", "text-embedding-3-large"), api_key=config.get("api_key"))
        if provider == "azure_openai":
            deployment_raw = config.get("deployment")
            deployment = str(deployment_raw) if deployment_raw is not None else ""
            endpoint = config.get("endpoint")
            if not endpoint:
                raise ConfigurationError(
                    "azure_openai embed_model requires explicit 'endpoint' configuration. "
                    "Do not rely on AZURE_OPENAI_ENDPOINT environment variable for security/audit purposes."
                )
            return AzureOpenAIEmbedder(
                endpoint=endpoint,
                deployment=deployment,
                api_key=config.get("api_key"),
                api_version=config.get("api_version"),
            )
        raise ValueError(f"Unsupported embed_model provider '{provider}'")
