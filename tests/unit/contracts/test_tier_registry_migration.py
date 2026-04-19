"""Pre/post migration parity (ADR-010 §Decision 2) plus AuditEvidenceBase widening."""

from __future__ import annotations


def test_all_four_pre_migration_members_remain_tier_1() -> None:
    from elspeth.contracts.errors import (
        AuditIntegrityError,
        FrameworkBugError,
        OrchestrationInvariantError,
        PassThroughContractViolation,
    )
    from elspeth.contracts.tier_registry import TIER_1_ERRORS

    for cls in (AuditIntegrityError, FrameworkBugError, OrchestrationInvariantError, PassThroughContractViolation):
        assert cls in TIER_1_ERRORS, f"{cls.__name__} missing from TIER_1_ERRORS after migration"


def test_plugin_contract_violation_is_NOT_tier_1() -> None:
    """Base class stays out (ADR-008: plugin bug != framework corruption)."""
    from elspeth.contracts.errors import PluginContractViolation
    from elspeth.contracts.tier_registry import TIER_1_ERRORS

    assert PluginContractViolation not in TIER_1_ERRORS


def test_plugin_contract_violation_is_audit_evidence() -> None:
    """But PluginContractViolation DOES inherit AuditEvidenceBase after Task 4."""
    from elspeth.contracts.audit_evidence import AuditEvidenceBase
    from elspeth.contracts.errors import PluginContractViolation

    assert issubclass(PluginContractViolation, AuditEvidenceBase)


def test_errors_module_tier_1_errors_is_live_view_not_snapshot() -> None:
    """Regression test for reviewer B8.

    Before v1: from elspeth.contracts.errors import TIER_1_ERRORS captured a
    snapshot; late registrations never reached errors-module callers. After
    v1: errors.TIER_1_ERRORS is a module __getattr__ returning the live tuple.
    """
    from elspeth.contracts import errors as errors_mod
    from elspeth.contracts import tier_registry

    before = errors_mod.TIER_1_ERRORS
    # Cannot register after freeze; simulate a non-frozen scenario by
    # temporarily flipping the freeze flag.
    prior_frozen = tier_registry._FROZEN
    tier_registry._FROZEN = False
    try:

        class _TempViolation(Exception):
            pass

        tier_registry._register_with_module_prefix(
            cls=_TempViolation,
            reason="regression test for live view",
            caller_module="elspeth.contracts.test_only",
        )
        after = errors_mod.TIER_1_ERRORS
        assert _TempViolation in after, "errors.TIER_1_ERRORS did not reflect late registration"
        assert _TempViolation not in before, "Test setup error — class pre-existed"
    finally:
        # Rollback: pop the temp registration.
        tier_registry._REGISTRY.remove(_TempViolation)
        tier_registry._REASONS.pop(_TempViolation, None)
        tier_registry._FROZEN = prior_frozen


def test_tier_1_reason_is_non_empty_for_all_members() -> None:
    from elspeth.contracts.tier_registry import TIER_1_ERRORS, tier_1_reason

    for cls in TIER_1_ERRORS:
        reason = tier_1_reason(cls)
        assert reason and reason.strip(), f"{cls.__name__} registered without meaningful reason"
