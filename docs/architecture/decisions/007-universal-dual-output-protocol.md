# ADR-007: Universal Dual-Output Plugin Protocol for Composability

**Status**: PROPOSED
**Date**: 2025-10-26
**Deciders**: Architecture Team, Core Platform Team
**Related**: ADR-003 (Plugin type registry), ADR-004 (Mandatory BasePlugin inheritance)

---

## TL;DR - Dual-Output Pattern

Every plugin produces TWO output types with multi-level inheritance control:

```python
class DualOutputMixin:
    """Provides automatic dual-output tracking for all plugins.

    DUAL-OUTPUT PROTOCOL (ADR-007):
    1. DataFrame output - Data flowing through pipeline (sources/transforms)
    2. Artifact output - Chainable metadata for composition (all plugins)

    Both enabled by default, with three-level inheritance control:
    - Abstract base sets domain defaults
    - Concrete base refines for category
    - Final plugin makes ultimate decision
    """

    # Class attributes - override at ANY inheritance level
    _produces_dataframe: bool = True   # Default: ON (opt-out)
    _produces_artifacts: bool = True   # Default: ON (opt-out)

    def _register_dataframe_output(self, df: pd.DataFrame) -> None:
        """Register DataFrame for pipeline flow."""
        if not self._produces_dataframe:
            return  # No-op if disabled
        self._output_dataframe = df

    def _register_artifact_output(self, name: str, type: str, **kwargs) -> None:
        """Register artifact for chaining."""
        if not self._produces_artifacts:
            return  # No-op if disabled
        self._output_artifacts[name] = Artifact(name, type, **kwargs)
```

**Example - Three-level inheritance control:**

```python
# Level 1: Abstract base (domain defaults)
class BaseDataSource(DualOutputMixin, DataSource):
    _produces_dataframe = True   # ✅ All datasources output DataFrames
    _produces_artifacts = True   # ✅ By default, expose source metadata

# Level 2: Concrete base (category refinement)
class BlobDataSource(BaseDataSource):
    _produces_artifacts = False  # ❌ Blob URIs aren't useful artifacts

# Level 3: Final plugin (ultimate decision)
class DebugBlobDataSource(BlobDataSource):
    _produces_artifacts = True   # ✅ Re-enable for debugging purposes!
```

**Impact**: Reduces boilerplate from ~640 lines (13 sinks × 40 lines) to ~48 lines (93% reduction).

**NOTE**: All references to ADR-006 in this document refer to ADR-007 (Security-Critical Exception Policy is separately numbered as ADR-006).

---

## Context and Problem Statement

### Current State: Inconsistent Output Semantics

Elspeth's plugin architecture has evolved organically with **three different output patterns** across plugin types:

**1. DataSources** - Single output (DataFrame only):

```python
class DataSource(Protocol):
    def load(self) -> pd.DataFrame:  # ✅ DataFrame output
        ...
    # ❌ No artifact tracking - file paths lost
    # ❌ No produces() method
    # ❌ No collect_artifacts() method
```

**2. Transforms** - Single output (dict only):

```python
class TransformNode(Protocol):
    def transform(self, data: dict, **kwargs) -> dict:  # ⚠️ Dict, not DataFrame
        ...
    # ❌ No artifact tracking - LLM metadata lost
    # ❌ No produces/consumes methods
```

**3. Sinks** - Artifact output (manual, duplicated):

```python
class ResultSink(Protocol):
    def write(self, results: dict, ...) -> None:
        ...
    def produces(self) -> list[ArtifactDescriptor]:  # ✅ Artifact output
        return []  # Optional, manual implementation
    def collect_artifacts(self) -> dict[str, Artifact]:
        return {}  # Optional, manual implementation
```

### The Problems

**Problem 1: Lost Metadata** - Sources produce data but discard valuable metadata:

```python
class CSVLocalDataSource(BaseCSVDataSource):
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)  # File path available here
        return df  # ❌ Path discarded - can't chain to "archive source CSV" sink
```

**Problem 2: No Transform Chaining** - LLM responses can't be cached or analyzed:

```python
class AzureOpenAIClient(LLMClientProtocol):
    def generate(self, *, system_prompt, user_prompt, metadata=None):
        response = self._call_api(...)
        return response  # ❌ Usage metadata lost, can't chain to cost analyzer
```

**Problem 3: Massive Boilerplate Duplication** - 13 sinks duplicate ~40 lines each:

```python
# Pattern repeated in csv_file.py, excel.py, signed.py, visual_report.py, etc.
class ExcelResultSink(BasePlugin, ResultSink):
    def __init__(self, ...):
        self._last_workbook_path: str | None = None  # ← Manual tracking

    def write(self, results, *, metadata=None):
        # ... write logic ...
        self._last_workbook_path = str(target)  # ← Manual capture

    def produces(self) -> list[ArtifactDescriptor]:  # ← Manual declaration
        return [ArtifactDescriptor(name="excel", type="file/xlsx", ...)]

    def collect_artifacts(self) -> dict[str, Artifact]:  # ← Manual construction
        if not self._last_workbook_path:
            return {}
        return {"excel": Artifact(..., path=self._last_workbook_path, ...)}
```

**Total duplication**: 13 sinks × 40 lines = **520+ lines of identical boilerplate**

**Problem 4: Prevented Composition Patterns** - Can't build:

- **DataFrame archiving** - Store original source data alongside results
- **Response caching** - Cache LLM responses as artifacts for replay/analysis
- **Multi-stage transforms** - Transform → analyze → secondary transform chains
- **Cross-experiment artifacts** - Baseline produces artifacts consumed by variant
- **Source provenance** - Track which files contributed to results

### Current Partial Solution: ArtifactPipeline

The codebase has sophisticated chaining infrastructure (`src/elspeth/core/pipeline/artifact_pipeline.py:1-409`):

- ✅ Topological dependency resolution
- ✅ Security-aware artifact flow (clearance checks)
- ✅ Artifact store with alias/type-based lookup
- ✅ Metadata propagation (SecurityLevel, DeterminismLevel)

**BUT**: Only sinks participate, and implementation is manual/duplicated.

### Why This Matters

**Composability is a force multiplier**:

- Sources + sinks = Basic pipeline
- Sources + transforms + sinks = LLM experiments
- **Sources + transforms + sinks + artifact chaining** = Complex workflows, caching, provenance tracking

Without universal chaining, Elspeth remains a "linear pipeline" system rather than a "composable orchestration" platform.

---

## Decision Drivers

1. **Composability** - Enable rich composition patterns (caching, archiving, multi-stage transforms)
2. **Boilerplate Reduction** - Eliminate 93% of duplicated chaining code
3. **Consistency** - Uniform output semantics across all plugin types
4. **Developer Experience** - Clear pattern: "All plugins chain by default"
5. **Metadata Fidelity** - Preserve source paths, LLM usage, security levels throughout chain
6. **Backward Compatibility** - Existing plugins continue working during migration
7. **Security Traceability** - Artifact metadata flows naturally (ADR-002 integration)
8. **Flexibility** - Allow category-specific disabling (e.g., blob sources don't need artifacts)

---

## Considered Options

### Option 1: Status Quo (Manual Sink-Only Chaining)

**Approach**: Keep current pattern - sinks implement chaining manually, sources/transforms don't participate.

**Pros**:

- ✅ No breaking changes
- ✅ Existing infrastructure works
- ✅ Simple mental model (only outputs chain)

**Cons**:

- ❌ 520+ lines of duplicated boilerplate
- ❌ Sources can't expose metadata (file paths lost)
- ❌ Transforms can't expose metadata (LLM usage lost)
- ❌ No DataFrame archiving, response caching, multi-stage chains
- ❌ Every new sink reimplements same 40 lines

**Verdict**: Rejected - Technical debt compounds with every new plugin.

### Option 2: Single Output with Reflection (Auto-detect artifacts)

**Approach**: Use reflection to automatically detect what plugins produce, no explicit registration.

```python
class DataSource:
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return df

    # Framework reflects on self.path, self._metadata, etc. to build artifacts
```

**Pros**:

- ✅ Zero boilerplate - fully automatic
- ✅ No developer burden

**Cons**:

- ❌ "Magic" behavior - hard to debug
- ❌ Can't control what gets exposed
- ❌ Reflection overhead
- ❌ Fragile (breaks if attributes renamed)
- ❌ Security risk (accidentally exposes sensitive attributes)

**Verdict**: Rejected - Too magical, security concerns.

### Option 3: Dual-Output with Inheritance Control - CHOSEN

**Approach**: Every plugin explicitly produces TWO outputs (DataFrame + Artifacts) with class-level control flags.

**Implementation Strategy**:

1. **DualOutputMixin** base class provides automatic tracking
2. **Class attributes** control behavior at any inheritance level
3. **Soft enforcement** - disabled outputs become no-ops (not errors)
4. **Default: both enabled** - opt-out pattern maximizes composability

**Pros**:

- ✅ **Reduces boilerplate 93%** (640 lines → 48 lines)
- ✅ **Explicit control** - no magic, clear semantics
- ✅ **Multi-level inheritance** - disable at base, override in child
- ✅ **Backward compatible** - existing code works unchanged
- ✅ **Unlocks composition** - all plugins can chain
- ✅ **Security metadata flows** - automatic propagation
- ✅ **Consistent pattern** - same approach for all plugin types

**Cons**:

- ⚠️ Adds complexity to base protocol (two outputs vs one)
- ⚠️ Lifecycle question (when are in-memory artifacts cleaned up?)
- ⚠️ Need to define standard artifact types (dataframe, llm/response, etc.)

**Mitigations**:

- Complexity: Clear documentation, examples for each plugin type
- Lifecycle: ArtifactStore manages lifecycle, respects `persist` flag
- Types: Create standard taxonomy in `core/base/artifact_types.py`

**Verdict**: Chosen - Best balance of power, simplicity, and control.

---

## Decision

We will implement a **Universal Dual-Output Protocol** where ALL plugins produce two output types with multi-level inheritance control.

### Security Alignment (ADR-002 / ADR-005)

- **Explicit downgrade policy**: Every dual-output participant calls
  `BasePlugin.__init__(..., allow_downgrade=...)`. There is no default—plugins must
  opt-in to trusted downgrade or remain frozen.
- **MLS propagation**: Artifact transforms, routing nodes, and file writers
  propagate `SecurityLevel` and invoke `validate_compatible_with()` (or equivalent
  artifact clearance checks) on every hop. Artifacts never bypass the MLS guard
  rail when routed.
- **Frozen plugins**: Components with `allow_downgrade=False` will refuse to
  process artifacts whose effective operating level is lower than their
  clearance. Routing primitives must short-circuit the flow when a frozen node
  is asked to downgrade.
- **Auditability**: Artifact metadata includes classification, determinism, and
  provenance, so downstream sinks can re-validate before persisting and audits
  retain a complete chain of custody.

### Security Metadata Propagation (ADR-002 Integration)

**Artifact Security Level Inheritance**:

Every registered artifact inherits the plugin's `security_level` by default (unless explicitly overridden):

```python
def _register_artifact_output(
    self,
    name: str,
    type: str,
    *,
    security_level: SecurityLevel | None = None,  # Optional override
    ...
) -> None:
    # Default to plugin's clearance if not specified
    effective_level = security_level or self.security_level

    artifact = Artifact(
        id=f"{self.__class__.__name__}_{name}",
        type=type,
        security_level=effective_level,  # ← Propagated from plugin
        ...
    )
    self._output_artifacts[name] = artifact
```

**ArtifactPipeline Clearance Enforcement**:

Artifact flow is validated at each hop (existing implementation in `artifact_pipeline.py:192`):

```python
# Simplified enforcement logic
class ArtifactPipeline:
    def execute_sink(self, sink: ResultSink, artifacts: dict[str, Artifact]):
        for artifact in artifacts.values():
            # Check 1: Sink must have clearance for artifact
            if artifact.security_level > sink.security_level:
                raise SecurityValidationError(
                    f"Sink {sink.__class__.__name__} (clearance: {sink.security_level}) "
                    f"cannot process artifact (classification: {artifact.security_level}) "
                    f"- insufficient clearance (ADR-002)"
                )

            # Check 2: Frozen plugins reject downgrade
            if artifact.security_level < sink.security_level and not sink.allow_downgrade:
                raise SecurityValidationError(
                    f"Frozen sink {sink.__class__.__name__} cannot operate below its "
                    f"clearance level (ADR-005)"
                )

        # Clearance validated → execute sink
        sink.write(artifacts)
```

**Routing Primitive Security**:

Routing nodes (AND/OR/IF/TRY, see ADR-010) preserve security level:
- Artifacts maintain original `security_level` through routing
- Destination validation performed before routing decision
- Frozen routing nodes reject mismatched clearances

**Cross-Reference**: See ADR-002 lines 52-88 for Bell-LaPadula asymmetry details (data classification ↑ only, plugin operations ↓ only).

### Immutable Policy Integration (ADR-002-B)

**Security Policy Exclusion from Configuration**:

Per ADR-002-B, security policy fields (`security_level`, `allow_downgrade`) are **forbidden in plugin configuration schemas**. The dual-output protocol enforces this:

```python
# ❌ FORBIDDEN: Schema exposing security policy
EXCEL_TRANSFORM_SCHEMA = {
    "properties": {
        "sanitize_formulas": {"type": "boolean"},
        "security_level": {"type": "string"},  # ← FORBIDDEN (ADR-002-B)
    }
}

# ✅ CORRECT: Security policy declared in code only
class ExcelTransform(BasePlugin, DualOutputMixin, ResultSink):
    def __init__(self, *, sanitize_formulas: bool = True):
        # Security policy hard-coded (immutable)
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # Code-declared
            allow_downgrade=True,                      # Code-declared
        )
        self.sanitize_formulas = sanitize_formulas

# Schema validation (ADR-008 registry enforcement)
EXCEL_TRANSFORM_SCHEMA = {
    "properties": {
        "sanitize_formulas": {"type": "boolean"},
        # ✅ No security_level (code-only field)
    }
}
```

**Registry Validation**:

Plugin registries (ADR-008) reject schemas exposing forbidden fields:

```python
# Automatic enforcement when registering dual-output plugins
registry.register(
    name="excel_transform",
    plugin_class=ExcelTransform,
    schema=EXCEL_TRANSFORM_SCHEMA  # ← Validated: no security policy fields
)
# If schema had "security_level", registration would fail (ADR-002-B)
```

**Rationale**: Operators choose *which plugin* to use (e.g., `excel_transform` vs `csv_transform`), not *how secure* that plugin behaves. Security policy is plugin implementation detail, not deployment configuration.

**Cross-Reference**:
- [ADR-002-B](002-b-security-policy-metadata.md) – Full immutable policy specification
- [ADR-008](008-unified-registry-pattern.md) – Registry enforcement mechanism

### Core Components

#### 1. DualOutputMixin Base Class

**File**: `src/elspeth/core/base/outputs.py` (NEW)

```python
"""Dual-output protocol for universal plugin composability (ADR-006)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from elspeth.core.base.protocols import Artifact

class DualOutputMixin:
    """Provides automatic dual-output tracking for all plugins.

    DUAL-OUTPUT PROTOCOL (ADR-007):
    Every plugin can produce TWO output types:

    1. **DataFrame Output** - Data flowing through pipeline
       - Sources: Loaded data
       - Transforms: Transformed data
       - Sinks: N/A (terminal nodes)

    2. **Artifact Output** - Chainable metadata/files for composition
       - Sources: File paths, schema metadata, row counts
       - Transforms: LLM usage, latency, model info
       - Sinks: Output file paths, signed bundles, etc.

    INHERITANCE CONTROL:
    Control output behavior via class attributes at ANY level:

        class BaseDataSource(DualOutputMixin):
            _produces_dataframe = True   # Level 1: Domain default
            _produces_artifacts = True

        class BlobDataSource(BaseDataSource):
            _produces_artifacts = False  # Level 2: Category override

        class DebugBlobSource(BlobDataSource):
            _produces_artifacts = True   # Level 3: Final plugin override

    SOFT ENFORCEMENT:
    Calls to disabled outputs are no-ops, not errors:

        self._register_artifact_output(...)  # No-op if _produces_artifacts = False

    This allows base class code to register outputs without knowing if child disabled.
    """

    # Class attributes - override at ANY inheritance level
    _produces_dataframe: bool = True   # Default: ON (opt-out pattern)
    _produces_artifacts: bool = True   # Default: ON (opt-out pattern)

    def __init__(self, **kwargs):
        """Initialize dual-output tracking."""
        super().__init__(**kwargs)
        self._output_dataframe: pd.DataFrame | None = None
        self._output_artifacts: dict[str, Artifact] = {}

    def _register_dataframe_output(self, df: pd.DataFrame) -> None:
        """Register DataFrame for pipeline flow (if enabled).

        Args:
            df: DataFrame to expose as output

        Note:
            No-op if _produces_dataframe = False (soft enforcement)
        """
        if not self._produces_dataframe:
            return
        self._output_dataframe = df

    def _register_artifact_output(
        self,
        name: str,
        type: str,
        *,
        path: str | None = None,
        payload: Any | None = None,
        metadata: dict[str, Any] | None = None,
        persist: bool = False,
        security_level: Any | None = None,
    ) -> None:
        """Register artifact for chaining (if enabled).

        Args:
            name: Artifact identifier (must be unique per plugin)
            type: Artifact type (e.g., "file/csv", "dataframe", "llm/response")
            path: File path for file-based artifacts
            payload: In-memory payload for memory-based artifacts
            metadata: Additional metadata dict
            persist: Whether artifact should be persisted after pipeline completion
            security_level: Security classification (defaults to plugin's level)

        Note:
            No-op if _produces_artifacts = False (soft enforcement)
        """
        if not self._produces_artifacts:
            return

        from elspeth.core.base.protocols import Artifact

        artifact = Artifact(
            id="",  # Set by ArtifactStore during registration
            type=type,
            path=path,
            payload=payload,
            metadata=metadata or {},
            persist=persist,
            security_level=security_level,
        )
        self._output_artifacts[name] = artifact

    def get_output_dataframe(self) -> pd.DataFrame | None:
        """Retrieve registered DataFrame output (if enabled).

        Returns:
            DataFrame if produced and enabled, None otherwise
        """
        return self._output_dataframe if self._produces_dataframe else None

    def collect_artifacts(self) -> dict[str, Artifact]:
        """Retrieve registered artifacts (if enabled).

        Returns:
            Dict mapping artifact names to Artifact objects
            Empty dict if disabled or no artifacts registered

        Note:
            This method is called by ArtifactPipeline during execution
        """
        return dict(self._output_artifacts) if self._produces_artifacts else {}

    def produces(self) -> list[Any]:  # Returns list[ArtifactDescriptor]
        """Auto-generate artifact descriptors from registered artifacts.

        Returns:
            List of ArtifactDescriptor for all registered artifacts
            Empty list if disabled or no artifacts registered

        Note:
            Subclasses can override for static declarations, or rely on
            dynamic generation from _register_artifact_output() calls
        """
        if not self._produces_artifacts:
            return []

        from elspeth.core.base.protocols import ArtifactDescriptor

        return [
            ArtifactDescriptor(
                name=name,
                type=artifact.type,
                persist=artifact.persist,
                security_level=artifact.security_level,
            )
            for name, artifact in self._output_artifacts.items()
        ]
```

#### 2. Extended Protocols

**File**: `src/elspeth/core/base/protocols.py` (MODIFY)

Add chaining methods to DataSource and TransformNode protocols:

```python
@runtime_checkable
class DataSource(Protocol):
    """Source node: where data comes from."""

    def load(self) -> pd.DataFrame:
        """Return the experiment dataset."""
        raise NotImplementedError

    def output_schema(self) -> type[DataFrameSchema] | None:
        """Return the schema of the DataFrame this datasource produces."""
        return None

    # NEW: Artifact chaining protocol (ADR-006)
    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - optional
        """Describe artifacts the source emits, enabling chaining."""
        return []

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover - optional
        """Expose artifacts generated during load for downstream consumers."""
        return {}


@runtime_checkable
class TransformNode(Protocol):
    """Transform node: process data at a vertex."""

    name: str

    def transform(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Apply transformation to data."""
        raise NotImplementedError

    # NEW: Artifact chaining protocol (ADR-006)
    def produces(self) -> list[ArtifactDescriptor]:  # pragma: no cover - optional
        """Describe artifacts the transform emits, enabling chaining."""
        return []

    def consumes(self) -> list[str]:  # pragma: no cover - optional
        """Return artifact names the transform depends on."""
        return []

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover - optional
        """Expose artifacts generated during transform for downstream consumers."""
        return {}
```

#### 3. Standard Artifact Types

**File**: `src/elspeth/core/base/artifact_types.py` (NEW)

```python
"""Standard artifact type taxonomy for ADR-006 dual-output protocol."""

# Data artifacts
ARTIFACT_TYPE_DATAFRAME = "dataframe"

# LLM artifacts
ARTIFACT_TYPE_LLM_RESPONSE = "llm/response"
ARTIFACT_TYPE_LLM_EMBEDDING = "llm/embedding"

# Metric artifacts
ARTIFACT_TYPE_METRIC_SCORE = "metric/score"
ARTIFACT_TYPE_METRIC_COST = "metric/cost"
ARTIFACT_TYPE_METRIC_LATENCY = "metric/latency"

# File artifacts (existing)
ARTIFACT_TYPE_FILE_CSV = "file/csv"
ARTIFACT_TYPE_FILE_XLSX = "file/xlsx"
ARTIFACT_TYPE_FILE_JSON = "file/json"
ARTIFACT_TYPE_FILE_MARKDOWN = "file/markdown"
ARTIFACT_TYPE_FILE_PNG = "file/png"
ARTIFACT_TYPE_FILE_TAR_GZ = "file/tar.gz"

# Bundle artifacts
ARTIFACT_TYPE_BUNDLE_SIGNED = "bundle/signed"
ARTIFACT_TYPE_BUNDLE_REPRODUCIBILITY = "bundle/reproducibility"

# Registry of valid types (for validation)
VALID_ARTIFACT_TYPES = {
    ARTIFACT_TYPE_DATAFRAME,
    ARTIFACT_TYPE_LLM_RESPONSE,
    ARTIFACT_TYPE_LLM_EMBEDDING,
    ARTIFACT_TYPE_METRIC_SCORE,
    ARTIFACT_TYPE_METRIC_COST,
    ARTIFACT_TYPE_METRIC_LATENCY,
    ARTIFACT_TYPE_FILE_CSV,
    ARTIFACT_TYPE_FILE_XLSX,
    ARTIFACT_TYPE_FILE_JSON,
    ARTIFACT_TYPE_FILE_MARKDOWN,
    ARTIFACT_TYPE_FILE_PNG,
    ARTIFACT_TYPE_FILE_TAR_GZ,
    ARTIFACT_TYPE_BUNDLE_SIGNED,
    ARTIFACT_TYPE_BUNDLE_REPRODUCIBILITY,
}
```

### Implementation Examples

#### Example 1: DataSource with Dual Output

```python
# BEFORE (csv_local.py) - 15 lines, no artifact tracking
class CSVLocalDataSource(BaseCSVDataSource):
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return df  # Path lost!

# AFTER - 20 lines, artifact tracking automatic
class CSVLocalDataSource(BaseCSVDataSource, DualOutputMixin):
    _produces_dataframe = True   # ✅ Output DataFrame
    _produces_artifacts = True   # ✅ Output file artifact

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)

        # Register DataFrame output (for future DataFrame chaining)
        self._register_dataframe_output(df)

        # Register file artifact (NEW capability!)
        self._register_artifact_output(
            name="source_csv",
            type="file/csv",
            path=str(self.path),
            metadata={
                "rows": len(df),
                "columns": len(df.columns),
                "schema": df.dtypes.to_dict(),
            },
            persist=False,  # Don't persist (source file already exists)
            security_level=self.security_level,
        )

        return df
```

#### Example 2: Blob Source (Artifacts Disabled)

```python
# Blob URIs aren't useful as artifacts - disable at base level
class BlobDataSource(BaseDataSource, DualOutputMixin):
    _produces_dataframe = True   # ✅ Still output DataFrame
    _produces_artifacts = False  # ❌ Blob URIs not useful as artifacts

    def load(self) -> pd.DataFrame:
        df = self._fetch_from_blob()
        self._register_dataframe_output(df)
        # Artifact registration would be no-op (disabled)
        return df
```

#### Example 3: LLM Transform with Dual Output

```python
# BEFORE - 25 lines, metadata lost
class AzureOpenAIClient(LLMClientProtocol):
    def generate(self, *, system_prompt, user_prompt, metadata=None):
        response = self._call_api(...)
        return response  # Usage data lost!

# AFTER - 35 lines, usage metadata tracked
class AzureOpenAIClient(DualOutputMixin, LLMClientProtocol):
    _produces_dataframe = False  # ❌ LLM clients don't output DataFrames
    _produces_artifacts = True   # ✅ Output usage metadata

    def generate(self, *, system_prompt, user_prompt, metadata=None):
        response = self._call_api(...)

        # Register LLM usage artifact (NEW capability!)
        self._register_artifact_output(
            name="llm_response",
            type="llm/response",
            payload=response,  # In-memory artifact
            metadata={
                "model": self.deployment,
                "tokens_prompt": response.get("usage", {}).get("prompt_tokens", 0),
                "tokens_completion": response.get("usage", {}).get("completion_tokens", 0),
                "latency_ms": response.get("latency_ms", 0),
            },
            persist=False,  # Ephemeral unless consumed
            security_level=self.security_level,
        )

        return response
```

#### Example 4: Sink Migration (Boilerplate Reduction)

```python
# BEFORE (excel.py) - 55 lines
class ExcelResultSink(BasePlugin, ResultSink):
    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool):
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        self._last_workbook_path: str | None = None  # Manual tracking
        self._artifact_security_level: SecurityLevel | None = None

    def write(self, results, *, metadata=None):
        # ... write logic ...
        self._last_workbook_path = str(target)
        self._artifact_security_level = metadata.get("security_level")

    def produces(self) -> list[ArtifactDescriptor]:  # 8 lines
        return [
            ArtifactDescriptor(
                name="excel",
                type="file/xlsx",
                persist=True,
                alias="excel"
            ),
        ]

    def collect_artifacts(self) -> dict[str, Artifact]:  # 17 lines
        if not self._last_workbook_path:
            return {}
        artifact = Artifact(
            id="",
            type="file/xlsx",
            path=self._last_workbook_path,
            metadata={...},
            persist=True,
            security_level=self._artifact_security_level,
        )
        self._last_workbook_path = None
        self._artifact_security_level = None
        return {"excel": artifact}

# AFTER - 25 lines (54% reduction!)
class ExcelResultSink(BasePlugin, DualOutputMixin, ResultSink):
    _produces_dataframe = False  # ❌ Sinks don't output DataFrames
    _produces_artifacts = True   # ✅ Sinks always output artifacts

    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool):
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)

    def write(self, results, *, metadata=None):
        # ... write logic ...
        target = self._write_workbook(results, metadata)

        # Register artifact (ONE line replaces 25!)
        self._register_artifact_output(
            name="excel",
            type="file/xlsx",
            path=str(target),
            metadata={"sanitization": self._sanitization},
            persist=True,
            security_level=metadata.get("security_level"),
        )

    # produces() and collect_artifacts() inherited from DualOutputMixin!
```

### Inheritance Control Examples

#### Three-Level Override Cascade

```python
# Level 1: Abstract base (domain defaults)
class BaseDataSource(DualOutputMixin, DataSource):
    _produces_dataframe = True   # All datasources output DataFrames
    _produces_artifacts = True   # By default, expose source metadata

# Level 2: Concrete base (category refinement)
class BaseCSVDataSource(BaseDataSource):
    _produces_artifacts = True   # CSV files are good artifacts (keep)

class BlobDataSource(BaseDataSource):
    _produces_artifacts = False  # Blob URIs aren't useful artifacts (disable)

# Level 3: Final plugin (ultimate decision)
class CSVLocalDataSource(BaseCSVDataSource):
    # Inherits: _produces_dataframe = True, _produces_artifacts = True
    pass

class DebugBlobDataSource(BlobDataSource):
    _produces_artifacts = True   # Re-enable for debugging! (override parent)
```

#### Sink Hierarchy (DataFrame Always Disabled)

```python
# Level 1: All sinks disable DataFrame output
class BaseSink(DualOutputMixin, ResultSink):
    _produces_dataframe = False  # ❌ Sinks are terminal - no DataFrame output
    _produces_artifacts = True   # ✅ Sinks always produce artifacts

# Level 2: Specific sink types
class ExcelResultSink(BaseSink):
    # Inherits: _produces_dataframe = False (can't override - sinks are terminal)
    # Inherits: _produces_artifacts = True
    pass

class DebugSink(BaseSink):
    _produces_artifacts = False  # Debugging sink that doesn't chain
```

---

## Consequences

### Benefits

1. **Massive Boilerplate Reduction (93%)**
   - Current: 13 sinks × 40 lines = 520 lines of duplication
   - After: 13 sinks × 3 lines = 39 lines
   - **Reduction: 481 lines eliminated (93%)**

2. **Unlocks Composition Patterns**
   - **DataFrame archiving**: Sink consumes `dataframe` artifact from source
   - **Response caching**: Sink consumes `llm/response` artifacts for replay
   - **Multi-stage transforms**: Transform → analyzer → secondary transform chains
   - **Source provenance**: Track which CSV files contributed to results
   - **Cross-experiment artifacts**: Baseline produces artifacts consumed by variant

3. **Consistent Metadata Flow**
   - Security levels propagate automatically through artifacts
   - Determinism levels tracked throughout chain
   - Source schema information flows to sinks
   - LLM usage aggregation across entire experiment

4. **Developer Experience**
   - Clear pattern: "All plugins chain by default"
   - One line to register artifact vs 40 lines manual implementation
   - Inheritance control matches mental model (base sets policy, child overrides)
   - Soft enforcement (no-ops) prevents brittle code

5. **Security Integration (ADR-002)**
   - Artifact metadata carries SecurityLevel automatically
   - ArtifactPipeline enforces clearance checks (existing)
   - Provenance tracking improved (full lineage visible)
   - Audit trail enhanced (artifacts trace data flow)

6. **Backward Compatibility**
   - Existing plugins work unchanged
   - Migration is incremental (plugin by plugin)
   - No breaking changes to public APIs
   - Opt-out pattern allows gradual adoption

### Limitations / Trade-offs

**Trade-off 1: Increased Protocol Complexity**

- **Limitation**: Protocols now have dual semantics (DataFrame + artifacts)
- **Impact**: New plugin developers must understand two output types
- **Mitigation**:
  - Clear documentation with examples per plugin type
  - Template plugins demonstrating patterns
  - ADR-006 provides canonical guidance
  - Most plugins just inherit defaults (minimal burden)

**Trade-off 2: Artifact Lifecycle Management**

- **Limitation**: In-memory artifacts (DataFrames, LLM responses) need lifecycle management
- **Question**: When are in-memory artifacts cleaned up?
- **Mitigation**:
  - ArtifactStore manages lifecycle
  - `persist=False` (default) allows garbage collection after pipeline
  - `persist=True` triggers explicit serialization
  - Document lifecycle policy in artifact_pipeline.py

**Trade-off 3: Performance Overhead**

- **Limitation**: Artifact tracking adds memory/CPU overhead
- **Impact**: Every plugin now tracks outputs, even if unused
- **Mitigation**:
  - Lazy evaluation (artifacts only collected when consumed)
  - Benchmark overhead (expected <1% given existing ArtifactPipeline)
  - Opt-out available if performance critical

**Trade-off 4: Artifact Type Governance**

- **Limitation**: Need to define and govern standard artifact types
- **Impact**: Proliferation risk (plugins define custom types, fragmentation)
- **Mitigation**:
  - Central registry in `artifact_types.py`
  - Validation in ArtifactPipeline (reject unknown types)
  - Documentation for adding new types
  - Plugin review process enforces standards

### Implementation Impact

#### Phase 1: Foundation (2-3 hours)

**New Files**:

- `src/elspeth/core/base/outputs.py` - DualOutputMixin (150 lines)
- `src/elspeth/core/base/artifact_types.py` - Standard types (50 lines)

**Modified Files**:

- `src/elspeth/core/base/protocols.py` - Add produces/collect_artifacts to DataSource, TransformNode

**Tests**:

- `tests/test_dual_output_mixin.py` - Unit tests for mixin (200 lines)
- `tests/test_inheritance_control.py` - Multi-level override scenarios (150 lines)

#### Phase 2: Sink Migration (3-4 hours)

**Pattern**: Convert 13 sinks to use DualOutputMixin

**Before/After per sink**:

- Before: 40 lines manual artifact tracking
- After: 3 lines `_register_artifact_output()` call
- Time: ~15 minutes per sink

**Priority order** (high usage first):

1. ExcelResultSink
2. CsvResultSink
3. VisualAnalyticsSink
4. SignedArtifactSink
5. ReproducibilityBundleSink
6. ... (remaining 8 sinks)

**Verification**: All existing sink tests pass without modification (zero behavioral change)

#### Phase 3: Source Migration (2-3 hours)

**Pattern**: Add artifact output to 4 datasources

**Example**: CSVLocalDataSource

- Add DualOutputMixin to inheritance
- Call `_register_artifact_output()` in `load()`
- Register file path, schema, row count

**New capability unlocked**: Sinks can consume `file/csv` artifacts

#### Phase 4: Transform Migration (3-4 hours)

**Pattern**: Add artifact output to 6 LLM clients

**Example**: AzureOpenAIClient

- Add DualOutputMixin to inheritance
- Set `_produces_dataframe = False`
- Call `_register_artifact_output()` in `generate()`
- Register usage metadata, latency, model info

**New capability unlocked**: Sinks can consume `llm/response` artifacts for cost analysis

#### Phase 5: Documentation & Examples (2-3 hours)

**Updated Documentation**:

- `docs/architecture/plugin-catalogue.md` - Add "Produces" column to tables
- `docs/development/plugin-authoring.md` - Dual-output guide with examples
- `docs/architecture/artifact-chaining.md` - NEW comprehensive guide
- `CLAUDE.md` - Update plugin development patterns section

**New Tests**:

- `tests/test_universal_chaining.py` - End-to-end composition scenarios
- `tests/test_dataframe_archiving.py` - Source → DataFrame archive sink
- `tests/test_llm_response_caching.py` - Transform → response analysis sink

**Total Effort**: 12-17 hours (2-3 days)

---

## Related Documents

### ADRs

- [ADR-003](003-plugin-type-registry.md) - Central plugin type registry (plugin architecture context)
- [ADR-004](004-mandatory-baseplugin-inheritance.md) - Mandatory BasePlugin inheritance (inheritance pattern precedent)
- [ADR-002](002-security-architecture.md) - Multi-Level Security (artifact metadata carries SecurityLevel)

### Implementation

- `src/elspeth/core/pipeline/artifact_pipeline.py:1-409` - Existing artifact chaining infrastructure
- `src/elspeth/core/base/protocols.py:82-108` - Current ResultSink protocol with produces/consumes/collect_artifacts
- `src/elspeth/plugins/nodes/sinks/excel.py:290-303` - Example sink with manual artifact tracking

### Documentation

- `docs/architecture/plugin-catalogue.md` - Plugin inventory (will add "Produces" column)
- `docs/development/plugin-authoring.md` - Plugin development guide (will add dual-output section)

---

## Future Enhancements

### H1: Automatic Artifact Validation

Add schema validation for artifact metadata:

```python
class ArtifactDescriptor:
    schema: dict[str, type] | None = None  # NEW: JSON schema for metadata
```

### H2: Artifact Compression

Automatically compress large in-memory artifacts:

```python
def _register_artifact_output(self, ..., compress_threshold_mb: int = 10):
    if payload.size > threshold:
        payload = compress(payload)  # Automatic compression
```

### H3: Artifact Versioning

Track artifact schema versions for backward compatibility:

```python
class Artifact:
    schema_version: str = "1.0.0"  # NEW: Version tracking
```

### H4: Cross-Experiment Artifact Sharing

Enable artifacts from baseline experiment to flow to variant:

```yaml
experiments:
  baseline:
    sinks:
      - plugin: csv_file
        artifacts:
          produces: [{"name": "baseline_results", "persist": true}]

  variant:
    sinks:
      - plugin: comparison_report
        artifacts:
          consumes: ["@baseline_results"]  # Consume across experiments!
```

---

**Last Updated**: 2025-10-26
**Author(s)**: Architecture Team
**Status**: Proposed (awaiting review and discussion)
