"""Characterization tests documenting ExperimentRunner.run() behavior.

These tests capture the exact current behavior to detect any changes during refactoring.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from elspeth.core.base.protocols import Artifact, LLMRequest, ResultSink
from elspeth.core.experiments.runner import ExperimentRunner


class SimpleLLM:
    """Deterministic LLM for characterization tests."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        row_id = metadata.get("row_id", "unknown")
        return {
            "content": f"response_{row_id}",
            "raw": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        }


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
