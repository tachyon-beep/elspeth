"""For every registered DeclarationContract, runtime_check(negative_example())
MUST raise the contract's violation. Closes reviewer B6/F-7 (dormant
runtime_check disables VAL silently)."""

from __future__ import annotations

import pytest

# Ensure pass_through.py has registered PassThroughDeclarationContract before
# pytest evaluates the parametrize list at collection time.
import elspeth.engine.executors.pass_through  # noqa: F401
from elspeth.contracts.declaration_contracts import (
    DeclarationContractViolation,
    registered_declaration_contracts,
)


@pytest.mark.parametrize(
    "contract",
    list(registered_declaration_contracts()),
    ids=lambda c: c.name,
)
def test_negative_example_fires_violation(contract) -> None:
    """Dormant-runtime_check invariant (ADR-010 §Decision 3 / reviewer B6/F-7).

    If a registered contract's runtime_check silently returns None on its own
    negative_example, the framework's runtime VAL is disabled for that contract
    without any loud failure. This test is the last line of defence.
    """
    inputs, outputs = type(contract).negative_example()
    with pytest.raises((DeclarationContractViolation, RuntimeError)) as exc_info:
        contract.runtime_check(inputs, outputs)
    assert exc_info.value is not None, (
        f"Contract {contract.name!r}'s runtime_check did not raise on its own negative_example — VAL is dormant for this contract."
    )
