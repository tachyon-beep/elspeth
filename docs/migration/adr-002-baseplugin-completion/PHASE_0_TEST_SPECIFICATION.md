# Phase 0: Safety Net Test Specification

**Objective**: Build comprehensive test coverage proving ADR-002 validation currently short-circuits

**Estimated Effort**: 2-3 hours
**File**: `tests/test_adr002_baseplugin_compliance.py`

---

## Test Categories

### Category 1: Characterization Tests (Document Current State)

**Purpose**: Prove plugins DON'T currently implement BasePlugin

```python
"""Test that plugins currently lack BasePlugin methods (CHARACTERIZATION)."""

import pytest
from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource
from elspeth.plugins.nodes.sources.csv_local import CSVLocalDataSource
from elspeth.plugins.nodes.sinks.csv_file import CSVFileSink


class TestCurrentStateDatasources:
    """Characterization: Datasources currently missing BasePlugin methods."""

    def test_basecsvdatasource_no_get_security_level(self, tmp_path):
        """BaseCSVDataSource currently lacks get_security_level() method."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(ds, "get_security_level")
        # But attribute does exist
        assert hasattr(ds, "security_level")
        assert ds.security_level == SecurityLevel.SECRET

    def test_basecsvdatasource_no_validate_method(self, tmp_path):
        """BaseCSVDataSource currently lacks validate_can_operate_at_level() method."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(ds, "validate_can_operate_at_level")

    def test_all_datasource_classes_missing_methods(self, tmp_path):
        """All 4 datasource classes currently lack BasePlugin methods."""
        from elspeth.plugins.nodes.sources.csv_blob import CSVBlobDataSource
        from elspeth.plugins.nodes.sources.blob import BlobDataSource

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        datasource_classes = [
            (BaseCSVDataSource, {"path": str(csv_file), "retain_local": False}),
            (CSVLocalDataSource, {"path": str(csv_file), "retain_local": False}),
            # Note: CSVBlobDataSource, BlobDataSource require Azure credentials - skip for now
        ]

        for cls, kwargs in datasource_classes:
            ds = cls(**kwargs, security_level=SecurityLevel.OFFICIAL)

            # CHARACTERIZATION: Both methods missing
            assert not hasattr(ds, "get_security_level"), \
                f"{cls.__name__} unexpectedly has get_security_level()"
            assert not hasattr(ds, "validate_can_operate_at_level"), \
                f"{cls.__name__} unexpectedly has validate_can_operate_at_level()"


class TestCurrentStateSinks:
    """Characterization: Sinks currently missing BasePlugin methods."""

    def test_csvfilesink_no_get_security_level(self, tmp_path):
        """CSVFileSink currently lacks get_security_level() method."""
        output = tmp_path / "output.csv"

        sink = CSVFileSink(
            path=str(output),
            security_level=SecurityLevel.UNOFFICIAL
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(sink, "get_security_level")
        # But attribute does exist
        assert hasattr(sink, "security_level")
        assert sink.security_level == SecurityLevel.UNOFFICIAL

    def test_csvfilesink_no_validate_method(self, tmp_path):
        """CSVFileSink currently lacks validate_can_operate_at_level() method."""
        output = tmp_path / "output.csv"

        sink = CSVFileSink(
            path=str(output),
            security_level=SecurityLevel.UNOFFICIAL
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(sink, "validate_can_operate_at_level")
```

---

### Category 2: Security Bug Tests (Prove Validation Skips)

**Purpose**: Demonstrate SECRET→UNOFFICIAL flows unchecked

```python
"""Test that validation currently short-circuits (SECURITY BUG)."""

import pandas as pd
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner


class TestValidationShortCircuits:
    """Security bug: Validation doesn't run due to hasattr short-circuit."""

    def test_secret_to_unofficial_currently_allowed(self, tmp_path):
        """SECURITY BUG: SECRET datasource → UNOFFICIAL sink currently allowed."""
        # Create SECRET datasource
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("password,ssn\nABC123,111-11-1111\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Create UNOFFICIAL sink
        public_output = tmp_path / "public.csv"
        unofficial_sink = CSVFileSink(
            path=str(public_output),
            security_level=SecurityLevel.UNOFFICIAL
        )

        # Build minimal experiment config
        experiment_config = {
            "name": "security_bypass_test",
            "datasource": secret_ds,
            "sinks": [unofficial_sink],
            # ... other required config
        }

        # ❌ SECURITY BUG: This currently SUCCEEDS (should FAIL!)
        runner = ExperimentSuiteRunner(...)
        result = runner.run(experiment_config)

        # Data flowed unchecked!
        assert result["status"] == "success"  # ← WRONG!
        assert public_output.exists()  # ← SECRET data in UNOFFICIAL file!

        # Read output to confirm data leaked
        output_df = pd.read_csv(public_output)
        assert "password" in output_df.columns  # ← CLASSIFICATION BREACH!

    def test_hasattr_check_returns_false(self, tmp_path):
        """Prove hasattr checks return False (causing short-circuit)."""
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("col1\n1\n")

        ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # The check that suite_runner.py uses
        has_method = hasattr(ds, "validate_can_operate_at_level")

        # PROOF: Returns False → validation skips!
        assert has_method is False
```

---

### Category 3: Security Property Tests (Define Success)

**Purpose**: Tests that MUST pass after implementation (currently xfail)

```python
"""Test ADR-002 security properties (MUST work after fix)."""


class TestSecurityPropertiesAfterFix:
    """Security properties that MUST hold after BasePlugin implementation."""

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_secret_datasource_unofficial_sink_blocked(self, tmp_path):
        """SECRET datasource → UNOFFICIAL sink MUST be blocked by validation."""
        from elspeth.core.validation.base import SecurityValidationError

        # Create SECRET datasource
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("password\nABC123\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Create UNOFFICIAL sink
        public_output = tmp_path / "public.csv"
        unofficial_sink = CSVFileSink(
            path=str(public_output),
            security_level=SecurityLevel.UNOFFICIAL
        )

        # Minimal experiment config
        experiment_config = create_experiment_config(
            datasource=secret_ds,
            sinks=[unofficial_sink]
        )

        # MUST raise SecurityValidationError during _validate_component_clearances
        with pytest.raises(SecurityValidationError) as exc_info:
            runner = ExperimentSuiteRunner(...)
            runner.run(experiment_config)

        # Verify error message mentions the mismatch
        error_msg = str(exc_info.value).lower()
        assert "secret" in error_msg
        assert "unofficial" in error_msg

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_unofficial_datasource_secret_sink_allowed(self, tmp_path):
        """UNOFFICIAL datasource → SECRET sink MUST be allowed (uplifting)."""
        # Create UNOFFICIAL datasource
        public_csv = tmp_path / "public.csv"
        public_csv.write_text("data\n123\n")

        unofficial_ds = BaseCSVDataSource(
            path=str(public_csv),
            retain_local=False,
            security_level=SecurityLevel.UNOFFICIAL
        )

        # Create SECRET sink
        secret_output = tmp_path / "secret.csv"
        secret_sink = CSVFileSink(
            path=str(secret_output),
            security_level=SecurityLevel.SECRET
        )

        # Minimal experiment config
        experiment_config = create_experiment_config(
            datasource=unofficial_ds,
            sinks=[secret_sink]
        )

        # MUST succeed (uplifting is allowed)
        runner = ExperimentSuiteRunner(...)
        result = runner.run(experiment_config)

        assert result["status"] == "success"
        assert secret_output.exists()

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_all_datasources_implement_baseplugin(self, tmp_path):
        """All datasource classes MUST implement BasePlugin protocol after fix."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1\n1\n")

        datasource_classes = [
            (BaseCSVDataSource, {"path": str(csv_file), "retain_local": False}),
            (CSVLocalDataSource, {"path": str(csv_file), "retain_local": False}),
        ]

        for cls, kwargs in datasource_classes:
            ds = cls(**kwargs, security_level=SecurityLevel.OFFICIAL)

            # MUST have both methods
            assert hasattr(ds, "get_security_level"), \
                f"{cls.__name__} missing get_security_level()"
            assert hasattr(ds, "validate_can_operate_at_level"), \
                f"{cls.__name__} missing validate_can_operate_at_level()"

            # Methods MUST be callable
            assert callable(getattr(ds, "get_security_level"))
            assert callable(getattr(ds, "validate_can_operate_at_level"))

            # get_security_level() MUST return correct value
            level = ds.get_security_level()
            assert isinstance(level, SecurityLevel)
            assert level == SecurityLevel.OFFICIAL

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_validate_can_operate_at_level_raises_correctly(self, tmp_path):
        """validate_can_operate_at_level() MUST raise when level mismatch."""
        from elspeth.core.validation.base import SecurityValidationError

        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("col1\n1\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Operating at OFFICIAL level (lower than SECRET)
        with pytest.raises(SecurityValidationError) as exc_info:
            secret_ds.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        # Error message MUST be informative
        error_msg = str(exc_info.value)
        assert "BaseCSVDataSource" in error_msg
        assert "SECRET" in error_msg
        assert "OFFICIAL" in error_msg

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_validate_can_operate_at_level_succeeds_when_safe(self, tmp_path):
        """validate_can_operate_at_level() MUST succeed when level matches."""
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("col1\n1\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Operating at SECRET level (matches) - should NOT raise
        secret_ds.validate_can_operate_at_level(SecurityLevel.SECRET)

        # Operating at TOP_SECRET level (higher) - should NOT raise
        secret_ds.validate_can_operate_at_level(SecurityLevel.TOP_SECRET)
```

---

### Category 4: Registry Enforcement Tests (Registration-Time)

**Purpose**: Verify plugins WITHOUT BasePlugin methods are **rejected at registration time**

```python
"""Test that plugin registries enforce BasePlugin protocol at registration."""


class TestRegistryEnforcement:
    """Registry must reject plugins without BasePlugin methods (FAIL FAST)."""

    @pytest.mark.xfail(reason="Registry enforcement not yet implemented", strict=True)
    def test_datasource_registry_rejects_non_baseplugin(self):
        """Datasource registry MUST reject plugins without BasePlugin methods."""
        from elspeth.core.registries.datasource_registry import DatasourceRegistry

        # Create plugin WITHOUT BasePlugin methods
        class BrokenDatasource:
            """Datasource missing get_security_level() and validate_can_operate_at_level()."""
            def __init__(self, path: str, security_level: SecurityLevel):
                self.path = path
                self.security_level = security_level

            def load(self) -> pd.DataFrame:
                return pd.DataFrame({"col": [1, 2, 3]})

            # ❌ NO get_security_level() method
            # ❌ NO validate_can_operate_at_level() method

        # Attempt to register
        registry = DatasourceRegistry()

        # MUST raise TypeError or ValueError at registration time
        with pytest.raises((TypeError, ValueError)) as exc_info:
            registry.register("broken", BrokenDatasource)

        # Error message MUST mention BasePlugin protocol
        error_msg = str(exc_info.value).lower()
        assert "baseplugin" in error_msg or "protocol" in error_msg

    @pytest.mark.xfail(reason="Registry enforcement not yet implemented", strict=True)
    def test_sink_registry_rejects_non_baseplugin(self):
        """Sink registry MUST reject plugins without BasePlugin methods."""
        from elspeth.core.registries.sink_registry import SinkRegistry

        class BrokenSink:
            """Sink missing BasePlugin methods."""
            def __init__(self, path: str, security_level: SecurityLevel):
                self.path = path
                self.security_level = security_level

            def write(self, df: pd.DataFrame) -> None:
                pass

            # ❌ NO BasePlugin methods

        registry = SinkRegistry()

        # MUST raise at registration time
        with pytest.raises((TypeError, ValueError)):
            registry.register("broken", BrokenSink)

    @pytest.mark.xfail(reason="Registry enforcement not yet implemented", strict=True)
    def test_plugin_with_baseplugin_methods_registers_successfully(self):
        """Plugins WITH BasePlugin methods MUST register successfully."""
        from elspeth.core.registries.datasource_registry import DatasourceRegistry

        class ValidDatasource:
            """Datasource with complete BasePlugin implementation."""
            def __init__(self, path: str, security_level: SecurityLevel):
                self.path = path
                self.security_level = security_level

            def load(self) -> pd.DataFrame:
                return pd.DataFrame({"col": [1, 2, 3]})

            # ✅ BasePlugin methods present
            def get_security_level(self) -> SecurityLevel:
                return self.security_level

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < self.security_level:
                    raise SecurityValidationError("...")

        registry = DatasourceRegistry()

        # MUST succeed (no exception)
        registry.register("valid", ValidDatasource)
        assert "valid" in registry.list()
```

---

### Category 5: Integration Tests (End-to-End)

**Purpose**: Verify validation runs in real suite execution

```python
"""Integration tests with full suite runner."""


class TestIntegrationAfterFix:
    """End-to-end tests proving validation runs in real workflows."""

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_suite_runner_validates_before_data_load(self, tmp_path):
        """Suite runner MUST validate BEFORE loading data (fail-fast)."""
        from elspeth.core.validation.base import SecurityValidationError

        # Create SECRET datasource
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("password\nABC123\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Track if datasource.load() was called
        original_load = secret_ds.load
        load_called = {"value": False}

        def tracked_load():
            load_called["value"] = True
            return original_load()

        secret_ds.load = tracked_load

        # Create UNOFFICIAL sink
        public_output = tmp_path / "public.csv"
        unofficial_sink = CSVFileSink(
            path=str(public_output),
            security_level=SecurityLevel.UNOFFICIAL
        )

        # Build experiment
        experiment_config = create_experiment_config(
            datasource=secret_ds,
            sinks=[unofficial_sink]
        )

        # Run suite - MUST fail during validation
        with pytest.raises(SecurityValidationError):
            runner = ExperimentSuiteRunner(...)
            runner.run(experiment_config)

        # CRITICAL: datasource.load() MUST NOT have been called
        # (validation should fail BEFORE data retrieval)
        assert load_called["value"] is False, \
            "Datasource load() called before validation failed (data leak risk!)"

    @pytest.mark.xfail(reason="ADR-002 BasePlugin not yet implemented", strict=True)
    def test_multi_sink_validation_all_checked(self, tmp_path):
        """With multiple sinks, ALL must be validated (not just first)."""
        from elspeth.core.validation.base import SecurityValidationError

        # Create SECRET datasource
        secret_csv = tmp_path / "secret.csv"
        secret_csv.write_text("data\n1\n")

        secret_ds = BaseCSVDataSource(
            path=str(secret_csv),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # Create 3 sinks: SECRET (ok), SECRET (ok), UNOFFICIAL (FAIL)
        secret_sink_1 = CSVFileSink(
            path=str(tmp_path / "out1.csv"),
            security_level=SecurityLevel.SECRET
        )
        secret_sink_2 = CSVFileSink(
            path=str(tmp_path / "out2.csv"),
            security_level=SecurityLevel.SECRET
        )
        unofficial_sink = CSVFileSink(  # ← This should cause failure
            path=str(tmp_path / "out3.csv"),
            security_level=SecurityLevel.UNOFFICIAL
        )

        experiment_config = create_experiment_config(
            datasource=secret_ds,
            sinks=[secret_sink_1, secret_sink_2, unofficial_sink]
        )

        # MUST raise on third sink (proves all sinks checked)
        with pytest.raises(SecurityValidationError):
            runner = ExperimentSuiteRunner(...)
            runner.run(experiment_config)
```

---

## Test Execution Strategy

### Phase 0.1: Write Characterization Tests (1 hour)

1. Create `tests/test_adr002_baseplugin_compliance.py`
2. Write Category 1 tests (current state documentation)
3. Run: `pytest tests/test_adr002_baseplugin_compliance.py -v -k Characterization`
4. **Expected**: All PASS (documents current broken state)

### Phase 0.2: Write Security Property Tests (1-2 hours)

1. Add Category 2 tests (security bug proof)
2. Add Category 3 tests (success criteria, @pytest.mark.xfail)
3. Add Category 4 tests (integration, @pytest.mark.xfail)
4. Run: `pytest tests/test_adr002_baseplugin_compliance.py -v`
5. **Expected**:
   - Category 1: All PASS
   - Category 2: All PASS (proves bug exists)
   - Category 3: All XFAIL (will pass after implementation)
   - Category 4: All XFAIL (will pass after implementation)

---

## Exit Criteria

- ✅ Test file created: `tests/test_adr002_baseplugin_compliance.py`
- ✅ Characterization tests (Category 1) all PASS
- ✅ Security bug tests (Category 2) all PASS
- ✅ Security property tests (Category 3) marked with `@pytest.mark.xfail`
- ✅ Integration tests (Category 4) marked with `@pytest.mark.xfail`
- ✅ Test coverage ≥ 95% on validation code paths
- ✅ All stakeholders understand the gap

---

## Helper Functions (Test Utilities)

```python
"""Test utilities for ADR-002 BasePlugin compliance tests."""

import pandas as pd
from typing import Any


def create_experiment_config(
    datasource: Any,
    sinks: list[Any],
    name: str = "test_experiment"
) -> dict[str, Any]:
    """Create minimal experiment config for testing.

    Args:
        datasource: Datasource instance
        sinks: List of sink instances
        name: Experiment name

    Returns:
        Experiment configuration dict
    """
    return {
        "name": name,
        "datasource": datasource,
        "sinks": sinks,
        "llm_config": None,  # Not needed for validation tests
        "row_plugins": [],
        "aggregation_plugins": [],
        # ... other minimal required fields
    }
```

---

**Next Phase**: [PHASE_1_IMPLEMENTATION_GUIDE.md](./PHASE_1_IMPLEMENTATION_GUIDE.md)
