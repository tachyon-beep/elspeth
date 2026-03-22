"""Tests for RAG query construction."""

import os
from unittest.mock import patch

import pytest

from elspeth.plugins.infrastructure.templates import TemplateError
from elspeth.plugins.transforms.rag.query import _FORK_CTX, QueryBuilder

# =============================================================================
# Helpers
# =============================================================================


def _make_crashing_process(exitcode: int = 1):
    """Factory for a patched Process that crashes with the given exit code.

    Returns a side_effect callable for use with patch.object(_FORK_CTX, "Process").
    """
    original_process = _FORK_CTX.Process

    def _factory(*args, **kwargs):
        def _die(*_args):
            os._exit(exitcode)

        kwargs["target"] = _die
        return original_process(*args, **kwargs)

    return _factory


# =============================================================================
# Field-only mode
# =============================================================================


class TestFieldOnlyMode:
    def test_extracts_value_verbatim(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": "What is RAG?"})
        assert result.query == "What is RAG?"

    def test_missing_field_crashes(self):
        """Missing field is a contract violation (Tier 2) — crash, don't quarantine."""
        builder = QueryBuilder(query_field="question")
        with pytest.raises(KeyError):
            builder.build({"other_field": "value"})

    def test_none_value_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": None})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "null_value"

    def test_empty_string_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": ""})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "empty_query"

    def test_whitespace_only_returns_error(self):
        builder = QueryBuilder(query_field="question")
        result = builder.build({"question": "   \t\n  "})
        assert result.error is not None
        assert result.error["reason"] == "invalid_input"
        assert result.error["cause"] == "empty_query"


# =============================================================================
# Template mode
# =============================================================================


class TestTemplateMode:
    def test_renders_with_query_and_row(self):
        builder = QueryBuilder(
            query_field="topic",
            query_template="Find documents about {{ query }} for {{ row.category }}",
        )
        result = builder.build({"topic": "compliance", "category": "finance"})
        assert result.query == "Find documents about compliance for finance"

    def test_structural_error_at_compile_time(self):
        with pytest.raises(TemplateError):
            QueryBuilder(
                query_field="topic",
                query_template="{% if unclosed",
            )

    def test_render_error_returns_error(self):
        builder = QueryBuilder(
            query_field="topic",
            query_template="{{ query }} for {{ row.missing_field }}",
        )
        result = builder.build({"topic": "test"})
        assert result.error is not None
        assert result.error["reason"] == "template_rendering_failed"


# =============================================================================
# Regex mode
# =============================================================================


class TestRegexMode:
    def test_captures_first_group(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+?)(?:\n|$)",
        )
        result = builder.build({"text": "issue: payment failed\nother stuff"})
        assert result.query == "payment failed"

    def test_full_match_when_no_groups(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"\w+@\w+\.\w+",
        )
        result = builder.build({"text": "contact user@example.com for help"})
        assert result.query == "user@example.com"

    def test_no_match_returns_error(self):
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )
        result = builder.build({"text": "no issue here"})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"

    def test_non_participating_group_returns_error(self):
        """Optional capture group that didn't participate."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"(?:issue|problem)(?::\s*(.+?))?$",
        )
        result = builder.build({"text": "issue"})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"
        assert result.error["cause"] == "capture_group_empty"

    def test_timeout_on_catastrophic_backtracking(self):
        """ReDoS protection: pathological pattern with adversarial input."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"(a+)+b",
            regex_timeout=0.1,  # Short timeout for test
        )
        result = builder.build({"text": "a" * 30})
        assert result.error is not None
        assert result.error["reason"] == "no_regex_match"
        assert result.error["cause"] == "regex_timeout"


# =============================================================================
# Subprocess crash detection
# =============================================================================


class TestSubprocessCrashDetection:
    """Bug fix: subprocess crash must CRASH the pipeline, not quarantine the row.

    _regex_worker is system-owned code. A crash is a code bug (or OS/runtime
    failure), not a data issue. Per offensive programming rules: plugin bugs
    crash immediately — they don't silently quarantine.
    """

    def test_crashed_subprocess_raises_runtime_error(self):
        """When child process exits non-zero, build() must raise, not return error."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )

        with (
            patch.object(_FORK_CTX, "Process", side_effect=_make_crashing_process(1)),
            pytest.raises(RuntimeError, match="Regex worker subprocess crashed"),
        ):
            builder.build({"text": "issue: payment failed"})

    def test_crash_error_includes_exitcode_and_pattern(self):
        """Crash exception must include diagnostic details."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )

        with (
            patch.object(_FORK_CTX, "Process", side_effect=_make_crashing_process(42)),
            pytest.raises(RuntimeError, match="exitcode 42") as exc_info,
        ):
            builder.build({"text": "issue: payment failed"})
        assert "issue:" in str(exc_info.value)  # pattern included


# =============================================================================
# Queue resource cleanup
# =============================================================================


class TestQueueResourceCleanup:
    """Bug fix: multiprocessing.Queue must be closed after regex evaluation.

    Verified via mock-based close() spy (deterministic) and supplementary
    FD-count integration test (Linux-only, environment-sensitive).
    """

    def test_queue_close_called_on_success(self):
        """Queue.close() and join_thread() are called after successful match."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )

        original_queue = _FORK_CTX.Queue

        close_calls = []
        join_thread_calls = []

        def _tracking_queue(*args, **kwargs):
            q = original_queue(*args, **kwargs)
            original_close = q.close
            original_join_thread = q.join_thread

            def _close():
                close_calls.append(True)
                return original_close()

            def _join_thread():
                join_thread_calls.append(True)
                return original_join_thread()

            q.close = _close
            q.join_thread = _join_thread
            return q

        with patch.object(_FORK_CTX, "Queue", side_effect=_tracking_queue):
            result = builder.build({"text": "issue: payment failed"})

        assert result.query == "payment failed"
        assert len(close_calls) == 1, "Queue.close() must be called exactly once"
        assert len(join_thread_calls) == 1, "Queue.join_thread() must be called exactly once"

    def test_queue_close_called_on_crash(self):
        """Queue.close() is called even when subprocess crashes (finally block)."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )

        original_queue = _FORK_CTX.Queue
        close_calls = []

        def _tracking_queue(*args, **kwargs):
            q = original_queue(*args, **kwargs)
            original_close = q.close

            def _close():
                close_calls.append(True)
                return original_close()

            q.close = _close
            return q

        with (
            patch.object(_FORK_CTX, "Queue", side_effect=_tracking_queue),
            patch.object(_FORK_CTX, "Process", side_effect=_make_crashing_process(1)),
            pytest.raises(RuntimeError),
        ):
            builder.build({"text": "issue: payment failed"})

        assert len(close_calls) == 1, "Queue.close() must be called even on crash path"

    @pytest.mark.skipif(not os.path.exists("/proc"), reason="Linux /proc required")
    def test_no_fd_leak_after_repeated_evaluations(self):
        """Supplementary integration test: FDs don't accumulate over many calls."""
        builder = QueryBuilder(
            query_field="text",
            query_pattern=r"issue:\s*(.+)",
        )
        pid = os.getpid()
        fd_count_before = len(os.listdir(f"/proc/{pid}/fd"))

        for _ in range(20):
            result = builder.build({"text": "issue: payment failed"})
            assert result.query is not None

        fd_count_after = len(os.listdir(f"/proc/{pid}/fd"))

        assert fd_count_after - fd_count_before < 10, (
            f"File descriptor leak: {fd_count_after - fd_count_before} new FDs "
            f"after 20 regex evaluations (before={fd_count_before}, after={fd_count_after})"
        )
