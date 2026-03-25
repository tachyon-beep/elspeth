"""Tests for RAG ingestion error types."""

from __future__ import annotations

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


class TestRetrievalNotReadyError:
    def test_construction_and_message(self) -> None:
        err = RetrievalNotReadyError("RAG transform 'retrieve' requires a populated collection. Collection 'science-facts' is empty")
        assert "science-facts" in str(err)

    def test_is_exception(self) -> None:
        err = RetrievalNotReadyError("test")
        assert isinstance(err, Exception)
