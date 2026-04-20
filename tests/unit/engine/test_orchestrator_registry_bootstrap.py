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

# Module-level import so ``_isolate_both_registries`` snapshots a
# fully-populated registry even when this file is the *only* one pytest
# collects (``pytest test_orchestrator_registry_bootstrap.py::test_x`` in
# isolation). Without this, the first test's ``importlib.reload(pt_mod)``
# triggers a duplicate-registration error because the initial import and the
# reload both fire the module-level side-effect against a fresh registry.
import elspeth.engine.executors.pass_through  # noqa: F401  — registers PassThroughDeclarationContract


@pytest.fixture()
def _isolate_both_registries():
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
    RuntimeError naming every contract missing from the manifest.

    This is the core safety guarantee of ADR-010 §Decision 3: a silently empty
    registry disables all runtime VAL checks. prepare_for_run() must make that
    failure visible immediately with an explicit missing-contract diff.
    """
    from elspeth.contracts.declaration_contracts import (
        EXPECTED_CONTRACTS,
        _clear_registry_for_tests,
    )
    from elspeth.engine.orchestrator import prepare_for_run

    # Clear the registry WITHOUT re-importing pass_through.py — simulates an
    # import-order bug where the module-level side-effect never fired.
    _clear_registry_for_tests()

    with pytest.raises(RuntimeError) as exc_info:
        prepare_for_run()

    message = str(exc_info.value)
    assert "declaration contract registry mismatch" in message.lower()
    # Every expected contract must be explicitly named in the diff.
    for expected_name in EXPECTED_CONTRACTS:
        assert repr(expected_name) in message or expected_name in message, (
            f"Error message must name missing contract {expected_name!r}; got: {message}"
        )


def test_bootstrap_fails_when_specific_contract_conditionally_skipped(_isolate_both_registries) -> None:
    """Simulates the C2 failure mode: a *subset* of expected contracts is
    registered (e.g. a conditional import silently skipped PassThroughDeclarationContract).

    The registry is non-empty — the old ``if not contracts`` check would have
    passed. The new set-equality check must raise with ``missing:`` naming
    ``passes_through_input`` explicitly.

    This is the acceptance criterion from elspeth-b03c6112c0 ("ConditionalRegistration
    test path — wrapping a contract's registration in an `if` that skips fails
    bootstrap loudly").
    """
    from typing import TypedDict

    from elspeth.contracts.declaration_contracts import (
        _clear_registry_for_tests,
        register_declaration_contract,
    )
    from elspeth.engine.orchestrator import prepare_for_run

    class _DummyPayload(TypedDict):
        reason: str

    class _UnexpectedContract:
        name = "unexpected_for_c2_test"
        payload_schema: type = _DummyPayload

        def applies_to(self, plugin: object) -> bool:
            return False

        def runtime_check(self, inputs: object, outputs: object) -> None:
            pass

        @classmethod
        def negative_example(cls):  # type: ignore[override]
            raise NotImplementedError

        @classmethod
        def positive_example_does_not_apply(cls):  # type: ignore[override]
            # N2 Layer A: fixture registered only for this bootstrap test;
            # never exercised by the invariant harness.
            raise NotImplementedError

    # Clear registry, then register ONLY an unexpected contract — pass_through
    # is missing. The registry is non-empty, so a bare truthiness check would
    # pass. The manifest-equality check must catch this.
    _clear_registry_for_tests()
    register_declaration_contract(_UnexpectedContract())

    with pytest.raises(RuntimeError) as exc_info:
        prepare_for_run()

    message = str(exc_info.value)
    # The canonical PassThroughDeclarationContract name must appear under "missing".
    assert "passes_through_input" in message, f"Expected error to name missing contract 'passes_through_input'; got: {message}"
    assert "missing" in message.lower()


def test_bootstrap_fails_when_extra_contract_registered(_isolate_both_registries) -> None:
    """If a contract outside the manifest is registered, bootstrap must raise.

    Set-equality — not subset — is the safety guarantee. An extra registration
    indicates the manifest is out of date; CI should have caught it. Bootstrap
    is the last line of defence.
    """
    import importlib
    from typing import TypedDict

    from elspeth.contracts.declaration_contracts import (
        _clear_registry_for_tests,
        register_declaration_contract,
    )
    from elspeth.engine.orchestrator import prepare_for_run

    class _DummyPayload(TypedDict):
        reason: str

    class _UnexpectedContract:
        name = "extra_not_in_manifest"
        payload_schema: type = _DummyPayload

        def applies_to(self, plugin: object) -> bool:
            return False

        def runtime_check(self, inputs: object, outputs: object) -> None:
            pass

        @classmethod
        def negative_example(cls):  # type: ignore[override]
            raise NotImplementedError

        @classmethod
        def positive_example_does_not_apply(cls):  # type: ignore[override]
            # N2 Layer A: fixture registered only for this bootstrap test;
            # never exercised by the invariant harness.
            raise NotImplementedError

    # Clear + re-register PassThrough so manifest is satisfied, then add an
    # unexpected extra contract.
    _clear_registry_for_tests()
    import elspeth.engine.executors.pass_through as pt_mod

    importlib.reload(pt_mod)
    register_declaration_contract(_UnexpectedContract())

    with pytest.raises(RuntimeError) as exc_info:
        prepare_for_run()

    message = str(exc_info.value)
    assert "extra_not_in_manifest" in message, f"Expected error to name extra contract 'extra_not_in_manifest'; got: {message}"
    assert "extra" in message.lower()


def test_bootstrap_passes_when_registry_exactly_matches_manifest(_isolate_both_registries) -> None:
    """The happy path: registry == EXPECTED_CONTRACTS → no exception, registries freeze.

    Verifies the set-equality check permits the nominal case. Uses the
    importlib.reload pattern to re-trigger pass_through.py's module-level
    registration side-effect after _clear_registry_for_tests().
    """
    import importlib

    from elspeth.contracts.declaration_contracts import (
        _clear_registry_for_tests,
        declaration_registry_is_frozen,
    )
    from elspeth.engine.orchestrator import prepare_for_run

    _clear_registry_for_tests()
    import elspeth.engine.executors.pass_through as pt_mod

    importlib.reload(pt_mod)

    # Must not raise.
    prepare_for_run()
    assert declaration_registry_is_frozen()


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

        @classmethod
        def positive_example_does_not_apply(cls):  # type: ignore[override]
            # N2 Layer A: fixture registered only for this bootstrap test;
            # never exercised by the invariant harness.
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

        @tier_1_error(reason="post-bootstrap: must fail", caller_module=__name__)
        class _TooLate(Exception):
            pass


def test_resume_calls_prepare_for_run() -> None:
    """resume() must call prepare_for_run() before any recovery work.

    The resume path runs in a new process. Module-level imports ensure
    PassThroughDeclarationContract is registered, but without an explicit
    prepare_for_run() call the registries are never frozen — leaving a window
    where register_declaration_contract() could succeed after bootstrap.

    This structural test confirms the call is present without requiring
    a full Orchestrator construction (which needs a live LandscapeDB).
    """
    import inspect

    from elspeth.engine.orchestrator.core import Orchestrator

    source = inspect.getsource(Orchestrator.resume)
    assert "prepare_for_run" in source, (
        "Orchestrator.resume() must invoke prepare_for_run() to freeze registries on the recovery path (ADR-010 §Decision 3)"
    )
