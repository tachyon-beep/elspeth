# ADR-002 BasePlugin Implementation Checklist

**Quick Reference**: Use this checklist to track progress through all 3 phases

**Total Effort**: 6-8 hours (1 day)
**Priority**: P0 - BLOCKS ADR-002 MERGE

---

## Phase 0: Safety Net Construction (2-3 hours)

### Preparation
- [ ] Read `README.md` (understand the problem)
- [ ] Read `PHASE_0_TEST_SPECIFICATION.md` (test strategy)
- [ ] Confirm current branch: `feature/adr-002-security-enforcement`

### Test File Creation
- [ ] Create `tests/test_adr002_baseplugin_compliance.py`
- [ ] Add imports and test class structure

### Category 1: Characterization Tests
- [ ] Write `test_basecsvdatasource_no_get_security_level`
- [ ] Write `test_basecsvdatasource_no_validate_method`
- [ ] Write `test_all_datasource_classes_missing_methods`
- [ ] Write `test_csvfilesink_no_get_security_level`
- [ ] Write `test_csvfilesink_no_validate_method`
- [ ] Run tests: `pytest tests/test_adr002_baseplugin_compliance.py -v -k Characterization`
- [ ] **Expected**: All PASS (documents current broken state)

### Category 2: Security Bug Tests
- [ ] Write `test_secret_to_unofficial_currently_allowed`
- [ ] Write `test_hasattr_check_returns_false`
- [ ] Run tests: `pytest tests/test_adr002_baseplugin_compliance.py -v -k SecurityBug`
- [ ] **Expected**: All PASS (proves validation skips)

### Category 3: Security Property Tests
- [ ] Write `test_secret_datasource_unofficial_sink_blocked` (with @pytest.mark.xfail)
- [ ] Write `test_unofficial_datasource_secret_sink_allowed` (with @pytest.mark.xfail)
- [ ] Write `test_all_datasources_implement_baseplugin` (with @pytest.mark.xfail)
- [ ] Write `test_validate_can_operate_at_level_raises_correctly` (with @pytest.mark.xfail)
- [ ] Write `test_validate_can_operate_at_level_succeeds_when_safe` (with @pytest.mark.xfail)
- [ ] Run tests: `pytest tests/test_adr002_baseplugin_compliance.py -v -k SecurityProperties`
- [ ] **Expected**: All XFAIL (will pass after implementation)

### Category 4: Integration Tests
- [ ] Write `test_suite_runner_validates_before_data_load` (with @pytest.mark.xfail)
- [ ] Write `test_multi_sink_validation_all_checked` (with @pytest.mark.xfail)
- [ ] Run tests: `pytest tests/test_adr002_baseplugin_compliance.py -v -k Integration`
- [ ] **Expected**: All XFAIL (will pass after implementation)

### Phase 0 Exit
- [ ] Full test file runs: `pytest tests/test_adr002_baseplugin_compliance.py -v`
- [ ] Test count: ~10-15 tests
- [ ] All characterization/bug tests PASS
- [ ] All property/integration tests XFAIL
- [ ] Commit: `git add tests/ && git commit -m "test: Add ADR-002 BasePlugin compliance test suite"`

**Phase 0 Complete**: Safety net in place, ready for implementation

---

## Phase 1: Implementation (2-3 hours)

### Preparation
- [ ] Read `PHASE_1_IMPLEMENTATION_GUIDE.md`
- [ ] Verify Phase 0 tests exist and run correctly
- [ ] Create implementation tracking branch (optional)

### Group 1: Datasources (4 classes, ~30 minutes)

#### BaseCSVDataSource
- [ ] Open `src/elspeth/plugins/nodes/sources/_csv_base.py`
- [ ] Add `get_security_level()` method after `__init__`
- [ ] Add `validate_can_operate_at_level()` method
- [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k BaseCSVDataSource`
- [ ] MyPy: `mypy src/elspeth/plugins/nodes/sources/_csv_base.py`
- [ ] Commit: `git add src/elspeth/plugins/nodes/sources/_csv_base.py && git commit -m "feat: Add BasePlugin protocol to BaseCSVDataSource"`

#### CSVLocalDataSource
- [ ] Open `src/elspeth/plugins/nodes/sources/csv_local.py`
- [ ] Verify methods inherited from BaseCSVDataSource
- [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k CSVLocalDataSource`
- [ ] Commit (if changes needed)

#### CSVBlobDataSource
- [ ] Open `src/elspeth/plugins/nodes/sources/csv_blob.py`
- [ ] Verify methods inherited from BaseCSVDataSource
- [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k CSVBlobDataSource`
- [ ] Commit (if changes needed)

#### BlobDataSource
- [ ] Open `src/elspeth/plugins/nodes/sources/blob.py`
- [ ] Add `get_security_level()` method
- [ ] Add `validate_can_operate_at_level()` method
- [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k BlobDataSource`
- [ ] MyPy: `mypy src/elspeth/plugins/nodes/sources/blob.py`
- [ ] Commit: `git add src/elspeth/plugins/nodes/sources/blob.py && git commit -m "feat: Add BasePlugin protocol to BlobDataSource"`

### Group 2: LLM Clients (6 classes, ~45 minutes)

#### AzureOpenAIClient
- [ ] Open `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`
- [ ] Add `get_security_level()` method
- [ ] Add `validate_can_operate_at_level()` method
- [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k AzureOpenAIClient`
- [ ] Commit

#### OpenAIHTTPClient
- [ ] Open `src/elspeth/plugins/nodes/transforms/llm/openai_http.py`
- [ ] Add methods
- [ ] Test
- [ ] Commit

#### MockLLMClient
- [ ] Open `src/elspeth/plugins/nodes/transforms/llm/mock_llm.py`
- [ ] Add methods
- [ ] Test
- [ ] Commit

#### StaticLLMClient
- [ ] Open `src/elspeth/plugins/nodes/transforms/llm/static_llm.py`
- [ ] Add methods
- [ ] Test
- [ ] Commit

#### Middleware (check if needed)
- [ ] Review `src/elspeth/plugins/nodes/transforms/llm/middleware/*.py`
- [ ] Add methods if classes have `security_level` attribute
- [ ] Test
- [ ] Commit (if applicable)

### Group 3: Sinks (16 classes, ~90 minutes)

**Strategy**: Process all sinks systematically

- [ ] List all sink files: `ls src/elspeth/plugins/nodes/sinks/*.py`
- [ ] For EACH sink file:
  - [ ] Open file
  - [ ] Add `get_security_level()` method
  - [ ] Add `validate_can_operate_at_level()` method
  - [ ] Test: `pytest tests/test_adr002_baseplugin_compliance.py -v -k <SinkName>`
  - [ ] Commit: `git add <file> && git commit -m "feat: Add BasePlugin protocol to <SinkName>"`

**Sink Checklist** (check off as completed):
- [ ] CSVFileSink
- [ ] ExcelSink
- [ ] JSONSink
- [ ] MarkdownSink
- [ ] SignedBundleSink
- [ ] RepositorySink
- [ ] [Additional sinks - list after survey]

### Phase 1 Exit
- [ ] All 26 plugin classes have both methods
- [ ] Run full test suite: `pytest tests/test_adr002_baseplugin_compliance.py -v`
- [ ] **Expected**: Category 3 (Security Properties) tests now PASS (not xfail)
- [ ] MyPy clean: `mypy src/elspeth/plugins/`
- [ ] Ruff clean: `ruff check src/elspeth/plugins/`
- [ ] Commit count: 1 bulk commit OR 26 individual commits (your choice)

**Phase 1 Complete**: All plugins implement BasePlugin protocol

---

## Phase 2: Validation Cleanup (30 minutes)

### Preparation
- [ ] Read `PHASE_2_VALIDATION_CLEANUP.md`
- [ ] Verify Phase 1 complete (all plugins have methods)

### Implementation
- [ ] Open `src/elspeth/core/experiments/suite_runner.py`
- [ ] Locate `_validate_component_clearances()` method
- [ ] Remove `if hasattr(self.datasource, "validate_can_operate_at_level"):` check
- [ ] Remove `if hasattr(self.llm_client, "validate_can_operate_at_level"):` check
- [ ] Remove `if hasattr(sink, "validate_can_operate_at_level"):` check from loop
- [ ] Update method docstring with protocol requirement explanation
- [ ] Save file

### Testing
- [ ] Run integration tests: `pytest tests/test_adr002_suite_integration.py -v`
- [ ] MyPy: `mypy src/elspeth/core/experiments/suite_runner.py`
- [ ] Ruff: `ruff check src/elspeth/core/experiments/suite_runner.py`

### Phase 2 Exit
- [ ] No hasattr checks remain in validation code
- [ ] All integration tests pass
- [ ] MyPy clean
- [ ] Commit: `git add src/elspeth/core/experiments/suite_runner.py && git commit -m "refactor: Remove hasattr checks from ADR-002 validation (BasePlugin guaranteed)"`

**Phase 2 Complete**: Validation code simplified

---

## Phase 3: Verification (1-2 hours)

### Preparation
- [ ] Read `PHASE_3_VERIFICATION.md`
- [ ] Ensure Phases 0-2 complete

### Automated Testing
- [ ] Full test suite: `pytest tests/ -v` (all 800+ tests)
  - [ ] **Expected**: All PASS
- [ ] ADR-002 tests: `pytest tests/test_adr002*.py -v`
  - [ ] **Expected**: All PASS
- [ ] MyPy: `mypy src/elspeth --strict`
  - [ ] **Expected**: Clean
- [ ] Ruff: `ruff check src tests`
  - [ ] **Expected**: Clean

### Manual Testing

#### Test 1: SECRET → UNOFFICIAL (Must FAIL)
- [ ] Create `/tmp/test_secret_unofficial.yaml` with SECRET datasource + UNOFFICIAL sink
- [ ] Create test data
- [ ] Run: `python -m elspeth.cli --settings /tmp/test_secret_unofficial.yaml ...`
- [ ] **Expected**: SecurityValidationError raised
- [ ] Verify error message mentions "SECRET" and "UNOFFICIAL"
- [ ] Verify output file NOT created

#### Test 2: UNOFFICIAL → SECRET (Must SUCCEED)
- [ ] Create `/tmp/test_unofficial_secret.yaml` with UNOFFICIAL datasource + SECRET sink
- [ ] Create test data
- [ ] Run: `python -m elspeth.cli --settings /tmp/test_unofficial_secret.yaml ...`
- [ ] **Expected**: Experiment succeeds
- [ ] Verify output file created with correct data

#### Test 3: Multi-Sink Validation
- [ ] Create `/tmp/test_multi_sink.yaml` with 2 SECRET sinks + 1 UNOFFICIAL sink
- [ ] Run experiment
- [ ] **Expected**: SecurityValidationError on 3rd sink
- [ ] Verify all sinks validated (not just first)

### Documentation
- [ ] Update `docs/architecture/decisions/002-security-architecture.md` with implementation status
- [ ] Update `docs/architecture/decisions/002-a-trusted-container-model.md` with status
- [ ] Mark ADR-002 as "COMPLETE - Fully implemented and verified"

### Phase 3 Exit
- [ ] All automated tests pass
- [ ] All manual tests produce expected results
- [ ] Documentation updated
- [ ] Stakeholder sign-off obtained:
  - [ ] Security Team
  - [ ] Platform Team
  - [ ] Tech Lead

**Phase 3 Complete**: ADR-002 implementation verified

---

## Final Checklist (Before Merge)

### Code Quality
- [ ] All 800+ tests pass
- [ ] MyPy clean (no type errors)
- [ ] Ruff clean (no lint errors)
- [ ] No regressions introduced

### Security Validation
- [ ] SECRET→UNOFFICIAL blocked
- [ ] UNOFFICIAL→SECRET allowed
- [ ] Multi-sink validation works
- [ ] Error messages clear and actionable

### Documentation
- [ ] ADR-002 marked as COMPLETE
- [ ] Migration documentation in `docs/migration/adr-002-baseplugin-completion/`
- [ ] Implementation status documented

### Approval
- [ ] Security Team sign-off
- [ ] Platform Team sign-off
- [ ] Tech Lead sign-off

---

## Post-Merge Actions

- [ ] Announce ADR-002 completion to team
- [ ] Update project roadmap (ADR-002 ✅)
- [ ] Close related issues/tickets
- [ ] Proceed with ADR-003/004 migration

---

**Checklist Version**: 1.0
**Last Updated**: 2025-10-25
**Completion Date**: [FILL IN WHEN DONE]
