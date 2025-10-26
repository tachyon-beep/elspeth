# Plugin Registry

Factory pattern for plugin registration and instantiation with schema validation.

---

## Overview

Elspeth uses a **registry pattern** to manage plugin lifecycle:

1. **Register** plugin factories with schemas
2. **Validate** configuration against schemas
3. **Create** plugin instances with context propagation
4. **Enumerate** available plugins

All registries inherit from `BasePluginRegistry[T]` for consistency.

---

## Class Documentation

::: elspeth.core.registries.base.BasePluginRegistry
    options:
      members:
        - __init__
        - register
        - create
        - list_plugins
        - get_schema
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

::: elspeth.core.registries.base.BasePluginFactory
    options:
      members:
        - create
        - validate
        - instantiate
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

---

## Usage Examples

### Creating a Registry

```python
from elspeth.core.registries.base import BasePluginRegistry, BasePluginFactory
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel

# Define plugin type
class MyPlugin:
    def __init__(self, *, name: str, value: int):
        self.name = name
        self.value = value

# Create registry
registry = BasePluginRegistry[MyPlugin]()

# Define factory function
def create_my_plugin(opts: dict, ctx: PluginContext) -> MyPlugin:
    return MyPlugin(name=opts['name'], value=opts['value'])

# Define schema
my_plugin_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "integer", "minimum": 0}
    },
    "required": ["name", "value"]
}

# Register plugin
registry.register(
    "my_plugin",
    factory=BasePluginFactory(
        create=create_my_plugin,
        schema=my_plugin_schema,
        plugin_type="my_plugin"
    )
)
```

### Creating Plugin Instances

```python
from elspeth.core.base.plugin_context import PluginContext

# Create context
context = PluginContext(
    security_level=SecurityLevel.OFFICIAL,
    run_id="test-run-001",
    plugin_kind="my_plugin"
)

# Create plugin instance
plugin = registry.create(
    "my_plugin",
    options={"name": "example", "value": 42},
    plugin_context=context
)

print(plugin.name)   # "example"
print(plugin.value)  # 42
```

### Schema Validation

```python
from elspeth.core.validation.base import ConfigurationError

# Valid configuration
valid_opts = {"name": "test", "value": 10}
plugin = registry.create("my_plugin", valid_opts, context)  # ✅ OK

# Invalid configuration (missing required field)
invalid_opts = {"name": "test"}  # Missing 'value'
try:
    plugin = registry.create("my_plugin", invalid_opts, context)
except ConfigurationError as e:
    print(f"Validation failed: {e}")  # ❌ Missing required field 'value'

# Invalid configuration (wrong type)
invalid_opts = {"name": "test", "value": "not a number"}
try:
    plugin = registry.create("my_plugin", invalid_opts, context)
except ConfigurationError as e:
    print(f"Validation failed: {e}")  # ❌ 'value' must be integer
```

### Listing Available Plugins

```python
# Get all registered plugin names
plugins = registry.list_plugins()
print(plugins)  # ['my_plugin']

# Get schema for specific plugin
schema = registry.get_schema("my_plugin")
print(schema)  # {...}
```

---

## Built-In Registries

Elspeth provides several specialized registries:

| Registry | Module | Purpose |
|----------|--------|---------|
| **DatasourceRegistry** | `elspeth.core.registries.datasources` | CSV, Azure Blob datasources |
| **TransformRegistry** | `elspeth.core.registries.transforms` | LLM clients and middleware |
| **SinkRegistry** | `elspeth.core.registries.sinks` | CSV, Excel, signed artifacts |
| **ExperimentPluginRegistry** | `elspeth.core.experiments.plugin_registry` | Row, aggregation, validation plugins |

### Example: Using Datasource Registry

```python
from elspeth.core.registries.datasources import datasource_registry
from elspeth.core.base.plugin_context import PluginContext

# List available datasources
datasources = datasource_registry.list_plugins()
print(datasources)  # ['csv_local', 'csv_blob', 'azure_blob']

# Create CSV datasource
context = PluginContext(
    security_level=SecurityLevel.OFFICIAL,
    run_id="exp-001"
)

datasource = datasource_registry.create(
    "csv_local",
    options={"path": "data/input.csv"},
    plugin_context=context
)
```

---

## Advanced: Custom Plugin Registration

### With Security Level Inheritance

```python
from elspeth.core.base.plugin import BasePlugin

class SecurePlugin(BasePlugin):
    """Plugin with security level enforcement."""

    def __init__(self, *, security_level: SecurityLevel, config: dict):
        super().__init__(security_level=security_level)
        self.config = config

def create_secure_plugin(opts: dict, ctx: PluginContext) -> SecurePlugin:
    """Factory with context-aware security level."""
    return SecurePlugin(
        security_level=ctx.security_level,
        config=opts
    )

# Register with security awareness
registry.register(
    "secure_plugin",
    factory=BasePluginFactory(
        create=create_secure_plugin,
        schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "endpoint": {"type": "string"}
            },
            "required": ["endpoint"]
        },
        plugin_type="secure_plugin"
    )
)

# Create with context
plugin = registry.create(
    "secure_plugin",
    options={"endpoint": "https://api.example.com"},
    plugin_context=PluginContext(
        security_level=SecurityLevel.PROTECTED,
        run_id="run-001"
    )
)

print(plugin.get_security_level())  # SecurityLevel.PROTECTED
```

### With Capabilities

```python
# Register plugin with declared capabilities
registry.register(
    "advanced_plugin",
    factory=BasePluginFactory(
        create=create_advanced_plugin,
        schema=advanced_schema,
        plugin_type="advanced",
        capabilities=frozenset(["streaming", "caching", "retry"])
    )
)

# Check capabilities
factory = registry._plugins["advanced_plugin"]
print("streaming" in factory.capabilities)  # True
```

---

## Error Handling

### ConfigurationError

Raised when plugin configuration is invalid:

```python
from elspeth.core.validation.base import ConfigurationError

try:
    plugin = registry.create(
        "my_plugin",
        options={"invalid": "config"},
        plugin_context=context
    )
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    print(f"Context: {e.context}")  # Plugin name and location
```

### Unknown Plugin

Attempting to create unregistered plugin:

```python
try:
    plugin = registry.create(
        "nonexistent_plugin",
        options={},
        plugin_context=context
    )
except KeyError as e:
    print(f"Plugin not found: {e}")
```

---

## Schema Validation Details

### JSON Schema Support

Registries use JSON Schema Draft 7 for validation:

```python
schema = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100
        },
        "age": {
            "type": "integer",
            "minimum": 0,
            "maximum": 120
        },
        "email": {
            "type": "string",
            "format": "email"
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": true
        }
    },
    "required": ["name", "age"],
    "additionalProperties": false
}
```

### Schema Compilation Caching

Schemas are compiled once and cached for performance:

```python
# First call: compile schema
plugin1 = registry.create("my_plugin", opts1, context)  # Compile + validate

# Subsequent calls: use cached validator
plugin2 = registry.create("my_plugin", opts2, context)  # Validate only (fast)
```

---

## Related Documentation

- **[BasePlugin](../core/base-plugin.md)** - Plugin base class
- **[Plugin Catalogue](../../plugins/overview.md)** - User-facing plugin documentation
- **[Configuration](../../user-guide/configuration.md)** - YAML configuration reference

---

## ADR Cross-References

- **ADR-004**: Mandatory BasePlugin Inheritance - Registry enforces BasePlugin subclassing
- **ADR-002**: Multi-Level Security - PluginContext propagates security_level
