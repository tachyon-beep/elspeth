"""Tests for configuration contracts."""

import pytest

from elspeth.contracts import config as contract_config
from elspeth.core import config as core_config


class TestConfigReexports:
    """Verify config types are accessible from contracts."""

    @pytest.mark.parametrize("name", contract_config.__all__)
    def test_contract_reexports_identity(self, name: str) -> None:
        """Contract re-exports are identical to core config types."""
        contract_type = getattr(contract_config, name)
        core_type = getattr(core_config, name)
        assert contract_type is core_type

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
