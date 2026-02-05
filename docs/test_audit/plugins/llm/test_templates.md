# Test Audit: test_templates.py

**File:** `tests/plugins/llm/test_templates.py`
**Lines:** 236
**Audited:** 2026-02-05

## Summary

Comprehensive tests for the PromptTemplate Jinja2 wrapper. Good coverage of template features, security sandbox, lookup functionality, and canonicalization error handling. The P2-2026-01-31 regression tests are well-documented.

## Findings

### 1. Good Practices Observed

- **Security testing** - Tests sandbox prevents dangerous operations (line 73-79)
- **Hash stability tests** - Verifies deterministic hashing for audit
- **Lookup data tests** - Comprehensive coverage of 2D lookups, iteration, missing keys
- **Regression tests** - Well-documented P2-2026-01-31 canonicalization fix (lines 165-236)
- **Edge case distinction** - Tests `None` vs `{}` lookup data semantics (lines 153-162)

### 2. Potential Issues

#### 2.1 Incomplete Sandbox Security Tests (Missing Coverage - Medium)

**Location:** Lines 73-79

Only one dangerous operation is tested (attribute traversal via `__class__.__mro__`). Other attack vectors are not tested:
- `{{ [].__class__.__bases__[0].__subclasses__() }}` - subclass enumeration
- `{% for c in [].__class__.__base__.__subclasses__() %}` - loop-based escape
- File/module access attempts

**Recommendation:** Add tests for other common Jinja2 sandbox escape vectors.

#### 2.2 Test Name Misleading: `test_render_returns_metadata`

**Location:** Lines 57-65

Test name suggests `render()` returns metadata, but it actually tests `render_with_metadata()`. The name should reflect the actual method being tested.

**Recommendation:** Rename to `test_render_with_metadata_returns_all_hashes`.

### 3. Missing Coverage

| Path Not Tested | Risk |
|-----------------|------|
| Template syntax errors | Low - constructor raises TemplateError |
| Nested template access (e.g., `{{ row.items[0].name }}`) | Medium - common pattern |
| Jinja2 filters (other than `default`) | Low - builtin filters |
| Jinja2 macros | Low - advanced feature |
| Empty template string | Low - edge case |

#### 3.1 Missing Test for Template Source Metadata Round-Trip

**Location:** Lines 81-93

The test verifies `template_source` and `lookup_source` are set, but doesn't verify they survive multiple renders or that different sources produce different metadata.

### 4. Tests That Do Nothing

None - all tests have meaningful assertions.

### 5. Test Quality Score

| Criterion | Score |
|-----------|-------|
| Defects | 0 |
| Overmocking | 0 |
| Missing Coverage | 2 (security vectors, nested access) |
| Tests That Do Nothing | 0 |
| Inefficiency | 0 |
| Structural Issues | 0 |

**Overall: PASS** - Well-structured tests with good regression coverage. Consider expanding security testing.

## Specific Test Review

### TestPromptTemplateCanonicalSafety (Lines 165-236)

This class is an excellent example of regression test documentation:
- Clear docstrings referencing bug ticket P2-2026-01-31
- Tests both the error case and the continued-working case
- Verifies that `render()` (no hash) still works with NaN while `render_with_metadata()` fails
- Tests nested NaN to ensure deep inspection works

**Rating:** Exemplary
