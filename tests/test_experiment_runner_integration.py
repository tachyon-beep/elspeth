"""High-impact integration coverage for ExperimentRunner."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import pytest

from elspeth.core.controls import FixedPriceCostTracker, FixedWindowRateLimiter
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.interfaces import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.llm.middleware import LLMRequest


class FlakyLLM:
    """LLM client that simulates transient and permanent failures."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.attempts: Dict[str, int] = {}

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        metadata = metadata or {}
        row_id = metadata.get("row_id") or "<unknown>"
        attempt = int(metadata.get("attempt", 1))
        with self._lock:
            self.attempts.setdefault(row_id, 0)
            self.attempts[row_id] = max(self.attempts[row_id], attempt)

        if row_id == "A2" and attempt == 1:
            # Transient failure that should succeed on retry.
            raise RuntimeError("transient failure")
        if row_id == "A3":
            # Permanent failure to exercise exhausted retry handling.
            raise RuntimeError("permanent failure")

        return {
            "content": f"response-{row_id}-attempt{attempt}",
            "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
            "metrics": {"attempt": attempt},
        }


class RecordingMiddleware:
    """Middleware that records lifecycle events and retry exhaustion hooks."""

    name = "recording"

    def __init__(self) -> None:
        self.before: List[tuple[str, int]] = []
        self.after: List[str] = []
        self.retry_events: List[Dict[str, Any]] = []

    def before_request(self, request: LLMRequest) -> LLMRequest:
        self.before.append((request.metadata.get("row_id"), request.metadata.get("attempt")))
        return request

    def after_response(self, request: LLMRequest, response: Dict[str, Any]) -> Dict[str, Any]:
        self.after.append(response.get("content"))
        return response

    def on_retry_exhausted(self, request: LLMRequest, metadata: Dict[str, Any], error: Exception) -> None:
        entry = dict(metadata)
        entry["error"] = str(error)
        self.retry_events.append(entry)


class CollectingSink(ResultSink):
    """Result sink that exposes pipeline interactions for assertions."""

    def __init__(self) -> None:
        self.calls: List[tuple[Dict[str, Any], Dict[str, Any] | None]] = []
        self.prepared: List[Dict[str, Any]] = []
        self.collected: List[Dict[str, Artifact]] = []

    def prepare_artifacts(self, artifacts: Dict[str, List[Artifact]]) -> None:
        self.prepared.append(dict(artifacts))

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
        self.calls.append((results, metadata))

    def collect_artifacts(self) -> Dict[str, Artifact]:
        artifact = Artifact(
            id="bundle",
            type="data/json",
            payload={"ok": True},
            security_level="official",
            persist=True,
        )
        bundle = {"bundle": artifact}
        self.collected.append(bundle)
        return bundle

    def produces(self) -> List[ArtifactDescriptor]:
        return [
            ArtifactDescriptor(
                name="bundle",
                type="data/json",
                persist=True,
                security_level="official",
            )
        ]


def test_experiment_runner_handles_retries_and_artifact_pipeline(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {"APPID": "A1", "payload": "first"},
            {"APPID": "A2", "payload": "retry"},
            {"APPID": "A3", "payload": "always-bad"},
        ]
    )
    df.attrs["security_level"] = "official"

    middleware = RecordingMiddleware()
    sink = CollectingSink()
    runner = ExperimentRunner(
        llm_client=FlakyLLM(),
        sinks=[sink],
        prompt_system="system {{ payload }}",
        prompt_template="prompt {{ payload }}",
        prompt_fields=["APPID", "payload"],
        retry_config={"max_attempts": 2, "initial_delay": 0},
        rate_limiter=FixedWindowRateLimiter(requests=10, per_seconds=0.01),
        cost_tracker=FixedPriceCostTracker(prompt_token_price=0.001, completion_token_price=0.002),
        llm_middlewares=[middleware],
        concurrency_config={
            "enabled": True,
            "max_workers": 3,
            "backlog_threshold": 1,
            "utilization_pause": 0.5,
        },
        checkpoint_config={"path": str(tmp_path / "checkpoint.jsonl"), "field": "APPID"},
        security_level="secret",
        experiment_name="integration",
    )

    payload = runner.run(df)

    # Successful rows only include A1 and A2 (A3 exhausts retries).
    row_ids = {entry["row"]["APPID"] for entry in payload["results"]}
    assert row_ids == {"A1", "A2"}
    assert payload["metadata"]["rows"] == 2
    assert payload["metadata"]["security_level"] == "secret"

    retry_summary = payload["metadata"]["retry_summary"]
    assert retry_summary["total_requests"] == 3  # two successes + one failure
    assert retry_summary["exhausted"] == 1

    # Cost tracker aggregates usage from both successful rows.
    cost_summary = payload["metadata"]["cost_summary"]
    assert cost_summary["prompt_tokens"] == 20
    assert cost_summary["completion_tokens"] == 10
    expected_total = 2 * ((10 * 0.001) + (5 * 0.002))
    assert cost_summary["total_cost"] == pytest.approx(expected_total, rel=1e-9)

    # Failure record contains retry history for A3.
    assert len(payload["failures"]) == 1
    failure = payload["failures"][0]
    assert failure["row"]["APPID"] == "A3"
    assert failure["retry"]["attempts"] == 2
    assert failure["retry"]["history"][0]["status"] == "error"

    # Middleware recorded before/after hooks and retry exhaustion hook fired.
    assert middleware.before
    assert middleware.after
    exhausted = middleware.retry_events[0]
    assert exhausted["attempts"] == 2
    assert exhausted["error_type"] == "RuntimeError"

    # Sink participated in pipeline with prepare + collect.
    assert len(sink.calls) == 1
    recorded_results, recorded_metadata = sink.calls[0]
    assert recorded_results is payload
    assert recorded_metadata["rows"] == 2
    assert sink.prepared  # prepare_artifacts invoked even with no dependencies
    assert sink.prepared[0] == {}
    assert sink.collected and "bundle" in sink.collected[0]
    assert sink.collected[0]["bundle"].persist is True

    # Checkpoint file contains processed IDs (A1 and A2 only).
    contents = (tmp_path / "checkpoint.jsonl").read_text(encoding="utf-8").splitlines()
    assert set(contents) == {"A1", "A2"}
