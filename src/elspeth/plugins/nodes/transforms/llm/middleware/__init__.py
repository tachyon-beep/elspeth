"""LLM middleware plugins."""

# Import all middleware modules to trigger registration
from elspeth.plugins.nodes.transforms.llm.middleware import (
    audit,
    azure_content_safety,
    classified_material,
    health_monitor,
    pii_shield,
    prompt_shield,
)

# Re-export classes for backward compatibility
from elspeth.plugins.nodes.transforms.llm.middleware.audit import AuditMiddleware
from elspeth.plugins.nodes.transforms.llm.middleware.azure_content_safety import AzureContentSafetyMiddleware
from elspeth.plugins.nodes.transforms.llm.middleware.classified_material import ClassifiedMaterialMiddleware
from elspeth.plugins.nodes.transforms.llm.middleware.health_monitor import HealthMonitorMiddleware
from elspeth.plugins.nodes.transforms.llm.middleware.pii_shield import PIIShieldMiddleware
from elspeth.plugins.nodes.transforms.llm.middleware.prompt_shield import PromptShieldMiddleware

__all__ = [
    # Modules
    "audit",
    "azure_content_safety",
    "classified_material",
    "health_monitor",
    "pii_shield",
    "prompt_shield",
    # Classes (backward compatibility)
    "AuditMiddleware",
    "AzureContentSafetyMiddleware",
    "ClassifiedMaterialMiddleware",
    "HealthMonitorMiddleware",
    "PIIShieldMiddleware",
    "PromptShieldMiddleware",
]
