from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from elspeth.plugins.nodes.sinks.embeddings_store import (
    EmbeddingsStoreSink,
    UpsertResponse,
    VectorRecord,
    VectorStoreClient,
)


class _FakeClient(VectorStoreClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[VectorRecord]]] = []

    def upsert_many(self, namespace: str, records: Iterable[VectorRecord]) -> UpsertResponse:  # noqa: D401
        items = list(records)
        self.calls.append((namespace, items))
        return UpsertResponse(count=len(items), took=0.01, namespace=namespace)

    def close(self) -> None:  # noqa: D401
        return None


class _FakeEmbedder:
    def embed(self, text: str) -> Sequence[float]:  # noqa: D401
        return [1.0, 0.0, 0.5]


def _results(n: int = 2) -> dict[str, Any]:
    return {
        "results": [
            {"row": {"APPID": f"A{i}"}, "response": {"content": f"text-{i}"}} for i in range(n)
        ]
    }


def test_embeddings_store_happy_path(tmp_path: Path) -> None:
    fake_client = _FakeClient()

    def provider_factory(name: str, options: dict[str, Any]) -> VectorStoreClient:  # noqa: D401
        return fake_client

    def embedder_factory(cfg: dict[str, Any]):  # noqa: D401
        return _FakeEmbedder()

    sink = EmbeddingsStoreSink(
        provider="pgvector",
        namespace="ns",
        dsn="postgresql://localhost/db",
        table="t",
        embed_model={"provider": "openai", "model": "text-embedding"},
        provider_factory=provider_factory,
        embedder_factory=embedder_factory,
    )

    sink.write(_results(), metadata={"experiment": "e", "run_id": "r1", "security_level": "INTERNAL", "determinism_level": "guaranteed"})
    artifacts = sink.collect_artifacts()
    assert "embeddings_manifest" in artifacts
    assert fake_client.calls and fake_client.calls[-1][0] == "ns"
    assert fake_client.calls[-1][1], "Expected at least one upsert record"

