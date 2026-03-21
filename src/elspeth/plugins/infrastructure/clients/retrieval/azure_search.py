"""Azure AI Search provider for RAG retrieval."""

from __future__ import annotations

import json
import math
import re
import urllib.parse
from typing import TYPE_CHECKING, Any, Literal, Self, cast

import structlog
from pydantic import BaseModel, field_validator, model_validator

from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.core.rate_limit.limiter import RateLimiter
    from elspeth.core.rate_limit.registry import NoOpLimiter
    from elspeth.plugins.infrastructure.clients.base import TelemetryEmitCallback


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


# Score normalization ranges per search mode.
_SCORE_RANGES: dict[str, tuple[float, float]] = {
    "keyword": (0.0, 50.0),
    "vector": (0.0, 1.0),
    "hybrid": (0.0, 50.0),
    "semantic": (0.0, 4.0),
}


class AzureSearchProvider:
    """Azure AI Search implementation of RetrievalProvider.

    Constructs a per-call AuditedHTTPClient scoped to each row's state_id.
    """

    def __init__(
        self,
        config: AzureSearchProviderConfig,
        *,
        recorder: LandscapeRecorder,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
        limiter: RateLimiter | NoOpLimiter | None = None,
    ) -> None:
        self._config = config
        self._recorder = recorder
        self._run_id = run_id
        self._telemetry_emit = telemetry_emit
        self._limiter = limiter

        self._search_url = f"{config.endpoint.rstrip('/')}/indexes/{config.index}/docs/search?api-version={config.api_version}"
        self._score_range = _SCORE_RANGES[config.search_mode]

    def search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        *,
        state_id: str,
        token_id: str | None,
    ) -> list[RetrievalChunk]:
        response_data = self._execute_search(query, top_k, state_id=state_id, token_id=token_id)
        chunks, skipped_items = self._parse_response(response_data, min_score)
        # "Record what we didn't get" — skipped items are audit evidence
        if skipped_items:
            structlog.get_logger(__name__).debug(
                "azure_search_skipped_items",
                state_id=state_id,
                skipped=skipped_items,
                skipped_count=len(skipped_items),
            )
        return chunks

    def _execute_search(
        self,
        query: str,
        top_k: int,
        *,
        state_id: str,
        token_id: str | None,
    ) -> dict[str, Any]:
        from elspeth.plugins.infrastructure.clients.http import AuditedHTTPClient

        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["api-key"] = self._config.api_key

        body = self._build_request_body(query, top_k)

        http_client = AuditedHTTPClient(
            recorder=self._recorder,
            state_id=state_id,
            run_id=self._run_id,
            telemetry_emit=self._telemetry_emit,
            timeout=self._config.request_timeout,
            limiter=self._limiter,
            token_id=token_id,
            headers=headers,
        )
        try:
            response = http_client.post(self._search_url, json=body)

            status_code = response.status_code
            if status_code in (401, 403):
                raise RetrievalError(
                    f"Authentication failed for {self._config.endpoint} index {self._config.index!r}: HTTP {status_code}",
                    retryable=False,
                    status_code=status_code,
                )
            if status_code == 429:
                raise RetrievalError("Rate limited by Azure AI Search", retryable=True, status_code=429)
            if status_code >= 500:
                raise RetrievalError(f"Azure AI Search server error: HTTP {status_code}", retryable=True, status_code=status_code)
            if status_code >= 400:
                raise RetrievalError(f"Azure AI Search client error: HTTP {status_code}", retryable=False, status_code=status_code)

            try:
                return cast(dict[str, Any], response.json())
            except (json.JSONDecodeError, ValueError) as exc:
                raise RetrievalError(f"Malformed JSON response from Azure AI Search: {exc}", retryable=False) from exc
        except RetrievalError:
            raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise RetrievalError(f"Search request failed: {exc}", retryable=True) from exc
        finally:
            http_client.close()

    def _build_request_body(self, query: str, top_k: int) -> dict[str, Any]:
        body: dict[str, Any] = {"top": top_k}
        mode = self._config.search_mode

        if mode in ("keyword", "hybrid"):
            body["search"] = query
        if mode in ("vector", "hybrid"):
            body["vectorQueries"] = [
                {
                    "kind": "text",
                    "text": query,
                    "fields": self._config.vector_field,
                    "k": top_k,
                }
            ]
        if mode == "semantic":
            body["search"] = query
            body["queryType"] = "semantic"
            body["semanticConfiguration"] = self._config.semantic_config

        return body

    def _parse_response(self, response_data: dict[str, Any], min_score: float) -> tuple[list[RetrievalChunk], list[dict[str, Any]]]:
        if "value" not in response_data:
            raise RetrievalError("Azure AI Search response missing 'value' array", retryable=False)

        results = response_data["value"]
        chunks: list[RetrievalChunk] = []
        # Track items skipped at Tier 3 boundary — "record what we didn't get"
        skipped_items: list[dict[str, Any]] = []

        for item in results:
            raw_score = item.get("@search.score")
            if raw_score is None:
                skipped_items.append({"reason": "missing_score", "id": item.get("id")})
                continue

            normalized_score = self._normalize_score(raw_score)
            if normalized_score < min_score:
                continue

            content = item.get("content")
            if content is None:
                skipped_items.append({"reason": "missing_content", "id": item.get("id")})
                continue
            if not content:
                skipped_items.append({"reason": "empty_content", "id": item.get("id")})
                continue

            source_id = item.get("id") or item.get("@search.documentId")
            if source_id is None:
                # No identifier available — skip rather than fabricate "unknown".
                # "record what we didn't get": absence is captured by the count
                # gap between results returned and chunks emitted.
                skipped_items.append({"reason": "missing_id", "keys": list(item.keys())})
                continue

            metadata: dict[str, Any] = {
                k: str(v) if not isinstance(v, (str, int, float, bool, type(None), list, dict)) else v
                for k, v in item.items()
                if k not in ("@search.score", "content", "id")
            }

            try:
                chunks.append(
                    RetrievalChunk(
                        content=content,
                        score=normalized_score,
                        source_id=str(source_id),
                        metadata=metadata,
                    )
                )
            except ValueError as exc:
                raise RetrievalError(f"Provider returned invalid data: {exc}", retryable=False) from exc

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks, skipped_items

    def _normalize_score(self, raw_score: float) -> float:
        if not math.isfinite(raw_score):
            raise RetrievalError(
                f"Azure AI Search returned non-finite score: {raw_score!r}. "
                f"This indicates a malformed API response (Tier 3 boundary violation).",
                retryable=False,
            )
        min_val, max_val = self._score_range
        if max_val <= min_val:
            return 0.0
        normalized = (raw_score - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    def close(self) -> None:
        pass
