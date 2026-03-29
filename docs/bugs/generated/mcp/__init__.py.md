## Summary

`src/elspeth/mcp/__init__.py` lazily imports the optional MCP server, but it still leaks a raw `ModuleNotFoundError` when `.[mcp]` is not installed instead of raising a clear, actionable install error from the public entrypoint.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/mcp/__init__.py`
- Line(s): 17-28
- Function/Method: `create_server`, `main`

## Evidence

`/home/john/elspeth/src/elspeth/mcp/__init__.py:17-28` is the public package surface and console-script target, but it only forwards imports:

```python
def create_server(*args, **kwargs):
    """Create an MCP server instance. Requires the [mcp] extra."""
    from elspeth.mcp.server import create_server as _create_server
    return _create_server(*args, **kwargs)

def main(*args, **kwargs):
    """Run the MCP server. Requires the [mcp] extra."""
    from elspeth.mcp.server import main as _main
    return _main(*args, **kwargs)
```

`/home/john/elspeth/src/elspeth/mcp/server.py:29-31` immediately imports the optional third-party package:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult as CallToolResult
```

The package exposes `main` unconditionally as a CLI entrypoint in `/home/john/elspeth/pyproject.toml:206-209`:

```toml
[project.scripts]
elspeth = "elspeth.cli:app"
elspeth-mcp = "elspeth.mcp:main"
```

The user-facing docs explicitly say MCP support must be installed via `/home/john/elspeth/docs/guides/landscape-mcp-analysis.md:7-13`:

```bash
# Install with MCP support
uv pip install -e ".[mcp]"
...
elspeth-mcp
```

I verified the current runtime behavior by forcing `mcp` imports to fail before calling the wrapper. The public API surfaces the deep import failure directly:

```text
ModuleNotFoundError
No module named 'mcp'
mcp.server
```

So the code currently does this:
- imports lazily, which satisfies `/home/john/elspeth/tests/unit/mcp/test_mcp_init.py:16-38`
- but on actual invocation without the extra, it raises a bare dependency error from inside `elspeth.mcp.server`

What it should do:
- catch missing `mcp`/`mcp.*` in the wrapper
- raise a clear error telling the caller to install `uv pip install -e ".[mcp]"`

## Root Cause Hypothesis

The file was fixed only halfway: eager import was removed, but the wrapper did not translate missing optional-dependency failures into a package-level error message. Because `elspeth.mcp:main` is the installed public entrypoint, this leaves the CLI and library surface with an opaque deep import failure instead of the contract implied by the docstrings and install guide.

## Suggested Fix

Wrap the lazy imports in `try/except ModuleNotFoundError`, detect `mcp` / `mcp.*`, and re-raise with an actionable install message while preserving unrelated import errors.

Example shape:

```python
def create_server(database_url: str, *, passphrase: str | None = None):
    try:
        from elspeth.mcp.server import create_server as _create_server
    except ModuleNotFoundError as exc:
        if exc.name == "mcp" or (exc.name and exc.name.startswith("mcp.")):
            raise ModuleNotFoundError(
                'MCP support is not installed. Install with: uv pip install -e ".[mcp]"'
            ) from exc
        raise
    return _create_server(database_url, passphrase=passphrase)

def main() -> None:
    try:
        from elspeth.mcp.server import main as _main
    except ModuleNotFoundError as exc:
        if exc.name == "mcp" or (exc.name and exc.name.startswith("mcp.")):
            raise ModuleNotFoundError(
                'MCP support is not installed. Install with: uv pip install -e ".[mcp]"'
            ) from exc
        raise
    _main()
```

A regression test should cover calling the wrapper when `mcp` is unavailable, not just importing `elspeth.mcp`.

## Impact

Users who install ELSPETH without `.[mcp]` can still receive the `elspeth-mcp` entrypoint, but invoking it fails with a raw traceback from a nested import. That is an integration/contract failure at the public API boundary: the package advertises optional MCP support, but the boundary does not explain how to satisfy it. This does not corrupt audit data, but it does make the MCP tooling harder to diagnose and breaks the expected optional-dependency UX.
