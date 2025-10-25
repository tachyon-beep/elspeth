# ADR 009 – Pass-Through Artifact Lifecycle & Transform Composition

## Status

**DRAFT** (2025-10-26)

**Priority**: P0 – CRITICAL (Blocks ADR-006 implementation, 1.0 release)

## Context

Elspeth's artifact pipeline chains plugins that consume and produce artifacts (DataFrames, Excel workbooks, CSV files, JSON objects). ADR-006 "Universal Dual-Output Protocol" proposed that all plugins can produce both DataFrame and Artifact outputs, enabling composability. However, the artifact lifecycle model—when artifacts are created, passed between plugins, and cleaned up—remained undefined.

### Current State Problems

**Problem 1: Monolithic Sinks**
Current "sinks" conflate two concerns:
- **Artifact transformation**: Converting DataFrames → Excel/CSV/JSON (shape change)
- **File writing**: Persisting artifacts to disk/blob/S3 (I/O operation)

This violates separation of concerns and prevents user extensibility:
```python
# Current: Monolithic sink
class ExcelResultSink:
    def write(self, results):
        excel_data = self._create_workbook(results)  # Transform
        with open("output.xlsx", "wb") as f:          # Write
            f.write(excel_data)

# Problems:
# ❌ Cannot reuse Excel generation without file I/O
# ❌ Cannot write to custom destinations (Azure Blob, S3, mainframe)
# ❌ Cannot route Excel artifact to multiple destinations
```

**Problem 2: Artifact Accumulation**
No defined lifecycle for artifact cleanup:
- When are in-memory artifacts freed?
- Do artifacts persist after pipeline execution?
- What happens with high-velocity data (100+ experiments)?
- How to prevent memory exhaustion?

**Problem 3: No Routing Primitives**
Cannot express enterprise routing topologies:
- Write to ALL destinations simultaneously (redundancy, multi-cloud)
- Load balance across destinations (high-velocity data)
- Conditional routing based on security level or content
- Resilient fallback chains (cloud → local on network failure)

### Architectural Discovery

During architecture review, a fundamental insight emerged: **the true plugin taxonomy divides by transformation type**, not just data flow direction:

**Data Transforms** (change **value**):
- Input: DataFrame → Output: DataFrame
- Examples: LLM predictions, filters, aggregations
- Question: "What does this data mean?"

**Artifact Transforms** (change **shape**):
- Input: DataFrame → Output: Artifact
- Examples: Excel generators, JSON serializers, markdown formatters
- Question: "How should this data be represented?"

**File Write Sinks** (persist **artifacts**):
- Input: Artifact → Output: Persisted file
- Examples: Local disk, Azure Blob, S3, **custom user destinations**
- Question: "Where should this artifact be stored?"

This taxonomy enables **composability**: `ExcelTransform` → `IfRouting` → `TryFallback` → `AzureBlobWriter`

### User Extensibility Requirement

> "We need to facilitate users creating their own 'special purpose' plugins (including writing to some bizarre mainframe solution they bought 13 years ago from a company that has gone bankrupt)."

**Users MUST be able to implement custom file writers without forking Elspeth.**

Examples of real-world custom destinations:
- Legacy mainframes (COBOL interfaces, proprietary protocols)
- Custom document management systems
- Proprietary cloud storage (non-AWS/Azure)
- Air-gapped networks (sneakernet/USB drives)
- Compliance systems with specific requirements

### Performance Requirement

> "Remember that these frames will be flying around 'at speed' so we can't have dozens of artifacts backing up."

High-velocity pipelines (1000+ rows/second, 100+ experiments) cannot accumulate artifacts in memory. Need immediate pass-through.

## Decision

We will adopt a **Pass-Through Artifact Lifecycle Model** with **three-tier plugin architecture** and **logical routing primitives** to enable composability, user extensibility, and high-velocity data processing.

### Architecture Overview

```
Tier 1: Artifact Transforms (shape change)
   ↓
Tier 2: Logical Routing (AND/OR/IF/TRY)
   ↓
Tier 3: File Write Sinks (destination-specific I/O)
```

---

## Part 1: Three-Tier Plugin Architecture

### Tier 1: Artifact Transforms (Shape Change)

**Purpose**: Convert DataFrame → Artifact (no I/O)

**Design Principle**: Pure transformation, no side effects

**Examples**:
```python
class ExcelTransform(BasePlugin, ResultSink):
    """Transform DataFrame into Excel workbook artifact.

    No file I/O - pure transformation.
    Compose with BaseFileWriteSink for persistence.
    """

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        # Generate Excel workbook in memory
        workbook = self._create_workbook(results["dataframe"])

        # Create artifact (no file I/O!)
        artifact = Artifact(
            id=f"excel_{uuid.uuid4()}",
            type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=workbook,  # In-memory bytes
            metadata=metadata or {},
            security_level=self.security_level,
        )

        # Hand off to next stage (immediate pass-through)
        self._output_artifact = artifact

    def collect_artifacts(self) -> list[Artifact]:
        """Provide artifact to downstream plugins."""
        return [self._output_artifact] if hasattr(self, "_output_artifact") else []
```

**Built-in Artifact Transforms**:
- `ExcelTransform`: DataFrame → Excel workbook (.xlsx)
- `CsvTransform`: DataFrame → CSV (.csv)
- `JsonTransform`: DataFrame → JSON (.json)
- `MarkdownTransform`: Results → Markdown report (.md)

**Key Properties**:
- No file I/O (pure transformation)
- Produces Artifact objects
- Reusable across multiple destinations
- Fast (no disk/network latency)

---

### Tier 2: BaseFileWriteSink (Abstract Persistence)

**Purpose**: Define common interface for artifact persistence with security enforcement

**Design Pattern**: ADR-004 "Security Bones" – concrete security enforcement in base class

```python
from abc import ABC, abstractmethod

class BaseFileWriteSink(BasePlugin, ResultSink, ABC):
    """Abstract base for artifact persistence.

    Enables user extensibility for custom destinations:
    - Legacy mainframes (COBOL interfaces, proprietary protocols)
    - Custom document management systems
    - Proprietary cloud storage (non-AWS/Azure)
    - Air-gapped networks (sneakernet/USB drives)
    - Compliance systems with specific requirements

    ADR-004 "Security Bones" pattern:
    - Security clearance checking (concrete, @final)
    - Common error handling patterns
    - Audit logging hooks
    """

    def __init__(self, *, security_level: SecurityLevel):
        super().__init__(security_level=security_level)
        self._written_artifacts: list[Artifact] = []

    @final
    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Write artifacts with security enforcement (ADR-004 @final method)."""
        # Get artifacts from upstream
        artifacts = self._get_artifacts_from_results(results)

        # Security clearance check (concrete implementation, ADR-002)
        for artifact in artifacts:
            if artifact.security_level > self.security_level:
                raise SecurityValidationError(
                    f"Sink lacks clearance for {artifact.security_level} data "
                    f"(sink level: {self.security_level})"
                )

        # Delegate to subclass implementation
        self.write_artifacts(artifacts, metadata=metadata)

        # Audit logging (concrete implementation)
        if self.plugin_logger:
            self.plugin_logger.log_event(
                "artifacts_written",
                count=len(artifacts),
                destination=self.__class__.__name__,
            )

    @abstractmethod
    def write_artifacts(
        self,
        artifacts: list[Artifact],
        *,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Write artifacts to destination.

        Subclasses implement destination-specific logic:
        - File path construction
        - Network protocol (HTTP, SFTP, COBOL)
        - Authentication
        - Error handling
        - Retry logic
        """
        pass
```

**Security Enforcement** (ADR-002, ADR-004):
- ✅ Security clearance checking (concrete, cannot override)
- ✅ Audit logging (concrete, cannot override)
- ✅ BasePlugin inheritance (enforced at registration, ADR-004)
- ✅ @final methods prevent security bypass

**Why This Matters**:
> "We need to facilitate users creating their own 'special purpose' plugins (including writing to some bizarre mainframe solution they bought 13 years ago from a company that has gone bankrupt)."

Users inherit from `BaseFileWriteSink`, implement `write_artifacts()`, and get security for free.

---

### Tier 3: Concrete File Writers (Destination-Specific)

**Purpose**: Implement destination-specific persistence logic

**Built-in Implementations**:

#### LocalFileWriteSink
```python
class LocalFileWriteSink(BaseFileWriteSink):
    """Write artifacts to local filesystem."""

    def __init__(self, base_path: Path, *, security_level: SecurityLevel):
        super().__init__(security_level=security_level)
        self.base_path = base_path

    def write_artifacts(
        self,
        artifacts: list[Artifact],
        *,
        metadata: dict[str, Any] | None,
    ) -> None:
        for artifact in artifacts:
            # Construct safe file path
            file_path = self.base_path / artifact.id

            # Path validation (prevent directory traversal)
            resolved = resolve_under_base(file_path, self.base_path)

            # Atomic write
            safe_atomic_write(resolved, artifact.data)
```

#### AzureBlobWriteSink
```python
class AzureBlobWriteSink(BaseFileWriteSink):
    """Write artifacts to Azure Blob Storage."""

    def __init__(
        self,
        container: str,
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.container = container
        self.blob_client = BlobServiceClient(...)  # Managed identity auth

    def write_artifacts(
        self,
        artifacts: list[Artifact],
        *,
        metadata: dict[str, Any] | None,
    ) -> None:
        for artifact in artifacts:
            blob_client = self.blob_client.get_blob_client(
                container=self.container,
                blob=artifact.id,
            )
            blob_client.upload_blob(artifact.data, overwrite=True)
```

**User-Extensible Examples**:

#### LegacyMainframeWriteSink
```python
class LegacyMainframeWriteSink(BaseFileWriteSink):
    """Write to legacy mainframe via COBOL interface.

    System: BIZARRESYS V2 (vendor: DEFUNCT_CORP, bankrupt 2012)
    Protocol: Proprietary binary over TCP/390
    """

    def __init__(
        self,
        host: str,
        interface: str,
        timeout: int = 300,
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.host = host
        self.interface = interface
        self.timeout = timeout

    def write_artifacts(
        self,
        artifacts: list[Artifact],
        *,
        metadata: dict[str, Any] | None,
    ) -> None:
        # User's custom mainframe integration
        connection = self._connect_cobol_interface()
        try:
            for artifact in artifacts:
                connection.send_binary(artifact.data)
        finally:
            connection.close()
```

**Composition Example**:
```yaml
# User's experiment config
sinks:
  # Tier 1: Artifact transform
  - type: excel_transform
    produces: excel_artifact

  # Tier 3: User's custom file writer
  - type: legacy_mainframe_writer
    consumes: excel_artifact
    config:
      host: "10.0.0.1"
      interface: "BIZARRESYS.V2"
      timeout: 300  # It's slow!
```

---

## Part 2: Pass-Through Lifecycle Semantics

### Lifecycle Model: "Hand It Over and Forget It Immediately"

> "The answer is hand it over and forget about it immediately - e.g. the excel file sink creates an excel artifact, hands it to the file_write sink and forgets about it immediately."

**Lifecycle Stages**:
1. **Creation**: Artifact transform creates artifact in memory
2. **Hand-Off**: Artifact passed to downstream plugin via `collect_artifacts()`
3. **Consumption**: File write sink receives artifact via pipeline
4. **Persistence**: File write sink persists artifact to destination
5. **Cleanup**: Python GC frees in-memory artifact (automatic)

**No Accumulation**: Artifacts are NOT held in a "collection phase". Each artifact is passed immediately.

**Memory Safety**:
- Artifacts exist ONLY during pipeline execution
- Python garbage collection handles cleanup automatically
- No explicit cleanup code required
- High-velocity pipelines (1000+ rows/second) safe

**Pipeline Orchestration**:
```python
# ArtifactPipeline orchestrates hand-offs
for plugin in pipeline_order:
    # Execute plugin
    plugin.write(results, metadata=metadata)

    # Immediate hand-off (no accumulation)
    artifacts = plugin.collect_artifacts()

    # Pass to next plugin
    if downstream_plugin:
        results["artifacts"] = artifacts
```

**Failure Handling**:
- If file write fails, artifact is NOT retried from memory
- Artifact transform must re-execute to regenerate
- This is intentional (stateless, reproducible)

---

## Part 3: Logical Routing Plugins (Core Patterns)

Logical routing plugins enable enterprise topologies: redundancy, load balancing, conditional routing, resilient fallbacks.

### Pattern 1: AND (Fan-Out)

**Purpose**: Write artifact to **ALL destinations simultaneously**

**Use Cases**:
- Redundancy: Write to local AND cloud backup
- Multi-cloud: Write to Azure AND AWS AND GCP
- Compliance: Write to production AND audit archive AND DR site

**Implementation**:
```python
class AndRoutingSink(BasePlugin, ResultSink):
    """Route artifact to ALL configured destinations."""

    def __init__(
        self,
        destinations: list[BaseFileWriteSink],
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.destinations = destinations

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        for destination in self.destinations:
            destination.write(results, metadata=metadata)  # Fan-out to all
```

**Configuration Example**:
```yaml
sinks:
  - type: excel_transform
    produces: excel_artifact

  - type: and_routing
    consumes: excel_artifact
    destinations:
      - type: local_file_writer
        path: ./outputs/
      - type: azure_blob_writer
        container: backups
      - type: s3_writer
        bucket: dr-archive
```

---

### Pattern 2: OR (Load Balancing)

**Purpose**: Write artifact to **ONE of multiple destinations** (distribute load)

**Strategies**:
- Round-robin: Distribute evenly across destinations
- Random: Random selection
- Least-loaded: Send to destination with lowest queue
- Health-aware: Skip unhealthy destinations

**Use Cases**:
- High-velocity data: Distribute writes across destinations
- Regional routing: Send to closest/fastest destination
- Cost optimization: Route to cheapest available destination

**Implementation**:
```python
class OrRoutingSink(BasePlugin, ResultSink):
    """Route artifact to ONE destination using load balancing strategy."""

    def __init__(
        self,
        destinations: list[BaseFileWriteSink],
        strategy: str = "round_robin",
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.destinations = destinations
        self.strategy = strategy
        self._counter = 0  # For round-robin

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        destination = self._select_destination()  # Pick ONE
        destination.write(results, metadata=metadata)

    def _select_destination(self) -> BaseFileWriteSink:
        if self.strategy == "round_robin":
            destination = self.destinations[self._counter % len(self.destinations)]
            self._counter += 1
            return destination
        elif self.strategy == "random":
            return random.choice(self.destinations)
        # ... other strategies
```

**Configuration Example** (high-velocity data):
```yaml
sinks:
  - type: csv_transform
    produces: csv_artifact

  - type: or_routing
    consumes: csv_artifact
    strategy: round_robin
    destinations:
      - type: local_file_writer
        path: /mnt/fast-disk-1/
      - type: local_file_writer
        path: /mnt/fast-disk-2/
      - type: local_file_writer
        path: /mnt/fast-disk-3/
```

---

### Pattern 3: IF (Conditional Routing)

**Purpose**: Route artifact to **different destinations based on conditions**

**Use Cases**:
- Security-based routing: SECRET → encrypted storage, UNCLASSIFIED → regular
- Size-based routing: Large files → blob, small → database
- Content-based routing: PII detected → compliance archive
- Regional routing: EU data → EU region, US data → US region (GDPR)

**Implementation**:
```python
class IfRoutingSink(BasePlugin, ResultSink):
    """Route artifact based on conditional logic."""

    def __init__(
        self,
        conditions: list[tuple[Callable[[Artifact], bool], BaseFileWriteSink]],
        default: BaseFileWriteSink,
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.conditions = conditions  # [(predicate, destination), ...]
        self.default = default

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        artifacts = self._get_artifacts(results)
        for artifact in artifacts:
            for predicate, destination in self.conditions:
                if predicate(artifact):
                    destination.write({**results, "artifacts": [artifact]}, metadata=metadata)
                    break
            else:
                self.default.write({**results, "artifacts": [artifact]}, metadata=metadata)
```

**Configuration Example** (security-based routing):
```yaml
sinks:
  - type: excel_transform
    produces: excel_artifact

  - type: if_routing
    consumes: excel_artifact
    conditions:
      - when: "artifact.security_level == SecurityLevel.SECRET"
        destination:
          type: azure_blob_writer
          container: classified-storage
          encryption: true

      - when: "artifact.security_level == SecurityLevel.CONFIDENTIAL"
        destination:
          type: s3_writer
          bucket: confidential-storage
          sse: AES256

    default:
      type: local_file_writer
      path: ./outputs/unclassified/
```

**Why This Matters**:
- **Security compliance**: Different security levels → different storage tiers
- **Cost optimization**: Route expensive data to appropriate storage (hot vs cold)
- **Regulatory**: EU data → EU region, US data → US region (GDPR compliance)

---

### Pattern 4: TRY (Fallback Chain)

**Purpose**: Attempt primary destination, **fall back to secondary on failure**

**Use Cases**:
- Network resilience: Try cloud, fall back to local on network failure
- Multi-cloud failover: Try Azure, fall back to AWS, fall back to local
- Availability prioritization (ADR-001 priority #3)

**Implementation**:
```python
class TryFallbackSink(BasePlugin, ResultSink):
    """Resilient routing with fallback chain."""

    def __init__(
        self,
        destinations: list[BaseFileWriteSink],
        *,
        security_level: SecurityLevel,
    ):
        super().__init__(security_level=security_level)
        self.destinations = destinations  # Try in order

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        last_exception = None
        for destination in self.destinations:
            try:
                destination.write(results, metadata=metadata)
                return  # Success! Stop trying
            except Exception as exc:
                last_exception = exc
                logger.warning(f"Destination {destination} failed, trying next...")
                continue
        raise last_exception  # All destinations failed
```

**Configuration Example** (multi-cloud resilience):
```yaml
sinks:
  - type: csv_transform
    produces: csv_artifact

  - type: try_fallback
    consumes: csv_artifact
    destinations:
      - type: azure_blob_writer
        container: primary-storage
      - type: s3_writer
        bucket: backup-storage
      - type: local_file_writer
        path: /mnt/local-fallback/
```

**Why This Matters**:
- **High availability**: ADR-001 priority #3 (Availability)
- **Network resilience**: Continue operating during cloud outages
- **Cost optimization**: Try cheap storage first, fall back to expensive on failure

---

### Pattern 5: Composite AND/OR (Complex Topologies)

**Purpose**: Combine routing patterns for enterprise topologies

**Example** (redundant multi-region with load balancing):
```yaml
sinks:
  - type: excel_transform
    produces: excel_artifact

  # AND: Write to both regions (redundancy)
  - type: and_routing
    consumes: excel_artifact
    destinations:
      # Region A: Load balance across 3 nodes
      - type: or_routing
        strategy: round_robin
        destinations:
          - {type: s3_writer, bucket: us-east-1-node-1}
          - {type: s3_writer, bucket: us-east-1-node-2}
          - {type: s3_writer, bucket: us-east-1-node-3}

      # Region B: Load balance across 3 nodes
      - type: or_routing
        strategy: round_robin
        destinations:
          - {type: s3_writer, bucket: eu-west-1-node-1}
          - {type: s3_writer, bucket: eu-west-1-node-2}
          - {type: s3_writer, bucket: eu-west-1-node-3}
```

**Result**: Every artifact written to **both regions** (AND), with writes **load-balanced within each region** (OR).

---

## Consequences

### Benefits

1. **Composability**: Artifact transforms reusable across destinations
   - Example: `ExcelTransform` + `LocalFileWriter` OR `AzureBlobWriter`

2. **User Extensibility**: Custom destinations without forking
   - Example: Legacy mainframe, proprietary storage, air-gapped networks

3. **Enterprise Topologies**: Routing primitives enable complex patterns
   - Redundancy (AND), load balancing (OR), conditional (IF), resilient (TRY)

4. **Memory Safety**: Pass-through lifecycle prevents accumulation
   - High-velocity pipelines (1000+ rows/second) safe

5. **Security**: BaseFileWriteSink enforces clearance checks (ADR-002, ADR-004)
   - Users cannot bypass security (concrete @final methods)

6. **Separation of Concerns**: Transform vs I/O cleanly separated
   - Testability: Transform logic testable without I/O
   - Performance: Transform benchmarking without I/O latency

7. **ADR-006 Enablement**: Unlocks universal dual-output protocol
   - All plugins can produce artifacts, compose freely

### Limitations / Trade-offs

1. **Complexity**: Three-tier architecture more complex than monolithic sinks
   - *Mitigation*: Documentation with examples, migration guide

2. **Configuration Verbosity**: Routing plugins add YAML lines
   - *Mitigation*: Sensible defaults, configuration templates

3. **No Artifact Caching**: Artifacts not held for reuse
   - *Mitigation*: Intentional (stateless, reproducible), regenerate if needed

4. **Breaking Change**: Existing monolithic sinks must decompose
   - *Mitigation*: Migration guide, adapter pattern for backward compatibility

5. **Learning Curve**: Developers must understand composition
   - *Mitigation*: Examples in documentation, plugin authoring guide

### Advanced Patterns (Post-1.0)

The following patterns are deferred to ADR-013 "Advanced Routing Patterns":

- **WHEN (guard)**: Conditional filtering (only write if condition met)
- **CIRCUIT_BREAKER**: Fault tolerance (prevent cascade failures)
- **THROTTLE**: Rate limiting (respect external API limits)
- **TEE (audit)**: Side-effect + pass-through (non-terminal audit trail)

**Rationale**: Core 4 patterns (AND/OR/IF/TRY) sufficient for 1.0, advanced patterns add complexity without blocking functionality.

### Implementation Checklist

**Phase 1: Foundation** (P0, blocking 1.0):
- [ ] Implement `BaseFileWriteSink` abstract base
- [ ] Migrate built-in sinks to three-tier architecture
  - [ ] `ExcelTransform` + `LocalFileWriteSink`
  - [ ] `CsvTransform` + `LocalFileWriteSink`
  - [ ] `JsonTransform` + `LocalFileWriteSink`
- [ ] Implement core routing plugins (AND/OR/IF/TRY)
- [ ] Update ArtifactPipeline for pass-through lifecycle
- [ ] Write migration guide for custom sink authors

**Phase 2: Azure/AWS Integration** (P1):
- [ ] Implement `AzureBlobWriteSink`
- [ ] Implement `S3WriteSink`
- [ ] Add examples for multi-cloud topologies

**Phase 3: Advanced Patterns** (P2, post-1.0):
- [ ] ADR-013: WHEN/CIRCUIT_BREAKER/THROTTLE/TEE patterns
- [ ] Performance benchmarking (high-velocity pipelines)
- [ ] Plugin catalog update with routing examples

### Migration Path

**Existing Monolithic Sinks**:
```python
# Before (monolithic)
class ExcelResultSink(BasePlugin, ResultSink):
    def write(self, results):
        excel_data = self._create_workbook(results)
        with open("output.xlsx", "wb") as f:
            f.write(excel_data)

# After (decomposed)
class ExcelTransform(BasePlugin, ResultSink):
    def write(self, results):
        excel_data = self._create_workbook(results)
        self._output_artifact = Artifact(data=excel_data, ...)

class LocalFileWriteSink(BaseFileWriteSink):
    def write_artifacts(self, artifacts):
        for artifact in artifacts:
            with open(artifact.id, "wb") as f:
                f.write(artifact.data)
```

**Configuration Migration**:
```yaml
# Before
sinks:
  - type: excel_result_sink
    path: ./outputs/

# After
sinks:
  - type: excel_transform
  - type: local_file_writer
    path: ./outputs/
```

**Backward Compatibility** (temporary adapter):
```python
class ExcelResultSinkAdapter(ExcelTransform):
    """Backward compatibility adapter (deprecated, remove post-1.0)."""

    def __init__(self, path: Path, **kwargs):
        super().__init__(**kwargs)
        self.file_writer = LocalFileWriteSink(path)

    def write(self, results, *, metadata=None):
        super().write(results, metadata=metadata)
        artifacts = self.collect_artifacts()
        self.file_writer.write_artifacts(artifacts, metadata=metadata)
```

### Related ADRs

- **ADR-001**: Design Philosophy – Fail-closed principle, security-first
- **ADR-002**: Multi-Level Security – BaseFileWriteSink enforces clearance checks
- **ADR-004**: Mandatory BasePlugin – BaseFileWriteSink uses "security bones" pattern
- **ADR-006**: Universal Dual-Output – Enabled by pass-through lifecycle
- **ADR-007**: Unified Registry Pattern – File write sinks registered consistently
- **Future ADR-013**: Advanced Routing Patterns – WHEN/CIRCUIT_BREAKER/THROTTLE/TEE

### Implementation References

- `src/elspeth/core/base/artifact.py` – Artifact data model
- `src/elspeth/core/pipeline/artifact_pipeline.py` – Pass-through orchestration
- `src/elspeth/plugins/nodes/transforms/` – Artifact transforms (shape change)
- `src/elspeth/plugins/nodes/sinks/` – File write sinks (destination I/O)
- `src/elspeth/plugins/nodes/sinks/routing/` – Logical routing plugins

---

**Document Status**: DRAFT – Requires review and acceptance before implementation
**Next Steps**:
1. Review with team (architecture implications)
2. Prototype BaseFileWriteSink + one routing plugin
3. Migration guide for existing sinks
4. Update ADR-006 with lifecycle semantics
