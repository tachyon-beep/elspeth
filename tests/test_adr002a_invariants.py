"""ADR-002-A Trusted Container Model - Security Invariant Tests

This module tests the security properties of the ClassifiedDataFrame trusted
container model, which prevents classification laundering attacks.

Security Model (ADR-002-A):
    - Only datasources can create ClassifiedDataFrame instances
    - Plugins can only uplift classifications, never create fresh ones
    - This prevents malicious plugins from relabeling data

Test-First Security Development:
    These tests are written BEFORE implementation (RED state).
    They define security properties that MUST hold after implementation.

Property Testing Strategy:
    Each test verifies a security invariant:
    1. Plugin creation blocked → SecurityValidationError
    2. Datasource creation allowed → Success
    3. Uplifting bypasses check → Success
    4. with_new_data() preserves classification → Success
    5. Classification laundering attack blocked → SecurityValidationError

Expected State: ALL TESTS WILL FAIL (RED) until implementation complete.
"""

import pandas as pd
import pytest

from elspeth.core.base.protocols import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import ClassifiedDataFrame
from elspeth.core.validation.base import SecurityValidationError


# ============================================================================
# Mock Components for Testing
# ============================================================================


class MockDatasource(BasePlugin):
    """Mock datasource for testing datasource-only creation."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.OFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.OFFICIAL:
            raise SecurityValidationError(
                f"MockDatasource requires OFFICIAL, got {operating_level.name}"
            )

    def load(self) -> pd.DataFrame:
        return pd.DataFrame({"data": [1, 2, 3]})


class MockPlugin(BasePlugin):
    """Mock plugin for testing plugin creation blocking."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MockPlugin requires SECRET, got {operating_level.name}"
            )


# ============================================================================
# Security Invariant Tests (RED State - Will FAIL Until Implementation)
# ============================================================================


class TestADR002ATrustedContainerModel:
    """Security invariant tests for ADR-002-A Trusted Container Model.

    These tests define security properties that MUST hold after implementation.
    Expected: ALL TESTS FAIL (RED) in current state.
    """

    def test_invariant_plugin_cannot_create_frame_directly(self):
        """SECURITY INVARIANT: Plugins cannot create ClassifiedDataFrame directly.

        Attack Prevented: Classification laundering
            - Malicious plugin creates "fresh" frame with lower classification
            - Bypasses with_uplifted_classification() uplifting logic
            - Allows SECRET data to be relabeled as OFFICIAL

        Security Property:
            ClassifiedDataFrame(data, level) from plugin context → SecurityValidationError

        Expected State: FAILS (RED) - No __post_init__ validation yet
        """
        df = pd.DataFrame({"secret_data": ["classified1", "classified2"]})

        # Simulate plugin attempting to create frame directly
        # (In real attack, this would be inside plugin.process() method)
        with pytest.raises(SecurityValidationError) as exc_info:
            # ❌ ATTACK: Plugin creates frame claiming OFFICIAL classification
            ClassifiedDataFrame(df, SecurityLevel.OFFICIAL)

        error_msg = str(exc_info.value)
        assert "datasource" in error_msg.lower(), (
            "Error should explain only datasources can create frames"
        )
        assert "plugin" in error_msg.lower() or "must use" in error_msg.lower(), (
            "Error should guide plugins to use with_uplifted_classification()"
        )

    def test_cve_adr002a_002_bypass_flag_not_exposed(self):
        """CVE-ADR-002-A-002: _created_by_datasource parameter bypass BLOCKED.

        Vulnerability:
            Without init=False on _created_by_datasource field, attackers could call:
                ClassifiedDataFrame(data, level, _created_by_datasource=True)
            This bypasses __post_init__ security check, allowing classification laundering.

        Attack Scenario:
            Malicious plugin creates "fresh" frame with UNOFFICIAL classification,
            bypassing uplifting requirements and laundering SECRET data.

        Fix:
            Add init=False to _created_by_datasource field definition to remove
            it from __init__ signature entirely.

        Security Property:
            ClassifiedDataFrame(..., _created_by_datasource=True) → TypeError

        Discovery: Code review by GPT-4 (2025-10-25)
        """
        df = pd.DataFrame({"secret": ["classified1", "classified2"]})

        # Attempt bypass by passing _created_by_datasource=True
        with pytest.raises(TypeError) as exc_info:
            ClassifiedDataFrame(
                data=df,
                classification=SecurityLevel.UNOFFICIAL,  # DOWNGRADE attempt
                _created_by_datasource=True  # Bypass flag
            )

        error_msg = str(exc_info.value)
        assert "_created_by_datasource" in error_msg, (
            "Error should mention the invalid parameter name"
        )
        assert "unexpected keyword argument" in error_msg, (
            "Error should indicate parameter not in __init__ signature"
        )

    def test_invariant_datasource_can_create_frame(self):
        """SECURITY INVARIANT: Datasources can create ClassifiedDataFrame instances.

        Trusted Source Principle:
            - Datasources are TRUSTED to label data correctly
            - They are the authoritative source of classification metadata
            - Certification verifies datasource classification labeling

        Security Property:
            ClassifiedDataFrame.create_from_datasource(data, level) → Success

        Expected State: FAILS (RED) - No create_from_datasource() method yet
        """
        df = pd.DataFrame({"data": [1, 2, 3]})

        # Datasource should be able to create frames using factory method
        frame = ClassifiedDataFrame.create_from_datasource(
            df, SecurityLevel.OFFICIAL
        )

        assert frame.data.equals(df), "Data should be preserved"
        assert frame.classification == SecurityLevel.OFFICIAL, (
            "Classification should match datasource labeling"
        )

    def test_invariant_with_uplifted_classification_bypasses_check(self):
        """SECURITY INVARIANT: with_uplifted_classification() bypasses constructor check.

        Uplifting Design:
            - Uplifting is the ONLY way plugins can create new ClassifiedDataFrame
            - Uses max() operation (cannot downgrade)
            - Bypasses __post_init__ check (internal method, trusted)

        Security Property:
            frame.with_uplifted_classification(level) → Success (no validation error)

        Expected State: MAY FAIL (RED) - Depends on __post_init__ implementation
        """
        # Create initial frame via datasource (trusted source)
        df = pd.DataFrame({"data": [1, 2, 3]})
        initial_frame = ClassifiedDataFrame.create_from_datasource(
            df, SecurityLevel.OFFICIAL
        )

        # Uplifting should succeed (bypasses __post_init__ check)
        uplifted_frame = initial_frame.with_uplifted_classification(
            SecurityLevel.SECRET
        )

        assert uplifted_frame.classification == SecurityLevel.SECRET, (
            "Uplifting should create SECRET frame"
        )
        assert uplifted_frame.data is initial_frame.data, (
            "Should share DataFrame reference (container vs. content separation)"
        )

        # Attempting to "downgrade" should preserve higher classification
        result = uplifted_frame.with_uplifted_classification(SecurityLevel.OFFICIAL)
        assert result.classification == SecurityLevel.SECRET, (
            "max() operation should prevent downgrade"
        )

    def test_invariant_with_new_data_preserves_classification(self):
        """SECURITY INVARIANT: with_new_data() preserves classification, blocks downgrade.

        LLM/Aggregation Pattern:
            - Some plugins generate entirely new DataFrames (LLMs, aggregations)
            - They cannot mutate .data in-place (different schema)
            - Must still preserve/uplift classification (cannot downgrade)

        Security Property:
            frame.with_new_data(df) → New frame with SAME classification
            Must still call with_uplifted_classification() afterwards

        Expected State: FAILS (RED) - No with_new_data() method yet
        """
        # Create initial frame via datasource
        initial_df = pd.DataFrame({"input": ["row1", "row2"]})
        initial_frame = ClassifiedDataFrame.create_from_datasource(
            initial_df, SecurityLevel.SECRET
        )

        # Plugin generates completely new DataFrame
        new_df = pd.DataFrame({"output": ["result1", "result2"]})

        # with_new_data() should create frame with SAME classification
        result_frame = initial_frame.with_new_data(new_df)

        assert result_frame.data.equals(new_df), "Data should be replaced"
        assert result_frame.classification == SecurityLevel.SECRET, (
            "Classification should be preserved from input frame"
        )

        # Plugin must still uplift to its own security level
        plugin_level = SecurityLevel.SECRET
        final_frame = result_frame.with_uplifted_classification(plugin_level)
        assert final_frame.classification == SecurityLevel.SECRET

    def test_invariant_malicious_classification_laundering_blocked(self):
        """SECURITY INVARIANT: Classification laundering attack is technically blocked.

        Attack Scenario (from ADR-002-A):
            1. Malicious plugin receives SECRET data (validated at start-time)
            2. Plugin truthfully reports get_security_level() = SECRET (passes validation)
            3. Plugin processes data, then creates "fresh" frame claiming OFFICIAL
            4. ❌ BLOCKED: Constructor validation prevents direct creation

        Defense Layers:
            - Before ADR-002-A: Certification must review every transformation
            - After ADR-002-A: Framework blocks attack automatically

        Security Property:
            Plugin attempting to create downgraded frame → SecurityValidationError

        Expected State: FAILS (RED) - No constructor protection yet
        """
        # Simulate attack scenario from ADR-002-A specification
        class SubtlyMaliciousPlugin(BasePlugin):
            """Plugin that attempts classification laundering attack."""

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.SECRET  # ✅ Truthful - passes start-time validation

            def validate_can_operate_at_level(
                self, operating_level: SecurityLevel
            ) -> None:
                if operating_level < SecurityLevel.SECRET:
                    raise SecurityValidationError("Requires SECRET")

            def process(
                self, input_data: ClassifiedDataFrame
            ) -> ClassifiedDataFrame:
                """Process SECRET data, attempt to launder classification.

                Attack: Create "fresh" frame claiming OFFICIAL classification,
                bypassing with_uplifted_classification() uplifting logic.
                """
                # Transform data (legitimate operation)
                result = input_data.data.copy()
                result["processed"] = True

                # ❌ ATTACK: Create "fresh" frame claiming lower classification
                # This is the EXACT attack from ADR-002-A specification
                return ClassifiedDataFrame(result, SecurityLevel.OFFICIAL)

        # Set up attack scenario
        secret_data = pd.DataFrame({"classified": ["secret1", "secret2"]})
        secret_frame = ClassifiedDataFrame.create_from_datasource(
            secret_data, SecurityLevel.SECRET
        )

        malicious_plugin = SubtlyMaliciousPlugin()

        # Attack should be BLOCKED by constructor validation
        with pytest.raises(SecurityValidationError) as exc_info:
            malicious_plugin.process(secret_frame)

        error_msg = str(exc_info.value)
        assert "datasource" in error_msg.lower(), (
            "Error should explain only datasources can create frames"
        )

    def test_invariant_method_name_spoofing_blocked(self):
        """SECURITY INVARIANT: Method name spoofing attack is blocked (CVE-ADR-002-A-001).

        Attack Scenario (from Security Review):
            1. Malicious plugin defines a method named 'with_uplifted_classification'
            2. Inside this method, attacker creates ClassifiedDataFrame with arbitrary classification
            3. Frame inspection finds matching name 'with_uplifted_classification'
            4. ❌ BLOCKED: Instance verification detects this is NOT our method

        Vulnerability:
            Before fix: Frame inspection only checked function name
            After fix: Frame inspection verifies caller's 'self' is ClassifiedDataFrame instance

        Security Property:
            Plugin spoofing method name → Still blocked by instance verification

        This test verifies the fix for HIGH severity finding from security review.
        """
        # Simulate name spoofing attack from security review
        class NameSpoofingPlugin(BasePlugin):
            """Plugin that attempts to bypass constructor protection via name spoofing."""

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.SECRET

            def validate_can_operate_at_level(
                self, operating_level: SecurityLevel
            ) -> None:
                if operating_level < SecurityLevel.SECRET:
                    raise SecurityValidationError("Requires SECRET")

            def with_uplifted_classification(self, input_data: ClassifiedDataFrame) -> ClassifiedDataFrame:
                """Spoofed method name - attempt to bypass frame inspection.

                Attack: Create "fresh" frame inside a method named 'with_uplifted_classification'
                to trick frame inspection into thinking this is a legitimate internal call.

                Before Fix: Would succeed (only checked name)
                After Fix: Blocked (verifies 'self' is ClassifiedDataFrame, not NameSpoofingPlugin)
                """
                # ❌ ATTACK: Create frame with lower classification inside spoofed method
                return ClassifiedDataFrame(input_data.data, SecurityLevel.OFFICIAL)

        # Set up attack scenario
        secret_data = pd.DataFrame({"classified": ["secret1", "secret2"]})
        secret_frame = ClassifiedDataFrame.create_from_datasource(
            secret_data, SecurityLevel.SECRET
        )

        spoofing_plugin = NameSpoofingPlugin()

        # Attack should be BLOCKED by instance verification
        with pytest.raises(SecurityValidationError) as exc_info:
            spoofing_plugin.with_uplifted_classification(secret_frame)

        error_msg = str(exc_info.value)
        assert "datasource" in error_msg.lower(), (
            "Error should explain only datasources can create frames"
        )
        # Verify spoofing attack was blocked
        assert exc_info.value is not None, "Spoofing attack should raise SecurityValidationError"

    def test_security_fail_closed_when_frame_unavailable(self, monkeypatch):
        """SECURITY INVARIANT: Fail-closed when stack inspection unavailable (CVE-ADR-002-A-003).

        Attack Prevented: Bypass via exotic runtime or C extension
            - Attacker runs code in environment where inspect.currentframe() returns None
            - Could be exotic Python runtime (PyPy edge case, Jython, embedded Python)
            - Could be malicious C extension that hides call stack

        Security Property (ADR-001 Fail-Closed Principle):
            When security control unavailable (can't inspect stack) → DENY operation
            Never fail-open for convenience - classified data systems MUST fail-closed

        Before Fix: Returned (fail-open) → allowed creation
        After Fix: Raises SecurityValidationError (fail-closed) → denies creation

        Expected State: PASSES (GREEN) after CVE-ADR-002-A-003 fix
        """
        import inspect

        # Mock inspect.currentframe() to return None (simulates unavailable stack inspection)
        monkeypatch.setattr(inspect, "currentframe", lambda: None)

        df = pd.DataFrame({"data": [1, 2, 3]})

        # Should BLOCK creation with clear error (fail-closed)
        with pytest.raises(SecurityValidationError) as exc_info:
            ClassifiedDataFrame(df, SecurityLevel.OFFICIAL)

        error_msg = str(exc_info.value)
        # Verify error explains the security control failure
        assert "stack inspection" in error_msg.lower(), (
            "Error should explain stack inspection unavailable"
        )
        assert "unavailable" in error_msg.lower(), (
            "Error should mention runtime limitation"
        )
        assert "create_from_datasource" in error_msg.lower(), (
            "Error should guide to safe factory method"
        )


# ============================================================================
# Test Summary
# ============================================================================

"""
ADR-002-A Security Invariant Test Coverage:

✅ test_invariant_plugin_cannot_create_frame_directly
   - Property: Direct construction from plugin → SecurityValidationError
   - Attack Prevented: Classification laundering via fresh frame creation
   - Implementation: __post_init__ with frame inspection

✅ test_invariant_datasource_can_create_frame
   - Property: Datasources can create frames via factory method
   - Trusted Source: Datasources are authoritative for classification labels
   - Implementation: create_from_datasource() class method

✅ test_invariant_with_uplifted_classification_bypasses_check
   - Property: Uplifting bypasses __post_init__ validation
   - Design: Uplifting is internal, trusted operation
   - Implementation: Check caller name in __post_init__

✅ test_invariant_with_new_data_preserves_classification
   - Property: New data generation preserves classification
   - Use Case: LLMs, aggregations generating new DataFrames
   - Implementation: with_new_data() method

✅ test_invariant_malicious_classification_laundering_blocked
   - Property: End-to-end attack scenario blocked
   - Attack: Malicious plugin creating downgraded frame
   - Certification Impact: Reduces review burden (technical control vs. manual)

Total: 5 security invariant tests (expected RED state)

Next: Phase 1 - Implement features to make tests GREEN
"""
