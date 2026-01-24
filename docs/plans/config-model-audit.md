# Plugin Config Model Inventory

## Sources
- AzureBlobSource → AzureBlobSourceConfig ✓
- CSVSource → CSVSourceConfig ✓
- JSONSource → JSONSourceConfig ✓
- NullSource → No config class (resume-only source, takes dict but ignores it)

## Transforms
- AzureBatchLLMTransform → AzureBatchConfig ✓
- AzureContentSafety → AzureContentSafetyConfig ✓
- AzureLLMTransform → AzureOpenAIConfig ✓
- AzureMultiQueryLLMTransform → MultiQueryConfig ✓
- AzurePromptShield → AzurePromptShieldConfig ✓
- BatchReplicate → BatchReplicateConfig ✓
- BatchStats → BatchStatsConfig ✓
- FieldMapper → FieldMapperConfig ✓
- JSONExplode → JSONExplodeConfig ✓
- KeywordFilter → KeywordFilterConfig ✓
- OpenRouterLLMTransform → OpenRouterConfig ✓
- Passthrough → PassThroughConfig ✓
- Truncate → TruncateConfig ✓

## Gates
- No gate plugins in codebase yet

## Sinks
- AzureBlobSink → AzureBlobSinkConfig ✓
- CSVSink → CSVSinkConfig ✓
- DatabaseSink → DatabaseSinkConfig ✓
- JSONSink → JSONSinkConfig ✓

## Summary
- **Total plugins:** 21
- **Plugins with config classes:** 20 / 21 (95%)
- **Config base classes have from_dict():** ✓

## Validator Implementation Notes
All plugins with config classes follow the same pattern. Validator can use:
```python
config_class.from_dict(config)  # Validates and returns instance
```

Special case: NullSource has no config class (resume-only source). Validator should skip validation for this plugin.
