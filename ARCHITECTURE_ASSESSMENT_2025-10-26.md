# Elspeth Architecture Assessment & Roadmap

**Assessment Date**: 2025-10-26
**Scope**: Pre-1.0 Architecture Review, Gap Analysis, and Strategic Direction
**Status**: Final - Ready for Implementation
**Reviewer**: Claude (Architecture Analysis)

---

## Executive Summary

### Overall Assessment

Elspeth's architecture demonstrates **exceptional security-first design** with comprehensive documentation (147 markdown files, ~3,276 lines of ADRs) and battle-tested refactoring methodology (100% success rate, 85%+ complexity reduction). The codebase is well-positioned for 1.0 release with intentional architectural evolution from security hardening to composability enablement.

**Overall Rating**: ⭐⭐⭐⭐ **4.4/5.0** - Excellent architecture with minor gaps

| Dimension | Rating | Assessment |
|-----------|--------|------------|
| Documentation Quality | ⭐⭐⭐⭐⭐ 5/5 | Exceptional depth, publication-worthy |
| Security Design | ⭐⭐⭐⭐⭐ 5/5 | Consistent security-first application |
| Separation of Concerns | ⭐⭐⭐⭐⭐ 5/5 | Clear layering, no violations |
| ADR Coverage | ⭐⭐⭐⭐ 4/5 | Strong but 5 patterns undocumented |
| Consistency | ⭐⭐⭐ 3/5 | Namespace migration incomplete |
| Completeness | ⭐⭐⭐⭐ 4/5 | Comprehensive but 3 critical gaps |
| Maintainability | ⭐⭐⭐⭐⭐ 5/5 | Refactoring methodology world-class |

### Key Findings

**Identified**: 17 architectural gaps requiring attention before 1.0 release
- **5 P0 gaps** (blocking, 13.5-16.5 hours total effort)
- **6 P1 gaps** (next sprint, 13-18 hours)
- **6 P2 gaps** (post-1.0 polish, 8.5-12.5 hours)

**Critical Discovery**: The artifact lifecycle decision revealed a fundamental architectural insight—current "sinks" are actually **artifact transforms** that should compose with **file write sinks**. This enables:
- Separation of data shape transformation from I/O
- User-extensible file writers for custom destinations (legacy mainframes, proprietary systems)
- Logical routing plugins (AND/OR/IF/TRY/WHEN/CIRCUIT_BREAKER/THROTTLE/TEE)
- True composability: `ExcelTransform` → `IfRouting` → `TryFallback` → `LocalFileWriter`

### 1.0 Release Philosophy

> **"Act the way we're meant to be"**

**1.0 Release Gates**:
- ✅ **Function Complete**: All core features implemented (sources, transforms, sinks, artifact pipeline)
- ✅ **Security Complete**: All security ADRs implemented (ADR-001 through 005, MLS enforcement)
- ✅ **Zero Intentional Debt**: No "we'll fix this later" architectural compromises
- ⚠️ **Quality Acceptable**: Minor lint/complexity warnings acceptable, but core behavior correct

### Strategic Direction (6 Key Decisions)

| Decision Area | Direction | Impact |
|--------------|-----------|--------|
| **Namespace Migration** | Clean sweep - migrate ALL docs to new structure | Zero technical debt |
| **Registry Consolidation** | Investigate and consolidate duplicate directories | Code organization |
| **Artifact Lifecycle** | **Pass-through model** - immediate hand-off | **CRITICAL - Architecture change** |
| **ADR Numbering** | Rename historical ADRs to A001, A002 | Documentation clarity |
| **Observability** | ADR-012 for global policy, middleware for environment | Compliance foundation |
| **1.0 Criteria** | Function + Security complete, zero intentional debt | Release gates |

### Implementation Roadmap Summary

**P0 (Before 1.0)**: 13.5-16.5 hours (2 days)
- ADR-007 "Registry Architecture" (3-4h)
- ADR-009 "Pass-Through Lifecycle & Routing" (7-8h) - **Expanded scope**
- Namespace migration cleanup (1-2h)
- Registry directory consolidation (1h)
- Rename historical ADRs (30m)
- Security terminology glossary (1h)

**P1 (Next Sprint)**: 13-18 hours (2-3 days)
- ADR-008 "Configuration Composition" (3-4h)
- ADR-010 "Error Classification & Recovery" (3-4h)
- ADR-011 "Testing Strategy" (2-3h)
- ADR-012 "Observability Policy" (2-3h)
- Orchestration layers documentation (2h)
- PluginContext design documentation (1-2h)

**P2 (Post-1.0 Polish)**: 8.5-12.5 hours (1-2 days)
- Advanced routing patterns (WHEN/CIRCUIT_BREAKER/THROTTLE/TEE)
- Deployment architecture guide
- Data retention policy
- Documentation cleanup

---

## Part 1: Architectural Strengths (Preserve These!)

### 1.1 Security-First Design Consistently Applied

**Evidence of Excellence**:

Elspeth demonstrates **exceptional discipline** in applying security-first principles (ADR-001) across all architectural layers:

1. **Prompt Rendering** (security-first):
   - Jinja2 StrictUndefined (no silent failures)
   - Sandboxed templates (no arbitrary code execution)
   - Missing field detection (fail-fast)

2. **Artifact Pipeline** (security-first):
   - Clearance checks before artifact consumption
   - Security level propagation automatic
   - Topological sort prevents dependency violations

3. **Error Handling** (security-first):
   - ADR-001: Fail-closed principle
   - ADR-005: SecurityCriticalError for invariant violations
   - No fallback that bypasses security

4. **Dependency Management** (security-first):
   - Always use lockfiles with `--require-hashes`
   - Never install from unpinned ranges
   - Supply chain attack mitigation

**Assessment**: ✅ Security-first principle applied at EVERY architectural decision point.

### 1.2 ADR Evolution Shows Intentional Maturity

**Timeline of Architectural Maturity**:

```
Phase 1: Security Foundation (ADR-001 through 002-A)
├─ ADR-001: Design Philosophy (Security-first priority hierarchy)
├─ ADR-002: Multi-Level Security (Bell-LaPadula MLS enforcement)
└─ ADR-002-A: Trusted Container Model (ClassifiedDataFrame immutability)

Phase 2: Security Mechanics (ADR-003 through 005)
├─ ADR-003: Plugin Type Registry (Validation completeness)
├─ ADR-004: Mandatory BasePlugin (Nominal typing enforcement)
└─ ADR-005: Security-Critical Exceptions (Fail-loud policy)

Phase 3: Composability (ADR-006)
└─ ADR-006: Universal Dual-Output (DataFrame + Artifact chaining)
    ↳ NEW THEME: Transition from security hardening → composability unlocking
```

**Insight**: This architectural evolution is **intentional and well-paced**:
1. First: **Security foundation** (non-negotiable)
2. Then: **Security mechanics** (enforcement mechanisms)
3. Finally: **Composability** (unlock value while maintaining security)

**Assessment**: ✅ Rare in open-source - most projects skip security to focus on features!

### 1.3 Documentation Depth is Exceptional

**Evidence**:
- **147 markdown files** (all updated in last 30 days - active maintenance!)
- **~3,276 lines of ADRs** alone (not counting other docs)
- **Architecture overview** with line-number citations (e.g., "src/file.py:192")
- **Mermaid diagrams** for complex flows
- **CLAUDE.md** for AI assistant guidance (393 lines)
- **Refactoring methodology** (69.5 KB guide - **publication-worthy**)

**Comparison to Industry**:
- Typical open-source: README + scattered docs
- Well-documented: README + architecture overview
- **Elspeth**: README + comprehensive architecture + ADRs + methodology + compliance docs

**Assessment**: ✅ **Publication-worthy**. Consider submitting refactoring methodology to IEEE Software or ACM Queue.

### 1.4 Refactoring Methodology is Battle-Tested

**Success Metrics**:
- PR #10 (runner.py): 73 → 11 complexity (85% reduction)
- PR #11 (suite_runner.py): 69 → 8 complexity (88.4% reduction)
- Both: 100% test pass rate, zero behavioral changes, zero regressions
- Coverage: Maintained or improved in both cases

**5-Phase Process**:
1. **Phase 0 (35% of time)**: Build comprehensive test safety net
2. **Phase 1-3 (55%)**: Extract helpers ONE AT A TIME, test after EACH
3. **Phase 4 (10%)**: Documentation and cleanup

**Key Innovation**: "Extract ONE method, test, commit" discipline
- Prevents "big bang" refactoring failures
- Enables fast rollback (`git reset --hard HEAD~1`)
- Builds confidence incrementally

**Assessment**: ✅ **Major architectural asset** and competitive advantage. This is world-class.

### 1.5 Clear Separation of Concerns

**Layered Architecture**:

```
┌─────────────────────────────────────────┐
│ CLI Layer (user interface)             │
├─────────────────────────────────────────┤
│ Orchestration Layer                     │
│ - SuiteRunner (multi-experiment)        │
│ - ExperimentRunner (single experiment)  │
│ - Orchestrator (component binding)      │
├─────────────────────────────────────────┤
│ Pipeline Layer                          │
│ - ArtifactPipeline (dependency order)   │
│ - Middleware chain (LLM wrapping)       │
├─────────────────────────────────────────┤
│ Registry Layer (plugin management)      │
│ - BasePluginRegistry[T]                 │
│ - DataSourceRegistry, LLMRegistry, etc. │
├─────────────────────────────────────────┤
│ Plugin Layer (extensibility)            │
│ - Sources, Transforms, Sinks            │
└─────────────────────────────────────────┘
```

**Assessment**: ✅ No layer violations observed - each layer has clear responsibilities!

---

## Part 2: Critical Gaps & Remediation

### 2.1 P0 Gaps (Blocking 1.0 Release)

#### GAP-P0-1: Registry Architecture Pattern Undocumented

**Status**: ✅ Implemented, 📋 Documented in code, ❌ No ADR

**Finding**:
- `src/elspeth/core/registries/base.py` implements `BasePluginRegistry[T]` generic
- Phase 2 registry migration **COMPLETE** (historical/004-complete-registry-migration.md)
- All plugin types use unified framework (DataSourceRegistry, LLMClientRegistry, SinkRegistry, etc.)
- **BUT**: ADR-003 "Central Plugin Type Registry" doesn't cover the ACTUAL registry pattern

**Impact**: **HIGH** - Security validation completeness (ADR-003) depends on registry pattern

**Remediation**: Create **ADR-007 "Unified Registry Pattern"**
- Document BasePluginRegistry[T] generic design
- Schema validation, security level stamping, type safety
- Decorator pattern vs factory functions
- Plugin registration lifecycle

**Effort**: 3-4 hours

---

#### GAP-P0-2: Artifact Lifecycle & Transform Composition (CRITICAL)

**Status**: ⚠️ Partially Implemented, ❌ Undefined Policy, 🔍 **Architectural Discovery**

**Finding**:
During architectural review, a fundamental insight emerged: current "sinks" conflate two concerns:
1. **Artifact transformation** (DataFrame → Excel/CSV/JSON)
2. **File writing** (Artifact → disk/blob/S3)

This violates separation of concerns and prevents user extensibility.

**Critical Discovery**: The true division line is:
- **Data Transforms**: Change **value** of data (LLM predictions, filters)
- **Artifact Transforms**: Change **shape** of data (Excel generator, JSON serializer)
- **File Write Sinks**: Persist artifacts to **destinations** (local, blob, S3, **custom**)

**Architectural Implications**:
1. **Sink Decomposition**:
   - Before: `ExcelResultSink` (generate + write)
   - After: `ExcelTransform` (generate) → `BaseFileWriteSink` (write)

2. **User Extensibility**:
   - Users can implement custom file writers for legacy systems
   - Example: 13-year-old mainframe from bankrupt vendor
   - No forking required - inherit from `BaseFileWriteSink`

3. **Logical Routing Plugins**:
   - AND/OR/IF/TRY (core routing patterns)
   - WHEN/CIRCUIT_BREAKER/THROTTLE/TEE (advanced patterns)
   - Enable enterprise topologies (redundant multi-region, load balancing)

**Impact**: **CRITICAL** - Blocks ADR-006 implementation, enables composability

**Remediation**: Create **ADR-009 "Pass-Through Artifact Lifecycle & Transform Composition"**
- Three-tier architecture (Transform → Base → Concrete)
- BaseFileWriteSink hierarchy (ADR-004 security bones)
- Core logical routing plugins (AND/OR/IF/TRY)
- Pass-through lifecycle semantics

**Effort**: 7-8 hours (expanded scope)

**See Part 3** for detailed architectural patterns.

---

#### GAP-P0-3: Namespace Migration Incomplete

**Status**: ⚠️ Inconsistent References

**Finding**:
Documentation references **both** old (`plugins/datasources/`) and new (`plugins/nodes/sources/`) paths:
- architecture-overview.md line 21: NEW paths (correct)
- Footnotes: OLD paths (incorrect)
- component-diagram.md: "legacy diagram labels preserved"

**Impact**: **MEDIUM** - Confusing for new developers, broken links

**Decision**: **Clean sweep** - migrate ALL documentation to new paths
> "Pre-1.0, no sloppy dual references. We're agile(esque) but that doesn't mean we want to look sloppy."

**Remediation**:
- Update all footnotes and examples to `plugins/nodes/` structure
- Remove old path references (except historical context)
- Zero dual references

**Effort**: 1-2 hours

---

#### GAP-P0-4: Dual Registry Directories

**Status**: ⚠️ Unclear Purpose

**Finding**:
Two registry directories exist:
- `/src/elspeth/core/registries/` (plural)
- `/src/elspeth/core/registry/` (singular)

**Impact**: **LOW** - Code navigation confusion

**Decision**: **Consolidate** - no legacy debt
> "Same reason [as namespace migration] - legacy debt. Nail it."

**Remediation**:
- Investigate both directories
- Consolidate to single structure (likely `registries/` plural)

**Effort**: 1 hour

---

#### GAP-P0-5: ADR Numbering Collision

**Status**: ⚠️ Ambiguous References

**Finding**:
ADR numbers reused:
- ADR-003 (current): "Central Plugin Type Registry" (proposed)
- ADR-003 (historical): "Remove Legacy Code" (completed)
- ADR-004 (current): "Mandatory BasePlugin" (proposed)
- ADR-004 (historical): "Complete Registry Migration" (completed)

**Impact**: **LOW** - Documentation ambiguity

**Decision**: **Rename historical ADRs with 'A' prefix**
> "I propose we rename the archived ones A001 and A002 rather than keeping 3 and 4."

**Remediation**:
- Rename `historical/003-*` → `historical/A001-*`
- Rename `historical/004-*` → `historical/A002-*`
- Update README.md ADR index
- Document naming convention

**Effort**: 30 minutes

---

#### GAP-P0-6: Security Terminology Inconsistency

**Status**: ⚠️ Conceptual Ambiguity

**Finding**:
"security_level", "classification", "clearance" used inconsistently:
- ADR-002: "security_level" (e.g., `SecurityLevel.SECRET`)
- ADR-002-A: "classification" (e.g., `ClassifiedDataFrame.classification`)
- Some docs: "clearance" vs "security level" interchangeably

**Impact**: **MEDIUM** - Conceptual confusion for developers

**Conceptual Model** (inferred):
```python
# Plugin's CLEARANCE (what it CAN handle)
plugin.security_level = SecurityLevel.SECRET

# Data's CLASSIFICATION (what protection it REQUIRES)
data.classification = SecurityLevel.SECRET

# Access control rule (Bell-LaPadula "no read up"):
if data.classification > plugin.security_level:
    raise SecurityValidationError("Plugin lacks clearance")
```

**Remediation**: Create **Security Terminology Glossary**
- `security_level`: Plugin's **clearance** (capability)
- `classification`: Data's **label** (protection required)
- `operating_level`: Pipeline's **envelope** (minimum across components)
- `clearance`: **Avoid** in docs (use security_level)

**Effort**: 1 hour

---

### 2.2 P1 Gaps (Next Sprint)

#### GAP-P1-1: Configuration Merge & Validation Pipeline

**Status**: ✅ Implemented, 📚 Documented, ❌ No ADR

**Finding**:
- `docs/architecture/configuration-security.md` (25 KB) documents merge order
- Precedence: Suite defaults → Prompt packs → Experiment overrides
- Deep merge semantics non-obvious
- Validation chain spans 3 modules

**Impact**: **MEDIUM** - User experience, debugging efficiency

**Remediation**: Create **ADR-008 "Configuration Composition & Validation"**
- Explicit precedence rules
- Deep merge vs shallow replace semantics
- Fail-fast validation at each layer

**Effort**: 3-4 hours

---

#### GAP-P1-2: Error Handling & Recovery Strategy

**Status**: ⚠️ Partially Covered (ADR-005), ❌ Incomplete

**Finding**:
- ADR-005 covers **security errors only** (SecurityCriticalError vs SecurityValidationError)
- **Missing**: Non-security error taxonomy
  - DataSource failures (blob unavailable, schema mismatch)
  - LLM failures (rate limits, timeouts, bad JSON)
  - Sink failures (disk full, permission denied)
- `on_error` policy exists but semantics not formalized

**Impact**: **MEDIUM-HIGH** - Resilience, user experience

**Remediation**: Create **ADR-010 "Error Classification & Recovery"**
- Error taxonomy: Security, Transient, Permanent, Fatal
- `on_error` policy semantics (abort/skip/log)
- Retry strategy (exponential backoff, max retries)
- Checkpoint recovery

**Effort**: 3-4 hours

---

#### GAP-P1-3: Testing Strategy & Quality Gates

**Status**: ✅ Implemented, 📋 Documented, ❌ No ADR

**Finding**:
- `docs/development/testing-overview.md` exists
- Test markers implemented (`@pytest.mark.integration`, `@pytest.mark.slow`)
- Coverage gates via SonarQube
- Mutation testing used in refactoring methodology
- **BUT**: No formal architectural decision on requirements

**Impact**: **MEDIUM** - Quality assurance, contributor onboarding

**Remediation**: Create **ADR-011 "Testing Strategy & Quality Gates"**
- Coverage requirements by component type (security: >90%, core: >80%, plugins: >70%)
- Test pyramid (70% unit, 25% integration, 5% e2e)
- Quality gates (all tests pass, MyPy clean, Ruff clean)

**Effort**: 2-3 hours

---

#### GAP-P1-4: Observability Architecture

**Status**: ✅ Implemented, ❌ No Governance

**Finding**:
- Audit logging implemented (`docs/architecture/audit-logging.md`)
- Telemetry middleware (Azure ML)
- Health monitoring, cost tracking
- **BUT**: No ADR covering observability architecture

**Impact**: **MEDIUM** - Compliance, security visibility

**Decision**: **Dual approach** - ADR for global policy, middleware for environment
> "Observability was originally left to middleware as it's environment specific, but all 'global observability questions' should be centralised in an ADR."

**Remediation**: Create **ADR-012 "Global Observability Policy"**
- What MUST be logged (security events, data access)
- What MUST NOT be logged (PII, classified content)
- Retention policy requirements
- Compliance obligations

**Effort**: 2-3 hours

---

#### GAP-P1-5: Orchestration Layer Relationships

**Status**: ⚠️ Undocumented

**Finding**:
Three orchestration layers, relationships unclear:
- `ExperimentOrchestrator` (component binding)
- `ExperimentRunner` (single experiment execution)
- `ExperimentSuiteRunner` (multi-experiment coordination)

**Impact**: **MEDIUM** - Developer onboarding

**Remediation**: Add **Orchestration Layers** section to architecture-overview.md
- Mermaid sequence diagram: CLI → SuiteRunner → Runner → Orchestrator → Plugins
- Responsibility boundaries

**Effort**: 2 hours

---

#### GAP-P1-6: PluginContext Propagation

**Status**: ⚠️ Critical but Undocumented

**Finding**:
- `plugin-catalogue.md`: "All built-in plugins receive PluginContext"
- Contains: `security_level`, `run_id`, `audit_logger`
- Propagates through entire plugin stack
- **BUT**: No ADR or architecture doc explaining design

**Impact**: **MEDIUM** - Plugin developer guidance

**Remediation**: Add **PluginContext Design** section to plugin-security-model.md
- Required vs optional fields
- Immutability contract
- Lifecycle (creation → destruction)
- Security considerations

**Effort**: 1-2 hours

---

### 2.3 P2 Gaps (Post-1.0 Polish)

#### GAP-P2-1: Middleware Ordering & Composition

**Finding**: Middleware chain order undocumented (Audit → Shield → ContentSafety → Health → AzureEnv → LLM)

**Remediation**: Document ordering rules and customization in middleware-lifecycle.md

**Effort**: 1-2 hours

---

#### GAP-P2-2: "Update 2025-10-12" Annotations Clutter

**Finding**: 50+ inline update annotations reduce readability

**Remediation**: Option A (recommended) - Move to CHANGELOG.md, remove annotations

**Effort**: 2-3 hours

---

#### GAP-P2-3: Deployment Architecture

**Finding**: Container signing documented, deployment topology not

**Remediation**: Create `docs/operations/deployment-guide.md` (supported targets, resource requirements)

**Effort**: 3-4 hours

---

#### GAP-P2-4: Data Retention & Cleanup Policy

**Finding**: Logs have retention policy, outputs don't

**Remediation**: Create `docs/operations/data-retention-policy.md`

**Effort**: 1-2 hours

---

#### GAP-P2-5: Prompt Hygiene Terminology

**Finding**: "Prompt rendering" vs "Prompt hygiene" may be conflated

**Remediation**: Clarify in security-controls.md

**Effort**: 30 minutes

---

#### GAP-P2-6: Advanced Routing Patterns

**Finding**: WHEN/CIRCUIT_BREAKER/THROTTLE/TEE patterns identified but not implemented

**Remediation**: Create ADR-013 "Advanced Routing Patterns" (post-1.0)

**Effort**: 6-8 hours (implementation + documentation)

---

## Part 3: Extended Architecture Patterns

### 3.1 Three-Tier Plugin Architecture

The pass-through artifact lifecycle decision requires **three-tier architecture** for complete extensibility:

#### Tier 1: Artifact Transforms (Shape Change)

**Purpose**: Convert DataFrame → Artifact (no I/O)

**Examples**:
- `ExcelTransform`: DataFrame → Excel workbook artifact
- `CsvTransform`: DataFrame → CSV artifact
- `JsonTransform`: DataFrame → JSON artifact
- `MarkdownTransform`: Results → Markdown report artifact

**Key Properties**:
- No file I/O (pure transformation)
- Produces Artifact objects
- Reusable across multiple destinations

**Example**:
```python
class ExcelTransform(BasePlugin, ResultSink):
    """Transform DataFrame into Excel workbook artifact.

    No file I/O - pure transformation.
    Compose with BaseFileWriteSink for persistence.
    """

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        # Generate Excel workbook in memory
        workbook = self._create_workbook(results)

        # Create artifact (no file I/O!)
        artifact = Artifact(
            id=f"excel_{uuid.uuid4()}",
            type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            data=workbook,  # In-memory workbook
            metadata=metadata,
            security_level=self.security_level,
        )

        # Hand off to next stage
        self._output_artifact = artifact
```

---

#### Tier 2: BaseFileWriteSink (Abstract Persistence)

**Purpose**: Define common interface for artifact persistence

**Design Pattern**: ADR-004 "Security Bones" - concrete security enforcement in base class

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
        # Security clearance check (concrete implementation)
        artifacts = self._get_artifacts_from_results(results)
        for artifact in artifacts:
            if artifact.security_level > self.security_level:
                raise SecurityValidationError(
                    f"Sink lacks clearance for {artifact.security_level} data"
                )

        # Delegate to subclass implementation
        self.write_artifacts(artifacts, metadata=metadata)

        # Audit logging (concrete implementation)
        if self.plugin_logger:
            self.plugin_logger.log_event("artifacts_written", count=len(artifacts))

    @abstractmethod
    def write_artifacts(self, artifacts: list[Artifact], *, metadata: dict[str, Any] | None) -> None:
        """Write artifacts to destination.

        Subclasses implement destination-specific logic.
        """
        pass
```

**Why This Matters**:
> "We need to facilitate users creating their own 'special purpose' plugins (including writing to some bizarre mainframe solution they bought 13 years ago from a company that has gone bankrupt)."

**Users MUST be able to implement custom file writers without forking Elspeth.**

---

#### Tier 3: Concrete File Writers (Destination-Specific)

**Purpose**: Implement destination-specific persistence logic

**Built-in Implementations**:

1. **LocalFileWriteSink**: Local filesystem
   - Atomic writes via `safe_atomic_write()`
   - Path validation via `resolve_under_base()`
   - Configurable base directory

2. **AzureBlobWriteSink**: Azure Blob Storage
   - Managed identity authentication
   - Container-level security
   - Async upload support

3. **S3WriteSink**: AWS S3
   - IAM role authentication
   - Server-side encryption
   - Multi-part upload for large files

**User-Extensible Examples**:

1. **LegacyMainframeWriteSink**: 13-year-old mainframe
   ```python
   class LegacyMainframeWriteSink(BaseFileWriteSink):
       """Write to legacy mainframe via COBOL interface.

       System: BIZARRESYS V2 (vendor: DEFUNCT_CORP, bankrupt 2012)
       Protocol: Proprietary binary over TCP/390
       """

       def write_artifacts(self, artifacts: list[Artifact], *, metadata=None) -> None:
           # User's custom mainframe integration
           for artifact in artifacts:
               self._cobol_interface.send(artifact.data)
   ```

2. **SharePointWriteSink**: Corporate SharePoint
3. **SFTPWriteSink**: Secure FTP to partner systems
4. **EncryptedArchiveWriteSink**: PGP-encrypted archives for compliance

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

### 3.2 Core Logical Routing Plugins

#### Pattern 1: AND (Fan-Out)

**Purpose**: Write artifact to **ALL destinations simultaneously**

**Use Cases**:
- Redundancy: Write to local AND cloud backup
- Multi-cloud: Write to Azure AND AWS AND GCP
- Compliance: Write to production AND audit archive AND DR site

**Implementation**:
```python
class AndRoutingSink(BasePlugin, ResultSink):
    """Route artifact to ALL configured destinations."""

    def __init__(self, destinations: list[BaseFileWriteSink], *, security_level: SecurityLevel):
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

#### Pattern 2: OR (Load Balancing)

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

#### Pattern 3: IF (Conditional Routing)

**Purpose**: Route artifact to **different destinations based on conditions**

**Use Cases**:
- Security-based routing: SECRET → encrypted storage, UNCLASSIFIED → regular
- Size-based routing: Large files → blob, small → database
- Content-based routing: PII detected → compliance archive
- Regional routing: EU data → EU region, US data → US region

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

#### Pattern 4: TRY (Fallback Chain)

**Purpose**: Attempt primary destination, **fall back to secondary on failure**

**Use Cases**:
- Network resilience: Try cloud, fall back to local on network failure
- Multi-cloud failover: Try Azure, fall back to AWS, fall back to local
- Availability prioritization (ADR-001 priority #3)

**Implementation**:
```python
class TryFallbackSink(BasePlugin, ResultSink):
    """Resilient routing with fallback chain."""

    def __init__(self, destinations: list[BaseFileWriteSink], *, security_level: SecurityLevel):
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

#### Pattern 5: Composite AND/OR (Complex Topologies)

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

### 3.3 Advanced Logical Routing Plugins (Post-1.0)

**Summary Table**:

| Pattern | Purpose | Terminating? | Primary Use Case |
|---------|---------|--------------|------------------|
| **WHEN** (guard) | Conditional write | ✅ Yes | Selective writes, cost control |
| **CIRCUIT_BREAKER** | Fault tolerance | ✅ Yes | External API protection |
| **THROTTLE** | Rate limiting | ✅ Yes | API rate limits, cost control |
| **TEE** (audit) | Side effect + pass-through | ❌ No | Audit trail, monitoring |

**WHEN Pattern** (Conditional Filter):
```python
class WhenGuardSink(BasePlugin, ResultSink):
    """Only write if condition met."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        if self.condition(results, metadata):
            self.destination.write(results, metadata=metadata)
        # else: Silent no-op (guard failed)
```

**Use Case**: Only write failed experiments to audit storage (cost reduction)

---

**CIRCUIT_BREAKER Pattern** (Prevent Cascade Failures):
```python
class CircuitBreakerSink(BasePlugin, ResultSink):
    """Circuit breaker with CLOSED/OPEN/HALF_OPEN states."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        if self.state == "OPEN":
            raise CircuitOpenError("Destination unhealthy")

        try:
            self.destination.write(results, metadata=metadata)
            self._on_success()
        except Exception:
            self._on_failure()
            raise
```

**Use Case**: Stop calling rate-limited external API, detect failures early

---

**THROTTLE Pattern** (Rate Limiting):
```python
class ThrottleSink(BasePlugin, ResultSink):
    """Rate-limit writes (token bucket, fixed window, sliding window)."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        self._wait_if_rate_exceeded()  # Block until token available
        self.destination.write(results, metadata=metadata)
```

**Use Case**: Respect external API rate limits (max 100 writes/minute)

---

**TEE Pattern** (Side-Effect + Pass-Through):
```python
class TeeAuditSink(BasePlugin, ResultSink):
    """Write to side-effect destination AND pass downstream."""

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        # Side effect (best-effort)
        try:
            self.side_effect.write(results, metadata=metadata)
        except Exception as exc:
            logger.warning(f"Audit side-effect failed: {exc}")

        # Pass through (non-terminal!)
        self._output_artifact = self._get_artifact(results)
```

**Use Case**: Write to audit archive AND continue pipeline (compliance without blocking)

**Key Distinction**: AND is **terminal fan-out**, TEE is **side-effect with pass-through**

---

### 3.4 Logical Plugin Taxonomy Summary

**Complete Taxonomy**:

| Pattern | Purpose | Terminating? | 1.0 Scope |
|---------|---------|--------------|-----------|
| **AND** | Write to ALL | ✅ Yes | ✅ ADR-009 |
| **OR** | Load balance | ✅ Yes | ✅ ADR-009 |
| **IF** | Conditional route | ✅ Yes | ✅ ADR-009 |
| **TRY** | Resilient fallback | ✅ Yes | ✅ ADR-009 |
| **WHEN** | Conditional filter | ✅ Yes | ❌ Post-1.0 |
| **CIRCUIT_BREAKER** | Fault tolerance | ✅ Yes | ❌ Post-1.0 |
| **THROTTLE** | Rate limiting | ✅ Yes | ❌ Post-1.0 |
| **TEE** | Side effect + pass | ❌ No | ❌ Post-1.0 |

**Architecture Principle**: **Not Turing-complete, but functionally complete** for enterprise data pipeline routing

**1.0 Scope**: Core routing patterns (AND/OR/IF/TRY) in ADR-009
**Post-1.0**: Advanced patterns (WHEN/CIRCUIT_BREAKER/THROTTLE/TEE) in ADR-013

---

## Part 4: Implementation Roadmap

### 4.1 P0 Roadmap (Before 1.0 Release)

**Total Effort**: 13.5-16.5 hours (2 days)

| Priority | Issue | Type | Effort | Deliverable |
|----------|-------|------|--------|-------------|
| P0-1 | Registry Architecture | ADR | 3-4h | ADR-007 "Unified Registry Pattern" |
| P0-2 | Artifact Lifecycle | ADR | **7-8h** | ADR-009 "Pass-Through Lifecycle & Routing" |
| P0-3 | Namespace Migration | Code | 1-2h | All docs use `plugins/nodes/` structure |
| P0-4 | Registry Consolidation | Code | 1h | Single `registries/` directory |
| P0-5 | ADR Numbering | Docs | 30m | Historical → A001, A002 |
| P0-6 | Security Terminology | Docs | 1h | Glossary in `docs/architecture/` |

**P0-2 Scope Breakdown** (ADR-009, 7-8h):
- Artifact transform pattern (1h)
- BaseFileWriteSink hierarchy design (2h)
- Core routing plugins: AND/OR/IF/TRY (2-3h)
- Pass-through lifecycle semantics (1h)
- Integration examples and test cases (1-2h)

**Critical Path**: ADR-009 → ADR-006 implementation → 1.0 release

---

### 4.2 P1 Roadmap (Next Sprint)

**Total Effort**: 13-18 hours (2-3 days)

| Priority | Issue | Type | Effort | Deliverable |
|----------|-------|------|--------|-------------|
| P1-1 | Configuration Merge | ADR | 3-4h | ADR-008 "Configuration Composition" |
| P1-2 | Error Handling | ADR | 3-4h | ADR-010 "Error Classification & Recovery" |
| P1-3 | Testing Strategy | ADR | 2-3h | ADR-011 "Testing Strategy & Quality Gates" |
| P1-4 | Observability | ADR | 2-3h | ADR-012 "Global Observability Policy" |
| P1-5 | Orchestration Layers | Docs | 2h | Mermaid diagram in architecture-overview.md |
| P1-6 | PluginContext Design | Docs | 1-2h | Section in plugin-security-model.md |

**Priority Rationale**:
- ADR-008: Frequent user pain point (configuration errors)
- ADR-010: Resilience is core principle (ADR-001 priority #3)
- ADR-011: Quality gate formalization
- ADR-012: Compliance requirement (audit trail)

---

### 4.3 P2 Roadmap (Post-1.0 Polish)

**Total Effort**: 14.5-20.5 hours (2-3 days)

| Priority | Issue | Type | Effort | Deliverable |
|----------|-------|------|--------|-------------|
| P2-1 | Middleware Composition | Docs | 1-2h | Ordering rules in middleware-lifecycle.md |
| P2-2 | Update Annotations | Docs | 2-3h | Move to CHANGELOG.md, clean docs |
| P2-3 | Deployment Architecture | Docs | 3-4h | `docs/operations/deployment-guide.md` |
| P2-4 | Data Retention Policy | Docs | 1-2h | `docs/operations/retention-policy.md` |
| P2-5 | Prompt Hygiene Terms | Docs | 30m | Clarify in security-controls.md |
| P2-6 | Advanced Routing | ADR+Code | 6-8h | ADR-013 + WHEN/CIRCUIT_BREAKER/THROTTLE/TEE |

**Defer Rationale**: Not blocking 1.0, refinement and expansion

---

### 4.4 Roadmap Summary by Work Type

| Work Type | P0 | P1 | P2 | Total |
|-----------|----|----|-----|-------|
| **ADRs** | 10-12h | 10-14h | 6-8h | 26-34h |
| **Code** | 2-3h | 0h | 0h | 2-3h |
| **Docs** | 1.5h | 3-4h | 8.5-12.5h | 13-18h |
| **TOTAL** | **13.5-16.5h** | **13-18h** | **14.5-20.5h** | **41-55h** |

**Total Pre-1.0 Effort** (P0): 13.5-16.5 hours (2 days)
**Total Post-1.0 Polish** (P1+P2): 27.5-38.5 hours (4-5 days)

---

## Part 5: Strategic Architectural Direction

### 5.1 Decision Summary

All critical architectural questions have been resolved. Below are the strategic directions:

#### Direction 1: Namespace Migration

**Decision**: Clean sweep - migrate ALL documentation to new `plugins/nodes/` structure

**Rationale**:
> "Pre-1.0, no sloppy dual references. We're agile(esque) but that doesn't mean we want to look sloppy."

**Implementation**:
- Update all footnotes and examples to consistent structure
- Remove old path references (except historical context)
- Zero dual references or confusing artifacts

**Priority**: P0 (1-2 hours)

---

#### Direction 2: Registry Directory Consolidation

**Decision**: Investigate and consolidate duplicate directories

**Rationale**:
> "Same reason [as namespace migration] - legacy debt. Nail it."

**Implementation**:
- Investigate `core/registries/` vs `core/registry/` purpose
- Consolidate to single directory (likely `registries/` plural)
- Document directory structure clearly

**Priority**: P0 (1 hour)

---

#### Direction 3: Artifact Lifecycle Model (CRITICAL)

**Decision**: **Pass-through model** - "Hand it over and forget it immediately"

**Rationale**:
> "Remember that these frames will be flying around 'at speed' so we can't have dozens of artifacts backing up. The answer is hand it over and forget about it immediately - e.g. the excel file sink creates an excel artifact, hands it to the file_write sink and forgets about it immediately."

**Architectural Implications**:
1. **Sink Decomposition**:
   - Monolithic sinks → Artifact transforms + File write sinks
   - Example: `ExcelResultSink` → `ExcelTransform` + `LocalFileWriteSink`

2. **User Extensibility**:
   - BaseFileWriteSink inheritance hierarchy
   - Users implement custom writers without forking

3. **Logical Routing**:
   - AND/OR/IF/TRY (core patterns, 1.0)
   - WHEN/CIRCUIT_BREAKER/THROTTLE/TEE (advanced, post-1.0)

4. **Composability**:
   - `ExcelTransform` → `IfRouting` → `TryFallback` → `AzureBlobWriter`
   - Enterprise topologies: Redundant multi-region with load balancing

**Impact**: **CRITICAL** - Changes sink architecture fundamentally

**Priority**: P0 (7-8 hours for ADR-009)

**Note**: This is the most architecturally significant decision in this review. ADR-009 becomes a **major architectural ADR** (not just lifecycle policy).

---

#### Direction 4: ADR Numbering Convention

**Decision**: Rename historical ADRs with 'A' prefix

**Rationale**:
> "The ADR issue is weird and honestly I propose we rename the archived ones A001 and A002 rather than keeping 3 and 4."

**Implementation**:
- `historical/003-remove-legacy-code.md` → `historical/A001-remove-legacy-code.md`
- `historical/004-complete-registry-migration.md` → `historical/A002-complete-registry-migration.md`
- Update README.md ADR index
- Document naming convention:
  - Active: 001, 002, 003, ... (numeric)
  - Historical: A001, A002, A003, ... ('A' prefix)

**Priority**: P0 (30 minutes)

---

#### Direction 5: Observability Architecture

**Decision**: Dual approach - ADR for global policy, middleware for environment-specific implementation

**Rationale**:
> "Observability was originally left to middleware as it's environment specific, but all 'global observability questions' should be centralised in an ADR."

**Implementation**:
- **ADR-012 "Global Observability Policy"**:
  - What MUST be logged (security events, data access, classification changes)
  - What MUST NOT be logged (PII, classified content, prompt/response payloads)
  - Correlation ID propagation rules
  - Retention policy requirements
  - Compliance obligations

- **Middleware** (environment-specific):
  - Azure ML telemetry middleware
  - Generic audit logger
  - Health monitoring middleware

**Separation**: Policy (ADR) vs Implementation (Middleware)

**Priority**: P1 (2-3 hours)

---

#### Direction 6: 1.0 Release Criteria

**Decision**: Function + Security complete, zero intentional debt

**Rationale**:
> "We need to be both function complete and security complete. Minor lint, complexity issues etc are fine but we need to act the way we're meant to be."

**1.0 Release Gates**:

✅ **Function Complete**:
- All core features implemented (sources, transforms, sinks, artifact pipeline)
- Dual-output protocol functional (ADR-006)
- Pass-through artifact lifecycle working (ADR-009)
- Configuration system complete with validation
- Baseline comparison, early stopping, aggregation working

✅ **Security Complete**:
- All security ADRs implemented (ADR-001 through 005)
- MLS enforcement working (Bell-LaPadula)
- ClassifiedDataFrame immutability enforced
- BasePlugin ABC security bones in place
- Security-critical exceptions fail-loud
- Audit logging comprehensive

⚠️ **Quality Acceptable** (not perfect):
- Minor lint issues acceptable
- Complexity warnings acceptable (not critical)
- Test coverage good (not necessarily 100%)
- Documentation complete for implemented features

❌ **Zero Intentional Debt**:
- No "we'll fix this later" architectural debt
- No confusing dual references or legacy paths
- Clean namespace migration
- Consolidated registry structure
- Clear ADR numbering
- "Act the way we're meant to be" - no sloppy artifacts

**What Can Be Deferred**:
- Advanced features (PostgreSQL datasource, Azure Search)
- Performance optimization (as long as functional)
- Polish and refinement
- Non-critical documentation improvements

**Priority**: N/A (release criteria, not implementation task)

---

### 5.2 Architectural Philosophy

The decision discussions revealed **core pre-1.0 philosophy**:

> **"Act the way we're meant to be"**

**Principles**:
1. ✅ **Function + Security complete** (non-negotiable)
2. ✅ **Zero intentional technical debt**
3. ✅ **Clean, unambiguous structure**
4. ⚠️ **Quality good, not perfect** (lint/complexity acceptable)
5. ❌ **No "we'll fix this later" debt**
6. ❌ **No confusing dual references**

This philosophy drives all pre-1.0 decisions and gates 1.0 release readiness.

---

## Part 6: Appendices

### Appendix A: Gap Analysis Matrix

| Gap | Priority | Type | Impact | Effort | ADR# |
|-----|----------|------|--------|--------|------|
| Registry Architecture | P0 | Missing ADR | HIGH | 3-4h | ADR-007 |
| Artifact Lifecycle | P0 | Missing ADR | CRITICAL | 7-8h | ADR-009 |
| Namespace Migration | P0 | Inconsistency | MEDIUM | 1-2h | - |
| Registry Consolidation | P0 | Inconsistency | LOW | 1h | - |
| ADR Numbering | P0 | Inconsistency | LOW | 30m | - |
| Security Terminology | P0 | Inconsistency | MEDIUM | 1h | - |
| Config Merge | P1 | Missing ADR | MEDIUM | 3-4h | ADR-008 |
| Error Handling | P1 | Missing ADR | MEDIUM-HIGH | 3-4h | ADR-010 |
| Testing Strategy | P1 | Missing ADR | MEDIUM | 2-3h | ADR-011 |
| Observability | P1 | Missing ADR | MEDIUM | 2-3h | ADR-012 |
| Orchestration Docs | P1 | Undocumented | MEDIUM | 2h | - |
| PluginContext Docs | P1 | Undocumented | MEDIUM | 1-2h | - |
| Middleware Composition | P2 | Undocumented | LOW-MEDIUM | 1-2h | - |
| Update Annotations | P2 | Debt | LOW | 2-3h | - |
| Deployment Guide | P2 | Missing Docs | MEDIUM | 3-4h | - |
| Retention Policy | P2 | Missing Docs | LOW-MEDIUM | 1-2h | - |
| Prompt Hygiene | P2 | Debt | LOW | 30m | - |

**Total**: 17 gaps (5 P0, 6 P1, 6 P2)

---

### Appendix B: ADR Roadmap

**Active ADRs** (Current):
- ADR-001: Design Philosophy ✅ Accepted
- ADR-002: Multi-Level Security ✅ Accepted
- ADR-002-A: Trusted Container Model ✅ Accepted
- ADR-003: Plugin Type Registry 📋 Proposed
- ADR-004: Mandatory BasePlugin 📋 Proposed
- ADR-005: Security-Critical Exceptions 📋 Proposed
- ADR-006: Universal Dual-Output 📋 Proposed

**Planned ADRs** (Pre-1.0):
- ADR-007: Unified Registry Pattern (P0, 3-4h)
- ADR-008: Configuration Composition (P1, 3-4h)
- ADR-009: Pass-Through Lifecycle & Routing (P0, 7-8h) ⭐ **CRITICAL**
- ADR-010: Error Classification & Recovery (P1, 3-4h)
- ADR-011: Testing Strategy & Quality Gates (P1, 2-3h)
- ADR-012: Global Observability Policy (P1, 2-3h)

**Future ADRs** (Post-1.0):
- ADR-013: Advanced Routing Patterns (P2, 6-8h)

**Historical ADRs** (Completed):
- A001: Remove Legacy Code ✅ Completed (renamed from 003)
- A002: Complete Registry Migration ✅ Completed (renamed from 004)

**Total ADR Effort** (Pre-1.0): 26-30 hours (4-5 days for all missing ADRs)

---

### Appendix C: Strengths Preservation Checklist

As you address gaps, **preserve these exceptional qualities**:

✅ **Comprehensive documentation** - Best-in-class depth
✅ **Security-first consistency** - Applied at every layer
✅ **Clear ADR evolution** - Intentional architectural maturity
✅ **Refactoring methodology** - Battle-tested, publication-worthy
✅ **Separation of concerns** - Clean layering, no violations

**Critical**: Don't let gap-filling compromise these strengths!

---

### Appendix D: Key Architectural Insight

**Discovery**: The artifact lifecycle decision revealed the **true plugin taxonomy**:

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

**Implication**: Current monolithic sinks (ExcelResultSink, CsvResultSink) are actually **artifact transforms** that should compose with **file write sinks**.

**Composability Unlocked**:
```
ExcelTransform + LocalFileWriter → writes to disk
ExcelTransform + AzureBlobWriter → writes to Azure Blob
ExcelTransform + LegacyMainframeWriter → writes to mainframe (user-extensible!)

# OR compose with routing:
ExcelTransform → IfRouting → TryFallback → destination
```

**Status**: This insight should be central to ADR-009 "Pass-Through Artifact Lifecycle & Transform Composition"

---

**END OF ASSESSMENT**

*Generated: 2025-10-26*
*Reviewer: Claude (Architecture Analysis)*
*Status: Final - Ready for Implementation*
*Next Steps: Begin P0 roadmap (ADR-007, ADR-009, namespace cleanup)*
