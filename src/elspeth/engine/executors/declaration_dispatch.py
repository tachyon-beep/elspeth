"""Declaration-contract runtime dispatcher (ADR-010 §Decision 3).

Called from TransformExecutor and processor flush path. Iterates the
registry, skips contracts whose ``applies_to`` returns False, and invokes
each applicable contract's ``runtime_check``.

Violations (`DeclarationContractViolation`) propagate. Unexpected exceptions
from `applies_to` or `runtime_check` ALSO propagate — per CLAUDE.md plugin-
ownership posture, a buggy contract is a framework bug that must crash.
This dispatcher is pure orchestration: no try/except wrapping.
"""

from __future__ import annotations

from elspeth.contracts.declaration_contracts import (
    RuntimeCheckInputs,
    RuntimeCheckOutputs,
    registered_declaration_contracts,
)


def run_runtime_checks(
    *,
    inputs: RuntimeCheckInputs,
    outputs: RuntimeCheckOutputs,
) -> None:
    for contract in registered_declaration_contracts():
        if not contract.applies_to(inputs.plugin):
            continue
        contract.runtime_check(inputs, outputs)
