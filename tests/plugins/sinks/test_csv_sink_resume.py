"""Tests for CSVSink resume capability."""

from elspeth.plugins.sinks.csv_sink import CSVSink


def test_csv_sink_supports_resume():
    """CSVSink should declare supports_resume=True."""
    assert CSVSink.supports_resume is True


def test_csv_sink_configure_for_resume_sets_append_mode():
    """CSVSink.configure_for_resume should set mode to append."""
    sink = CSVSink(
        {
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
            "mode": "write",  # Explicit write mode
        }
    )

    assert sink._mode == "write"

    sink.configure_for_resume()

    assert sink._mode == "append"


def test_csv_sink_configure_for_resume_idempotent():
    """Calling configure_for_resume multiple times should be safe."""
    sink = CSVSink(
        {
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
        }
    )

    sink.configure_for_resume()
    sink.configure_for_resume()  # Second call

    assert sink._mode == "append"
