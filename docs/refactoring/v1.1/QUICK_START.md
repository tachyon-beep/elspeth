# Complexity Reduction - Quick Start Guide

**Version:** 1.1
**For:** Experienced developers who've refactored before
**Full Guide:** [METHODOLOGY.md](METHODOLOGY.md)

---

## Decision Tree: Should I Refactor?

```
Start
  │
  ├─> Complexity < 25? ──YES──> Stop (not worth the effort)
  │         │
  │         NO
  │         │
  ├─> Test coverage < 70? ──YES──> Build tests first (separate PR)
  │         │
  │         NO
  │         │
  ├─> Active feature work? ──YES──> Wait until stable
  │         │
  │         NO
  │         │
  ├─> Code changing >2 PRs/week? ──YES──> High merge conflict risk, defer
  │         │
  │         NO
  │         │
  ├─> Scheduled for deletion <6mo? ──YES──> Not worth investment
  │         │
  │         NO
  │         │
  ├─> Calculate ROI:
  │   Break-Even = 13 hours / (0.5 × current_modification_time)
  │   Modification frequency > Break-Even/year? ──YES──> Proceed!
  │                                              │
  │                                              NO
  │                                              │
  └─────────────────────────────────────────────> Defer refactoring
```

---

## TL;DR: Five-Phase Process

### Phase 0: Safety Net (4-6 hours, 35% of time) 🛡️

**Goal:** Build comprehensive test coverage BEFORE touching code

**Actions:**
```bash
# 1. Read code, document behavior
# 2. Risk assessment (two-stage: upfront + detailed)
# 3. Write 6+ characterization tests
# 4. Achieve 80%+ coverage
# 5. Run mutation testing
pytest tests/test_<target>*.py -v --cov
mutmut run --paths-to-mutate src/<path>/target.py
```

**Exit Criteria:**
- ✅ All tests passing (100%)
- ✅ Coverage ≥ 80%
- ✅ Mutation score ≤ 10% survivors
- ✅ MyPy clean, Ruff clean

---

### Phase 1: Supporting Classes (1-2 hours, 10% of time) 🏗️

**Goal:** Create dataclasses to consolidate scattered state

**Actions:**
```python
from dataclasses import dataclass, field

@dataclass(frozen=True)  # Prefer immutability
class SuiteExecutionContext:
    """Consolidates 8 scattered variables."""
    defaults: dict[str, Any]
    experiments: list[ExperimentConfig]
    results: dict[str, Any] = field(default_factory=dict)
    # ... more fields
```

**Exit Criteria:**
- ✅ 1-3 dataclasses created
- ✅ Type hints on all fields
- ✅ All tests still passing

---

### Phase 2: Simple Helpers (2-3 hours, 20% of time) 🔧

**Goal:** Extract low-risk, clearly-defined helpers (5-20 lines each)

**Actions:**
- Extract 4-6 simple helpers (one at a time)
- Run tests after EACH extraction
- Commit after 2-3 extractions

**Examples:**
- `_prepare_suite_context()` - Initialization
- `_resolve_experiment_sinks()` - Priority chain lookup
- `_finalize_suite()` - Cleanup

**Exit Criteria:**
- ✅ Complexity reduced by ~30-40%
- ✅ Lines reduced by ~30-40%
- ✅ All tests passing after each extraction

---

### Phase 3: Complex Helpers (3-4 hours, 30% of time) ⚙️

**Goal:** Extract high-complexity orchestration methods (15-40 lines each)

**Actions:**
- Extract 5-7 complex helpers (ONE AT A TIME)
- Run tests IMMEDIATELY after each
- Commit after each extraction

**Examples:**
- `_notify_middleware_suite_loaded()` - Hook deduplication
- `_run_baseline_comparison()` - Full comparison orchestration
- `_merge_baseline_plugin_defs()` - 3-level config merge

**Critical Protocol:**
```bash
# For EACH complex extraction:
1. Extract ONE method with full docstring
2. Update run() to call new method
3. pytest tests/test_<target>*.py -v  # MUST PASS
4. mypy src/<path>/target.py          # MUST BE CLEAN
5. git commit (or revert if tests fail)
6. Repeat for next method
```

**Exit Criteria:**
- ✅ Complexity reduced by ≥ 85%
- ✅ Lines reduced by ~60%
- ✅ run() is readable orchestration template (30-60 lines)
- ✅ All tests passing

---

### Phase 4: Documentation (1-2 hours, 10% of time) 📝

**Goal:** Ensure future maintainability

**Actions:**
1. Enhance run() docstring (50+ lines with execution flow)
2. Review all helper docstrings
3. Create refactoring summary document
4. Create ADR in `docs/architecture/decisions/`

**Final Verification:**
```bash
pytest tests/test_<target>*.py -v    # 100% pass
pytest tests/ -v                     # No new failures
mypy src/<path>/target.py            # Clean
ruff check src/<path>/target.py      # Clean
radon cc src/<path>/target.py -s     # Complexity ≤ 15
```

**Exit Criteria:**
- ✅ Comprehensive documentation
- ✅ All final checks passing
- ✅ ADR created and indexed
- ✅ Ready for code review

---

## Quick Commands Reference

### Pre-Flight

```bash
# Check current complexity
radon cc src/<path>/target.py -s

# Check test coverage
pytest --cov=src/<path>/target.py tests/test_<target>*.py

# Create branch
git checkout -b refactor/<target>-complexity
```

### During Refactoring

```bash
# Run tests (after every extraction)
pytest tests/test_<target>*.py -v

# Run MyPy
mypy src/<path>/target.py

# Run Ruff
ruff check src/<path>/target.py

# Commit (after each phase or complex extraction)
git add src tests docs
git commit -m "Phase X: ..."
```

### Phase 0: Mutation Testing

```bash
# Install mutmut (primary, simple)
pip install mutmut

# Run mutation testing
mutmut run --paths-to-mutate src/<path>/target.py

# View results
mutmut results

# Show surviving mutants
mutmut show

# Target: ≤ 10% survivors
```

### Phase 4: Final Verification

```bash
# Full test suite
pytest tests/ -v

# Coverage check
pytest --cov=src/<path>/target.py --cov-report=term-missing tests/test_<target>*.py

# Complexity verification
radon cc src/<path>/target.py -s

# Create ADR
cp docs/architecture/decisions/000-template.md \
   docs/architecture/decisions/005-complexity-reduction-<target>.md

# Edit ADR and update index
vim docs/architecture/decisions/005-complexity-reduction-<target>.md
vim docs/architecture/decisions/README.md
```

---

## Common Quick Fixes

### Tests failing after extraction?

```bash
# Revert immediately
git reset --hard HEAD~1

# Investigate, try smaller extraction
```

### Complexity not reducing enough?

- Target 10-15 helpers, not 5-7
- Break large helpers into sub-helpers
- Add guard clauses at start of each helper

### Too many parameters (>5)?

- Use dataclass to group related parameters
- Or method might be doing too much - split further

---

## Success Metrics Checklist

**Target Goals:**
- [ ] Complexity reduced by ≥ 85%
- [ ] All tests passing (100%)
- [ ] Zero behavioral changes
- [ ] Zero regressions
- [ ] Coverage maintained or improved
- [ ] Time investment: 10-15 hours

**Phase Checkpoints:**
- [ ] After Phase 2: ~30-40% complexity reduction
- [ ] After Phase 3: ≥ 85% complexity reduction
- [ ] After Phase 4: All documentation complete

---

## When to Stop and Ask for Help

**Red Flags:**
- [ ] Tests failing repeatedly after extractions
- [ ] Complexity not reducing despite extracting 10+ methods
- [ ] Stuck on same extraction for > 2 hours
- [ ] Breaking existing tests to make them pass
- [ ] Time investment > 15 hours

**Action:** Consult full [METHODOLOGY.md](METHODOLOGY.md), reach out to team, or defer refactoring.

---

## Essential Reading

**Before starting:**
- [METHODOLOGY.md - Prerequisites](METHODOLOGY.md#prerequisites)
- [METHODOLOGY.md - When NOT to Use](METHODOLOGY.md#when-to-use-this-methodology)

**During refactoring:**
- [CHECKLIST.md](CHECKLIST.md) - Phase-by-phase execution
- [TEMPLATES.md](TEMPLATES.md) - Code and document templates

**After refactoring:**
- [METHODOLOGY.md - Phase 4](METHODOLOGY.md#phase-4-documentation--cleanup)
- [TEMPLATES.md - ADR Template](TEMPLATES.md#adr-template)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Version:** 1.1
**Last Updated:** 2025-10-25
**Success Rate:** 2/2 (100%) - 86.7% avg complexity reduction
**Team:** Elspeth Engineering
