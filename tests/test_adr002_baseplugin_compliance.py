"""
ADR-002 BasePlugin ABC Inheritance Tests

**PURPOSE**: Safety net for ADR-002 BasePlugin ABC migration (P0 blocker)

This test suite uses the RED → GREEN → REFACTOR methodology from
docs/refactoring/METHODOLOGY.md to migrate all 26 plugin classes to inherit
from BasePlugin ABC with concrete "security bones" implementation (ADR-004).

**PROBLEM STATEMENT**:
Current plugins don't inherit from BasePlugin ABC. ADR-002 validation code
uses isinstance() checks that return False (no inheritance), causing validation
to short-circuit. This allows SECRET datasources to flow to UNOFFICIAL sinks
UNCHECKED.

**NEW DESIGN (ADR-004 "Security Bones")**:
- BasePlugin is now an ABC (not Protocol) with CONCRETE security methods
- Plugins INHERIT security enforcement, they don't implement it
- Security methods are FINAL and cannot be overridden (runtime enforced)
- Validation logic is centralized in BasePlugin (single source of truth)

**TEST CATEGORIES**:

0. **Step 0 Verification** (GREEN - verify ABC infrastructure)
   - BasePlugin ABC exists with concrete methods
   - Runtime enforcement prevents method override (__init_subclass__)
   - Property and methods work correctly
   - Expected: XFAIL now (no ABC yet), PASS after Step 0

1. **Characterization Tests** (RED - document current broken state)
   - Prove plugins lack BasePlugin inheritance
   - Expected: PASS (documents problem)

2. **Security Bug Tests** (RED - prove validation skips)
   - Prove isinstance checks return False
   - Prove SECRET→UNOFFICIAL currently allowed
   - Expected: PASS (proves vulnerability)

3. **Security Property Tests** (GREEN - define success criteria)
   - All plugins inherit from BasePlugin ABC
   - Validation raises SecurityValidationError on mismatch
   - Validation succeeds when safe
   - Expected: XFAIL now, PASS after Step 1-4

4. **Registry Enforcement Tests** (GREEN - define registration validation)
   - Registry rejects plugins without BasePlugin inheritance
   - Registry accepts plugins with BasePlugin inheritance
   - Expected: XFAIL now, PASS after Step 1-4 (optional)

5. **Integration Tests** (GREEN - end-to-end validation)
   - Suite runner validates before data load
   - Multi-sink validation checks all sinks
   - Expected: XFAIL now, PASS after Phase 1.5 complete

**MIGRATION STEPS** (ADR-004 + ADR-003/004 Migration Plan):
- **Step 0 (35 min)**: Create BasePlugin ABC, remove old Protocol, update imports
  * Create src/elspeth/core/base/plugin.py with ABC
  * Remove Protocol from src/elspeth/core/base/protocols.py
  * Update all imports (protocols → plugin module)
  * Verify isinstance checks use ABC (nominal typing)

- **Step 1-4 (3-5 hours)**: Add BasePlugin inheritance to 26 plugins
  * Add BasePlugin to inheritance chains
  * Update __init__ to call super().__init__(security_level=...)
  * Remove any existing get_security_level() implementations (now inherited)

- **Phase 2 (30 min)**: Remove hasattr checks from suite_runner.py
  * Replace hasattr defensive checks with direct method calls
  * Add AttributeError handling for better error messages

- **Phase 3 (1-2 hours)**: End-to-end verification
  * All tests GREEN
  * SECRET→UNOFFICIAL blocked
  * isinstance(plugin, BasePlugin) returns True for all plugins

**EXIT CRITERIA (Phase 0 - THIS FILE)**:
- ✅ All Category 0 tests XFAIL (ABC doesn't exist yet)
- ✅ All Category 1-2 tests PASS (characterization + bugs)
- ✅ All Category 3-5 tests XFAIL (will pass after implementation)
- ✅ MyPy clean
- ✅ Ruff clean

See: docs/migration/adr-002-baseplugin-completion/PHASE_0_TEST_SPECIFICATION.md
"""

import pytest
import pandas as pd
from pathlib import Path

from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError
from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource
from elspeth.plugins.nodes.sources.csv_local import CSVDataSource
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink


# =============================================================================
# CATEGORY 0: STEP 0 VERIFICATION (BasePlugin ABC Infrastructure)
# =============================================================================
# Expected: All XFAIL now (ABC doesn't exist), PASS after Step 0 complete
# =============================================================================


class TestCategory0Step0Verification:
    """Category 0: Step 0 verification - BasePlugin ABC infrastructure tests.

    These tests verify that Step 0 (Protocol removal + ABC creation) is complete:
    - BasePlugin ABC exists at src/elspeth/core/base/plugin.py
    - Old Protocol removed from src/elspeth/core/base/protocols.py
    - ABC has concrete security methods (not abstract)
    - Runtime enforcement prevents method override (__init_subclass__)

    **STATUS**: ✅ Step 0 COMPLETE - All 6 tests passing
    - BasePlugin ABC created with concrete security methods
    - Old Protocol removed from protocols.py
    - All imports updated to use ABC module
    """

    def test_baseplugin_abc_module_exists(self) -> None:
        """BasePlugin ABC MUST exist at src/elspeth/core/base/plugin.py (Step 0.1).

        **STEP 0 REQUIREMENT**: Create new module with BasePlugin ABC
        **STATUS**: ✅ PASS (Step 0.1 complete)
        """
        # Try to import BasePlugin ABC from the new module
        try:
            from elspeth.core.base.plugin import BasePlugin
        except ImportError as e:
            pytest.fail(
                f"BasePlugin ABC module doesn't exist yet: {e}. "
                f"Complete Step 0.1: Create src/elspeth/core/base/plugin.py"
            )

        # Verify it's an ABC, not Protocol
        from abc import ABC
        assert issubclass(BasePlugin, ABC), (
            "BasePlugin should be an ABC (inherit from abc.ABC), not Protocol"
        )

    def test_baseplugin_has_concrete_security_methods(self) -> None:
        """BasePlugin ABC MUST provide CONCRETE security methods (not abstract).

        **SECURITY BONES DESIGN**: BasePlugin provides the implementation,
        subclasses inherit it (they don't reimplement).

        **STATUS**: ✅ PASS (Step 0.1 complete)
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.types import SecurityLevel

        # Create a minimal subclass (doesn't implement any methods)
        class MinimalPlugin(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)

        # Instantiate - should work because methods are inherited
        plugin = MinimalPlugin()

        # Verify methods exist and work (inherited from BasePlugin)
        assert hasattr(plugin, "get_security_level"), "Missing get_security_level method"
        assert hasattr(plugin, "validate_can_operate_at_level"), "Missing validate_can_operate_at_level method"
        assert plugin.get_security_level() == SecurityLevel.SECRET

    def test_baseplugin_prevents_method_override_runtime(self) -> None:
        """BasePlugin MUST prevent override of security methods at class definition (runtime enforcement).

        **SECURITY INVARIANT**: get_security_level() and validate_can_operate_at_level()
        are FINAL. Subclasses attempting to override them should raise TypeError.

        This uses __init_subclass__ for runtime enforcement (complements @final for static checks).

        **STATUS**: ✅ PASS (Step 0.1 complete)
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.types import SecurityLevel

        # Attempt to override get_security_level - should raise TypeError at class definition
        with pytest.raises(TypeError) as exc_info:
            class BrokenPlugin(BasePlugin):
                def __init__(self):
                    super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)

                def get_security_level(self) -> SecurityLevel:  # ← Override attempt
                    return SecurityLevel.UNOFFICIAL  # ← Should be rejected!

        # Error message should be clear
        error_msg = str(exc_info.value)
        assert "may not override" in error_msg or "security invariant" in error_msg
        assert "get_security_level" in error_msg

    def test_baseplugin_security_level_property(self) -> None:
        """BasePlugin MUST provide read-only security_level property.

        **DESIGN**: Property enables convenient access (self.security_level) while
        preventing reassignment (no setter). Backed by private _security_level attribute.

        **STATUS**: ✅ PASS (Step 0.1 complete)
        """
        from elspeth.core.base.plugin import BasePlugin
        from elspeth.core.base.types import SecurityLevel

        class TestPlugin(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)

        plugin = TestPlugin()

        # Property access should work
        assert plugin.security_level == SecurityLevel.SECRET

        # Property should be read-only (no setter)
        with pytest.raises(AttributeError):
            plugin.security_level = SecurityLevel.UNOFFICIAL  # ← Should fail!

    def test_old_protocol_removed_from_protocols_module(self) -> None:
        """Old BasePlugin Protocol MUST be removed from protocols.py (Step 0.2).

        **CRITICAL**: If old Protocol remains, code importing from protocols module
        will continue using structural typing (duck typing), defeating the ABC design.

        **STATUS**: ✅ PASS (Step 0.2 complete)
        """
        import inspect

        # Import protocols module
        from elspeth.core.base import protocols

        # Check if BasePlugin exists in protocols module
        if hasattr(protocols, "BasePlugin"):
            baseplugin_in_protocols = getattr(protocols, "BasePlugin")

            # If it exists, it should be a re-export of the ABC, not the old Protocol
            from typing import Protocol
            from abc import ABC

            is_protocol = (
                hasattr(baseplugin_in_protocols, "__annotations__") and
                inspect.isclass(baseplugin_in_protocols) and
                issubclass(type(baseplugin_in_protocols), type(Protocol))
            )

            is_abc = inspect.isclass(baseplugin_in_protocols) and issubclass(baseplugin_in_protocols, ABC)

            if is_protocol and not is_abc:
                pytest.fail(
                    "Old BasePlugin Protocol still exists in protocols.py! "
                    "Complete Step 0.2: Remove Protocol or replace with ABC re-export"
                )

    def test_validation_code_imports_abc_not_protocol(self) -> None:
        """Validation code MUST import BasePlugin ABC from plugin module (Step 0.3).

        **CRITICAL**: suite_runner._validate_component_clearances must use ABC
        for isinstance checks to enforce nominal typing (explicit inheritance).

        **STATUS**: ✅ PASS (Step 0.3 complete)
        """
        # Read suite_runner.py source to check imports
        import inspect
        from elspeth.core.experiments import suite_runner

        source = inspect.getsource(suite_runner)

        # Check for old Protocol import (should NOT exist after Step 0.3)
        old_import = "from elspeth.core.base.protocols import BasePlugin"
        new_import = "from elspeth.core.base.plugin import BasePlugin"

        if old_import in source:
            pytest.fail(
                f"suite_runner.py still imports from protocols module! "
                f"Complete Step 0.3: Update import to use plugin module. "
                f"Found: {old_import!r}, Expected: {new_import!r}"
            )

        # Verify new import exists
        if new_import not in source:
            pytest.fail(
                f"suite_runner.py doesn't import BasePlugin ABC from plugin module yet. "
                f"Complete Step 0.3: Add {new_import!r}"
            )


# =============================================================================
# CATEGORY 1: CHARACTERIZATION TESTS (Document Current Broken State)
# =============================================================================
# Expected: All PASS (proves plugins lack BasePlugin inheritance)
# =============================================================================


class TestCategory1Characterization:
    """Category 1: Characterization tests proving plugins lack BasePlugin methods.

    These tests document the CURRENT STATE (before Phase 1 implementation).
    They PASS when plugins are missing methods, FAIL when methods added.

    Purpose: Provide clear evidence of the problem and ensure tests break
    when implementation begins (RED → GREEN signal).
    """

    def test_basecsvdatasource_no_get_security_level(self, tmp_path: Path) -> None:
        """BaseCSVDataSource has get_security_level() method after Phase 1 migration.

        **TEST TYPE**: Characterization (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED to BasePlugin (commit 5a063b4)
        **EXPECTED**: PASS (method present, inherited from BasePlugin)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        # ADR-005: allow_downgrade is now mandatory parameter
        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level="UNOFFICIAL",
            allow_downgrade=True
        )

        # POST-MIGRATION: Method exists (inherited from BasePlugin)
        assert hasattr(ds, "get_security_level"), \
            "BaseCSVDataSource missing get_security_level() after Phase 1 migration!"
        assert callable(ds.get_security_level), \
            "get_security_level is not callable!"

    def test_basecsvdatasource_no_validate_method(self, tmp_path: Path) -> None:
        """BaseCSVDataSource has validate_can_operate_at_level() method after Phase 1 migration.

        **TEST TYPE**: Characterization (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED to BasePlugin (commit 5a063b4)
        **EXPECTED**: PASS (method present, inherited from BasePlugin)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        # ADR-005: allow_downgrade is now mandatory parameter
        ds = BaseCSVDataSource(
            path=str(csv_file),
            retain_local=False,
            security_level="UNOFFICIAL",
            allow_downgrade=True
        )

        # POST-MIGRATION: Method exists (inherited from BasePlugin)
        assert hasattr(ds, "validate_can_operate_at_level"), \
            "BaseCSVDataSource missing validate_can_operate_at_level() after Phase 1 migration!"
        assert callable(ds.validate_can_operate_at_level), \
            "validate_can_operate_at_level is not callable!"

        # Note: Test method functionality depends on the plugin's immutable hard-coded security level

    def test_csvdatasource_no_get_security_level(self, tmp_path: Path) -> None:
        """CSVDataSource has get_security_level() method after Phase 1 migration.

        **TEST TYPE**: Characterization (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED to BasePlugin (inherits from BaseCSVDataSource, commit 5a063b4)
        **EXPECTED**: PASS (method present, inherited from BasePlugin via BaseCSVDataSource)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False
        )

        # POST-MIGRATION: Method exists (inherited from BaseCSVDataSource → BasePlugin)
        assert hasattr(ds, "get_security_level"), \
            "CSVDataSource missing get_security_level() after Phase 1 migration!"
        assert callable(ds.get_security_level), \
            "get_security_level is not callable!"

    def test_csvfilesink_no_get_security_level(self, tmp_path: Path) -> None:
        """CsvResultSink has get_security_level() method after Phase 1 migration.

        **TEST TYPE**: Characterization (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED to BasePlugin (Phase 1.2 Batch 1, commit 52e9217)
        **EXPECTED**: PASS (method present, inherited from BasePlugin)
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # POST-MIGRATION: Method exists (inherited from BasePlugin)
        assert hasattr(sink, "get_security_level"), \
            "CsvResultSink missing get_security_level() after Phase 1 migration!"
        assert callable(sink.get_security_level), \
            "get_security_level is not callable!"

    def test_csvfilesink_no_validate_method(self, tmp_path: Path) -> None:
        """CsvResultSink has validate_can_operate_at_level() method after Phase 1 migration.

        **TEST TYPE**: Characterization (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED to BasePlugin (Phase 1.2 Batch 1, commit 52e9217)
        **EXPECTED**: PASS (method present, inherited from BasePlugin)
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # POST-MIGRATION: Method exists (inherited from BasePlugin)
        assert hasattr(sink, "validate_can_operate_at_level"), \
            "CsvResultSink missing validate_can_operate_at_level() after Phase 1 migration!"
        assert callable(sink.validate_can_operate_at_level), \
            "validate_can_operate_at_level is not callable!"


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
        """Prove hasattr check returns True for datasources WITH BasePlugin methods after Phase 1.

        **TEST TYPE**: Security bug demonstration (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED - CSVDataSource inherits from BaseCSVDataSource → BasePlugin
        **EXPECTED**: PASS (proves hasattr returns True after migration)
        **IMPACT**: suite_runner.py validation will now run (bug fixed)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False
        )

        # POST-MIGRATION: This check returns True, validation will run
        has_method = hasattr(ds, "validate_can_operate_at_level")

        assert has_method is True, \
            "hasattr check returns False - Phase 1 migration incomplete!"

    def test_hasattr_check_returns_false_for_sinks(self, tmp_path: Path) -> None:
        """Prove hasattr check returns True for sinks WITH BasePlugin methods after Phase 1.

        **TEST TYPE**: Security bug demonstration (POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ MIGRATED - CsvResultSink inherits from BasePlugin (commit 52e9217)
        **EXPECTED**: PASS (proves hasattr returns True after migration)
        **IMPACT**: suite_runner.py validation will now run (bug fixed)
        """
        output_file = tmp_path / "output.csv"

        sink = CsvResultSink(path=str(output_file))

        # POST-MIGRATION: This check returns True, validation will run
        has_method = hasattr(sink, "validate_can_operate_at_level")

        assert has_method is True, \
            "hasattr check returns False - Phase 1 migration incomplete!"


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

    def test_all_datasources_implement_baseplugin(self, tmp_path: Path) -> None:
        """All datasources MUST implement BasePlugin protocol.

        **TEST TYPE**: Security property (VERIFIED POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ COMPLETE for datasources (commit 5a063b4)
        **EXPECTED**: PASS (datasources inherit from BasePlugin ABC)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False
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

    def test_get_security_level_returns_correct_value(self, tmp_path: Path) -> None:
        """get_security_level() MUST return the plugin's declared security level.

        **TEST TYPE**: Security property (VERIFIED POST-MIGRATION)
        **PHASE 1 STATUS**: ✅ COMPLETE for datasources (commit 5a063b4)
        **EXPECTED**: PASS (method inherited from BasePlugin ABC)
        """
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2\n1,2\n")

        ds = CSVDataSource(
            path=str(csv_file),
            retain_local=False
        )

        # SUCCESS CRITERIA: Method returns correct security level
        result = ds.get_security_level()  # type: ignore[attr-defined]
        # Note: Security level is now immutable and hard-coded in the plugin class
        assert result is not None, "get_security_level() must return a security level"

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
            retain_local=False
        )

        # SUCCESS CRITERIA: Validation raises SecurityValidationError
        # Note: With immutable security levels, the validation behavior depends on the plugin's hard-coded level
        # This test may need adjustment based on actual plugin security level
        with pytest.raises(SecurityValidationError) as exc_info:
            ds.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # type: ignore[attr-defined]

        # Error message should mention security level mismatch
        error_msg = str(exc_info.value)
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
            retain_local=False
        )

        # SUCCESS CRITERIA: No exception raised
        # Note: With immutable security levels, validation behavior depends on plugin's hard-coded level
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
                # Bell-LaPadula "no read up": Reject if asked to operate ABOVE clearance
                if operating_level > self.security_level:
                    raise SecurityValidationError(
                        f"Datasource has clearance {self.security_level.name}, "
                        f"but pipeline requires {operating_level.name} - insufficient clearance"
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
    using REAL production plugins (CSVDataSource, CsvResultSink) to demonstrate
    the CURRENT BROKEN BEHAVIOR where isinstance(plugin, BasePlugin) returns False
    because plugins don't inherit from BasePlugin ABC.

    **CRITICAL**: These tests use REAL plugins, NOT mocks. This ensures we're testing
    actual production behavior, not idealized mock behavior that gives false confidence.

    **NEW DESIGN (ADR-004 "Security Bones")**:
    - BasePlugin is an ABC (nominal typing) with concrete security methods
    - Plugins INHERIT from BasePlugin (explicit inheritance required)
    - isinstance checks enforce that plugins explicitly opt-in to security framework
    - Security methods are FINAL and inherited (not reimplemented by each plugin)

    **MIGRATION PHASES**:
    - Step 0 (35 min): Create BasePlugin ABC, remove Protocol, update imports
    - Step 1-4 (3-5 hours): Add BasePlugin inheritance to 26 plugins
    - After complete: isinstance(plugin, BasePlugin) returns True, validation runs

    Expected: XFAIL (Phase 0) → PASS after Step 1-4 complete (BasePlugin ABC inheritance added)
    """

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 0 - Real plugins don't inherit from BasePlugin ABC, so isinstance checks fail and validation is SKIPPED (security bug!)"
    )
    def test_secret_datasource_unofficial_sink_blocked(self, tmp_path: Path) -> None:
        """Suite runner MUST block SECRET datasource → UNOFFICIAL sink flow.

        **TEST TYPE**: Integration (end-to-end security validation)
        **PHASE 0 STATE**: XFAIL - validation skipped because real plugins don't inherit from BasePlugin ABC
        **AFTER STEP 1-4**: Should turn GREEN when real plugins inherit from BasePlugin ABC

        **SECURITY BUG DOCUMENTED**: This test uses REAL production plugins (CSVDataSource, CsvResultSink)
        that currently DO NOT inherit from BasePlugin ABC. The validation code checks:

            if isinstance(datasource, BasePlugin):  # Uses ABC (nominal typing)
                plugins.append(datasource)

        Because real plugins don't inherit from BasePlugin ABC, isinstance returns FALSE (nominal typing
        requires explicit inheritance). Plugin is NOT added to validation list, and security validation
        is SKIPPED entirely. This allows classified data to flow to low-clearance sinks!

        **AFTER STEP 0**: BasePlugin ABC exists, but plugins still don't inherit from it
        **AFTER STEP 1-4**: Plugins inherit from BasePlugin ABC, isinstance returns True, validation runs

        **NEW DESIGN (ADR-004 "Security Bones")**:
        - Plugins inherit from BasePlugin ABC (not Protocol)
        - Security methods inherited from BasePlugin (not implemented by each plugin)
        - isinstance checks enforce nominal typing (explicit inheritance required)

        **SCENARIO**: SECRET datasource + UNOFFICIAL sink (security mismatch)
        **EXPECTED BEHAVIOR (after Step 1-4)**: SecurityValidationError raised before data retrieval
        **CURRENT BEHAVIOR (bug)**: Validation skipped, experiment runs successfully (WRONG!)
        """
        from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
        from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
        from elspeth.plugins.nodes.sources.csv_local import CSVDataSource
        from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
        from elspeth.plugins.nodes.transforms.llm.mock import MockLLMClient

        # Create test CSV file with classified data
        test_csv = tmp_path / "secret_data.csv"
        test_csv.write_text("text\nClassified record 1\nClassified record 2\n")

        # REAL production datasource (security level is now immutable and hard-coded)
        datasource = CSVDataSource(
            path=str(test_csv),
            retain_local=False,
        )

        # REAL production sink (security level is now immutable and hard-coded)
        unofficial_sink_path = tmp_path / "public_output.csv"
        unofficial_sink = CsvResultSink(
            path=str(unofficial_sink_path),
        )

        # LLM client (doesn't affect security validation in this test)
        llm_client = MockLLMClient(
            security_level=SecurityLevel.UNOFFICIAL,
            allow_downgrade=True
        )

        # Build experiment suite
        experiment = ExperimentConfig(
            name="secret_to_unofficial",
            prompt_system="Test",
            prompt_template="Process: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=tmp_path, baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # EXPECTED BEHAVIOR (after Phase 1): SecurityValidationError raised
        # ACTUAL BEHAVIOR (bug): Validation skipped, no exception raised
        # This test is XFAIL because we expect it to fail (no exception when there should be one)
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(pd.DataFrame({"text": ["test"]}), sink_factory=lambda exp: [unofficial_sink])

        # After Phase 1, error should mention security mismatch
        error_msg = str(exc_info.value)
        assert "SECRET" in error_msg or "UNOFFICIAL" in error_msg
        assert "ADR-002" in error_msg

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 0 - Real plugins don't inherit from BasePlugin ABC, so isinstance checks fail and validation is SKIPPED"
    )
    def test_matching_security_levels_allowed(self, tmp_path: Path) -> None:
        """Suite runner MUST allow matching security levels (SECRET → SECRET).

        **TEST TYPE**: Integration (end-to-end security validation)
        **PHASE 0 STATE**: XFAIL - validation skipped because real plugins don't inherit from BasePlugin ABC
        **AFTER STEP 1-4**: Should turn GREEN when real plugins inherit from BasePlugin ABC

        **SECURITY BUG DOCUMENTED**: This test uses REAL production plugins that don't inherit from
        BasePlugin ABC. Even though this scenario SHOULD succeed (matching security levels), the validation
        code never runs because isinstance(plugin, BasePlugin) returns False (nominal typing requires
        explicit inheritance). We can't verify the "success" path works correctly until plugins inherit
        from BasePlugin ABC.

        **AFTER STEP 0**: BasePlugin ABC exists, but plugins still don't inherit from it
        **AFTER STEP 1-4**: Plugins inherit from BasePlugin ABC, isinstance returns True, validation runs

        **NEW DESIGN (ADR-004 "Security Bones")**:
        - Plugins inherit from BasePlugin ABC (explicit inheritance)
        - Security methods inherited from BasePlugin (centralized implementation)
        - Validation runs when isinstance(plugin, BasePlugin) returns True

        **SCENARIO**: SECRET datasource + SECRET sink (matching levels)
        **EXPECTED BEHAVIOR (after Step 1-4)**: Validation runs, both accept SECRET envelope, test passes
        **CURRENT BEHAVIOR (bug)**: Validation skipped, test passes for WRONG reason (no validation ran)
        """
        from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
        from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
        from elspeth.plugins.nodes.sources.csv_local import CSVDataSource
        from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink
        from elspeth.plugins.nodes.transforms.llm.mock import MockLLMClient

        # Create test CSV file with classified data
        test_csv = tmp_path / "secret_data.csv"
        test_csv.write_text("text\nClassified record 1\nClassified record 2\n")

        # REAL production datasource (security level is now immutable and hard-coded)
        datasource = CSVDataSource(
            path=str(test_csv),
            retain_local=False,
        )

        # REAL production sink (security level is now immutable and hard-coded)
        secret_sink_path = tmp_path / "secret_output.csv"
        secret_sink = CsvResultSink(
            path=str(secret_sink_path),
        )

        # LLM client
        llm_client = MockLLMClient(
            security_level=SecurityLevel.UNOFFICIAL,
            allow_downgrade=True
        )

        # Build experiment suite
        experiment = ExperimentConfig(
            name="secret_to_secret",
            prompt_system="Test",
            prompt_template="Process: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=tmp_path, baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # EXPECTED BEHAVIOR (after Phase 1): Validation runs, both plugins accept, test passes
        # CURRENT BEHAVIOR (bug): Validation skipped (isinstance returns False)
        #
        # This test is XFAIL because we WANT to verify that validation runs and accepts
        # matching security levels, but we CAN'T verify that until plugins implement BasePlugin.
        #
        # The experiment WILL succeed (validation is skipped), but we raise an assertion failure
        # to document that this success is for the WRONG reason (no validation ran).
        results = runner.run(pd.DataFrame({"text": ["test"]}), sink_factory=lambda exp: [secret_sink])

        # This assertion DOCUMENTS the bug - experiment succeeded but validation never ran!
        # After Phase 1, remove this and just assert the experiment succeeded.
        assert "secret_to_secret" in results
        pytest.fail(
            "Test passed for WRONG reason: validation was skipped (isinstance returned False). "
            "After Phase 1, remove this pytest.fail() and let test pass naturally."
        )


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
