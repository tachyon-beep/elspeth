# Datasources API

API documentation for datasource plugins that load data into experiments.

!!! info "User Guide Available"
    For configuration examples and usage patterns, see **[Plugin Catalogue: Loading Data](../../plugins/overview.md#loading-data-datasources)**.

---

## Overview

Datasource plugins implement the `load_data()` interface and return `ClassifiedDataFrame` instances.

**Common Interface**:
```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.security.classified_data import ClassifiedDataFrame

class DatasourcePlugin(BasePlugin):
    def load_data(self) -> ClassifiedDataFrame:
        """Load data and return classified frame."""
        pass
```

---

## Built-In Datasources

### CSV Local

Load CSV files from local filesystem.

::: elspeth.plugins.nodes.sources.csv_local.CSVLocalDatasource
    options:
      members:
        - __init__
        - load_data
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
datasource:
  type: csv_local
  path: data/input.csv
  security_level: OFFICIAL
  encoding: utf-8
  dtype:
    column1: str
    column2: int
```

---

### CSV Blob

Load CSV files from Azure Blob Storage (direct URI).

::: elspeth.plugins.nodes.sources.csv_blob.CSVBlobDatasource
    options:
      members:
        - __init__
        - load_data
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
datasource:
  type: csv_blob
  path: https://storageaccount.blob.core.windows.net/container/data.csv
  security_level: OFFICIAL
```

---

### Azure Blob

Load CSV files from Azure Blob with profile-based authentication.

::: elspeth.plugins.nodes.sources.blob.AzureBlobDatasource
    options:
      members:
        - __init__
        - load_data
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
datasource:
  type: azure_blob
  config_path: config/blob_profiles.yaml
  profile: production
  security_level: PROTECTED
```

---

## Common Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `security_level` | SecurityLevel | ✅ Yes | Plugin's security clearance |
| `path` | str | ✅ Yes | File path or blob URI |
| `encoding` | str | ❌ No | File encoding (default: `utf-8`) |
| `dtype` | dict | ❌ No | Column type hints for Pandas |
| `on_error` | str | ❌ No | Error handling: `abort` \| `skip` \| `log` |

---

## Error Handling

### on_error Policy

```yaml
datasource:
  type: csv_local
  path: data/input.csv
  on_error: abort  # abort | skip | log
```

- **abort** (default): Raise exception immediately
- **skip**: Log error and return empty DataFrame
- **log**: Log error and continue

---

## Custom Datasource Example

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import ClassifiedDataFrame
import pandas as pd

class PostgreSQLDatasource(BasePlugin):
    """Load data from PostgreSQL database."""

    def __init__(self, *, security_level: SecurityLevel, connection_string: str, query: str):
        super().__init__(security_level=security_level)
        self.connection_string = connection_string
        self.query = query

    def load_data(self) -> ClassifiedDataFrame:
        """Load data from database."""
        import psycopg2

        with psycopg2.connect(self.connection_string) as conn:
            df = pd.read_sql(self.query, conn)

        return ClassifiedDataFrame.create_from_datasource(
            df, self.get_security_level()
        )
```

---

## Related Documentation

- **[Plugin Catalogue](../../plugins/overview.md#loading-data-datasources)** - Configuration examples
- **[ClassifiedDataFrame](../core/classified-dataframe.md)** - Return type documentation
- **[BasePlugin](../core/base-plugin.md)** - Plugin base class
