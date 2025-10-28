# Artifact Pipeline

Dependency-ordered sink execution with security enforcement and chaining support.

---

## Overview

The **Artifact Pipeline** executes sinks in dependency order, ensuring:

1. **Dependency Resolution** - Sinks run after their dependencies complete
2. **Security Enforcement** - Each sink validates it can handle data classification
3. **Metadata Chaining** - Sinks can consume outputs from previous sinks
4. **Error Isolation** - Sink failures don't block independent sinks

---

## Class Documentation

::: elspeth.core.pipeline.artifact_pipeline.ArtifactPipeline
    options:
      members:
        - __init__
        - execute
        - _topological_sort
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

---

## Basic Usage

### Simple Pipeline (No Dependencies)

```python
from elspeth.core.pipeline.artifact_pipeline import ArtifactPipeline
from elspeth.core.security.classified_data import ClassifiedDataFrame
from elspeth.core.base.types import SecurityLevel

# Create sinks
csv_sink = CSVSink(path="output.csv", security_level=SecurityLevel.OFFICIAL)
excel_sink = ExcelWorkbookSink(base_path="report", security_level=SecurityLevel.OFFICIAL)

# Create pipeline
pipeline = ArtifactPipeline(
    sinks=[csv_sink, excel_sink],
    operating_level=SecurityLevel.OFFICIAL
)

# Execute (sinks run in parallel)
frame = ClassifiedDataFrame.create_from_datasource(data, SecurityLevel.OFFICIAL)
pipeline.execute(frame, metadata={"experiment_name": "test"})
```

### Pipeline with Dependencies

```python
# Define sink dependencies
sink_configs = [
    {
        "name": "csv_output",
        "type": "csv",
        "path": "results.csv",
        "security_level": "OFFICIAL"
    },
    {
        "name": "signed_bundle",
        "type": "signed_artifact",
        "base_path": "artifacts",
        "consumes": ["csv_output"],  # ← Wait for CSV to complete
        "security_level": "OFFICIAL"
    }
]

# Pipeline ensures csv_output runs before signed_bundle
pipeline = ArtifactPipeline(sinks=created_sinks, operating_level=SecurityLevel.OFFICIAL)
pipeline.execute(frame, metadata={})
```

---

## Dependency Resolution

### Topological Sort

Sinks are executed in topological order based on `consumes` declarations:

```yaml
sinks:
  # Independent sinks (run first, in parallel)
  - name: csv
    type: csv
    path: data.csv

  - name: excel
    type: excel_workbook
    base_path: report

  # Dependent sinks (run after csv completes)
  - name: signed
    type: signed_artifact
    consumes: [csv]

  - name: zip
    type: zip_bundle
    consumes: [csv, excel]  # Waits for both
```

**Execution Order**:
```
1. csv, excel (parallel)
       ↓
2. signed (waits for csv)
       ↓
3. zip (waits for csv AND excel)
```

### Cycle Detection

Circular dependencies are detected and rejected:

```yaml
sinks:
  - name: sink_a
    consumes: [sink_b]  # ← A depends on B

  - name: sink_b
    consumes: [sink_a]  # ← B depends on A (cycle!)

# Raises: ValueError: Circular dependency detected
```

---

## Security Enforcement

### Per-Sink Validation

Each sink validates it can operate at the pipeline's level:

```python
# Pipeline operating level = OFFICIAL
pipeline = ArtifactPipeline(
    sinks=[
        CSVSink(security_level=SecurityLevel.SECRET),     # ✅ OK (can downgrade)
        ExcelSink(security_level=SecurityLevel.OFFICIAL), # ✅ OK (exact match)
        PDFSink(security_level=SecurityLevel.UNOFFICIAL)  # ❌ Fails (insufficient clearance)
    ],
    operating_level=SecurityLevel.OFFICIAL
)

# PDFSink validation fails:
# SecurityValidationError: Sink 'pdf' has insufficient clearance (UNOFFICIAL) for pipeline level (OFFICIAL)
```

### Data Classification Validation

Sinks validate they can handle the data's classification:

```python
# Data classified as SECRET
frame = ClassifiedDataFrame.create_from_datasource(data, SecurityLevel.SECRET)

# Sink with OFFICIAL clearance
sink = CSVSink(security_level=SecurityLevel.OFFICIAL)

# Execution fails:
# SecurityValidationError: Sink cannot write SECRET data (clearance: OFFICIAL)
```

---

## Metadata Chaining

### Consuming Outputs

Sinks can access outputs from their dependencies:

```python
class SignedBundleSink(BasePlugin):
    def write(self, frame: ClassifiedDataFrame, metadata: dict) -> dict:
        """Write signed bundle."""
        # Access CSV sink output
        csv_path = metadata.get('csv_output', {}).get('path')

        if csv_path:
            # Include CSV in signed bundle
            bundle.add_file(csv_path)

        # Return metadata for downstream sinks
        return {
            "bundle_path": bundle_path,
            "signature_path": signature_path
        }
```

**Metadata Flow**:
```
csv_sink.write()
   ↓ returns {"path": "data.csv"}
   ↓
metadata["csv_output"] = {"path": "data.csv"}
   ↓
signed_sink.write(metadata) ← accesses metadata["csv_output"]["path"]
```

---

## Error Handling

### on_error Policy

Sinks can specify error handling:

```yaml
sinks:
  - name: critical_sink
    type: csv
    on_error: abort  # ← Stop pipeline on error

  - name: optional_sink
    type: analytics_report
    on_error: skip  # ← Log error and continue
```

### Partial Execution

Independent sinks continue even if others fail:

```python
sinks = [
    csv_sink,      # ← Fails
    excel_sink,    # ← Succeeds (independent)
    signed_sink    # ← Skipped (depends on csv_sink)
]

pipeline = ArtifactPipeline(sinks=sinks)
pipeline.execute(frame, metadata={})

# Result:
# - csv_sink: FAILED
# - excel_sink: SUCCESS (independent, unaffected)
# - signed_sink: SKIPPED (dependency failed)
```

---

## Advanced Usage

### Custom Execution Context

```python
class ArtifactPipeline:
    def execute(
        self,
        frame: ClassifiedDataFrame,
        metadata: dict,
        *,
        dry_run: bool = False,
        timeout: Optional[float] = None
    ) -> dict:
        """Execute sinks with custom context.

        Args:
            frame: Data to write
            metadata: Experiment metadata
            dry_run: Simulate execution without writing
            timeout: Per-sink timeout in seconds

        Returns:
            Aggregated metadata from all sinks
        """
        pass
```

### Parallel Execution

Independent sinks can run in parallel:

```python
import concurrent.futures

def execute_parallel(self, frame, metadata):
    """Execute independent sinks in parallel."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Group sinks by dependency level
        levels = self._topological_sort()

        for level_sinks in levels:
            # Run sinks at same level in parallel
            futures = [
                executor.submit(sink.write, frame, metadata)
                for sink in level_sinks
            ]
            # Wait for level to complete before next level
            concurrent.futures.wait(futures)
```

---

## Sink Interface

### Required Methods

```python
from elspeth.core.base.plugin import BasePlugin

class CustomSink(BasePlugin):
    def write(
        self,
        frame: ClassifiedDataFrame,
        metadata: dict
    ) -> dict:
        """Write data to destination.

        Args:
            frame: Data with classification
            metadata: Experiment metadata + outputs from dependencies

        Returns:
            Metadata for downstream sinks (optional)

        Raises:
            SecurityValidationError: If insufficient clearance
        """
        # Validate can operate at data's classification
        self.validate_can_operate_at_level(frame.classification)

        # Write data
        # ...

        # Return metadata for downstream
        return {"output_path": path}
```

### Optional Properties

```python
class CustomSink(BasePlugin):
    def consumes(self) -> list[str]:
        """Return names of sinks this sink depends on."""
        return ["csv_output", "excel_output"]

    def produces(self) -> list[str]:
        """Return names this sink exports to metadata."""
        return ["signed_bundle_path", "signature_path"]
```

---

## Related Documentation

- **[Sinks](../plugins/generated-sinks.md)** - Sink plugin API
- **[ClassifiedDataFrame](../core/classified-dataframe.md)** - Data container
- **[Security Model](../../user-guide/security-model.md)** - Security enforcement

---

## ADR Cross-References

- **ADR-002**: Multi-Level Security - Pipeline enforces security level validation per sink
