from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from elspeth.core.pipeline.artifact_pipeline import ArtifactPipeline, SinkBinding
from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink


class DummySink(ResultSink):
    def __init__(
        self,
        name: str,
        produced: list[ArtifactDescriptor] | None = None,
        consumed: list[str] | None = None,
        log: list[str] | None = None,
        produced_artifacts: Dict[str, Artifact] | None = None,
        security_level: str | None = None,
        on_error: str = "abort",
        capture_consumed: bool = False,
    ):
        self.name = name
        self.calls: list[str] = []
        self._produced = produced or []
        self._consumed = consumed or []
        self.log = log
        self._produced_artifacts = produced_artifacts or {}
        self.on_error = on_error
        self._elspeth_security_level = security_level
        self.capture_consumed = capture_consumed
        self.prepared_artifacts: list[Dict[str, list[Dict[str, Any]]]] = []

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
        self.calls.append(self.name)
        if self.log is not None:
            self.log.append(self.name)

    def produces(self) -> list[ArtifactDescriptor]:
        return self._produced

    def consumes(self) -> list[str]:
        return self._consumed

    def collect_artifacts(self) -> Dict[str, Artifact]:
        return self._produced_artifacts

    def prepare_artifacts(self, artifacts: Dict[str, list[Artifact]]) -> None:
        if self.capture_consumed:
            snapshot: Dict[str, list[Dict[str, Any]]] = {}
            for token, values in artifacts.items():
                snapshot[token] = [
                    {
                        "id": artifact.id,
                        "type": artifact.type,
                        "security_level": artifact.security_level,
                        "produced_by": artifact.produced_by,
                    }
                    for artifact in values
                ]
            self.prepared_artifacts.append(snapshot)


def binding_for(
    index: int,
    sink: ResultSink,
    *,
    artifacts: Dict[str, Any] | None = None,
    security_level: str | None = "official",
) -> SinkBinding:
    return SinkBinding(
        id=f"{sink.__class__.__name__}:{index}",
        plugin="dummy",
        sink=sink,
        artifact_config=artifacts or {},
        original_index=index,
        security_level=security_level,
    )


def test_pipeline_requires_security_level():
    sink = DummySink("missing_security")
    with pytest.raises(ValueError, match="must declare a security_level"):
        ArtifactPipeline([binding_for(0, sink, security_level=None)])


def test_pipeline_preserves_order_without_artifacts():
    a = DummySink("a")
    b = DummySink("b")
    pipeline = ArtifactPipeline([binding_for(0, a), binding_for(1, b)])
    pipeline.execute({"results": []}, {})
    assert a.calls == ["a"]
    assert b.calls == ["b"]
    assert len(a.calls) == 1 and len(b.calls) == 1


def test_pipeline_orders_by_consumes_alias():
    execution_log: list[str] = []
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="csv", type="file/csv")],
        log=execution_log,
    )
    consumer = DummySink("consumer", consumed=["@csv"], log=execution_log)
    pipeline = ArtifactPipeline([binding_for(0, consumer), binding_for(1, producer)])
    pipeline.execute({"results": []}, {})
    assert execution_log == ["producer", "consumer"]


def test_pipeline_orders_by_consumes_type():
    execution_log: list[str] = []
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="xlsx", type="file/xlsx")],
        log=execution_log,
    )
    consumer = DummySink("consumer", consumed=["file/xlsx"], log=execution_log)
    pipeline = ArtifactPipeline([binding_for(0, producer), binding_for(1, consumer)])
    pipeline.execute({"results": []}, {})
    assert execution_log == ["producer", "consumer"]


def test_pipeline_detects_cycles():
    one = DummySink("one", consumed=["@two"], produced=[ArtifactDescriptor(name="one", type="file/csv")])
    two = DummySink("two", consumed=["@one"], produced=[ArtifactDescriptor(name="two", type="file/json")])

    with pytest.raises(ValueError):
        ArtifactPipeline([binding_for(0, one), binding_for(1, two)])


def test_pipeline_mode_all():
    log: list[str] = []
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="csv", type="file/csv")],
        log=log,
    )
    consumer = DummySink(
        "consumer",
        consumed=[{"token": "file/csv", "mode": "all"}],
        log=log,
    )
    pipeline = ArtifactPipeline([binding_for(0, producer), binding_for(1, consumer)])
    pipeline.execute({"results": []}, {})
    assert log == ["producer", "consumer"]


def test_pipeline_denies_insufficient_security():
    artifact = Artifact(
        id="",
        type="file/csv",
        path=None,
        persist=True,
        security_level="SECRET",
    )
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="csv", type="file/csv")],
        produced_artifacts={"csv": artifact},
        security_level="SECRET",
    )
    consumer = DummySink(
        "consumer",
        consumed=[{"token": "file/csv", "mode": "all"}],
        security_level="official",
    )
    with pytest.raises(PermissionError):
        ArtifactPipeline(
            [
                binding_for(0, producer, security_level="SECRET"),
                binding_for(1, consumer, security_level="official"),
            ]
        )


def test_pipeline_skip_setting_still_raises_on_security():
    artifact = Artifact(
        id="",
        type="file/csv",
        path=None,
        persist=True,
        security_level="SECRET",
    )
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="csv", type="file/csv")],
        produced_artifacts={"csv": artifact},
        security_level="SECRET",
    )
    consumer = DummySink(
        "consumer",
        consumed=[{"token": "file/csv", "mode": "all"}],
        security_level="official",
        on_error="skip",
    )
    with pytest.raises(PermissionError):
        ArtifactPipeline(
            [
                binding_for(0, producer, security_level="SECRET"),
                binding_for(1, consumer, security_level="official"),
            ]
        )


def test_pipeline_golden_snapshot():
    execution_log: list[str] = []
    producer = DummySink(
        "producer",
        produced=[ArtifactDescriptor(name="raw", type="file/raw", alias="raw")],
        produced_artifacts={
            "raw": Artifact(
                id="",
                type="file/raw",
                path=None,
                persist=True,
                security_level="SECRET",
            )
        },
        security_level="SECRET",
        log=execution_log,
    )
    sanitizer = DummySink(
        "sanitizer",
        consumed=["@raw"],
        produced=[ArtifactDescriptor(name="sanitized", type="file/csv", alias="sanitized")],
        produced_artifacts={
            "sanitized": Artifact(
                id="",
                type="file/csv",
                path=None,
                persist=True,
                security_level="official",
            )
        },
        security_level="SECRET",
        log=execution_log,
        capture_consumed=True,
    )
    consumer = DummySink(
        "consumer",
        consumed=["file/csv"],
        security_level="SECRET",
        log=execution_log,
        capture_consumed=True,
    )

    pipeline = ArtifactPipeline(
        [
            binding_for(0, consumer, security_level="SECRET"),
            binding_for(1, sanitizer, security_level="SECRET"),
            binding_for(2, producer, security_level="SECRET"),
        ]
    )
    store = pipeline.execute({"results": []}, {"security_level": "SECRET", "determinism_level": "guaranteed"})

    artifact_snapshot = {
        artifact_id: {
            "type": artifact.type,
            "produced_by": artifact.produced_by,
            "security_level": artifact.security_level,
            "persist": artifact.persist,
        }
        for artifact_id, artifact in sorted(store.items(), key=lambda item: item[0])
    }

    snapshot = {
        "execution_order": execution_log,
        "prepared": {
            "sanitizer": sanitizer.prepared_artifacts,
            "consumer": consumer.prepared_artifacts,
        },
        "store": artifact_snapshot,
    }

    golden_path = Path(__file__).with_name("data") / "artifact_pipeline_golden.json"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert snapshot == expected
