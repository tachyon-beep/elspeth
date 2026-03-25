"""Tests for RAG ingestion error types."""

from __future__ import annotations

from types import MappingProxyType

from elspeth.contracts.errors import (
    CommencementGateFailedError,
    DependencyFailedError,
    RetrievalNotReadyError,
)


class TestDependencyFailedError:
    def test_construction_and_message(self) -> None:
        err = DependencyFailedError(
            dependency_name="index_corpus",
            run_id="abc-123",
            reason="Source file not found",
        )
        assert "index_corpus" in str(err)
        assert "abc-123" in str(err)
        assert err.dependency_name == "index_corpus"
        assert err.run_id == "abc-123"
        assert err.reason == "Source file not found"

    def test_is_exception(self) -> None:
        err = DependencyFailedError(dependency_name="x", run_id="y", reason="z")
        assert isinstance(err, Exception)


class TestCommencementGateFailedError:
    def test_construction_and_message(self) -> None:
        snapshot = {"collections": {"test": {"count": 0, "reachable": True}}}
        err = CommencementGateFailedError(
            gate_name="corpus_ready",
            condition="collections['test']['count'] > 0",
            reason="Condition evaluated to falsy",
            context_snapshot=snapshot,
        )
        assert "corpus_ready" in str(err)
        assert err.gate_name == "corpus_ready"
        assert err.condition == "collections['test']['count'] > 0"
        assert err.context_snapshot == snapshot

    def test_is_exception(self) -> None:
        err = CommencementGateFailedError(
            gate_name="x",
            condition="True",
            reason="z",
            context_snapshot={},
        )
        assert isinstance(err, Exception)

    def test_context_snapshot_is_deeply_frozen(self) -> None:
        """context_snapshot must be frozen — it's named 'snapshot' so it must snapshot."""
        original = {"collections": {"test": {"count": 0, "reachable": True}}}
        err = CommencementGateFailedError(
            gate_name="g",
            condition="True",
            reason="r",
            context_snapshot=original,
        )
        # Outer dict is frozen
        assert isinstance(err.context_snapshot, MappingProxyType)
        # Nested dict is also frozen
        assert isinstance(err.context_snapshot["collections"], MappingProxyType)
        assert isinstance(err.context_snapshot["collections"]["test"], MappingProxyType)

    def test_context_snapshot_mutation_isolated(self) -> None:
        """Mutating the original dict after construction must not affect the error."""
        original: dict = {"key": {"nested": 1}}
        err = CommencementGateFailedError(
            gate_name="g",
            condition="True",
            reason="r",
            context_snapshot=original,
        )
        original["key"]["nested"] = 999
        original["new_key"] = "injected"
        assert err.context_snapshot["key"]["nested"] == 1
        assert "new_key" not in err.context_snapshot


class TestRetrievalNotReadyError:
    def test_construction_and_message(self) -> None:
        err = RetrievalNotReadyError(
            collection="science-facts",
            reason="Collection is empty",
        )
        assert "science-facts" in str(err)
        assert err.collection == "science-facts"
        assert err.reason == "Collection is empty"

    def test_is_exception(self) -> None:
        err = RetrievalNotReadyError(collection="test", reason="unreachable")
        assert isinstance(err, Exception)
