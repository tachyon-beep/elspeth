# WP001: Streaming Datasource Architecture

**Status**: Planning
**Priority**: Critical Blocker
**Estimated Effort**: 3-5 days (1 FTE)
**Owner**: Core Tech Team
**Created**: 2025-10-13

## Executive Summary

The current batch-oriented datasource architecture forces complete dataset loading into memory before processing begins. This creates critical blockers for:

1. **Large-scale experiments** (10k-100k rows): Excessive memory consumption and startup latency
2. **Generative/programmatic sources**: Cannot support LLM-generated adversarial prompts or infinite streams where row count is unknown upfront

This work package proposes a streaming-first architecture that processes rows incrementally while maintaining backward compatibility with existing batch-based configurations.

## Problem Statement

### Current Architecture Limitations

**Datasource Contract** (`src/elspeth/core/interfaces.py:12-17`):
```python
class Datasource(Protocol):
    def load(self) -> pd.DataFrame:  # Forces complete buffering
```

**Runner Execution Model** (`src/elspeth/core/experiments/runner.py:61`):
```python
def run(self, df: pd.DataFrame) -> Dict[str, Any]:
    for idx, (_, row) in enumerate(df.iterrows()):  # Requires full DataFrame
```

**Issues**:
- **Memory bloat**: 100k row DataFrame with embeddings/long text fields → GB-scale memory usage
- **Startup latency**: Must load entire dataset before first LLM call
- **No streaming sources**: Cannot support generative datasources (e.g., adversarial prompt generators, live API feeds)
- **No backpressure**: Cannot throttle source emission based on processing capacity

### Critical Use Cases

#### UC1: Large Static Datasets
```yaml
datasource:
  type: csv_blob
  path: experiments/adversarial_prompts_100k.csv  # 100k rows, ~2GB
```
**Current behavior**: Load all 2GB into memory → OOM risk, slow startup
**Required behavior**: Stream rows incrementally, minimal memory footprint

#### UC2: Generative Adversarial Testing
```yaml
datasource:
  type: adversarial_generator
  llm:
    type: azure_openai
    deployment: gpt-4
  templates:
    - jailbreak_attempts
    - prompt_injection
    - context_manipulation
  count: 1000  # Generate 1000 test cases on-the-fly
```
**Current behavior**: Not supported (no streaming datasource protocol)
**Required behavior**: Generate prompts lazily as experiment consumes them

#### UC3: Live API Data Feeds
```yaml
datasource:
  type: api_stream
  endpoint: https://monitoring.example.com/alerts/stream
  poll_interval: 30s
  max_items: 5000
```
**Current behavior**: Not supported
**Required behavior**: Poll API, yield new items, process incrementally

## Requirements

### Functional Requirements

**FR1**: Support streaming datasources that yield rows incrementally
**FR2**: Maintain backward compatibility with existing batch datasources
**FR3**: Enable memory-efficient processing of large datasets (10k-100k+ rows)
**FR4**: Support generative/programmatic datasources with unknown row counts
**FR5**: Allow sinks to consume records incrementally (e.g., CSV append mode)
**FR6**: Provide buffering utility for aggregators requiring complete datasets
**FR7**: Support early stopping on streaming sources
**FR8**: Maintain existing security context propagation and artifact pipeline semantics using Australian Government security classification levels
**FR9**: All plugins must handle dynamic batch sizes (1 row, 3 rows, 100 rows, 10k rows) without errors
**FR10**: Process rows in FIFO order consistently across streaming and batch modes
**FR11**: Policy-driven determinism validation: Plugins declare determinism compatibility, experiments declare requirements, system fails at config-time if incompatible

### Non-Functional Requirements

**NFR1**: Zero breaking changes for existing configurations
**NFR2**: Memory usage should scale with concurrency, not dataset size
**NFR3**: First record processed within seconds of stream start (no bulk buffering)
**NFR4**: Backpressure support: slow sinks should not cause unbounded memory growth
**NFR5**: Checkpoint/resume support for long-running streams

## Architecture Design

### Design Principles

#### 1. Variable Batch Size Tolerance

**All plugins must be resilient to variable batch sizes without making assumptions about row counts.**

**Examples**:

❌ **Bad** (assumes batch size):
```python
class MyAggregator:
    def finalize(self, records: List[Dict]) -> Dict[str, Any]:
        # Assumes at least 100 records!
        percentile_95 = records[95]  # IndexError if len(records) < 100
        return {"p95": percentile_95}
```

✅ **Good** (handles any size):
```python
class MyAggregator:
    def finalize(self, records: List[Dict]) -> Dict[str, Any]:
        if not records:
            return {}

        # Works with 1, 3, 100, or 10k records
        values = sorted([r["score"] for r in records])
        p95_idx = int(len(values) * 0.95)
        return {"p95": values[p95_idx] if values else None}
```

**Row-Level Plugins**: Already compliant (process one record at a time)

**Aggregators**: Must handle empty lists and small sample sizes:
- Return empty dict or null values for empty input
- Skip percentile calculations if `len(records) < 2`
- Use guard clauses: `if not records: return {}`

**Sinks**: Must handle incremental writes of any size:
- CSV: Write header once, append rows individually
- JSON: Build array incrementally, don't assume batch size
- Blob uploads: Chunk by byte size, not row count

#### 2. FIFO Processing Order

**Rows must be processed in the order emitted by the datasource.**

- Streaming mode: Natural iterator order
- Batch mode: DataFrame row order (via `iterrows()`)
- Concurrent mode: Results re-sorted by original index (already implemented in `runner.py:155`)

**Critical**: Datasources must emit rows in deterministic order for reproducibility. Generators should use fixed seeds.

#### 3. No Batch Size Leakage

**Internal chunk sizes must not be visible to user-facing plugins.**

- Datasources may chunk internally (500 rows per read) but yield rows individually
- Runner may buffer for concurrency but presents single records to row plugins
- Aggregators receive complete results list (after FIFO ordering)

#### 4. Policy-Driven Determinism Validation

**Plugins declare their determinism compatibility. Experiments declare their requirements. System validates at config-time and fails fast if incompatible.**

**Design Goal**: No silent non-determinism. If a user requires determinism, the system MUST either guarantee it or reject the configuration with actionable errors.

**Compliance Context**: Determinism is not just for debugging - it's a **cryptographic audit contract**. When `determinism: required` is set:

1. **Results are cryptographically signed** (via `signed_artifact` sink)
2. **Signature includes**: code versions, plugin fingerprints, configuration, data checksums, runtime metadata
3. **Auditor verification**: External auditors can re-run the signed package and expect **byte-identical results**
4. **Regulatory requirement**: Some compliance frameworks require verifiable reproducibility (e.g., FDA 21 CFR Part 11, GxP)

**Why this matters**:
- Cryptographic signatures prove **authenticity** (no tampering)
- Determinism enables **verification via re-execution** (auditors can independently confirm results)
- Non-deterministic plugins break the audit chain: signature is valid but re-execution produces different outputs
- This creates compliance risk: auditors cannot independently verify the work

**Example audit workflow**:
```
1. Team runs experiment → produces signed artifact bundle
2. Bundle contains: results.csv, config.yaml, code_manifest.json, signature.hmac
3. Auditor receives bundle → verifies signature (proves authenticity)
4. Auditor re-runs experiment from bundle → expects identical results.csv
5. If results differ → audit failure (either tampering or non-deterministic execution)
```

**Therefore**: `determinism: required` is a **compliance promise**, not a preference. Violations must be rejected at config-time.

##### Signed Artifact Requirements for Deterministic Experiments

When `determinism: required`, the `signed_artifact` sink must capture everything needed for byte-identical re-execution:

**Manifest Contents** (`src/elspeth/plugins/outputs/signed.py`):

```json
{
  "experiment": {
    "name": "reproducible_eval",
    "timestamp": "2025-10-13T14:32:00Z",
    "determinism_requirement": "required",
    "determinism_validation": {
      "all_plugins_compatible": true,
      "validated_at": "2025-10-13T14:31:55Z"
    }
  },
  "code_manifest": {
    "elspeth_version": "2.1.0",
    "python_version": "3.11.5",
    "dependencies": {
      "pandas": "2.1.0",
      "numpy": "1.25.2"
    },
    "plugin_fingerprints": {
      "datasource.local_csv": "sha256:abc123...",
      "llm.mock": "sha256:def456...",
      "middleware.audit_logger": "sha256:789ghi...",
      "sink.csv": "sha256:012jkl..."
    }
  },
  "configuration": {
    "merged_config_hash": "sha256:merged_abc...",
    "config_files": [
      {"path": "suite/defaults.yaml", "hash": "sha256:..."},
      {"path": "packs/eval_pack.yaml", "hash": "sha256:..."},
      {"path": "experiments/exp001.yaml", "hash": "sha256:..."}
    ]
  },
  "data_manifest": {
    "datasource": {
      "type": "local_csv",
      "path": "data/test_set.csv",
      "hash": "sha256:data_hash...",
      "row_count": 1000,
      "schema_hash": "sha256:schema..."
    }
  },
  "runtime": {
    "concurrency": {"enabled": false},
    "seed": 42,
    "llm_settings": {
      "temperature": 0.0,
      "seed": 42
    }
  },
  "results": {
    "results_file": "results.csv",
    "results_hash": "sha256:results...",
    "aggregates": {...},
    "cost_summary": {...}
  },
  "signature": {
    "algorithm": "HMAC-SHA256",
    "key_derivation": "PBKDF2-HMAC-SHA256",
    "signature": "base64_encoded_signature",
    "signed_at": "2025-10-13T14:32:05Z"
  }
}
```

**Critical Fields**:
- `determinism_validation.all_plugins_compatible`: Proof that config-time validation passed
- `plugin_fingerprints`: Code hashes for all plugins (detect code changes between runs)
- `data_manifest.hash`: Input data checksum (verify data not changed)
- `merged_config_hash`: Complete configuration hash (detect config drift)
- `runtime.seed`: All random seeds captured

**Auditor Re-execution Checklist**:
1. Verify signature against manifest
2. Check plugin fingerprints match installed versions
3. Verify data hash matches
4. Verify configuration hash matches
5. Re-run experiment with exact settings
6. Compare results hash → must match
7. If mismatch → investigate manifest fields for drift

##### Plugin Determinism as First-Class Attribute

**Determinism is mandatory for all plugins**, just like `security_level`. Every plugin must declare its determinism level at registration.

**Architectural Parallel**:

| Attribute | Purpose | Aggregation Rule | Propagated Via |
|-----------|---------|------------------|----------------|
| `security_level` | Data classification | **Most restrictive wins** (confidential > internal > public) | `PluginContext` |
| `determinism_level` | Reproducibility guarantee | **Least deterministic wins** (none < low < high < guaranteed) | `PluginContext` |

**Plugin Declaration**:

```python
class HealthMonitorMiddleware(LLMMiddleware):
    name = "health_monitor"

    # MANDATORY: Determinism level declaration
    determinism_level = "none"  # Options: "guaranteed", "high", "low", "none"

    # Optional: Additional constraints
    determinism_constraints = ["serial_only"]  # Requires serial execution

    # MANDATORY: Explanation for auditors/docs
    determinism_notes = (
        "Wall-clock latency tracking creates timing variance across runs. "
        "Thread interleaving in concurrent mode amplifies non-determinism."
    )
```

**PluginContext Extension**:

```python
@dataclass
class PluginContext:
    """Enhanced with determinism tracking."""
    security_level: str
    determinism_level: str  # NEW: Propagated like security_level
    provenance: str
    plugin_kind: str
    plugin_name: str
    parent_context: PluginContext | None = None

    def derive(self, **overrides) -> PluginContext:
        """Create child context, inheriting determinism."""
        return PluginContext(
            security_level=overrides.get("security_level", self.security_level),
            determinism_level=overrides.get("determinism_level", self.determinism_level),
            ...
        )
```

**Experiment-Level Aggregation**:

Like `security_level`, the experiment's overall `determinism_level` is **aggregated from all components**:

**File**: `src/elspeth/core/determinism.py` (new)

```python
def resolve_determinism_level(*levels: str) -> str:
    """
    Resolve experiment determinism from component levels.

    Rule: LEAST deterministic wins (opposite of security "most restrictive wins")

    Examples:
        resolve_determinism_level("guaranteed", "high") → "high"
        resolve_determinism_level("high", "none") → "none"
        resolve_determinism_level("guaranteed", "guaranteed") → "guaranteed"
    """
    ranking = {"guaranteed": 3, "high": 2, "low": 1, "none": 0}
    min_rank = min(ranking[lvl] for lvl in levels if lvl)
    for level, rank in ranking.items():
        if rank == min_rank:
            return level
    return "none"  # Fallback
```

**Integration in ExperimentRunner**:

```python
# In runner.py:run()
datasource_det = getattr(datasource, "determinism_level", "none")
llm_det = getattr(llm_client, "determinism_level", "none")
middleware_dets = [getattr(m, "determinism_level", "none") for m in llm_middlewares]
plugin_dets = [
    getattr(p, "determinism_level", "none")
    for p in (row_plugins + aggregator_plugins + validation_plugins)
]

experiment_determinism = resolve_determinism_level(
    datasource_det,
    llm_det,
    *middleware_dets,
    *plugin_dets,
)

metadata["determinism_level"] = experiment_determinism
```

**Artifact Tagging**:

All artifacts produced by sinks inherit the experiment's resolved determinism level:

```python
# Artifact metadata
{
    "artifact_id": "results_exp001",
    "security_level": "internal",  # From security resolution
    "determinism_level": "high",   # From determinism resolution
    "produced_by": "csv_sink",
    "timestamp": "2025-10-13T14:32:00Z",
}
```

**Determinism Spectrum**:

Plugins declare their determinism level using a **4-level scale** that reflects **how much variance to expect** in results:

| Level | Meaning | Variance Expectation | Example Plugins |
|-------|---------|---------------------|-----------------|
| `guaranteed` | Byte-identical results every execution (pure deterministic logic) | **Zero variance** - Results are cryptographically identical | `AuditMiddleware`, `PromptShieldMiddleware`, `CSVFileSink`, `ScoreStatsAggregator` |
| `high` | Extremely low variance (may have floating-point rounding differences) | **Negligible variance** - Core results match, minor numerical differences | `MockLLM` (temp=0, seeded), `AzureOpenAI` (temp=0, seed set), Statistical aggregators |
| `low` | Significant variance expected but same distribution | **Moderate variance** - Different specific outputs, same statistical properties | `AzureOpenAI` (temp>0, seeded), `AdversarialGenerator` (seeded), Retry with jitter |
| `none` | Non-deterministic by design (uncontrolled sources of randomness) | **High variance** - Completely different results each run | `AzureOpenAI` (no seed), Wall-clock timestamps, Network latency metrics, `HealthMonitor` timing |

**Additional Constraints** (orthogonal to spectrum):

| Constraint | Meaning | Example |
|------------|---------|---------|
| `serial_only` | Requires serial execution (thread interleaving breaks determinism) | `HealthMonitorMiddleware`, Early-stop timing |
| `conditional` | Requires specific config (seed, temperature, etc.) to reach declared level | `MockLLM` (needs seed for `high`), LLMs (need temp=0 + seed for `high`) |

##### Experiment Requirement Declaration

Experiments declare **minimum acceptable determinism level**. If any plugin has lower determinism, config validation fails.

```yaml
experiment:
  name: "reproducible_eval"

  requirements:
    determinism: guaranteed  # Strictest: Only byte-identical plugins allowed
    # OR
    determinism: high  # Allow minor floating-point variance
    # OR
    determinism: low  # Allow distribution-level variance
    # OR
    determinism: none  # No validation (default for backward compatibility)

    # Optional: Enforcement mode
    determinism_enforcement: strict  # Fail if requirement not met (default)
    # OR
    determinism_enforcement: warn  # Log warnings but proceed

  concurrency:
    enabled: true
    max_workers: 8
```

**Validation Logic**:

| Requirement Level | Allowed Plugin Levels | Rejected |
|-------------------|----------------------|----------|
| `guaranteed` | `guaranteed` only | `high`, `low`, `none` |
| `high` | `guaranteed`, `high` | `low`, `none` |
| `low` | `guaranteed`, `high`, `low` | `none` |
| `none` | All levels accepted | None |

**Example Error**:
```
ConfigurationError: Experiment requires determinism='guaranteed' but 2 plugins have insufficient determinism:

  ❌ llm.azure_openai: determinism='high' (temperature=0 but minor floating-point variance)
     Reason: Even with temperature=0, API may introduce negligible numerical differences
     Requirement: guaranteed
     Actual: high

  ❌ middleware.health_monitor: determinism='none' (timing-dependent metrics)
     Reason: Wall-clock latency tracking creates variance across runs
     Requirement: guaranteed
     Actual: none

💡 Solutions:
  1. Lower requirement to determinism='high' to accept LLM minor variance
  2. Remove health_monitor middleware (timing metrics not deterministic)
  3. Use MockLLM instead of AzureOpenAI for guaranteed determinism
```

##### Policy Validation Logic

**File**: `src/elspeth/core/validation/policy_validator.py` (new)

```python
from enum import Enum
from typing import List, Dict, Any

class DeterminismLevel(Enum):
    """Determinism levels on 4-point spectrum."""
    GUARANTEED = "guaranteed"  # Byte-identical results
    HIGH = "high"              # Negligible variance (float rounding)
    LOW = "low"                # Moderate variance (distribution-level)
    NONE = "none"              # Non-deterministic

    @classmethod
    def rank(cls, level: "DeterminismLevel") -> int:
        """Rank determinism levels for comparison (higher is more deterministic)."""
        ranking = {
            cls.NONE: 0,
            cls.LOW: 1,
            cls.HIGH: 2,
            cls.GUARANTEED: 3,
        }
        return ranking[level]

    def __lt__(self, other: "DeterminismLevel") -> bool:
        """Less deterministic than other."""
        return self.rank(self) < self.rank(other)

    def __ge__(self, other: "DeterminismLevel") -> bool:
        """At least as deterministic as other."""
        return self.rank(self) >= self.rank(other)

class DeterminismPolicyValidator:
    """
    Validates determinism compatibility between experiment requirements
    and plugin capabilities at configuration load time.
    """

    def validate(
        self,
        experiment_config: Dict[str, Any],
        plugins: Dict[str, Any],  # All datasources, LLMs, middleware, sinks
    ) -> None:
        """
        Validate determinism policy and raise ConfigurationError if incompatible.

        Raises:
            ConfigurationError: If required determinism cannot be guaranteed
        """
        requirements = experiment_config.get("requirements", {})
        determinism_req = DeterminismLevel(requirements.get("determinism", "none"))

        if determinism_req == DeterminismLevel.NONE:
            return  # No validation needed

        concurrency_enabled = experiment_config.get("concurrency", {}).get("enabled", False)

        # Collect incompatible plugins
        violations = []

        for plugin_type, plugin_configs in plugins.items():
            for plugin_name, plugin_instance in plugin_configs.items():
                capability = self._get_plugin_capability(plugin_instance)

                issue = self._check_compatibility(
                    plugin_name=plugin_name,
                    plugin_type=plugin_type,
                    capability=capability,
                    concurrency_enabled=concurrency_enabled,
                    determinism_req=determinism_req,
                )

                if issue:
                    violations.append(issue)

        if violations:
            self._raise_or_warn(determinism_req, violations, experiment_config)

    def _check_compatibility(
        self,
        plugin_name: str,
        plugin_type: str,
        capability: PluginDeterminismCapability,
        concurrency_enabled: bool,
        determinism_req: DeterminismLevel,
    ) -> Dict[str, Any] | None:
        """Check if plugin is compatible with determinism requirements."""

        if capability == PluginDeterminismCapability.NEVER:
            return {
                "plugin": f"{plugin_type}.{plugin_name}",
                "reason": "Non-deterministic by nature",
                "capability": "never",
            }

        if capability == PluginDeterminismCapability.SERIAL_ONLY and concurrency_enabled:
            return {
                "plugin": f"{plugin_type}.{plugin_name}",
                "reason": "Requires serial execution but concurrency enabled",
                "capability": "serial_only",
            }

        # CONDITIONAL plugins need additional checks (seed set, etc.)
        if capability == PluginDeterminismCapability.CONDITIONAL:
            if not self._check_conditional_requirements(plugin_name):
                return {
                    "plugin": f"{plugin_type}.{plugin_name}",
                    "reason": "Conditional determinism requirements not met",
                    "capability": "conditional",
                }

        return None  # Compatible

    def _raise_or_warn(
        self,
        determinism_req: DeterminismLevel,
        violations: List[Dict[str, Any]],
        experiment_config: Dict[str, Any],
    ) -> None:
        """Raise error or log warning based on determinism requirement level."""

        message = self._format_violation_message(violations, experiment_config)

        if determinism_req == DeterminismLevel.REQUIRED:
            raise ConfigurationError(message)
        elif determinism_req == DeterminismLevel.PREFERRED:
            logger.warning("Determinism violations detected:\n%s", message)

    def _format_violation_message(
        self,
        violations: List[Dict[str, Any]],
        experiment_config: Dict[str, Any],
    ) -> str:
        """Format actionable error message with solutions."""

        lines = [
            f"Experiment requires determinism='{experiment_config['requirements']['determinism']}' "
            f"but {len(violations)} incompatible plugin(s) detected:",
            ""
        ]

        for v in violations:
            lines.append(f"  ❌ {v['plugin']}: {v['reason']} (capability: {v['capability']})")

        lines.extend([
            "",
            "💡 Solutions:",
            "  1. Set requirements.determinism='none' to accept non-deterministic behavior",
        ])

        if any(v["capability"] == "serial_only" for v in violations):
            lines.append("  2. Disable concurrency: concurrency.enabled=false")

        if any(v["capability"] == "never" for v in violations):
            affected = [v["plugin"] for v in violations if v["capability"] == "never"]
            lines.append(f"  3. Remove or replace non-deterministic plugins: {', '.join(affected)}")

        if any(v["capability"] == "conditional" for v in violations):
            lines.append("  4. Satisfy conditional requirements (e.g., set seed, temperature=0)")

        return "\n".join(lines)
```

##### Configuration Schema Updates

**File**: `src/elspeth/core/config/schema.py`

```yaml
# Add to experiment schema
requirements:
  type: object
  properties:
    determinism:
      type: string
      enum: [required, preferred, none]
      default: none
      description: |
        Determinism policy enforcement level:
        - required: Fail configuration if determinism cannot be guaranteed
        - preferred: Warn but allow non-deterministic plugins
        - none: No validation (default for backward compatibility)
    reproducibility:
      type: string
      enum: [full, partial, none]
      default: none
      description: |
        Stricter than determinism: requires determinism + seeded randomness + versioning
```

##### Plugin Registration Updates

**File**: `src/elspeth/core/registries/__init__.py`

```python
def register_middleware(
    name: str,
    factory: Callable,
    schema: Dict[str, Any] | None = None,
    determinism_support: str = "conditional",  # NEW: Default to conditional
    determinism_notes: str | None = None,      # NEW: Explanation
) -> None:
    """
    Register middleware with determinism capability declaration.

    Args:
        determinism_support: "always", "serial_only", "conditional", or "never"
        determinism_notes: Human-readable explanation of determinism behavior
    """
    _middleware[name] = {
        "factory": factory,
        "schema": schema,
        "determinism_support": determinism_support,
        "determinism_notes": determinism_notes,
    }
```

##### Example: Middleware Registration

**File**: `src/elspeth/plugins/llms/middleware.py`

```python
register_middleware(
    "health_monitor",
    lambda options, context: HealthMonitorMiddleware(...),
    schema=_HEALTH_SCHEMA,
    determinism_support="serial_only",  # Declared non-deterministic in concurrent mode
    determinism_notes=(
        "Latency tracking uses deque with thread interleaving, making timing-dependent "
        "statistics non-deterministic in concurrent execution. Use serial mode for reproducibility."
    ),
)

register_middleware(
    "audit_logger",
    lambda options, context: AuditMiddleware(...),
    schema=_AUDIT_SCHEMA,
    determinism_support="always",  # Always deterministic
    determinism_notes="Pure logging with no state; deterministic in all modes.",
)
```

##### Integration Point

**File**: `src/elspeth/core/experiments/suite_runner.py`

```python
def _validate_experiment_config(self, experiment_config: Dict[str, Any]) -> None:
    """Validate experiment configuration including determinism policy."""

    # Existing schema validation
    validate_config_schema(experiment_config)

    # NEW: Determinism policy validation
    validator = DeterminismPolicyValidator()

    plugins = {
        "datasource": {"main": self.datasource},
        "llm": {"main": self.llm_client},
        "middleware": {m.name: m for m in self.llm_middlewares or []},
        "row_plugins": {p.name: p for p in self.row_plugins or []},
        "aggregators": {p.name: p for p in self.aggregator_plugins or []},
        "sinks": {s.__class__.__name__: s for s in self.sinks},
    }

    validator.validate(experiment_config, plugins)
```

##### Example Error Output

```
ConfigurationError: Experiment requires determinism='required' but 3 incompatible plugin(s) detected:

  ❌ middleware.health_monitor: Requires serial execution but concurrency enabled (capability: serial_only)
  ❌ llm.azure_openai: Non-deterministic by nature (capability: never)
  ❌ middleware.rate_limiter: Timing-dependent throttling (capability: serial_only)

💡 Solutions:
  1. Set requirements.determinism='none' to accept non-deterministic behavior
  2. Disable concurrency: concurrency.enabled=false
  3. Remove or replace non-deterministic plugins: llm.azure_openai
  4. Replace health_monitor and rate_limiter with deterministic alternatives
```

#### 5. Security Classification System (Australian Government PSPF)

**Elspeth uses the Australian Government Protective Security Policy Framework (PSPF) security classification system.**

Reference: [Australian Government PSPF](https://www.protectivesecurity.gov.au/information/sensitive-classified-information/Pages/default.aspx)

##### Classification Levels (Hierarchical)

| Level | Abbreviation | Description | Use Case |
|-------|--------------|-------------|----------|
| **UNOFFICIAL** | `UNOFFICIAL` | Publicly releasable information | Public datasets, open research, demo data |
| **OFFICIAL** | `OFFICIAL` | Government information not publicly available | Internal operations, low-sensitivity admin data |
| **OFFICIAL: Sensitive** | `OFFICIAL_SENSITIVE` | Government information requiring additional protection | Personal information, commercial-in-confidence, operational details |
| **PROTECTED** | `PROTECTED` | Information that could damage national interests if compromised | Law enforcement intel, critical infrastructure, security assessments |
| **SECRET** | `SECRET` | Information that could cause serious damage to national security | National security operations, intelligence sources, sensitive negotiations |

**Note**: There is a higher classification level (TOP SECRET) but it is outside the scope of Elspeth's design envelope.

##### Security Level Hierarchy

**Read-up restriction**: Higher classifications can read lower classifications, but not vice versa.

```
SECRET (5)
  ↓ can read
PROTECTED (4)
  ↓ can read
OFFICIAL: Sensitive (3)
  ↓ can read
OFFICIAL (2)
  ↓ can read
UNOFFICIAL (1)
```

**Example**: A sink with `PROTECTED` clearance can consume artifacts from `OFFICIAL` and `UNOFFICIAL` datasources, but **cannot** consume `SECRET` artifacts.

##### Configuration Examples

**Datasource Declaration**:
```yaml
datasource:
  type: azure_blob
  config_path: storage_config.yaml
  profile: prod_data
  security_level: OFFICIAL_SENSITIVE  # Australian classification
```

**LLM Declaration**:
```yaml
llm:
  type: azure_openai
  deployment: gpt-4
  security_level: PROTECTED  # Can process OFFICIAL_SENSITIVE and below
```

**Sink Declaration**:
```yaml
sinks:
  - type: csv
    path: outputs/results.csv
    security_level: OFFICIAL  # Can only consume OFFICIAL and UNOFFICIAL artifacts
```

##### Artifact Pipeline Enforcement

**File**: `src/elspeth/core/pipeline/artifact_pipeline.py`

The artifact pipeline enforces security clearance at every artifact transfer:

```python
def _check_clearance(
    self,
    producer_level: str,
    consumer_level: str,
) -> bool:
    """
    Verify consumer can read producer's artifacts.

    Uses Australian Government security hierarchy:
    UNOFFICIAL < OFFICIAL < OFFICIAL_SENSITIVE < PROTECTED < SECRET
    """
    hierarchy = {
        "UNOFFICIAL": 1,
        "OFFICIAL": 2,
        "OFFICIAL_SENSITIVE": 3,
        "PROTECTED": 4,
        "SECRET": 5,
    }

    producer_rank = hierarchy.get(producer_level.upper(), 0)
    consumer_rank = hierarchy.get(consumer_level.upper(), 0)

    # Consumer must have equal or higher clearance
    return consumer_rank >= producer_rank
```

**Error Example**:
```
SecurityClearanceError: Sink 'csv_export' (clearance: OFFICIAL) cannot consume
artifact 'analytics_summary' (classification: PROTECTED).

Sink clearance (OFFICIAL=2) < Artifact classification (PROTECTED=4)

💡 Solutions:
  1. Upgrade sink security_level to PROTECTED or higher
  2. Remove this sink from the experiment
  3. Ensure datasource/LLM security_level matches sink capabilities
```

##### PluginContext Security Propagation

Every plugin receives its security classification via `PluginContext`:

```python
@dataclass
class PluginContext:
    security_level: str  # Australian classification: UNOFFICIAL, OFFICIAL, etc.
    provenance: Dict[str, Any]
    plugin_kind: str
    plugin_name: str

    def derive(self, **overrides) -> PluginContext:
        """
        Create derived context for nested plugins.

        Security level inheritance:
        - Child plugins inherit parent's level by default
        - Can be elevated (e.g., parent=OFFICIAL → child=PROTECTED)
        - Cannot be downgraded (enforced by validation)
        """
        ...
```

##### Configuration Validation

**File**: `src/elspeth/core/config/schema.py`

```python
_AUSTRALIAN_SECURITY_LEVELS = [
    "UNOFFICIAL",
    "OFFICIAL",
    "OFFICIAL_SENSITIVE",
    "PROTECTED",
    "SECRET",
]

_SECURITY_LEVEL_SCHEMA = {
    "type": "string",
    "enum": _AUSTRALIAN_SECURITY_LEVELS,
    "description": (
        "Australian Government PSPF security classification. "
        "Hierarchy: UNOFFICIAL < OFFICIAL < OFFICIAL_SENSITIVE < PROTECTED < SECRET"
    ),
}

# All datasources, LLMs, and sinks MUST declare security_level
_DATASOURCE_SCHEMA = {
    "type": "object",
    "required": ["type", "security_level"],
    "properties": {
        "type": {"type": "string"},
        "security_level": _SECURITY_LEVEL_SCHEMA,
        # ... other properties
    },
}
```

##### Security Level Resolution Rules

**Most restrictive wins**:

```python
def resolve_security_level(*levels: str) -> str:
    """
    Resolve final security level from multiple sources.

    Rule: Most restrictive (highest) level wins.

    Example:
        datasource: OFFICIAL
        llm: PROTECTED
        → Experiment level: PROTECTED
    """
    hierarchy = {"UNOFFICIAL": 1, "OFFICIAL": 2, ...}

    normalized = [lvl.upper().replace(" ", "_").replace(":", "") for lvl in levels]
    ranked = [(hierarchy.get(lvl, 0), lvl) for lvl in normalized]

    return max(ranked, key=lambda x: x[0])[1]
```

##### Audit & Compliance

**Security classification must be logged in all audit trails**:

```python
# Middleware audit logging
logger.info(
    "[audit] LLM request",
    extra={
        "security_level": context.security_level,  # e.g., "PROTECTED"
        "experiment": experiment_name,
        "timestamp": timestamp,
        # Sensitive content ONLY logged if security_level permits
    }
)
```

**Artifact manifests include classification**:

```json
{
  "artifact_id": "analytics_summary_001",
  "produced_by": "analytics_report_sink",
  "security_level": "PROTECTED",
  "timestamp": "2025-10-13T14:32:00Z",
  "checksum": "sha256:abc123...",
  "classification_authority": "Australian Government PSPF"
}
```

##### Migration from Generic Levels

**Legacy configurations** using generic levels are automatically mapped:

| Legacy Level | Australian Equivalent | Rationale |
|--------------|----------------------|-----------|
| `public` | `UNOFFICIAL` | Publicly releasable |
| `internal` | `OFFICIAL` | Internal government use |
| `confidential` | `OFFICIAL_SENSITIVE` | Additional protection required |
| `restricted` | `PROTECTED` | Could damage interests if compromised |
| `secret` | `SECRET` | Direct mapping |

**Migration utility** (`src/elspeth/core/security/migration.py`):

```python
def migrate_legacy_security_level(legacy_level: str) -> str:
    """
    Map legacy security levels to Australian Government classifications.

    Logs warnings when migration occurs to encourage config updates.
    """
    mapping = {
        "public": "UNOFFICIAL",
        "internal": "OFFICIAL",
        "confidential": "OFFICIAL_SENSITIVE",
        "restricted": "PROTECTED",
        "secret": "SECRET",
    }

    normalized = legacy_level.lower()
    if normalized in mapping:
        new_level = mapping[normalized]
        logger.warning(
            "Migrating legacy security_level '%s' to Australian classification '%s'. "
            "Please update configuration to use standard PSPF levels.",
            legacy_level,
            new_level,
        )
        return new_level

    # Already using Australian classification
    return legacy_level.upper()
```

### Component Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Datasource Layer (with Completion Signals)                                   │
│  ┌──────────────────┐      ┌────────────────────────────────────────────┐   │
│  │ Batch Datasource │      │  Adaptive Datasource (Auto-detect mode)    │   │
│  │ (legacy)         │──┐   │  • Azure Blob (500 rows → batch)          │   │
│  │ load() → DataFrame│  │   │  • Azure Blob (10k rows → streaming)      │   │
│  └──────────────────┘  │   │  determine_mode() → 'batch' | 'streaming'  │   │
│                        │   └────────────────────────────────────────────┘   │
│                        │   ┌────────────────────────────────────────────┐   │
│                        │   │  Streaming Datasource                       │   │
│                        │   │  • CSV (chunked)                           │   │
│                        ▼   │  • Adversarial Generator                   │   │
│                   ┌────────┼──• API Polling                            │   │
│                   │ Adapter│  stream() → Iterator[Dict]                │   │
│                   │to_stream  is_complete() → bool                     │   │
│                   └────────┼──completion_status() → enum               │   │
│                            └────────────────────────────────────────────┘   │
│                                │                                             │
└────────────────────────────────┼─────────────────────────────────────────────┘
                                 │ Iterator[Dict[str, Any]]
                                 ▼
                        ┌──────────────────┐
                        │ StreamConnector  │  ← Bounded buffer (default: 100)
                        │  (Backpressure)  │  ← Blocks source when full
                        │                  │  ← Prevents flooding
                        │ put(row) → blocks│
                        │ get() → row      │
                        │ close() → done   │
                        └──────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ StreamingExperimentRunner                                                     │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ for row in connector:                                                  │ │
│  │     record = process_row(row)                                          │ │
│  │     accumulator.add(record)  # Buffer for aggregators                 │ │
│  │                                                                         │ │
│  │     for sink in streaming_sinks:                                       │ │
│  │         if not sink.can_accept():  # ← Capacity check                 │ │
│  │             raise SinkCapacityError("ALARM!")  # ← Critical alarm     │ │
│  │         sink.write_incremental(record)                                 │ │
│  │                                                                         │ │
│  │     if early_stop.check(record):                                       │ │
│  │         break                                                          │ │
│  │                                                                         │ │
│  │ # Check datasource completion                                          │ │
│  │ if datasource.is_complete():                                           │ │
│  │     logger.info("Datasource completed normally")                       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Aggregation Phase (after stream completes)                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ complete_results = accumulator.finalize()                              │ │
│  │ for plugin in aggregators:                                             │ │
│  │     derived = plugin.finalize(complete_results)                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ for sink in batch_sinks:                                               │ │
│  │     sink.write(payload)  # Final write after aggregation               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Core Protocol Changes

#### 1. Enhanced Datasource Protocol with Completion Signals

**File**: `src/elspeth/core/interfaces.py`

```python
from typing import Iterator, Protocol
from enum import Enum

class CompletionStatus(Enum):
    """Stream completion states."""
    ACTIVE = "active"          # Still emitting data
    COMPLETE = "complete"      # Finished, no more data
    EXHAUSTED = "exhausted"    # Hit configured limit
    TERMINATED = "terminated"  # Stopped early (error/early-stop)

class Datasource(Protocol):
    """Backward-compatible datasource protocol."""

    def load(self) -> pd.DataFrame:
        """Load complete dataset (legacy batch mode)."""
        ...

class StreamingDatasource(Protocol):
    """Streaming datasource protocol for incremental row emission with completion signals."""

    def stream(self) -> Iterator[Dict[str, Any]]:
        """
        Yield rows as available.

        Rows are yielded as dictionaries matching DataFrame column semantics.
        Iterator may be finite or infinite; runner handles early stopping.
        Iterator exhaustion (StopIteration) signals natural completion.
        """
        ...

    def supports_streaming(self) -> bool:
        """Indicate if source supports streaming (default: True)."""
        return True

    def is_complete(self) -> bool:
        """
        Check if datasource has finished emitting all available data.

        Returns True when:
        - All rows have been yielded
        - Configured limit reached
        - External source depleted (e.g., API has no more pages)

        Used by runner to distinguish natural completion from early termination.
        """
        ...

    def completion_status(self) -> CompletionStatus:
        """Return detailed completion status for observability."""
        ...

class AdaptiveDatasource(Protocol):
    """
    Datasource that intelligently chooses batch vs streaming based on dataset size.

    Example: Azure Blob datasource that:
    - Loads 500 rows as DataFrame (efficient batch)
    - Streams 10,000+ rows in chunks (memory-safe)
    """

    def determine_mode(self) -> str:
        """
        Inspect dataset and return 'batch' or 'streaming'.

        Called once before load()/stream() to determine execution strategy.
        Implementation should peek at row count, file size, or metadata.
        """
        ...

    def load(self) -> pd.DataFrame:
        """Batch mode: load complete dataset."""
        ...

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Streaming mode: yield rows incrementally."""
        ...
```

#### 2. Streaming Runner Core

**File**: `src/elspeth/core/experiments/streaming_runner.py` (new)

```python
class StreamingExperimentRunner:
    """
    Experiment runner supporting both batch and streaming datasources.

    Key behaviors:
    - Processes rows incrementally as emitted by source
    - Buffers records for aggregators (configurable max buffer size)
    - Supports incremental sink writes (CSV append, streaming exports)
    - Maintains early-stop, checkpointing, retry, and security semantics
    """

    def run(self, source: pd.DataFrame | Iterator[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute experiment on batch or streaming source.

        Args:
            source: DataFrame (batch) or Iterator[Dict] (streaming)

        Returns:
            Experiment payload with results, aggregates, metadata
        """
        # Convert DataFrame to iterator if needed
        rows_iter = self._prepare_iterator(source)

        # Initialize accumulator for aggregation plugins
        accumulator = self._create_accumulator()

        # Process rows incrementally
        for idx, row_dict in enumerate(rows_iter):
            if self._should_stop(idx):
                break

            record = self._process_single_row(row_dict, idx)

            # Add to accumulator
            accumulator.add(record)

            # Write to streaming sinks immediately
            self._write_incremental(record)

            # Check early stop
            if self._check_early_stop(record, idx):
                break

        # Finalize aggregation
        complete_results = accumulator.finalize()
        aggregates = self._run_aggregators(complete_results)

        # Build final payload
        payload = self._build_payload(complete_results, aggregates)

        # Execute batch sinks via artifact pipeline
        self._execute_sinks(payload)

        return payload
```

#### 3. Sink Capacity Control Protocol

**File**: `src/elspeth/core/interfaces.py` (additions)

```python
class SinkCapacityError(Exception):
    """Raised when sink receives data after declaring completion."""
    pass

class StreamingSink(Protocol):
    """Sink that can consume records incrementally with capacity control."""

    def supports_streaming(self) -> bool:
        """Indicate if sink supports incremental writes."""
        return True

    def begin_stream(self, metadata: Dict[str, Any]) -> None:
        """Initialize streaming mode (e.g., write headers, open connections)."""
        ...

    def can_accept(self) -> bool:
        """
        Check if sink can accept more data.

        Returns False when:
        - Configured record limit reached
        - Disk quota exceeded
        - External system rejected writes

        CRITICAL: If runner sends data after can_accept() returns False,
        must raise SinkCapacityError to trigger immediate alarm/investigation.
        """
        ...

    def write_incremental(self, record: Dict[str, Any]) -> None:
        """
        Write single record incrementally.

        Raises:
            SinkCapacityError: If can_accept() is False (alarm condition)
        """
        if not self.can_accept():
            raise SinkCapacityError(
                f"Sink {self.__class__.__name__} cannot accept more data but received record"
            )
        ...

    def finalize_stream(self, metadata: Dict[str, Any]) -> None:
        """Finalize streaming mode (close files, flush buffers)."""
        ...

    def is_complete(self) -> bool:
        """Check if sink has finished accepting all data."""
        ...
```

#### 4. Stream Connector (Bounded Buffer with Backpressure)

**File**: `src/elspeth/core/streaming/connector.py` (new)

```python
import threading
from collections import deque
from typing import Callable, Dict, Any, Iterator

class StreamConnector:
    """
    Bounded buffer between source and processor to prevent flooding.

    Key behaviors:
    - Bounded queue (default: 100 items) prevents unbounded memory growth
    - Blocks source when queue full (backpressure)
    - Signals when drained (allows graceful shutdown)
    - Thread-safe for concurrent producer/consumer

    Example:
        # Fast source, slow processor
        connector = StreamConnector(max_size=100)
        for row in datasource.stream():
            connector.put(row)  # Blocks if queue full
        connector.close()

        for row in connector:
            process_row(row)  # Consumes at own pace
    """

    def __init__(
        self,
        max_size: int = 100,
        timeout: float = 60.0,
        on_backpressure: Callable[[Dict[str, Any]], None] | None = None,
    ):
        """
        Args:
            max_size: Maximum items in queue before blocking producer
            timeout: Seconds to wait before raising timeout error
            on_backpressure: Callback when producer blocked (for metrics)
        """
        self._queue: deque = deque(maxlen=max_size)
        self._max_size = max_size
        self._timeout = timeout
        self._on_backpressure = on_backpressure
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)
        self._closed = False

    def put(self, item: Dict[str, Any]) -> None:
        """
        Add item to buffer, blocking if full (backpressure).

        Raises:
            TimeoutError: If queue remains full beyond timeout
            ValueError: If connector already closed
        """
        with self._not_full:
            if self._closed:
                raise ValueError("Cannot put to closed connector")

            start = time.time()
            while len(self._queue) >= self._max_size:
                if self._on_backpressure:
                    self._on_backpressure({"queue_size": len(self._queue)})

                waited = time.time() - start
                if waited >= self._timeout:
                    raise TimeoutError(
                        f"Connector queue full ({self._max_size}) for {waited:.1f}s"
                    )

                self._not_full.wait(timeout=1.0)

            self._queue.append(item)
            self._not_empty.notify()

    def get(self, block: bool = True) -> Dict[str, Any] | None:
        """
        Remove and return item from buffer.

        Args:
            block: Wait for item if queue empty

        Returns:
            Item dict or None if closed and empty
        """
        with self._not_empty:
            while not self._queue and not self._closed:
                if not block:
                    return None
                self._not_empty.wait(timeout=0.1)

            if not self._queue:
                return None

            item = self._queue.popleft()
            self._not_full.notify()
            return item

    def close(self) -> None:
        """Signal no more items will be added."""
        with self._lock:
            self._closed = True
            self._not_empty.notify_all()
            self._not_full.notify_all()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        """Iterate until closed and empty."""
        while True:
            item = self.get()
            if item is None:
                break
            yield item

    @property
    def size(self) -> int:
        """Current queue size (for monitoring)."""
        with self._lock:
            return len(self._queue)
```

#### 5. Record Accumulator Utility

**File**: `src/elspeth/core/utilities/accumulator.py` (new)

```python
class RecordAccumulator:
    """
    Buffers streaming records for batch-style aggregators.

    Supports configurable max buffer size with overflow strategies:
    - 'error': Raise exception when buffer full (default)
    - 'drop_oldest': FIFO eviction
    - 'sample': Reservoir sampling for large streams
    """

    def __init__(
        self,
        max_size: int | None = None,
        overflow: str = "error",
    ):
        self.max_size = max_size
        self.overflow = overflow
        self._buffer: List[Dict[str, Any]] = []
        self._complete = False

    def add(self, record: Dict[str, Any]) -> None:
        """Add record to buffer, applying overflow strategy if needed."""
        if self._complete:
            raise ValueError("Cannot add to finalized accumulator")

        if self.max_size and len(self._buffer) >= self.max_size:
            self._handle_overflow(record)
        else:
            self._buffer.append(record)

    def finalize(self) -> List[Dict[str, Any]]:
        """Return complete buffered dataset and mark as complete."""
        self._complete = True
        return list(self._buffer)

    def is_complete(self) -> bool:
        """Check if accumulator has been finalized."""
        return self._complete
```

### New Datasource Plugins

#### 1. Chunked CSV Reader

**File**: `src/elspeth/plugins/datasources/csv_streaming.py` (new)

```python
class ChunkedCSVDatasource:
    """
    Read large CSV files in chunks without loading entire file.

    Options:
    - path: CSV file path
    - chunk_size: Rows per chunk (default: 1000)
    - encoding, dtype: pandas read_csv options
    """

    def stream(self) -> Iterator[Dict[str, Any]]:
        for chunk in pd.read_csv(self.path, chunksize=self.chunk_size):
            for _, row in chunk.iterrows():
                yield row.to_dict()
```

#### 2. Adversarial Prompt Generator

**File**: `src/elspeth/plugins/datasources/adversarial_generator.py` (new)

```python
class AdversarialPromptGenerator:
    """
    Generate adversarial test prompts on-the-fly using LLM.

    Options:
    - llm: LLM definition for generation
    - templates: Attack templates (jailbreak, injection, etc.)
    - count: Max prompts to generate
    - seed: Random seed for reproducibility
    """

    def __init__(self, llm, templates, count, seed=42):
        self.llm = llm
        self.templates = templates
        self.count = count
        self.seed = seed
        self._generated = 0

    def stream(self) -> Iterator[Dict[str, Any]]:
        for i in range(self.count):
            template = random.choice(self.templates)
            prompt = self._generate_prompt(template, i)
            self._generated += 1
            yield {
                "id": f"adv_{i:06d}",
                "prompt": prompt,
                "template": template,
                "seed": self.seed + i,
            }

    def is_complete(self) -> bool:
        """Returns True when all configured prompts generated."""
        return self._generated >= self.count

    def completion_status(self) -> CompletionStatus:
        if self._generated >= self.count:
            return CompletionStatus.COMPLETE
        return CompletionStatus.ACTIVE
```

#### 3. Adaptive Azure Blob Datasource

**File**: `src/elspeth/plugins/datasources/blob.py` (enhanced)

```python
class AzureBlobDatasource:
    """
    Azure Blob datasource with intelligent batch/streaming selection.

    Automatically determines optimal strategy based on dataset size:
    - Small datasets (<1000 rows): Batch mode (single DataFrame)
    - Large datasets (≥1000 rows): Streaming mode (chunked iteration)

    Options:
    - config_path: Azure Storage config
    - profile: Storage account profile
    - adaptive_threshold: Row count threshold for streaming (default: 1000)
    - chunk_size: Rows per chunk in streaming mode (default: 500)
    """

    def __init__(
        self,
        config_path: str,
        profile: str,
        adaptive_threshold: int = 1000,
        chunk_size: int = 500,
        **pandas_kwargs,
    ):
        self.config_path = config_path
        self.profile = profile
        self.adaptive_threshold = adaptive_threshold
        self.chunk_size = chunk_size
        self.pandas_kwargs = pandas_kwargs
        self._mode: str | None = None
        self._row_count: int | None = None

    def determine_mode(self) -> str:
        """
        Peek at blob metadata to determine batch vs streaming.

        Checks:
        1. Blob size (bytes) to estimate row count
        2. If available, read first chunk to count rows
        3. Use configured threshold to decide

        Returns: 'batch' or 'streaming'
        """
        if self._mode:
            return self._mode

        # Peek at blob size/metadata
        blob_client = self._get_blob_client()
        properties = blob_client.get_blob_properties()
        size_bytes = properties.size

        # Estimate rows (assume ~500 bytes per row as heuristic)
        estimated_rows = size_bytes // 500

        if estimated_rows < self.adaptive_threshold:
            logger.info(
                "Azure Blob datasource: Detected %d estimated rows, using BATCH mode",
                estimated_rows,
            )
            self._mode = "batch"
        else:
            logger.info(
                "Azure Blob datasource: Detected %d estimated rows, using STREAMING mode (chunks of %d)",
                estimated_rows,
                self.chunk_size,
            )
            self._mode = "streaming"

        return self._mode

    def load(self) -> pd.DataFrame:
        """Load complete dataset (batch mode)."""
        mode = self.determine_mode()
        if mode == "streaming":
            # Adaptive mode chose streaming, but caller requested batch
            # Fall back to loading full DataFrame (with warning)
            logger.warning(
                "Azure Blob datasource: Dataset exceeds adaptive threshold, "
                "but batch load requested. This may cause memory pressure."
            )

        blob_client = self._get_blob_client()
        data = blob_client.download_blob().readall()
        return pd.read_csv(io.BytesIO(data), **self.pandas_kwargs)

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Stream dataset in chunks (streaming mode)."""
        blob_client = self._get_blob_client()
        data = blob_client.download_blob().readall()

        for chunk in pd.read_csv(
            io.BytesIO(data),
            chunksize=self.chunk_size,
            **self.pandas_kwargs,
        ):
            for _, row in chunk.iterrows():
                yield row.to_dict()

    def supports_streaming(self) -> bool:
        return True
```

### Incremental Sink Support

#### Enhanced CSV Sink

**File**: `src/elspeth/plugins/outputs/csv_file.py`

```python
class CSVFileSink:
    # Existing batch interface
    def write(self, payload: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        """Write complete results (batch mode)."""
        ...

    # New streaming interface
    def supports_streaming(self) -> bool:
        return True

    def begin_stream(self, metadata: Dict[str, Any]) -> None:
        """Initialize streaming mode (write CSV header)."""
        self._stream_file = open(self.path, 'w', newline='')
        self._stream_writer = csv.DictWriter(self._stream_file, fieldnames=...)
        self._stream_writer.writeheader()

    def write_incremental(self, record: Dict[str, Any]) -> None:
        """Append single record to CSV."""
        self._stream_writer.writerow(self._flatten_record(record))

    def finalize_stream(self, metadata: Dict[str, Any]) -> None:
        """Close streaming file."""
        self._stream_file.close()
```

## Implementation Plan

### Phase 0: Determinism Policy Infrastructure (0.5 days)

**Deliverables**:
- [ ] Implement `DeterminismPolicyValidator` class
- [ ] Add `determinism_support` and `determinism_notes` to all registry functions
- [ ] Update experiment configuration schema to include `requirements.determinism`
- [ ] Integrate validator into suite runner initialization
- [ ] Update `signed_artifact` sink to include determinism validation metadata

**Tests**:
- Policy validator unit tests (all capability levels)
- Config validation tests (required/preferred/none)
- Error message formatting tests
- Signed artifact manifest tests (verify determinism fields present)

**Files Modified**:
- `src/elspeth/core/validation/policy_validator.py` (new)
- `src/elspeth/core/validation/__init__.py` (new)
- `src/elspeth/core/config/schema.py` (schema updates)
- `src/elspeth/core/registries/__init__.py` (add determinism params)
- `src/elspeth/core/experiments/plugin_registry.py` (add determinism params)
- `src/elspeth/plugins/outputs/signed.py` (manifest updates)
- `tests/test_determinism_policy.py` (new)
- `tests/test_signed_artifact_determinism.py` (new)

**Success Criteria**:
- Config with `determinism: required` + non-deterministic plugins raises `ConfigurationError` at load time
- Signed artifact manifest includes `determinism_validation` and `plugin_fingerprints`

---

### Phase 1: Core Protocols & Adapters (1 day)

**Deliverables**:
- [ ] Define `StreamingDatasource` protocol with `is_complete()`, `completion_status()`
- [ ] Define `AdaptiveDatasource` protocol with `determine_mode()`
- [ ] Define `SinkCapacityError` exception and `StreamingSink` protocol
- [ ] Create adapter utilities to convert `pd.DataFrame → Iterator[Dict]`
- [ ] Create adapter utilities to convert batch `Datasource` to streaming
- [ ] Add feature flag: `ELSPETH_ENABLE_STREAMING` (default: False)

**Tests**:
- Protocol compliance tests
- Adapter tests (DataFrame → iterator conversion)
- Completion status tests

**Files Modified**:
- `src/elspeth/core/interfaces.py`
- `src/elspeth/core/adapters.py` (new)
- `tests/test_streaming_adapters.py` (new)

**Success Criteria**: Can convert existing batch datasources to iterators without behavior change

---

### Phase 2: Streaming Runner Implementation (1.5 days)

**Deliverables**:
- [ ] Implement `RecordAccumulator` utility
- [ ] Create `StreamingExperimentRunner` class
- [ ] Support both `pd.DataFrame` and `Iterator[Dict]` inputs
- [ ] Maintain existing retry, rate limiting, cost tracking, middleware hooks
- [ ] Implement checkpointing for streaming sources
- [ ] Early-stop support in streaming mode

**Tests**:
- Accumulator buffer management (overflow strategies)
- Streaming runner with small synthetic iterator
- Checkpoint/resume with streaming source
- Early-stop triggers in streaming mode
- Memory profiling tests (verify constant memory usage)

**Files Modified**:
- `src/elspeth/core/utilities/accumulator.py` (new)
- `src/elspeth/core/experiments/streaming_runner.py` (new)
- `tests/test_streaming_runner.py` (new)
- `tests/test_accumulator.py` (new)

**Success Criteria**: Can process 10k row iterator with <100MB memory footprint

---

### Phase 3: Streaming Datasource Plugins (1 day)

**Deliverables**:
- [ ] Implement `ChunkedCSVDatasource` (streaming CSV reader)
- [ ] Implement `AdversarialPromptGenerator` (LLM-based generation)
- [ ] Register plugins in datasource registry
- [ ] JSON schema validation
- [ ] Context-aware factory integration

**Tests**:
- Chunked CSV reading (compare results with batch CSV)
- Adversarial generator (validate prompt structure, seed reproducibility)
- Memory profiling (verify chunked CSV doesn't buffer full file)

**Files Modified**:
- `src/elspeth/plugins/datasources/csv_streaming.py` (new)
- `src/elspeth/plugins/datasources/adversarial_generator.py` (new)
- `src/elspeth/core/registries/__init__.py` (register new plugins)
- `tests/test_datasource_streaming_csv.py` (new)
- `tests/test_datasource_adversarial.py` (new)

**Success Criteria**: Can process 100k row CSV with constant memory usage

---

### Phase 4: Incremental Sink Support (1 day)

**Deliverables**:
- [ ] Add streaming interface to `CSVFileSink`
- [ ] Add streaming interface to `JSONBundleSink`
- [ ] Update artifact pipeline to support streaming sinks
- [ ] Distinguish streaming vs batch sinks in runner

**Tests**:
- CSV streaming mode (verify records written incrementally)
- Mixed sink scenario (some streaming, some batch)
- Verify artifact pipeline executes batch sinks after aggregation

**Files Modified**:
- `src/elspeth/plugins/outputs/csv_file.py`
- `src/elspeth/plugins/outputs/local_bundle.py`
- `src/elspeth/core/pipeline/artifact_pipeline.py` (streaming sink support)
- `tests/test_outputs_csv_streaming.py` (new)

**Success Criteria**: CSV sink writes records as they arrive, not at end

---

### Phase 5: Integration & Documentation (0.5 days)

**Deliverables**:
- [ ] Update suite runner to support streaming datasources
- [ ] Configuration schema updates (datasource streaming options)
- [ ] Update plugin catalogue documentation
- [ ] Add streaming examples to `config/sample_suite/`
- [ ] Update `CLAUDE.md` with streaming guidelines

**Tests**:
- End-to-end suite test with streaming datasource
- CLI test with `--head` flag on streaming source

**Files Modified**:
- `src/elspeth/core/experiments/suite_runner.py`
- `docs/architecture/plugin-catalogue.md`
- `docs/architecture/streaming-datasources.md` (new)
- `CLAUDE.md`
- `config/sample_suite/streaming_example.yaml` (new)

**Success Criteria**: Full experiment suite runs with streaming datasource

## Testing Strategy

### Unit Tests

- **Accumulator**: Buffer overflow, sampling strategies
- **Adapters**: DataFrame → iterator conversion
- **Streaming Runner**: Row processing, early stop, checkpointing
- **Datasource Plugins**: Chunked reading, generation logic
- **Variable Batch Sizes**: All plugins tested with:
  - Empty input (0 rows)
  - Single row (1 row)
  - Small batch (3 rows)
  - Standard batch (100 rows)
  - Large batch (10,000 rows)

### Integration Tests

- **End-to-end streaming**: CSV stream → runner → aggregation → sinks
- **Mixed mode**: Batch datasource with streaming sinks
- **Memory profiling**: Verify constant memory with 100k rows
- **Performance**: Compare streaming vs batch throughput
- **Variable batch sizes**: Test full pipeline with varying datasource sizes
- **FIFO ordering**: Verify output order matches input order in all modes

### Regression Tests

- **Existing configs**: All sample suite configs must pass unchanged
- **Backward compatibility**: Existing batch datasources work without modification
- **Plugin resilience**: Parametrized tests for all aggregators with batch sizes [0, 1, 3, 100, 10000]

### Specific Test Cases for Variable Batch Sizes

**Test: Aggregators with Small Samples**
```python
@pytest.mark.parametrize("row_count", [0, 1, 3, 100, 10000])
def test_aggregator_variable_sizes(row_count):
    records = [{"score": i} for i in range(row_count)]
    aggregator = CostSummaryAggregator()
    result = aggregator.finalize(records)

    # Must not raise exceptions
    assert isinstance(result, dict)

    if row_count == 0:
        assert result == {} or all(v == 0 for v in result.values())
    else:
        assert "total_cost" in result
```

**Test: Streaming Sink Incremental Writes**
```python
def test_sink_variable_incremental_writes():
    sink = CSVFileSink(path="test.csv")
    sink.begin_stream({})

    # Write variable batches: 1, then 3, then 0, then 100
    for i in range(1):
        sink.write_incremental({"id": i})

    for i in range(1, 4):
        sink.write_incremental({"id": i})

    for i in range(4, 104):
        sink.write_incremental({"id": i})

    sink.finalize_stream({})

    # Verify all 104 records written in FIFO order
    df = pd.read_csv("test.csv")
    assert len(df) == 104
    assert list(df["id"]) == list(range(104))
```

**Test: FIFO Order Preservation**
```python
def test_fifo_order_streaming_vs_batch():
    data = [{"id": i, "value": random.random()} for i in range(100)]

    # Test batch mode
    df = pd.DataFrame(data)
    batch_results = runner.run(df)

    # Test streaming mode
    stream_results = runner.run(iter(data))

    # Verify identical FIFO order
    assert [r["row"]["id"] for r in batch_results["results"]] == \
           [r["row"]["id"] for r in stream_results["results"]]
```

## Backward Compatibility

### Zero Breaking Changes

1. **Datasource Protocol**: `Datasource.load()` remains unchanged
2. **Runner API**: `ExperimentRunner.run(df)` signature unchanged for batch mode
3. **Configuration Schema**: Existing YAML configs work without modification
4. **Plugin Registry**: Batch datasources continue to work

### Migration Path

**Existing configs** (no changes required):
```yaml
datasource:
  type: local_csv  # Works as before
  path: data.csv
```

**Opt-in streaming** (explicit):
```yaml
datasource:
  type: csv_streaming  # New plugin type
  path: large_data.csv
  chunk_size: 1000
```

**Feature flag**: `ELSPETH_ENABLE_STREAMING=1` enables streaming runner by default

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Memory leaks in accumulator | High | Medium | Extensive profiling tests, overflow strategies |
| Aggregator incompatibility | Medium | Low | All existing aggregators work with buffered results |
| Performance regression (batch mode) | Medium | Low | Performance benchmarks in CI |
| Breaking changes in edge cases | High | Low | Comprehensive regression test suite |
| Infinite stream handling | Medium | Medium | Configurable max buffer size, timeout support |

## Success Metrics

### Functional Metrics
- [ ] 100k row CSV processed with <200MB memory footprint
- [ ] Adversarial generator creates valid prompts on-the-fly
- [ ] All existing test suites pass without modification
- [ ] Streaming CSV matches batch CSV output (determinism)

### Performance Metrics
- [ ] First record processed within 5s of stream start
- [ ] Throughput parity with batch mode (±10%)
- [ ] Memory usage scales with concurrency, not dataset size

### Quality Metrics
- [ ] >90% test coverage on new streaming components
- [ ] Zero regressions in existing test suite
- [ ] Documentation covers all streaming use cases

## Dependencies

**Blocked By**: None (standalone work package)

**Internal Dependencies**:
- **Phase 0 (Determinism Policy)** must complete before other phases
- Determinism validation integrated into Phase 1-5 plugin implementations
- All new plugins must declare `determinism_support` at registration

**Blocks**:
- Large-scale adversarial testing initiatives
- Real-time monitoring integrations
- Cost optimization for memory-constrained environments
- **Regulatory compliance initiatives** requiring cryptographically-signed, deterministically-reproducible experiments (e.g., FDA 21 CFR Part 11, GxP audits)

## Rollout Plan

### Phase 1: Internal Testing (Week 1)
- Feature flag disabled by default
- Core tech team validates on large datasets
- Performance benchmarking

### Phase 2: Opt-In Beta (Week 2)
- Documentation published
- Explicit opt-in via config (`type: csv_streaming`)
- Gather feedback on API ergonomics

### Phase 3: Default Enabled (Week 3)
- Feature flag enabled by default
- Batch datasources auto-converted to streaming
- Monitor for regressions

## Alarm & Monitoring Requirements

### Critical Alarm: SinkCapacityError

**Trigger**: Sink receives data after `can_accept()` returns False

**Severity**: **CRITICAL** - Indicates data loss or mismatched expectations

**Response Actions**:
1. Log full context: sink name, record count, capacity limit, record payload (sanitized)
2. Emit alert to monitoring system (CloudWatch, Azure Monitor, etc.)
3. Halt experiment immediately to prevent further data loss
4. Generate incident report with:
   - Sink configuration
   - Datasource completion status
   - Runner state (early stop triggered?)
   - Record buffer sizes

**Implementation**:
```python
# In StreamingExperimentRunner
try:
    sink.write_incremental(record)
except SinkCapacityError as exc:
    logger.critical(
        "ALARM: Sink capacity exceeded after declaring completion",
        extra={
            "sink": sink.__class__.__name__,
            "sink_config": getattr(sink, "_config", {}),
            "datasource_complete": datasource.is_complete(),
            "records_processed": len(accumulator),
            "error": str(exc),
        }
    )
    # Emit CloudWatch metric with alarm
    emit_alarm("SinkCapacityExceeded", severity="CRITICAL", ...)
    raise
```

### Monitoring Metrics

**Source/Sink Health**:
- `datasource.completion_status` (enum: ACTIVE, COMPLETE, EXHAUSTED, TERMINATED)
- `sink.can_accept()` polled every N records
- `connector.size` (queue depth for backpressure)

**Performance**:
- Time to first record (datasource startup latency)
- Records per second (throughput)
- Backpressure events (connector queue full count)

## Open Questions

1. **Infinite streams**: Should we support infinite streams (e.g., live API polling)? If yes, need timeout/max-records config.
   - **Recommendation**: Yes, with explicit `max_records` config and timeout. Add `CompletionStatus.TIMEOUT` enum value.

2. **Aggregator buffer limits**: What's reasonable max buffer size? 100k? 1M? Should it be configurable?
   - **Recommendation**: Configurable with defaults: 100k rows for standard memory (8GB), 10k for constrained environments.

3. **Checkpoint format**: Should streaming checkpoints differ from batch? (e.g., offset vs row IDs)
   - **Recommendation**: Support both. Streaming datasources can use offset-based checkpoints, generative sources use row IDs.

4. **Backpressure handling**: When connector queue full, should we log warnings or emit metrics?
   - **Recommendation**: Both. Log at WARN level on first occurrence, emit `backpressure_events` counter metric.

5. **Sampling strategies**: For 1M+ row streams, should accumulator use reservoir sampling for aggregation?
   - **Recommendation**: Yes, add `overflow="sample"` strategy using reservoir sampling algorithm (Algorithm R).

6. **Adaptive threshold tuning**: Should `adaptive_threshold` be auto-tuned based on available memory?
   - **Recommendation**: Phase 2 enhancement. Start with fixed defaults, add memory-aware tuning later.

7. **Multiple sink capacity limits**: What if different sinks have different capacity limits?
   - **Recommendation**: Runner checks all sinks' `can_accept()` before each write. First sink to refuse triggers early stop.

8. **Connector usage**: Should StreamConnector be explicit in config or automatic?
   - **Recommendation**: Automatic when concurrency > 1 or adaptive datasource detected. Expose `connector_buffer_size` config for tuning.

## References

- Current Datasource Protocol: `src/elspeth/core/interfaces.py:12-17`
- Current Runner Implementation: `src/elspeth/core/experiments/runner.py:61-217`
- Artifact Pipeline: `src/elspeth/core/pipeline/artifact_pipeline.py`
- Configuration Merge: `docs/architecture/configuration-merge.md`

## Changelog

- 2025-10-13: Initial work package created (Core Tech Team)
- 2025-10-13: Added completion signal protocols (`is_complete()`, `CompletionStatus` enum)
- 2025-10-13: Added sink capacity control (`can_accept()`, `SinkCapacityError` alarm)
- 2025-10-13: Added adaptive datasource protocol (`determine_mode()` for auto-detection)
- 2025-10-13: Added `StreamConnector` bounded buffer for backpressure management
- 2025-10-13: Added alarm/monitoring requirements and critical error handling
- 2025-10-13: Expanded open questions with recommendations for all 8 items
- 2025-10-13: Added design principles for variable batch size tolerance (FR9, FR10)
- 2025-10-13: Added FIFO ordering requirements and test cases
- 2025-10-13: Added parametrized tests for plugin resilience with batch sizes [0, 1, 3, 100, 10000]
- 2025-10-13: Added **determinism as first-class attribute** (FR11):
  - Determinism is **mandatory** for all plugins, like `security_level`
  - 4-level spectrum: `guaranteed` (byte-identical) > `high` (negligible variance) > `low` (distribution-level) > `none` (non-deterministic)
  - Experiment-level aggregation: **Least deterministic wins** (opposite of security resolution)
  - **Cryptographic audit contract**: `determinism: guaranteed` promises auditors can verify via re-execution
  - Signed artifact manifest includes: `determinism_validation`, `plugin_fingerprints`, `data_manifest.hash`, `runtime.seed`
  - Config-time validation with fail-fast and actionable error messages
  - `PluginContext` extended with `determinism_level` field
  - `resolve_determinism_level()` utility (parallel to `resolve_security_level()`)
  - Artifact tagging with determinism level
  - Regulatory compliance support (FDA 21 CFR Part 11, GxP)
- 2025-10-13: Standardized on **Australian Government PSPF security classification system**:
  - Five levels: UNOFFICIAL, OFFICIAL, OFFICIAL_SENSITIVE, PROTECTED, SECRET
  - Hierarchical clearance enforcement (read-up restriction: higher can read lower, not vice versa)
  - Configuration schema validation with enum constraints
  - Artifact pipeline `_check_clearance()` enforcement
  - Legacy level migration utility (public → UNOFFICIAL, internal → OFFICIAL, confidential → OFFICIAL_SENSITIVE, restricted → PROTECTED, secret → SECRET)
  - Audit trail compliance with `classification_authority` metadata
  - All datasources, LLMs, and sinks **require** explicit `security_level` declaration
