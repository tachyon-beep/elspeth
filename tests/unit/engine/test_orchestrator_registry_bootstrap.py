"""Orchestrator bootstrap freezes the declaration + tier registries and
asserts at least one declaration contract is registered (ADR-010 §Decision 3).

Test isolation strategy:
- Each test saves and restores the full state of both registries
  (contents + freeze flag). This prevents test pollution cascading into
  subsequent tests that rely on contracts being registered.
- The isolation fixture is autouse=False because these tests intentionally
  manipulate registry state; they must not auto-apply to unrelated tests in
  the same module.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def _isolate_both_registries(monkeypatch):
    """Save + restore declaration_contracts and tier_registry module state.

    Saves:
    - declaration_contracts._REGISTRY contents
    - declaration_contracts._FROZEN flag
    - tier_registry._REGISTRY contents
    - tier_registry._REASONS contents
    - tier_registry._FROZEN flag

    Restores all on teardown. This covers both the content and freeze state
    so tests that call prepare_for_run() (which freezes both) do not leave
    subsequent tests with frozen or empty registries.
    """
    import elspeth.contracts.declaration_contracts as dc
    import elspeth.contracts.tier_registry as tr

    # Snapshot current state
    saved_dc_registry = list(dc._REGISTRY)
    saved_dc_frozen = dc._FROZEN
    saved_tr_registry = list(tr._REGISTRY)
    saved_tr_reasons = dict(tr._REASONS)
    saved_tr_frozen = tr._FROZEN

    monkeypatch.setenv("ELSPETH_TESTING", "1")

    yield

    # Restore declaration_contracts state
    dc._REGISTRY.clear()
    dc._REGISTRY.extend(saved_dc_registry)
    dc._FROZEN = saved_dc_frozen

    # Restore tier_registry state
    tr._REGISTRY.clear()
    tr._REGISTRY.extend(saved_tr_registry)
    tr._REASONS.clear()
    tr._REASONS.update(saved_tr_reasons)
    tr._FROZEN = saved_tr_frozen


def test_bootstrap_asserts_registry_non_empty(_isolate_both_registries) -> None:
    """If no contracts are registered at bootstrap, prepare_for_run() must raise
    RuntimeError with a clear message about the import-order bug.

    This is the core safety guarantee of ADR-010 §Decision 3: a silently empty
    registry disables all runtime VAL checks. prepare_for_run() must make that
    failure visible immediately.
    """
    from elspeth.contracts.declaration_contracts import _clear_registry_for_tests
    from elspeth.engine.orchestrator import prepare_for_run

    # Clear the registry WITHOUT re-importing pass_through.py — simulates an
    # import-order bug where the module-level side-effect never fired.
    _clear_registry_for_tests()

    with pytest.raises(RuntimeError, match="no declaration contracts registered"):
        prepare_for_run()


def test_bootstrap_freezes_declaration_registry(_isolate_both_registries) -> None:
    """After prepare_for_run(), the declaration-contract registry must be frozen.

    Subsequent registration attempts must raise FrameworkBugError, proving the
    registry cannot be extended after bootstrap completes.
    """
    import importlib

    from elspeth.contracts.declaration_contracts import (
        _clear_registry_for_tests,
        register_declaration_contract,
    )
    from elspeth.contracts.tier_registry import FrameworkBugError
    from elspeth.engine.orchestrator import prepare_for_run

    # Clear registry and re-import pass_through.py to repopulate
    # PassThroughDeclarationContract via its module-level side-effect.
    _clear_registry_for_tests()
    import elspeth.engine.executors.pass_through as pt_mod

    importlib.reload(pt_mod)

    # Bootstrap: assert non-empty, freeze both registries.
    prepare_for_run()

    # Post-bootstrap: any registration attempt must fail with FrameworkBugError.
    from typing import TypedDict

    class _PostBootstrapPayload(TypedDict):
        reason: str

    class _PostBootstrapContract:
        name = "post_bootstrap_contract"
        payload_schema: type = _PostBootstrapPayload

        def applies_to(self, plugin: object) -> bool:
            return False

        def runtime_check(self, inputs: object, outputs: object) -> None:
            pass

        @classmethod
        def negative_example(cls):  # type: ignore[override]
            raise NotImplementedError

    with pytest.raises(FrameworkBugError):
        register_declaration_contract(_PostBootstrapContract())


def test_bootstrap_freezes_tier_registry(_isolate_both_registries) -> None:
    """After prepare_for_run(), the tier-1 error registry must be frozen.

    Subsequent @tier_1_error registrations must raise FrameworkBugError.
    """
    import importlib

    from elspeth.contracts.declaration_contracts import _clear_registry_for_tests
    from elspeth.contracts.tier_registry import FrameworkBugError, tier_1_error
    from elspeth.engine.orchestrator import prepare_for_run

    # Clear declaration registry and reload pass_through to repopulate.
    _clear_registry_for_tests()
    import elspeth.engine.executors.pass_through as pt_mod

    importlib.reload(pt_mod)

    prepare_for_run()

    # Post-bootstrap: tier-1 registration must fail.
    with pytest.raises(FrameworkBugError, match="frozen"):

        @tier_1_error(reason="post-bootstrap: must fail")
        class _TooLate(Exception):
            pass
