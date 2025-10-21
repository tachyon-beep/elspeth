"""CLI subcommand helpers for Elspeth.

This package re-exports the commonly used CLI functions so callers can import
from ``elspeth.core.cli`` without needing to know the internal module layout.
"""

# Re-export public CLI helpers from submodules
from .common import (
    create_signed_bundle,
    ensure_artifacts_dir,
    maybe_publish_artifacts_bundle,
    write_simple_artifacts,
)
from .config_utils import configure_sink_dry_run, strip_metrics_plugins
from .job import execute_job_file
from .single import maybe_write_artifacts_single, run_single
from .suite import (
    assemble_suite_defaults,
    clone_suite_sinks,
    handle_suite_management,
    maybe_write_artifacts_suite,
    run_suite,
)
from .validate import validate_schemas_command

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
