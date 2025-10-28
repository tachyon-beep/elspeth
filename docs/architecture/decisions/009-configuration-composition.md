# ADR-009 – Configuration Composition & Validation

## Status

**DRAFT** (2025-10-26)

**Priority**: P1 (Next Sprint)

## Context

Elspeth's configuration system supports multiple layers of composition to enable reusability and progressive refinement:
- **Suite defaults** (`config/suite_defaults.yaml`) – Global baseline
- **Prompt packs** (optional) – Reusable experiment templates
- **Experiment overrides** – Per-experiment customization

This three-layer merge enables "configuration as code" patterns where teams share prompt packs and override specific parameters per experiment. However, the configuration merge order, deep merge semantics, and validation pipeline are extensively documented (`docs/architecture/configuration-security.md`, 25KB) but **not formalized as an ADR**.

### Current State

**Implemented and Working**:
- ✅ Three-layer configuration merge
- ✅ Deep merge semantics (dict merge, list concat, scalar replace)
- ✅ Fail-fast validation at each layer
- ✅ Schema validation before plugin instantiation
- ✅ Comprehensive documentation (25KB guide)

**Problems**:
1. **No Canonical Truth**: Configuration behavior documented but not architecturally mandated
2. **User Confusion**: Merge order non-obvious (which layer wins?)
3. **Debugging Difficulty**: Configuration errors reported late (after merge)
4. **No ADR Authority**: When conflicts arise, no authoritative decision to reference

### User Pain Points

Configuration errors are the **#1 user frustration** (per documentation):
- "Why did my experiment override not work?" (merge order confusion)
- "Where did this value come from?" (debugging merged config)
- "Can I override a list or does it concat?" (deep merge semantics)
- "When is config validated?" (validation timing)

### Need for Formal Decision

Teams need:
1. **Explicit precedence rules** when layers conflict
2. **Deep merge semantics** formally defined (dict vs list vs scalar)
3. **Validation pipeline** architecture (when/where/how)
4. **Error handling** guarantees (fail-fast vs fail-later)

## Decision

We will formalize the **Configuration Composition & Validation Pipeline** architecture with explicit precedence rules, deep merge semantics, and fail-fast validation at each layer.

### Architecture Overview

```
Layer 1: Suite Defaults (config/suite_defaults.yaml)
   ↓ Deep merge
Layer 2: Prompt Pack (if specified)
   ↓ Deep merge
Layer 3: Experiment Override (per-experiment config)
   ↓ Validation pipeline
Final Configuration → Plugin Instantiation
```

---

## Part 1: Configuration Merge Order

### Precedence Rules (Lowest to Highest Priority)

**Precedence Order**:
1. **Suite Defaults** (lowest priority) – Global baseline, overridden by all layers
2. **Prompt Pack** (medium priority) – Overrides suite defaults, overridden by experiments
3. **Experiment Override** (highest priority) – Final say, overrides all

**Example**:
```yaml
# Layer 1: Suite defaults
llm:
  model: "gpt-3.5-turbo"
  temperature: 0.7
  max_tokens: 1000
  # ❌ FORBIDDEN: allow_downgrade NOT in config (ADR-002-B)
  #    Plugins declare security policy in code, not config

# Layer 2: Prompt pack
llm:
  temperature: 0.9  # Overrides suite default

# Layer 3: Experiment override
llm:
  max_tokens: 2000  # Overrides suite default

# Final merged config:
llm:
  model: "gpt-3.5-turbo"      # From suite defaults
  temperature: 0.9            # From prompt pack (overrides suite)
  max_tokens: 2000            # From experiment (overrides suite)
  # Security policy (allow_downgrade) declared in plugin code, not here
```

**Note**: Security policy fields (`security_level`, `allow_downgrade`) are **forbidden in configuration** per ADR-002-B (Immutable Security Policy Metadata). These fields are plugin-author-owned and declared in code.

**Rationale**: Higher layers are more specific, should have final say.

---

## Part 2: Deep Merge Semantics

### Merge Rules by Data Type

#### Rule 1: Dictionaries → Deep Merge (Recursive)

Nested dictionaries are merged recursively, not replaced:

```yaml
# Layer 1: Suite defaults
llm_config:
  model: "gpt-3.5-turbo"
  temperature: 0.7
  retry:
    max_attempts: 3

# Layer 2: Experiment override
llm_config:
  temperature: 0.9
  retry:
    backoff: exponential

# Result: Deep merge (NOT dict replace)
llm_config:
  model: "gpt-3.5-turbo"      # From layer 1 (not overridden)
  temperature: 0.9            # From layer 2 (overrides layer 1)
  retry:
    max_attempts: 3           # From layer 1 (not overridden)
    backoff: exponential      # From layer 2 (adds new key)
```

**Rationale**: Deep merge preserves defaults while allowing targeted overrides.

#### Rule 2: Lists → Concatenation (Union)

Lists are concatenated (union), not replaced:

```yaml
# Layer 1: Suite defaults
sinks:
  - type: csv_file
  - type: json_file

# Layer 2: Experiment override
sinks:
  - type: excel_file

# Result: Concatenation (NOT list replace)
sinks:
  - type: csv_file       # From layer 1
  - type: json_file      # From layer 1
  - type: excel_file     # From layer 2
```

**Exception: Explicit Replace**:
To replace instead of concatenate, use `__replace__` marker:

```yaml
# Experiment override with replace marker
sinks:
  __replace__: true
  value:
    - type: excel_file

# Result: Replace (discard layer 1)
sinks:
  - type: excel_file     # Only layer 2, layer 1 discarded
```

**Deduplication Guidance**: Because union is the default, lists should include
stable identifiers (e.g., `name:` fields) so downstream validation can detect
duplicates. If a sink may only appear once, authors should either use
`__replace__` or rely on validation rules that error when duplicate identifiers
are encountered.

**Rationale**: Concatenation is safer default (additive), replace is opt-in.

#### Rule 3: Scalars → Replace (Last Wins)

Scalar values (strings, numbers, booleans) are replaced, not merged:

```yaml
# Layer 1: Suite defaults
temperature: 0.7

# Layer 2: Experiment override
temperature: 0.9

# Result: Replace (last wins)
temperature: 0.9
```

**Rationale**: Scalars cannot be "merged", replacement is only option.

### Null Handling

**Null/None values are IGNORED** (do not override):

```yaml
# Layer 1: Suite defaults
temperature: 0.7

# Layer 2: Experiment override
temperature: null   # Ignored, does not override

# Result: Layer 1 value preserved
temperature: 0.7
```

**Explicit Deletion**:
To delete a key, use `__delete__` marker:

```yaml
# Experiment override with delete marker
temperature:
  __delete__: true

# Result: Key removed from final config
# (temperature not present)
```

**Rationale**: Null is often accidental (missing value), explicit deletion prevents accidents.

---

## Part 2.5: Security Policy Field Exclusion (ADR-002-B Integration)

### Forbidden Configuration Fields

Per **ADR-002-B** (Immutable Security Policy Metadata), the following fields **MUST NOT** appear in configuration YAML at any layer:

- `security_level: SecurityLevel` – Plugin's clearance (code-declared)
- `allow_downgrade: bool` – Downgrade permission (code-declared)
- `max_operating_level: SecurityLevel` – Future: upper bound on operations

**Rationale**: Security policy is a property of the **plugin implementation**, not the **deployment configuration**. Operators choose *which plugin* to use, not *how secure* that plugin behaves.

### Registry Enforcement

Plugin registries (ADR-008) reject schemas exposing forbidden fields:

```python
# src/elspeth/core/registries/base.py
class BasePluginRegistry(Generic[T]):
    FORBIDDEN_CONFIG_FIELDS = frozenset({
        "security_level",
        "allow_downgrade",
        "max_operating_level",
    })

    def register(self, plugin_name: str, plugin_class: type[T], config_schema: dict | None = None):
        if config_schema:
            properties = config_schema.get("properties", {})
            exposed_fields = self.FORBIDDEN_CONFIG_FIELDS & set(properties.keys())

            if exposed_fields:
                raise RegistrationError(
                    f"Plugin '{plugin_name}' schema exposes forbidden security policy fields: "
                    f"{exposed_fields}. These are author-owned and immutable (ADR-002-B)."
                )
```

### Configuration Merge Behavior

If forbidden fields appear in YAML (legacy configs, user error):

**Checkpoint 1 (Layer Load)**: Parse YAML successfully (no syntax error)

**Checkpoint 2 (Post-Merge)**: Detect forbidden fields, abort:

```python
def validate_no_security_policy_fields(config: dict) -> None:
    """Ensure configuration doesn't override security policy (ADR-002-B)."""
    forbidden = {"security_level", "allow_downgrade", "max_operating_level"}

    def check_recursively(obj: dict, path: str = ""):
        for key, value in obj.items():
            if key in forbidden:
                raise ConfigurationError(
                    f"Security policy field '{key}' found in configuration at path '{path}.{key}'. "
                    f"These fields are plugin-author-owned and immutable (ADR-002-B). "
                    f"Remove from YAML - plugins declare security policy in code via "
                    f"BasePlugin.__init__(security_level=..., allow_downgrade=...)."
                )
            if isinstance(value, dict):
                check_recursively(value, f"{path}.{key}")

    check_recursively(config)
```

**Error Example**:
```
ConfigurationError: Security policy field 'allow_downgrade' found in configuration at path 'plugins.datasource.allow_downgrade'. These fields are plugin-author-owned and immutable (ADR-002-B). Remove from YAML - plugins declare security policy in code via BasePlugin.__init__(security_level=..., allow_downgrade=...).
```

### Migration Guide (For Existing Configs)

**Before (invalid after ADR-002-B)**:
```yaml
datasource:
  type: "csv_local"
  path: "data.csv"
  allow_downgrade: true  # ❌ Forbidden!
```

**After (ADR-002-B compliant)**:
```yaml
datasource:
  type: "csv_local"
  path: "data.csv"
  # ✅ Security policy declared in plugin code (CsvLocalDataSource.__init__)
```

**Plugin Code** (where security policy belongs):
```python
class CsvLocalDataSource(BasePlugin, DataSource):
    def __init__(self, *, path: str):
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ← Code-declared
            allow_downgrade=True,                      # ← Code-declared
        )
        self.path = path
```

### Cross-References

- [ADR-002-B](002-b-security-policy-metadata.md) – Full specification of immutable security policy
- [ADR-008](008-unified-registry-pattern.md) – Registry validation enforcement
- [ADR-005](005-frozen-plugin-capability.md) – `allow_downgrade` semantics

---

## Part 3: Validation Pipeline

### Validation Layers

Configuration is validated at **three checkpoints** (fail-fast at each):

#### Checkpoint 1: Layer Load Validation

**When**: As each layer is loaded (suite defaults, prompt pack, experiment)

**What**: YAML syntax, basic structure

**Failures**: Abort immediately (cannot proceed with invalid YAML)

```python
# Load and validate each layer
try:
    suite_defaults = yaml.safe_load(suite_defaults_path)
    validate_yaml_structure(suite_defaults)
except yaml.YAMLError as exc:
    raise ConfigurationError(f"Invalid YAML in suite defaults: {exc}")
```

#### Checkpoint 2: Post-Merge Validation

**When**: After merging all layers

**What**: Required fields present, type correctness

**Failures**: Abort before plugin instantiation

```python
# Validate merged configuration
merged_config = deep_merge(suite_defaults, prompt_pack, experiment_override)
validate_required_fields(merged_config, required=["datasource", "llm", "sinks"])
validate_field_types(merged_config)
```

#### Checkpoint 3: Schema Validation

**When**: Before plugin instantiation

**What**: Plugin-specific JSON schema validation

**Failures**: Abort with detailed schema error

```python
# Validate against plugin schema
datasource_config = merged_config["datasource"]
datasource_schema = datasource_registry.get_schema(datasource_config["type"])
jsonschema.validate(datasource_config, datasource_schema)
```

### Fail-Fast Principle (ADR-001)

**All validation failures abort immediately** (fail-closed):
- ❌ **FORBIDDEN**: Log warning and proceed with defaults
- ✅ **REQUIRED**: Raise `ConfigurationError` and abort

**Rationale**: Configuration errors are security-critical (ADR-001 priority #1). Silent failures create attack surfaces.

---

## Part 4: Configuration Sources

### Suite Defaults (`config/suite_defaults.yaml`)

**Purpose**: Global baseline for all experiments

**Scope**: Entire suite

**Override**: Overridden by prompt pack and experiment

**Security**: Read-only (cannot be modified by experiments)

**Example**:
```yaml
# config/suite_defaults.yaml
llm:
  model: "gpt-3.5-turbo"
  temperature: 0.7
  max_tokens: 1000

sinks:
  - type: csv_file
    path: "./outputs/"
```

### Prompt Packs (Optional)

**Purpose**: Reusable experiment templates (e.g., "summarization_prompts", "qa_prompts")

**Scope**: Specific prompt family

**Override**: Overrides suite defaults, overridden by experiment

**Security**: Read-only (shipped with Elspeth or team-shared)

**Example**:
```yaml
# config/prompt_packs/summarization.yaml
llm:
  temperature: 0.3  # Lower for deterministic summaries
  system_prompt: "You are a summarization assistant..."

prompts:
  - name: "brief_summary"
    template: "Summarize the following in 2-3 sentences: {{text}}"
```

### Experiment Overrides

**Purpose**: Per-experiment customization

**Scope**: Single experiment

**Override**: Highest priority, overrides all

**Security**: User-provided (validation critical)

**Example**:
```yaml
# experiments/experiment_001.yaml
llm:
  max_tokens: 2000  # Override suite default

prompts:
  - name: "custom_prompt"
    template: "Custom template for this experiment..."
```

---

## Part 5: Error Handling

### Configuration Error Taxonomy

#### 1. Syntax Errors (Checkpoint 1)

**Type**: Invalid YAML syntax

**Detection**: Layer load validation

**Error Message**: Line number, syntax issue

**Example**:
```
ConfigurationError: Invalid YAML in suite_defaults.yaml:
  Line 15: mapping values are not allowed here
```

#### 2. Structure Errors (Checkpoint 2)

**Type**: Missing required fields, wrong types

**Detection**: Post-merge validation

**Error Message**: Missing field, expected type

**Example**:
```
ConfigurationError: Missing required field 'datasource' in merged configuration
ConfigurationError: Field 'temperature' must be float, got str
```

#### 3. Schema Errors (Checkpoint 3)

**Type**: Plugin schema violation

**Detection**: Schema validation (jsonschema)

**Error Message**: Schema path, constraint, actual value

**Example**:
```
ConfigurationError: Schema validation failed for datasource:
  Path: /datasource/config/file_path
  Error: 'file_path' is required but not present
```

### Error Recovery (None)

**No automatic error recovery** (fail-fast, ADR-001):
- ❌ **FORBIDDEN**: Use default values on error
- ❌ **FORBIDDEN**: Skip invalid sections
- ✅ **REQUIRED**: Abort with clear error message

**Rationale**: Silent recovery hides configuration errors, leads to unexpected behavior.

---

## Consequences

### Benefits

1. **Predictable Behavior**: Merge order and semantics explicitly defined
2. **Fail-Fast**: Errors detected early (before plugin instantiation)
3. **Debuggability**: Clear precedence rules aid debugging
4. **Reusability**: Prompt packs enable "configuration as code"
5. **Security**: Validation at every layer (ADR-001 fail-closed)
6. **Documentation**: Canonical truth for configuration behavior

### Limitations / Trade-offs

1. **Complexity**: Three-layer merge more complex than single config file
   - *Mitigation*: Documentation with examples, validation errors explain merge

2. **Debugging Difficulty**: "Where did this value come from?" still requires trace
   - *Mitigation*: Configuration audit trail (log merge provenance)

3. **Performance Overhead**: Validation at each layer adds latency
   - *Mitigation*: Acceptable (configuration load is one-time, ~100ms)

4. **List Concatenation**: Default concat may surprise users expecting replace
   - *Mitigation*: `__replace__` marker for explicit control, documented

5. **Null Handling**: Ignored nulls may confuse users
   - *Mitigation*: `__delete__` marker for explicit deletion, validation errors explain

### Future Enhancements (Post-1.0)

1. **Configuration Diff Tool**: Show effective config after merge
   - `elspeth config diff --suite suite.yaml --experiment exp.yaml`

2. **Merge Provenance**: Track which layer contributed each value
   - Logged during merge for debugging

3. **Configuration Validation CLI**: Validate without running
   - `elspeth config validate --suite suite.yaml --experiment exp.yaml`

4. **Configuration Templates**: Jinja2 templating in config files
   - `temperature: {{ env.TEMPERATURE | default(0.7) }}`

5. **Environment Variable Override**: CLI flags override config
   - `--temperature 0.9` overrides merged config

### Implementation Checklist

**Phase 1: Documentation** (P1, 2-3 hours):
- [x] Configuration merge documented (25KB guide exists)
- [ ] Formalize as ADR (this document)
- [ ] Update plugin authoring guide with merge examples
- [ ] Add troubleshooting guide for common config errors

**Phase 2: Validation Enhancement** (P1, 1-2 hours):
- [ ] Add merge provenance logging (debug mode)
- [ ] Enhance validation error messages (show merge context)
- [ ] Add `__replace__` and `__delete__` marker support

**Phase 3: Tooling** (P2, post-1.0):
- [ ] Configuration diff tool
- [ ] Configuration validation CLI
- [ ] Configuration templates (Jinja2)

### Related ADRs

- **ADR-001**: Design Philosophy – Fail-fast principle, security-first
- **ADR-007**: Unified Registry Pattern – Schema validation at registration
- **ADR-010**: Error Classification & Recovery – Configuration error taxonomy

### Implementation References

- `src/elspeth/core/config.py` – Configuration merge logic
- `src/elspeth/core/validation/settings.py` – Settings validation
- `src/elspeth/core/validation/suite.py` – Suite validation
- `src/elspeth/core/validation/schema.py` – Schema validation
- `docs/architecture/configuration-security.md` – 25KB comprehensive guide

---

**Document Status**: DRAFT – Requires review and acceptance
**Next Steps**:
1. Review with team (merge semantics approval)
2. Implement `__replace__` and `__delete__` markers
3. Add merge provenance logging
4. Update plugin authoring guide
