# ADR-009 – Configuration Composition & Validation (LITE)

## Status

**DRAFT** (2025-10-26) | **Priority**: P1

## Context

Elspeth supports three-layer configuration composition:
- Suite defaults (`suite_defaults.yaml`) – Global baseline
- Prompt packs (optional) – Reusable templates
- Experiment overrides – Per-experiment customization

**Problems**:
- No canonical merge order authority
- User confusion ("which layer wins?")
- Late error reporting (after merge)
- Merge semantics undocumented (dict vs list vs scalar)

## Decision

Formalize **Configuration Composition & Validation Pipeline** with explicit precedence, deep merge semantics, fail-fast validation.

### Architecture

```
Layer 1: Suite Defaults → Layer 2: Prompt Pack → Layer 3: Experiment Override
  ↓ Deep merge              ↓ Deep merge              ↓ Validation pipeline
                          Final Configuration → Plugin Instantiation
```

## Part 1: Merge Order (Precedence Rules)

**Lowest to Highest Priority**:
1. **Suite Defaults** (lowest) – Global baseline, overridden by all
2. **Prompt Pack** (medium) – Overrides defaults, overridden by experiments
3. **Experiment Override** (highest) – Final say, overrides all

**Example**:
```yaml
# Layer 1: Suite defaults
llm:
  model: "gpt-3.5-turbo"
  temperature: 0.7
  max_tokens: 1000
  # ❌ FORBIDDEN: allow_downgrade (ADR-002-B - security policy in code, not config)

# Layer 2: Prompt pack
llm:
  temperature: 0.9  # Overrides suite default

# Layer 3: Experiment override
llm:
  max_tokens: 2000  # Overrides suite default

# Final merged:
llm:
  model: "gpt-3.5-turbo"      # From layer 1
  temperature: 0.9            # From layer 2 (overrides 1)
  max_tokens: 2000            # From layer 3 (overrides 1)
```

**Note**: Security fields (`security_level`, `allow_downgrade`) **forbidden in config** (ADR-002-B). Plugin authors declare in code.

## Part 2: Deep Merge Semantics

### Rule 1: Dictionaries → Deep Merge (Recursive)

```yaml
# Layer 1
llm_config:
  model: "gpt-3.5"
  temperature: 0.7
  retry:
    max_attempts: 3

# Layer 2
llm_config:
  temperature: 0.9
  retry:
    backoff: exponential

# Result: Deep merge (NOT replace)
llm_config:
  model: "gpt-3.5"           # From 1
  temperature: 0.9           # From 2 (overrides 1)
  retry:
    max_attempts: 3          # From 1
    backoff: exponential     # From 2 (adds new)
```

### Rule 2: Lists → Concatenation (Union)

```yaml
# Layer 1
sinks:
  - type: csv_file
  - type: json_file

# Layer 2
sinks:
  - type: excel_file

# Result: Concatenation (NOT replace)
sinks:
  - type: csv_file       # From 1
  - type: json_file      # From 1
  - type: excel_file     # From 2
```

**Explicit Replace** (opt-in):
```yaml
# Layer 2 with __replace__ marker
sinks:
  __replace__: true
  value:
    - type: excel_file

# Result: Replace (discards layer 1)
sinks:
  - type: excel_file     # Only 2
```

**Deduplication**: Lists should include stable IDs (`name:` fields) for downstream validation to detect duplicates.

### Rule 3: Scalars → Replace (Last Wins)

```yaml
# Layer 1
temperature: 0.7

# Layer 2
temperature: 0.9

# Result: Replace
temperature: 0.9
```

## Part 3: Validation Pipeline

### Fail-Fast at Each Layer

```python
def load_configuration(suite_root, experiment_name):
    """Load and merge config with fail-fast validation."""

    # Load Layer 1: Suite defaults
    defaults = load_yaml("suite_defaults.yaml")
    validate_schema(defaults, SUITE_DEFAULTS_SCHEMA)  # ← Fail-fast

    # Load Layer 2: Prompt pack (if specified)
    if defaults.get("prompt_pack"):
        pack = load_yaml(f"prompt_packs/{defaults['prompt_pack']}.yaml")
        validate_schema(pack, PROMPT_PACK_SCHEMA)  # ← Fail-fast
        defaults = deep_merge(defaults, pack)

    # Load Layer 3: Experiment override
    experiment = load_yaml(f"{suite_root}/{experiment_name}.yaml")
    validate_schema(experiment, EXPERIMENT_SCHEMA)  # ← Fail-fast
    final = deep_merge(defaults, experiment)

    # Final validation
    validate_final_configuration(final)  # ← Fail-fast

    return final
```

### Validation Stages

1. **Layer validation** - Each layer validated against schema before merge
2. **Merge validation** - Post-merge structure validated
3. **Plugin validation** - Plugin-specific validation before instantiation
4. **Security validation** - MLS enforcement (ADR-002)

**Failure Mode**: **Abort on first error** (fail-fast, ADR-001).

## Part 4: Security Policy Enforcement (ADR-002-B)

### Forbidden Configuration Fields

**FORBIDDEN in config** (author-owned, immutable):
- `security_level` - Plugin's clearance (declare in code)
- `allow_downgrade` - Downgrade policy (declare in code)
- `max_operating_level` - Future-proofing

**Enforcement**:
```python
FORBIDDEN_FIELDS = {"security_level", "allow_downgrade", "max_operating_level"}

def validate_no_forbidden_fields(config: dict):
    """Verify config doesn't override security policy (ADR-002-B)."""
    for field in FORBIDDEN_FIELDS:
        if field in config:
            raise ConfigurationError(
                f"Field '{field}' is forbidden in configuration (ADR-002-B). "
                f"Security policy is plugin-author-owned - declare in plugin code via "
                f"BasePlugin.__init__(security_level=..., allow_downgrade=...)."
            )
```

**Rationale**: Security policy determined by plugin author (trust model), not runtime config (user-controlled).

## Part 5: Debugging & Observability

### Configuration Provenance Tracking

Each value tagged with source layer:
```python
{
  "llm": {
    "model": {"value": "gpt-3.5", "_source": "suite_defaults"},
    "temperature": {"value": 0.9, "_source": "prompt_pack"},
    "max_tokens": {"value": 2000, "_source": "experiment"},
  }
}
```

**CLI command**:
```bash
python -m elspeth.cli config-trace my_experiment
# Shows: temperature=0.9 from prompt_pack (overrides suite_defaults 0.7)
```

### Error Messages

```
ConfigurationError: LLM client validation failed
  Field: llm.temperature
  Value: 1.5
  Source: experiment override (experiments/my_test.yaml:12)
  Validation: Must be between 0.0 and 1.0
  Fix: Change temperature to value in range [0.0, 1.0]
```

## Consequences

### Benefits
- **Explicit precedence** - No ambiguity on which layer wins
- **Additive composition** - Higher layers extend, don't replace (default)
- **Fail-fast validation** - Errors caught early (per-layer)
- **Security enforcement** - Policy fields forbidden in config (ADR-002-B)
- **Debug-friendly** - Provenance tracking shows value sources
- **Opt-in replace** - `__replace__` marker when needed

### Limitations
- **Concatenation default** - Lists may accumulate duplicates (need validation)
- **Deep merge complexity** - Nested configs harder to reason about
- **`__replace__` marker** - Special syntax adds cognitive overhead

### Mitigations
- **Provenance tracking** - Shows exact merge path
- **CLI trace command** - Debugging tool for configs
- **Clear documentation** - Examples for each pattern

## Related

ADR-001 (Philosophy - fail-fast), ADR-002-B (Security policy metadata), ADR-003 (Plugin registry), ADR-008 (Registry pattern)

---
**Last Updated**: 2025-10-26
