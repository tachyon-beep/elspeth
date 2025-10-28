# Phase 3: End-to-End Verification

**Objective**: Prove ADR-002 validation now works end-to-end

**Estimated Effort**: 1-2 hours
**Priority**: CRITICAL - Blocks merge

---

## Verification Strategy

1. **Automated Tests** - Comprehensive test suite
2. **Manual Testing** - Real configurations
3. **Type Checking** - Protocol conformance
4. **Documentation** - Update ADR-002 status

---

## 1. Automated Test Verification

### 1.1 Full Test Suite (ALL tests)

```bash
# Run ALL tests (800+ tests)
pytest tests/ -v

# Expected: All PASS (zero regressions)
```

**If failures occur**:
- Review failure output
- Determine if test needs updating (reflects new behavior)
- OR if implementation has bug

---

### 1.2 ADR-002 Specific Tests

```bash
# Run all ADR-002 tests
pytest tests/test_adr002*.py -v

# Expected results:
# - test_adr002_baseplugin_compliance.py: All PASS (no xfails)
# - test_adr002_suite_integration.py: All PASS
# - test_adr002_error_handling.py: All PASS
# - test_adr002_middleware_integration.py: All PASS
```

---

### 1.3 Security Property Verification

```bash
# Run ONLY security property tests
pytest tests/test_adr002_baseplugin_compliance.py::TestSecurityPropertiesAfterFix -v

# Expected: All PASS (xfails removed during Phase 1)
```

**Critical Tests** (must ALL pass):
- `test_secret_datasource_unofficial_sink_blocked` - ✅ Mismatch detected
- `test_unofficial_datasource_secret_sink_allowed` - ✅ Uplifting works
- `test_all_datasources_implement_baseplugin` - ✅ Protocol conformance
- `test_validate_can_operate_at_level_raises_correctly` - ✅ Error handling
- `test_validation_no_longer_short_circuits` - ✅ **CRITICAL** - Proves fix worked!

---

## 2. Manual Testing

### 2.1 Test SECRET → UNOFFICIAL (MUST FAIL)

**Create test configuration**:

```yaml
# /tmp/test_secret_unofficial.yaml
datasources:
  secret_passwords:
    type: csv_local
    path: data/passwords.csv
    security_level: SECRET
    retain_local: false

sinks:
  public_output:
    type: csv_file
    path: outputs/public_report.csv
    security_level: UNOFFICIAL

experiments:
  - name: security_test
    datasource: secret_passwords
    sinks:
      - public_output
```

**Create test data**:
```bash
mkdir -p /tmp/test_data
echo "username,password" > /tmp/test_data/passwords.csv
echo "admin,SuperSecret123" >> /tmp/test_data/passwords.csv
```

**Run experiment**:
```bash
python -m elspeth.cli \
  --settings /tmp/test_secret_unofficial.yaml \
  --suite-root /tmp/test_suite \
  --reports-dir /tmp/outputs

# ✅ EXPECTED: SecurityValidationError raised
# ❌ FAILURE: If experiment succeeds, validation not working!
```

**Verify output**:
```bash
# Check error message
# MUST contain:
# - "SecurityValidationError"
# - "requires SECRET"
# - "envelope is UNOFFICIAL"
# OR similar mismatch indication

# Verify data was NOT written
ls /tmp/outputs/public_report.csv
# Should NOT exist (validation failed before data retrieval)
```

---

### 2.2 Test UNOFFICIAL → SECRET (MUST SUCCEED)

**Create test configuration**:

```yaml
# /tmp/test_unofficial_secret.yaml
datasources:
  public_data:
    type: csv_local
    path: data/public.csv
    security_level: UNOFFICIAL
    retain_local: false

sinks:
  secure_output:
    type: csv_file
    path: outputs/secure_report.csv
    security_level: SECRET

experiments:
  - name: uplifting_test
    datasource: public_data
    sinks:
      - secure_output
```

**Create test data**:
```bash
echo "metric,value" > /tmp/test_data/public.csv
echo "count,42" >> /tmp/test_data/public.csv
```

**Run experiment**:
```bash
python -m elspeth.cli \
  --settings /tmp/test_unofficial_secret.yaml \
  --suite-root /tmp/test_suite \
  --reports-dir /tmp/outputs

# ✅ EXPECTED: Experiment succeeds (uplifting allowed)
# ❌ FAILURE: If SecurityValidationError raised, too strict!
```

**Verify output**:
```bash
# Check output file exists
ls /tmp/outputs/secure_report.csv
# MUST exist

# Verify data written
cat /tmp/outputs/secure_report.csv
# MUST contain test data
```

---

### 2.3 Test Multi-Sink Validation

**Create configuration with mixed sinks**:

```yaml
# /tmp/test_multi_sink.yaml
datasources:
  secret_data:
    type: csv_local
    path: data/secret.csv
    security_level: SECRET
    retain_local: false

sinks:
  secure_sink_1:
    type: csv_file
    path: outputs/secure1.csv
    security_level: SECRET

  secure_sink_2:
    type: csv_file
    path: outputs/secure2.csv
    security_level: SECRET

  public_sink:  # ← This should trigger failure
    type: csv_file
    path: outputs/public.csv
    security_level: UNOFFICIAL

experiments:
  - name: multi_sink_test
    datasource: secret_data
    sinks:
      - secure_sink_1
      - secure_sink_2
      - public_sink
```

**Run experiment**:
```bash
python -m elspeth.cli \
  --settings /tmp/test_multi_sink.yaml \
  --suite-root /tmp/test_suite \
  --reports-dir /tmp/outputs

# ✅ EXPECTED: SecurityValidationError (3rd sink fails validation)
# ❌ FAILURE: If only first 2 sinks validated, validation incomplete!
```

---

## 3. Type Checking Verification

### 3.1 MyPy Full Codebase

```bash
# Type check entire src/elspeth
mypy src/elspeth --strict

# Expected: Clean (no protocol violations)
```

**Common MyPy Issues**:

If MyPy complains about protocol conformance:
```
error: "CSVLocalDataSource" does not explicitly implement protocol "BasePlugin"
```

**Solution**: Plugins implement protocol **duck-typing style** (no explicit inheritance needed). If MyPy complains, verify:
1. Both methods exist: `get_security_level()`, `validate_can_operate_at_level()`
2. Signatures match protocol exactly
3. Return types correct

---

### 3.2 Ruff Linting

```bash
# Lint entire codebase
ruff check src tests

# Expected: Clean (or pre-existing issues only)
```

---

## 4. Performance Verification

### 4.1 Validation Overhead Measurement

**Goal**: Confirm validation adds <1ms overhead per suite

**Test**:
```python
import time
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner

# Create experiment with 10 sinks
config = create_config_with_n_sinks(n=10)

# Time validation
start = time.perf_counter()
runner = ExperimentSuiteRunner(config)
runner._validate_component_clearances(SecurityLevel.OFFICIAL)
end = time.perf_counter()

validation_time_ms = (end - start) * 1000

print(f"Validation time (10 sinks): {validation_time_ms:.2f}ms")

# Expected: <1ms total (negligible overhead)
assert validation_time_ms < 1.0, f"Validation too slow: {validation_time_ms}ms"
```

---

## 5. Documentation Updates

### 5.1 Update ADR-002 Status

**File**: `docs/architecture/decisions/002-security-architecture.md`

**Add to end of document**:

```markdown
## Implementation Status

**Status**: ✅ COMPLETE - Fully implemented and verified (2025-10-25)

**BasePlugin Protocol Compliance**:
All 26 concrete plugin classes implement the BasePlugin protocol:
- 4 datasources: BaseCSVDataSource, CSVLocalDataSource, CSVBlobDataSource, BlobDataSource
- 6 LLM clients: AzureOpenAIClient, OpenAIHTTPClient, MockLLMClient, StaticLLMClient, + middleware
- 16 sinks: All sink implementations in plugins/nodes/sinks/

**Validation Proven**:
- ✅ SECRET→UNOFFICIAL configurations correctly blocked (ADR-002 Threat T1)
- ✅ UNOFFICIAL→SECRET configurations correctly allowed (uplifting works)
- ✅ Multi-sink validation works (all sinks checked)
- ✅ Zero regressions (all 800+ tests pass)
- ✅ Type system enforces protocol conformance (MyPy clean)

**Test Coverage**:
- Characterization tests: Document pre-implementation state
- Security property tests: Verify ADR-002 guarantees
- Integration tests: End-to-end validation with real plugins
- Manual verification: Confirms validation works in practice

**Migration**: See `docs/migration/adr-002-baseplugin-completion/` for implementation details.
```

---

### 5.2 Update ADR-002-A Status

**File**: `docs/architecture/decisions/002-a-trusted-container-model.md`

**Add similar implementation status section**

---

## Verification Checklist

### Automated Testing
- [ ] Full test suite passes: `pytest tests/ -v` (all 800+ tests)
- [ ] ADR-002 tests pass: `pytest tests/test_adr002*.py -v`
- [ ] Security property tests pass (no xfails)
- [ ] MyPy clean: `mypy src/elspeth --strict`
- [ ] Ruff clean: `ruff check src tests`

### Manual Testing
- [ ] SECRET→UNOFFICIAL blocked (config fails validation)
- [ ] UNOFFICIAL→SECRET allowed (config succeeds)
- [ ] Multi-sink validation works (all sinks checked)
- [ ] Error messages are clear and actionable

### Performance
- [ ] Validation overhead <1ms per suite
- [ ] No performance regressions in full test suite

### Documentation
- [ ] ADR-002 updated with implementation status
- [ ] ADR-002-A updated with implementation status
- [ ] Migration documentation complete

### Code Quality
- [ ] No hasattr checks in validation code
- [ ] All 26 plugins have BasePlugin methods
- [ ] Comprehensive docstrings on validation methods
- [ ] Type hints correct throughout

---

## Exit Criteria

**MUST HAVE (Blocking)**:
- ✅ All 800+ tests pass (zero regressions)
- ✅ SECRET→UNOFFICIAL correctly blocked
- ✅ UNOFFICIAL→SECRET correctly allowed
- ✅ MyPy clean, Ruff clean
- ✅ Documentation updated

**SHOULD HAVE**:
- ✅ Manual verification confirms validation works
- ✅ Performance benchmarks show <1ms overhead
- ✅ All stakeholders reviewed changes

**NICE TO HAVE**:
- ⭕ Performance baseline documented
- ⭕ Comprehensive ADR status report

---

## Final Approval

**Before merging ADR-002 branch**:

1. Review this verification report with team
2. Confirm all exit criteria met
3. Get sign-off from:
   - [ ] Security Team (validation works correctly)
   - [ ] Platform Team (no regressions, performance OK)
   - [ ] Tech Lead (architecture approved)

---

## Post-Merge Actions

1. ⭕ Announce ADR-002 completion
2. ⭕ Update project roadmap (ADR-002 ✅ COMPLETE)
3. ⭕ Proceed with ADR-003/004 migration
4. ⭕ Close related security issues/tickets

---

🤖 **Generated with [Claude Code](https://claude.com/claude-code)**

**Verification Completed**: [DATE]
**Verified By**: [NAME]
**Sign-Off**: [STAKEHOLDERS]
