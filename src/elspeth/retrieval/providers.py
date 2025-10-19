"""Vector store retrieval providers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from elspeth.core.security import validate_azure_search_endpoint
from elspeth.core.validation.base import ConfigurationError


@dataclass
class QueryResult:
    document_id: str
    text: str
    score: float
    metadata: dict[str, object]


class VectorQueryClient:
    """Abstract similarity search client."""

    def query(
        self,
        namespace: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float,
    ) -> Iterable[QueryResult]:  # pragma: no cover - interface
        raise NotImplementedError


class PgVectorQueryClient(VectorQueryClient):
    def __init__(self, *, dsn: str, table: str = "elspeth_rag", connect_timeout: float | int | None = None) -> None:
        # Defer importing psycopg until query() is executed. This makes unit tests
        # that only validate DSN handling independent from system libpq availability.
        self._psycopg: Any = None
        self._sql: Any = None
        self._dsn = dsn
        self._table = table
        self._connect_timeout = int(connect_timeout) if connect_timeout is not None else None
        self._logger = logging.getLogger(__name__)

    def query(
        self,
        namespace: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float,
    ) -> Iterable[QueryResult]:
        # Import psycopg here to allow initialization without libpq in minimal test envs.
        if self._psycopg is None and self._sql is None:  # pragma: no cover - trivial path
            try:
                import psycopg
            except Exception as exc:  # pragma: no cover - environment missing psycopg
                raise RuntimeError("psycopg unavailable; cannot perform pgvector queries") from exc
            self._psycopg = psycopg
            try:
                from psycopg import sql

                self._sql = sql
            except Exception:
                # Keep self._sql = None; downstream will refuse raw SQL fallback
                self._sql = None

        vector_literal = self._vector_literal(query_vector)
        dsn = self._dsn
        if self._connect_timeout is not None:
            # Append connect_timeout to DSN for both URI and key-value DSN styles
            try:
                if "://" in dsn:
                    parsed = urlparse(dsn)
                    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
                    q["connect_timeout"] = str(self._connect_timeout)
                    new_query = urlencode(q, doseq=True)
                    dsn = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
                else:
                    # libpq key-value DSN: append as space-delimited parameter
                    sep = " " if dsn and not dsn.endswith(" ") else ""
                    dsn = f"{dsn}{sep}connect_timeout={self._connect_timeout}"
            except Exception:
                # Fallback to safe whitespace-delimited append
                sep = " " if dsn and not dsn.endswith(" ") else ""
                dsn = f"{dsn}{sep}connect_timeout={self._connect_timeout}"
        conn = self._psycopg.connect(dsn, autocommit=True)
        try:
            # Use sql.Identifier to safely quote table name and prevent SQL injection
            with conn.cursor() as cur:
                if self._sql is not None:
                    query_sql = self._sql.SQL("""
                        SELECT document_id,
                               contents,
                               metadata::text,
                               1.0 - (embedding <=> %s::vector) AS score
                        FROM {}
                        WHERE namespace = %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT %s
                        """).format(self._sql.Identifier(self._table))
                    args = (vector_literal, namespace, vector_literal, top_k)
                else:
                    # Disallow raw SQL fallback to avoid injection risks if psycopg.sql isn't available
                    raise RuntimeError("psycopg.sql unavailable; refusing to execute raw SQL fallback")
                cur.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    query_sql,
                    args,
                )
                for document_id, contents, metadata, score in cur.fetchall():
                    similarity = float(score)
                    if similarity < min_score:
                        continue
                    metadata_payload = {}
                    if metadata:
                        try:
                            metadata_payload = json.loads(metadata)
                        except (json.JSONDecodeError, TypeError) as exc:  # pragma: no cover - best effort
                            self._logger.debug("Failed to parse metadata JSON for document_id=%s: %s", document_id, exc)
                            metadata_payload = {}
                    yield QueryResult(
                        document_id=document_id,
                        text=contents or "",
                        score=similarity,
                        metadata=metadata_payload,
                    )
        finally:
            conn.close()

    def _vector_literal(self, vector: Sequence[float]) -> str:
        values = ",".join(f"{float(value):.12g}" for value in vector)
        return f"[{values}]"


class AzureSearchQueryClient(VectorQueryClient):
    def __init__(
        self,
        *,
        endpoint: str,
        index: str,
        api_key: str,
        vector_field: str = "embedding",
        namespace_field: str = "namespace",
        content_field: str = "contents",
        request_timeout: float | int | None = None,
    ) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        self._SearchClient = SearchClient
        self._AzureKeyCredential = AzureKeyCredential
        self._client = self._SearchClient(endpoint=endpoint, index_name=index, credential=self._AzureKeyCredential(api_key))
        self._vector_field = vector_field
        self._namespace_field = namespace_field
        self._content_field = content_field
        self._timeout = float(request_timeout) if request_timeout is not None else None

    def query(
        self,
        namespace: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float,
    ) -> Iterable[QueryResult]:
        filter_clause = f"{self._namespace_field} eq '{namespace}'"
        search_kwargs: dict[str, Any] = {}
        if self._timeout is not None:
            search_kwargs["timeout"] = self._timeout
        results = self._client.search(
            search_text="",
            filter=filter_clause,
            vector=list(query_vector),
            top_k=top_k,
            vector_fields=self._vector_field,
            **search_kwargs,
        )
        for doc in results:
            score = float(getattr(doc, "@search.score", 0.0))
            if score < min_score:
                continue
            metadata = doc.get("metadata", {}) or {}
            text = doc.get(self._content_field, "")
            yield QueryResult(
                document_id=doc.get("document_id", ""),
                text=text or "",
                score=score,
                metadata=metadata,
            )


def create_query_client(provider: str, options: Mapping[str, Any]) -> VectorQueryClient:
    provider = (provider or "").lower()
    if provider == "pgvector":
        dsn = options.get("dsn")
        if not dsn:
            raise ConfigurationError("pgvector retriever requires 'dsn'")
        table = options.get("table")
        if not table:
            raise ConfigurationError("pgvector retriever requires 'table' (e.g., 'elspeth_rag')")
        return PgVectorQueryClient(dsn=dsn, table=table)
    if provider == "azure_search":
        endpoint = options.get("endpoint")
        index = options.get("index")
        api_key = options.get("api_key")
        if not api_key:
            api_key_env = options.get("api_key_env")
            if not api_key_env:
                raise ConfigurationError(
                    "azure_search retriever requires 'api_key' or 'api_key_env'. "
                    "Provide explicit 'api_key_env' (e.g., 'AZURE_SEARCH_KEY') in configuration."
                )
            api_key = os.getenv(api_key_env)
        if not endpoint or not index or not api_key:
            raise ConfigurationError("azure_search retriever requires 'endpoint', 'index', and API key")

        try:
            validate_azure_search_endpoint(endpoint)
        except ValueError as exc:
            raise ConfigurationError(f"azure_search retriever endpoint validation failed: {exc}") from exc

        # Require explicit field configuration for security/audit purposes
        vector_field = options.get("vector_field")
        if not vector_field:
            raise ConfigurationError("azure_search retriever requires 'vector_field' (e.g., 'embedding')")
        namespace_field = options.get("namespace_field")
        if not namespace_field:
            raise ConfigurationError("azure_search retriever requires 'namespace_field' (e.g., 'namespace')")
        content_field = options.get("content_field")
        if not content_field:
            raise ConfigurationError("azure_search retriever requires 'content_field' (e.g., 'contents')")

        return AzureSearchQueryClient(
            endpoint=endpoint,
            index=index,
            api_key=api_key,
            vector_field=vector_field,
            namespace_field=namespace_field,
            content_field=content_field,
            request_timeout=options.get("request_timeout") or options.get("timeout"),
        )
    raise ValueError(f"Unsupported retriever provider '{provider}'")
