# tests/plugins/llm/conftest.py
"""Shared fixtures and helpers for LLM plugin tests."""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock, patch

from elspeth.contracts.identity import TokenInfo
from elspeth.plugins.context import PluginContext

# Common schema config used across LLM tests
DYNAMIC_SCHEMA = {"fields": "dynamic"}


def make_azure_multi_query_config(**overrides: Any) -> dict[str, Any]:
    """Create valid Azure Multi-Query config with optional overrides.

    This is the canonical config factory for AzureMultiQueryLLMTransform tests.
    Use overrides to customize specific fields.
    """
    config = {
        "deployment_name": "gpt-4o",
        "endpoint": "https://test.openai.azure.com",
        "api_key": "test-key",
        "template": "Input: {{ row.input_1 }}\nCriterion: {{ row.criterion.name }}",
        "system_prompt": "You are an assessment AI. Respond in JSON.",
        "case_studies": [
            {"name": "cs1", "input_fields": ["cs1_bg", "cs1_sym", "cs1_hist"]},
            {"name": "cs2", "input_fields": ["cs2_bg", "cs2_sym", "cs2_hist"]},
        ],
        "criteria": [
            {"name": "diagnosis", "code": "DIAG"},
            {"name": "treatment", "code": "TREAT"},
        ],
        "response_format": "standard",
        "output_mapping": {
            "score": {"suffix": "score", "type": "integer"},
            "rationale": {"suffix": "rationale", "type": "string"},
        },
        "schema": DYNAMIC_SCHEMA,
        "required_input_fields": [],  # Explicit opt-out for tests
        "pool_size": 4,
    }
    config.update(overrides)
    return config


def make_token(row_id: str = "row-1", token_id: str | None = None) -> TokenInfo:
    """Create a TokenInfo for testing."""
    return TokenInfo(
        row_id=row_id,
        token_id=token_id or f"token-{row_id}",
        row_data={},  # Not used in these tests
    )


def make_plugin_context(
    state_id: str = "state-123",
    token: TokenInfo | None = None,
) -> PluginContext:
    """Create a PluginContext with mocked landscape."""
    mock_landscape = Mock()
    mock_landscape.record_external_call = Mock()
    mock_landscape.record_call = Mock()
    return PluginContext(
        run_id="run-123",
        landscape=mock_landscape,
        state_id=state_id,
        config={},
        token=token or make_token("row-1"),
    )


@contextmanager
def mock_azure_openai_responses(
    responses: list[dict[str, Any]],
) -> Generator[Mock, None, None]:
    """Mock Azure OpenAI to return sequence of JSON responses.

    Thread-safe: Uses itertools.cycle for concurrent access.
    """
    response_cycle = itertools.cycle(responses)
    lock = threading.Lock()

    def make_response(**kwargs: Any) -> Mock:
        with lock:
            response_data = next(response_cycle)
        content = json.dumps(response_data)

        mock_usage = Mock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_message = Mock()
        mock_message.content = content

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o"
        mock_response.usage = mock_usage
        mock_response.model_dump = Mock(return_value={"model": "gpt-4o"})

        return mock_response

    with patch("openai.AzureOpenAI") as mock_azure_class:
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = make_response
        mock_azure_class.return_value = mock_client
        yield mock_client
