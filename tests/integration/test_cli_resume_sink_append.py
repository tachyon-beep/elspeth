"""Unit tests for sink resume capability.

These tests verify that sinks properly declare and implement resume capability,
which is used by the CLI resume command to configure sinks for append mode.
"""

import os

import pytest

from elspeth.plugins.sinks.csv_sink import CSVSink
from elspeth.plugins.sinks.database_sink import DatabaseSink
from elspeth.plugins.sinks.json_sink import JSONSink


class TestSinkResumeCapabilityDeclarations:
    """Verify sinks correctly declare their resume capability."""

    def test_csv_sink_supports_resume(self):
        """CSVSink declares supports_resume=True."""
        assert CSVSink.supports_resume is True

    def test_database_sink_supports_resume(self):
        """DatabaseSink declares supports_resume=True."""
        assert DatabaseSink.supports_resume is True

    def test_jsonl_sink_supports_resume(self):
        """JSONSink with JSONL format supports resume."""
        sink = JSONSink(
            {
                "path": "/tmp/test.jsonl",
                "schema": {"fields": "dynamic"},
                "format": "jsonl",
            }
        )
        assert sink.supports_resume is True

    def test_json_array_sink_does_not_support_resume(self):
        """JSONSink with JSON array format does NOT support resume."""
        sink = JSONSink(
            {
                "path": "/tmp/test.json",
                "schema": {"fields": "dynamic"},
                "format": "json",
            }
        )
        assert sink.supports_resume is False


class TestSinkConfigureForResume:
    """Verify sinks properly implement configure_for_resume."""

    def test_csv_sink_configure_for_resume(self):
        """CSVSink.configure_for_resume sets mode to append."""
        sink = CSVSink(
            {
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "mode": "write",
            }
        )
        assert sink._mode == "write"

        sink.configure_for_resume()

        assert sink._mode == "append"

    @pytest.fixture(autouse=True)
    def allow_raw_secrets(self):
        """Allow raw secrets for database testing."""
        os.environ["ELSPETH_ALLOW_RAW_SECRETS"] = "true"
        yield
        os.environ.pop("ELSPETH_ALLOW_RAW_SECRETS", None)

    def test_database_sink_configure_for_resume(self):
        """DatabaseSink.configure_for_resume sets if_exists to append."""
        sink = DatabaseSink(
            {
                "url": "sqlite:///:memory:",
                "table": "test",
                "schema": {"fields": "dynamic"},
                "if_exists": "replace",
            }
        )
        assert sink._if_exists == "replace"

        sink.configure_for_resume()

        assert sink._if_exists == "append"

    def test_jsonl_sink_configure_for_resume(self):
        """JSONSink JSONL format configure_for_resume sets mode to append."""
        sink = JSONSink(
            {
                "path": "/tmp/test.jsonl",
                "schema": {"fields": "dynamic"},
                "format": "jsonl",
                "mode": "write",
            }
        )
        assert sink._mode == "write"

        sink.configure_for_resume()

        assert sink._mode == "append"

    def test_json_array_sink_configure_for_resume_raises(self):
        """JSONSink JSON array format configure_for_resume raises NotImplementedError."""
        sink = JSONSink(
            {
                "path": "/tmp/test.json",
                "schema": {"fields": "dynamic"},
                "format": "json",
            }
        )

        with pytest.raises(NotImplementedError) as exc_info:
            sink.configure_for_resume()

        assert "jsonl" in str(exc_info.value).lower()
