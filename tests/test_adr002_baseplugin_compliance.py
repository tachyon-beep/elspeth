"""
ADR-002 BasePlugin Protocol Compliance Tests

**PURPOSE**: Safety net for ADR-002 BasePlugin completion migration (P0 blocker)

This test suite uses the RED → GREEN → REFACTOR methodology from
docs/refactoring/METHODOLOGY.md to implement the BasePlugin protocol across
all 26 plugin classes.

**PROBLEM STATEMENT**:
Current ADR-002 validation code uses hasattr() defensive checks that
short-circuit when plugins don't implement BasePlugin protocol methods
(get_security_level() and validate_can_operate_at_level()). This allows
SECRET datasources to flow to UNOFFICIAL sinks UNCHECKED.

**TEST CATEGORIES**:

1. **Characterization Tests** (RED - document current broken state)
   - Prove plugins lack BasePlugin methods
   - Expected: PASS (documents problem)

2. **Security Bug Tests** (RED - prove validation skips)
   - Prove hasattr checks return False
   - Prove SECRET→UNOFFICIAL currently allowed
   - Expected: PASS (proves vulnerability)

3. **Security Property Tests** (GREEN - define success criteria)
   - All plugins implement BasePlugin
   - Validation raises SecurityValidationError on mismatch
   - Validation succeeds when safe
   - Expected: XFAIL now, PASS after Phase 1

4. **Registry Enforcement Tests** (GREEN - define registration validation)
   - Registry rejects plugins without BasePlugin methods
   - Registry accepts plugins with BasePlugin methods
   - Expected: XFAIL now, PASS after Phase 1.5 (optional)

5. **Integration Tests** (GREEN - end-to-end validation)
   - Suite runner validates before data load
   - Multi-sink validation checks all sinks
   - Expected: XFAIL now, PASS after Phase 2

**MIGRATION PHASES**:
- Phase 0 (THIS FILE): Build safety net (2-3 hours)
- Phase 1: Add BasePlugin methods to 26 plugins (2-3 hours)
- Phase 2: Remove hasattr checks from suite_runner.py (30 min)
- Phase 3: End-to-end verification (1-2 hours)

**EXIT CRITERIA (Phase 0)**:
- ✅ All Category 1-2 tests PASS (characterization + bugs)
- ✅ All Category 3-5 tests XFAIL (will pass after implementation)
- ✅ MyPy clean
- ✅ Ruff clean

See: docs/migration/adr-002-baseplugin-completion/PHASE_0_TEST_SPECIFICATION.md
"""

import pytest
import pandas as pd
from pathlib import Path
from typing import List

from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError
from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource
from elspeth.plugins.nodes.sources.csv_local import CSVDataSource
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink


# =============================================================================
# CATEGORY 1: CHARACTERIZATION TESTS (Document Current Broken State)
# =============================================================================
# Expected: All PASS (proves plugins lack BasePlugin methods)
# =============================================================================


class TestCategory1Characterization:
    """Category 1: Characterization tests proving plugins lack BasePlugin methods.

    These tests document the CURRENT STATE (before Phase 1 implementation).
    They PASS when plugins are missing methods, FAIL when methods added.

    Purpose: Provide clear evidence of the problem and ensure tests break
    when implementation begins (RED → GREEN signal).
    """

    def test_basecsvdatasource_no_get_security_level(self, tmp_path: Path) -> None:
        """BaseCSVDataSource currently lacks get_security_level() method.

        **TEST TYPE**: Characterization (documents current state)
        **EXPECTED**: PASS (method missing) → FAIL after Phase 1 (method added)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(ds, "get_security_level"), \
            "BaseCSVDataSource already has get_security_level() - Phase 1 started!"

    def test_basecsvdatasource_no_validate_method(self, tmp_path: Path) -> None:
        """BaseCSVDataSource currently lacks validate_can_operate_at_level() method.

        **TEST TYPE**: Characterization (documents current state)
        **EXPECTED**: PASS (method missing) → FAIL after Phase 1 (method added)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(ds, "validate_can_operate_at_level"), \
            "BaseCSVDataSource already has validate_can_operate_at_level() - Phase 1 started!"

    def test_csvdatasource_no_get_security_level(self, tmp_path: Path) -> None:
        """CSVDataSource currently lacks get_security_level() method.

        **TEST TYPE**: Characterization (documents current state)
        **EXPECTED**: PASS (method missing) → FAIL after Phase 1 (method added)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(ds, "get_security_level"), \
            "CSVDataSource already has get_security_level() - Phase 1 started!"

    def test_csvfilesink_no_get_security_level(self, tmp_path: Path) -> None:
        """CsvResultSink currently lacks get_security_level() method.

        **TEST TYPE**: Characterization (documents current state)
        **EXPECTED**: PASS (method missing) → FAIL after Phase 1 (method added)
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(sink, "get_security_level"), \
            "CsvResultSink already has get_security_level() - Phase 1 started!"

    def test_csvfilesink_no_validate_method(self, tmp_path: Path) -> None:
        """CsvResultSink currently lacks validate_can_operate_at_level() method.

        **TEST TYPE**: Characterization (documents current state)
        **EXPECTED**: PASS (method missing) → FAIL after Phase 1 (method added)
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # CHARACTERIZATION: Method doesn't exist (yet)
        assert not hasattr(sink, "validate_can_operate_at_level"), \
            "CsvResultSink already has validate_can_operate_at_level() - Phase 1 started!"


# =============================================================================
# CATEGORY 2: SECURITY BUG TESTS (Prove Validation Skips)
# =============================================================================
# Expected: All PASS (proves hasattr checks short-circuit)
# =============================================================================


class TestCategory2SecurityBugs:
    """Category 2: Security bug tests proving validation short-circuits.

    These tests prove the CURRENT VULNERABILITY where hasattr() checks
    return False and validation is silently skipped.

    Expected: PASS (proves bug exists) → These tests may become obsolete
    after Phase 2 (when hasattr checks removed).
    """

    def test_hasattr_check_returns_false_for_datasources(self, tmp_path: Path) -> None:
        """Prove hasattr check returns False for datasources without BasePlugin methods.

        **TEST TYPE**: Security bug demonstration
        **EXPECTED**: PASS (proves hasattr returns False)
        **IMPACT**: suite_runner.py validation skips when this is False
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # SECURITY BUG: This check returns False, causing validation to skip
        has_method = hasattr(ds, "validate_can_operate_at_level")

        assert has_method is False, \
            "hasattr check now returns True - validation will run!"

    def test_hasattr_check_returns_false_for_sinks(self, tmp_path: Path) -> None:
        """Prove hasattr check returns False for sinks without BasePlugin methods.

        **TEST TYPE**: Security bug demonstration
        **EXPECTED**: PASS (proves hasattr returns False)
        **IMPACT**: suite_runner.py validation skips when this is False
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # SECURITY BUG: This check returns False, causing validation to skip
        has_method = hasattr(sink, "validate_can_operate_at_level")

        assert has_method is False, \
            "hasattr check now returns True - validation will run!"


# =============================================================================
# CATEGORY 3: SECURITY PROPERTY TESTS (Define Success Criteria)
# =============================================================================
# Expected: All XFAIL (will pass after Phase 1 implementation)
# =============================================================================


class TestCategory3SecurityProperties:
    """Category 3: Security property tests defining success criteria.

    These tests define what SUCCESS looks like after Phase 1 implementation.
    They use @pytest.mark.xfail to indicate they SHOULD FAIL NOW but will
    PASS after all plugins implement BasePlugin.

    Expected: XFAIL → PASS after Phase 1
    """

    @pytest.mark.xfail(
        reason="Phase 1 not started - plugins don't implement BasePlugin yet",
        strict=True
    )
    def test_all_datasources_implement_baseplugin(self, tmp_path: Path) -> None:
        """All datasources MUST implement BasePlugin protocol after Phase 1.

        **TEST TYPE**: Security property (success criteria)
        **EXPECTED**: XFAIL (plugins lack methods) → PASS after Phase 1
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # SUCCESS CRITERIA: Both methods must exist
        assert hasattr(ds, "get_security_level"), \
            "Datasource missing get_security_level() method"
        assert callable(ds.get_security_level), \
            "get_security_level must be callable"

        assert hasattr(ds, "validate_can_operate_at_level"), \
            "Datasource missing validate_can_operate_at_level() method"
        assert callable(ds.validate_can_operate_at_level), \
            "validate_can_operate_at_level must be callable"

    @pytest.mark.xfail(
        reason="Phase 1 not started - plugins don't implement BasePlugin yet",
        strict=True
    )
    def test_all_sinks_implement_baseplugin(self, tmp_path: Path) -> None:
        """All sinks MUST implement BasePlugin protocol after Phase 1.

        **TEST TYPE**: Security property (success criteria)
        **EXPECTED**: XFAIL (plugins lack methods) → PASS after Phase 1
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # SUCCESS CRITERIA: Both methods must exist
        assert hasattr(sink, "get_security_level"), \
            "Sink missing get_security_level() method"
        assert callable(sink.get_security_level), \
            "get_security_level must be callable"

        assert hasattr(sink, "validate_can_operate_at_level"), \
            "Sink missing validate_can_operate_at_level() method"
        assert callable(sink.validate_can_operate_at_level), \
            "validate_can_operate_at_level must be callable"

    @pytest.mark.xfail(
        reason="Phase 1 not started - plugins don't implement BasePlugin yet",
        strict=True
    )
    def test_get_security_level_returns_correct_value(self, tmp_path: Path) -> None:
        """get_security_level() MUST return the plugin's declared security level.

        **TEST TYPE**: Security property (behavior verification)
        **EXPECTED**: XFAIL (method missing) → PASS after Phase 1
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # SUCCESS CRITERIA: Method returns correct security level
        result = ds.get_security_level()  # type: ignore[attr-defined]
        assert result == SecurityLevel.SECRET, "get_security_level() must return plugin's declared security level"

    @pytest.mark.xfail(
        reason="Phase 1 not started - plugins don't implement BasePlugin yet",
        strict=True
    )
    def test_validate_raises_on_security_mismatch(self, tmp_path: Path) -> None:
        """validate_can_operate_at_level() MUST raise when operating level too low.

        **TEST TYPE**: Security property (validation behavior)
        **EXPECTED**: XFAIL (method missing) → PASS after Phase 1

        **SCENARIO**: SECRET datasource, UNOFFICIAL operating level
        **EXPECTED BEHAVIOR**: SecurityValidationError raised
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.SECRET
        )

        # SUCCESS CRITERIA: Validation raises SecurityValidationError
        with pytest.raises(SecurityValidationError) as exc_info:
            ds.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # type: ignore[attr-defined]

        # Error message should mention both levels
        error_msg = str(exc_info.value)
        assert "SECRET" in error_msg, "Error must mention datasource level (SECRET)"
        assert "UNOFFICIAL" in error_msg, "Error must mention operating level (UNOFFICIAL)"

    @pytest.mark.xfail(
        reason="Phase 1 not started - plugins don't implement BasePlugin yet",
        strict=True
    )
    def test_validate_succeeds_when_safe(self, tmp_path: Path) -> None:
        """validate_can_operate_at_level() MUST succeed when operating level >= required.

        **TEST TYPE**: Security property (validation behavior)
        **EXPECTED**: XFAIL (method missing) → PASS after Phase 1

        **SCENARIO**: UNOFFICIAL datasource, SECRET operating level
        **EXPECTED BEHAVIOR**: No exception (validation passes)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level=SecurityLevel.UNOFFICIAL
        )

        # SUCCESS CRITERIA: No exception raised
        ds.validate_can_operate_at_level(SecurityLevel.SECRET)  # type: ignore[attr-defined]  # Should succeed


# =============================================================================
# CATEGORY 4: REGISTRY ENFORCEMENT TESTS (Optional Phase 1.5)
# =============================================================================
# Expected: All XFAIL (will pass after Phase 1.5, if implemented)
# =============================================================================


class TestCategory4RegistryEnforcement:
    """Category 4: Registry enforcement tests (optional Phase 1.5).

    These tests define registry-level enforcement where plugins without
    BasePlugin methods are rejected at REGISTRATION time, not runtime.

    NOTE: Phase 1.5 is OPTIONAL and recommended to defer post-merge.
    These tests document the desired behavior but are not blocking.

    Expected: XFAIL → PASS after Phase 1.5 (if implemented)
    """

    @pytest.mark.xfail(
        reason="Phase 1.5 not implemented - registry doesn't enforce BasePlugin yet",
        strict=False  # Not strict - this is optional future work
    )
    def test_registry_rejects_plugin_without_baseplugin(self, tmp_path: Path) -> None:
        """Registry SHOULD reject plugins missing BasePlugin methods at registration.

        **TEST TYPE**: Registry enforcement (optional Phase 1.5)
        **EXPECTED**: XFAIL (not implemented) → PASS after Phase 1.5
        **PRIORITY**: P2 - Nice to have, not blocking
        """
        from elspeth.core.registries.base import BasePluginRegistry
        from elspeth.core.base.protocols import DataSource

        class BrokenDatasource:
            """Datasource missing BasePlugin methods."""
            def __init__(self, path: str):
                self.path = path

            def load(self) -> pd.DataFrame:
                return pd.DataFrame({"col": [1]})

            # ❌ NO get_security_level()
            # ❌ NO validate_can_operate_at_level()

        registry = BasePluginRegistry[DataSource]("test_datasource")

        # DESIRED BEHAVIOR: Registry raises TypeError at registration
        with pytest.raises(TypeError) as exc_info:
            registry.register("broken", BrokenDatasource)  # type: ignore[arg-type]

        # Error message should be helpful
        error_msg = str(exc_info.value)
        assert "BasePlugin" in error_msg
        assert "get_security_level" in error_msg or "validate_can_operate_at_level" in error_msg

    @pytest.mark.xfail(
        reason="Phase 1.5 not implemented - registry doesn't enforce BasePlugin yet",
        strict=False  # Not strict - this is optional future work
    )
    def test_registry_accepts_plugin_with_baseplugin(self, tmp_path: Path) -> None:
        """Registry SHOULD accept plugins with complete BasePlugin implementation.

        **TEST TYPE**: Registry enforcement (optional Phase 1.5)
        **EXPECTED**: XFAIL (not implemented) → PASS after Phase 1.5
        **PRIORITY**: P2 - Nice to have, not blocking
        """
        from elspeth.core.registries.base import BasePluginRegistry
        from elspeth.core.base.protocols import DataSource

        class ValidDatasource:
            """Complete BasePlugin implementation."""
            def __init__(self, path: str, security_level: SecurityLevel):
                self.path = path
                self.security_level = security_level

            def load(self) -> pd.DataFrame:
                return pd.DataFrame({"col": [1]})

            # ✅ BasePlugin methods
            def get_security_level(self) -> SecurityLevel:
                return self.security_level

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < self.security_level:
                    raise SecurityValidationError(
                        f"Datasource requires {self.security_level.name}, "
                        f"operating envelope is {operating_level.name}"
                    )

        registry = BasePluginRegistry[DataSource]("test_datasource")

        # DESIRED BEHAVIOR: Registration succeeds
        registry.register("valid", ValidDatasource)  # type: ignore[arg-type]
        assert "valid" in registry.list()  # type: ignore[attr-defined]


# =============================================================================
# CATEGORY 5: INTEGRATION TESTS (End-to-End Validation)
# =============================================================================
# Expected: All XFAIL (will pass after Phase 2 - validation cleanup)
# =============================================================================


class TestCategory5Integration:
    """Category 5: Integration tests for end-to-end security validation.

    These tests verify the complete validation flow in ExperimentSuiteRunner,
    ensuring validation runs BEFORE data retrieval and checks ALL components.

    Expected: XFAIL → PASS after Phase 2 (hasattr checks removed)
    """

    @pytest.mark.xfail(
        reason="Phase 1-2 not complete - validation still uses hasattr checks",
        strict=True
    )
    def test_secret_datasource_unofficial_sink_blocked(self, tmp_path: Path) -> None:
        """Suite runner MUST block SECRET datasource → UNOFFICIAL sink flow.

        **TEST TYPE**: Integration (end-to-end security validation)
        **EXPECTED**: XFAIL (validation skips) → PASS after Phase 2

        **SCENARIO**: SECRET datasource + UNOFFICIAL sink
        **EXPECTED BEHAVIOR**: SecurityValidationError raised BEFORE datasource.load()
        """
        from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner

        # Create test data
        csv_file = tmp_path / "secret_data.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        output_file = tmp_path / "output.csv"

        # Minimal suite config (will create SECRET datasource + UNOFFICIAL sink)
        config = {
            "suite_id": "test_suite",
            "suite_metadata": {"name": "Test Suite"},
            "experiments": [
                {
                    "experiment_id": "exp1",
                    "datasource": {"type": "csv_local", "path": str(csv_file)},
                    "sinks": [{"type": "csv_file", "path": str(output_file)}]
                }
            ]
        }

        # SUCCESS CRITERIA: SecurityValidationError raised
        with pytest.raises(SecurityValidationError) as exc_info:
            runner = ExperimentSuiteRunner(config)  # type: ignore[arg-type,call-arg]
            runner.run()  # type: ignore[call-arg]

        # Error should mention security mismatch
        error_msg = str(exc_info.value)
        assert "SECRET" in error_msg or "UNOFFICIAL" in error_msg, \
            "Error must mention security level mismatch"

        # Output file should NOT be created (validation failed before data load)
        assert not output_file.exists(), \
            "Output file should not exist - validation should abort before data retrieval"

    @pytest.mark.xfail(
        reason="Phase 1-2 not complete - validation still uses hasattr checks",
        strict=True
    )
    def test_unofficial_datasource_secret_sink_allowed(self, tmp_path: Path) -> None:
        """Suite runner MUST allow UNOFFICIAL datasource → SECRET sink flow.

        **TEST TYPE**: Integration (end-to-end security validation)
        **EXPECTED**: XFAIL (validation skips) → PASS after Phase 2

        **SCENARIO**: UNOFFICIAL datasource + SECRET sink
        **EXPECTED BEHAVIOR**: Experiment succeeds (safe downward flow)
        """
        from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner

        # Create test data
        csv_file = tmp_path / "unofficial_data.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        output_file = tmp_path / "output.csv"

        # Minimal suite config
        config = {
            "suite_id": "test_suite",
            "suite_metadata": {"name": "Test Suite"},
            "experiments": [
                {
                    "experiment_id": "exp1",
                    "datasource": {
                        "type": "csv_local",
                        "path": str(csv_file),
                        "security_level": "UNOFFICIAL"
                    },
                    "sinks": [
                        {
                            "type": "csv_file",
                            "path": str(output_file),
                            "security_level": "SECRET"
                        }
                    ]
                }
            ]
        }

        # SUCCESS CRITERIA: No exception raised, output file created
        runner = ExperimentSuiteRunner(config)  # type: ignore[arg-type,call-arg]
        runner.run()  # type: ignore[call-arg]

        assert output_file.exists(), \
            "Output file should be created - validation should pass for safe downward flow"


# =============================================================================
# TEST EXECUTION NOTES
# =============================================================================
"""
**PHASE 0 EXECUTION**:

Run tests to verify safety net:
```bash
# All tests
pytest tests/test_adr002_baseplugin_compliance.py -v

# By category
pytest tests/test_adr002_baseplugin_compliance.py -v -k Category1  # Characterization
pytest tests/test_adr002_baseplugin_compliance.py -v -k Category2  # Security bugs
pytest tests/test_adr002_baseplugin_compliance.py -v -k Category3  # Security properties
pytest tests/test_adr002_baseplugin_compliance.py -v -k Category4  # Registry enforcement
pytest tests/test_adr002_baseplugin_compliance.py -v -k Category5  # Integration
```

**EXPECTED RESULTS (Phase 0)**:
- Category 1 (Characterization): All PASS ✅
- Category 2 (Security Bugs): All PASS ✅
- Category 3 (Security Properties): All XFAIL ⚠️
- Category 4 (Registry Enforcement): All XFAIL ⚠️ (optional)
- Category 5 (Integration): All XFAIL ⚠️

**AFTER PHASE 1** (BasePlugin methods added):
- Category 1: All FAIL ✅ (proves methods added - tests become obsolete)
- Category 2: All FAIL ✅ (hasattr returns True - tests become obsolete)
- Category 3: All PASS ✅ (security properties achieved!)
- Category 4: Still XFAIL ⚠️ (Phase 1.5 not implemented)
- Category 5: Still XFAIL ⚠️ (Phase 2 not complete)

**AFTER PHASE 2** (hasattr checks removed):
- Category 5: All PASS ✅ (end-to-end validation works!)

**AFTER PHASE 1.5** (optional registry enforcement):
- Category 4: All PASS ✅ (registration-time validation)
"""
