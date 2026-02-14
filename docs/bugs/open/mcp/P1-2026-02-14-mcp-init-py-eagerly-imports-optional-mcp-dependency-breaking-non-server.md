## Summary

`src/elspeth/mcp/__init__.py` eagerly imports `elspeth.mcp.server`, which hard-couples the whole `elspeth.mcp` package to the optional `mcp` dependency and breaks imports of otherwise non-MCP-SDK modules (for example `elspeth.mcp.analyzer`) when `.[mcp]` is not installed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/mcp/__init__.py`
- Line(s): 17
- Function/Method: module import surface (`__init__.py` top-level)

## Evidence

`src/elspeth/mcp/__init__.py:17` does eager import at module load:

```python
from elspeth.mcp.server import create_server, main
```

`src/elspeth/mcp/server.py:28-30` imports the optional SDK immediately:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
```

But `mcp` is optional in packaging (`pyproject.toml:116-119`), not a base dependency.

Also, many MCP analysis modules do **not** require the external `mcp` SDK (`src/elspeth/mcp/analyzer.py:13-16`, and `rg` only finds `from mcp...` in `src/elspeth/mcp/server.py`).

Repro (import-block test) shows importing analyzer fails via `__init__.py` eager import chain:

```text
File ".../src/elspeth/mcp/__init__.py", line 17, in <module>
  from elspeth.mcp.server import create_server, main
File ".../src/elspeth/mcp/server.py", line 28, in <module>
  from mcp.server import Server
ModuleNotFoundError: No module named 'mcp' (blocked for test)
```

What it does now: importing `elspeth.mcp.*` requires `mcp` SDK at package-import time.
What it should do: only require `mcp` SDK when actually invoking MCP server entrypoints.

## Root Cause Hypothesis

`__init__.py` is acting as a re-export shim with eager imports. Because Python loads package `__init__.py` before submodules, this turns an optional runtime dependency (`mcp`) into an effective package-wide import-time dependency.

## Suggested Fix

Make `src/elspeth/mcp/__init__.py` lazy for `create_server`/`main` instead of importing `server` at module import time.

Example shape:

```python
def create_server(database_url: str, *, passphrase: str | None = None):
    try:
        from elspeth.mcp.server import create_server as _create_server
    except ModuleNotFoundError as e:
        if e.name == "mcp" or (e.name and e.name.startswith("mcp.")):
            raise ModuleNotFoundError(
                "MCP support is not installed. Install with: uv pip install -e '.[mcp]'"
            ) from e
        raise
    return _create_server(database_url, passphrase=passphrase)

def main() -> None:
    try:
        from elspeth.mcp.server import main as _main
    except ModuleNotFoundError as e:
        if e.name == "mcp" or (e.name and e.name.startswith("mcp.")):
            raise ModuleNotFoundError(
                "MCP support is not installed. Install with: uv pip install -e '.[mcp]'"
            ) from e
        raise
    _main()
```

Keep `__all__ = ["create_server", "main"]`.

## Impact

- `elspeth.mcp` package import behavior violates optional-dependency expectations.
- Users without `.[mcp]` get hard import failure even when using non-server modules under `elspeth.mcp`.
- Failure mode is abrupt `ModuleNotFoundError` from deep import path, not a clear install instruction.
- This is an integration/contract issue (package surface vs optional dependency model), not an audit-trail data integrity issue.
