# API Reference

Complete API documentation for Elspeth's core modules, plugins, and interfaces.

!!! info "Auto-Generated Documentation"
    API documentation is automatically generated from **docstrings** in the source code using [mkdocstrings](https://mkdocstrings.github.io/). All examples shown are extracted from the actual codebase.

---

## Overview

Elspeth's API is organized into functional modules:

```
Core                    → BasePlugin, ClassifiedDataFrame, SecurityLevel
Registries              → Plugin registration and factory patterns
Plugins                 → Datasources, Transforms (LLMs), Sinks
Pipeline                → Artifact pipeline, chaining, execution
Security                → Security validation, signing, PII detection
```

---

## Quick Navigation

### Core Abstractions

**[BasePlugin](core/base-plugin.md)**
Abstract base class for all plugins with security enforcement

**[ClassifiedDataFrame](core/classified-dataframe.md)**
DataFrame wrapper with immutable classification metadata

**[SecurityLevel](core/security-level.md)**
Enumeration of security clearance levels (UNOFFICIAL → SECRET)

### Plugin Development

**[Plugin Registry](registries/base.md)**
Factory pattern for plugin registration and instantiation

**[Datasources](plugins/datasources.md)**
Data loading plugins (CSV, Azure Blob, etc.)

**[Transforms](plugins/transforms.md)**
LLM clients and middleware

**[Sinks](plugins/sinks.md)**
Output plugins (CSV, Excel, signed artifacts, etc.)

### Pipeline Execution

**[Artifact Pipeline](pipeline/artifact-pipeline.md)**
Dependency-ordered sink execution with security enforcement

---

## Key Concepts

### Plugin Inheritance

All plugins **must** inherit from `BasePlugin`:

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel

class MyDatasource(BasePlugin):
    def __init__(self, *, security_level: SecurityLevel, path: str):
        super().__init__(security_level=security_level)
        self.path = path
```

See [BasePlugin](core/base-plugin.md) for complete documentation.

### Security Enforcement

All data is wrapped in `ClassifiedDataFrame` with immutable classification:

```python
from elspeth.core.security.classified_data import ClassifiedDataFrame

# Created by datasource (trusted source)
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)

# Uplifted by plugin (automatic max operation)
result = frame.with_uplifted_classification(plugin.get_security_level())
```

See [ClassifiedDataFrame](core/classified-dataframe.md) for complete documentation.

### Plugin Registration

Plugins are registered via factory pattern:

```python
from elspeth.core.registries.base import BasePluginRegistry

registry = BasePluginRegistry[MyPluginType]()

registry.register(
    "my_plugin",
    factory=my_plugin_factory,
    schema=my_plugin_schema
)

plugin = registry.create("my_plugin", options, context)
```

See [Plugin Registry](registries/base.md) for complete documentation.

---

## Architecture Decisions

API design is guided by ADRs (Architecture Decision Records):

| ADR | Topic | Impact on API |
|-----|-------|---------------|
| **ADR-001** | Design Philosophy | Security-first priority hierarchy |
| **ADR-002** | Multi-Level Security | ClassifiedDataFrame immutability, validation |
| **ADR-004** | Mandatory BasePlugin Inheritance | All plugins inherit BasePlugin (nominal typing) |
| **ADR-005** | Frozen Plugin Protection | `allow_downgrade` parameter |

See [Architecture](../architecture/overview.md) for complete ADR catalog.

---

## Conventions

### Docstring Style

All modules use **Google-style docstrings**:

```python
def process_data(data: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Process dataframe with threshold filtering.

    Filters rows where score column is above the threshold and
    applies standardization to numeric columns.

    Args:
        data: Input dataframe with 'score' column
        threshold: Minimum score value (0.0 to 1.0)

    Returns:
        Filtered and standardized dataframe

    Raises:
        ValueError: If threshold is outside [0.0, 1.0] range
        KeyError: If 'score' column missing

    Example:
        >>> df = pd.DataFrame({'score': [0.3, 0.7, 0.9]})
        >>> result = process_data(df, threshold=0.5)
        >>> len(result)
        2
    """
```

### Type Annotations

All public APIs use type annotations:

```python
from typing import Optional
from elspeth.core.base.types import SecurityLevel

def validate_level(
    level: SecurityLevel,
    *,
    allow_unofficial: bool = False
) -> Optional[str]:
    """Validate security level meets policy requirements."""
```

### Error Handling

Security-critical errors raise specific exceptions:

```python
from elspeth.core.validation.base import (
    SecurityValidationError,  # Security policy violations
    ConfigurationError,       # Invalid configuration
)
```

See individual module documentation for exception hierarchies.

---

## Usage Examples

### Creating a Custom Datasource

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import ClassifiedDataFrame
import pandas as pd

class CustomDatasource(BasePlugin):
    """Load data from custom source."""

    def __init__(self, *, security_level: SecurityLevel, source_path: str):
        super().__init__(security_level=security_level)
        self.source_path = source_path

    def load_data(self) -> ClassifiedDataFrame:
        """Load data from source.

        Returns:
            ClassifiedDataFrame with source data

        Raises:
            FileNotFoundError: If source_path doesn't exist
        """
        data = pd.read_csv(self.source_path)
        return ClassifiedDataFrame.create_from_datasource(
            data, self.get_security_level()
        )
```

### Creating a Custom Sink

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.security.classified_data import ClassifiedDataFrame

class CustomSink(BasePlugin):
    """Write data to custom destination."""

    def __init__(self, *, security_level: SecurityLevel, output_path: str):
        super().__init__(security_level=security_level)
        self.output_path = output_path

    def write(self, frame: ClassifiedDataFrame, metadata: dict) -> None:
        """Write classified dataframe to destination.

        Args:
            frame: Data to write
            metadata: Experiment metadata

        Raises:
            PermissionError: If insufficient write permissions
        """
        # Validate security level
        self.validate_can_operate_at_level(frame.classification)

        # Write data
        frame.data.to_csv(self.output_path, index=False)
```

---

## Further Reading

- **[Plugin Catalogue](../plugins/overview.md)** - User-facing plugin documentation
- **[Security Model](../user-guide/security-model.md)** - Understanding Bell-LaPadula MLS
- **[Configuration](../user-guide/configuration.md)** - YAML configuration reference
- **[Architecture](../architecture/overview.md)** - System design and ADRs

---

!!! tip "Contributing"
    When adding new APIs, ensure:

    - ✅ Google-style docstrings with examples
    - ✅ Type annotations on all public methods
    - ✅ Security considerations documented
    - ✅ ADR cross-references where applicable
    - ✅ Unit tests with ≥80% coverage
