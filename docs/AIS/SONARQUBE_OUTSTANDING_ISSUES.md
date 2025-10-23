# Outstanding SonarQube Issues (Excluding Production Blockers)

**Repository:** elspeth
**Branch:** remediation
**Analysis Date:** 2025-10-23
**Total Outstanding:** 69 issues (excluding AUD-0007 and AUD-0008)

---

## Summary by Category

| Category | Count | Effort | Priority |
|----------|-------|--------|----------|
| **Cognitive Complexity (15-70)** | 48 | L-XL | HIGH-MEDIUM |
| **String Duplication** | 4 | S | LOW |
| **Empty Code Blocks** | 11 | S | LOW |
| **Unused Parameters** | 4 | S | LOW |
| **Too Many Parameters** | 2 | M | MEDIUM |
| **PEP 695 Type Syntax** | 4 | S | LOW |
| **Nested If Statements** | 1 | S | LOW |
| **Redundant Exceptions** | 2 | S | LOW |
| **Regex Simplification** | 1 | S | LOW |
| **TODO Comments** | 2 | S | LOW |

**Total Issues:** 79 (excluding 2 production blockers)

---

## 1. Cognitive Complexity Issues (48 functions)

### Priority 1: VERY HIGH Complexity (50+) — 5 functions

| File | Line | Complexity | Function | Effort | Notes |
|------|------|------------|----------|--------|-------|
| `visual_report.py` | 216 | **63** | `_generate_visual_reports()` | M | AUD-0006: Chart generation |
| `config/validation.py` | 142 | **59** | `validate_suite_config()` | L | AUD-0009: Config validation |
| `pii_shield.py` | 471 | **56** | `detect_pii()` | L | AUD-0010: PII detection |
| `score_significance.py` | 73 | **51** | `compute_score_significance()` | M | AUD-0011: Statistical tests |
| `zip_bundle.py` | 79 | **50** | `create_bundle()` | M | AUD-0012: Artifact bundling |

**Recommendation**: Already documented as AUD-0006 through AUD-0012 in audit findings.

---

### Priority 2: HIGH Complexity (40-49) — 6 functions

| File | Line | Complexity | Function/Context | Effort |
|------|------|------------|------------------|--------|
| `runner.py` | 551 | **44** | Row processing helper | M |
| `runner.py` | 715 | **44** | Parallel execution | M |
| `score_agreement.py` | 53 | **44** | Agreement calculation | M |
| `_stats_helpers.py` | 123 | **42** | Statistical analysis | M |
| `classified_material.py` | 379 | **41** | Material classification | M |
| `rationale_analysis.py` | 120 | **39** | Rationale scoring | M |

**Recommendation**: Refactor in Phase 2 (medium complexity sprint).

---

### Priority 3: MEDIUM-HIGH Complexity (30-39) — 5 functions

| File | Line | Complexity | Context | Effort |
|------|------|------------|---------|--------|
| `enhanced_visual_report.py` | 185 | **34** | Enhanced visualization | M |
| `artifact_pipeline.py` | 324 | **34** | Pipeline execution | M |
| `suite_runner.py` | 45 | **31** | Suite initialization | M |
| `referee_alignment.py` | 86 | **31** | Referee scoring | S-M |
| `score_flip_analysis.py` | 71 | **30** | Score flip detection | S-M |

---

### Priority 4: MEDIUM Complexity (20-29) — 23 functions

**Statistical & Aggregation** (12 functions):
- `_stats_helpers.py:65` — Complexity 26
- `_stats_helpers.py:208` — Complexity 21
- `runner.py:267` — Complexity 26
- `config_merger.py:56` — Complexity 19
- `config/validation.py:26` — Complexity 27
- `score_assumptions.py:63` — Complexity 24
- `criteria_effects.py:73` — Complexity 23
- `score_power.py:73` — Complexity 23
- `score_stats.py:48` — Complexity 23
- `retrieval/providers.py:148` — Complexity 23
- `prompt_variants.py:40` — Complexity 24
- `cli.py:507` — Complexity 23

**Sinks & Visual** (6 functions):
- `enhanced_visual_report.py:71` — Complexity 28
- `visual_report.py:53` — Complexity 29
- `visual_report.py:281` — Complexity 16 (borderline)
- `local_bundle.py:52` — Complexity 27
- `zip_bundle.py:205` — Complexity 25
- `blob.py:70` — Complexity 22

**Other** (5 functions):
- `reporting.py:144` — Complexity 22
- `reporting.py:181` — Complexity 22
- `plugin_helpers.py:33` — Complexity 24
- `model_factory.py:50` — Complexity 22
- `validation/rules.py:11` — Complexity 21

**Recommendation**: Refactor opportunistically or document complex sections.

---

### Priority 5: LOW Complexity (16-19) — 9 functions

**Acceptable for specialized logic, document edge cases**:

| File | Line | Complexity | Notes |
|------|------|------------|-------|
| `file_copy.py` | 54 | 16 | File operations |
| `reproducibility_bundle.py` | 84 | 21 | Bundle creation |
| `analytics_report.py` | 50 | 17 | Report generation |
| `excel.py` | 123 | 19 | Excel formatting |
| `csv_file.py` | 136 | 17 | CSV writing |
| `cli.py` | 131 | 18 | CLI routing |
| `cli.py` | 472 | 18 | CLI options |
| `artifact_pipeline.py` | 111 | 17 | Dependency resolution |
| `blob_store.py` | 41 | 16 | Blob operations |

**Recommendation**: Monitor during future changes; add inline documentation.

---

## 2. String Duplication (S1192) — 4 instances

**Rule**: Define constants instead of duplicating string literals 3+ times.

| File | Line | Duplicated String | Occurrences | Fix |
|------|------|-------------------|-------------|-----|
| `pii_shield.py` | 126 | `r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b"` | 3 | `PHONE_PATTERN = r"..."` |
| `experiment_registry.py` | 128 | `"Unreachable: allow_none=False prevents None return"` | 5 | `UNREACHABLE_MSG = "..."` |
| `blob_store.py` | 65 | `"Provide either 'storage_uri' or all of..."` | 3 | `STORAGE_CONFIG_ERR = "..."` |
| `analytics_report.py` | 174 | `` `json `` | 4 | `JSON_CODE_FENCE = "```json"` |

**Effort**: S (1-2 hours total)

**Example Fix**:
```python
# Before
if not re.match(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b", phone):
    # ... later
    pattern = r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b"
    # ... again
    result = re.search(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b", text)

# After
PHONE_PATTERN = r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b"

if not re.match(PHONE_PATTERN, phone):
    # ... later
    pattern = PHONE_PATTERN
    # ... again
    result = re.search(PHONE_PATTERN, text)
```

---

## 3. Empty Code Blocks (S108) — 11 instances

**Rule**: Either remove or fill empty code blocks (pass statements).

All instances are in **baseline comparison plugins** with intentional placeholder implementations:

| File | Line | Method | Current State |
|------|------|--------|---------------|
| `baseline/category_effects.py` | 17 | `__init__()` | Empty `pass` |
| `baseline/criteria_effects.py` | 18 | `__init__()` | Empty `pass` |
| `baseline/outlier_detection.py` | 14 | `__init__()` | Empty `pass` |
| `baseline/referee_alignment.py` | 14 | `__init__()` | Empty `pass` |
| `baseline/score_assumptions.py` | 16 | `__init__()` | Empty `pass` |
| `baseline/score_bayesian.py` | 15 | `__init__()` | Empty `pass` |
| `baseline/score_cliffs_delta.py` | 15 | `__init__()` | Empty `pass` |
| `baseline/score_delta.py` | 11 | `__init__()` | Empty `pass` |
| `baseline/score_distribution.py` | 15 | `__init__()` | Empty `pass` |
| `baseline/score_flip_analysis.py` | 14 | `__init__()` | Empty `pass` |
| `baseline/score_practical.py` | 16 | `__init__()` | Empty `pass` |
| `baseline/score_significance.py` | 17 | `__init__()` | Empty `pass` |

**Effort**: S (2-3 hours)

**Recommended Fix** (Option 1 - Document Intent):
```python
def __init__(self):
    """Initialize baseline comparison plugin.

    Note: No initialization required for stateless comparison.
    All configuration is passed via compare() method.
    """
    pass  # Explicitly empty - no state to initialize
```

**Recommended Fix** (Option 2 - Remove Empty Method):
```python
# Remove __init__ entirely if not needed
class ScoreDeltaPlugin(BaselineComparisonPlugin):
    name = "score_delta"

    def compare(self, baseline_payload, variant_payload):
        # ... implementation
```

---

## 4. Unused Parameters (S1172) — 4 instances

**Rule**: Remove unused function parameters.

| File | Line | Parameter | Function | Fix |
|------|------|-----------|----------|-----|
| `cli.py` | 198 | `suite_root` | CLI handler | Remove or use |
| `cli.py` | 198 | `args` | CLI handler | Remove or use |
| `score_distribution.py` | 50 | `records` | Baseline comparison | Prefix `_records` |
| `score_extractor.py` | 83 | `row` | Row processing | Prefix `_row` |

**Effort**: S (30 minutes)

**Recommended Fix**:
```python
# Before
def handle_command(suite_root, args):
    # suite_root and args are not used
    return process_defaults()

# After (Option 1: Remove)
def handle_command():
    return process_defaults()

# After (Option 2: Prefix with _ if needed for protocol)
def handle_command(_suite_root, _args):
    """Unused params required by CLI protocol."""
    return process_defaults()
```

---

## 5. Too Many Parameters (S107) — 2 instances

**Rule**: Functions should not have more than 13 parameters (detected at 14+).

### Instance 1: `embeddings_store.py:218-233`

```python
def __init__(
    self,
    provider: str,
    namespace: str | None = None,
    dsn: str | None = None,
    endpoint: str | None = None,
    embed_model: str | None = None,
    # ... 9 more parameters
):
```

**Recommendation**: Use configuration object.

```python
@dataclass
class EmbeddingsStoreConfig:
    provider: str
    namespace: str | None = None
    dsn: str | None = None
    endpoint: str | None = None
    embed_model: str | None = None
    # ... other params

def __init__(self, config: EmbeddingsStoreConfig):
    self.config = config
    # ...
```

**Effort**: M (2-3 hours including tests)

---

### Instance 2: `blob.py:35-50`

```python
def __init__(
    self,
    storage_uri: str | None = None,
    account_name: str | None = None,
    account_key: str | None = None,
    # ... 11 more parameters
):
```

**Recommendation**: Use builder pattern or config object.

```python
@dataclass
class BlobSinkConfig:
    storage_uri: str | None = None
    account_name: str | None = None
    account_key: str | None = None
    # ... other params

    @classmethod
    def from_options(cls, options: dict) -> "BlobSinkConfig":
        return cls(**options)

def __init__(self, config: BlobSinkConfig):
    self.config = config
    # ...
```

**Effort**: M (2-3 hours including registry updates)

---

## 6. PEP 695 Type Parameter Syntax (S6792, S6796) — 4 instances

**Rule**: Use modern type parameter syntax (Python 3.12+).

| File | Line | Current Syntax | Modern Syntax |
|------|------|----------------|---------------|
| `registries/base.py` | 27 | `TypeVar("T")` | `type T` |
| `registries/base.py` | 80 | Generic type in function | Function with type param |
| `registries/base.py` | 116 | `TypeVar("U")` | `type U` |
| `registries/base.py` | 198 | Generic type in function | Function with type param |

**Effort**: S (1 hour)

**Example Fix**:
```python
# Before (Python 3.11 style)
from typing import TypeVar, Generic

T = TypeVar("T")

class Registry(Generic[T]):
    def create(self, name: str) -> T:
        ...

# After (Python 3.12+ PEP 695)
class Registry[T]:
    def create(self, name: str) -> T:
        ...
```

---

## 7. Nested If Statements (S1066) — 1 instance

**Rule**: Merge nested if statements when possible.

| File | Line | Current | Recommended |
|------|------|---------|-------------|
| `secure_mode.py` | 160 | `if a: if b: ...` | `if a and b: ...` |

**Effort**: S (5 minutes)

**Example Fix**:
```python
# Before
if endpoint_approved:
    if security_level_valid:
        process_request()

# After
if endpoint_approved and security_level_valid:
    process_request()
```

---

## 8. Redundant Exception Handling (S5713) — 2 instances

**Rule**: Remove redundant exception class in handler.

| File | Line | Issue | Impact |
|------|------|-------|--------|
| `_csv_base.py` | 97 | Catches same exception twice | Low - defensive coding |
| `_csv_base.py` | 211 | Catches same exception twice | Low - defensive coding |

**Effort**: S (10 minutes)

**Example Fix**:
```python
# Before
try:
    parse_csv()
except ValueError as e:
    logger.error(f"Parse error: {e}")
except ValueError:  # Redundant
    logger.error("Parse failed")

# After
try:
    parse_csv()
except ValueError as e:
    logger.error(f"Parse error: {e}")
```

---

## 9. Regex Simplification (S6353) — 1 instance

**Rule**: Use `\w` instead of `[a-zA-Z0-9_]`.

| File | Line | Current Pattern | Simplified |
|------|------|----------------|------------|
| `prompts/engine.py` | 15 | `[a-zA-Z0-9_]` | `\w` |

**Effort**: S (2 minutes)

**Example Fix**:
```python
# Before
VARIABLE_PATTERN = r"[a-zA-Z0-9_]+"

# After
VARIABLE_PATTERN = r"\w+"
```

---

## 10. TODO Comments (S1135) — 2 instances

**Rule**: Complete tasks associated with TODO comments or create tracking issues.

| File | Line | TODO Comment | Action |
|------|------|--------------|--------|
| `signed.py` | 140 | Implementation note | Review and complete or document |
| `azure_openai.py` | 55 | Feature enhancement | Create issue or implement |

**Effort**: S (30 minutes to review, variable for completion)

**Recommended Action**:
```python
# Before
def process_signature():
    # TODO: Add support for EdDSA signatures
    pass

# After (Option 1: Complete)
def process_signature():
    """Process signature with EdDSA support."""
    # Implementation added

# After (Option 2: Create Issue)
def process_signature():
    # NOTE: EdDSA support planned for v3.1 (see issue #456)
    pass
```

---

## Quick Win Action Plan

### Phase 1: Low-Hanging Fruit (1 day)

**Total Effort**: S (6-8 hours)
**Issues Resolved**: 25

1. **String Duplication** (1-2 hours)
   - Extract 4 constants
   - Update references
   - Run tests

2. **Empty Blocks** (2-3 hours)
   - Add docstrings to 11 `__init__` methods
   - Document intent clearly

3. **Unused Parameters** (30 minutes)
   - Prefix 4 parameters with `_`
   - Add protocol compliance comments

4. **Nested If** (5 minutes)
   - Merge condition in `secure_mode.py`

5. **Redundant Exceptions** (10 minutes)
   - Remove duplicate handlers in `_csv_base.py`

6. **Regex Simplification** (2 minutes)
   - Replace `[a-zA-Z0-9_]` with `\w`

7. **PEP 695 Type Syntax** (1 hour)
   - Modernize type parameters in `base.py`
   - Requires Python 3.12+

8. **TODO Comments** (30 minutes)
   - Review 2 TODOs
   - Create issues or document

**Validation**:
```bash
# Re-run SonarQube
sonar-scanner

# Expected reduction: 25 issues → 54 remaining
# Focus on complexity issues only
```

---

### Phase 2: Configuration Objects (2 days)

**Total Effort**: M (12-16 hours)
**Issues Resolved**: 2

1. **EmbeddingsStore Refactoring** (1 day)
   - Create `EmbeddingsStoreConfig` dataclass
   - Update factory in registry
   - Update tests
   - Update documentation

2. **BlobSink Refactoring** (1 day)
   - Create `BlobSinkConfig` dataclass
   - Update factory in registry
   - Update tests
   - Update configuration examples

**Validation**:
```bash
# Run affected tests
pytest tests/test_outputs_embeddings_store.py -v
pytest tests/test_outputs_blob.py -v

# Verify registry integration
pytest tests/test_registry.py -v
```

---

### Phase 3: Medium Complexity Refactoring (1-2 weeks)

**Target**: 23 functions with complexity 20-29
**Approach**: Extract helper methods, simplify control flow

**Priority Ordering**:
1. **Statistical helpers** (high reuse)
2. **Visual sinks** (user-facing quality)
3. **Config/validation** (error prevention)
4. **CLI handlers** (user experience)

**Example Pattern**:
```python
# Before (complexity 27)
def validate_config(config):
    # 150 lines of nested validation logic
    if config.datasource:
        if config.datasource.type == "csv":
            if config.datasource.path:
                # ... more nesting
    # ... many more checks

# After (complexity ~8)
def validate_config(config):
    _validate_datasource(config.datasource)
    _validate_llm(config.llm)
    _validate_prompts(config.prompts)
    _validate_plugins(config.plugins)

def _validate_datasource(datasource):
    # Focused validation (complexity ~5)
```

---

## Monitoring & Prevention

### SonarQube Quality Gate

Configure quality gate to prevent new complexity:

```yaml
# sonar-project.properties
sonar.qualitygate.wait=true
sonar.qualitygate.timeout=300

# Quality gate conditions:
# - Cognitive Complexity ≤15 per function
# - No new HIGH severity issues
# - Coverage on new code ≥80%
# - Duplicated lines on new code ≤3%
```

### Pre-commit Hooks

Add complexity checks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: radon-complexity
        name: Radon Complexity Check
        entry: radon cc --min C --show-complexity src/
        language: system
        pass_filenames: false
```

### CI/CD Integration

```yaml
# .github/workflows/code-quality.yml
- name: SonarQube Analysis
  run: |
    sonar-scanner \
      -Dsonar.qualitygate.wait=true \
      -Dsonar.newCodePeriod.type=PREVIOUS_VERSION

- name: Fail on Quality Gate
  if: failure()
  run: exit 1
```

---

## Summary

**Total Outstanding Issues**: 69 (excluding 2 production blockers)

**By Effort**:
- **Quick Wins** (1-2 days): 25 issues
- **Medium Effort** (2-3 days): 2 issues
- **Long-term** (1-2 weeks): 23 complexity issues
- **Documented/Tracked**: 19 low-priority complexity issues

**Recommended Approach**:
1. **Week 1**: Complete quick wins (25 issues resolved)
2. **Week 2**: Refactor config objects (2 issues resolved)
3. **Weeks 3-4**: Medium complexity functions (10-15 issues resolved)
4. **Ongoing**: Monitor low-priority complexity during feature work

**Expected Final State**:
- **Quick wins resolved**: 27 issues
- **Complexity reduced**: 15-20 functions refactored
- **Remaining acceptable complexity**: 20-25 functions (documented)
- **SonarQube quality gate**: PASSING

---

**Document Status**: READY FOR SPRINT PLANNING
**Next Step**: Prioritize quick wins sprint (1-2 days)
**Owner**: Development Team
