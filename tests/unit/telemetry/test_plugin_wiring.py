# tests/telemetry/test_plugin_wiring.py
"""Verify all external-call plugins are wired for telemetry.

This test ensures no plugin is accidentally left without telemetry support.
It inspects plugin source code to verify they:
1. Capture run_id and telemetry_emit in on_start()
2. Pass these to audited clients (or to providers that create audited clients)

This is a regression guard - if a new plugin is added that makes
external calls, this test will fail until it's properly wired.
"""

from pathlib import Path
from typing import Any

import pytest

# Plugins that make external calls and MUST emit telemetry
EXTERNAL_CALL_PLUGINS: dict[str, dict[str, Any]] = {
    # Unified LLM transform — dispatches to providers which create audited clients.
    # Captures run_id/telemetry_emit in on_start() and passes to provider constructors.
    "src/elspeth/plugins/transforms/llm/transform.py": {
        "class": "LLMTransform",
        "client_type": "AzureLLMProvider",  # One of the provider constructors in source
        "pattern": "on_start_capture",  # Captures in on_start, passes to providers
    },
    # Provider implementations (Phase B of T10 LLM consolidation)
    "src/elspeth/plugins/transforms/llm/providers/azure.py": {
        "class": "AzureLLMProvider",
        "client_type": "AuditedLLMClient",
        "pattern": "init_capture",  # Receives run_id/telemetry_emit in __init__
    },
    "src/elspeth/plugins/transforms/llm/providers/openrouter.py": {
        "class": "OpenRouterLLMProvider",
        "client_type": "AuditedHTTPClient",
        "pattern": "init_capture",  # Receives run_id/telemetry_emit in __init__
    },
    # Azure safety transforms: on_start() and _get_http_client() live in the base class.
    # Subclasses inherit telemetry wiring — verify at the base level.
    "src/elspeth/plugins/transforms/azure/base.py": {
        "class": "BaseAzureSafetyTransform",
        "client_type": "AuditedHTTPClient",
        "pattern": "on_start_capture",
    },
    "src/elspeth/plugins/transforms/web_scrape.py": {
        "class": "WebScrapeTransform",
        "client_type": "AuditedHTTPClient",
        "pattern": "ctx_passthrough",
    },
}

# Plugins that are EXEMPT from telemetry (with reason)
TELEMETRY_EXEMPT_PLUGINS: dict[str, str] = {
    "src/elspeth/plugins/transforms/llm/azure_batch.py": "Batch API - uses file uploads, not per-row calls",
    "src/elspeth/plugins/transforms/llm/openrouter_batch.py": "Batch API - uses file uploads, not per-row calls",
    # Legacy individual transforms — deprecated by unified LLMTransform (T10 Phase B).
    # These files still exist during the transition period and will be deleted in Task 12.
    "src/elspeth/plugins/transforms/llm/azure.py": "Legacy — deprecated by unified LLMTransform, pending deletion in Task 12",
    "src/elspeth/plugins/transforms/llm/azure_multi_query.py": "Legacy — deprecated by unified LLMTransform, pending deletion in Task 12",
    "src/elspeth/plugins/transforms/llm/openrouter.py": "Legacy — deprecated by unified LLMTransform, pending deletion in Task 12",
    "src/elspeth/plugins/transforms/llm/openrouter_multi_query.py": "Legacy — deprecated by unified LLMTransform, pending deletion in Task 12",
}

# Files that define audited clients (not plugins that USE them)
CLIENT_DEFINITION_FILES: set[str] = {
    "src/elspeth/plugins/infrastructure/clients/llm.py",  # Defines AuditedLLMClient
    "src/elspeth/plugins/infrastructure/clients/http.py",  # Defines AuditedHTTPClient
    "src/elspeth/plugins/transforms/llm/base.py",  # Base class with AuditedLLMClient factory
}


class TestTelemetryWiring:
    """Verify telemetry wiring for all external-call plugins."""

    @pytest.mark.parametrize(
        "plugin_path,config",
        list(EXTERNAL_CALL_PLUGINS.items()),
        ids=lambda x: x if isinstance(x, str) else x.get("class", "unknown"),
    )
    def test_plugin_captures_telemetry_context(self, plugin_path: str, config: dict[str, Any]) -> None:
        """Verify plugin captures run_id and telemetry_emit."""
        full_path = Path(plugin_path)
        assert full_path.exists(), f"Plugin file not found: {plugin_path}"

        source = full_path.read_text()
        pattern = config["pattern"]

        if pattern == "on_start_capture":
            # Check on_start captures run_id and telemetry_emit
            assert "self._run_id" in source or "ctx.run_id" in source, f"{plugin_path} must capture run_id in on_start()"
            assert "self._telemetry_emit" in source or "ctx.telemetry_emit" in source, (
                f"{plugin_path} must capture telemetry_emit in on_start()"
            )

        elif pattern == "ctx_passthrough":
            # Check that ctx.run_id and ctx.telemetry_emit are passed through
            # This pattern passes them directly from PluginContext, not storing on self
            assert "ctx.run_id" in source, f"{plugin_path} must pass ctx.run_id"
            assert "ctx.telemetry_emit" in source, f"{plugin_path} must pass ctx.telemetry_emit"

        elif pattern == "init_capture":
            # Provider classes receive run_id/telemetry_emit in __init__
            # and store them for passing to audited clients
            assert "run_id" in source, f"{plugin_path} must accept run_id in __init__"
            assert "telemetry_emit" in source, f"{plugin_path} must accept telemetry_emit in __init__"

    @pytest.mark.parametrize(
        "plugin_path,config",
        list(EXTERNAL_CALL_PLUGINS.items()),
        ids=lambda x: x if isinstance(x, str) else x.get("class", "unknown"),
    )
    def test_plugin_passes_telemetry_to_client(self, plugin_path: str, config: dict[str, Any]) -> None:
        """Verify plugin passes telemetry params to audited client or provider."""
        full_path = Path(plugin_path)
        source = full_path.read_text()

        client_type = config["client_type"]

        # Check that the client/provider constructor is called in source
        assert f"{client_type}(" in source, f"{plugin_path} must use {client_type}"

        # Check for run_id= and telemetry_emit= in constructor calls
        assert "run_id=" in source, f"{plugin_path} must pass run_id to {client_type}"
        assert "telemetry_emit=" in source, f"{plugin_path} must pass telemetry_emit to {client_type}"

    def test_all_external_call_plugins_are_listed(self) -> None:
        """Ensure we haven't missed any plugins that make external calls.

        This test finds all plugins that import audited clients and verifies
        they are either in EXTERNAL_CALL_PLUGINS or TELEMETRY_EXEMPT_PLUGINS.
        """
        plugins_dir = Path("src/elspeth/plugins")

        # Find all Python files that import audited clients
        audited_imports = ["AuditedLLMClient", "AuditedHTTPClient"]
        found_plugins: set[str] = set()

        for py_file in plugins_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue

            content = py_file.read_text()
            for client in audited_imports:
                if client in content and f"{client}(" in content:
                    rel_path = str(py_file)
                    found_plugins.add(rel_path)

        # Check all found plugins are accounted for
        known_plugins = set(EXTERNAL_CALL_PLUGINS.keys()) | set(TELEMETRY_EXEMPT_PLUGINS.keys()) | CLIENT_DEFINITION_FILES

        unknown = found_plugins - known_plugins
        assert not unknown, (
            f"Found plugins using audited clients that are not listed in "
            f"EXTERNAL_CALL_PLUGINS, TELEMETRY_EXEMPT_PLUGINS, or CLIENT_DEFINITION_FILES: {unknown}"
        )
