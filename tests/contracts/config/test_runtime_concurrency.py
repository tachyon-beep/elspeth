# tests/contracts/config/test_runtime_concurrency.py
"""Tests for RuntimeConcurrencyConfig.

TDD tests written before implementation. These verify:
1. Protocol compliance (structural typing)
2. Orphan field detection (no fields without Settings origin)
3. Field name mapping (explicit mapping assertions)
4. Factory method behavior (from_settings, default)
"""

import pytest


class TestRuntimeConcurrencyProtocolCompliance:
    """Verify RuntimeConcurrencyConfig implements RuntimeConcurrencyProtocol."""

    def test_runtime_concurrency_implements_protocol(self) -> None:
        """RuntimeConcurrencyConfig must implement RuntimeConcurrencyProtocol.

        This uses runtime_checkable to verify structural typing.
        """
        from elspeth.contracts.config import RuntimeConcurrencyProtocol
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # Create instance with defaults
        config = RuntimeConcurrencyConfig.default()

        # Protocol check via isinstance (runtime_checkable)
        assert isinstance(config, RuntimeConcurrencyProtocol), (
            "RuntimeConcurrencyConfig does not implement RuntimeConcurrencyProtocol. "
            "Check that all protocol properties are present with correct types."
        )

    def test_protocol_fields_have_correct_types(self) -> None:
        """Protocol fields must return correct types."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        config = RuntimeConcurrencyConfig.default()

        assert isinstance(config.max_workers, int)


class TestRuntimeConcurrencyAllFields:
    """Verify RuntimeConcurrencyConfig has all expected fields from Settings."""

    def test_has_all_settings_fields(self) -> None:
        """RuntimeConcurrencyConfig must have all ConcurrencySettings fields."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # ConcurrencySettings has only one field: max_workers
        expected_fields = {"max_workers"}

        actual_fields = set(RuntimeConcurrencyConfig.__dataclass_fields__.keys())

        assert expected_fields == actual_fields, (
            f"RuntimeConcurrencyConfig fields mismatch.\n"
            f"Missing: {expected_fields - actual_fields}\n"
            f"Extra: {actual_fields - expected_fields}"
        )


class TestRuntimeConcurrencyNoOrphanFields:
    """Verify RuntimeConcurrencyConfig has no orphan fields.

    Every field must come from ConcurrencySettings (no internal-only fields).
    """

    def test_runtime_has_no_orphan_fields(self) -> None:
        """Every RuntimeConcurrencyConfig field must have documented origin."""
        from elspeth.contracts.config import FIELD_MAPPINGS, ConcurrencySettings
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # Get all RuntimeConcurrencyConfig fields
        runtime_fields = set(RuntimeConcurrencyConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "ConcurrencySettings"
        settings_fields = set(ConcurrencySettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All runtime fields must be accounted for
        orphan_fields = runtime_fields - runtime_from_settings

        assert not orphan_fields, (
            f"RuntimeConcurrencyConfig has orphan fields: {orphan_fields}. These must be mapped from ConcurrencySettings."
        )

    def test_no_missing_settings_fields(self) -> None:
        """RuntimeConcurrencyConfig must receive all Settings fields."""
        from elspeth.contracts.config import FIELD_MAPPINGS, ConcurrencySettings
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # Get all RuntimeConcurrencyConfig fields
        runtime_fields = set(RuntimeConcurrencyConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "ConcurrencySettings"
        settings_fields = set(ConcurrencySettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All settings fields must exist in runtime
        missing_fields = runtime_from_settings - runtime_fields

        assert not missing_fields, (
            f"RuntimeConcurrencyConfig is missing Settings fields: {missing_fields}. Add these fields to RuntimeConcurrencyConfig."
        )


class TestConcurrencyFieldNameMapping:
    """Verify field name mappings are correct.

    ConcurrencySettings uses same field names as RuntimeConcurrencyConfig,
    so there should be NO entries in FIELD_MAPPINGS.
    """

    def test_no_field_name_mappings_needed(self) -> None:
        """ConcurrencySettings uses same names - no mappings needed."""
        from elspeth.contracts.config import FIELD_MAPPINGS

        # ConcurrencySettings should not have any field mappings
        # because all field names are the same between Settings and Runtime
        mappings = FIELD_MAPPINGS.get("ConcurrencySettings", {})

        assert mappings == {}, f"ConcurrencySettings should have no field mappings (same names), but found: {mappings}"


class TestRuntimeConcurrencyFromSettings:
    """Test from_settings() factory method."""

    def test_from_settings_maps_all_fields(self) -> None:
        """from_settings() must map all Settings fields correctly."""
        from elspeth.contracts.config import ConcurrencySettings
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # Create settings with non-default values
        settings = ConcurrencySettings(max_workers=16)

        config = RuntimeConcurrencyConfig.from_settings(settings)

        # Verify field mapped correctly
        assert config.max_workers == 16, "max_workers not mapped correctly"

    def test_from_settings_with_defaults(self) -> None:
        """from_settings() should handle default values from Settings."""
        from elspeth.contracts.config import ConcurrencySettings
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        # Use Settings defaults
        settings = ConcurrencySettings()
        config = RuntimeConcurrencyConfig.from_settings(settings)

        # ConcurrencySettings default: max_workers=4
        assert config.max_workers == 4


class TestRuntimeConcurrencyConvenienceFactories:
    """Test convenience factory methods."""

    def test_default_creates_config_with_default_workers(self) -> None:
        """default() should create a config with default max_workers (4)."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        config = RuntimeConcurrencyConfig.default()

        # Default max_workers should be 4 (same as ConcurrencySettings)
        assert config.max_workers == 4


class TestRuntimeConcurrencyImmutability:
    """Test that RuntimeConcurrencyConfig is immutable (frozen dataclass)."""

    def test_frozen_dataclass(self) -> None:
        """RuntimeConcurrencyConfig should be frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        config = RuntimeConcurrencyConfig.default()

        with pytest.raises(FrozenInstanceError):
            config.max_workers = 10  # type: ignore[misc]

    def test_has_slots(self) -> None:
        """RuntimeConcurrencyConfig should use __slots__ for memory efficiency."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        assert hasattr(RuntimeConcurrencyConfig, "__slots__"), "RuntimeConcurrencyConfig should have __slots__"


class TestRuntimeConcurrencyValidation:
    """Test validation in RuntimeConcurrencyConfig."""

    def test_max_workers_must_be_positive(self) -> None:
        """max_workers < 1 should raise ValueError."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            RuntimeConcurrencyConfig(max_workers=0)

    def test_max_workers_negative_raises(self) -> None:
        """Negative max_workers should raise ValueError."""
        from elspeth.contracts.config.runtime import RuntimeConcurrencyConfig

        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            RuntimeConcurrencyConfig(max_workers=-1)
