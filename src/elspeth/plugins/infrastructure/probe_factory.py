"""Factory for constructing collection probes from explicit config declarations."""

from __future__ import annotations

from typing import Any

from elspeth.contracts.probes import CollectionProbe, CollectionReadinessResult
from elspeth.core.dependency_config import CollectionProbeConfig


class ChromaCollectionProbe:
    """Probes a ChromaDB collection for readiness.

    Provider config is Tier 3 data (operator-authored YAML), so .get()
    with defaults is appropriate for optional fields like mode and port.
    """

    def __init__(self, collection: str, config: dict[str, Any]) -> None:
        self.collection_name = collection
        self._config = config

    def probe(self) -> CollectionReadinessResult:
        """Check collection existence and document count."""
        try:
            import chromadb

            # Tier 3 boundary — operator-provided config values
            mode = self._config.get("mode", "persistent")
            if mode == "persistent":
                client = chromadb.PersistentClient(path=self._config["persist_directory"])
            else:
                client = chromadb.HttpClient(
                    host=self._config["host"],
                    port=self._config.get("port", 8000),
                    ssl=self._config.get("ssl", True),
                )

            try:
                collection = client.get_collection(self.collection_name)
                count = collection.count()
                return CollectionReadinessResult(
                    collection=self.collection_name,
                    reachable=True,
                    count=count,
                    message=(
                        f"Collection '{self.collection_name}' has {count} documents"
                        if count > 0
                        else f"Collection '{self.collection_name}' is empty"
                    ),
                )
            except Exception:
                return CollectionReadinessResult(
                    collection=self.collection_name,
                    reachable=True,
                    count=0,
                    message=f"Collection '{self.collection_name}' not found",
                )
        except Exception:
            return CollectionReadinessResult(
                collection=self.collection_name,
                reachable=False,
                count=0,
                message=f"Collection '{self.collection_name}' unreachable",
            )


_PROBE_REGISTRY: dict[str, type] = {
    "chroma": ChromaCollectionProbe,
}


def build_collection_probes(
    configs: list[CollectionProbeConfig],
) -> list[CollectionProbe]:
    """Construct probes from explicit config declarations."""
    probes: list[CollectionProbe] = []
    for config in configs:
        probe_cls = _PROBE_REGISTRY.get(config.provider)
        if probe_cls is None:
            raise ValueError(f"Unknown collection probe provider: {config.provider!r}. Available: {sorted(_PROBE_REGISTRY)}")
        probes.append(probe_cls(config.collection, config.provider_config))
    return probes
