"""Characterization tests documenting ExperimentRunner.run() behavior.

These tests capture the exact current behavior to detect any changes during refactoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from elspeth.core.base.protocols import Artifact, LLMRequest, ResultSink
from elspeth.core.experiments.runner import (
    CheckpointManager,
    ExperimentContext,
    ExperimentRunner,
    ExecutionMetadata,
    ProcessingResult,
    ResultHandlers,
    RowBatch,
)
from elspeth.core.prompts import PromptEngine
from tests.conftest import SimpleLLM


class CollectingSink(ResultSink):
    """Sink that records all calls for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        self._elspeth_security_level = "official"

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        self.calls.append((results, metadata))


@pytest.fixture
def simple_runner() -> ExperimentRunner:
    """Basic runner for characterization tests."""
    return ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[CollectingSink()],
        prompt_system="You are a test assistant.",
        prompt_template="Process: {{ field }}",
    )


def test_run_result_structure(simple_runner: ExperimentRunner) -> None:
    """INVARIANT: run() returns dict with required top-level keys."""
    df = pd.DataFrame([{"field": "value1"}])
    result = simple_runner.run(df)

    # Top-level keys
    assert isinstance(result, dict)
    assert "results" in result
    assert "failures" in result
    assert "metadata" in result

    # Metadata structure
    metadata = result["metadata"]
    assert "rows" in metadata
    assert "row_count" in metadata
    assert "security_level" in metadata
    assert "determinism_level" in metadata

    # Results structure
    assert isinstance(result["results"], list)
    assert isinstance(result["failures"], list)


def test_run_preserves_dataframe_order(simple_runner: ExperimentRunner) -> None:
    """INVARIANT: Results maintain DataFrame row order (even with concurrency)."""
    df = pd.DataFrame([
        {"field": "A", "id": "row1"},
        {"field": "B", "id": "row2"},
        {"field": "C", "id": "row3"},
        {"field": "D", "id": "row4"},
        {"field": "E", "id": "row5"},
    ])

    result = simple_runner.run(df)

    # Extract field values in result order
    result_fields = [r["row"]["field"] for r in result["results"]]
    expected_fields = ["A", "B", "C", "D", "E"]

    assert result_fields == expected_fields, "Result order must match DataFrame order"


def test_run_checkpoint_idempotency(tmp_path: Path) -> None:
    """INVARIANT: Re-running with checkpoint skips already processed rows."""
    checkpoint_file = tmp_path / "test_checkpoint.jsonl"

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        checkpoint_config={
            "path": str(checkpoint_file),
            "field": "id",
            "allowed_base_path": str(tmp_path),  # Required for fail-closed validation
        },
    )

    df = pd.DataFrame([
        {"id": "A", "data": "first"},
        {"id": "B", "data": "second"},
    ])

    # First run: process both rows
    result1 = runner.run(df)
    assert len(result1["results"]) == 2
    assert checkpoint_file.exists()

    # Verify checkpoint contents (plain text format, one ID per line)
    with checkpoint_file.open("r") as f:
        checkpoint_ids = {line.strip() for line in f if line.strip()}
    assert checkpoint_ids == {"A", "B"}

    # Second run: both rows already checkpointed
    result2 = runner.run(df)
    assert len(result2["results"]) == 0, "All rows should be skipped"

    # Third run: add new row
    df_extended = pd.DataFrame([
        {"id": "A", "data": "first"},
        {"id": "B", "data": "second"},
        {"id": "C", "data": "third"},
    ])
    result3 = runner.run(df_extended)
    assert len(result3["results"]) == 1, "Only new row C should be processed"
    assert result3["results"][0]["row"]["id"] == "C"


def test_run_early_stop_terminates_processing() -> None:
    """INVARIANT: Early stop prevents further row processing."""
    class StopAfterTwo:
        name = "stop_after_two"

        def __init__(self) -> None:
            self.count = 0

        def reset(self) -> None:
            self.count = 0

        def check(self, record: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
            self.count += 1
            if self.count >= 2:
                return {
                    "reason": "stopped_after_two",
                    "row_index": metadata.get("row_index") if metadata else None,
                }
            return None

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        early_stop_plugins=[StopAfterTwo()],
    )

    df = pd.DataFrame([{"id": f"row{i}"} for i in range(10)])
    result = runner.run(df)

    # Should process exactly 2 rows before stopping
    assert len(result["results"]) == 2
    assert "early_stop" in result["metadata"]
    assert result["metadata"]["early_stop"]["reason"] == "stopped_after_two"


def test_run_aggregator_receives_complete_results() -> None:
    """INVARIANT: Aggregators receive all processed results."""
    class CountingAggregator:
        name = "counter"

        def __init__(self) -> None:
            self.received_count: int | None = None
            self.received_results: list[dict[str, Any]] | None = None

        def finalize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
            self.received_count = len(results)
            self.received_results = list(results)  # Copy for inspection
            return {"count": self.received_count, "row_ids": [r["row"]["id"] for r in results]}

    agg = CountingAggregator()
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        aggregator_plugins=[agg],
    )

    df = pd.DataFrame([{"id": f"row{i}"} for i in range(5)])
    result = runner.run(df)

    # Verify aggregator received all results
    assert agg.received_count == 5
    assert len(agg.received_results) == 5

    # Verify aggregator output in payload
    assert "aggregates" in result
    assert "counter" in result["aggregates"]
    assert result["aggregates"]["counter"]["count"] == 5


def test_run_single_failure_doesnt_block_others() -> None:
    """INVARIANT: Row failures don't prevent processing other rows."""
    class FailingLLM:
        """LLM that always fails."""

        def generate(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            raise RuntimeError("Simulated permanent failure")

    runner = ExperimentRunner(
        llm_client=FailingLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        retry_config={"max_attempts": 1},  # Don't retry to keep test fast
    )

    df = pd.DataFrame([
        {"id": "row1"},
        {"id": "row2"},
        {"id": "row3"},
    ])

    result = runner.run(df)

    # All rows should fail, but processing should complete
    assert len(result["results"]) == 0, "All rows should fail"
    assert len(result["failures"]) == 3, "3 rows should be in failures"

    # Verify failure structure
    assert "row" in result["failures"][0]
    assert "retry" in result["failures"][0]

    # Verify metadata includes retry summary
    assert "retry_summary" in result["metadata"]
    assert result["metadata"]["retry_summary"]["exhausted"] == 3


def test_checkpoint_manager_tracks_ids(tmp_path: Path) -> None:
    """Unit test: CheckpointManager tracks processed IDs correctly."""
    checkpoint_file = tmp_path / "test_checkpoint.txt"
    mgr = CheckpointManager(path=checkpoint_file, id_field="id")

    # Initially empty
    assert not mgr.is_processed("row1")

    # Mark as processed
    mgr.mark_processed("row1")
    assert mgr.is_processed("row1")

    # Verify persistence: Checkpoint format is plain text, one ID per line with newline terminator
    # Expected content: "row1\n" (single line with trailing newline)
    assert checkpoint_file.exists()
    with checkpoint_file.open("r") as f:
        content = f.read()
        assert "row1\n" == content

    # Mark another ID
    mgr.mark_processed("row2")
    assert mgr.is_processed("row2")

    # Verify both IDs persisted: Plain text format, one ID per line
    # Expected content: "row1\nrow2\n" (two lines, each with trailing newline)
    with checkpoint_file.open("r") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert lines == ["row1", "row2"]

    # Load from file (new instance)
    mgr2 = CheckpointManager(path=checkpoint_file, id_field="id")
    assert mgr2.is_processed("row1")
    assert mgr2.is_processed("row2")
    assert not mgr2.is_processed("row3")


def test_dataclasses_instantiate() -> None:
    """Smoke test: New dataclasses can be instantiated."""
    # ExperimentContext
    ctx = ExperimentContext(
        engine=PromptEngine(),
        system_template=PromptEngine().compile("test", name="test"),
        user_template=PromptEngine().compile("test", name="test"),
        criteria_templates={},
        checkpoint_manager=None,
        row_plugins=[],
    )
    assert ctx.engine is not None

    # RowBatch
    batch = RowBatch(rows=[])
    assert batch.count == 0

    # ProcessingResult
    result = ProcessingResult(records=[], failures=[])
    assert result.records == []

    # ResultHandlers
    handlers = ResultHandlers(
        on_success=lambda i, r, rid: None,
        on_failure=lambda f: None,
    )
    assert callable(handlers.on_success)

    # ExecutionMetadata
    meta = ExecutionMetadata(rows=0, row_count=0)
    meta_dict = meta.to_dict()
    assert "rows" in meta_dict
    assert "retry_summary" not in meta_dict  # None values omitted


def test_calculate_retry_summary_no_retries() -> None:
    """Unit: _calculate_retry_summary returns None when no retries."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
    )

    result = ProcessingResult(
        records=[{"data": "test"}],
        failures=[],
    )

    summary = runner._calculate_retry_summary(result)
    assert summary is None


def test_calculate_retry_summary_with_retries() -> None:
    """Unit: _calculate_retry_summary counts retries correctly."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Test",
    )

    result = ProcessingResult(
        records=[
            {"retry": {"attempts": 3}},  # 2 retries
            {"retry": {"attempts": 1}},  # 0 retries
        ],
        failures=[
            {"retry": {"attempts": 2}},  # 1 retry
        ],
    )

    summary = runner._calculate_retry_summary(result)
    assert summary is not None
    assert summary["total_requests"] == 3
    assert summary["total_retries"] == 3  # 2 + 0 + 1
    assert summary["exhausted"] == 1


def test_checkpoint_config_fails_closed_on_missing_allowed_base(tmp_path: Path) -> None:
    """SECURITY: Missing allowed_base_path defaults to CWD (fail-closed), not None (fail-open).

    This test verifies the critical security property: user configurations cannot
    bypass path validation by omitting allowed_base_path. Without this protection,
    malicious configs could perform path traversal attacks:

        checkpoint_config:
          path: "../../../etc/passwd"  # Path traversal
          # Omit allowed_base_path to bypass validation → FAIL OPEN (insecure!)

    The fail-closed implementation defaults to Path.cwd() when allowed_base_path
    is missing, ensuring ALL user-provided checkpoint paths are validated.
    """
    # Create a checkpoint path that attempts traversal
    traversal_path = "../../../outside_cwd/malicious.txt"

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        checkpoint_config={
            "path": traversal_path,
            "field": "id",
            # Deliberately omit allowed_base_path to test fail-closed behavior
        },
    )

    df = pd.DataFrame([{"id": "test"}])

    # SECURITY ASSERTION: Path traversal should be blocked
    # If this doesn't raise ValueError, we have a FAIL-OPEN vulnerability!
    with pytest.raises(ValueError, match="Checkpoint path validation failed"):
        runner.run(df)
