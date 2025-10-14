# Configuration Attributability Design

**Date**: October 14, 2025
**Status**: DRAFT - Critical requirement for compliance

---

## Problem Statement

**Current issue**: Configuration is scattered across multiple files with complex merge logic, making it impossible to answer "What exactly ran?" without re-executing the merge.

**Compliance requirement**: Every orchestration run must have a **single, self-contained configuration snapshot** that:
1. Fully describes what ran (orchestrator, plugins, security, parameters)
2. Can be used to reproduce the exact run
3. Serves as audit trail for compliance/security reviews
4. Shows provenance (what defaults/packs contributed)

---

## Current State Analysis

### Configuration Fragmentation

**Example: Experiment Run**

Configuration comes from 3+ sources:

```
User writes:
├── config/settings.yaml           (suite defaults - 100 lines)
├── config/packs/standard.yaml     (prompt pack - 50 lines)
└── config/experiments/sentiment.yaml (experiment - 20 lines)

Runtime resolution:
├── ConfigMerger.merge_scalar()    (last wins)
├── ConfigMerger.merge_list()      (concatenate)
├── ConfigMerger.merge_dict()      (update)
├── resolve_security_level()       (most restrictive)
└── ... (complex merge logic)

Result:
└── Final config (in memory only, never persisted)
```

### Audit Trail Gaps

**Question**: "What LLM middleware was active for run #1234?"

**Current answer path** (BROKEN):
1. Read `outputs/run_1234/metadata.json` → Get experiment name
2. Read `config/experiments/sentiment.yaml` → Check for middleware
3. If not found, read prompt pack → Check pack middleware
4. If not found, read defaults → Check default middleware
5. Apply merge logic: `merge_list("llm_middleware_defs", "llm_middlewares")`
6. Handle normalization: `normalize_early_stop_definitions()`
7. Hope nothing changed since run #1234

**Problems**:
- ❌ 7 steps to answer simple question
- ❌ Requires re-executing merge logic
- ❌ Assumes config files unchanged
- ❌ No guarantee of accuracy

**Desired answer path** (FIXED):
1. Read `outputs/run_1234/config_snapshot.yaml`
2. See complete, resolved config
3. Answer immediately: `middleware: [audit_logger, prompt_shield, health_monitor]`

---

## Proposed Architecture

### Component 1: Configuration Resolver

**Location**: `core/configuration/resolver.py`

**Purpose**: Resolve all configuration into canonical, self-contained structure

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class ResolvedConfiguration:
    """Complete, self-contained orchestration configuration.

    This is the single source of truth for what ran.
    Saved as artifact for every run.
    """

    # Meta
    version: str = "1.0"                    # Config schema version
    orchestrator: str                       # e.g., "experiment", "batch_processing"
    run_id: str                             # Unique run identifier
    timestamp: str                          # ISO 8601 timestamp

    # Orchestrator-specific config
    orchestrator_config: dict[str, Any]     # Full config for orchestrator

    # Universal plugin configs (resolved, not references)
    datasource: dict[str, Any]              # Complete datasource config
    llm_client: dict[str, Any]              # Complete LLM config
    llm_middleware: list[dict[str, Any]]    # All middleware (resolved order)
    sinks: list[dict[str, Any]]             # All sinks (resolved order)

    # Security context
    security_level: str                     # Resolved security level
    determinism_level: str                  # Resolved determinism level

    # Provenance tracking
    provenance: dict[str, Any]              # Where each value came from
    source_files: dict[str, str]            # Hash of each source file

    # Reproducibility
    elspeth_version: str                    # Elspeth version
    python_version: str                     # Python version
    environment: dict[str, str]             # Relevant env vars (no secrets)


class ConfigurationResolver:
    """Resolve configuration into canonical form."""

    def resolve(
        self,
        *,
        orchestrator_type: str,
        defaults: dict[str, Any],
        packs: dict[str, dict[str, Any]],
        config: dict[str, Any],
    ) -> ResolvedConfiguration:
        """Resolve layered configs into single canonical config.

        Returns:
            ResolvedConfiguration with ALL values resolved and provenance tracked
        """

        # Perform merge (existing logic)
        merged = self._merge_configs(defaults, packs, config)

        # Track provenance (NEW)
        provenance = self._build_provenance(defaults, packs, config, merged)

        # Resolve plugin definitions to complete configs
        datasource_config = self._resolve_datasource(merged)
        llm_config = self._resolve_llm(merged)
        middleware_configs = self._resolve_middleware(merged)
        sink_configs = self._resolve_sinks(merged)

        # Extract orchestrator-specific config
        orchestrator_config = self._extract_orchestrator_config(
            orchestrator_type, merged
        )

        return ResolvedConfiguration(
            orchestrator=orchestrator_type,
            run_id=self._generate_run_id(),
            timestamp=self._iso_timestamp(),
            orchestrator_config=orchestrator_config,
            datasource=datasource_config,
            llm_client=llm_config,
            llm_middleware=middleware_configs,
            sinks=sink_configs,
            security_level=merged["security_level"],
            determinism_level=merged.get("determinism_level", "none"),
            provenance=provenance,
            source_files=self._hash_source_files([defaults, packs, config]),
            elspeth_version=get_version(),
            python_version=sys.version,
            environment=self._capture_environment(),
        )

    def _build_provenance(
        self,
        defaults: dict,
        packs: dict,
        config: dict,
        merged: dict,
    ) -> dict[str, Any]:
        """Track where each merged value originated.

        Returns:
            {
                "security_level": {
                    "value": "OFFICIAL",
                    "source": "defaults",
                    "file": "config/settings.yaml",
                    "line": 12
                },
                "llm_middleware": {
                    "value": ["audit_logger", "prompt_shield"],
                    "sources": [
                        {"name": "audit_logger", "from": "pack:standard"},
                        {"name": "prompt_shield", "from": "config:sentiment"}
                    ]
                },
                ...
            }
        """
        # Implementation tracks each merge decision
        pass
```

### Component 2: Configuration Snapshot Sink

**Location**: `plugins/data_output/config_snapshot.py`

**Purpose**: Automatically save resolved config for every run

```python
class ConfigSnapshotSink:
    """Saves resolved configuration as artifact for audit trail."""

    name = "config_snapshot"

    def __init__(
        self,
        output_path: str = "config_snapshot.yaml",
        format: str = "yaml",  # yaml, json, toml
        include_provenance: bool = True,
    ):
        self.output_path = output_path
        self.format = format
        self.include_provenance = include_provenance

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any]) -> None:
        """Write resolved configuration snapshot."""

        # Extract resolved config from metadata
        resolved_config: ResolvedConfiguration = metadata["resolved_config"]

        # Serialize
        if self.format == "yaml":
            content = yaml.dump(asdict(resolved_config), sort_keys=False)
        elif self.format == "json":
            content = json.dumps(asdict(resolved_config), indent=2)
        else:
            raise ValueError(f"Unsupported format: {self.format}")

        # Write to output path
        output_file = Path(self.output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content)

        # Also produce artifact for pipeline
        self._artifact = Artifact(
            id="config_snapshot",
            type="config",
            path=str(output_file),
            security_level=resolved_config.security_level,
            determinism_level=resolved_config.determinism_level,
            metadata={
                "run_id": resolved_config.run_id,
                "orchestrator": resolved_config.orchestrator,
                "timestamp": resolved_config.timestamp,
            },
        )

    def produces(self) -> list[ArtifactDescriptor]:
        return [
            ArtifactDescriptor(
                name="config_snapshot",
                type="config",
                persist=True,
            )
        ]

    def collect_artifacts(self) -> dict[str, Artifact]:
        return {"config_snapshot": self._artifact}
```

**Integration**: This sink is **automatically added** to every orchestration run (user can disable).

### Component 3: Example Snapshot

**What gets saved**: `outputs/run_1234/config_snapshot.yaml`

```yaml
# Elspeth Configuration Snapshot
# This is the complete, resolved configuration for this run.
# Use this to reproduce the exact run or for audit trails.

version: "1.0"
orchestrator: experiment
run_id: run_1234_sentiment_analysis_20251014_143022
timestamp: "2025-10-14T14:30:22.123456Z"

# ORCHESTRATOR CONFIGURATION
orchestrator_config:
  experiment_name: sentiment_analysis
  temperature: 0.7
  max_tokens: 1000
  prompt_system: "You are a sentiment analysis assistant."
  prompt_template: "Analyze the sentiment of: {{ text }}"
  prompt_fields: [text]
  baseline: sentiment_baseline
  concurrency_config:
    max_workers: 10
    timeout: 30

# DATA INPUT
datasource:
  plugin: csv_blob
  options:
    config_path: data/reviews.csv
    profile: prod_storage
    security_level: OFFICIAL
  resolved_path: "azblob://prodstore/reviews.csv"
  row_count: 1000

# LLM CLIENT
llm_client:
  plugin: azure_openai
  options:
    deployment: gpt-4
    api_version: "2024-08-01"
    endpoint: "https://prod-openai.openai.azure.com"
    security_level: OFFICIAL
  resolved_endpoint: "https://prod-openai.openai.azure.com"

# LLM MIDDLEWARE (in execution order)
llm_middleware:
  - name: audit_logger
    options:
      log_level: INFO
      redact_prompts: false
    source: pack:standard
    order: 1

  - name: prompt_shield
    options:
      block_jailbreaks: true
      block_injections: true
    source: pack:standard
    order: 2

  - name: health_monitor
    options:
      alert_on_error: true
      timeout_seconds: 30
    source: config:sentiment
    order: 3

# SINKS (in execution order)
sinks:
  - name: csv_results
    plugin: csv_file
    options:
      output_path: outputs/run_1234/results.csv
      security_level: OFFICIAL
    order: 1

  - name: analytics
    plugin: analytics_report
    options:
      output_path: outputs/run_1234/analytics.json
      security_level: OFFICIAL
    order: 2
    consumes: [csv_results]

  - name: config_snapshot  # ★ Auto-added
    plugin: config_snapshot
    options:
      output_path: outputs/run_1234/config_snapshot.yaml
      security_level: OFFICIAL
    order: 0  # Runs first

# EXPERIMENT-SPECIFIC PLUGINS
row_plugins:
  - name: score_extractor
    options:
      score_field: sentiment_score
    source: pack:standard

aggregation_plugins:
  - name: statistics
    options:
      metrics: [mean, std, median]
    source: defaults

validation_plugins: []
early_stop_plugins: []
baseline_plugins:
  - name: frequentist_comparison
    options:
      alpha: 0.05
    source: defaults

# SECURITY CONTEXT
security_level: OFFICIAL  # Most restrictive from datasource + LLM
determinism_level: low

# PROVENANCE TRACKING
provenance:
  security_level:
    value: OFFICIAL
    source: datasource
    resolution: "most_restrictive(datasource.OFFICIAL, llm.OFFICIAL) = OFFICIAL"

  temperature:
    value: 0.7
    source: config:sentiment
    file: config/experiments/sentiment.yaml
    line: 15

  llm_middleware:
    sources:
      - {name: audit_logger, from: pack:standard, file: config/packs/standard.yaml}
      - {name: prompt_shield, from: pack:standard, file: config/packs/standard.yaml}
      - {name: health_monitor, from: config:sentiment, file: config/experiments/sentiment.yaml}

  prompt_system:
    value: "You are a sentiment analysis assistant."
    source: pack:standard
    file: config/packs/standard.yaml
    line: 25

# SOURCE FILES (for integrity checking)
source_files:
  config/settings.yaml: sha256:a1b2c3d4...
  config/packs/standard.yaml: sha256:e5f6g7h8...
  config/experiments/sentiment.yaml: sha256:i9j0k1l2...

# REPRODUCIBILITY
elspeth_version: 2.5.0
python_version: "3.11.5"
environment:
  ELSPETH_ENV: production
  # No secrets included
```

---

## Integration with Orchestrators

### Orchestrator Responsibility

Each orchestrator type **must** produce a `ResolvedConfiguration`:

```python
# plugins/orchestrators/experiment/runner.py
class ExperimentOrchestrator:
    def run(
        self,
        data: pd.DataFrame,
        config: dict[str, Any],
        *,
        defaults: dict[str, Any],
        packs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        # Step 1: Resolve configuration
        resolver = ConfigurationResolver()
        resolved_config = resolver.resolve(
            orchestrator_type="experiment",
            defaults=defaults,
            packs=packs,
            config=config,
        )

        # Step 2: Add to metadata for all plugins
        metadata = {
            "resolved_config": resolved_config,
            "run_id": resolved_config.run_id,
            "security_level": resolved_config.security_level,
        }

        # Step 3: Run orchestration using resolved config
        results = self._execute(data, resolved_config, metadata)

        # Step 4: Config snapshot is automatically saved by sink
        return results
```

### User Configuration (Simplified)

Users still write layered configs (for convenience), but **resolution happens at runtime**:

```yaml
# config/experiments/sentiment.yaml (user writes this)
name: sentiment_analysis
temperature: 0.7
llm_middleware:
  - name: health_monitor
    options:
      alert_on_error: true

# At runtime, merged with defaults + packs → produces config_snapshot.yaml
```

---

## Benefits

### 1. Single Source of Truth

**Before**:
```
"What ran?" → Reconstruct from 3 files + merge logic
```

**After**:
```
"What ran?" → Read config_snapshot.yaml
```

### 2. Audit Trail

**Compliance question**: "Prove run #1234 used OFFICIAL security"

**Answer**:
```bash
$ cat outputs/run_1234/config_snapshot.yaml | grep security_level
security_level: OFFICIAL

$ cat outputs/run_1234/config_snapshot.yaml | grep -A 5 provenance
provenance:
  security_level:
    value: OFFICIAL
    source: datasource
    resolution: "most_restrictive(datasource.OFFICIAL, llm.OFFICIAL)"
```

### 3. Reproducibility

**Reproduce exact run**:
```bash
# Extract config from old run
$ cp outputs/run_1234/config_snapshot.yaml reproduce_config.yaml

# Run with same config
$ elspeth run --from-snapshot reproduce_config.yaml
```

### 4. Change Tracking

**See what changed between runs**:
```bash
$ diff outputs/run_1234/config_snapshot.yaml \
       outputs/run_1235/config_snapshot.yaml

> temperature: 0.7
< temperature: 0.5
```

### 5. Provenance Transparency

**See where each value came from**:
```yaml
provenance:
  temperature:
    value: 0.7
    source: config:sentiment
    file: config/experiments/sentiment.yaml
    line: 15
```

---

## Implementation Plan

### Phase 1: Configuration Resolver (2-3 hours)
- [ ] Create `core/configuration/resolver.py`
- [ ] Implement `ResolvedConfiguration` dataclass
- [ ] Implement `ConfigurationResolver.resolve()`
- [ ] Add provenance tracking

### Phase 2: Config Snapshot Sink (1 hour)
- [ ] Create `plugins/data_output/config_snapshot.py`
- [ ] Register in sink registry
- [ ] Make it auto-added to all runs

### Phase 3: Orchestrator Integration (2-3 hours)
- [ ] Update `ExperimentOrchestrator` to use resolver
- [ ] Pass resolved config to all plugins via metadata
- [ ] Update suite runner to resolve before each experiment

### Phase 4: CLI Support (1-2 hours)
- [ ] Add `--from-snapshot` flag to reproduce from snapshot
- [ ] Add `--no-snapshot` flag to disable snapshot sink
- [ ] Add validation for snapshot schema

### Phase 5: Testing & Docs (2-3 hours)
- [ ] Test snapshot generation for all orchestrators
- [ ] Test reproduction from snapshot
- [ ] Document snapshot format and provenance model
- [ ] Add compliance guide showing audit workflows

**Total**: 8-12 hours

---

## Configuration Schema Versioning

**Problem**: Snapshot format may evolve

**Solution**: Version field + migration path

```yaml
# Version 1.0 (current)
version: "1.0"
orchestrator: experiment
# ...

# Version 2.0 (future - adds telemetry)
version: "2.0"
orchestrator: experiment
telemetry_config:  # NEW field
  enabled: true
# ...
```

**Backward compatibility**:
```python
class SnapshotLoader:
    def load(self, snapshot_path: str) -> ResolvedConfiguration:
        raw = yaml.safe_load(Path(snapshot_path).read_text())
        version = raw.get("version", "1.0")

        if version == "1.0":
            return self._load_v1(raw)
        elif version == "2.0":
            return self._load_v2(raw)
        else:
            raise ValueError(f"Unsupported snapshot version: {version}")
```

---

## Open Questions

### Q1: Snapshot Storage Location

**Option A**: With results (proposed)
```
outputs/run_1234/
├── results.csv
├── analytics.json
└── config_snapshot.yaml  # Co-located with results
```
**Pro**: Everything for a run in one place
**Con**: Duplicates config if multiple experiments in suite

**Option B**: Separate config archive
```
configs/snapshots/
└── run_1234_config_snapshot.yaml
```
**Pro**: Centralized config management
**Con**: Separated from results, harder to find

**Recommendation**: Option A - co-locate with results

### Q2: Secrets in Snapshots

**Question**: How to handle secrets in resolved config?

**Option A**: Redact all secrets (proposed)
```yaml
llm_client:
  plugin: azure_openai
  options:
    api_key: "[REDACTED]"  # Never include secrets
    endpoint: "https://prod-openai.openai.azure.com"
```

**Option B**: Store encrypted
```yaml
llm_client:
  plugin: azure_openai
  options:
    api_key: "encrypted:a1b2c3d4..."
    endpoint: "https://prod-openai.openai.azure.com"
```

**Recommendation**: Option A - always redact, never store secrets

### Q3: Snapshot as Input Format

**Question**: Should users be able to WRITE snapshots directly (skip layering)?

**Option A**: Yes, snapshots are valid input
- User can write `config_snapshot.yaml` directly
- Skip defaults/packs/merge if input is snapshot
- Pro: Simple, explicit, self-contained
- Con: Verbose for users

**Option B**: No, snapshots are output-only
- Users must write layered configs
- Snapshots only for output/reproduction
- Pro: Keeps user configs concise
- Con: Can't hand-write self-contained config

**Recommendation**: Option A - support both input modes

---

## Success Criteria

- [ ] Every run produces `config_snapshot.yaml`
- [ ] Snapshot is self-contained (no external references)
- [ ] Can reproduce run from snapshot: `elspeth run --from-snapshot config_snapshot.yaml`
- [ ] Provenance tracks where every value originated
- [ ] Snapshot includes integrity hashes of source files
- [ ] Compliance audit can answer "what ran?" in <30 seconds
- [ ] Change tracking via `diff` on snapshots is meaningful

---

## Appendix: Real-World Audit Scenarios

### Scenario 1: Security Incident

**Incident**: PII detected in output file

**Questions**:
1. What security level was configured?
2. What middleware was active?
3. Was PII redaction enabled?
4. What datasource was used?

**With snapshots**:
```bash
$ cat outputs/run_1234/config_snapshot.yaml | grep security_level
security_level: OFFICIAL  # ← Should have been PROTECTED

$ cat outputs/run_1234/config_snapshot.yaml | grep -A 20 llm_middleware
llm_middleware:
  - name: audit_logger
  - name: prompt_shield
  # ← Missing pii_redaction middleware!

$ cat outputs/run_1234/config_snapshot.yaml | grep -A 10 datasource
datasource:
  plugin: csv_local
  options:
    path: customer_data_PROTECTED.csv  # ← Security mismatch!
```

**Root cause identified**: Security level downgrade + missing redaction

### Scenario 2: Reproducibility Challenge

**Request**: "Re-run experiment from 6 months ago with same config"

**With snapshots**:
```bash
# Retrieve snapshot from archive
$ cp archive/2024-04-14/config_snapshot.yaml reproduce.yaml

# Verify integrity
$ cat reproduce.yaml | grep source_files
source_files:
  config/settings.yaml: sha256:a1b2c3d4...
  # Compare hashes to detect drift

# Reproduce exact run
$ elspeth run --from-snapshot reproduce.yaml

# Results will be identical (except timestamps)
```

### Scenario 3: Change Control

**Question**: "What changed between v1 and v2 of the model?"

**With snapshots**:
```bash
$ diff outputs/v1_run/config_snapshot.yaml \
       outputs/v2_run/config_snapshot.yaml

< temperature: 0.7
> temperature: 0.5

< prompt_system: "You are a helpful assistant."
> prompt_system: "You are an expert sentiment analyst."

< - name: basic_validator
> - name: advanced_validator
```

**Answer**: Temperature, prompt, and validator changed
