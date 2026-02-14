"""Regression test for Phase 0 fix #3: MCP eager import.

Bug: `from elspeth.mcp import create_server` eagerly imported
`elspeth.mcp.server` at import time, pulling in heavy dependencies
(fastmcp, etc.) even when the caller just wanted to check availability.

Fix: Lazy imports behind wrapper functions in `elspeth/mcp/__init__.py`.
The real module is only imported when the function is actually called.
"""

from __future__ import annotations

import sys


def test_mcp_init_does_not_eagerly_import_server() -> None:
    """Importing elspeth.mcp should NOT import elspeth.mcp.server.

    The fix uses wrapper functions that defer the import of
    elspeth.mcp.server until the function is called, not at import time.
    """
    # Remove elspeth.mcp and elspeth.mcp.server from sys.modules
    # so we can test a fresh import
    modules_to_remove = [key for key in sys.modules if key == "elspeth.mcp" or key.startswith("elspeth.mcp.")]
    saved = {key: sys.modules.pop(key) for key in modules_to_remove}

    try:
        # Import the package — this should NOT trigger server import
        import elspeth.mcp

        # The wrapper functions should be accessible
        assert hasattr(elspeth.mcp, "create_server")
        assert hasattr(elspeth.mcp, "main")

        # But elspeth.mcp.server should NOT be in sys.modules yet
        assert "elspeth.mcp.server" not in sys.modules, (
            "elspeth.mcp.server was eagerly imported at import time. The __init__.py should use lazy imports via wrapper functions."
        )
    finally:
        # Restore original modules
        for key in list(sys.modules):
            if key == "elspeth.mcp" or key.startswith("elspeth.mcp."):
                sys.modules.pop(key, None)
        sys.modules.update(saved)
