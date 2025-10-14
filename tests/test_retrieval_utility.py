from __future__ import annotations

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.plugins.utilities.retrieval import RetrievalContextUtility
from elspeth.retrieval import QueryResult


class StubRetrievalService:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def retrieve(self, namespace: str, query_text: str, *, top_k: int, min_score: float):
        self.calls.append((namespace, query_text, top_k, min_score))
        return [hit for hit in self.hits if hit.score >= min_score]


def _attach_utility_context(plugin, *, security_level: str = "official") -> None:
    suite_ctx = PluginContext(plugin_name="suite", plugin_kind="suite", security_level=security_level)
    experiment_ctx = suite_ctx.derive(plugin_name="experiment", plugin_kind="experiment")
    plugin_ctx = experiment_ctx.derive(plugin_name="retrieval_context", plugin_kind="utility")
    apply_plugin_context(plugin, plugin_ctx)


def test_retrieval_utility_build_payload_with_hits():
    hits = [
        QueryResult(document_id="doc-1", text="Context A", score=0.9, metadata={}),
        QueryResult(document_id="doc-2", text="Context B", score=0.7, metadata={}),
    ]
    service = StubRetrievalService(hits)
    utility = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgresql://example",
        embed_model={"provider": "openai", "model": "irrelevant"},
        service_factory=lambda config: service,
        template="Retrieved context:\n{{ context }}",
        top_k=5,
        min_score=0.5,
    )
    _attach_utility_context(utility)

    payload = utility.build_payload(row={"query": "weather"})

    assert "retrieved_context" in payload
    assert "Context A" in payload["retrieved_context"]
    assert payload["metrics"]["retrieval"]["hits"] == 2
    namespace, query_text, _, _ = service.calls[0]
    assert namespace == "suite.experiment.official"
    assert query_text == "weather"


def test_retrieval_utility_metadata_only_mode():
    hits = [QueryResult(document_id="doc-1", text="Only context", score=0.8, metadata={})]
    service = StubRetrievalService(hits)
    utility = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgresql://example",
        embed_model={"provider": "openai", "model": "irrelevant"},
        service_factory=lambda config: service,
        inject_mode="metadata_only",
        template="Context: {{ context }}",
    )
    _attach_utility_context(utility)

    payload = utility.build_payload(row={"query": "example"})

    assert "retrieved_context" not in payload
    assert payload["metadata"]["retrieved_context"].startswith("Context:")
    assert payload["metrics"]["retrieval"]["hits"] == 1


def test_retrieval_utility_no_hits_returns_metrics_block():
    service = StubRetrievalService([])
    utility = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgresql://example",
        embed_model={"provider": "openai", "model": "irrelevant"},
        service_factory=lambda config: service,
    )
    _attach_utility_context(utility)

    payload = utility.build_payload(row={"query": "absent"})

    assert payload == {"metrics": {"retrieval": {"hits": 0, "namespace": "suite.experiment.official"}}}


def test_retrieval_utility_resolves_query_from_metadata():
    hits = [QueryResult(document_id="doc-1", text="Hit", score=0.6, metadata={})]
    service = StubRetrievalService(hits)
    utility = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgresql://example",
        embed_model={"provider": "openai", "model": "irrelevant"},
        service_factory=lambda config: service,
        query_field="metadata.prompt",
    )
    _attach_utility_context(utility)

    payload = utility.build_payload(row={}, metadata={"prompt": "from metadata"})

    assert payload["metrics"]["retrieval"]["hits"] == 1
    namespace, query_text, _, _ = service.calls[0]
    assert namespace == "suite.experiment.official"
    assert query_text == "from metadata"
