# Code Patterns & Technical Reference

**Quick reference for common patterns and technical details**

---

## Current Registry Structure (18 files to consolidate)

### Main Registry (`src/elspeth/core/registry.py`)

- Singleton pattern: `registry = PluginRegistry()`
- Has: `_datasources`, `_llms`, `_sinks` dicts
- Methods: `create_datasource()`, `create_llm()`, `create_sink()`

### Split Registries

1. `src/elspeth/core/datasource_registry.py` - Datasource registry
2. `src/elspeth/core/llm_registry.py` - LLM registry
3. `src/elspeth/core/sink_registry.py` - Sink registry
4. `src/elspeth/core/controls/registry.py` - Controls registry
5. `src/elspeth/core/controls/cost_tracker_registry.py` - Cost tracker registry
6. `src/elspeth/core/controls/rate_limiter_registry.py` - Rate limiter registry
7. `src/elspeth/core/experiments/plugin_registry.py` - Main experiment plugin registry
8. `src/elspeth/core/experiments/row_plugin_registry.py` - Row plugin registry
9. `src/elspeth/core/experiments/aggregation_plugin_registry.py` - Aggregation registry
10. `src/elspeth/core/experiments/validation_plugin_registry.py` - Validation registry
11. `src/elspeth/core/experiments/baseline_plugin_registry.py` - Baseline registry
12. `src/elspeth/core/experiments/early_stop_plugin_registry.py` - Early stop registry
13. `src/elspeth/plugins/llms/middleware/registry.py` (if exists)
14. `src/elspeth/plugins/utilities/registry.py`
15-18. Others in experiment/controls domains

---

## Key Code Patterns

### Security Level Enforcement (FIXED)

**BAD (Old pattern with silent default)**:

```python
def create_plugin(options: dict[str, Any], context: PluginContext) -> Plugin:
    level = options.get("security_level", "OFFICIAL")  # ❌ Silent default
    return Plugin(security_level=level)
```

**GOOD (Current pattern)**:

```python
def create_plugin(options: dict[str, Any], context: PluginContext) -> Plugin:
    level = options.get("security_level")
    if not level:
        raise ConfigurationError("security_level is required")
    return Plugin(security_level=level)
```

### Plugin Creation with Context

**Pattern in `plugin_helpers.py`**:

```python
from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

def create_row_plugin(
    definition: dict[str, Any],
    parent_context: PluginContext,
) -> RowExperimentPlugin:
    result = create_plugin_with_inheritance(
        plugin_type="row_plugin",
        definition=definition,
        parent_context=parent_context,
        registry=_row_plugins,
        allow_none=False,  # Never returns None when False
    )
    # When allow_none=False, result is never None
    assert result is not None, "Unreachable: allow_none=False prevents None return"
    return result
```

### Type Narrowing for Mypy

**Pattern for validation functions**:

```python
def validate_row_plugin_definition(definition: dict[str, Any]) -> None:
    name = definition.get("name")
    # Type narrow: ensure name is str before passing to validate()
    if not name or not isinstance(name, str):
        raise ConfigurationError("Row plugin definition missing 'name' field or name is not a string")
    # Now safe: name is guaranteed to be str
    validate(definition, _row_plugin_schemas[name])
```

### Configuration Merge Pattern (ConfigMerger)

**Usage in `suite_runner.py`**:

```python
from elspeth.core.experiments.config_merger import ConfigMerger

merger = ConfigMerger(defaults, pack, config)

# Merge lists (extends)
middleware_defs = merger.merge_list("llm_middleware_defs", "llm_middlewares")

# Merge dicts (updates)
prompt_defaults = merger.merge_dict("prompt_defaults")

# Merge scalars (last wins)
prompt_system = merger.merge_scalar("prompt_system", default="")

# Merge plugin definitions (special pattern)
row_plugin_defs = merger.merge_plugin_definitions("row_plugin_defs", "row_plugins")
```

### Schema Validation Pattern

**GOOD (Required fields explicit)**:

```python
AZURE_OPENAI_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "temperature": {"type": "number"},
        "security_level": {"type": "string", "enum": SECURITY_LEVELS},
    },
    "required": ["model", "temperature", "security_level"],  # ← Explicit
}
```

### Backward Compatibility Shim Pattern

**Example from current code**:

```python
# src/elspeth/core/registry/__init__.py
import importlib.util
from pathlib import Path

# Load old registry.py file (being shadowed by registry/ directory)
_registry_file = Path(__file__).parent.parent / "registry.py"
_spec = importlib.util.spec_from_file_location("elspeth.core._old_registry", _registry_file)

if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load registry module from {_registry_file}")

_old_registry_module = importlib.util.module_from_spec(_spec)
sys.modules["elspeth.core._old_registry"] = _old_registry_module
_spec.loader.exec_module(_old_registry_module)

# Re-export for backward compatibility
registry = _old_registry_module.registry
PluginFactory = _old_registry_module.PluginFactory
PluginRegistry = _old_registry_module.PluginRegistry
```

---

## Registry Creation Patterns

### BasePluginRegistry Usage (Phase 2)

**Current pattern**:

```python
from elspeth.core.registry import BasePluginRegistry
from elspeth.core.interfaces import DataSource

# Create registry
datasource_registry = BasePluginRegistry[DataSource]("datasource")

# Register plugin
datasource_registry.register(
    "csv_local",
    factory=create_csv_local_datasource,
    schema=CSV_LOCAL_SCHEMA,
)

# Create plugin
datasource = datasource_registry.create(
    "csv_local",
    options={"path": "/data/test.csv", "security_level": "internal"},
    parent_context=context,
)
```

### Old Registry Pattern (to be replaced)

```python
from elspeth.core.registry import registry

# Register
registry._datasources["csv_local"] = create_csv_local_datasource

# Create
datasource = registry.create_datasource({
    "plugin": "csv_local",
    "path": "/data/test.csv",
    "security_level": "internal",
})
```

---

## Import Patterns to Map

### Common Registry Imports (need backward compat)

```python
from elspeth.core.registry import registry
from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.llm_registry import llm_client_registry, llm_middleware_registry
from elspeth.core.sink_registry import sink_registry
from elspeth.core.experiments.plugin_registry import (
    create_row_plugin,
    create_aggregation_plugin,
    create_validation_plugin,
)
```

### Plugin Imports (will move)

```python
from elspeth.plugins.datasources.csv_local import create_csv_local_datasource
from elspeth.plugins.llms.azure_openai import create_azure_openai_client
from elspeth.plugins.outputs.csv_file import create_csv_file_sink
from elspeth.plugins.experiments.metrics import ScoreExtractorPlugin
```

---

## Testing Patterns

### Characterization Test Pattern

```python
def test_current_registry_behavior():
    """Document how registry currently works (golden test)."""
    from elspeth.core.registry import registry

    # Document current structure
    assert hasattr(registry, "_datasources")
    assert isinstance(registry._datasources, dict)

    # Document current plugins
    assert "csv_local" in registry._datasources
    assert "csv_blob" in registry._datasources

    # Document current behavior
    factory = registry._datasources["csv_local"]
    assert callable(factory)
```

### Security Enforcement Test Pattern

```python
def test_explicit_security_level_required():
    """All plugins must fail without explicit security_level."""
    from elspeth.core.registry import registry

    with pytest.raises(ConfigurationError, match="security_level"):
        registry.create_datasource({
            "plugin": "csv_local",
            "path": "/tmp/test.csv",
            # Missing: security_level
        })
```

### Performance Regression Test Pattern

```python
def test_registry_lookup_performance():
    """Registry lookups should be <1ms."""
    import time
    from elspeth.core.registry import registry

    start = time.perf_counter()
    for _ in range(1000):
        factory = registry._datasources.get("csv_local")
    end = time.perf_counter()

    avg_time = (end - start) / 1000
    assert avg_time < 0.001, f"Too slow: {avg_time*1000:.2f}ms"
```

---

## Configuration Patterns

### Current Config Structure (to maintain compatibility)

**Datasource config**:

```yaml
datasource:
  plugin: csv_local
  path: /data/customers.csv
  security_level: internal
  encoding: utf-8
  has_header: true
```

**LLM config**:

```yaml
llm:
  plugin: azure_openai
  model: gpt-4
  temperature: 0.7
  security_level: internal
  azure_endpoint: https://...
```

**Experiment config**:

```yaml
experiments:
  - name: baseline
    prompt_pack: baseline_pack
    llm_middleware_defs:
      - name: audit_logger
    row_plugin_defs:
      - name: score_extractor
        field: response
```

---

## File Movement Map (Migration Phase 2)

### Datasources → Sources

```
src/elspeth/plugins/datasources/csv_local.py
  → src/elspeth/plugins/nodes/sources/csv_local.py

src/elspeth/plugins/datasources/csv_blob.py
  → src/elspeth/plugins/nodes/sources/csv_blob.py

src/elspeth/plugins/datasources/blob.py
  → src/elspeth/plugins/nodes/sources/azure_blob.py
```

### Outputs → Sinks

```
src/elspeth/plugins/outputs/*
  → src/elspeth/plugins/nodes/sinks/*
```

### LLMs → Transform Nodes

```
src/elspeth/plugins/llms/azure_openai.py
  → src/elspeth/plugins/nodes/transforms/llm/clients/azure_openai.py

src/elspeth/plugins/llms/middleware.py
  → src/elspeth/plugins/nodes/transforms/llm/middleware/audit_logger.py

src/elspeth/core/controls/rate_limit.py
  → src/elspeth/plugins/nodes/transforms/llm/controls/rate_limiter.py

src/elspeth/core/controls/cost_tracker.py
  → src/elspeth/plugins/nodes/transforms/llm/controls/cost_tracker.py
```

### Experiments → Orchestrator

```
src/elspeth/core/experiments/runner.py
  → src/elspeth/plugins/orchestrators/experiment/runner.py

src/elspeth/plugins/experiments/metrics.py (split into):
  → src/elspeth/plugins/nodes/transforms/numeric/scoring.py (row plugin)
  → src/elspeth/plugins/nodes/aggregators/statistics.py (aggregator)
  → src/elspeth/plugins/orchestrators/experiment/baseline/ (baseline comparison)
```

---

## Useful Commands

### Test & Quality

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=elspeth --cov-report=html --cov-report=term-missing

# Type check
.venv/bin/python -m mypy src/elspeth

# Lint
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format src tests

# Run sample suite
make sample-suite
```

### Search Patterns

```bash
# Find silent defaults
rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/

# Find registry imports
rg "from elspeth\.core\.registry" src/ tests/

# Find plugin references in configs
rg "plugin:\s*" config/ tests/
```

### Performance Profiling

```bash
# Profile CLI
python -m cProfile -o profile.prof -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite

# Time execution
time python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --head 100
```

---

## Key Files Locations

### Core Registry Files (to refactor)

- `src/elspeth/core/registry.py` - Main singleton
- `src/elspeth/core/registry/base.py` - BasePluginRegistry
- `src/elspeth/core/registry/plugin_helpers.py` - create_plugin_with_inheritance
- `src/elspeth/core/registry/context_utils.py` - Context utilities
- `src/elspeth/core/registry/schemas.py` - Common schemas

### Configuration Files

- `src/elspeth/core/experiments/config.py` - ExperimentConfig
- `src/elspeth/core/experiments/config_merger.py` - ConfigMerger
- `src/elspeth/config.py` - Top-level config loading

### Test Files

- `tests/conftest.py` - Shared fixtures
- `tests/test_experiments.py` - Core experiment tests
- `tests/test_suite_runner_integration.py` - Suite integration tests
- `tests/test_registry_*.py` - Registry tests (Phase 2)

---

## Protocol Definitions (to consolidate)

### Current Locations

- `src/elspeth/core/interfaces.py` - Main protocols
- `src/elspeth/core/experiments/plugins.py` - Experiment plugins
- Various files have protocol definitions

### Target Location (Phase 4)

- `src/elspeth/core/protocols.py` - ALL universal protocols
- `src/elspeth/plugins/orchestrators/experiment/protocols.py` - Experiment-specific

---

## Remember

1. **All factory functions must validate security_level** - no silent defaults
2. **All schemas must mark critical fields as required**
3. **Backward compatibility shims are essential** - external code depends on current imports
4. **Each phase must leave system working** - all 545+ tests must pass
5. **Characterization tests capture current behavior** - so we can detect changes
6. **Performance regression tests have thresholds** - <1ms registry, <10ms plugin creation
