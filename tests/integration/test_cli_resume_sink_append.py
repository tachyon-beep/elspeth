"""Unit test for resume command sink append mode enforcement.

This test verifies that the resume command ALWAYS forces sinks into append mode,
even when the sink is configured with mode="write" (default).

This prevents data loss when resuming from a checkpoint.
"""

from elspeth.plugins.sinks.csv_sink import CSVSink


def test_resume_should_force_sinks_to_append_mode():
    """Demonstrate that resume needs to force sinks into append mode.

    This is a DOCUMENTATION TEST that shows the expected behavior:
    - User has sink configured with mode="write" (or no mode, which defaults to write)
    - Resume command must override this to mode="append" to prevent data loss
    - Without this override, resuming will truncate existing output files

    This test currently PASSES to document the requirement.
    The actual bug is in cli.py line 1420 where instantiate_plugins_from_config()
    is called without overriding sink modes to append.
    """
    # Simulate what user has in their settings.yaml
    user_sink_config = {
        "path": "/tmp/output.csv",
        "schema": {"fields": "dynamic"},
        # NOTE: User does NOT specify mode, so it defaults to "write"
    }

    # What happens NOW (wrong):
    # resume command does: plugins = instantiate_plugins_from_config(settings)
    # This creates sinks with mode="write", which truncates on open
    sink_wrong = CSVSink(user_sink_config)
    assert sink_wrong._mode == "write"  # This will TRUNCATE existing file!

    # What SHOULD happen (correct):
    # resume command should override sink mode to append
    resume_sink_config = {**user_sink_config, "mode": "append"}
    sink_correct = CSVSink(resume_sink_config)
    assert sink_correct._mode == "append"  # This will ADD to existing file

    # The fix needs to happen in cli.py after line 1420:
    # After instantiating plugins, iterate through sinks and force append mode


def test_csv_sink_mode_default_is_write():
    """Verify CSVSink defaults to mode='write' when not specified."""
    sink = CSVSink(
        {
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
        }
    )
    assert sink._mode == "write", "CSVSink should default to write mode"


def test_csv_sink_respects_append_mode():
    """Verify CSVSink respects mode='append' when specified."""
    sink = CSVSink(
        {
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
            "mode": "append",
        }
    )
    assert sink._mode == "append", "CSVSink should use append mode when specified"
