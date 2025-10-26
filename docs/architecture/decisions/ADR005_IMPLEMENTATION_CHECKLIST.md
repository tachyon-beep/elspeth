# ADR-005 Implementation Checklist

## Overview

Implementation of frozen plugin capability (`allow_downgrade=False`) as specified in [ADR-005](005-frozen-plugin-capability.md).

**Estimated Effort**: 5-8 hours
**Complexity**: Low (single parameter + validation logic)
**Risk**: Low (backwards compatible, well-tested)

---

## Phase 1: Core Implementation (1-2 hours)

### File: `src/elspeth/core/base/plugin.py`

- [ ] **1.1** Update `BasePlugin.__init__()` signature
  ```python
  def __init__(
      self,
      *,
      security_level: SecurityLevel,
      allow_downgrade: bool = True,  # ← NEW parameter
      **kwargs: object
  ) -> None:
  ```

- [ ] **1.2** Add `_allow_downgrade` private field
  ```python
  self._security_level = security_level
  self._allow_downgrade = allow_downgrade  # ← NEW field
  super().__init__(**kwargs)
  ```

- [ ] **1.3** Add `allow_downgrade` read-only property (after `security_level` property)
  ```python
  @property
  def allow_downgrade(self) -> bool:
      """Read-only property for downgrade permission.

      Returns:
          bool: Whether plugin can operate at lower pipeline levels.
      """
      return self._allow_downgrade
  ```

- [ ] **1.4** Update `validate_can_operate_at_level()` with frozen check
  - Location: Between insufficient clearance check and method end
  - Insert after line ~195 (after existing insufficient clearance check)
  ```python
  # Existing: Check insufficient clearance
  if operating_level > self._security_level:
      raise SecurityValidationError(...)

  # NEW: Check frozen plugin downgrade rejection
  if operating_level < self._security_level and not self._allow_downgrade:
      raise SecurityValidationError(
          f"{type(self).__name__} is frozen at {self._security_level.name} "
          f"(allow_downgrade=False). Cannot operate at lower level {operating_level.name}. "
          f"This plugin requires exact level matching and does not support trusted downgrade."
      )
  ```

- [ ] **1.5** Update `__init__()` docstring
  - Add `allow_downgrade` parameter documentation
  - Add frozen plugin example to docstring

- [ ] **1.6** Update `validate_can_operate_at_level()` docstring
  - Add frozen plugin validation logic explanation
  - Add frozen plugin examples to docstring

- [ ] **1.7** Update class docstring
  - Add `_allow_downgrade` to Attributes section
  - Add `allow_downgrade` to Properties section

### Verification (Phase 1)

```bash
# Type checking
python -m mypy src/elspeth/core/base/plugin.py

# No existing tests should break (backwards compatible)
python -m pytest tests/test_adr002_baseplugin_compliance.py -v
python -m pytest tests/test_adr002_invariants.py -v
```

**Exit Criteria**: All existing tests pass, MyPy clean, no behavioral changes to default behavior.

---

## Phase 2: Test Coverage (2-3 hours)

### File: `tests/test_baseplugin_frozen.py` (NEW)

- [ ] **2.1** Create test file with module docstring
  ```python
  """Frozen Plugin Capability Tests (ADR-005).

  Tests the allow_downgrade=False capability for strict level enforcement.
  """
  ```

- [ ] **2.2** Create `MockPlugin` test fixture
  - Simple plugin accepting `security_level` and `allow_downgrade` parameters

- [ ] **2.3** Implement `TestDefaultTrustedDowngrade` class (5 tests)
  - `test_default_parameter_is_true` – Backwards compatibility
  - `test_trusted_downgrade_to_lower_level` – SECRET → OFFICIAL
  - `test_trusted_downgrade_to_lowest_level` – SECRET → UNOFFICIAL
  - `test_exact_match_allowed` – OFFICIAL → OFFICIAL
  - `test_insufficient_clearance_rejected` – OFFICIAL → SECRET (fails)

- [ ] **2.4** Implement `TestFrozenPlugin` class (5 tests)
  - `test_frozen_property_reflects_parameter` – Property check
  - `test_frozen_exact_match_allowed` – SECRET frozen → SECRET (succeeds)
  - `test_frozen_downgrade_rejected` – SECRET frozen → OFFICIAL (fails)
  - `test_frozen_two_level_downgrade_rejected` – SECRET frozen → UNOFFICIAL (fails)
  - `test_frozen_insufficient_clearance_rejected` – OFFICIAL frozen → SECRET (fails)

- [ ] **2.5** Implement `TestPropertyBased` class (2 parameterized tests)
  - `test_trusted_downgrade_matrix` – 3×3 matrix (9 test cases)
  - `test_frozen_matrix` – 3×3 matrix (9 test cases)

**Test Count**: 12 unit tests + 18 parameterized = **30 total test cases**

### File: `tests/test_adr002_suite_integration.py` (additions)

- [ ] **2.6** Add helper functions
  - `create_frozen_datasource(level)` – Datasource with `allow_downgrade=False`
  - `create_frozen_sink(level)` – Sink with `allow_downgrade=False`

- [ ] **2.7** Add integration tests (3 tests)
  - `test_frozen_datasource_exact_match` – All SECRET (succeeds)
  - `test_frozen_datasource_rejects_lower_level_sink` – SECRET frozen + OFFICIAL sink (fails)
  - `test_frozen_sink_accepts_higher_level_datasource` – SECRET source + OFFICIAL frozen sink (succeeds)

### Verification (Phase 2)

```bash
# Run new frozen tests
python -m pytest tests/test_baseplugin_frozen.py -v

# Run integration tests
python -m pytest tests/test_adr002_suite_integration.py -v

# Check coverage on new code
python -m pytest tests/test_baseplugin_frozen.py --cov=elspeth.core.base.plugin --cov-report=term-missing

# Mutation testing (optional but recommended)
mutmut run --paths-to-mutate src/elspeth/core/base/plugin.py
```

**Exit Criteria**: All 33 new tests pass, 100% coverage on frozen code paths, mutation testing survivors ≤10%.

---

## Phase 3: Documentation (1-2 hours)

### File: `docs/architecture/decisions/002-security-architecture.md`

- [ ] **3.1** Update section title (line ~90)
  - Change from: `### Plugin Customization: Freezing at Declared Level (Future Work)`
  - Change to: `### Plugin Customization: Freezing at Declared Level`

- [ ] **3.2** Remove "Implementation Status" paragraph (lines ~102-104)
  - Delete the note about sealed methods
  - Delete the HYPOTHETICAL CODE warning

- [ ] **3.3** Update code example (lines ~107-138)
  - Remove `# HYPOTHETICAL CODE` comments
  - Remove `# HYPOTHETICAL: This method is currently @final` comment
  - Change to actual implementation pattern:
  ```python
  class FrozenSecretDataSource(BasePlugin, DataSource):
      """SECRET-only datasource - refuses to operate at lower classification levels."""

      def __init__(self):
          super().__init__(
              security_level=SecurityLevel.SECRET,
              allow_downgrade=False  # ← Frozen behavior
          )

      def load_data(self, context: PluginContext) -> SecureDataFrame:
          # Will only operate in SECRET pipelines
          ...
  ```

- [ ] **3.4** Replace "Implementation Options" section (lines ~140-154)
  - Delete the 3 proposed approaches
  - Replace with "Implementation" section documenting chosen approach:
  ```markdown
  **Implementation**: Configuration-driven via `allow_downgrade` parameter (see ADR-005).
  ```

- [ ] **3.5** Remove "Current Workaround" paragraph (lines ~152-154)
  - Delete the workaround note (no longer needed)

- [ ] **3.6** Update "Certification Note" (lines ~177-182)
  - Remove "(when frozen plugin support is implemented)" qualifier
  - Change "would require" → "requires"
  - Change "would need to verify" → "must verify"

### File: `docs/architecture/decisions/002-a-trusted-container-model.md`

- [ ] **3.7** Update section title (line ~215)
  - Change from: `## Interaction with Plugin Customization (ADR-002 Future Work)`
  - Change to: `## Interaction with Plugin Customization (ADR-002)`

- [ ] **3.8** Remove future-work qualifier (lines ~217-220)
  - Remove: "**Note**: This is currently future work..."
  - Change "would be orthogonal" → "is orthogonal"

### File: `docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md`

- [ ] **3.9** Update BasePlugin constructor specification
  - Add `allow_downgrade: bool = True` parameter
  - Add frozen plugin example to sealed methods section

### File: `docs/development/plugin-authoring.md`

- [ ] **3.10** Add "Frozen Plugins" section (after security level section)
  - Document use cases (dedicated domains, compliance, high-assurance)
  - Show `allow_downgrade=False` pattern
  - Add certification notes

### Verification (Phase 3)

```bash
# Check for remaining "Future Work" mentions
grep -r "Future Work" docs/architecture/decisions/002*.md
grep -r "HYPOTHETICAL" docs/architecture/decisions/002*.md
grep -r "currently sealed" docs/architecture/decisions/002*.md

# Verify ADR cross-references
grep -r "ADR-005" docs/architecture/decisions/*.md
```

**Exit Criteria**: No future-work qualifiers, all examples show actual implementation, ADR-005 referenced where appropriate.

---

## Phase 4: Final Verification (30 minutes)

- [ ] **4.1** Run full test suite
  ```bash
  make test
  ```

- [ ] **4.2** Run linting and type checking
  ```bash
  make lint
  ```

- [ ] **4.3** Verify backwards compatibility
  - All existing tests pass unchanged
  - No behavioral changes to default behavior
  - Existing plugins work without modification

- [ ] **4.4** Review diff for security implications
  - New validation logic correct (frozen check after insufficient clearance check)
  - Error messages clear and informative
  - No new attack surfaces introduced

- [ ] **4.5** Update CHANGELOG (if maintained)
  ```markdown
  ### Added
  - Frozen plugin capability via `allow_downgrade=False` parameter (ADR-005)
    - Enables strict level enforcement for dedicated classification domains
    - Backwards compatible (defaults to trusted downgrade behavior)
  ```

**Exit Criteria**: All tests pass, lint clean, security review complete, documentation consistent.

---

## Definition of Done

✅ All checklist items completed
✅ 33+ tests passing (12 unit + 18 parameterized + 3 integration)
✅ 100% coverage on new frozen validation logic
✅ MyPy clean (no type errors)
✅ Ruff clean (no lint errors)
✅ All existing tests pass (backwards compatibility verified)
✅ Documentation updated (no "future work" qualifiers)
✅ ADR-005 marked as "Accepted"
✅ Security review completed (no new attack surfaces)

---

## Rollback Plan

If issues discovered during implementation:

1. **Revert code changes**: `git revert <commit-hash>`
2. **Restore documentation**: `git checkout main -- docs/architecture/decisions/002*.md`
3. **Mark ADR-005 as "Rejected"** with lessons learned
4. **Keep test file** for future implementation attempts

Low risk due to:
- Backwards compatibility (default behavior unchanged)
- Minimal code changes (single parameter + one validation check)
- Comprehensive test coverage
- Clear rollback path

---

## Success Metrics

**Code Quality**:
- Test coverage ≥ 100% on frozen validation logic
- Mutation testing survivors ≤ 10%
- Zero regressions in existing tests

**Documentation Quality**:
- No "future work" qualifiers remaining
- All examples use actual implementation
- Clear certification guidance for frozen plugins

**Timeline**:
- Phase 1-4 completed within 8 hours
- All tests green on first run
- Documentation review < 30 minutes

---

🤖 **Implementation Ready**: All phases planned, tests specified, success criteria defined.
