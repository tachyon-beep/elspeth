"""Utility plugin for retrieval-augmented context lookups."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.utility import register_utility_plugin
from elspeth.core.validation.base import ConfigurationError
from elspeth.retrieval import RetrievalService, create_retrieval_service

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = "Retrieved context:\n{{ context }}"


class RetrievalContextUtility:
    """General-purpose retrieval helper for day-to-day prompt enrichment."""

    name = "retrieval_context"

    def __init__(
        self,
        *,
        provider: str,
        namespace: str | None = None,
        dsn: str | None = None,
        table: str = "elspeth_rag",
        query_field: str = "query",
        inject_mode: str = "prompt_append",
        template: str = DEFAULT_TEMPLATE,
        top_k: int = 5,
        min_score: float = 0.0,
        embed_model: Mapping[str, Any] | None = None,
        provider_options: Mapping[str, Any] | None = None,
        service_factory: Callable[[Mapping[str, Any]], RetrievalService] | None = None,
    ) -> None:
        self.provider_name = provider
        self._namespace_override = namespace
        self._query_field = query_field or ""
        self._inject_mode = inject_mode or "prompt_append"
        self._template = template or DEFAULT_TEMPLATE
        self._top_k = max(int(top_k), 1)
        self._min_score = float(min_score)
        self._service = (service_factory or create_retrieval_service)(
            {
                "provider": provider,
                "provider_options": _build_provider_options(provider, dsn=dsn, table=table, extra=provider_options),
                "embed_model": embed_model or {},
            }
        )

    # ------------------------------------------------------------------ public
    def build_payload(
        self,
        *,
        query_text: str | None = None,
        namespace: str | None = None,
        row: Mapping[str, Any] | None = None,
        responses: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve context and format payload for downstream consumers."""

        row = row or {}
        responses = responses or {}
        metadata = metadata or {}

        resolved_query = query_text or self._extract_query(row, responses, metadata)
        if not resolved_query:
            logger.debug("RetrievalContextUtility[name=%s]: no query text resolved", self.name)
            return {}

        resolved_namespace = namespace or self._resolve_namespace(row, metadata)
        hits = list(self._service.retrieve(resolved_namespace, resolved_query, top_k=self._top_k, min_score=self._min_score))
        if not hits:
            return {"metrics": {"retrieval": {"hits": 0, "namespace": resolved_namespace}}}

        context_block = "\n\n".join(hit.text for hit in hits)
        rendered_context = self._template.replace("{{ context }}", context_block)

        payload: dict[str, Any] = {
            "retrieval_metadata": {
                "namespace": resolved_namespace,
                "hits": [
                    {
                        "document_id": hit.document_id,
                        "score": hit.score,
                    }
                    for hit in hits
                ],
            },
            "metrics": {
                "retrieval": {
                    "hits": len(hits),
                    "namespace": resolved_namespace,
                    "min_score": self._min_score,
                }
            },
        }

        mode = (self._inject_mode or "prompt_append").lower()
        if mode == "prompt_append":
            payload["retrieved_context"] = rendered_context
        elif mode == "metadata_only":
            payload.setdefault("metadata", {})["retrieved_context"] = rendered_context

        return payload

    # ------------------------------------------------------------------ helpers
    def _extract_query(
        self,
        row: Mapping[str, Any],
        responses: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> str | None:
        """Determine the query text from explicit args, row payload, or responses."""

        value = self._extract_from_scope(self._query_field, row=row, responses=responses, metadata=metadata)
        if value:
            return str(value)

        default_response = responses.get("default")
        if isinstance(default_response, Mapping):
            content = default_response.get("content")
            if content:
                return str(content)
        return None

    def _resolve_namespace(self, row: Mapping[str, Any], metadata: Mapping[str, Any]) -> str:
        if self._namespace_override:
            return self._namespace_override
        context: PluginContext | None = getattr(self, "plugin_context", None)
        # Security level casing policy:
        # - If provided explicitly in metadata, preserve the caller's casing to reflect
        #   the external label (e.g., "OFFICIAL").
        # - When derived from plugin context, normalize to lowercase for namespacing stability
        #   (avoids collisions across aliases and canonical enum values).
        if "security_level" in metadata:
            level_meta = metadata.get("security_level")
            if isinstance(level_meta, SecurityLevel):
                level = level_meta.value
            else:
                level = str(level_meta)
        else:
            level_ctx = getattr(context, "security_level", "unofficial")
            if isinstance(level_ctx, SecurityLevel):
                level = level_ctx.value.lower()
            else:
                level = str(level_ctx).lower()
        experiment_context = getattr(context, "parent", None)
        suite_context = getattr(experiment_context, "parent", None)
        experiment = metadata.get("experiment") or getattr(experiment_context, "plugin_name", None) or row.get("experiment", "experiment")
        suite = metadata.get("suite_name") or getattr(suite_context, "plugin_name", None) or row.get("suite_name", "suite")
        return f"{suite}.{experiment}.{level}"

    def _extract_from_scope(
        self,
        path: str,
        *,
        row: Mapping[str, Any],
        responses: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> Any:
        if not path:
            return None

        scope, remainder = self._split_scope(path)
        if scope == "row":
            return self._extract_path(row, remainder)
        if scope == "responses":
            return self._extract_path(responses, remainder)
        if scope == "metadata":
            return self._extract_path(metadata, remainder)
        if scope == "response":
            return self._extract_path(responses.get("default", {}), remainder)
        # No explicit scope, try row first then metadata.
        value = self._extract_path(row, path)
        if value is not None:
            return value
        return self._extract_path(metadata, path)

    def _split_scope(self, path: str) -> tuple[str, str]:
        if "." not in path:
            return "", path
        prefix, remainder = path.split(".", 1)
        if prefix in {"row", "responses", "metadata", "response"}:
            return prefix, remainder
        return "", path

    def _extract_path(self, payload: Mapping[str, Any], path: str) -> Any:
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


def _build_provider_options(
    provider: str,
    *,
    dsn: str | None,
    table: str,
    extra: Mapping[str, Any] | None,
) -> dict[str, Any]:
    options: dict[str, Any] = dict(extra or {})
    provider = (provider or "").lower()
    if provider == "pgvector":
        options.setdefault("dsn", dsn)
        options.setdefault("table", table)
        if not options.get("dsn"):
            raise ConfigurationError("pgvector retriever requires a 'dsn'")
    return options


register_utility_plugin(
    "retrieval_context",
    lambda options, context: RetrievalContextUtility(
        provider=options["provider"],
        namespace=options.get("namespace"),
        dsn=options.get("dsn"),
        table=options.get("table", "elspeth_rag"),
        query_field=options.get("query_field", "row.query"),
        inject_mode=options.get("inject_mode", "prompt_append"),
        template=options.get("template", DEFAULT_TEMPLATE),
        top_k=options.get("top_k", 5),
        min_score=options.get("min_score", 0.0),
        embed_model=options.get("embed_model"),
        provider_options={
            key: options.get(key)
            for key in (
                "endpoint",
                "index",
                "api_key",
                "api_key_env",
                "vector_field",
                "namespace_field",
                "content_field",
            )
            if options.get(key) is not None
        },
    ),
    schema={
        "type": "object",
        "properties": {
            "provider": {"type": "string"},
            "namespace": {"type": "string"},
            "dsn": {"type": "string"},
            "table": {"type": "string"},
            "query_field": {"type": "string"},
            "inject_mode": {"type": "string", "enum": ["prompt_append", "metadata_only", "none"]},
            "template": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1},
            "min_score": {"type": "number"},
            "embed_model": {"type": "object"},
            "endpoint": {"type": "string"},
            "index": {"type": "string"},
            "api_key": {"type": "string"},
            "api_key_env": {"type": "string"},
            "vector_field": {"type": "string"},
            "namespace_field": {"type": "string"},
            "content_field": {"type": "string"},
            "security_level": {"type": "string"},
        },
        "required": ["provider", "embed_model"],
        "additionalProperties": True,
    },
)


__all__ = ["RetrievalContextUtility"]
