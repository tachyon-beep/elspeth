"""Tests for dependency, commencement gate, and collection probe config models."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from pydantic import ValidationError

from elspeth.core.dependency_config import (
    CollectionProbeConfig,
    CommencementGateConfig,
    DependencyConfig,
    DependencyRunResult,
    GateResult,
)


class TestDependencyConfig:
    def test_valid_config(self) -> None:
        config = DependencyConfig(name="index_corpus", settings="./index.yaml")
        assert config.name == "index_corpus"
        assert config.settings == "./index.yaml"

    def test_frozen(self) -> None:
        config = DependencyConfig(name="x", settings="./x.yaml")
        with pytest.raises(ValidationError):
            config.name = "y"  # type: ignore[misc]

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            DependencyConfig(name="x", settings="./x.yaml", extra="bad")  # type: ignore[call-arg]


class TestCommencementGateConfig:
    def test_valid_config(self) -> None:
        config = CommencementGateConfig(
            name="corpus_ready",
            condition="collections['test']['count'] > 0",
        )
        assert config.name == "corpus_ready"
        assert config.on_fail == "abort"  # default

    def test_on_fail_default_abort(self) -> None:
        config = CommencementGateConfig(name="x", condition="True")
        assert config.on_fail == "abort"

    def test_rejects_invalid_on_fail(self) -> None:
        with pytest.raises(ValidationError):
            CommencementGateConfig(name="x", condition="True", on_fail="warn")  # type: ignore[arg-type]


class TestCollectionProbeConfig:
    def test_valid_config(self) -> None:
        config = CollectionProbeConfig(
            collection="science-facts",
            provider="chroma",
            provider_config={
                "mode": "persistent",
                "persist_directory": "./chroma_data",
            },
        )
        assert config.collection == "science-facts"
        assert config.provider == "chroma"

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            CollectionProbeConfig(
                collection="x",
                provider="chroma",
                provider_config={},
                extra="bad",  # type: ignore[call-arg]
            )


class TestDependencyRunResult:
    def test_construction(self) -> None:
        result = DependencyRunResult(
            name="index_corpus",
            run_id="abc-123",
            settings_hash="sha256:deadbeef",
            duration_ms=4520,
            indexed_at="2026-03-25T14:02:33Z",
        )
        assert result.name == "index_corpus"
        assert result.run_id == "abc-123"
        assert result.indexed_at == "2026-03-25T14:02:33Z"

    def test_frozen(self) -> None:
        result = DependencyRunResult(name="x", run_id="y", settings_hash="z", duration_ms=0, indexed_at="t")
        with pytest.raises(AttributeError):
            result.name = "other"  # type: ignore[misc]


class TestGateResult:
    def test_construction(self) -> None:
        snapshot = {"collections": {"test": {"count": 10, "reachable": True}}}
        result = GateResult(
            name="corpus_ready",
            condition="collections['test']['count'] > 0",
            result=True,
            context_snapshot=snapshot,
        )
        assert result.name == "corpus_ready"
        assert result.result is True

    def test_context_snapshot_is_deep_frozen(self) -> None:
        snapshot = {"collections": {"test": {"count": 10}}}
        result = GateResult(name="x", condition="True", result=True, context_snapshot=snapshot)
        assert isinstance(result.context_snapshot, MappingProxyType)
        # Nested dict should also be frozen
        assert isinstance(result.context_snapshot["collections"], MappingProxyType)

    def test_frozen(self) -> None:
        result = GateResult(name="x", condition="True", result=True, context_snapshot={})
        with pytest.raises(AttributeError):
            result.name = "other"  # type: ignore[misc]
