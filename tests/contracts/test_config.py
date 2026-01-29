"""Tests for configuration contracts."""

import pytest

from elspeth.contracts import config as contract_config
from elspeth.core import config as core_config

# Settings classes that should be re-exported from core.config
SETTINGS_REEXPORTS = {
    "AggregationSettings",
    "CheckpointSettings",
    "CoalesceSettings",
    "ConcurrencySettings",
    "DatabaseSettings",
    "ElspethSettings",
    "GateSettings",
    "LandscapeExportSettings",
    "LandscapeSettings",
    "PayloadStoreSettings",
    "RateLimitSettings",
    "RetrySettings",
    "ServiceRateLimit",
    "SinkSettings",
    "SourceSettings",
    "TransformSettings",
    "TriggerConfig",
}

# Items defined in the contracts.config subpackage (not from core.config)
CONTRACTS_CONFIG_ITEMS = {
    # Runtime protocols
    "RuntimeCheckpointProtocol",
    "RuntimeConcurrencyProtocol",
    "RuntimeRateLimitProtocol",
    "RuntimeRetryProtocol",
    # Runtime configuration dataclasses
    "RuntimeRetryConfig",
    # Default registries
    "INTERNAL_DEFAULTS",
    "POLICY_DEFAULTS",
    "get_internal_default",
    "get_policy_default",
    # Alignment documentation
    "EXEMPT_SETTINGS",
    "FIELD_MAPPINGS",
    "SETTINGS_TO_RUNTIME",
    "get_runtime_field_name",
    "get_settings_field_name",
    "is_exempt_settings",
}


class TestConfigReexports:
    """Verify config types are accessible from contracts."""

    @pytest.mark.parametrize("name", sorted(SETTINGS_REEXPORTS))
    def test_settings_reexports_identity(self, name: str) -> None:
        """Settings re-exports are identical to core config types."""
        contract_type = getattr(contract_config, name)
        core_type = getattr(core_config, name)
        assert contract_type is core_type

    @pytest.mark.parametrize("name", sorted(CONTRACTS_CONFIG_ITEMS))
    def test_contracts_config_items_exist(self, name: str) -> None:
        """Items defined in contracts.config subpackage are accessible."""
        item = getattr(contract_config, name)
        assert item is not None

    def test_all_exports_categorized(self) -> None:
        """All items in __all__ must be in either SETTINGS_REEXPORTS or CONTRACTS_CONFIG_ITEMS."""
        all_exports = set(contract_config.__all__)
        categorized = SETTINGS_REEXPORTS | CONTRACTS_CONFIG_ITEMS

        missing = all_exports - categorized
        extra = categorized - all_exports

        assert not missing, f"Uncategorized exports: {missing}. Add to SETTINGS_REEXPORTS or CONTRACTS_CONFIG_ITEMS."
        assert not extra, f"Categorized items not in __all__: {extra}. Remove from test categories or add to __all__."

    def test_settings_are_pydantic_models(self) -> None:
        """Config types are Pydantic (trust boundary validation)."""
        from pydantic import BaseModel

        from elspeth.contracts import ElspethSettings, SourceSettings

        assert issubclass(ElspethSettings, BaseModel)
        assert issubclass(SourceSettings, BaseModel)

    def test_settings_are_frozen(self) -> None:
        """Config is immutable after construction."""
        from pydantic import ValidationError

        from elspeth.contracts import SourceSettings

        settings = SourceSettings(plugin="csv_local")

        with pytest.raises(ValidationError):
            settings.plugin = "other"  # type: ignore[misc]
