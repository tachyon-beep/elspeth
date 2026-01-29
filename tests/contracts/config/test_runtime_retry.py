# tests/contracts/config/test_runtime_retry.py
"""Tests for RuntimeRetryConfig.

TDD tests written before implementation. These verify:
1. Protocol compliance (structural typing)
2. Orphan field detection (no fields without Settings or INTERNAL origin)
3. Field name mapping (explicit mapping assertions)
4. Factory method behavior (from_settings, from_policy, default, no_retry)
"""

import pytest


class TestRuntimeRetryProtocolCompliance:
    """Verify RuntimeRetryConfig implements RuntimeRetryProtocol."""

    def test_runtime_retry_implements_protocol(self) -> None:
        """RuntimeRetryConfig must implement RuntimeRetryProtocol.

        This uses runtime_checkable to verify structural typing.
        """
        from elspeth.contracts.config import RuntimeRetryProtocol
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Create instance with defaults
        config = RuntimeRetryConfig.default()

        # Protocol check via isinstance (runtime_checkable)
        assert isinstance(config, RuntimeRetryProtocol), (
            "RuntimeRetryConfig does not implement RuntimeRetryProtocol. Check that all protocol properties are present with correct types."
        )

    def test_protocol_fields_have_correct_types(self) -> None:
        """Protocol fields must return correct types."""
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        config = RuntimeRetryConfig.default()

        assert isinstance(config.max_attempts, int)
        assert isinstance(config.base_delay, float)
        assert isinstance(config.max_delay, float)
        assert isinstance(config.exponential_base, float)


class TestRuntimeRetryNoOrphanFields:
    """Verify RuntimeRetryConfig has no orphan fields.

    Every field must be documented as either:
    - Coming from RetrySettings (possibly renamed)
    - Being INTERNAL (hardcoded, documented in INTERNAL_DEFAULTS)
    """

    def test_runtime_has_no_orphan_fields(self) -> None:
        """Every RuntimeRetryConfig field must have documented origin."""
        from elspeth.contracts.config import FIELD_MAPPINGS, INTERNAL_DEFAULTS, RetrySettings
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Get all RuntimeRetryConfig fields
        runtime_fields = set(RuntimeRetryConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "RetrySettings"
        settings_fields = set(RetrySettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # Get internal-only fields from INTERNAL_DEFAULTS
        internal_fields = set(INTERNAL_DEFAULTS.get("retry", {}).keys())

        # All runtime fields must be accounted for
        expected_fields = runtime_from_settings | internal_fields
        orphan_fields = runtime_fields - expected_fields

        assert not orphan_fields, (
            f"RuntimeRetryConfig has orphan fields: {orphan_fields}. "
            f"These must either be:\n"
            f"  1. Mapped from RetrySettings (add to FIELD_MAPPINGS if renamed)\n"
            f"  2. Documented as internal (add to INTERNAL_DEFAULTS['retry'])"
        )

    def test_no_missing_settings_fields(self) -> None:
        """RuntimeRetryConfig must receive all Settings fields."""
        from elspeth.contracts.config import FIELD_MAPPINGS, RetrySettings
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Get all RuntimeRetryConfig fields
        runtime_fields = set(RuntimeRetryConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "RetrySettings"
        settings_fields = set(RetrySettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All settings fields must exist in runtime
        missing_fields = runtime_from_settings - runtime_fields

        assert not missing_fields, (
            f"RuntimeRetryConfig is missing Settings fields: {missing_fields}. Add these fields to RuntimeRetryConfig."
        )


class TestRetryFieldNameMapping:
    """Verify field name mappings are correct and complete."""

    def test_retry_field_name_mapping(self) -> None:
        """Explicit assertion of all field name mappings."""
        from elspeth.contracts.config import FIELD_MAPPINGS

        # These are the expected mappings (documented in task)
        expected_mappings = {
            "initial_delay_seconds": "base_delay",
            "max_delay_seconds": "max_delay",
        }

        actual_mappings = FIELD_MAPPINGS.get("RetrySettings", {})

        assert actual_mappings == expected_mappings, (
            f"RetrySettings field mappings incorrect.\nExpected: {expected_mappings}\nActual: {actual_mappings}"
        )

    def test_same_name_fields_not_in_mapping(self) -> None:
        """Fields with same name in Settings and Runtime should NOT be in FIELD_MAPPINGS."""
        from elspeth.contracts.config import FIELD_MAPPINGS

        mappings = FIELD_MAPPINGS.get("RetrySettings", {})

        # These fields have the SAME name in both - should not be in mapping
        same_name_fields = {"max_attempts", "exponential_base"}

        for field in same_name_fields:
            assert field not in mappings, (
                f"Field '{field}' has same name in Settings and Runtime - should not be in FIELD_MAPPINGS (only list renames)"
            )


class TestRuntimeRetryFromSettings:
    """Test from_settings() factory method."""

    def test_from_settings_maps_all_fields(self) -> None:
        """from_settings() must map all Settings fields correctly."""
        from elspeth.contracts.config import RetrySettings
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Use non-default values to catch forgotten mappings
        settings = RetrySettings(
            max_attempts=99,
            initial_delay_seconds=99.0,
            max_delay_seconds=999.0,
            exponential_base=9.9,
        )

        config = RuntimeRetryConfig.from_settings(settings)

        # Verify field mapping
        assert config.max_attempts == 99, "max_attempts not mapped correctly"
        assert config.base_delay == 99.0, "initial_delay_seconds -> base_delay not mapped"
        assert config.max_delay == 999.0, "max_delay_seconds -> max_delay not mapped"
        assert config.exponential_base == 9.9, "exponential_base not mapped correctly"

    def test_from_settings_uses_internal_jitter(self) -> None:
        """from_settings() must use internal default for jitter."""
        from elspeth.contracts.config import INTERNAL_DEFAULTS, RetrySettings
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        settings = RetrySettings()
        config = RuntimeRetryConfig.from_settings(settings)

        expected_jitter = INTERNAL_DEFAULTS["retry"]["jitter"]
        assert config.jitter == expected_jitter, f"jitter should be {expected_jitter} (from INTERNAL_DEFAULTS), got {config.jitter}"


class TestRuntimeRetryFromPolicy:
    """Test from_policy() factory method."""

    def test_from_policy_none_returns_no_retry(self) -> None:
        """from_policy(None) should return no_retry config."""
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        config = RuntimeRetryConfig.from_policy(None)

        assert config.max_attempts == 1, "from_policy(None) should return no_retry (max_attempts=1)"

    def test_from_policy_uses_provided_values(self) -> None:
        """from_policy() should use values from RetryPolicy dict."""
        from elspeth.contracts import RetryPolicy
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        policy: RetryPolicy = {
            "max_attempts": 5,
            "base_delay": 2.0,
            "max_delay": 120.0,
            "jitter": 0.5,
            "exponential_base": 3.0,
        }

        config = RuntimeRetryConfig.from_policy(policy)

        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.jitter == 0.5
        assert config.exponential_base == 3.0

    def test_from_policy_partial_uses_defaults(self) -> None:
        """from_policy() with partial dict should use POLICY_DEFAULTS."""
        from elspeth.contracts import RetryPolicy
        from elspeth.contracts.config import POLICY_DEFAULTS
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Only provide max_attempts, rest should use defaults
        policy: RetryPolicy = {"max_attempts": 7}

        config = RuntimeRetryConfig.from_policy(policy)

        assert config.max_attempts == 7
        assert config.base_delay == POLICY_DEFAULTS["base_delay"]
        assert config.max_delay == POLICY_DEFAULTS["max_delay"]
        assert config.jitter == POLICY_DEFAULTS["jitter"]
        assert config.exponential_base == POLICY_DEFAULTS["exponential_base"]

    def test_from_policy_clamps_invalid_values(self) -> None:
        """from_policy() should clamp values to safe minimums."""
        from elspeth.contracts import RetryPolicy
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        # Invalid values that need clamping
        policy: RetryPolicy = {
            "max_attempts": 0,  # Must be >= 1
            "base_delay": 0.0,  # Must be > 0
            "max_delay": 0.0,  # Must be > 0
            "jitter": -1.0,  # Must be >= 0
            "exponential_base": 0.5,  # Must be > 1
        }

        config = RuntimeRetryConfig.from_policy(policy)

        assert config.max_attempts >= 1, "max_attempts must be clamped to >= 1"
        assert config.base_delay > 0, "base_delay must be clamped to > 0"
        assert config.max_delay > 0, "max_delay must be clamped to > 0"
        assert config.jitter >= 0, "jitter must be clamped to >= 0"
        assert config.exponential_base > 1, "exponential_base must be clamped to > 1"


class TestRuntimeRetryConvenienceFactories:
    """Test convenience factory methods."""

    def test_default_uses_policy_defaults(self) -> None:
        """default() should create config with POLICY_DEFAULTS values."""
        from elspeth.contracts.config import POLICY_DEFAULTS
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        config = RuntimeRetryConfig.default()

        assert config.max_attempts == POLICY_DEFAULTS["max_attempts"]
        assert config.base_delay == POLICY_DEFAULTS["base_delay"]
        assert config.max_delay == POLICY_DEFAULTS["max_delay"]
        assert config.jitter == POLICY_DEFAULTS["jitter"]
        assert config.exponential_base == POLICY_DEFAULTS["exponential_base"]

    def test_no_retry_single_attempt(self) -> None:
        """no_retry() should create config with max_attempts=1."""
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        config = RuntimeRetryConfig.no_retry()

        assert config.max_attempts == 1, "no_retry should have max_attempts=1"


class TestRuntimeRetryImmutability:
    """Test that RuntimeRetryConfig is immutable (frozen dataclass)."""

    def test_frozen_dataclass(self) -> None:
        """RuntimeRetryConfig should be frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        config = RuntimeRetryConfig.default()

        with pytest.raises(FrozenInstanceError):
            config.max_attempts = 10  # type: ignore[misc]

    def test_has_slots(self) -> None:
        """RuntimeRetryConfig should use __slots__ for memory efficiency."""
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        assert hasattr(RuntimeRetryConfig, "__slots__"), "RuntimeRetryConfig should have __slots__"


class TestRuntimeRetryValidation:
    """Test validation in RuntimeRetryConfig."""

    def test_max_attempts_must_be_positive(self) -> None:
        """max_attempts < 1 should raise ValueError."""
        from elspeth.contracts.config.runtime import RuntimeRetryConfig

        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RuntimeRetryConfig(
                max_attempts=0,
                base_delay=1.0,
                max_delay=60.0,
                jitter=1.0,
                exponential_base=2.0,
            )
