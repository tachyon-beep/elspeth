"""CLI subcommand helpers for Elspeth.

This package contains lightweight helpers used by the top-level
`elspeth.cli` entrypoint to keep the CLI module maintainable.
"""

__all__ = [
    # top-level commands
    "validate_schemas_command",
    "execute_job_file",
    # single-run helpers
    "maybe_write_artifacts_single",
    "run_single",
    # suite-run helpers
    "clone_suite_sinks",
    "assemble_suite_defaults",
    "maybe_write_artifacts_suite",
    "handle_suite_management",
    "run_suite",
    # common helpers
    "ensure_artifacts_dir",
    "write_simple_artifacts",
    "create_signed_bundle",
    "maybe_publish_artifacts_bundle",
    # config utils
    "strip_metrics_plugins",
    "configure_sink_dry_run",
]
