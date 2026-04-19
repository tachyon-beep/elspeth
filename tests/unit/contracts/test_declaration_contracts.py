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
            # C4 closure: ``contract_name`` is attached by the dispatcher from
            # the registry entry; contracts MUST NOT supply it here.
            raise DeclarationContractViolation(
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
def _isolate_registry():
    """Each declaration-contracts test starts with an empty registry and has
    the frozen flag reset to ``False``. After the test, the full prior state
    (registry contents + frozen flag) is restored so subsequent tests in the
    same worker process are not affected.

    Setup/teardown bypass ``_clear_registry_for_tests`` and write directly to
    ``dc._REGISTRY`` / ``dc._FROZEN``. Two reasons:
    (1) issue elspeth-cc511e7234 (C3) removed the ``ELSPETH_TESTING=1`` unlock
        from the helper; the only unlock is ``"pytest" in sys.modules``.
    (2) Some tests deliberately pop ``pytest`` from ``sys.modules`` (to
        prove production gating works). After such a test's body returns,
        pytest's ``monkeypatch`` teardown restores ``sys.modules``, but its
        teardown ordering relative to this fixture is not a guarantee we
        should rely on. Writing module attributes directly is unconditional,
        pytest-state-independent, and matches what the helper does internally
        anyway.
    """
    import elspeth.contracts.declaration_contracts as dc

    # Snapshot current state before the test touches anything.
    saved_registry = list(dc._REGISTRY)
    saved_frozen = dc._FROZEN

    # Setup: clear by direct attribute mutation (bypasses the pytest gate).
    dc._REGISTRY.clear()
    dc._FROZEN = False
    yield

    # Teardown: restore pre-test state by direct mutation.
    dc._REGISTRY.clear()
    dc._REGISTRY.extend(saved_registry)
    dc._FROZEN = saved_frozen


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
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"api_key": "sk-abcdef1234567890abcdef1234567890"},
        message="m",
    )
    # to_audit_dict reads contract_name, so attach before inspecting.
    v._attach_contract_name("t")
    dump = v.to_audit_dict()
    assert dump["payload"]["api_key"] == "<redacted-secret>"


def test_runtime_check_raises_violation() -> None:
    """Invoke the contract through the dispatcher so C4's contract_name
    attribution path is exercised. The pre-C4 version of this test called
    ``c.runtime_check`` directly and relied on the contract self-labelling;
    after C4 the authoritative label comes from the registry via the
    dispatcher, so driving the check end-to-end is the honest assertion."""
    from elspeth.engine.executors.declaration_dispatch import run_runtime_checks

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
        run_runtime_checks(inputs=inputs, outputs=outputs)
    assert exc_info.value.contract_name == "fake_declaration"


def test_emitted_rows_is_frozen_tuple() -> None:
    outputs = RuntimeCheckOutputs(emitted_rows=[1, 2, 3])
    assert isinstance(outputs.emitted_rows, tuple)  # freeze guard converts list→tuple


def test_emitted_rows_non_list_non_tuple_raises() -> None:
    """Offensive guard: arbitrary Sequence subtypes must not silently bypass
    the freeze guard. Lazy wrappers and iterators are the motivating case."""

    class _LazySeq:
        """Minimal Sequence subtype that would deceive static typing."""

        def __init__(self, items):
            self._items = items

        def __len__(self):
            return len(self._items)

        def __getitem__(self, i):
            return self._items[i]

    with pytest.raises(TypeError, match="must be list or tuple"):
        RuntimeCheckOutputs(emitted_rows=_LazySeq([1, 2, 3]))  # type: ignore[arg-type]


def test_negative_example_fires_the_violation() -> None:
    """This is the invariant every 2B/2C contract must satisfy."""
    c = _FakeContract()
    inputs, outputs = c.negative_example()
    with pytest.raises(DeclarationContractViolation):
        c.runtime_check(inputs, outputs)


def test_violation_to_audit_dict_contains_all_identity_fields() -> None:
    """Regression test: all identity fields must surface to the audit trail
    (attributability invariant per reviewer B16)."""
    v = DeclarationContractViolation(
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"k": "v"},
        message="m",
    )
    # Simulate dispatcher attribution so to_audit_dict's contract_name read
    # does not hit the pre-attach guard.
    v._attach_contract_name("c")
    dump = v.to_audit_dict()
    expected_keys = {
        "exception_type",
        "contract_name",
        "plugin",
        "node_id",
        "run_id",
        "row_id",
        "token_id",
        "payload",
        "message",
    }
    assert set(dump.keys()) == expected_keys
    assert dump["row_id"] == "rw"


def test_fake_contract_satisfies_declaration_contract_protocol() -> None:
    """@runtime_checkable verification — _FakeContract satisfies the Protocol."""
    from elspeth.contracts.declaration_contracts import DeclarationContract

    c = _FakeContract()
    assert isinstance(c, DeclarationContract)


# ---------------------------------------------------------------------------
# C4 — DeclarationContractViolation: contract_name must come from the
# dispatcher, not the caller. Mutation post-construction must raise.
# ---------------------------------------------------------------------------


def test_violation_init_does_not_accept_contract_name_kwarg() -> None:
    """C4 Part 1 (issue elspeth-d74fe81529): contract_name must not be a
    caller-supplied parameter. The authoritative name is attached by the
    dispatcher from the firing contract's registry entry; allowing callers
    to supply it lets one contract spoof another's identity in the audit
    trail.
    """
    with pytest.raises(TypeError):
        DeclarationContractViolation(
            contract_name="spoofed",  # type: ignore[call-arg]
            plugin="P",
            node_id="n",
            run_id="r",
            row_id="rw",
            token_id="tk",
            payload={"k": "v"},
            message="m",
        )


def test_violation_contract_name_read_before_dispatcher_attach_raises() -> None:
    """Reading ``violation.contract_name`` before the dispatcher has attached
    the authoritative name must raise, so a stray raise path that bypasses
    the dispatcher cannot silently serialize ``contract_name=None`` into the
    audit record.
    """
    v = DeclarationContractViolation(
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"k": "v"},
        message="m",
    )
    with pytest.raises((RuntimeError, AttributeError)):
        _ = v.contract_name


def test_violation_contract_name_is_read_only_after_attach() -> None:
    """C4 Part 2: ``violation.contract_name = "other"`` must raise
    AttributeError. Use the dispatcher-simulating helper to attach a name,
    then verify reassignment is rejected.
    """
    v = DeclarationContractViolation(
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"k": "v"},
        message="m",
    )
    v._attach_contract_name("contract_a")
    assert v.contract_name == "contract_a"
    with pytest.raises(AttributeError):
        v.contract_name = "contract_b"  # type: ignore[misc]


def test_violation_contract_name_attach_is_one_shot() -> None:
    """_attach_contract_name must reject a second call — guards against a
    misbehaving dispatcher or other code path trying to overwrite the
    authoritative name after it has been set.
    """
    v = DeclarationContractViolation(
        plugin="P",
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        payload={"k": "v"},
        message="m",
    )
    v._attach_contract_name("first")
    with pytest.raises(RuntimeError, match="already"):
        v._attach_contract_name("second")


def test_violation_declares_slots() -> None:
    """C4 Part 2: ``DeclarationContractViolation`` declares ``__slots__`` for
    every identity field. ``BaseException`` unavoidably carries a ``__dict__``,
    so __slots__ here is primarily a code-review signal + memory/speed win
    for the named fields — the mutation guarantee comes from the
    ``contract_name`` property. Assert the declaration exists so a future
    author doesn't quietly remove it.
    """
    slots = set(DeclarationContractViolation.__slots__)
    assert "_contract_name" in slots
    for field in ("plugin", "node_id", "run_id", "row_id", "token_id", "payload"):
        assert field in slots, f"{field} missing from __slots__: {slots}"


def test_dispatcher_attaches_contract_name_from_registry() -> None:
    """End-to-end C4 Part 1 acceptance: when a registered contract's
    ``runtime_check`` raises a DeclarationContractViolation WITHOUT
    supplying a name (new signature), the dispatcher attaches
    ``contract.name`` from the registry before the violation propagates.
    """
    from elspeth.contracts.declaration_contracts import (
        RuntimeCheckInputs,
        RuntimeCheckOutputs,
        register_declaration_contract,
    )
    from elspeth.engine.executors.declaration_dispatch import run_runtime_checks

    class _AttackerPayload(TypedDict):
        reason: str

    class _AttackerContract:
        """A contract that attempts to fire — the dispatcher must label the
        resulting violation with THIS contract's name, regardless of what the
        runtime_check body thought it was producing."""

        name = "authentic_contract_name"
        payload_schema: type = _AttackerPayload

        def applies_to(self, plugin: object) -> bool:
            return True

        def runtime_check(self, inputs: RuntimeCheckInputs, outputs: RuntimeCheckOutputs) -> None:
            raise DeclarationContractViolation(
                plugin="P",
                node_id="n",
                run_id="r",
                row_id="rw",
                token_id="tk",
                payload={"reason": "test"},
                message="under test",
            )

        @classmethod
        def negative_example(cls):  # type: ignore[override]
            raise NotImplementedError

    register_declaration_contract(_AttackerContract())

    inputs = RuntimeCheckInputs(
        plugin=_FakePlugin(),
        node_id="n",
        run_id="r",
        row_id="rw",
        token_id="tk",
        input_row=object(),
        static_contract=frozenset(),
    )
    outputs = RuntimeCheckOutputs(emitted_rows=(object(),))

    with pytest.raises(DeclarationContractViolation) as exc_info:
        run_runtime_checks(inputs=inputs, outputs=outputs)
    # Dispatcher wrote the authoritative name onto the violation.
    assert exc_info.value.contract_name == "authentic_contract_name"


def test_clear_registry_without_pytest_env_raises(monkeypatch) -> None:
    """_clear_registry_for_tests is pytest-gated; must not be callable in
    production."""
    import sys

    # Simulate non-test process: remove pytest from sys.modules. After the C3
    # fix (issue elspeth-cc511e7234) the ELSPETH_TESTING env var is no longer
    # an unlock path, so clearing it is no longer needed — but we drop it
    # anyway so the test is unambiguous about what it is verifying.
    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.delenv("ELSPETH_TESTING", raising=False)
    with pytest.raises(RuntimeError, match="pytest"):
        _clear_registry_for_tests()


def test_env_var_alone_does_not_unlock_clear_registry(monkeypatch) -> None:
    """ADR-010 / issue elspeth-cc511e7234 (C3): ``ELSPETH_TESTING=1`` MUST NOT
    be an independent unlock path for ``_clear_registry_for_tests``.

    Pre-fix semantics were ``pytest in sys.modules OR env_var == "1"``, which
    exposed a production bypass: any parent process leaking ``ELSPETH_TESTING=1``
    into its child's environment could clear the runtime VAL registry in prod.
    Post-fix semantics are ``pytest in sys.modules`` alone; the env var is inert.
    """
    import sys

    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.setenv("ELSPETH_TESTING", "1")
    with pytest.raises(RuntimeError, match="pytest"):
        _clear_registry_for_tests()


def test_env_var_alone_does_not_unlock_snapshot_registry(monkeypatch) -> None:
    """Symmetric to the _clear assertion: snapshot must also be pytest-gated only."""
    import sys

    from elspeth.contracts.declaration_contracts import _snapshot_registry_for_tests

    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.setenv("ELSPETH_TESTING", "1")
    with pytest.raises(RuntimeError, match="pytest"):
        _snapshot_registry_for_tests()


def test_env_var_alone_does_not_unlock_restore_registry(monkeypatch) -> None:
    """Symmetric to the _clear assertion: restore must also be pytest-gated only."""
    import sys

    from elspeth.contracts.declaration_contracts import _restore_registry_snapshot_for_tests

    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.setenv("ELSPETH_TESTING", "1")
    with pytest.raises(RuntimeError, match="pytest"):
        # Argument shape is irrelevant: the gate fires before any work.
        _restore_registry_snapshot_for_tests(([], False))
