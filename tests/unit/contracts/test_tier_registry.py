"""@tier_1_error(reason=...) decorator + registry tests (ADR-010 §Decision 2)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test gets a clean registry. Uses the module-private reset helper."""
    from elspeth.contracts import tier_registry

    before_registry = list(tier_registry._REGISTRY)
    before_reasons = dict(tier_registry._REASONS)
    before_frozen = tier_registry._FROZEN
    yield
    tier_registry._REGISTRY[:] = before_registry
    tier_registry._REASONS.clear()
    tier_registry._REASONS.update(before_reasons)
    tier_registry._FROZEN = before_frozen


def test_decorator_registers_class() -> None:
    from elspeth.contracts.tier_registry import TIER_1_ERRORS, tier_1_error

    @tier_1_error(reason="test: registered via decorator")
    class _TestViolation(Exception):
        pass

    assert _TestViolation in TIER_1_ERRORS


def test_decorator_requires_reason() -> None:
    from elspeth.contracts.tier_registry import tier_1_error

    with pytest.raises(TypeError, match="reason"):

        @tier_1_error  # missing ()
        class _Bad(Exception):
            pass


def test_reason_must_be_non_empty_string() -> None:
    from elspeth.contracts.tier_registry import tier_1_error

    with pytest.raises(ValueError, match="reason"):

        @tier_1_error(reason="")
        class _Bad(Exception):
            pass


def test_reason_persists_and_is_queryable() -> None:
    from elspeth.contracts.tier_registry import tier_1_error, tier_1_reason

    @tier_1_error(reason="ADR-008: pass-through annotation lie")
    class _Check(Exception):
        pass

    assert tier_1_reason(_Check) == "ADR-008: pass-through annotation lie"


def test_decorator_returns_the_class_unchanged() -> None:
    from elspeth.contracts.tier_registry import tier_1_error

    @tier_1_error(reason="test")
    class _Foo(Exception):
        pass

    assert _Foo.__name__ == "_Foo"


def test_double_registration_idempotent_with_matching_reason() -> None:
    from elspeth.contracts.tier_registry import TIER_1_ERRORS, tier_1_error

    decorator = tier_1_error(reason="first")

    @decorator
    class _Twice(Exception):
        pass

    decorator(_Twice)
    assert TIER_1_ERRORS.count(_Twice) == 1


def test_non_exception_class_raises_typeerror() -> None:
    from elspeth.contracts.tier_registry import tier_1_error

    with pytest.raises(TypeError, match="BaseException"):

        @tier_1_error(reason="test")
        class _NotException:
            pass


def test_module_outside_allowlist_raises() -> None:
    """Decoration from a plugin module must fail."""
    from elspeth.contracts.tier_registry import _register_with_module_prefix

    # Simulate a plugin-module caller by passing an explicit module name.
    with pytest.raises(PermissionError, match="plugin"):
        _register_with_module_prefix(
            cls=type("X", (Exception,), {}),
            reason="plugin attempt",
            caller_module="elspeth.plugins.transforms.custom",
        )


def test_registration_after_freeze_raises() -> None:
    from elspeth.contracts.tier_registry import (
        FrameworkBugError,
        freeze_tier_registry,
        tier_1_error,
    )

    freeze_tier_registry()
    with pytest.raises(FrameworkBugError, match="frozen"):

        @tier_1_error(reason="too late")
        class _Late(Exception):
            pass
