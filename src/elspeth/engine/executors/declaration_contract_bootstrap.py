"""Authoritative import surface for production declaration-contract registration.

Every production module that calls ``register_declaration_contract(...)`` at
module scope MUST be imported here. ``tests/unit/engine/
test_declaration_contract_bootstrap_drift.py`` AST-scans
``src/elspeth/engine/executors/`` and fails CI if a registered contract module
lands without its matching bootstrap import.

CLOSED SET: update this file in the same commit as any
``EXPECTED_CONTRACT_SITES`` change.
"""

import elspeth.engine.executors.declared_output_fields
import elspeth.engine.executors.pass_through  # noqa: F401
