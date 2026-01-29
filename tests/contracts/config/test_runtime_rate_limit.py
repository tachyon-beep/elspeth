# tests/contracts/config/test_runtime_rate_limit.py
"""Tests for RuntimeRateLimitConfig.

TDD tests written before implementation. These verify:
1. Protocol compliance (structural typing)
2. Orphan field detection (no fields without Settings origin)
3. Field name mapping (explicit mapping assertions)
4. Factory method behavior (from_settings, default)
"""

import pytest


class TestRuntimeRateLimitProtocolCompliance:
    """Verify RuntimeRateLimitConfig implements RuntimeRateLimitProtocol."""

    def test_runtime_rate_limit_implements_protocol(self) -> None:
        """RuntimeRateLimitConfig must implement RuntimeRateLimitProtocol.

        This uses runtime_checkable to verify structural typing.
        """
        from elspeth.contracts.config import RuntimeRateLimitProtocol
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # Create instance with defaults
        config = RuntimeRateLimitConfig.default()

        # Protocol check via isinstance (runtime_checkable)
        assert isinstance(config, RuntimeRateLimitProtocol), (
            "RuntimeRateLimitConfig does not implement RuntimeRateLimitProtocol. "
            "Check that all protocol properties are present with correct types."
        )

    def test_protocol_fields_have_correct_types(self) -> None:
        """Protocol fields must return correct types."""
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        config = RuntimeRateLimitConfig.default()

        assert isinstance(config.enabled, bool)
        # default_requests_per_second can be float or None
        assert config.default_requests_per_second is None or isinstance(config.default_requests_per_second, float)
        # default_requests_per_minute can be float or None
        assert config.default_requests_per_minute is None or isinstance(config.default_requests_per_minute, float)


class TestRuntimeRateLimitAllFields:
    """Verify RuntimeRateLimitConfig has all expected fields from Settings."""

    def test_has_all_settings_fields(self) -> None:
        """RuntimeRateLimitConfig must have all RateLimitSettings fields."""
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # All 5 fields from RateLimitSettings
        expected_fields = {
            "enabled",
            "default_requests_per_second",
            "default_requests_per_minute",
            "persistence_path",
            "services",
        }

        actual_fields = set(RuntimeRateLimitConfig.__dataclass_fields__.keys())

        assert expected_fields == actual_fields, (
            f"RuntimeRateLimitConfig fields mismatch.\nMissing: {expected_fields - actual_fields}\nExtra: {actual_fields - expected_fields}"
        )


class TestRuntimeRateLimitNoOrphanFields:
    """Verify RuntimeRateLimitConfig has no orphan fields.

    Every field must come from RateLimitSettings (no internal-only fields).
    """

    def test_runtime_has_no_orphan_fields(self) -> None:
        """Every RuntimeRateLimitConfig field must have documented origin."""
        from elspeth.contracts.config import FIELD_MAPPINGS, RateLimitSettings
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # Get all RuntimeRateLimitConfig fields
        runtime_fields = set(RuntimeRateLimitConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "RateLimitSettings"
        settings_fields = set(RateLimitSettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All runtime fields must be accounted for
        orphan_fields = runtime_fields - runtime_from_settings

        assert not orphan_fields, f"RuntimeRateLimitConfig has orphan fields: {orphan_fields}. These must be mapped from RateLimitSettings."

    def test_no_missing_settings_fields(self) -> None:
        """RuntimeRateLimitConfig must receive all Settings fields."""
        from elspeth.contracts.config import FIELD_MAPPINGS, RateLimitSettings
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # Get all RuntimeRateLimitConfig fields
        runtime_fields = set(RuntimeRateLimitConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "RateLimitSettings"
        settings_fields = set(RateLimitSettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All settings fields must exist in runtime
        missing_fields = runtime_from_settings - runtime_fields

        assert not missing_fields, (
            f"RuntimeRateLimitConfig is missing Settings fields: {missing_fields}. Add these fields to RuntimeRateLimitConfig."
        )


class TestRateLimitFieldNameMapping:
    """Verify field name mappings are correct.

    RateLimitSettings uses same field names as RuntimeRateLimitConfig,
    so there should be NO entries in FIELD_MAPPINGS.
    """

    def test_no_field_name_mappings_needed(self) -> None:
        """RateLimitSettings uses same names - no mappings needed."""
        from elspeth.contracts.config import FIELD_MAPPINGS

        # RateLimitSettings should not have any field mappings
        # because all field names are the same between Settings and Runtime
        mappings = FIELD_MAPPINGS.get("RateLimitSettings", {})

        assert mappings == {}, f"RateLimitSettings should have no field mappings (same names), but found: {mappings}"


class TestRuntimeRateLimitFromSettings:
    """Test from_settings() factory method."""

    def test_from_settings_maps_all_fields(self) -> None:
        """from_settings() must map all Settings fields correctly."""
        from elspeth.contracts.config import RateLimitSettings, ServiceRateLimit
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # Create settings with non-default values
        services = {"openai": ServiceRateLimit(requests_per_second=5)}
        settings = RateLimitSettings(
            enabled=False,
            default_requests_per_second=25,
            default_requests_per_minute=500,
            persistence_path="/tmp/rate_limits.db",
            services=services,
        )

        config = RuntimeRateLimitConfig.from_settings(settings)

        # Verify all fields mapped correctly
        assert config.enabled is False, "enabled not mapped correctly"
        assert config.default_requests_per_second == 25.0, "default_requests_per_second not mapped correctly"
        assert config.default_requests_per_minute == 500.0, "default_requests_per_minute not mapped correctly"
        assert config.persistence_path == "/tmp/rate_limits.db", "persistence_path not mapped correctly"
        assert config.services == services, "services not mapped correctly"

    def test_from_settings_with_defaults(self) -> None:
        """from_settings() should handle default values from Settings."""
        from elspeth.contracts.config import RateLimitSettings
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        # Use Settings defaults
        settings = RateLimitSettings()
        config = RuntimeRateLimitConfig.from_settings(settings)

        # RateLimitSettings defaults: enabled=True, default_requests_per_second=10
        assert config.enabled is True
        assert config.default_requests_per_second == 10.0
        assert config.default_requests_per_minute is None
        assert config.persistence_path is None
        assert config.services == {}

    def test_from_settings_converts_int_to_float(self) -> None:
        """from_settings() should convert int rates to float for protocol compliance."""
        from elspeth.contracts.config import RateLimitSettings
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        settings = RateLimitSettings(
            default_requests_per_second=10,  # int in Settings
            default_requests_per_minute=100,  # int in Settings
        )
        config = RuntimeRateLimitConfig.from_settings(settings)

        # Protocol expects float
        assert isinstance(config.default_requests_per_second, float)
        assert isinstance(config.default_requests_per_minute, float)


class TestRuntimeRateLimitConvenienceFactories:
    """Test convenience factory methods."""

    def test_default_creates_disabled_config(self) -> None:
        """default() should create a disabled rate limit config."""
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        config = RuntimeRateLimitConfig.default()

        # Default should be disabled (no rate limiting by default)
        assert config.enabled is False
        assert config.default_requests_per_second is None
        assert config.default_requests_per_minute is None
        assert config.persistence_path is None
        assert config.services == {}


class TestRuntimeRateLimitImmutability:
    """Test that RuntimeRateLimitConfig is immutable (frozen dataclass)."""

    def test_frozen_dataclass(self) -> None:
        """RuntimeRateLimitConfig should be frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        config = RuntimeRateLimitConfig.default()

        with pytest.raises(FrozenInstanceError):
            config.enabled = True  # type: ignore[misc]

    def test_has_slots(self) -> None:
        """RuntimeRateLimitConfig should use __slots__ for memory efficiency."""
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig

        assert hasattr(RuntimeRateLimitConfig, "__slots__"), "RuntimeRateLimitConfig should have __slots__"
