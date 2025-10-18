from dataclasses import dataclass
from typing import Iterable, Mapping

import pytest

from elspeth.plugins.utilities.retrieval import RetrievalContextUtility, _build_provider_options
from elspeth.core.validation.base import ConfigurationError
from elspeth.core.base.plugin_context import PluginContext


@dataclass
class _Hit:
    document_id: str
    score: float
    text: str


class _FakeRetrievalService:
    def __init__(self, hits: list[_Hit]):
        self._hits = hits

    def retrieve(self, namespace: str, query: str, *, top_k: int, min_score: float) -> Iterable[_Hit]:  # noqa: ARG002
        return [h for h in self._hits if h.score >= min_score][:top_k]


def _factory(_: Mapping[str, object]) -> _FakeRetrievalService:
    hits = [_Hit(document_id="d1", score=0.9, text="A"), _Hit(document_id="d2", score=0.5, text="B")]
    return _FakeRetrievalService(hits)


def test_build_provider_options_pgvector_requires_dsn():
    with pytest.raises(ConfigurationError):
        _build_provider_options("pgvector", dsn=None, table="t", extra=None)
    assert _build_provider_options("pgvector", dsn="postgres://", table="t", extra=None)["dsn"].startswith("postgres")


def test_retrieval_context_payload_append_and_metadata_only():
    util = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgres://",
        service_factory=_factory,
        inject_mode="prompt_append",
        query_field="metadata.q",
        min_score=0.6,
    )

    payload = util.build_payload(row={}, responses={}, metadata={"q": "hello", "security_level": "OFFICIAL"})
    assert payload["metrics"]["retrieval"]["hits"] == 1
    assert "retrieved_context" in payload

    util2 = RetrievalContextUtility(
        provider="pgvector",
        dsn="postgres://",
        service_factory=_factory,
        inject_mode="metadata_only",
        query_field="metadata.q",
        min_score=0.0,
    )
    payload2 = util2.build_payload(row={}, responses={}, metadata={"q": "hello", "security_level": "OFFICIAL"})
    assert payload2["metrics"]["retrieval"]["hits"] == 2
    # context placed under metadata
    assert "retrieved_context" in payload2.get("metadata", {})


def test_retrieval_context_no_query_returns_empty():
    util = RetrievalContextUtility(provider="pgvector", dsn="postgres://", service_factory=_factory, query_field="")
    assert util.build_payload(row={}, responses={}, metadata={}) == {}


def test_namespace_resolution_with_context_and_metadata():
    util = RetrievalContextUtility(provider="pgvector", dsn="postgres://", service_factory=_factory, query_field="row.q")
    # Build nested parent contexts to populate suite/experiment names
    suite_ctx = PluginContext(plugin_name="mysuite", plugin_kind="suite", security_level="OFFICIAL", determinism_level="low", provenance=("root",))
    exp_ctx = suite_ctx.derive(plugin_name="myexp", plugin_kind="experiment")
    util_ctx = exp_ctx.derive(plugin_name="retrieval_context", plugin_kind="utility")
    util.plugin_context = util_ctx  # attach like registry does
    payload = util.build_payload(row={"q": "hello"}, responses={}, metadata={"security_level": "OFFICIAL"})
    ns = payload.get("metrics", {}).get("retrieval", {}).get("namespace")
    assert ns and ns.startswith("mysuite.myexp.OFFICIAL")
