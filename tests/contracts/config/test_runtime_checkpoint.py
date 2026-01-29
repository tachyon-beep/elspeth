# tests/contracts/config/test_runtime_checkpoint.py
"""Tests for RuntimeCheckpointConfig.

TDD tests written before implementation. These verify:
1. Protocol compliance (structural typing)
2. Orphan field detection (no fields without Settings origin)
3. Field name mapping (explicit mapping assertions)
4. Factory method behavior (from_settings, default)

Note on frequency field:
    CheckpointSettings.frequency is a Literal["every_row", "every_n", "aggregation_only"]
    RuntimeCheckpointConfig.frequency is an int (checkpoint every N rows):
    - "every_row" -> 1
    - "every_n" -> checkpoint_interval value
    - "aggregation_only" -> 0

    This is documented in FIELD_MAPPINGS but the type transformation
    happens in from_settings(), not through field name mapping.
"""

import pytest


class TestRuntimeCheckpointProtocolCompliance:
    """Verify RuntimeCheckpointConfig implements RuntimeCheckpointProtocol."""

    def test_runtime_checkpoint_implements_protocol(self) -> None:
        """RuntimeCheckpointConfig must implement RuntimeCheckpointProtocol.

        This uses runtime_checkable to verify structural typing.
        """
        from elspeth.contracts.config import RuntimeCheckpointProtocol
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        # Create instance with defaults
        config = RuntimeCheckpointConfig.default()

        # Protocol check via isinstance (runtime_checkable)
        assert isinstance(config, RuntimeCheckpointProtocol), (
            "RuntimeCheckpointConfig does not implement RuntimeCheckpointProtocol. "
            "Check that all protocol properties are present with correct types."
        )

    def test_protocol_fields_have_correct_types(self) -> None:
        """Protocol fields must return correct types."""
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        config = RuntimeCheckpointConfig.default()

        assert isinstance(config.enabled, bool)
        assert isinstance(config.frequency, int)
        assert isinstance(config.aggregation_boundaries, bool)


class TestRuntimeCheckpointAllFields:
    """Verify RuntimeCheckpointConfig has all expected fields from Settings."""

    def test_has_all_settings_fields(self) -> None:
        """RuntimeCheckpointConfig must have all CheckpointSettings fields.

        CheckpointSettings has:
        - enabled: bool
        - frequency: Literal["every_row", "every_n", "aggregation_only"]
        - checkpoint_interval: int | None
        - aggregation_boundaries: bool

        RuntimeCheckpointConfig maps these to:
        - enabled: bool (direct)
        - frequency: int (computed from Settings.frequency + checkpoint_interval)
        - checkpoint_interval: int | None (preserved for full Settings fidelity)
        - aggregation_boundaries: bool (direct)
        """
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        # All 4 fields from CheckpointSettings (preserving all even if not in protocol)
        expected_fields = {
            "enabled",
            "frequency",
            "checkpoint_interval",
            "aggregation_boundaries",
        }

        actual_fields = set(RuntimeCheckpointConfig.__dataclass_fields__.keys())

        assert expected_fields == actual_fields, (
            f"RuntimeCheckpointConfig fields mismatch.\n"
            f"Missing: {expected_fields - actual_fields}\n"
            f"Extra: {actual_fields - expected_fields}"
        )


class TestRuntimeCheckpointNoOrphanFields:
    """Verify RuntimeCheckpointConfig has no orphan fields.

    Every field must come from CheckpointSettings (no internal-only fields).
    """

    def test_runtime_has_no_orphan_fields(self) -> None:
        """Every RuntimeCheckpointConfig field must have documented origin."""
        from elspeth.contracts.config import FIELD_MAPPINGS, CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        # Get all RuntimeCheckpointConfig fields
        runtime_fields = set(RuntimeCheckpointConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "CheckpointSettings"
        settings_fields = set(CheckpointSettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All runtime fields must be accounted for
        orphan_fields = runtime_fields - runtime_from_settings

        assert not orphan_fields, (
            f"RuntimeCheckpointConfig has orphan fields: {orphan_fields}. These must be mapped from CheckpointSettings."
        )

    def test_no_missing_settings_fields(self) -> None:
        """RuntimeCheckpointConfig must receive all Settings fields."""
        from elspeth.contracts.config import FIELD_MAPPINGS, CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        # Get all RuntimeCheckpointConfig fields
        runtime_fields = set(RuntimeCheckpointConfig.__dataclass_fields__.keys())

        # Get Settings fields (with their runtime names via mapping)
        settings_class = "CheckpointSettings"
        settings_fields = set(CheckpointSettings.model_fields.keys())
        field_mappings = FIELD_MAPPINGS.get(settings_class, {})

        # Map settings fields to their runtime names
        runtime_from_settings = {field_mappings.get(f, f) for f in settings_fields}

        # All settings fields must exist in runtime
        missing_fields = runtime_from_settings - runtime_fields

        assert not missing_fields, (
            f"RuntimeCheckpointConfig is missing Settings fields: {missing_fields}. Add these fields to RuntimeCheckpointConfig."
        )


class TestCheckpointFieldNameMapping:
    """Verify field name mappings are correct.

    CheckpointSettings uses same field names as RuntimeCheckpointConfig,
    so there should be NO entries in FIELD_MAPPINGS.

    Note: The 'frequency' field has a TYPE transformation (Literal -> int)
    but not a NAME change, so it's not in FIELD_MAPPINGS.
    """

    def test_no_field_name_mappings_needed(self) -> None:
        """CheckpointSettings uses same names - no mappings needed."""
        from elspeth.contracts.config import FIELD_MAPPINGS

        # CheckpointSettings should not have any field mappings
        # because all field names are the same between Settings and Runtime
        mappings = FIELD_MAPPINGS.get("CheckpointSettings", {})

        assert mappings == {}, f"CheckpointSettings should have no field mappings (same names), but found: {mappings}"


class TestRuntimeCheckpointFromSettings:
    """Test from_settings() factory method."""

    def test_from_settings_every_row(self) -> None:
        """from_settings() with frequency='every_row' produces frequency=1."""
        from elspeth.contracts.config import CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        settings = CheckpointSettings(
            enabled=True,
            frequency="every_row",
            aggregation_boundaries=True,
        )

        config = RuntimeCheckpointConfig.from_settings(settings)

        assert config.enabled is True
        assert config.frequency == 1, "every_row should map to frequency=1"
        assert config.checkpoint_interval is None
        assert config.aggregation_boundaries is True

    def test_from_settings_every_n(self) -> None:
        """from_settings() with frequency='every_n' uses checkpoint_interval."""
        from elspeth.contracts.config import CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        settings = CheckpointSettings(
            enabled=True,
            frequency="every_n",
            checkpoint_interval=50,
            aggregation_boundaries=False,
        )

        config = RuntimeCheckpointConfig.from_settings(settings)

        assert config.enabled is True
        assert config.frequency == 50, "every_n should map to checkpoint_interval value"
        assert config.checkpoint_interval == 50
        assert config.aggregation_boundaries is False

    def test_from_settings_aggregation_only(self) -> None:
        """from_settings() with frequency='aggregation_only' produces frequency=0."""
        from elspeth.contracts.config import CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        settings = CheckpointSettings(
            enabled=True,
            frequency="aggregation_only",
            aggregation_boundaries=True,
        )

        config = RuntimeCheckpointConfig.from_settings(settings)

        assert config.enabled is True
        assert config.frequency == 0, "aggregation_only should map to frequency=0"
        assert config.checkpoint_interval is None
        assert config.aggregation_boundaries is True

    def test_from_settings_disabled(self) -> None:
        """from_settings() preserves enabled=False."""
        from elspeth.contracts.config import CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        settings = CheckpointSettings(
            enabled=False,
            frequency="every_row",
            aggregation_boundaries=True,
        )

        config = RuntimeCheckpointConfig.from_settings(settings)

        assert config.enabled is False

    def test_from_settings_with_defaults(self) -> None:
        """from_settings() should handle default values from Settings."""
        from elspeth.contracts.config import CheckpointSettings
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        # Use Settings defaults
        settings = CheckpointSettings()
        config = RuntimeCheckpointConfig.from_settings(settings)

        # CheckpointSettings defaults:
        # enabled=True, frequency="every_row", checkpoint_interval=None, aggregation_boundaries=True
        assert config.enabled is True
        assert config.frequency == 1  # "every_row" -> 1
        assert config.checkpoint_interval is None
        assert config.aggregation_boundaries is True


class TestRuntimeCheckpointConvenienceFactories:
    """Test convenience factory methods."""

    def test_default_creates_enabled_every_row_config(self) -> None:
        """default() should create an enabled every-row checkpoint config.

        This matches CheckpointSettings defaults.
        """
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        config = RuntimeCheckpointConfig.default()

        # Defaults match CheckpointSettings: enabled, every_row (frequency=1), aggregation_boundaries
        assert config.enabled is True
        assert config.frequency == 1  # "every_row" -> 1
        assert config.checkpoint_interval is None
        assert config.aggregation_boundaries is True


class TestRuntimeCheckpointImmutability:
    """Test that RuntimeCheckpointConfig is immutable (frozen dataclass)."""

    def test_frozen_dataclass(self) -> None:
        """RuntimeCheckpointConfig should be frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        config = RuntimeCheckpointConfig.default()

        with pytest.raises(FrozenInstanceError):
            config.enabled = False  # type: ignore[misc]

    def test_has_slots(self) -> None:
        """RuntimeCheckpointConfig should use __slots__ for memory efficiency."""
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        assert hasattr(RuntimeCheckpointConfig, "__slots__"), "RuntimeCheckpointConfig should have __slots__"


class TestRuntimeCheckpointValidation:
    """Test validation in RuntimeCheckpointConfig."""

    def test_frequency_must_be_non_negative(self) -> None:
        """frequency < 0 should raise ValueError."""
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig

        with pytest.raises(ValueError, match="frequency must be >= 0"):
            RuntimeCheckpointConfig(
                enabled=True,
                frequency=-1,
                checkpoint_interval=None,
                aggregation_boundaries=True,
            )
