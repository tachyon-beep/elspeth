"""Tests for collection probe factory."""

from __future__ import annotations

import pytest

from elspeth.contracts.probes import CollectionProbe
from elspeth.core.dependency_config import CollectionProbeConfig
from elspeth.plugins.infrastructure.probe_factory import build_collection_probes


class TestBuildCollectionProbes:
    def test_builds_chroma_probe(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="test",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./data"},
            )
        ]
        probes = build_collection_probes(configs)
        assert len(probes) == 1
        assert isinstance(probes[0], CollectionProbe)
        assert probes[0].collection_name == "test"

    def test_empty_configs_returns_empty(self) -> None:
        assert build_collection_probes([]) == []

    def test_unknown_provider_raises(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="test",
                provider="unknown_provider",
                provider_config={},
            )
        ]
        with pytest.raises(ValueError, match="unknown_provider"):
            build_collection_probes(configs)

    def test_multiple_probes(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="a",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./a"},
            ),
            CollectionProbeConfig(
                collection="b",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./b"},
            ),
        ]
        probes = build_collection_probes(configs)
        assert len(probes) == 2
        assert probes[0].collection_name == "a"
        assert probes[1].collection_name == "b"
