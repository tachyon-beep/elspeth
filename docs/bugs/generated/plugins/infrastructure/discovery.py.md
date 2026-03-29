## Summary

Built-in plugin discovery aborts on legitimately absent optional extras because `discovery.py` eagerly imports every optional plugin module during startup instead of skipping plugins whose extra pack is not installed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py`
- Line(s): 75-82, 103-117, 182-185, 204-212
- Function/Method: `discover_plugins_in_directory`, `_discover_in_file`, `discover_all_plugins`

## Evidence

`discover_plugins_in_directory()` scans every `*.py` file in each configured plugin directory and immediately imports it:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py:75-82
for py_file in sorted(directory.glob("*.py")):
    if py_file.name in EXCLUDED_FILES:
        continue
    plugins = _discover_in_file(py_file, base_class)
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py:103-117
spec = importlib.util.spec_from_file_location(module_name, py_file)
module = importlib.util.module_from_spec(spec)
sys.modules[module.__name__] = module
spec.loader.exec_module(module)
```

`discover_all_plugins()` does this unconditionally for built-in sources/transforms/sinks, including optional-pack plugins:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py:182-185
PLUGIN_SCAN_CONFIG = {
    "sources": ["sources"],
    "transforms": ["transforms", "transforms/azure", "transforms/llm", "transforms/rag"],
    "sinks": ["sinks"],
}
```

The package metadata says these dependencies are optional, not baseline requirements:

- `/home/john/elspeth/pyproject.toml:20-68` puts core deps in `dependencies`
- `/home/john/elspeth/pyproject.toml:112-116` puts `html2text` and `beautifulsoup4` behind the `web` extra
- `/home/john/elspeth/pyproject.toml:118-121` puts `chromadb` behind the `rag` extra

But some discovered plugin modules import those optional packages at module import time:

```python
# /home/john/elspeth/src/elspeth/plugins/transforms/web_scrape_extraction.py:7-8
import html2text
from bs4 import BeautifulSoup
```

```python
# /home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py:14-16
import chromadb
import chromadb.api
import chromadb.errors
```

This failure is reachable through normal startup paths:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py:54-73` calls `discover_all_plugins()` from `register_builtin_plugins()`
- `/home/john/elspeth/src/elspeth/cli.py:1223-1255` uses the shared plugin manager for `elspeth plugins list`

I verified the breakage by simulating a base install that lacks `html2text`. With only an import hook that blocks `html2text`, `discover_all_plugins()` crashes inside `discovery.py`:

```text
Traceback (most recent call last):
  File "...", line 16, in <module>
  File "/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py", line 212, in discover_all_plugins
    discovered = discover_plugins_in_directory(directory, base_class)
  File "/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py", line 82, in discover_plugins_in_directory
    plugins = _discover_in_file(py_file, base_class)
  File "/home/john/elspeth/src/elspeth/plugins/infrastructure/discovery.py", line 117, in _discover_in_file
    spec.loader.exec_module(module)
ImportError: blocked html2text for simulation
```

Tracing the directory scan showed the failure occurs while scanning `web_scrape.py`, before discovery can finish:

```text
SCANNING batch_replicate.py
...
SCANNING web_scrape.py
FAILED_ON ImportError blocked html2text for simulation
```

There is extensive happy-path discovery coverage in `/home/john/elspeth/tests/unit/plugins/test_discovery.py` and `/home/john/elspeth/tests/unit/plugins/test_hookimpl_registration.py`, but no test for a valid base install without optional extras.

## Root Cause Hypothesis

`discovery.py` assumes every built-in plugin dependency is always installed, but the packaging model explicitly splits plugins across optional extras. Because discovery imports plugin modules eagerly and treats any import failure as a fatal bug, optional plugin packs become mandatory for all users. The true design mismatch is in the discovery layer: it has no notion of “optional plugin module with missing extra” versus “broken core plugin import”.

## Suggested Fix

Teach `discovery.py` to distinguish optional-extra absence from genuine internal import bugs, and skip only the former.

A safe pattern would be:

- Maintain an explicit map of optional plugin modules/directories to required extras or top-level packages.
- In `_discover_in_file()`, catch `ModuleNotFoundError`.
- Re-raise if `e.name` is an `elspeth.*` module or otherwise not an allowed optional external package.
- If the missing package is an allowed optional dependency for that plugin module, skip discovery of that module and continue.
- Preserve crash-on-bug behavior for syntax errors, internal import mistakes, and unexpected exceptions.

That keeps baseline installs usable while still failing loudly on real code defects.

## Impact

A valid installation of core `elspeth` can become unusable at startup if unrelated optional extras are absent. That affects:

- `PluginManager.register_builtin_plugins()`
- `elspeth plugins list`
- shared plugin-manager initialization used by CLI/web surfaces
- any test or runtime path that eagerly registers built-in plugins

Operationally, users who do not install `web`, `rag`, or other optional packs can be blocked from discovering and using even core plugins like `csv`, `json`, `passthrough`, and `database`.
