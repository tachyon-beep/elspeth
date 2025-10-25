# Sinks API

API documentation for sink plugins that write experiment outputs.

!!! info "User Guide Available"
    For configuration examples and sink chaining, see **[Plugin Catalogue: Saving Results](../../plugins/overview.md#saving-results-sinks)**.

---

## Overview

Sink plugins write `ClassifiedDataFrame` data to various destinations with security enforcement.

**Common Interface**:
```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.security.classified_data import ClassifiedDataFrame

class SinkPlugin(BasePlugin):
    def write(self, frame: ClassifiedDataFrame, metadata: dict) -> None:
        """Write classified data to destination.

        Args:
            frame: Data to write with classification
            metadata: Experiment metadata

        Raises:
            SecurityValidationError: If insufficient clearance
        """
        # Validate security level
        self.validate_can_operate_at_level(frame.classification)

        # Write data
        pass
```

---

## Built-In Sinks

### CSV Sink

Write data to CSV files with formula sanitization.

::: elspeth.plugins.nodes.sinks.csv_file.CSVSink
    options:
      members:
        - __init__
        - write
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
sinks:
  - type: csv
    path: results/output.csv
    security_level: OFFICIAL
    sanitize_formulas: true
    overwrite: true
```

---

### Excel Workbook

Write data to Excel workbooks with multiple sheets.

::: elspeth.plugins.nodes.sinks.excel.ExcelWorkbookSink
    options:
      members:
        - __init__
        - write
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
sinks:
  - type: excel_workbook
    base_path: results/report
    security_level: OFFICIAL
    timestamped: true
    include_manifest: true
    sanitize_formulas: true
```

---

### Signed Artifact

Generate cryptographically signed bundles.

::: elspeth.plugins.nodes.sinks.signed.SignedArtifactSink
    options:
      members:
        - __init__
        - write
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
sinks:
  - type: signed_artifact
    base_path: artifacts
    bundle_name: experiment_results
    security_level: PROTECTED
    algorithm: HMAC-SHA256
    key_env: SIGNING_KEY
```

**Supported Algorithms**:
- `HMAC-SHA256` - HMAC with SHA-256
- `HMAC-SHA512` - HMAC with SHA-512
- `RSA-PSS-SHA256` - RSA-PSS with SHA-256
- `ECDSA-P256-SHA256` - ECDSA P-256 with SHA-256

---

### Azure Blob

Upload results to Azure Blob Storage.

::: elspeth.plugins.nodes.sinks.blob.AzureBlobSink
    options:
      members:
        - __init__
        - write
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
sinks:
  - type: azure_blob
    config_path: config/blob_profiles.yaml
    profile: production
    path_template: "{experiment_name}/{timestamp}.csv"
    security_level: PROTECTED
```

---

## Common Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `security_level` | SecurityLevel | ✅ Yes | Sink's security clearance |
| `path` | str | ✅ Yes* | Output file path |
| `base_path` | str | ✅ Yes* | Output directory |
| `sanitize_formulas` | bool | ❌ No | Strip Excel formulas (default: `true`) |
| `overwrite` | bool | ❌ No | Overwrite existing files (default: `false`) |
| `on_error` | str | ❌ No | Error handling: `abort` \| `skip` \| `log` |

\* Either `path` or `base_path` required depending on sink type

---

## Formula Sanitization

CSV and Excel sinks sanitize formulas by default for security:

```python
# Input cell value
value = "=SUM(A1:A10)"

# Sanitized output
sanitized = "'=SUM(A1:A10)"  # Prefixed with apostrophe
```

**Configuration**:
```yaml
sinks:
  - type: csv
    path: output.csv
    sanitize_formulas: true  # ← Recommended (default)
    sanitize_guard: "'"      # Prefix character
```

**Disable** (not recommended):
```yaml
sinks:
  - type: csv
    path: output.csv
    sanitize_formulas: false  # ⚠️ Allows formula injection
```

---

## Security Validation

Sinks validate they can operate at the data's classification level:

```python
# Sink with OFFICIAL clearance
sink = CSVSink(
    path="output.csv",
    security_level=SecurityLevel.OFFICIAL
)

# Can write OFFICIAL data (exact match)
frame_official = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)
sink.write(frame_official, metadata={})  # ✅ OK

# Can write UNOFFICIAL data (higher clearance)
frame_public = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.UNOFFICIAL
)
sink.write(frame_public, metadata={})  # ✅ OK

# Cannot write SECRET data (insufficient clearance)
frame_secret = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.SECRET
)
sink.write(frame_secret, metadata={})  # ❌ SecurityValidationError
```

---

## Sink Chaining

Sinks can depend on other sinks via the artifact pipeline:

```yaml
sinks:
  # Primary CSV output
  - type: csv
    name: raw_results
    path: results.csv

  # Signed bundle depends on CSV
  - type: signed_artifact
    base_path: artifacts
    consumes: [raw_results]  # Wait for CSV to complete
```

See [Artifact Pipeline](../pipeline/artifact-pipeline.md) for details.

---

## Custom Sink Example

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import ClassifiedDataFrame
import json

class JSONLinesSink(BasePlugin):
    """Write data to JSON Lines format."""

    def __init__(self, *, security_level: SecurityLevel, output_path: str):
        super().__init__(security_level=security_level)
        self.output_path = output_path

    def write(self, frame: ClassifiedDataFrame, metadata: dict) -> None:
        """Write data as JSON Lines."""
        # Validate security level
        self.validate_can_operate_at_level(frame.classification)

        # Write JSON Lines
        with open(self.output_path, 'w') as f:
            for _, row in frame.data.iterrows():
                f.write(json.dumps(row.to_dict()) + '\n')
```

---

## Related Documentation

- **[Plugin Catalogue](../../plugins/overview.md#saving-results-sinks)** - Configuration examples
- **[Artifact Pipeline](../pipeline/artifact-pipeline.md)** - Sink chaining and dependencies
- **[BasePlugin](../core/base-plugin.md)** - Plugin base class
- **[ClassifiedDataFrame](../core/classified-dataframe.md)** - Input data type
