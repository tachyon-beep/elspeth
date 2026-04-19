"""Declaration-contract runtime dispatcher (ADR-010 §Decision 3).

Called from TransformExecutor and processor flush path. Iterates the
registry, skips contracts whose ``applies_to`` returns False, and invokes
each applicable contract's ``runtime_check``.

Violations (`DeclarationContractViolation`) propagate after the dispatcher
attaches the authoritative ``contract_name`` from the firing contract's
registry entry (issue elspeth-d74fe81529 / ADR-010 C4 — contract-name
spoofing closure). Unexpected exceptions from `applies_to` or
`runtime_check` ALSO propagate unmodified — per CLAUDE.md plugin-ownership
posture, a buggy contract is a framework bug that must crash. This
dispatcher remains pure orchestration: the only catch-and-enrich is the
one narrow case where the authoritative contract identity has to be
stamped onto a violation from outside the raising contract's blast radius.
"""

from __future__ import annotations

from elspeth.contracts.declaration_contracts import (
    DeclarationContractViolation,
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
        try:
            contract.runtime_check(inputs, outputs)
        except DeclarationContractViolation as exc:
            # C4 closure: attach the authoritative contract name from the
            # registry entry. Contracts can no longer supply contract_name
            # at construction (see DeclarationContractViolation docstring),
            # so this is the single attribution point for every violation
            # that flows through the dispatcher.
            exc._attach_contract_name(contract.name)
            raise
