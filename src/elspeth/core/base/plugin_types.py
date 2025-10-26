"""ADR-003 PLUGIN_TYPE_REGISTRY - Authoritative Plugin Type Catalog.

SECURITY RATIONALE:
This module defines the authoritative list of ALL plugin types that participate
in security validation. Missing entries = bypassed validation = security breach.

PLUGIN_TYPE_REGISTRY serves as the single source of truth for:
1. All plugin attributes in ExperimentRunner that require security validation
2. Cardinality classification (singleton vs list) for correct collection
3. Discovery validation (automated plugin discovery checks against this registry)

Design Pattern:
- Explicit is better than implicit (all plugin types declared here)
- Fail-fast enforcement (tests verify completeness)
- Security-first (missing entries = test failure = security breach prevented)

ADR-003 Threat Prevention:
- T1: Registration Bypass - Registry completeness tests catch missing entries
- T2: Incomplete Validation - collect_all_plugins() uses registry as ground truth
- T3: Configuration Drift - Tests fail if ExperimentRunner adds plugins without updating registry
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.base.plugin import BasePlugin

__all__ = ["PLUGIN_TYPE_REGISTRY", "collect_all_plugins"]


# ============================================================================
# PLUGIN_TYPE_REGISTRY - Authoritative Plugin Type Catalog
# ============================================================================

PLUGIN_TYPE_REGISTRY: dict[str, dict[str, Any]] = {
    # ========================================================================
    # LLM Client and Middleware
    # ========================================================================
    "llm_client": {
        "cardinality": "singleton",
        "description": "Primary LLM client for experiment execution",
        "type_hint": "LLMClientProtocol",
    },
    "llm_middlewares": {
        "cardinality": "list",
        "description": "LLM middleware chain (audit, PII shield, content safety, etc.)",
        "type_hint": "list[LLMMiddleware] | None",
    },
    # ========================================================================
    # Sinks (Output Destinations)
    # ========================================================================
    "sinks": {
        "cardinality": "list",
        "description": "Primary output sinks for experiment results",
        "type_hint": "list[ResultSink]",
    },
    "malformed_data_sink": {
        "cardinality": "singleton",
        "description": "Dedicated sink for malformed/schema-violating data",
        "type_hint": "ResultSink | None",
    },
    # ========================================================================
    # Experiment Plugins (Row, Aggregation, Validation)
    # ========================================================================
    "row_plugins": {
        "cardinality": "list",
        "description": "Row-level experiment plugins (per-record processing)",
        "type_hint": "list[RowExperimentPlugin] | None",
    },
    "aggregator_plugins": {
        "cardinality": "list",
        "description": "Aggregation plugins (post-processing, statistics)",
        "type_hint": "list[AggregationExperimentPlugin] | None",
    },
    "validation_plugins": {
        "cardinality": "list",
        "description": "Suite validation plugins (cross-experiment checks)",
        "type_hint": "list[ValidationPlugin] | None",
    },
    # ========================================================================
    # Control Plugins (Rate Limiting, Cost Tracking)
    # ========================================================================
    "rate_limiter": {
        "cardinality": "singleton",
        "description": "Rate limiter for LLM API calls",
        "type_hint": "RateLimiter | None",
    },
    "cost_tracker": {
        "cardinality": "singleton",
        "description": "Cost tracker for LLM API usage",
        "type_hint": "CostTracker | None",
    },
    # ========================================================================
    # Early Stop Plugins
    # ========================================================================
    "early_stop_plugins": {
        "cardinality": "list",
        "description": "Early stopping condition plugins",
        "type_hint": "list[EarlyStopPlugin] | None",
    },
}


# ============================================================================
# Plugin Collection Helper
# ============================================================================


def collect_all_plugins(runner: Any) -> list[BasePlugin]:
    """Collect all BasePlugin instances from ExperimentRunner for security validation.

    SECURITY: This function is used by compute_minimum_clearance_envelope() to gather
    ALL plugins for security level computation. Missing plugins = incomplete validation.

    Implementation Strategy:
    1. Iterate through PLUGIN_TYPE_REGISTRY (authoritative source)
    2. For each registered attribute, extract plugins from runner
    3. Handle cardinality (singleton vs list)
    4. Filter BasePlugin instances only (skip raw LLM clients, etc.)
    5. Handle None values and empty lists gracefully

    Args:
        runner: ExperimentRunner instance containing plugin attributes

    Returns:
        List of all BasePlugin instances found in the runner

    Example:
        >>> from elspeth.core.security import compute_minimum_clearance_envelope
        >>> plugins = collect_all_plugins(runner)
        >>> envelope = compute_minimum_clearance_envelope(plugins)

    ADR-003 Enforcement:
    - Uses PLUGIN_TYPE_REGISTRY as ground truth (prevents bypass)
    - Cardinality-aware (handles singletons and lists correctly)
    - Type-safe (only collects BasePlugin instances)
    """
    from elspeth.core.base.plugin import BasePlugin

    plugins: list[BasePlugin] = []

    for attr_name, entry in PLUGIN_TYPE_REGISTRY.items():
        # Get attribute value from runner
        attr_value = getattr(runner, attr_name, None)

        # Skip if None (optional plugin)
        if attr_value is None:
            continue

        cardinality = entry["cardinality"]

        if cardinality == "singleton":
            # Single plugin instance
            if isinstance(attr_value, BasePlugin):
                plugins.append(attr_value)
        elif cardinality == "list":
            # List of plugin instances
            if isinstance(attr_value, list):
                for item in attr_value:
                    if isinstance(item, BasePlugin):
                        plugins.append(item)

    return plugins
