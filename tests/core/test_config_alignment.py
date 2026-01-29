# tests/core/test_config_alignment.py
"""Config alignment tests - catch field orphaning before it becomes a bug.

These tests verify that Settings fields are actually wired to runtime code.
They serve as:
1. Documentation of which fields are used vs. pending implementation
2. Early warning when someone adds a field but forgets to wire it
3. Refactoring guide showing what needs to be connected

P2-2026-01-21 bug: exponential_base was added to RetrySettings but never
mapped to RuntimeRetryConfig. That bug motivated this comprehensive audit.

## Field Orphaning Categories

- WIRED: Field is used at runtime (tested in runtime_fields)
- PENDING: Field exists but implementation is not yet complete (documented)
- INTERNAL: Field used for validation/defaults only, not runtime behavior

## When These Tests Fail

If a test fails after adding a new field to a Settings class:
1. If the field IS wired: Add it to the test's runtime_fields set
2. If the field is NOT wired yet: Add it to pending_fields with a comment
3. If the field is internal-only: Add it to internal_fields with explanation
"""

from typing import ClassVar

import pytest


class TestRetryConfigAlignment:
    """Verify RetrySettings ↔ RetryConfig ↔ RetryPolicy alignment.

    RetrySettings is the only Settings class with a separate runtime
    dataclass (RetryConfig). This pattern requires careful alignment.
    """

    # Fields mapped between Settings and Config (may have different names)
    FIELD_MAPPINGS: ClassVar[dict[str, str]] = {
        "initial_delay_seconds": "base_delay",
        "max_delay_seconds": "max_delay",
    }

    # Fields in Config that don't come from Settings
    CONFIG_INTERNAL_ONLY: ClassVar[set[str]] = {"jitter"}

    def test_settings_fields_exist_in_config(self) -> None:
        """Every RetrySettings field must have a corresponding RetryConfig field."""
        from elspeth.core.config import RetrySettings
        from elspeth.contracts.config import RuntimeRetryConfig

        settings_fields = set(RetrySettings.model_fields.keys())
        config_fields = set(RuntimeRetryConfig.__dataclass_fields__.keys())

        expected_in_config = {self.FIELD_MAPPINGS.get(f, f) for f in settings_fields}

        missing = expected_in_config - config_fields
        assert not missing, f"RetrySettings fields not in RetryConfig: {missing}. Add these to RetryConfig and wire in from_settings()."

    def test_config_covers_settings(self) -> None:
        """RetryConfig should not have unexpected fields beyond Settings + internals."""
        from elspeth.core.config import RetrySettings
        from elspeth.contracts.config import RuntimeRetryConfig

        settings_fields = set(RetrySettings.model_fields.keys())
        config_fields = set(RuntimeRetryConfig.__dataclass_fields__.keys())

        expected = {self.FIELD_MAPPINGS.get(f, f) for f in settings_fields} | self.CONFIG_INTERNAL_ONLY

        unexpected = config_fields - expected
        assert not unexpected, f"RetryConfig has undocumented fields: {unexpected}. Add to Settings, CONFIG_INTERNAL_ONLY, or remove."

    def test_policy_matches_config(self) -> None:
        """RetryPolicy TypedDict should have same fields as RuntimeRetryConfig."""
        from elspeth.contracts import RetryPolicy
        from elspeth.contracts.config import RuntimeRetryConfig

        policy_fields = set(RetryPolicy.__annotations__.keys())
        config_fields = set(RuntimeRetryConfig.__dataclass_fields__.keys())

        assert policy_fields == config_fields, (
            f"RetryPolicy/RetryConfig mismatch. "
            f"Missing from Policy: {config_fields - policy_fields}, "
            f"Missing from Config: {policy_fields - config_fields}"
        )

    def test_from_settings_maps_all_fields(self) -> None:
        """Verify from_settings() uses non-default values (catches forgotten mappings)."""
        from elspeth.core.config import RetrySettings
        from elspeth.contracts.config import RuntimeRetryConfig

        settings = RetrySettings(
            max_attempts=99,
            initial_delay_seconds=99.0,
            max_delay_seconds=999.0,
            exponential_base=9.9,
        )
        config = RuntimeRetryConfig.from_settings(settings)

        assert config.max_attempts == 99
        assert config.base_delay == 99.0
        assert config.max_delay == 999.0
        assert config.exponential_base == 9.9
        assert config.jitter == 1.0  # internal default


class TestConcurrencySettingsAlignment:
    """Verify ConcurrencySettings field usage.

    STATUS: PENDING IMPLEMENTATION
    The max_workers field exists but is never passed to runtime components.
    Plugins that need concurrency (LLM, Azure) use their own settings.
    """

    # Fields that SHOULD be wired but aren't yet
    PENDING_FIELDS: ClassVar[set[str]] = {
        "max_workers",  # TODO: Pass to Orchestrator/ThreadPoolExecutor
    }

    def test_documents_pending_fields(self) -> None:
        """Document which fields are pending implementation."""
        from elspeth.core.config import ConcurrencySettings

        actual_fields = set(ConcurrencySettings.model_fields.keys())

        # This test passes as documentation - update when fields are wired
        assert actual_fields == self.PENDING_FIELDS, (
            f"ConcurrencySettings fields changed. "
            f"New fields: {actual_fields - self.PENDING_FIELDS}, "
            f"Removed: {self.PENDING_FIELDS - actual_fields}. "
            f"Update PENDING_FIELDS or add wiring tests."
        )

    @pytest.mark.xfail(reason="max_workers not yet wired to runtime")
    def test_max_workers_used_at_runtime(self) -> None:
        """max_workers should control thread pool size.

        This test is expected to fail until ConcurrencySettings is
        wired to Orchestrator or plugin execution.
        """
        # When implemented, this should verify:
        # 1. Orchestrator accepts concurrency_settings parameter
        # 2. ThreadPoolExecutor uses max_workers from settings
        pytest.fail("ConcurrencySettings.max_workers not implemented")


class TestRateLimitSettingsAlignment:
    """Verify RateLimitSettings field usage.

    STATUS: PENDING IMPLEMENTATION
    RateLimitRegistry exists and is well-designed, but never instantiated
    from CLI code paths. All 5 fields are orphaned.
    """

    # All fields pending - registry never instantiated
    PENDING_FIELDS: ClassVar[set[str]] = {
        "enabled",
        "default_requests_per_second",
        "default_requests_per_minute",
        "persistence_path",
        "services",
    }

    def test_documents_pending_fields(self) -> None:
        """Document which fields are pending implementation."""
        from elspeth.core.config import RateLimitSettings

        actual_fields = set(RateLimitSettings.model_fields.keys())

        assert actual_fields == self.PENDING_FIELDS, "RateLimitSettings fields changed. Update PENDING_FIELDS."

    @pytest.mark.xfail(reason="RateLimitRegistry never instantiated from CLI")
    def test_registry_instantiated_from_settings(self) -> None:
        """RateLimitRegistry should be created from RateLimitSettings.

        The registry class exists and has proper from_settings pattern,
        but CLI never calls it. This test documents the gap.
        """
        pytest.fail("RateLimitRegistry not wired to CLI execution path")


class TestLandscapeSettingsAlignment:
    """Verify LandscapeSettings field usage."""

    # Fields actively used at runtime
    WIRED_FIELDS: ClassVar[set[str]] = {
        "url",  # Used in LandscapeDB.from_url()
    }

    # Nested settings object - checked separately
    NESTED_FIELDS: ClassVar[set[str]] = {
        "export",  # LandscapeExportSettings - has its own wiring
    }

    # Fields that exist but aren't checked at runtime
    PENDING_FIELDS: ClassVar[set[str]] = {
        "enabled",  # Always assumed True
        "backend",  # Not validated beyond schema
    }

    def test_field_categorization_complete(self) -> None:
        """All fields must be categorized."""
        from elspeth.core.config import LandscapeSettings

        actual_fields = set(LandscapeSettings.model_fields.keys())
        categorized = self.WIRED_FIELDS | self.NESTED_FIELDS | self.PENDING_FIELDS

        assert actual_fields == categorized, (
            f"Uncategorized fields: {actual_fields - categorized}. Add to WIRED_FIELDS, NESTED_FIELDS, or PENDING_FIELDS."
        )

    def test_export_settings_wired(self) -> None:
        """LandscapeExportSettings fields should all be used."""
        from elspeth.core.config import LandscapeExportSettings

        # These are all accessed in orchestrator export logic
        expected_fields = {"enabled", "sink", "format", "sign"}
        actual_fields = set(LandscapeExportSettings.model_fields.keys())

        assert actual_fields == expected_fields, (
            "LandscapeExportSettings fields changed. Verify new fields are used in Orchestrator.run()/resume()."
        )


class TestCheckpointSettingsAlignment:
    """Verify CheckpointSettings field usage.

    STATUS: PARTIALLY WIRED
    Fields are used during resume but not during normal run.
    aggregation_boundaries is never checked.
    """

    # Fields used during resume
    WIRED_IN_RESUME: ClassVar[set[str]] = {
        "enabled",
        "frequency",
        "checkpoint_interval",
    }

    # Fields that exist but are never checked
    PENDING_FIELDS: ClassVar[set[str]] = {
        "aggregation_boundaries",  # Documented but not implemented
    }

    def test_field_categorization_complete(self) -> None:
        """All fields must be categorized."""
        from elspeth.core.config import CheckpointSettings

        actual_fields = set(CheckpointSettings.model_fields.keys())
        categorized = self.WIRED_IN_RESUME | self.PENDING_FIELDS

        assert actual_fields == categorized, (
            f"Uncategorized fields: {actual_fields - categorized}. Add to WIRED_IN_RESUME or PENDING_FIELDS."
        )

    @pytest.mark.xfail(reason="Checkpointing only active during resume, not normal run")
    def test_checkpoint_settings_used_in_normal_run(self) -> None:
        """CheckpointSettings should be passed to Orchestrator for normal runs.

        Currently checkpoint_settings is only passed during resume,
        meaning checkpointing is disabled for normal runs.
        """
        pytest.fail("CheckpointSettings not passed to Orchestrator for normal run")


class TestPayloadStoreSettingsAlignment:
    """Verify PayloadStoreSettings field usage.

    STATUS: FULLY WIRED
    All fields are accessed in CLI for store initialization and purge.
    """

    WIRED_FIELDS: ClassVar[set[str]] = {
        "backend",  # Validated in CLI (must be "filesystem")
        "base_path",  # Passed to FilesystemPayloadStore
        "retention_days",  # Used in purge command
    }

    def test_all_fields_wired(self) -> None:
        """All PayloadStoreSettings fields should be wired."""
        from elspeth.core.config import PayloadStoreSettings

        actual_fields = set(PayloadStoreSettings.model_fields.keys())

        assert actual_fields == self.WIRED_FIELDS, (
            f"PayloadStoreSettings fields changed. "
            f"New: {actual_fields - self.WIRED_FIELDS}, "
            f"Removed: {self.WIRED_FIELDS - actual_fields}. "
            f"Ensure new fields are wired in CLI."
        )


class TestElspethSettingsAlignment:
    """Verify top-level ElspethSettings structure."""

    # Pipeline definition fields (core pipeline config)
    PIPELINE_FIELDS: ClassVar[set[str]] = {
        "source",  # Required - source plugin config
        "transforms",  # Optional - transform chain
        "sinks",  # Required - named sink configs
        "default_sink",  # Required - default output sink name
        "gates",  # Optional - config-driven routing
        "coalesce",  # Optional - fork path merging
        "aggregations",  # Optional - config-driven batching
    }

    # Run mode fields (how to execute)
    RUN_MODE_FIELDS: ClassVar[set[str]] = {
        "run_mode",  # live, replay, or verify
        "replay_from",  # run ID for replay/verify modes
    }

    # Subsystem settings (infrastructure config)
    SUBSYSTEM_SETTINGS: ClassVar[set[str]] = {
        "landscape",  # Audit trail database
        "concurrency",  # Thread pool size (PENDING - not wired)
        "rate_limit",  # Rate limiting (PENDING - not wired)
        "checkpoint",  # Crash recovery
        "retry",  # Retry behavior
        "payload_store",  # Large blob storage
    }

    ALL_EXPECTED: ClassVar[set[str]] = PIPELINE_FIELDS | RUN_MODE_FIELDS | SUBSYSTEM_SETTINGS

    def test_all_fields_categorized(self) -> None:
        """All ElspethSettings fields must be categorized."""
        from elspeth.core.config import ElspethSettings

        actual_fields = set(ElspethSettings.model_fields.keys())

        missing = actual_fields - self.ALL_EXPECTED
        extra = self.ALL_EXPECTED - actual_fields

        assert not missing, (
            f"Uncategorized fields in ElspethSettings: {missing}. Add to PIPELINE_FIELDS, RUN_MODE_FIELDS, or SUBSYSTEM_SETTINGS."
        )
        assert not extra, f"Expected fields not in ElspethSettings: {extra}. Remove from test expectations."

    def test_subsystem_settings_have_alignment_tests(self) -> None:
        """Each subsystem setting should have its own alignment test class."""
        # This test documents which subsystems have alignment tests
        # Add a class when wiring a new subsystem
        tested_subsystems = {
            "landscape",  # TestLandscapeSettingsAlignment
            "checkpoint",  # TestCheckpointSettingsAlignment
            "retry",  # TestRetryConfigAlignment
            "payload_store",  # TestPayloadStoreSettingsAlignment
            "concurrency",  # TestConcurrencySettingsAlignment (xfail - pending)
            "rate_limit",  # TestRateLimitSettingsAlignment (xfail - pending)
        }

        assert tested_subsystems == self.SUBSYSTEM_SETTINGS, (
            f"Subsystem alignment test mismatch. Missing tests: {self.SUBSYSTEM_SETTINGS - tested_subsystems}"
        )
