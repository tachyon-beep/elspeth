# Silent Defaults Audit

**Date**: October 14, 2025
**Status**: Complete - Awaiting Review & Security Test Creation
**Total Defaults Found**: 200+

## Executive Summary

This audit identifies all silent defaults in the Elspeth codebase. Silent defaults bypass explicit configuration requirements and can introduce security vulnerabilities, compliance issues, and hidden behavior.

### Key Findings

- **CRITICAL (P0)**: 4 instances - API keys, credentials, authentication
- **HIGH (P1)**: 18 instances - Validation patterns, LLM parameters, security-adjacent
- **MEDIUM (P2)**: 150+ instances - Operational defaults (field names, timeouts, etc.)
- **LOW (P3)**: 30+ instances - Display/formatting defaults

### Action Required

1. **IMMEDIATE**: Remove or document all CRITICAL defaults
2. **SHORT-TERM**: Add security enforcement tests for HIGH defaults
3. **MEDIUM-TERM**: Review MEDIUM defaults for policy compliance
4. **ONGOING**: Establish "no silent defaults" policy for new code

---

## CRITICAL (P0) - Security/Authentication

**Risk**: Credential leakage, unauthorized access, security bypass

### 1. Azure Search API Key Environment Variable
**File**: `src/elspeth/retrieval/providers.py:161`
```python
api_key = os.getenv(options.get("api_key_env", "AZURE_SEARCH_KEY") or "AZURE_SEARCH_KEY")
```
**Risk**: Silent default to "AZURE_SEARCH_KEY" env var
**Impact**: If config is empty/None, system uses hardcoded env var name
**Recommendation**: Remove default, require explicit `api_key_env` in config

### 2. Azure Search API Key (Embeddings Sink)
**File**: `src/elspeth/plugins/outputs/embeddings_store.py:389`
```python
api_key = os.getenv(options.get("api_key_env", "AZURE_SEARCH_KEY") or "AZURE_SEARCH_KEY")
```
**Risk**: Same as #1
**Recommendation**: Remove default, require explicit `api_key_env` in config

### 3. Azure OpenAI Endpoint
**File**: `src/elspeth/plugins/outputs/embeddings_store.py:417`
```python
endpoint=config.get("endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT", ""),
```
**Risk**: Falls back to environment variable, then empty string
**Impact**: Silent failure or connection to unintended endpoint
**Recommendation**: Require explicit endpoint in config, fail if missing

### 4. Azure OpenAI API Version
**File**: `src/elspeth/retrieval/embedding.py:62`
```python
version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-13")
```
**Risk**: Hardcoded API version default
**Impact**: System may use outdated API version without user awareness
**Recommendation**: Require explicit API version in config

---

## HIGH (P1) - Validation/Business Logic

**Risk**: Bypassed validation, incorrect behavior, data integrity issues

### 5. Empty Validation Pattern
**File**: `src/elspeth/plugins/experiments/validation.py:136`
```python
pattern=options.get("pattern", ""),
```
**Risk**: Empty pattern means regex validation always passes
**Impact**: Validation plugin becomes no-op, security control bypassed
**Recommendation**: Make pattern required, fail if empty

### 6. LLM Temperature Default
**File**: `src/elspeth/core/validation.py:840`
```python
temperature = float(data.get("temperature", 0.0) or 0.0)
```
**Risk**: Silent default to deterministic mode
**Impact**: Users may expect randomness but get deterministic responses
**Recommendation**: Require explicit temperature in LLM config

### 7. LLM Max Tokens Default
**File**: `src/elspeth/core/validation.py:841`
```python
max_tokens = int(data.get("max_tokens", 0) or 0)
```
**Risk**: Zero means unlimited tokens
**Impact**: Potential cost explosion, rate limit issues
**Recommendation**: Require explicit max_tokens with reasonable upper bound

### 8. Static LLM Content
**File**: `src/elspeth/core/llm_registry.py:45`
```python
content=options.get("content", "STATIC RESPONSE"),
```
**Risk**: Fallback to hardcoded response
**Impact**: Tests may pass with wrong content
**Recommendation**: Make content required for static LLM

### 9. Static LLM Score
**File**: `src/elspeth/core/llm_registry.py:46`
```python
score=options.get("score", 0.5),
```
**Risk**: Default score may not match test expectations
**Impact**: Silent test failures or false positives
**Recommendation**: Make score required for static LLM

### 10. Database Table Name
**File**: `src/elspeth/retrieval/providers.py:155`
```python
return PgVectorQueryClient(dsn=dsn, table=options.get("table", "elspeth_rag"))
```
**Risk**: Silent default to "elspeth_rag" table
**Impact**: Data written to unexpected location, collision risk
**Recommendation**: Require explicit table name in config

### 11-13. Azure Search Field Names
**Files**: `src/elspeth/retrieval/providers.py:168-170`
```python
vector_field=options.get("vector_field", "embedding"),
namespace_field=options.get("namespace_field", "namespace"),
content_field=options.get("content_field", "contents"),
```
**Risk**: Hardcoded field schema assumptions
**Impact**: Data corruption if schema differs
**Recommendation**: Require explicit field names in config

### 14-18. Embeddings Store Defaults
**File**: `src/elspeth/core/sink_registry.py:140-147`
```python
table=options.get("table", "elspeth_rag"),
text_field=options.get("text_field", DEFAULT_TEXT_FIELD),
embedding_source=options.get("embedding_source", DEFAULT_EMBEDDING_FIELD),
id_field=options.get("id_field", DEFAULT_ID_FIELD),
batch_size=options.get("batch_size", 50),
upsert_conflict=options.get("upsert_conflict", "replace"),
```
**Risk**: Multiple schema and behavior defaults
**Impact**: Data written with wrong schema, conflicts handled incorrectly
**Recommendation**: Require explicit configuration

---

## MEDIUM (P2) - Operational Defaults

**Risk**: Unexpected behavior, performance issues, audit gaps

### Plugin Configuration Extraction (50+ instances)

**Pattern**: `options = dict(definition.get("options", {}) or {})`
**Files**: Multiple registry files
**Risk**: Empty dict fallback allows plugins to be created without options
**Impact**: Plugin-specific, varies by implementation
**Status**: ACCEPTABLE - This is structural, plugins validate their own requirements
**Monitoring**: Ensure plugin factories validate required options

### Statistics & Metrics Defaults (40+ instances)

**Files**: `src/elspeth/plugins/experiments/metrics.py` (throughout)
**Examples**:
```python
min_samples=int(options.get("min_samples", 2))
alpha=float(options.get("alpha", 0.05))
ddof=int(options.get("ddof", 0))
equal_var=bool(options.get("equal_var", False))
threshold=float(options.get("threshold", 1.0))
```
**Risk**: Statistical tests run with default parameters user may not expect
**Impact**: Incorrect statistical conclusions, false positives/negatives
**Status**: REVIEW - Document defaults in schema, consider requiring explicit values
**Recommendation**: Add schema documentation for each default's meaning

### Visual Analytics Defaults (10 instances)

**File**: `src/elspeth/core/sink_registry.py:107-130`
```python
dpi=int(options.get("dpi", 150))
seaborn_style=options.get("seaborn_style", "darkgrid")
color_palette=options.get("color_palette", "Set2")
include_table=options.get("include_table", True)
```
**Risk**: Outputs generated with unexpected styling
**Impact**: Reports don't match corporate branding, low quality exports
**Status**: ACCEPTABLE - Display defaults are low risk
**Monitoring**: Document defaults in sink documentation

### Rate Limiting Defaults (4 instances)

**File**: `src/elspeth/core/controls/rate_limiter_registry.py:36-46`
```python
requests=int(options.get("requests", 1))
per_seconds=float(options.get("per_seconds", 1.0))
requests_per_minute = int(options.get("requests_per_minute", options.get("requests", 60)) or 60)
interval_seconds = float(options.get("interval_seconds", 60.0))
```
**Risk**: Overly permissive defaults allow rate limit violations
**Impact**: API throttling, service degradation
**Status**: REVIEW - Defaults should be conservative
**Recommendation**: Document rate limit rationale, consider lower defaults

### Cost Tracking Defaults (4 instances)

**File**: `src/elspeth/core/controls/cost_tracker_registry.py:31-32`
```python
prompt_token_price=float(options.get("prompt_token_price", 0.0))
completion_token_price=float(options.get("completion_token_price", 0.0))
```
**Risk**: Zero price means no cost tracking
**Impact**: Budget overruns, missing cost alerts
**Status**: REVIEW - Consider requiring explicit prices
**Recommendation**: Document that 0.0 means "free" or "not tracked"

### Validation Tokens (3 instances)

**File**: `src/elspeth/plugins/experiments/validation.py:181-183`
```python
valid_token=options.get("valid_token", "VALID")
invalid_token=options.get("invalid_token", "INVALID")
strip_whitespace=options.get("strip_whitespace", True)
```
**Risk**: Hardcoded token assumptions
**Impact**: Validation false positives if LLM uses different tokens
**Status**: REVIEW - Document tokens in schema, consider requiring explicit
**Recommendation**: Make tokens explicit in validation plugin config

### File Naming Defaults (2 instances)

**File**: `src/elspeth/core/sink_registry.py:107, 123`
```python
file_stem=options.get("file_stem", "analytics_visual")
file_stem=options.get("file_stem", "enhanced_visual")
```
**Risk**: File naming collisions
**Impact**: Outputs overwrite each other
**Status**: ACCEPTABLE - Users should specify unique names
**Monitoring**: Document file_stem requirement

### Prompt Variant Generator (4 instances)

**File**: `src/elspeth/plugins/experiments/prompt_variants.py:163-166`
```python
count=options.get("count", 5)
strip=options.get("strip", True)
metadata_key=options.get("metadata_key", "prompt_variants")
max_attempts=options.get("max_attempts", 3)
```
**Risk**: Generator behavior unexpected
**Impact**: Too many/few variants generated
**Status**: ACCEPTABLE - Reasonable defaults documented
**Monitoring**: Ensure schema documents these defaults

### Feature Flags (2 instances)

**File**: `src/elspeth/core/validation.py:776-777`
```python
enabled = bool(data.get("enabled", True))
is_baseline = bool(data.get("is_baseline", False))
```
**Risk**: Experiments enabled by default
**Impact**: Disabled experiments must be explicitly marked
**Status**: ACCEPTABLE - Opt-out model is reasonable
**Monitoring**: Document default behavior

### Error Handling Modes (5 instances)

**Files**: Various plugins
```python
on_error=options.get("on_error", "abort")
```
**Risk**: Abort-on-error may be too strict for some use cases
**Impact**: Experiments fail unnecessarily
**Status**: REVIEW - Consider "warn" as default for some plugins
**Recommendation**: Document error modes in each plugin schema

---

## LOW (P3) - Display/Formatting

**Risk**: Cosmetic issues only

### Data Extraction Patterns (30+ instances)

**Files**: `src/elspeth/tools/reporting.py`, `src/elspeth/config.py`
**Pattern**: `data.get("key", {})` for nested dict access
**Examples**:
```python
variants = comparative.get("variants", {})
prompts=dict(profile_data.get("prompts", {}))
metadata = doc.get("metadata", {}) or {}
```
**Risk**: None - Safe fallback for optional nested structures
**Status**: ACCEPTABLE - Standard Python idiom for safe dict access
**Monitoring**: None required

### Score Extraction Defaults (5 instances)

**File**: `src/elspeth/plugins/experiments/metrics.py:284-290`
```python
key=options.get("key", "score")
parse_json_content=options.get("parse_json_content", True)
allow_missing=options.get("allow_missing", False)
threshold_mode=options.get("threshold_mode", "gte")
flag_field=options.get("flag_field", "score_flags")
```
**Risk**: Minimal - Standard score field names
**Status**: ACCEPTABLE - Conventional defaults
**Monitoring**: Document in schema

---

## Detailed Analysis by File

### Most Defaults: `src/elspeth/plugins/experiments/metrics.py` (80+ instances)
- Primarily statistical parameters (alpha, thresholds, sample sizes)
- Low individual risk, cumulative risk if users don't understand statistics
- **Recommendation**: Create comprehensive documentation for statistical defaults

### Most Critical: `src/elspeth/retrieval/providers.py` (10 instances)
- API keys, table names, field schemas
- Direct security and data integrity impact
- **Recommendation**: Priority for removal/documentation

### Most Complex: `src/elspeth/core/controls/rate_limiter_registry.py` (Nested defaults)
- `requests_per_minute = int(options.get("requests_per_minute", options.get("requests", 60)) or 60)`
- Nested fallback logic hard to understand
- **Recommendation**: Simplify to single explicit default

---

## Security Enforcement Tests Required

### Test 1: Critical Defaults Removed
```python
def test_no_api_key_default():
    """Verify API key env vars must be explicit"""
    with pytest.raises(ConfigurationError):
        create_azure_search_provider({})  # No api_key_env
```

### Test 2: Empty Validation Pattern Rejected
```python
def test_empty_pattern_rejected():
    """Verify regex validator requires pattern"""
    with pytest.raises(ConfigurationError):
        create_regex_validator({"pattern": ""})
```

### Test 3: Temperature Required
```python
def test_llm_temperature_required():
    """Verify LLM config requires explicit temperature"""
    with pytest.raises(ConfigurationError):
        create_llm_client({...})  # No temperature
```

### Test 4: Database Config Required
```python
def test_database_table_required():
    """Verify pgvector requires explicit table name"""
    with pytest.raises(ConfigurationError):
        create_pgvector_client({"dsn": "..."})  # No table
```

---

## Recommendations

### Immediate Actions (This Week)

1. **Remove CRITICAL defaults** (4 instances)
   - Add ConfigurationError for missing API keys, endpoints
   - Update schemas to mark fields as required
   - Add tests to enforce

2. **Document HIGH defaults** (18 instances)
   - Add schema descriptions explaining impact
   - Add validation to warn/fail on empty patterns
   - Create user guide for LLM parameters

3. **Create enforcement tests** (10+ tests)
   - Cover all CRITICAL and HIGH scenarios
   - Verify ConfigurationError raised
   - Add to CI pipeline

### Short-Term Actions (Next 2 Weeks)

4. **Review MEDIUM defaults** (150+ instances)
   - Audit statistical parameter defaults with statistician
   - Document operational defaults in schemas
   - Add warnings for high-risk defaults (rate limits, costs)

5. **Establish "No Silent Defaults" policy**
   - Add to CONTRIBUTING.md
   - Update plugin development guide
   - Add pre-commit hook to detect new defaults

### Long-Term Actions (Next Month)

6. **Migrate to explicit-only configuration**
   - Add migration guide for users
   - Provide schema validation tools
   - Create config migration script

7. **Add runtime configuration validation**
   - Validate all configs at load time
   - Generate warnings for deprecated defaults
   - Provide "explain config" CLI command

---

## Gate Status

- [ ] CRITICAL defaults documented and removal plan created
- [ ] HIGH defaults documented with schema annotations
- [ ] Security enforcement tests written (10+ tests)
- [ ] All tests passing after enforcement
- [ ] "No Silent Defaults" policy documented

**Gate Blocked**: Cannot proceed to migration until all CRITICAL/HIGH defaults addressed

---

## Appendix: Search Patterns Used

```bash
# Find .get() with defaults
rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/

# Find environment variable defaults
rg "getenv\(.*," src/elspeth/

# Find "or" fallbacks
rg "or \[|\{\}" src/elspeth/

# Find conditional defaults
rg "if not .* else" src/elspeth/
```

---

## Next Steps

1. Review this audit with team
2. Prioritize CRITICAL defaults for immediate removal
3. Create security enforcement tests
4. Update schemas with required fields
5. Run test suite to verify no breakage
6. Document policy in CONTRIBUTING.md
