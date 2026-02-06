# Audit: tests/plugins/test_discovery.py

## Summary
Tests for dynamic plugin discovery system. Comprehensive coverage of discovery, deduplication, hookimpl generation, and integration with PluginManager.

## Findings

### 1. Good Practices
- Tests discovery of specific plugins (csv, passthrough, etc.)
- Tests exclusion of non-plugin files (__init__.py, base.py)
- Tests skipping abstract classes
- Tests duplicate name detection and error handling
- Tests discovery across all plugin directories
- Tests expected plugin counts with clear update instructions
- Tests hookimpl generation and pluggy integration

### 2. Issues

#### Hardcoded Path Construction
- **Location**: Lines 18, 28, 38, 48, 60
- **Issue**: `Path(__file__).parent.parent.parent / "src" / "elspeth" / "plugins"`
- **Impact**: Low - fragile if directory structure changes
- **Recommendation**: Use importlib.resources or a fixture

#### Expected Counts Need Manual Updates
- **Location**: Lines 135-137
- **Issue**: `EXPECTED_SOURCE_COUNT = 4`, etc. require manual updates when plugins added
- **Impact**: Low - test will fail clearly when counts change
- **Note**: This is actually a feature - forces awareness of plugin additions

#### Complex Mock Setup
- **Location**: Lines 270-357
- **Issue**: test_discover_all_raises_on_duplicate_names has extensive monkeypatching
- **Impact**: Medium - complex setup may not catch real discovery issues
- **Recommendation**: Consider creating actual test plugin files in tmp_path

### 3. Missing Coverage

#### No Tests for Discovery Errors
- What happens if a plugin file has syntax errors?
- What happens if a plugin file raises during import?

#### No Tests for Plugin Load Order
- Is discovery order deterministic?
- Does alphabetical ordering matter?

### 4. Good Duplicate Detection Tests

- test_duplicate_names_raise_value_error creates real files in tmp_path
- test_discover_all_raises_on_duplicate_names uses mocking for isolation
- Both approaches together provide good coverage

## Verdict
**PASS** - Solid coverage of discovery system. Some fragility around path construction.

## Risk Assessment
- **Defects**: None
- **Overmocking**: Medium - one test heavily mocks discovery
- **Missing Coverage**: Low - error handling during import
- **Tests That Do Nothing**: None
- **Inefficiency**: None
