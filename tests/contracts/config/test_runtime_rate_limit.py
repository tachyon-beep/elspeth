# tests/contracts/config/test_runtime_rate_limit.py
"""Tests for RuntimeRateLimitConfig.

Rate-limit-specific tests only. Common tests (frozen, slots, protocol, orphan fields)
are in test_runtime_common.py.
"""


# NOTE: Protocol compliance, orphan detection, frozen/slots tests are in test_runtime_common.py


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
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig
        from elspeth.core.config import RateLimitSettings, ServiceRateLimit

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
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig
        from elspeth.core.config import RateLimitSettings

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
        from elspeth.contracts.config.runtime import RuntimeRateLimitConfig
        from elspeth.core.config import RateLimitSettings

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
