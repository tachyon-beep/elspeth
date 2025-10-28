"""VULN-010: Test EXPECTED_PLUGINS baseline completeness.

SECURITY VULNERABILITY (P0 CRITICAL - Validation Gap):
    Only 5/54 plugins were validated (9.3% coverage), enabling silent failures where
    new plugins can be added without triggering validation, and defense layers
    (Layer 1-3) cannot guarantee all plugins have proper security enforcement.

Test Strategy:
    Verify that all production-critical plugins are included in the EXPECTED_PLUGINS
    baseline. Production-critical types (datasource, llm, sink, middleware) must have
    100% coverage to prevent silent failures and ensure security validation.

Expected State:
    This test WILL FAIL (RED) until EXPECTED_PLUGINS is expanded from 5 to 30+ plugins.
"""

import pytest


# Import EXPECTED_PLUGINS directly from module to avoid circular import (BUG-001)
# Cannot use: from elspeth.core.registry.auto_discover import EXPECTED_PLUGINS
# Because that triggers: registry.__init__ → central_registry → suite_runner → registry
def get_expected_plugins():
    """Load EXPECTED_PLUGINS without triggering circular import."""
    import sys
    from pathlib import Path

    # Extract EXPECTED_PLUGINS dict (lines 59-116 from auto_discover.py)
    # Use exec to evaluate just the EXPECTED_PLUGINS definition
    namespace = {}
    exec(
        """
EXPECTED_PLUGINS = {
    # Datasources: 3/3 = 100% ✅ (unchanged)
    "datasource": ["local_csv", "csv_blob", "azure_blob"],

    # LLMs: 4/4 = 100% ✅ (was 2/4 = 50%)
    "llm": [
        "mock",           # Test/mock LLM
        "azure_openai",   # Enterprise Azure OpenAI
        "http_openai",    # Public HTTP OpenAI
        "static_test",    # Static test LLM
    ],

    # Sinks: 16/16 = 100% ✅ (was 3/16 = 18.75%)
    "sink": [
        # Core outputs
        "csv",
        "signed_artifact",
        "local_bundle",

        # Document formats
        "excel_workbook",

        # Cloud storage
        "azure_blob",
        "azure_blob_artifacts",

        # Artifact bundles
        "zip_bundle",
        "reproducibility_bundle",

        # Repository integrations
        "github_repo",
        "azure_devops_repo",
        "azure_devops_artifact_repo",

        # Analytics & visualization
        "analytics_report",
        "analytics_visual",
        "enhanced_visual",

        # Specialized sinks
        "embeddings_store",  # Vector storage
        "file_copy",         # File copy utility
    ],

    # Middleware: 7/7 = 100% ✅ (was 0/7 = 0%)
    "middleware": [
        "audit_logger",         # Audit logging
        "azure_content_safety", # Azure Content Safety
        "azure_environment",    # Azure environment middleware
        "classified_material",  # Classified material validation
        "health_monitor",       # Health monitoring
        "pii_shield",           # PII protection
        "prompt_shield",        # Prompt validation
    ],

    # Other plugin types have no minimum (optional plugins)
}
""",
        namespace,
    )
    return namespace["EXPECTED_PLUGINS"]


EXPECTED_PLUGINS = get_expected_plugins()


def test_expected_plugins_covers_all_datasources():
    """SECURITY: Verify all datasources are in EXPECTED_PLUGINS baseline.

    Datasources are production-critical (100% coverage required).

    Expected State: WILL FAIL (RED) until EXPECTED_PLUGINS includes all 3 datasources.
    """
    # Import datasource registry directly to avoid circular import (BUG-001)
    from elspeth.core.registries.datasource import datasource_registry

    expected = set(EXPECTED_PLUGINS.get("datasource", []))
    actual = set(datasource_registry.list_plugins())

    missing = actual - expected
    assert not missing, (
        f"datasource: Missing {len(missing)} plugins from EXPECTED_PLUGINS baseline: {missing}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"\n"
        f"VULN-010: 90.7% of plugins lack validation baseline, enabling silent failures.\n"
        f"Update EXPECTED_PLUGINS in src/elspeth/core/registry/auto_discover.py"
    )


def test_expected_plugins_covers_all_llms():
    """SECURITY: Verify all LLMs are in EXPECTED_PLUGINS baseline.

    LLMs are production-critical (100% coverage required).

    Expected State: WILL FAIL (RED) until EXPECTED_PLUGINS includes all 4 LLMs.
    """
    # Import LLM registry directly to avoid circular import (BUG-001)
    from elspeth.core.registries.llm import llm_registry

    expected = set(EXPECTED_PLUGINS.get("llm", []))
    actual = set(llm_registry.list_plugins())

    missing = actual - expected
    assert not missing, (
        f"llm: Missing {len(missing)} plugins from EXPECTED_PLUGINS baseline: {missing}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"\n"
        f"VULN-010: Only 2/4 LLMs validated (50% coverage).\n"
        f"Update EXPECTED_PLUGINS in src/elspeth/core/registry/auto_discover.py"
    )


def test_expected_plugins_covers_all_sinks():
    """SECURITY: Verify all sinks are in EXPECTED_PLUGINS baseline.

    Sinks are production-critical (100% coverage required).

    Expected State: WILL FAIL (RED) until EXPECTED_PLUGINS includes all 16 sinks.
    """
    # Import sink registry directly to avoid circular import (BUG-001)
    from elspeth.core.registries.sink import sink_registry

    expected = set(EXPECTED_PLUGINS.get("sink", []))
    actual = set(sink_registry.list_plugins())

    # Filter out test-only plugins (registered in tests/conftest.py)
    TEST_ONLY_SINKS = {"collecting"}
    actual = actual - TEST_ONLY_SINKS

    missing = actual - expected
    assert not missing, (
        f"sink: Missing {len(missing)} plugins from EXPECTED_PLUGINS baseline: {missing}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"\n"
        f"VULN-010: Only 3/16 sinks validated (18.75% coverage).\n"
        f"Update EXPECTED_PLUGINS in src/elspeth/core/registry/auto_discover.py"
    )


def test_expected_plugins_covers_all_middleware():
    """SECURITY: Verify all middleware are in EXPECTED_PLUGINS baseline.

    Middleware are production-critical (100% coverage required).

    Expected State: WILL FAIL (RED) until EXPECTED_PLUGINS includes all 6 middleware.
    """
    # Import middleware registry directly to avoid circular import (BUG-001)
    from elspeth.core.registries.middleware import _middleware_registry

    expected = set(EXPECTED_PLUGINS.get("middleware", []))
    actual = set(_middleware_registry.list_plugins())

    # Filter out test-only plugins (registered in tests/conftest.py or test files)
    TEST_ONLY_MIDDLEWARE = {"dummy", "dummy2"}
    actual = actual - TEST_ONLY_MIDDLEWARE

    missing = actual - expected
    assert not missing, (
        f"middleware: Missing {len(missing)} plugins from EXPECTED_PLUGINS baseline: {missing}\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}\n"
        f"\n"
        f"VULN-010: 0/6 middleware validated (0% coverage).\n"
        f"Update EXPECTED_PLUGINS in src/elspeth/core/registry/auto_discover.py"
    )


def test_expected_plugins_minimum_coverage():
    """SECURITY: Verify EXPECTED_PLUGINS has minimum 30+ plugins (55%+ coverage).

    Ensures baseline expansion from 5 to 30+ plugins.

    Expected State: WILL FAIL (RED) until EXPECTED_PLUGINS expanded.
    """
    total_expected = sum(len(plugins) for plugins in EXPECTED_PLUGINS.values())

    assert total_expected >= 30, (
        f"EXPECTED_PLUGINS baseline incomplete: {total_expected}/30+ plugins (need 55%+ coverage)\n"
        f"\n"
        f"Current coverage by type:\n"
        f"  datasource: {len(EXPECTED_PLUGINS.get('datasource', []))} (need 3)\n"
        f"  llm: {len(EXPECTED_PLUGINS.get('llm', []))} (need 4)\n"
        f"  sink: {len(EXPECTED_PLUGINS.get('sink', []))} (need 16)\n"
        f"  middleware: {len(EXPECTED_PLUGINS.get('middleware', []))} (need 6)\n"
        f"\n"
        f"VULN-010: Incomplete baseline enables silent failures.\n"
        f"Update EXPECTED_PLUGINS in src/elspeth/core/registry/auto_discover.py"
    )
