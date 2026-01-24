# Plugin Config Model Inventory

## Executive Summary

**Total builtin plugins:** 16
**Plugins with Pydantic config classes:** 15 / 16 (93.75%)
**Config base classes have from_dict():** ✓

## Verification Commands

```bash
# List all builtin plugin files
find src/elspeth/plugins/sources src/elspeth/plugins/transforms src/elspeth/plugins/sinks -name "*.py" -type f | grep -v __init__ | grep -v __pycache__
# Result: 15 plugin files

# Search for config classes
grep -rn "class.*Config.*\(SourceDataConfig\|TransformDataConfig\|GateDataConfig\|SinkDataConfig\|DataPluginConfig\|PathConfig\)" src/elspeth/plugins/ --include="*.py"
# Result: Found config classes for 15 plugins

# Verify from_dict method in base classes
grep -rn "from_dict" src/elspeth/plugins/config_base.py
# Result: from_dict() defined in PluginConfig base class (line 47)
```

## Sources (3 total)

| Plugin | Config Class | Base Class | Has from_dict() | Notes |
|--------|-------------|------------|-----------------|-------|
| CSVSource | `CSVSourceConfig` | `SourceDataConfig` | ✓ | Fully compliant |
| JSONSource | `JSONSourceConfig` | `SourceDataConfig` | ✓ | Fully compliant |
| NullSource | **NO CONFIG CLASS** | N/A | ❌ | Takes dict, ignores it (resume-only source) |

## Transforms (9 total)

| Plugin | Config Class | Base Class | Has from_dict() | Notes |
|--------|-------------|------------|-----------------|-------|
| Passthrough | `PassThroughConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| FieldMapper | `FieldMapperConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| JSONExplode | `JSONExplodeConfig` | `DataPluginConfig` | ✓ | Inherits from DataPluginConfig (no error routing) |
| KeywordFilter | `KeywordFilterConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| Truncate | `TruncateConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| BatchReplicate | `BatchReplicateConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| BatchStats | `BatchStatsConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| AzureContentSafety | `AzureContentSafetyConfig` | `TransformDataConfig` | ✓ | Fully compliant |
| AzurePromptShield | `AzurePromptShieldConfig` | `TransformDataConfig` | ✓ | Fully compliant |

## Sinks (3 total)

| Plugin | Config Class | Base Class | Has from_dict() | Notes |
|--------|-------------|------------|-----------------|-------|
| CSVSink | `CSVSinkConfig` | `PathConfig` | ✓ | Fully compliant |
| JSONSink | `JSONSinkConfig` | `PathConfig` | ✓ | Fully compliant |
| DatabaseSink | `DatabaseSinkConfig` | `DataPluginConfig` | ✓ | Fully compliant |

## Gates

No gate plugins found in codebase. Gates directory does not exist yet.

## LLM Plugin Pack (Optional - Not Builtin)

LLM plugins are in `plugins/llm/` and are part of an optional pack, not builtin plugins:

| Plugin | Config Class | Base Class | Has from_dict() | Notes |
|--------|-------------|------------|-----------------|-------|
| LLM (base) | `LLMConfig` | `TransformDataConfig` | ✓ | Base class for LLM transforms |
| AzureOpenAI | Uses `LLMConfig` | `TransformDataConfig` | ✓ | Inherits from LLM base |
| AzureBatch | `AzureBatchConfig` | `TransformDataConfig` | ✓ | Batch processing variant |
| AzureMultiQuery | Uses `AzureOpenAIConfig` | `TransformDataConfig` | ✓ | Multi-query variant |
| OpenRouter | Uses `LLMConfig` | `TransformDataConfig` | ✓ | OpenRouter integration |

## Config Base Class Hierarchy

```
PluginConfig (base)
├── from_dict() [LINE 47] ✓
├── schema_config: SchemaConfig | None
│
├── DataPluginConfig (requires schema)
│   ├── @model_validator: _require_schema()
│   │
│   ├── TransformDataConfig (adds on_error)
│   │   ├── on_error: str | None
│   │   └── Used by: All standard transforms, LLM transforms
│   │
│   ├── PathConfig (adds path + requires schema)
│   │   ├── path: str
│   │   ├── resolved_path() helper
│   │   │
│   │   ├── SourceDataConfig (adds on_validation_failure)
│   │   │   ├── on_validation_failure: str (required)
│   │   │   └── Used by: CSVSource, JSONSource
│   │   │
│   │   └── Used by: CSVSink, JSONSink
│   │
│   └── Used by: DatabaseSink, JSONExplode
│
└── Used by: (none directly - base class only)
```

## Special Case: NullSource

**Status:** No config class

**Rationale:**
- NullSource is a special resume-only source that yields no rows
- Takes `config: dict[str, Any]` but ignores all values
- Used when resuming from checkpoint (rows come from payload store, not source)
- No validation needed because there's no configuration to validate

**Validator Impact:**
The validator subsystem will need to handle this case:
```python
# In PluginConfigValidator
if plugin_name == "null":
    return  # No config validation needed
```

## Validator Implementation Notes

### Compatible Patterns Found

All plugins with config classes follow the same pattern:

```python
class PluginNameConfig(BaseConfigClass):
    """Configuration for PluginName."""
    field1: str
    field2: int = 42

class PluginName(BasePlugin):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = PluginNameConfig.from_dict(config)  # ← Validates here
        self._field1 = cfg.field1
        # ... rest of init
```

### Validator Can Use

```python
# In PluginConfigValidator.validate()
config_class = plugin_class.get_config_class()  # New protocol method
validated_config = config_class.from_dict(config)  # Raises PluginConfigError
```

### Required Changes

1. Add `get_config_class()` protocol method to plugin base classes
2. Each plugin class returns its config class type
3. NullSource returns `None` to signal "no config needed"

## Compliance Summary

**✅ READY FOR VALIDATOR EXTRACTION:**
- 15/16 plugins have Pydantic config classes with `from_dict()`
- All config classes inherit from common base with validation
- Config hierarchy is well-structured (PluginConfig → DataPluginConfig → specialized)
- Validation errors are consistent (`PluginConfigError`)

**⚠️ SPECIAL HANDLING REQUIRED:**
- NullSource (no config class - validator should skip)

**📋 NEXT STEPS:**
1. Add `get_config_class()` to plugin protocols (Task 1.1)
2. Implement validator subsystem using `config_class.from_dict()` (Task 1.2)
3. Extract validation from `__init__` methods (Task 2.x)
