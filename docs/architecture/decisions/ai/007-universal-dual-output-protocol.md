# ADR-007: Universal Dual-Output Plugin Protocol (LITE)

**Status**: PROPOSED
**Date**: 2025-10-26

## TL;DR

Every plugin produces TWO outputs with multi-level inheritance control:

1. **DataFrame output** - Data flowing through pipeline (sources/transforms)
2. **Artifact output** - Chain able metadata for composition (all plugins)

```python
class DualOutputMixin:
    """Automatic dual-output tracking for all plugins."""

    # Override at ANY inheritance level
    _produces_dataframe: bool = True   # Default ON (opt-out)
    _produces_artifacts: bool = True   # Default ON (opt-out)

    def _register_dataframe_output(self, df: pd.DataFrame):
        if not self._produces_dataframe: return
        self._output_dataframe = df

    def _register_artifact_output(self, name: str, type: str, **kwargs):
        if not self._produces_artifacts: return
        self._output_artifacts[name] = Artifact(name, type, **kwargs)
```

**Three-Level Inheritance Control**:
```python
# Level 1: Abstract base (domain defaults)
class BaseDataSource(DualOutputMixin):
    _produces_dataframe = True   # ✅ All datasources output DataFrames
    _produces_artifacts = True   # ✅ Expose source metadata

# Level 2: Concrete base (category refinement)
class BlobDataSource(BaseDataSource):
    _produces_artifacts = False  # ❌ Blob URIs not useful

# Level 3: Final plugin (ultimate decision)
class DebugBlobDataSource(BlobDataSource):
    _produces_artifacts = True   # ✅ Re-enable for debugging!
```

**Impact**: **93% boilerplate reduction** (640 lines → 48 lines across 13 sinks).

## Context

### Current State: Inconsistent Outputs

**Problem 1: Lost Metadata** - Sources discard valuable info:
```python
class CSVLocalDataSource:
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return df  # ❌ Path discarded - can't chain to "archive CSV" sink
```

**Problem 2: No Transform Chaining** - LLM metadata lost:
```python
class AzureOpenAIClient:
    def generate(self, *, system_prompt, user_prompt):
        response = self._call_api(...)
        return response  # ❌ Usage metadata lost, can't chain to cost analyzer
```

**Problem 3: Massive Boilerplate** - 13 sinks × 40 lines = **520+ lines duplicated**:
```python
# Repeated in csv_file.py, excel.py, signed.py, visual_report.py, etc.
class ExcelResultSink(BasePlugin, ResultSink):
    def __init__(self, ...):
        self._last_workbook_path: str | None = None  # Manual tracking

    def write(self, results, **kwargs):
        self._last_workbook_path = str(target)  # Manual capture

    def produces(self) -> list[ArtifactDescriptor]:  # Manual declaration
        return [ArtifactDescriptor(name="excel", type="file/xlsx", ...)]

    def collect_artifacts(self) -> dict[str, Artifact]:  # Manual construction
        return {"excel": Artifact(..., path=self._last_workbook_path, ...)}
```

**Problem 4: Prevented Composition** - Can't build:
- DataFrame archival (source DataFrames lost)
- LLM response caching (response metadata lost)
- Multi-stage chains (no chaining hooks)
- Cost analysis (usage metadata lost)

## Decision

Implement **Universal Dual-Output Protocol** where ALL plugins produce TWO outputs with multi-level inheritance control.

### Option Comparison

**Option 1: Status Quo** (rejected)
- ❌ 520+ lines duplicated boilerplate
- ❌ Sources/transforms can't expose metadata
- ❌ No composition patterns possible

**Option 2: Reflection Auto-detect** (rejected)
- ❌ "Magic" behavior - hard to debug
- ❌ Security risk (accidental attribute exposure)
- ❌ Fragile (breaks on renames)

**Option 3: Dual-Output with Inheritance** (CHOSEN)
- ✅ **93% boilerplate reduction**
- ✅ **Explicit control** - no magic
- ✅ **Multi-level inheritance** - disable at base, override in child
- ✅ **Backward compatible**
- ✅ **Unlocks composition**

## Security Integration (ADR-002/005)

### Artifact Security Level Inheritance

Artifacts inherit plugin's `security_level` by default:

```python
def _register_artifact_output(
    self,
    name: str,
    type: str,
    *,
    security_level: SecurityLevel | None = None,  # Optional override
    ...
):
    # Default to plugin's clearance
    effective_level = security_level or self.security_level

    artifact = Artifact(
        id=f"{self.__class__.__name__}_{name}",
        type=type,
        security_level=effective_level,  # ← Propagated from plugin
        ...
    )
```

### ArtifactPipeline Clearance Enforcement

```python
class ArtifactPipeline:
    def execute_sink(self, sink: ResultSink, artifacts: dict[str, Artifact]):
        for artifact in artifacts.values():
            # Check 1: Sink must have clearance for artifact
            if artifact.security_level > sink.security_level:
                raise SecurityValidationError(
                    f"Sink {sink} (clearance: {sink.security_level}) "
                    f"cannot process artifact (classification: {artifact.security_level})"
                )

            # Check 2: Frozen plugins reject downgrade
            if artifact.security_level < sink.security_level and not sink.allow_downgrade:
                raise SecurityValidationError(
                    f"Frozen sink {sink} cannot operate below clearance (ADR-005)"
                )
```

### MLS Propagation Rules

- **Explicit downgrade policy**: Every plugin calls `BasePlugin.__init__(..., allow_downgrade=...)`
- **Artifact routing**: Propagates `SecurityLevel`, invokes `validate_compatible_with()` every hop
- **Frozen plugins**: `allow_downgrade=False` refuses artifacts with lower operating level
- **Auditability**: Artifact metadata includes classification, provenance for chain of custody

## Implementation

### DualOutputMixin

**File**: `src/elspeth/core/base/dual_output.py` (NEW)

```python
class DualOutputMixin:
    """Provides dual-output tracking for all plugins (ADR-007)."""

    # Class attributes - override at ANY inheritance level
    _produces_dataframe: bool = True   # Default: ON (opt-out)
    _produces_artifacts: bool = True   # Default: ON (opt-out)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._output_dataframe: pd.DataFrame | None = None
        self._output_artifacts: dict[str, Artifact] = {}

    def _register_dataframe_output(self, df: pd.DataFrame) -> None:
        """Register DataFrame for pipeline flow."""
        if not self._produces_dataframe:
            return  # No-op if disabled
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
        security_level: SecurityLevel | None = None,
    ) -> None:
        """Register artifact for chaining."""
        if not self._produces_artifacts:
            return  # No-op if disabled

        artifact = Artifact(
            id="",  # Set by ArtifactStore
            type=type,
            path=path,
            payload=payload,
            metadata=metadata or {},
            persist=persist,
            security_level=security_level or self.security_level,  # Inherit clearance
        )
        self._output_artifacts[name] = artifact

    def get_output_dataframe(self) -> pd.DataFrame | None:
        """Retrieve DataFrame output (if enabled)."""
        return self._output_dataframe if self._produces_dataframe else None

    def collect_artifacts(self) -> dict[str, Artifact]:
        """Retrieve artifacts (if enabled)."""
        return dict(self._output_artifacts) if self._produces_artifacts else {}

    def produces(self) -> list[ArtifactDescriptor]:
        """Auto-generate artifact descriptors from registered artifacts."""
        if not self._produces_artifacts:
            return []

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

## Migration Examples

### Before: Manual Boilerplate (40 lines per sink)

```python
class ExcelResultSink(BasePlugin, ResultSink):
    def __init__(self, ...):
        super().__init__(...)
        self._last_workbook_path: str | None = None

    def write(self, results, **kwargs):
        # ... write logic ...
        self._last_workbook_path = str(target_path)

    def produces(self) -> list[ArtifactDescriptor]:
        return [ArtifactDescriptor(
            name="excel",
            type="file/xlsx",
            persist=True,
            security_level=self.security_level,
        )]

    def collect_artifacts(self) -> dict[str, Artifact]:
        if not self._last_workbook_path:
            return {}
        return {
            "excel": Artifact(
                id="",
                type="file/xlsx",
                path=self._last_workbook_path,
                persist=True,
                security_level=self.security_level,
            )
        }
```

### After: Automatic via DualOutputMixin (3 lines)

```python
class ExcelResultSink(DualOutputMixin, BasePlugin, ResultSink):
    def write(self, results, **kwargs):
        # ... write logic ...
        self._register_artifact_output(
            "excel",
            "file/xlsx",
            path=str(target_path),
            persist=True,
        )
        # produces() and collect_artifacts() auto-generated!
```

**Savings**: 40 lines → 3 lines per sink × 13 sinks = **481 lines eliminated** (92% reduction)

### Datasource Migration

**Before**:
```python
class CSVLocalDataSource(BasePlugin, DataSource):
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        return df  # ❌ Path lost
```

**After**:
```python
class CSVLocalDataSource(DualOutputMixin, BasePlugin, DataSource):
    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)

        # Register DataFrame
        self._register_dataframe_output(df)

        # Register source metadata for chaining
        self._register_artifact_output(
            "source_file",
            "file/csv",
            path=str(self.path),
            persist=False,  # Transient metadata
        )

        return df  # ✅ Artifact available for "archive source CSV" sink
```

### Transform Migration

**Before**:
```python
class AzureOpenAIClient(LLMClientProtocol):
    def generate(self, *, system_prompt, user_prompt):
        response = self._call_api(...)
        return response  # ❌ Usage metadata lost
```

**After**:
```python
class AzureOpenAIClient(DualOutputMixin, LLMClientProtocol):
    _produces_dataframe = False  # Transforms don't output DataFrames

    def generate(self, *, system_prompt, user_prompt):
        response = self._call_api(...)

        # Register LLM response for chaining
        self._register_artifact_output(
            "llm_response",
            "llm/response",
            payload=response,
            metadata={
                "model": self.model,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "cost_usd": self._calculate_cost(response.usage),
            },
            persist=False,
        )

        return response  # ✅ Usage available for cost analyzer
```

## Inheritance Control Patterns

### Pattern 1: Disable at Base, Enable in Child

```python
# Base: No artifacts by default
class BaseAggregator(DualOutputMixin, BasePlugin):
    _produces_artifacts = False  # Most aggregators don't need artifacts

# Child: Re-enable for specific use case
class DebugAggregator(BaseAggregator):
    _produces_artifacts = True   # Enable for debugging

    def aggregate(self, results):
        summary = super().aggregate(results)
        self._register_artifact_output(
            "debug_summary",
            "debug/aggregation",
            payload=summary,
        )
        return summary
```

### Pattern 2: Transform Chains (No DataFrames)

```python
class BaseTransform(DualOutputMixin, BasePlugin):
    _produces_dataframe = False  # Transforms work on dicts, not DataFrames
    _produces_artifacts = True   # But artifacts for metadata chaining
```

### Pattern 3: Sink-Only Artifacts

```python
class BaseSink(DualOutputMixin, BasePlugin, ResultSink):
    _produces_dataframe = False  # Sinks don't output DataFrames
    _produces_artifacts = True   # But produce file/report artifacts
```

## Consequences

### Benefits

- **93% boilerplate reduction** (640 → 48 lines)
- **Consistent pattern** across all plugin types
- **Unlocks composition** (DataFrame archival, LLM caching, multi-stage chains)
- **Security metadata flows** automatically (ADR-002 integration)
- **Multi-level control** - fine-grained enable/disable
- **Backward compatible** - existing code works unchanged
- **Explicit, not magic** - clear semantics

### Limitations

- **Complexity increase** - Two outputs vs one
- **Lifecycle management** - When are in-memory artifacts cleaned up?
- **Standard types needed** - Taxonomy for artifact types
- **Memory overhead** - All plugins track artifacts (even if disabled → no-op)

### Mitigations

- **Documentation** - Examples for each plugin type
- **ArtifactStore** - Manages lifecycle, respects `persist` flag
- **Taxonomy** - `core/base/artifact_types.py` defines standard types
- **Soft enforcement** - Disabled outputs = no-op (minimal overhead)

## Implementation Impact

**New Files**:
- `src/elspeth/core/base/dual_output.py` - DualOutputMixin
- `src/elspeth/core/base/artifact_types.py` - Standard artifact taxonomy

**Modified Files** (~15-20 plugins):
- Add `DualOutputMixin` to inheritance
- Add `_register_artifact_output()` calls
- Remove manual `produces()`/`collect_artifacts()` (auto-generated)

**Migration Effort**:
- ~15 datasources: +5 lines each (register source metadata)
- ~10 transforms: +5 lines each (register LLM/transform metadata)
- ~13 sinks: -35 lines each (remove boilerplate)
- **Net**: -481 lines total

**Timeline**:
- Week 1: DualOutputMixin implementation + tests
- Week 2: Datasource migration (15 files)
- Week 3: Transform migration (10 files)
- Week 4: Sink migration (13 files) + integration tests

## Related

ADR-002 (MLS), ADR-003 (Plugin registry), ADR-004 (BasePlugin), ADR-005 (Frozen plugins)

---
**Last Updated**: 2025-10-26
