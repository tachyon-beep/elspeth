"""Dispatcher iterates registry; propagates violations; propagates unexpected
exceptions (plugin-ownership posture per CLAUDE.md)."""

from __future__ import annotations

from typing import Any, TypedDict

import pytest

from elspeth.contracts.declaration_contracts import (
    DeclarationContractViolation,
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
    _clear_registry_for_tests,
    _restore_registry_snapshot_for_tests,
    _snapshot_registry_for_tests,
    register_declaration_contract,
)
from elspeth.engine.executors.declaration_dispatch import run_runtime_checks


class _Payload(TypedDict):
    note: str


class _AppliesContract:
    name = "applies"
    payload_schema: type = _Payload
    invoked: bool = False

    def applies_to(self, plugin: Any) -> bool:
        return True

    def runtime_check(self, inputs: Any, outputs: Any) -> None:
        _AppliesContract.invoked = True

    @classmethod
    def negative_example(cls):
        return _inputs(), _outputs()


class _SkipsContract:
    name = "skips"
    payload_schema: type = _Payload
    invoked: bool = False

    def applies_to(self, plugin: Any) -> bool:
        return False

    def runtime_check(self, inputs: Any, outputs: Any) -> None:
        _SkipsContract.invoked = True

    @classmethod
    def negative_example(cls):
        return _inputs(), _outputs()


class _RaisesViolationContract:
    name = "raises_violation"
    payload_schema: type = _Payload

    def applies_to(self, plugin: Any) -> bool:
        return True

    def runtime_check(self, inputs, outputs) -> None:
        # C4: contract_name is attached by the dispatcher from the registry;
        # contracts MUST NOT supply it at construction.
        raise DeclarationContractViolation(
            plugin="P",
            node_id="n",
            run_id="r",
            row_id="rw",
            token_id="t",
            payload={"note": "boom"},
            message="boom",
        )

    @classmethod
    def negative_example(cls):
        return _inputs(), _outputs()


class _ApplyRaisesContract:
    """Simulates a buggy contract whose applies_to raises — must propagate."""

    name = "apply_raises"
    payload_schema: type = _Payload

    def applies_to(self, plugin: Any) -> bool:
        raise KeyError("bug in applies_to")

    def runtime_check(self, inputs, outputs) -> None: ...

    @classmethod
    def negative_example(cls):
        return _inputs(), _outputs()


class _CheckRaisesContract:
    name = "check_raises"
    payload_schema: type = _Payload

    def applies_to(self, plugin: Any) -> bool:
        return True

    def runtime_check(self, inputs, outputs) -> None:
        raise RuntimeError("bug in runtime_check")

    @classmethod
    def negative_example(cls):
        return _inputs(), _outputs()


def _inputs() -> RuntimeCheckInputs:
    return RuntimeCheckInputs(
        plugin=object(),
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=object(),
        static_contract=frozenset(),
    )


def _outputs() -> RuntimeCheckOutputs:
    return RuntimeCheckOutputs(emitted_rows=(object(),))


@pytest.fixture(autouse=True)
def _isolate():
    # Save the registry state (e.g. PassThroughDeclarationContract registered
    # via module-level side-effect) so it can be restored after the test.
    # Without this, clearing the registry in one worker would leave all
    # subsequent tests on that worker without the built-in contracts.
    snapshot = _snapshot_registry_for_tests()
    _clear_registry_for_tests()
    _AppliesContract.invoked = False
    _SkipsContract.invoked = False
    yield
    _restore_registry_snapshot_for_tests(snapshot)


def test_dispatch_invokes_applicable_contracts() -> None:
    register_declaration_contract(_AppliesContract())
    register_declaration_contract(_SkipsContract())
    run_runtime_checks(inputs=_inputs(), outputs=_outputs())
    assert _AppliesContract.invoked and not _SkipsContract.invoked


def test_dispatch_propagates_violation() -> None:
    register_declaration_contract(_RaisesViolationContract())
    with pytest.raises(DeclarationContractViolation):
        run_runtime_checks(inputs=_inputs(), outputs=_outputs())


def test_dispatch_propagates_unexpected_exception_from_applies_to() -> None:
    """Reviewer B17 — buggy contract must crash loudly."""
    register_declaration_contract(_ApplyRaisesContract())
    with pytest.raises(KeyError, match="applies_to"):
        run_runtime_checks(inputs=_inputs(), outputs=_outputs())


def test_dispatch_propagates_unexpected_exception_from_runtime_check() -> None:
    register_declaration_contract(_CheckRaisesContract())
    with pytest.raises(RuntimeError, match="runtime_check"):
        run_runtime_checks(inputs=_inputs(), outputs=_outputs())


def test_empty_registry_still_runs() -> None:
    """Bootstrap (Task 5b) asserts the registry is non-empty; the dispatcher
    itself does NOT — it is pure iteration, no-op on empty."""
    run_runtime_checks(inputs=_inputs(), outputs=_outputs())
