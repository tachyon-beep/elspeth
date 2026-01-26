"""Tests for Azure Multi-Query LLM transform with row-level pipelining."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock, patch

import pytest

from elspeth.contracts import Determinism, TransformResult
from elspeth.contracts.identity import TokenInfo
from elspeth.plugins.batching.ports import CollectorOutputPort
from elspeth.plugins.config_base import PluginConfigError
from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.azure_multi_query import AzureMultiQueryLLMTransform

# Common schema config
DYNAMIC_SCHEMA = {"fields": "dynamic"}


def make_config(**overrides: Any) -> dict[str, Any]:
    """Create valid config with optional overrides."""
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
        "response_format": "json",
        "output_mapping": {"score": "score", "rationale": "rationale"},
        "schema": DYNAMIC_SCHEMA,
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


@contextmanager
def mock_azure_openai_responses(
    responses: list[dict[str, Any]],
) -> Generator[Mock, None, None]:
    """Mock Azure OpenAI to return sequence of JSON responses.

    Thread-safe: Uses itertools.cycle for concurrent access.
    """
    import itertools
    import threading

    # Thread-safe cycling through responses
    response_cycle = itertools.cycle(responses)
    lock = threading.Lock()

    def make_response() -> Mock:
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
        mock_client.chat.completions.create.side_effect = lambda **kwargs: make_response()
        mock_azure_class.return_value = mock_client
        yield mock_client


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


class TestAzureMultiQueryLLMTransformInit:
    """Tests for transform initialization."""

    def test_transform_has_correct_name(self) -> None:
        """Transform registers with correct plugin name."""
        transform = AzureMultiQueryLLMTransform(make_config())
        assert transform.name == "azure_multi_query_llm"

    def test_transform_is_non_deterministic(self) -> None:
        """LLM transforms are non-deterministic."""
        transform = AzureMultiQueryLLMTransform(make_config())
        assert transform.determinism == Determinism.NON_DETERMINISTIC

    def test_transform_expands_queries_on_init(self) -> None:
        """Transform pre-computes query specs on initialization."""
        transform = AzureMultiQueryLLMTransform(make_config())
        # 2 case studies x 2 criteria = 4 queries
        assert len(transform._query_specs) == 4

    def test_transform_requires_case_studies(self) -> None:
        """Transform requires case_studies in config."""
        config = make_config()
        del config["case_studies"]
        with pytest.raises(PluginConfigError):
            AzureMultiQueryLLMTransform(config)

    def test_transform_requires_criteria(self) -> None:
        """Transform requires criteria in config."""
        config = make_config()
        del config["criteria"]
        with pytest.raises(PluginConfigError):
            AzureMultiQueryLLMTransform(config)

    def test_process_raises_not_implemented(self) -> None:
        """process() raises NotImplementedError directing to accept()."""
        transform = AzureMultiQueryLLMTransform(make_config())
        ctx = make_plugin_context()

        with pytest.raises(NotImplementedError, match="row-level pipelining"):
            transform.process({"text": "hello"}, ctx)


class TestSingleQueryProcessing:
    """Tests for _process_single_query method."""

    def test_process_single_query_renders_template(self) -> None:
        """Single query renders template with input fields and criterion."""
        responses = [{"score": 85, "rationale": "Good diagnosis"}]

        with mock_azure_openai_responses(responses) as mock_client:
            transform = AzureMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            # Call on_start to set up the recorder
            transform.on_start(ctx)

            row = {
                "cs1_bg": "45yo male",
                "cs1_sym": "chest pain",
                "cs1_hist": "family history",
            }
            spec = transform._query_specs[0]  # cs1_diagnosis

            assert ctx.state_id is not None
            transform._process_single_query(row, spec, ctx.state_id)

            # Check template was rendered with correct content
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_message = messages[-1]["content"]

            assert "45yo male" in user_message
            assert "diagnosis" in user_message.lower()

    def test_process_single_query_parses_json_response(self) -> None:
        """Single query parses JSON and returns mapped fields."""
        responses = [{"score": 85, "rationale": "Excellent assessment"}]

        with mock_azure_openai_responses(responses):
            transform = AzureMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]  # cs1_diagnosis

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "success"
            assert result.row is not None
            # Output fields use prefix from spec
            assert result.row["cs1_diagnosis_score"] == 85
            assert result.row["cs1_diagnosis_rationale"] == "Excellent assessment"

    def test_process_single_query_handles_invalid_json(self) -> None:
        """Single query returns error on invalid JSON response."""
        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="not json"))]
            mock_response.model = "gpt-4o"
            mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
            mock_response.model_dump = Mock(return_value={})
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert "json" in result.reason["reason"].lower()

    def test_process_single_query_raises_capacity_error_on_rate_limit(self) -> None:
        """Rate limit errors are converted to CapacityError for pooled retry."""
        from elspeth.plugins.clients.llm import RateLimitError
        from elspeth.plugins.pooling import CapacityError

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            # Simulate rate limit from the underlying client
            mock_client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            # Need to mock at AuditedLLMClient level since that's where RateLimitError comes from
            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = RateLimitError("Rate limit exceeded")
                mock_get_client.return_value = mock_llm_client

                assert ctx.state_id is not None
                with pytest.raises(CapacityError) as exc_info:
                    transform._process_single_query(row, spec, ctx.state_id)

                assert exc_info.value.status_code == 429

    def test_process_single_query_handles_template_error(self) -> None:
        """Template rendering errors return error result with details."""
        from elspeth.plugins.llm.templates import TemplateError

        with mock_azure_openai_responses([{"score": 85, "rationale": "ok"}]):
            transform = AzureMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            # Mock template to raise error
            with patch.object(transform._template, "render_with_metadata") as mock_render:
                mock_render.side_effect = TemplateError("Undefined variable 'missing'")

                assert ctx.state_id is not None
                result = transform._process_single_query(row, spec, ctx.state_id)

                assert result.status == "error"
                assert result.reason is not None
                assert result.reason["reason"] == "template_rendering_failed"
                assert "missing" in result.reason["error"]

    def test_get_llm_client_requires_recorder(self) -> None:
        """_get_llm_client raises RuntimeError if recorder not set via on_start."""
        transform = AzureMultiQueryLLMTransform(make_config())
        # Don't call on_start - recorder will be None

        with pytest.raises(RuntimeError) as exc_info:
            transform._get_llm_client("state-123")

        assert "recorder" in str(exc_info.value).lower()


class TestRowProcessingWithPipelining:
    """Tests for full row processing using accept() API with pipelining.

    These tests verify the new accept() API that uses BatchTransformMixin
    for concurrent row processing with FIFO output ordering.
    """

    @pytest.fixture
    def mock_recorder(self) -> Mock:
        """Create mock LandscapeRecorder."""
        recorder = Mock()
        recorder.record_call = Mock()
        return recorder

    @pytest.fixture
    def collector(self) -> CollectorOutputPort:
        """Create output collector for capturing results."""
        return CollectorOutputPort()

    @pytest.fixture
    def ctx(self, mock_recorder: Mock) -> PluginContext:
        """Create plugin context with landscape, state_id, and token."""
        token = make_token("row-1")
        return PluginContext(
            run_id="run-123",
            config={},
            landscape=mock_recorder,
            state_id="state-123",
            token=token,
        )

    @pytest.fixture
    def transform(
        self,
        collector: CollectorOutputPort,
        mock_recorder: Mock,
    ) -> Generator[AzureMultiQueryLLMTransform, None, None]:
        """Create and initialize Azure multi-query transform with pipelining."""
        t = AzureMultiQueryLLMTransform(make_config())
        # Initialize with recorder reference
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        t.on_start(init_ctx)
        # Connect output port
        t.connect_output(collector, max_pending=10)
        yield t
        # Cleanup
        t.close()

    def test_successful_row_emits_all_query_results(
        self,
        ctx: PluginContext,
        transform: AzureMultiQueryLLMTransform,
        collector: CollectorOutputPort,
    ) -> None:
        """Successful row emits results with all query outputs merged."""
        # 4 queries (2 case studies x 2 criteria)
        responses = [
            {"score": 85, "rationale": "CS1 diagnosis"},
            {"score": 90, "rationale": "CS1 treatment"},
            {"score": 75, "rationale": "CS2 diagnosis"},
            {"score": 80, "rationale": "CS2 treatment"},
        ]

        with mock_azure_openai_responses(responses) as mock_client:
            row = {
                "cs1_bg": "case1 bg",
                "cs1_sym": "case1 sym",
                "cs1_hist": "case1 hist",
                "cs2_bg": "case2 bg",
                "cs2_sym": "case2 sym",
                "cs2_hist": "case2 hist",
            }
            transform.accept(row, ctx)
            transform.flush_batch_processing(timeout=10.0)

        assert len(collector.results) == 1
        _token, result, _state_id = collector.results[0]
        assert isinstance(result, TransformResult)

        assert result.status == "success"
        assert mock_client.chat.completions.create.call_count == 4

        # All query results merged into output
        assert result.row is not None
        assert "cs1_diagnosis_score" in result.row
        assert "cs1_treatment_score" in result.row
        assert "cs2_diagnosis_score" in result.row
        assert "cs2_treatment_score" in result.row

    def test_row_preserves_original_fields(
        self,
        ctx: PluginContext,
        transform: AzureMultiQueryLLMTransform,
        collector: CollectorOutputPort,
    ) -> None:
        """Output row preserves original input fields."""
        responses = [
            {"score": 85, "rationale": "R1"},
            {"score": 90, "rationale": "R2"},
            {"score": 75, "rationale": "R3"},
            {"score": 80, "rationale": "R4"},
        ]

        with mock_azure_openai_responses(responses):
            row = {
                "cs1_bg": "bg1",
                "cs1_sym": "sym1",
                "cs1_hist": "hist1",
                "cs2_bg": "bg2",
                "cs2_sym": "sym2",
                "cs2_hist": "hist2",
                "original_field": "preserved",
            }
            transform.accept(row, ctx)
            transform.flush_batch_processing(timeout=10.0)

        assert len(collector.results) == 1
        _, result, _state_id = collector.results[0]
        assert isinstance(result, TransformResult)

        assert result.status == "success"
        assert result.row is not None
        # Original fields preserved
        assert result.row["original_field"] == "preserved"
        assert result.row["cs1_bg"] == "bg1"

    def test_row_fails_if_any_query_fails(
        self,
        ctx: PluginContext,
        transform: AzureMultiQueryLLMTransform,
        collector: CollectorOutputPort,
    ) -> None:
        """All-or-nothing: if any query fails, entire row fails."""
        # First 3 succeed, 4th returns invalid JSON
        call_count = [0]

        def make_response(**kwargs: Any) -> Mock:
            call_count[0] += 1
            if call_count[0] == 4:
                content = "not valid json"
            else:
                content = json.dumps({"score": 85, "rationale": "ok"})

            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content=content))]
            mock_response.model = "gpt-4o"
            mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
            mock_response.model_dump = Mock(return_value={})
            return mock_response

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            row = {
                "cs1_bg": "bg",
                "cs1_sym": "sym",
                "cs1_hist": "hist",
                "cs2_bg": "bg",
                "cs2_sym": "sym",
                "cs2_hist": "hist",
            }
            transform.accept(row, ctx)
            transform.flush_batch_processing(timeout=10.0)

        assert len(collector.results) == 1
        _, result, _state_id = collector.results[0]
        assert isinstance(result, TransformResult)

        # Entire row fails
        assert result.status == "error"
        assert result.reason is not None
        assert "query_failed" in result.reason["reason"]

    def test_connect_output_required_before_accept(self, mock_recorder: Mock) -> None:
        """accept() raises RuntimeError if connect_output() not called."""
        transform = AzureMultiQueryLLMTransform(make_config())

        token = make_token("row-1")
        ctx = PluginContext(
            run_id="test-run",
            config={},
            state_id="test-state-id",
            token=token,
        )

        with pytest.raises(RuntimeError, match="connect_output"):
            transform.accept({"text": "hello"}, ctx)

    def test_connect_output_cannot_be_called_twice(
        self,
        collector: CollectorOutputPort,
        mock_recorder: Mock,
    ) -> None:
        """connect_output() raises if called more than once."""
        transform = AzureMultiQueryLLMTransform(make_config())
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        try:
            with pytest.raises(RuntimeError, match="already called"):
                transform.connect_output(collector, max_pending=10)
        finally:
            transform.close()


class TestMultiRowPipelining:
    """Tests for processing multiple rows with FIFO ordering."""

    @pytest.fixture
    def mock_recorder(self) -> Mock:
        """Create mock LandscapeRecorder."""
        recorder = Mock()
        recorder.record_call = Mock()
        return recorder

    @pytest.fixture
    def collector(self) -> CollectorOutputPort:
        """Create output collector for capturing results."""
        return CollectorOutputPort()

    def test_multiple_rows_processed_in_fifo_order(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """Multiple rows are emitted in submission order (FIFO).

        This test focuses on row-level pipelining via BatchTransformMixin,
        using sequential query execution (no pool_size) to avoid interference
        between query-level and row-level concurrency in the test.
        """
        # Disable query-level pooling to focus on row-level pipelining
        config = make_config()
        del config["pool_size"]

        transform = AzureMultiQueryLLMTransform(config)
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        # Use consistent response for all queries - test is about FIFO ordering
        response = {"score": 85, "rationale": "Good"}

        try:
            with mock_azure_openai_responses([response]):
                for i in range(3):
                    row = {
                        "row_id": f"row-{i}",
                        "cs1_bg": f"r{i}",
                        "cs1_sym": f"r{i}",
                        "cs1_hist": f"r{i}",
                        "cs2_bg": f"r{i}",
                        "cs2_sym": f"r{i}",
                        "cs2_hist": f"r{i}",
                    }
                    token = make_token(f"row-{i}")
                    ctx = PluginContext(
                        run_id="run-123",
                        config={},
                        landscape=mock_recorder,
                        state_id=f"state-{i}",
                        token=token,
                    )
                    transform.accept(row, ctx)

                transform.flush_batch_processing(timeout=10.0)
        finally:
            transform.close()

        # Results should be in FIFO order
        assert len(collector.results) == 3
        for i, (_token, result, _state_id) in enumerate(collector.results):
            assert isinstance(result, TransformResult)
            assert result.status == "success"
            assert result.row is not None
            assert result.row["row_id"] == f"row-{i}"

    def test_rows_use_shared_state_id_for_queries(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """Each row's queries share a state_id (FK constraint).

        All queries for a row share ctx.state_id to satisfy FK constraint:
        - calls.state_id must reference existing node_states.state_id
        - Uniqueness comes from call_index allocated by recorder
        """
        transform = AzureMultiQueryLLMTransform(make_config())
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        responses = [{"score": i, "rationale": f"R{i}"} for i in range(8)]  # 2 rows x 4 queries
        created_state_ids: list[str] = []

        # Patch _get_llm_client to track state_ids
        original_get_client = transform._get_llm_client

        def tracking_get_client(state_id: str) -> Any:
            created_state_ids.append(state_id)
            return original_get_client(state_id)

        transform._get_llm_client = tracking_get_client  # type: ignore[method-assign]

        try:
            with mock_azure_openai_responses(responses):
                for i in range(2):
                    row = {
                        "cs1_bg": f"r{i}",
                        "cs1_sym": f"r{i}",
                        "cs1_hist": f"r{i}",
                        "cs2_bg": f"r{i}",
                        "cs2_sym": f"r{i}",
                        "cs2_hist": f"r{i}",
                    }
                    token = make_token(f"row-{i}")
                    ctx = PluginContext(
                        run_id="run-123",
                        config={},
                        landscape=mock_recorder,
                        state_id=f"batch-{i:03d}",
                        token=token,
                    )
                    transform.accept(row, ctx)

                transform.flush_batch_processing(timeout=10.0)
        finally:
            transform.close()

        # All state_ids should be from the set {batch-000, batch-001}
        unique_state_ids = set(created_state_ids)
        assert unique_state_ids == {"batch-000", "batch-001"}

        # Verify NO synthetic per-query state_ids were created
        for state_id in created_state_ids:
            assert "_q" not in state_id, f"Found synthetic per-query state_id: {state_id}"

    def test_clients_cleaned_up_after_row_processing(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """Clients are cleaned up after each row is processed."""
        transform = AzureMultiQueryLLMTransform(make_config())
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        responses = [{"score": i, "rationale": f"R{i}"} for i in range(8)]

        try:
            with mock_azure_openai_responses(responses):
                for i in range(2):
                    row = {
                        "cs1_bg": f"r{i}",
                        "cs1_sym": f"r{i}",
                        "cs1_hist": f"r{i}",
                        "cs2_bg": f"r{i}",
                        "cs2_sym": f"r{i}",
                        "cs2_hist": f"r{i}",
                    }
                    token = make_token(f"row-{i}")
                    ctx = PluginContext(
                        run_id="run-123",
                        config={},
                        landscape=mock_recorder,
                        state_id=f"batch-{i:03d}",
                        token=token,
                    )
                    transform.accept(row, ctx)

                transform.flush_batch_processing(timeout=10.0)

            # After processing, clients should be cleaned up
            assert len(transform._llm_clients) == 0
        finally:
            transform.close()

    def test_on_start_captures_recorder(self, mock_recorder: Mock) -> None:
        """on_start() captures recorder reference for LLM client creation."""
        transform = AzureMultiQueryLLMTransform(make_config())

        # Verify _recorder starts as None
        assert transform._recorder is None

        ctx = PluginContext(
            run_id="test-run",
            config={},
            landscape=mock_recorder,
            state_id="test-state-id",
        )
        transform.on_start(ctx)

        # Verify recorder was captured
        assert transform._recorder is mock_recorder

    def test_close_clears_recorder_and_clients(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """close() clears recorder reference and cached clients."""
        transform = AzureMultiQueryLLMTransform(make_config())
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        assert transform._recorder is not None

        transform.close()

        assert transform._recorder is None


class TestSequentialMode:
    """Tests for sequential mode (no pool_size) using accept() API."""

    @pytest.fixture
    def mock_recorder(self) -> Mock:
        """Create mock LandscapeRecorder."""
        recorder = Mock()
        recorder.record_call = Mock()
        return recorder

    @pytest.fixture
    def collector(self) -> CollectorOutputPort:
        """Create output collector for capturing results."""
        return CollectorOutputPort()

    def test_sequential_mode_processes_rows(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """Sequential mode (no pool_size) processes rows correctly."""
        # Create config WITHOUT pool_size - forces sequential mode
        config = make_config()
        del config["pool_size"]

        transform = AzureMultiQueryLLMTransform(config)
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        # Verify no executor created (sequential mode)
        assert transform._executor is None

        responses = [{"score": i, "rationale": f"R{i}"} for i in range(4)]

        try:
            with mock_azure_openai_responses(responses):
                row = {
                    "cs1_bg": "r1",
                    "cs1_sym": "r1",
                    "cs1_hist": "r1",
                    "cs2_bg": "r1",
                    "cs2_sym": "r1",
                    "cs2_hist": "r1",
                }
                token = make_token("row-1")
                ctx = PluginContext(
                    run_id="run-123",
                    config={},
                    landscape=mock_recorder,
                    state_id="batch-seq-001",
                    token=token,
                )
                transform.accept(row, ctx)
                transform.flush_batch_processing(timeout=10.0)
        finally:
            transform.close()

        assert len(collector.results) == 1
        _, result, _state_id = collector.results[0]
        assert isinstance(result, TransformResult)
        assert result.status == "success"

    def test_sequential_mode_cleans_up_clients(
        self,
        mock_recorder: Mock,
        collector: CollectorOutputPort,
    ) -> None:
        """Sequential mode cleans up clients after processing."""
        config = make_config()
        del config["pool_size"]

        transform = AzureMultiQueryLLMTransform(config)
        init_ctx = PluginContext(run_id="test", config={}, landscape=mock_recorder)
        transform.on_start(init_ctx)
        transform.connect_output(collector, max_pending=10)

        responses = [{"score": i, "rationale": f"R{i}"} for i in range(8)]  # 2 rows x 4 queries

        try:
            with mock_azure_openai_responses(responses):
                for i in range(2):
                    row = {
                        "cs1_bg": f"r{i}",
                        "cs1_sym": f"r{i}",
                        "cs1_hist": f"r{i}",
                        "cs2_bg": f"r{i}",
                        "cs2_sym": f"r{i}",
                        "cs2_hist": f"r{i}",
                    }
                    token = make_token(f"row-{i}")
                    ctx = PluginContext(
                        run_id="run-123",
                        config={},
                        landscape=mock_recorder,
                        state_id=f"batch-seq-{i:03d}",
                        token=token,
                    )
                    transform.accept(row, ctx)

                transform.flush_batch_processing(timeout=10.0)

            # Clients should be cleaned up after each row
            assert len(transform._llm_clients) == 0
        finally:
            transform.close()
