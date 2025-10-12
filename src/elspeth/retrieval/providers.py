"""Vector store retrieval providers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence

from elspeth.core.validation import ConfigurationError


@dataclass
class QueryResult:
    document_id: str
    text: str
    score: float
    metadata: Dict[str, object]


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
    def __init__(self, *, dsn: str, table: str = "elspeth_rag") -> None:
        try:
            import psycopg  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("psycopg package is required for pgvector retrieval") from exc

        self._psycopg = psycopg
        self._dsn = dsn
        self._table = table

    def query(
        self,
        namespace: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float,
    ) -> Iterable[QueryResult]:
        vector_literal = self._vector_literal(query_vector)
        conn = self._psycopg.connect(self._dsn, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT document_id,
                           contents,
                           metadata::text,
                           1.0 - (embedding <=> %s::vector) AS score
                    FROM {self._table}
                    WHERE namespace = %s
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT %s
                    """,
                    (vector_literal, namespace, vector_literal, top_k),
                )
                for document_id, contents, metadata, score in cur.fetchall():
                    similarity = float(score)
                    if similarity < min_score:
                        continue
                    metadata_payload = {}
                    if metadata:
                        try:
                            metadata_payload = json.loads(metadata)
                        except Exception:  # pragma: no cover - best effort
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
    ) -> None:
        try:
            from azure.core.credentials import AzureKeyCredential  # type: ignore
            from azure.search.documents import SearchClient  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("azure-search-documents package is required for Azure retrieval") from exc

        self._SearchClient = SearchClient
        self._AzureKeyCredential = AzureKeyCredential
        self._client = self._SearchClient(endpoint=endpoint, index_name=index, credential=self._AzureKeyCredential(api_key))
        self._vector_field = vector_field
        self._namespace_field = namespace_field
        self._content_field = content_field

    def query(
        self,
        namespace: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float,
    ) -> Iterable[QueryResult]:
        filter_clause = f"{self._namespace_field} eq '{namespace}'"
        results = self._client.search(
            search_text="",
            filter=filter_clause,
            vector=list(query_vector),
            top_k=top_k,
            vector_fields=self._vector_field,
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
        return PgVectorQueryClient(dsn=dsn, table=options.get("table", "elspeth_rag"))
    if provider == "azure_search":
        endpoint = options.get("endpoint")
        index = options.get("index")
        api_key = options.get("api_key")
        if not api_key:
            api_key = os.getenv(options.get("api_key_env", "AZURE_SEARCH_KEY") or "AZURE_SEARCH_KEY")
        if not endpoint or not index or not api_key:
            raise ConfigurationError("azure_search retriever requires 'endpoint', 'index', and API key")
        return AzureSearchQueryClient(
            endpoint=endpoint,
            index=index,
            api_key=api_key,
            vector_field=options.get("vector_field", "embedding"),
            namespace_field=options.get("namespace_field", "namespace"),
            content_field=options.get("content_field", "contents"),
        )
    raise ValueError(f"Unsupported retriever provider '{provider}'")
