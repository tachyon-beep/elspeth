# Silent Defaults Removal Plan

**Purpose**: Remove all critical silent defaults to enforce explicit configuration for security-sensitive parameters.

**Status**: Generated 2025-10-15

**Tracking Test**: `tests/test_security_enforcement_defaults.py`

---

## Current Status Summary

### ✅ Already Fixed (5/6 critical items)

1. **Azure Search API Key Validation** ✅
   - **Location**:
     - `src/elspeth/retrieval/providers.py:164-169`
     - `src/elspeth/plugins/nodes/sinks/embeddings_store.py:392-398`
   - **Current Behavior**: Requires explicit `api_key` or `api_key_env` parameter
   - **Error Message**: "azure_search retriever requires 'api_key' or 'api_key_env'. Provide explicit 'api_key_env' (e.g., 'AZURE_SEARCH_KEY') in configuration."
   - **Status**: ✅ **COMPLETE**

2. **Azure OpenAI Endpoint Validation** ✅
   - **Location**:
     - `src/elspeth/plugins/nodes/sinks/embeddings_store.py:54-58`
     - `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:28`
   - **Current Behavior**: Requires explicit `endpoint` / `azure_endpoint` parameter
   - **Error Message**: "azure_openai embed_model requires explicit 'endpoint' configuration. Do not rely on AZURE_OPENAI_ENDPOINT environment variable for security/audit purposes."
   - **Status**: ✅ **COMPLETE**

3. **Azure OpenAI API Version Validation** ✅
   - **Location**: `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:27`
   - **Current Behavior**: Requires explicit `api_version` parameter via `_resolve_required()`
   - **Error Message**: "AzureOpenAIClient missing required config value 'api_version'"
   - **Status**: ✅ **COMPLETE**

4. **LLM Temperature Parameter** ✅
   - **Location**: `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:20, 92-93`
   - **Current Behavior**: Already optional - uses `config.get("temperature")` which returns None if not set
   - **OpenAI Behavior**: When `temperature` is None, it's not passed to the API, so OpenAI uses its own default (typically 1.0 for creative, 0.7 for chat)
   - **Status**: ✅ **ACCEPTABLE** - No silent default in Elspeth code; decision delegated to LLM provider
   - **Note**: Tests can verify that config without temperature doesn't inject a default

5. **LLM Max Tokens Parameter** ✅
   - **Location**: `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:21, 94-95`
   - **Current Behavior**: Already optional - uses `config.get("max_tokens")` which returns None if not set
   - **OpenAI Behavior**: When `max_tokens` is None, OpenAI uses model-specific defaults (e.g., 4096 for GPT-4)
   - **Status**: ✅ **ACCEPTABLE** - No silent default in Elspeth code; decision delegated to LLM provider
   - **Note**: Tests can verify that config without max_tokens doesn't inject a default

### ❌ Needs Fix (1/6 critical items)

6. **Static LLM Content Default** ❌
   - **Location**:
     - `src/elspeth/core/llm_registry.py:45`
     - `src/elspeth/plugins/nodes/transforms/llm/static.py:16`
   - **Current Behavior**: Defaults to `"STATIC RESPONSE"` if not provided
   - **Risk**: Tests may pass with implicit defaults, hiding missing configuration
   - **Status**: ❌ **NEEDS FIX**

---

## Implementation Plan

### Phase 1: Static LLM Content (CRITICAL - P0)

**Objective**: Require explicit `content` parameter for static_test LLM

**Files to Modify**:
1. `src/elspeth/core/llm_registry.py`
2. `src/elspeth/plugins/nodes/transforms/llm/static.py`
3. Schema definition in `src/elspeth/core/llm_registry.py:101-113`

**Changes**:

#### 1. Remove default from StaticLLMClient.__init__()

**File**: `src/elspeth/plugins/nodes/transforms/llm/static.py`

**Current** (line 16):
```python
content: str = "STATIC RESPONSE",
```

**After**:
```python
content: str,  # Required parameter - no default
```

#### 2. Remove default from factory function

**File**: `src/elspeth/core/llm_registry.py`

**Current** (lines 44-48):
```python
def _create_static_llm(options: dict[str, Any], context: PluginContext) -> StaticLLMClient:
    """Create static LLM client."""
    return StaticLLMClient(
        content=options.get("content", "STATIC RESPONSE"),
        score=options.get("score", 0.5),
        metrics=options.get("metrics"),
    )
```

**After**:
```python
def _create_static_llm(options: dict[str, Any], context: PluginContext) -> StaticLLMClient:
    """Create static LLM client."""
    content = options.get("content")
    if not content:
        raise ConfigurationError(
            "static_test LLM requires explicit 'content' parameter. "
            "Provide the test response content explicitly in configuration."
        )
    return StaticLLMClient(
        content=content,
        score=options.get("score", 0.5),
        metrics=options.get("metrics"),
    )
```

**Import needed**:
```python
from elspeth.core.validation_base import ConfigurationError
```

#### 3. Update schema to mark content as required

**File**: `src/elspeth/core/llm_registry.py`

**Current** (lines 101-113):
```python
_STATIC_LLM_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "score": {"type": "number"},
            "metrics": {"type": "object"},
        },
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)
```

**After**:
```python
_STATIC_LLM_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Static response content to return for all requests"},
            "score": {"type": "number", "description": "Optional score metric (default: 0.5)"},
            "metrics": {"type": "object", "description": "Optional additional metrics"},
        },
        "required": ["content"],  # Enforce explicit content
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)
```

---

### Phase 2: Update Test Configurations

**Objective**: Update all test configurations that use `static_test` LLM to include explicit `content` parameter

**Search Command**:
```bash
grep -rn "plugin: static_test" tests/
grep -rn '"static_test"' tests/
```

**Expected Files to Update**:
- All test YAML configurations using `static_test`
- All test Python code instantiating StaticLLMClient
- Example configs in `config/` directory (if any)

**Change Pattern**:

**Before**:
```yaml
llm:
  plugin: static_test
  security_level: OFFICIAL
  determinism_level: guaranteed
  options:
    score: 0.8
```

**After**:
```yaml
llm:
  plugin: static_test
  security_level: OFFICIAL
  determinism_level: guaranteed
  options:
    content: "Test response content"
    score: 0.8
```

---

### Phase 3: Update Test Expectations

**Objective**: Enable the TODO tests in `test_security_enforcement_defaults.py`

**File**: `tests/test_security_enforcement_defaults.py`

**Changes**:

#### 1. Enable test_static_llm_content_default_documented (line 85-93)

**Current**:
```python
def test_static_llm_content_default_documented(self):
    """Document static LLM content default."""
    # ...
    pytest.skip("TODO: Require explicit static LLM content after migration")
```

**After**:
```python
def test_static_llm_content_requires_explicit_config(self):
    """Verify static LLM requires explicit content parameter."""
    from elspeth.core.llm_registry import llm_registry
    from elspeth.core.validation_base import ConfigurationError

    # Should raise ConfigurationError when content is missing
    with pytest.raises(ConfigurationError, match="static_test LLM requires explicit 'content'"):
        llm_registry.create(
            name="static_test",
            options={"security_level": "internal"},
            require_determinism=False
        )

    # Should succeed when content is provided
    llm = llm_registry.create(
        name="static_test",
        options={"security_level": "internal", "content": "Explicit test content"},
        require_determinism=False
    )
    assert llm is not None
    assert llm.content == "Explicit test content"
```

#### 2. Update gate status test (line 153-176)

**Current**:
```python
critical_defaults_removed = {
    "azure_search_api_key_env": False,  # Still has default
    "azure_search_field_names": False,  # Still has default
    "pgvector_table_name": False,       # Still has default
    "azure_openai_endpoint": False,     # Still has default
    "azure_openai_api_version": False,  # Still has default
    "regex_empty_pattern": True,        # Now enforced (validation.py:136)
}
```

**After**:
```python
critical_defaults_removed = {
    "azure_search_api_key_env": True,    # ✅ Fixed in providers.py:164
    "azure_search_field_names": True,    # ✅ Fixed in providers.py:175-183
    "pgvector_table_name": True,         # ✅ Fixed in providers.py:156
    "azure_openai_endpoint": True,       # ✅ Fixed in azure_openai.py:28
    "azure_openai_api_version": True,    # ✅ Fixed in azure_openai.py:27
    "static_llm_content": True,          # ✅ Will be fixed in this phase
    "regex_empty_pattern": True,         # ✅ Already enforced (validation.py:136)
}

total = len(critical_defaults_removed)
fixed = sum(critical_defaults_removed.values())

print(f"\nCritical Defaults Status: {fixed}/{total} fixed")

# Once all fixed, this test will pass instead of skip
assert fixed == total, (
    f"Gate BLOCKED: {total - fixed} critical defaults remain. "
    f"See SILENT_DEFAULTS_AUDIT.md for details."
)
```

---

## Testing Strategy

### Unit Tests

1. **Test explicit content requirement**:
   ```python
   def test_static_llm_requires_content():
       with pytest.raises(ConfigurationError):
           llm_registry.create("static_test", {"security_level": "internal"})
   ```

2. **Test successful creation with explicit content**:
   ```python
   def test_static_llm_with_explicit_content():
       llm = llm_registry.create(
           "static_test",
           {"security_level": "internal", "content": "Test response"}
       )
       assert llm.content == "Test response"
   ```

### Integration Tests

1. Update all integration tests using `static_test` LLM
2. Verify configuration validation catches missing `content`
3. Verify error messages are helpful

---

## Migration Impact Assessment

### Affected Components

**Low Risk** - Only affects test code:
- ✅ `static_test` LLM is only used in tests, not production
- ✅ Schema validation will catch missing parameters before runtime
- ✅ Clear error messages guide users to fix

### Breaking Changes

- **Tests**: All tests using `static_test` without explicit `content` will fail
- **Production**: No impact - `static_test` is test-only

### Rollback Plan

If issues arise:
1. Revert changes to `static.py` and `llm_registry.py`
2. Re-run test suite
3. Investigate why explicit content wasn't provided in tests

---

## Completion Criteria

### Phase 1 (Static LLM Content)
- [ ] Remove default from `StaticLLMClient.__init__()`
- [ ] Update factory function with validation
- [ ] Update schema with `required: ["content"]`
- [ ] Add ConfigurationError import

### Phase 2 (Test Updates)
- [ ] Find all uses of `static_test` in tests
- [ ] Update YAML configs with explicit `content`
- [ ] Update Python test code with explicit `content`
- [ ] Verify no grep matches without content

### Phase 3 (Test Enforcement)
- [ ] Enable `test_static_llm_content_requires_explicit_config`
- [ ] Update gate status test with all items marked True
- [ ] Verify gate test passes (not skips)
- [ ] Run full test suite - all pass

### Documentation
- [ ] Update plugin catalogue with schema changes
- [ ] Update SILENT_DEFAULTS_AUDIT.md status
- [ ] Add entry to CHANGELOG.md
- [ ] Update this plan with completion dates

---

## Schedule

- **Phase 1**: 30 minutes (code changes)
- **Phase 2**: 1-2 hours (test configuration updates)
- **Phase 3**: 30 minutes (test enforcement)
- **Total**: ~2-3 hours

---

## Notes

### Already Completed Work

The orchestrator_2 migration has already fixed 5 out of 6 critical silent defaults:
1. Azure Search API keys - explicit validation added
2. Azure Search field names - explicit validation added
3. pgvector table names - explicit validation added
4. Azure OpenAI endpoints - explicit validation added
5. Azure OpenAI API versions - explicit validation added

Only the static LLM content default remains.

### Design Decision: Temperature/Max_Tokens

The original audit flagged `temperature` and `max_tokens` as having defaults in validation.py.
However, investigation shows:
- These parameters are optional in the LLM client code
- They default to `None`, not a hardcoded value
- When `None`, they're omitted from the OpenAI API call
- The LLM provider (OpenAI/Azure) applies its own defaults

**Decision**: This is ACCEPTABLE behavior. Elspeth should not mandate temperature/max_tokens
for all LLM calls. Users who want specific values can configure them; users who want
provider defaults can omit them.

The audit tests for these can be updated to verify that Elspeth doesn't inject a default
value (i.e., verify that None is passed through correctly).
