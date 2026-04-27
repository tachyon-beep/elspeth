"""Verify L0 purity of the plugin semantics + assistance contract modules.

These modules sit in src/elspeth/contracts/ which is L0 — they may not
import anything from core/ (L1), engine/ (L2), or plugins/web/mcp/tui/
(L3). The CI script enforce_tier_model.py also catches this; this test
gives faster feedback during development.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SRC = _PROJECT_ROOT / "src"

_FORBIDDEN_PREFIXES = (
    "elspeth.core",
    "elspeth.engine",
    "elspeth.plugins",
    "elspeth.web",
    "elspeth.mcp",
    "elspeth.composer_mcp",
    "elspeth.tui",
    "elspeth.cli",
    "elspeth.telemetry",
    "elspeth.testing",
)


def _module_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return imports


@pytest.mark.parametrize(
    "module_path",
    [
        "src/elspeth/contracts/plugin_semantics.py",
        "src/elspeth/contracts/plugin_assistance.py",
    ],
)
def test_module_does_not_import_above_l0(module_path: str):
    path = _PROJECT_ROOT / module_path
    imports = _module_imports(path)
    violations = [imp for imp in imports if any(imp == prefix or imp.startswith(f"{prefix}.") for prefix in _FORBIDDEN_PREFIXES)]
    assert not violations, f"{module_path} imports L1+ modules: {violations}. Contracts must remain L0-pure."
