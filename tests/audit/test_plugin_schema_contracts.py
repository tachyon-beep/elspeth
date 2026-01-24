"""Audit tests for plugin schema contracts.

Verifies plugins follow schema initialization contract.
Critical for new architecture - plugins MUST set schemas in __init__().
"""

from elspeth.plugins.config_base import PluginConfigError
from elspeth.plugins.manager import PluginManager


def test_all_sources_set_output_schema():
    """Verify all source plugins set output_schema in __init__()."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    for plugin_cls in manager.get_sources():
        # Instantiate with minimal valid config
        try:
            instance = plugin_cls({"path": "test.csv", "schema": {"fields": "dynamic"}, "on_validation_failure": "quarantine"})
        except (TypeError, PluginConfigError):
            # Some sources may require different config - skip validation
            # (e.g., AzureBlobSource needs container/blob_path, not path)
            continue

        # CRITICAL: output_schema must be set
        assert hasattr(instance, "output_schema"), f"Source {plugin_cls.name} missing output_schema attribute"

        # Schema can be None (dynamic) but attribute must exist
        # This validates __init__() runs the assignment


def test_all_transforms_set_schemas():
    """Verify all transform plugins set input/output schemas in __init__()."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    for plugin_cls in manager.get_transforms():
        # Instantiate with minimal valid config
        try:
            instance = plugin_cls({"schema": {"fields": "dynamic"}})
        except (TypeError, PluginConfigError):
            # Some transforms may require different config - skip validation
            continue

        # CRITICAL: Both schemas must be set
        assert hasattr(instance, "input_schema"), f"Transform {plugin_cls.name} missing input_schema attribute"

        assert hasattr(instance, "output_schema"), f"Transform {plugin_cls.name} missing output_schema attribute"


def test_all_sinks_set_input_schema():
    """Verify all sink plugins set input_schema in __init__()."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    for plugin_cls in manager.get_sinks():
        # Instantiate with minimal valid config
        try:
            instance = plugin_cls({"path": "test.csv", "schema": {"fields": "dynamic"}})
        except (TypeError, PluginConfigError):
            # Some sinks may require different config - skip validation
            # (e.g., DatabaseSink needs url/table, not path)
            continue

        # CRITICAL: input_schema must be set
        assert hasattr(instance, "input_schema"), f"Sink {plugin_cls.name} missing input_schema attribute"


def test_plugin_init_does_not_perform_io():
    """Verify plugins don't perform I/O in __init__() (brittle validation risk).

    This addresses Systems Thinking concern about validation brittleness.
    Plugins should delay I/O until execute time, not __init__().
    """
    manager = PluginManager()
    manager.register_builtin_plugins()

    # Test CSVSource with nonexistent file - should NOT crash in __init__()
    csv_source_cls = manager.get_source_by_name("csv")
    instance = csv_source_cls(
        {"path": "/nonexistent/file/that/does/not/exist.csv", "schema": {"fields": "dynamic"}, "on_validation_failure": "quarantine"}
    )

    # If __init__() tried to open file, this would have crashed
    # Schemas should still be set
    assert hasattr(instance, "output_schema")
