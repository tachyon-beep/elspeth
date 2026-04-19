"""DeclarationContract protocol + registry + violation (ADR-010 §Decision 3)."""

from __future__ import annotations

from types import MappingProxyType
from typing import TypedDict

import pytest

from elspeth.contracts.declaration_contracts import (
    DeclarationContractViolation,
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
    _clear_registry_for_tests,
    freeze_declaration_registry,
    register_declaration_contract,
    registered_declaration_contracts,
)


class _FakePayload(TypedDict):
    reason: str


class _FakeContract:
    name = "fake_declaration"
    payload_schema: type = _FakePayload

    def applies_to(self, plugin: object) -> bool:
        # Direct attribute access — NOT getattr with default (CLAUDE.md).
        return plugin.__class__.__name__ == "_FakePlugin" and plugin.fake_flag

    def runtime_check(self, inputs: RuntimeCheckInputs, outputs: RuntimeCheckOutputs) -> None:
        if inputs.plugin.fake_violate:
            raise DeclarationContractViolation(
                contract_name="fake_declaration",
                plugin=type(inputs.plugin).__name__,
                node_id=inputs.node_id,
                run_id=inputs.run_id,
                row_id=inputs.row_id,
                token_id=inputs.token_id,
                payload={"reason": "fake"},
                message="fake violation",
            )

    @classmethod
    def negative_example(cls) -> tuple[RuntimeCheckInputs, RuntimeCheckOutputs]:
        plugin = _FakePlugin()
        plugin.fake_violate = True
        return (
            RuntimeCheckInputs(
                plugin=plugin,
                node_id="n",
                run_id="r",
                row_id="rw",
                token_id="t",
                input_row=object(),
                static_contract=frozenset(),
            ),
            RuntimeCheckOutputs(emitted_rows=(object(),)),
        )


class _FakePlugin:
    fake_flag = True
    fake_violate = False


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch):
    monkeypatch.setenv("ELSPETH_TESTING", "1")
    _clear_registry_for_tests()
    yield
    # Teardown: force the env guard open directly in case the test patched it
    # out (e.g. test_clear_registry_without_pytest_env_raises removes both
    # pytest from sys.modules and ELSPETH_TESTING from env before returning).
    import os as _os

    _saved = _os.environ.get("ELSPETH_TESTING")
    _os.environ["ELSPETH_TESTING"] = "1"
    try:
        _clear_registry_for_tests()
    finally:
        if _saved is None:
            _os.environ.pop("ELSPETH_TESTING", None)
        else:
            _os.environ["ELSPETH_TESTING"] = _saved


def test_register_adds_to_registry() -> None:
    c = _FakeContract()
    register_declaration_contract(c)
    assert c in registered_declaration_contracts()


def test_duplicate_name_raises() -> None:
    register_declaration_contract(_FakeContract())
    with pytest.raises(ValueError, match="duplicate contract name"):
        register_declaration_contract(_FakeContract())


def test_contract_without_payload_schema_rejected() -> None:
    class _NoSchema:
        name = "no_schema"

        # payload_schema attribute missing
        def applies_to(self, p):
            return False

        def runtime_check(self, i, o):
            pass

        @classmethod
        def negative_example(cls):
            raise NotImplementedError

    with pytest.raises(TypeError, match="payload_schema"):
        register_declaration_contract(_NoSchema())  # type: ignore[arg-type]


def test_contract_without_negative_example_rejected() -> None:
    class _NoNeg:
        name = "no_neg"
        payload_schema = _FakePayload

        def applies_to(self, p):
            return False

        def runtime_check(self, i, o):
            pass

        # negative_example missing

    with pytest.raises(TypeError, match="negative_example"):
        register_declaration_contract(_NoNeg())  # type: ignore[arg-type]


def test_registration_after_freeze_raises() -> None:
    freeze_declaration_registry()
    with pytest.raises(Exception, match="frozen"):
        register_declaration_contract(_FakeContract())


def test_violation_inherits_audit_evidence_base() -> None:
    from elspeth.contracts.audit_evidence import AuditEvidenceBase

    v = DeclarationContractViolation(
        contract_name="t",
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"k": "v"},
        message="m",
    )
    assert isinstance(v, AuditEvidenceBase)


def test_violation_payload_is_deep_frozen() -> None:
    v = DeclarationContractViolation(
        contract_name="t",
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"outer": {"inner": [1, 2]}},
        message="m",
    )
    assert isinstance(v.payload, MappingProxyType)
    # nested dict also frozen
    assert isinstance(v.payload["outer"], MappingProxyType)
    # nested list is now tuple
    assert isinstance(v.payload["outer"]["inner"], tuple)


def test_violation_payload_secrets_scrubbed() -> None:
    v = DeclarationContractViolation(
        contract_name="t",
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"api_key": "sk-abcdef1234567890abcdef1234567890"},
        message="m",
    )
    dump = v.to_audit_dict()
    assert dump["payload"]["api_key"] == "<redacted-secret>"


def test_runtime_check_raises_violation() -> None:
    c = _FakeContract()
    register_declaration_contract(c)

    plugin = _FakePlugin()
    plugin.fake_violate = True
    inputs = RuntimeCheckInputs(
        plugin=plugin,
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="t",
        input_row=object(),
        static_contract=frozenset(),
    )
    outputs = RuntimeCheckOutputs(emitted_rows=(object(),))

    with pytest.raises(DeclarationContractViolation) as exc_info:
        c.runtime_check(inputs, outputs)
    assert exc_info.value.contract_name == "fake_declaration"


def test_emitted_rows_is_frozen_tuple() -> None:
    outputs = RuntimeCheckOutputs(emitted_rows=[1, 2, 3])
    assert isinstance(outputs.emitted_rows, tuple)  # freeze guard converts list→tuple


def test_negative_example_fires_the_violation() -> None:
    """This is the invariant every 2B/2C contract must satisfy."""
    c = _FakeContract()
    inputs, outputs = c.negative_example()
    with pytest.raises(DeclarationContractViolation):
        c.runtime_check(inputs, outputs)


def test_clear_registry_without_pytest_env_raises(monkeypatch) -> None:
    """_clear_registry_for_tests is pytest-gated; must not be callable in
    production."""
    import sys

    # Simulate non-test process: remove pytest from sys.modules AND clear env var.
    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.delenv("ELSPETH_TESTING", raising=False)
    with pytest.raises(RuntimeError, match="pytest"):
        _clear_registry_for_tests()
