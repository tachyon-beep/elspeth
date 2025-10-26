# Complexity Reduction - Templates

**Version:** 1.1
**Purpose:** Copy-paste ready templates for refactoring artifacts

---

## Table of Contents

1. [ADR Template](#adr-template)
2. [PR Template](#pr-template)
3. [Metrics Collection Template](#metrics-collection-template)
4. [Code Templates](#code-templates)
   - [Characterization Test Template](#characterization-test-template)
   - [Dataclass Template](#dataclass-template)
   - [Helper Method Docstring Template](#helper-method-docstring-template)
   - [Performance Probe Template](#performance-probe-template)
5. [Commit Message Templates](#commit-message-templates)

---

## ADR Template

**File:** `docs/architecture/decisions/XXX-complexity-reduction-<target>.md`

```markdown
# ADR XXX – Complexity Reduction: <target>

## Status

Accepted (YYYY-MM-DD)

## Context

The `<target>` function in `src/<path>/file.py` had cognitive complexity of **X**
(SonarQube Critical threshold), making maintenance difficult and increasing bug risk.
This violated our design philosophy (ADR-001) regarding maintainability and created
significant technical debt.

**Problem Statement:**

- **Complexity:** X (target: ≤ 15)
- **Lines:** Y lines
- **Nested Conditionals:** Z levels deep
- **Modification Time:** ~A hours per change
- **Bug Risk:** High (complex code paths difficult to reason about)

**Impact:**

- Feature development slowed by high cognitive load
- Review time increased (reviewers need 20+ minutes to understand changes)
- Bug introduction risk elevated due to hidden edge cases
- Technical debt accumulating (deferred refactoring for X months)

**Alternatives Considered:**

1. **Leave as-is** (defer technical debt)
   - Pro: Zero upfront time investment
   - Con: Ongoing high maintenance cost, increasing bug risk
   - Rejected: Technical debt compounds over time

2. **Full rewrite** (greenfield implementation)
   - Pro: Opportunity to redesign from scratch
   - Con: High risk of behavioral changes, long timeline
   - Rejected: Too risky, violates incremental improvement principle

3. **Incremental complexity reduction** (chosen)
   - Pro: Preserves behavior, testable at each step, proven methodology
   - Con: Requires 13-hour upfront investment
   - Selected: Best risk/benefit ratio, zero behavioral changes

## Decision

We will apply the **five-phase complexity reduction methodology** to refactor
`<target>` while maintaining zero behavioral changes and 100% test pass rate.

**Implementation Approach:**

1. **Phase 0: Safety Net** (4-6 hours)
   - Build comprehensive characterization tests (6+ tests)
   - Achieve 80%+ coverage on target function
   - Run mutation testing (≤ 10% survivors)
   - Document high-risk areas with behavioral tests

2. **Phase 1: Supporting Classes** (1-2 hours)
   - Create N dataclasses to consolidate M scattered variables
   - Example: `SuiteExecutionContext` consolidates 8 state variables
   - Use `frozen=True` for immutability where possible

3. **Phase 2: Simple Helpers** (2-3 hours)
   - Extract P simple helpers (5-20 lines each)
   - Examples: `_prepare_suite_context()`, `_resolve_experiment_sinks()`
   - Target: ~30-40% complexity reduction

4. **Phase 3: Complex Helpers** (3-4 hours)
   - Extract Q complex helpers (15-40 lines each)
   - Examples: `_run_baseline_comparison()`, `_notify_middleware_suite_loaded()`
   - One extraction at a time, test after each
   - Target: ≥ 85% complexity reduction

5. **Phase 4: Documentation** (1-2 hours)
   - Enhance run() docstring with execution flow
   - Create refactoring summary document
   - Create this ADR
   - Final verification (tests, MyPy, Ruff, complexity)

**Implementation:**

- **PR:** #XX ([link])
- **Branch:** `refactor/<target>-complexity`
- **Time Investment:** Y hours (target: 10-15 hours)
- **Team:** <name(s)>

**Design Patterns Applied:**

1. **Template Method Pattern**
   - run() serves as orchestration template
   - Delegates specific responsibilities to focused helpers
   - Maintains clear, linear execution flow

2. **Parameter Object Pattern**
   - Dataclasses consolidate related state
   - Reduces parameter list complexity
   - Type-safe attribute access

3. **Guard Clause Pattern**
   - Early returns eliminate deep nesting
   - Reduces conditional complexity
   - Makes error paths explicit

## Consequences

### Benefits

1. **Maintainability Dramatically Improved**
   - Complexity: X → Y (**Z% reduction**, exceeded 85% target)
   - Lines: A → B (**C% reduction**)
   - Future modifications: ~50% faster (estimated 2-3 hour savings per change)
   - Review time: Reduced from 20+ minutes to 5-10 minutes

2. **Risk Reduction**
   - Comprehensive test coverage: D% → E% (+Fpp)
   - Mutation testing validates test strength (G% survivors, ≤ 10% target)
   - Zero behavioral changes (all tests passing)
   - Zero regressions (full test suite passing)

3. **Code Quality**
   - run() now readable orchestration template (H lines)
   - I helper methods with single, clear responsibilities
   - All methods have comprehensive docstrings
   - Type-safe with MyPy validation

4. **Knowledge Transfer**
   - Clear execution flow enables faster onboarding
   - Comprehensive documentation reduces tribal knowledge dependency
   - Helper methods serve as reusable building blocks

### Limitations / Trade-offs

1. **Upfront Time Investment**
   - **Cost:** Y hours one-time investment
   - **Break-Even:** ~8-10 future modifications (estimated 6-12 months)
   - **Mitigation:** Investment pays off quickly for frequently-modified code

2. **More Methods**
   - **Impact:** I new helper methods (was: 0, now: I)
   - **Trade-off:** More methods vs. more complexity per method
   - **Justification:** Each helper has single, clear responsibility (complexity ≤ 10)

3. **Learning Curve**
   - **Impact:** Developers unfamiliar with Template Method pattern need brief orientation
   - **Mitigation:** Comprehensive docstrings explain orchestration flow

### Implementation Impact

**Files Changed:**

- `src/<path>/target.py` - Refactored target function
- `tests/test_<target>_characterization.py` - New characterization tests
- `tests/test_<target>_<risk1>.py` - Risk reduction behavioral tests
- `tests/test_<target>_<risk2>.py` - Additional behavioral tests
- `tests/conftest.py` - Optional test infrastructure (if needed)
- `docs/refactoring/<target>_summary.md` - Refactoring summary document

**Migration Considerations:**

- None (internal refactoring only, no API changes)
- Zero behavioral changes, fully backward compatible
- No dependency updates required

**Verification:**

- ✅ All J tests passing (100% pass rate)
- ✅ MyPy clean (zero type errors)
- ✅ Ruff clean (zero linting issues)
- ✅ Complexity: X → Y (Z% reduction)
- ✅ Coverage: D% → E% (maintained/improved)
- ✅ Mutation score: G% survivors (≤ 10% target)
- ✅ Non-functional parity: Performance/memory within tolerance

**Monitoring:**

- 30-day post-merge observation period
- Track bug rate (target: zero bugs in refactored code)
- Track modification time (target: 50% reduction)
- Track developer confidence (qualitative feedback)

**Post-Merge Results (30 days):**

- Incidents: 0
- Bugs introduced: 0
- Modification count: K changes
- Average modification time: L hours (down from M hours, N% faster)

## Related Documents

- **[METHODOLOGY.md](../../refactoring/v1.1/METHODOLOGY.md)** – Five-phase refactoring process
- **[CHECKLIST.md](../../refactoring/v1.1/CHECKLIST.md)** – Phase execution checklist
- **[ADR-001](001-design-philosophy.md)** – Design philosophy (maintainability priority)
- **PR #XX** – Implementation pull request
- **`src/<path>/target.py`** – Refactored code
- **`docs/refactoring/<target>_summary.md`** – Detailed refactoring summary

---

**Last Updated**: YYYY-MM-DD
**Author(s)**: <name(s)>
```

---

## PR Template

**For:** Creating draft PR after Phase 4 complete

**GitHub PR Description:**

```markdown
# Complexity Reduction: <target>

**Type:** Refactoring (Structure Only)
**Scope:** Internal implementation, zero behavioral changes
**Complexity Reduction:** X → Y (**Z% reduction**)

---

## Summary

Reduced cognitive complexity of `<target>` from **X** (SonarQube Critical) to **Y**
through systematic extraction of helper methods following the five-phase complexity
reduction methodology. All tests passing, zero behavioral changes, zero regressions.

**Key Metrics:**

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Cognitive Complexity** | X | Y | **-Z%** ✅ |
| **Lines** | A | B | **-C%** |
| **Helper Methods** | 0 | I | **+I methods** |
| **Test Coverage** | D% | E% | **+Fpp** |
| **Tests Created** | 0 | J | **+J tests** |
| **Mutation Score** | - | G% | **≤ 10% target** ✅ |

**Time Investment:** ~Y hours

---

## Motivation

`<target>` had complexity of X, significantly exceeding the maintainability threshold
(SonarQube Critical at ≥ 25). This created:

- High cognitive load for developers (20+ minute review time)
- Elevated bug risk due to complex nested logic
- Slow feature development (A hours per modification)

**Problem:** Technical debt accumulating, violates ADR-001 maintainability principle

**Solution:** Apply proven five-phase methodology with zero-regression guarantee

---

## Changes

### Phase 0: Safety Net (4-6 hours)

**Characterization Tests:**
- `test_<target>_characterization.py` - 6+ integration tests capturing workflows

**Risk Reduction Tests:**
- `test_<target>_<risk1>.py` - N tests for [risk area 1]
- `test_<target>_<risk2>.py` - M tests for [risk area 2]

**Coverage:** D% → E% (+Fpp)
**Mutation Score:** G% survivors (≤ 10% target)

### Phase 1: Supporting Classes (1-2 hours)

**Created N dataclasses:**
1. `<Dataclass1>` - Consolidates P variables
2. `<Dataclass2>` - Consolidates Q variables

**Benefits:** Reduced parameter passing, type-safe state management

### Phase 2: Simple Helpers (2-3 hours)

**Extracted R simple helpers:**
1. `_<helper1>()` - [purpose] (S lines)
2. `_<helper2>()` - [purpose] (T lines)
3. `_<helper3>()` - [purpose] (U lines)
4. `_<helper4>()` - [purpose] (V lines)

**Impact:** ~30-40% complexity reduction

### Phase 3: Complex Helpers (3-4 hours)

**Extracted W complex helpers:**
1. `_<helper5>()` - [purpose] (X lines, complexity Y)
2. `_<helper6>()` - [purpose] (Z lines, complexity W)
3. `_<helper7>()` - [purpose] (AA lines, complexity BB)

**Impact:** Final complexity reduction to Y (Z% total)

### Phase 4: Documentation (1-2 hours)

- Enhanced `run()` docstring (CC lines with execution flow)
- All helper methods have comprehensive docstrings
- Created `REFACTORING_COMPLETE_<target>.md` summary
- Created ADR-XXX for architectural record

---

## Design Patterns

1. **Template Method** - run() orchestrates, helpers handle details
2. **Parameter Object** - Dataclasses consolidate state
3. **Guard Clause** - Early returns reduce nesting

---

## Testing

**Test Coverage:**
- Characterization tests: 6+
- Risk reduction tests: DD
- Pre-existing tests: EE
- **Total:** FF tests, 100% passing

**Validation:**
- ✅ All tests passing (100% pass rate)
- ✅ MyPy clean
- ✅ Ruff clean
- ✅ Complexity ≤ 15
- ✅ Zero behavioral changes
- ✅ Zero regressions

**Non-Functional Parity:**
- Performance delta: ±GG% (within ±5% tolerance)
- Memory delta: ±HH% (within ±10% tolerance)
- Logging structure: Unchanged
- Security posture: Unchanged

---

## Review Checklist

**For Reviewers:**

### Phase 0 Artifacts
- [ ] Characterization tests exist and cover key workflows
- [ ] Risk reduction tests address identified high-risk areas
- [ ] Coverage ≥ 80% on target function
- [ ] Mutation report attached (≤ 10% survivors)

### Complexity Reduction
- [ ] Complexity metrics match stated values (X → Y, Z% reduction)
- [ ] Line count reduced by stated amount (A → B, C% reduction)
- [ ] Helper method count matches (I new methods)

### Code Quality
- [ ] Each helper has single, clear responsibility
- [ ] All helpers have comprehensive docstrings (Args/Returns/Complexity note)
- [ ] run() reads like orchestration template (H lines, minimal nesting)
- [ ] Type hints on all parameters and returns

### Safety
- [ ] No public API changes
- [ ] No behavioral changes (all original tests passing)
- [ ] No regressions (full test suite passing)
- [ ] Non-functional parity (performance/memory/logging unchanged)

### Phase 3 Commit Hygiene
- [ ] One complex extraction per commit (verifiable via git log)
- [ ] Each commit passes tests independently

### Documentation
- [ ] run() docstring enhanced with execution flow
- [ ] Refactoring summary document created
- [ ] ADR created and indexed

### Final Verification
- [ ] pytest tests/test_<target>*.py -v → 100% pass
- [ ] pytest tests/ -v → No new failures
- [ ] mypy src/<path>/target.py → Clean
- [ ] ruff check src/<path>/target.py → Clean

---

## Related Documents

- **ADR-XXX:** `docs/architecture/decisions/XXX-complexity-reduction-<target>.md`
- **Summary:** `docs/refactoring/<target>_summary.md`
- **Methodology:** `docs/refactoring/v1.1/METHODOLOGY.md`

---

## Post-Merge Monitoring

**30-day observation period:**
- Bug rate (target: 0)
- Modification time (target: 50% reduction)
- Developer confidence (qualitative feedback)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Metrics Collection Template

**For:** Tracking refactoring metrics consistently

**File:** `refactoring_metrics_<target>.md` or add to refactoring summary

```markdown
## Refactoring Metrics: <target>

**Project:** Elspeth
**File:** `src/<path>/target.py`
**Function:** `<target>()`
**PR Number:** #XX
**Date:** YYYY-MM-DD
**Branch:** `refactor/<target>-complexity`

---

### Before Metrics (Baseline)

**Code Metrics:**
- Cognitive Complexity: X
- Lines: Y
- Cyclomatic Complexity: Z (optional)
- Nesting Depth: W levels
- Parameters: P
- Local Variables: Q

**Test Metrics:**
- Test Coverage: R%
- Test Count: S
- Mutation Score: Not captured

**Non-Functional Baseline:**
- p50 Runtime: TT ms
- p95 Runtime: UU ms
- Peak Memory: VV MB
- Log Event Count: WW events

---

### After Metrics (Post-Refactoring)

**Code Metrics:**
- Cognitive Complexity: X2 (**-Z%** from X)
- Lines: Y2 (**-C%** from Y)
- Cyclomatic Complexity: Z2 (**-D%** from Z)
- Nesting Depth: W2 levels (**-E levels**)
- Helper Methods: H new methods
- Parameters: P2 (dataclasses reduced parameter count)

**Test Metrics:**
- Test Coverage: R2% (**+Fpp** from R%)
- Test Count: S2 (**+G tests**)
- Mutation Score: M% survivors (≤ 10% target)

**Non-Functional Results:**
- p50 Runtime: TT2 ms (**±H%** delta, within ±5% tolerance)
- p95 Runtime: UU2 ms (**±I%** delta)
- Peak Memory: VV2 MB (**±J%** delta, within ±10% tolerance)
- Log Event Count: WW2 events (**unchanged**)

---

### Time Investment

**Phase Breakdown:**
- Phase 0: Safety Net - K hours
- Phase 1: Supporting Classes - L hours
- Phase 2: Simple Helpers - M hours
- Phase 3: Complex Helpers - N hours
- Phase 4: Documentation - O hours
- **Total:** P hours (target: 10-15 hours)

**Time Distribution:**
- Phase 0: Q% (target: 35%)
- Phase 1: R% (target: 10%)
- Phase 2: S% (target: 20%)
- Phase 3: T% (target: 30%)
- Phase 4: U% (target: 10%)

---

### Tests Created

**Characterization Tests:** V tests
- Test 1: [description]
- Test 2: [description]
- ...

**Risk Reduction Tests:** W tests
- Risk Area 1: X tests
- Risk Area 2: Y tests
- Risk Area 3: Z tests

**Pre-existing Tests:** AA tests (all still passing)

**Total Tests:** BB tests (100% passing)

---

### Helper Methods Extracted

**Simple Helpers (Phase 2):** CC methods
1. `_<helper1>()` - [purpose] (DD lines, complexity EE)
2. `_<helper2>()` - [purpose] (FF lines, complexity GG)
3. ...

**Complex Helpers (Phase 3):** HH methods
1. `_<helper5>()` - [purpose] (II lines, complexity JJ)
2. `_<helper6>()` - [purpose] (KK lines, complexity LL)
3. ...

**Total Helpers:** MM methods

---

### Design Patterns Applied

1. **Template Method Pattern**
   - run() orchestrates workflow
   - Delegates to MM focused helpers

2. **Parameter Object Pattern**
   - NN dataclasses created
   - Consolidated OO scattered variables

3. **Guard Clause Pattern**
   - PP guard clauses added
   - Eliminated QQ levels of nesting

---

### Verification Results

**Automated Checks:**
- ✅ pytest tests/test_<target>*.py -v → BB/BB passing (100%)
- ✅ pytest tests/ -v → RR/RR passing (no regressions)
- ✅ mypy src/<path>/target.py → Success: no issues found
- ✅ ruff check src/<path>/target.py → All checks passed!
- ✅ Complexity: X → X2 (≤ 15 target)

**Manual Verification:**
- ✅ Behavioral changes: 0
- ✅ API changes: 0
- ✅ Non-functional parity: Verified

---

### Review Process

**Reviewers:**
- Security Review: [Name] - ✓ Approved / ✗ Changes Requested
- Peer Review: [Name] - ✓ Approved / ✗ Changes Requested
- Copilot Review: Addressed (0 blocking findings)

**Review Rounds:** SS iterations
**Review Time:** TT hours total

---

### Post-Merge Monitoring (30 days)

**Incident Tracking:**
- Bugs introduced: 0
- Production incidents: 0
- Rollbacks required: 0

**Performance Tracking:**
- Modification count: UU changes
- Average modification time: VV hours (down from WW hours, **XX% faster**)
- Review time: YY minutes (down from ZZ minutes)

**Developer Feedback:**
- "Much easier to understand and modify"
- "Clear execution flow makes debugging trivial"
- "Helper methods serve as reusable building blocks"

---

### Success Criteria

| Criteria | Target | Actual | Status |
|----------|--------|--------|--------|
| Complexity Reduction | ≥ 85% | Z% | ✅ / ❌ |
| Test Pass Rate | 100% | 100% | ✅ |
| Behavioral Changes | 0 | 0 | ✅ |
| Regressions | 0 | 0 | ✅ |
| Coverage | Maintained | +Fpp | ✅ |
| Time Investment | 10-15h | Ph | ✅ / ❌ |
| Mutation Score | ≤ 10% | M% | ✅ / ❌ |

**Overall:** ✅ SUCCESS / ❌ NEEDS IMPROVEMENT

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Code Templates

### Characterization Test Template

**Purpose:** Capture complete workflows before refactoring

```python
def test_characterization_<workflow_name>_complete_workflow(self):
    """CHARACTERIZATION: <Workflow description>.

    This test captures the EXISTING behavior of <target>. Any change to this
    test during refactoring indicates a behavioral regression and must be
    investigated immediately.

    Verifies:
    - Input processing from <source>
    - Output structure with expected keys
    - Side effects (sink writes, logging, state changes)
    - Edge case handling for <specific case>

    Coverage:
    - Happy path with N rows
    - <Specific integration point>
    - <Specific edge case>
    """
    # Setup: Create realistic input matching production scenarios
    input_data = create_realistic_input_data(
        row_count=10,
        include_edge_cases=True,
    )
    expected_side_effects = [
        # Document expected sink.write() calls, logging, etc.
    ]

    # Execute: Run target function
    result = self.target_function(
        input_data,
        config=test_config,
        # ... other params
    )

    # Verify: Complete behavior validation

    # 1. Output structure
    assert isinstance(result, dict)
    assert "status" in result
    assert "results" in result
    assert "metadata" in result

    # 2. Output content
    assert result["status"] == "success"
    assert len(result["results"]) == 10  # Expected result count
    assert all("row_id" in r for r in result["results"])

    # 3. Side effects (critical for characterization)
    assert len(mock_sink.calls) == 10  # Verify sink writes
    assert logger.info.call_count == 12  # Verify logging
    assert state_tracker.updated == True  # Verify state changes

    # 4. Data integrity
    for idx, row_result in enumerate(result["results"]):
        assert row_result["input_id"] == input_data[idx]["id"]
        assert "output" in row_result
        assert "timestamp" in row_result

    # 5. Edge case handling
    assert result["metadata"]["empty_inputs_handled"] == 2
    assert result["metadata"]["errors_caught"] == 0
```

### Dataclass Template

**Purpose:** Consolidate scattered state variables

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)  # Prefer immutability where possible
class <Name>Context:
    """<One-line description of what this context manages>.

    This dataclass consolidates N scattered variables into a cohesive state
    object, reducing parameter passing complexity and making state management
    explicit. Created during Phase 1 of complexity reduction refactoring.

    Design Pattern: Parameter Object pattern
    Benefit: Reduces function parameter count from X to Y

    Attributes:
        field1: <Type and description>
            Example: "Configuration defaults for suite execution"
        field2: <Type and description>
            Example: "List of experiments in baseline-first order"
        field3: <Type and description, include default if applicable>
            Example: "Aggregated results, initially empty"

    Immutability:
        This dataclass is frozen to prevent accidental mutation during
        execution. Use .replace() pattern if state updates needed:

        ```python
        new_ctx = ctx.replace(results={...})
        ```

    Example:
        >>> ctx = SuiteExecutionContext.create(suite, defaults)
        >>> ctx.experiments[0].is_baseline
        True
        >>> ctx.results  # Empty initially
        {}

    See Also:
        - <TargetFunction>.run() - Primary consumer of this context
        - <HelperMethod>() - Factory method using this context
    """
    # Required fields (no defaults)
    field1: Type
    field2: Type

    # Optional fields (with defaults)
    field3: Type | None = None
    field4: dict[str, Any] = field(default_factory=dict)
    field5: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate invariants after initialization.

        Use __post_init__ for assertions that must hold after construction.
        Raises ValueError if invariants violated.
        """
        if self.field1 is None:
            raise ValueError("field1 cannot be None")

        if not self.field2:
            raise ValueError("field2 must be non-empty")

    @classmethod
    def create(
        cls,
        source_data: SourceType,
        config: dict[str, Any],
        optional_param: Type | None = None,
    ) -> "<Name>Context":
        """Factory method to create context from source data.

        Use factory method when initialization logic is non-trivial or
        requires processing of source data before field assignment.

        Args:
            source_data: Source data to extract fields from
            config: Configuration dict with required keys
            optional_param: Optional parameter for customization

        Returns:
            Initialized context ready for use in target function

        Raises:
            ValueError: If required config keys missing
            TypeError: If source_data type invalid

        Example:
            >>> ctx = SuiteExecutionContext.create(suite, defaults)
            >>> len(ctx.experiments)
            5
        """
        # Extract and transform data
        field1_value = process_field1(source_data)
        field2_value = extract_field2(source_data, config)

        # Handle optional fields
        field3_value = optional_param or default_value

        # Construct with validated data
        return cls(
            field1=field1_value,
            field2=field2_value,
            field3=field3_value,
            field4={},  # Initialize mutable defaults explicitly
        )
```

### Helper Method Docstring Template

**Purpose:** Comprehensive documentation for extracted helpers

```python
def _<verb>_<noun>(
    self,
    param1: Type1,
    param2: Type2,
    param3: Type3 | None = None,
) -> ReturnType:
    """<One-line summary in imperative mood, explaining what this does>.

    <2-3 sentences explaining:
    - What this method does (purpose)
    - Why it was extracted (complexity reduction rationale)
    - How it fits into overall execution flow
    - Any important behavioral details or invariants>

    This method was extracted during Phase 2/3 of complexity reduction to
    isolate <specific responsibility> from the main orchestration flow. It
    handles <specific concern> without exposing implementation details to
    the caller.

    <Optional: Add subsections for complex behavior>

    Priority Order: (if applicable)
        1. Check param1 first
        2. Fall back to param2
        3. Use default if both None

    Side Effects: (if any)
        - Calls sink.write() for each result
        - Updates self.state_tracker
        - Logs to logger at INFO level

    Args:
        param1: <Type, description, constraints, examples>
            Example: "Configuration dict with required keys 'x', 'y'"
        param2: <Type, description, constraints, examples>
            Example: "List of experiments in execution order"
        param3: <Type, description, what None means>
            Example: "Optional factory, None means use self.default_factory"

    Returns:
        <Description of return value, structure, guarantees>
        Example: "List of processed results, one per input row. Each result
        contains 'row_id', 'output', and 'metadata' keys."

    Raises:
        ValueError: If param1 missing required keys
        TypeError: If param2 not iterable
        ConfigurationError: If no factory available (param3=None, no default)

    Complexity Reduction:
        Before: XX lines inline in run(), complexity YY
        After: Single method call, complexity reduced by ZZ points
        Pattern: <Template Method / Guard Clause / etc.>

    Example:
        >>> sinks = self._resolve_experiment_sinks(exp, pack, defaults, None)
        >>> len(sinks)
        2
        >>> sinks[0].__class__.__name__
        'CSVSink'

    See Also:
        - run() - Main orchestration method that calls this
        - _other_helper() - Related helper method
        - docs/architecture/<topic>.md - Detailed behavior documentation
    """
    # Implementation
    pass
```

### Performance Probe Template

**Purpose:** Optional instrumentation for performance parity verification

```python
from contextlib import contextmanager
import time
from typing import Optional, Any, Iterator

@contextmanager
def perf_probe(
    label: str,
    sink: Optional[Any] = None,
    threshold_ms: Optional[float] = None,
) -> Iterator[None]:
    """Context manager for performance monitoring during refactoring.

    Use this to instrument expensive code blocks and verify performance
    parity before/after refactoring. The probe is designed to be no-op
    when sink=None, making it safe to leave in production temporarily.

    Args:
        label: Identifier for this measurement point
            Example: "baseline_comparison", "sink_resolution"
        sink: Optional sink for metrics (logger, statsd client, etc.)
            None means no recording (no-op mode)
        threshold_ms: Optional threshold for warnings
            If duration > threshold_ms, log warning

    Yields:
        None (context manager protocol)

    Example:
        >>> with perf_probe("run_experiment", logger, threshold_ms=1000):
        ...     result = expensive_operation()
        ...
        # Logs: "perf_probe[run_experiment]: 250.5ms"

    Usage During Refactoring:
        Phase 0: Capture baseline measurements
        Phase 4: Re-measure and compare against baseline
        Post-Merge: Remove probe after 30-day observation
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        duration_ms = (t1 - t0) * 1000

        if sink is not None:
            # Record measurement (adapt to your sink interface)
            if hasattr(sink, "record"):
                sink.record(label, duration_ms)
            elif hasattr(sink, "info"):
                sink.info(f"perf_probe[{label}]: {duration_ms:.1f}ms")

        # Warn if threshold exceeded
        if threshold_ms and duration_ms > threshold_ms:
            if sink and hasattr(sink, "warning"):
                sink.warning(
                    f"perf_probe[{label}]: {duration_ms:.1f}ms "
                    f"exceeded threshold {threshold_ms}ms"
                )

# Usage example in refactored code:
def run(self, df, defaults=None):
    """Execute suite with optional performance monitoring."""
    with perf_probe("suite_initialization", logger):
        ctx = self._prepare_suite_context(defaults)

    for experiment in ctx.experiments:
        with perf_probe(f"experiment_{experiment.name}", logger, threshold_ms=5000):
            payload = self._run_single_experiment(experiment, ctx)

        with perf_probe("baseline_comparison", logger):
            self._run_baseline_comparison(experiment, ctx, payload)

    return ctx.results
```

---

## Commit Message Templates

### Phase 0 Commit

```
Phase 0: Safety net for <target> refactoring

Created comprehensive test coverage before refactoring:
- X characterization tests (integration workflows)
- Y behavioral tests (risk mitigation)
- Z% coverage (≥ 80% target)
- Mutation score: W% survivors (≤ 10% target)

Risk reduction activities completed:
- Activity 1: <Risk area> (N tests, M lines docs)
- Activity 2: <Risk area> (P tests, Q lines docs)
- Activity 3: <Risk area> (R tests, S lines docs)

Safety net construction complete. Zero behavioral changes.
All tests passing. Ready for Phase 1.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Phase 1 Commit

```
Phase 1: Supporting dataclasses for <target> refactoring

Created N dataclasses to consolidate scattered state:
- <Dataclass1>: M variables → single object
- <Dataclass2>: P variables → single object

Benefits:
- Reduced parameter passing complexity
- Type-safe attribute access
- Explicit state management
- Foundation for helper method extractions

All Q tests still passing. Zero behavioral changes.
MyPy clean. Ready for Phase 2.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Phase 2 Commit

```
Phase 2: Simple helper extractions from <target>

Extracted N low-risk helper methods:
- _<helper1>(): <Purpose> (X → Y lines)
- _<helper2>(): <Purpose> (A → B lines)
- _<helper3>(): <Purpose> (C → D lines)
- _<helper4>(): <Purpose> (E → F lines)

Impact:
- Lines: G → H (I% reduction)
- Complexity: J → K (L% reduction)
- All M tests passing
- Zero behavioral changes

Next: Phase 3 (Complex method extractions)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Phase 3 Commit

```
Phase 3: Complex method extractions from <target>

Extracted N high-complexity orchestration methods:
- _<helper5>(): <Purpose> (complexity -X)
- _<helper6>(): <Purpose> (complexity -Y)
- _<helper7>(): <Purpose> (complexity -Z)
- _<helper8>(): <Purpose> (complexity -W)
- _<helper9>(): <Purpose> (complexity -V)

Impact:
- Lines: A → B (C% total reduction from original D)
- Complexity: E → F (G% reduction from original H!)
- All I tests passing
- run() method now clear orchestration template (J lines)

Target exceeded: G% reduction vs 85% goal

Next: Phase 4 (Documentation & cleanup)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Phase 4 Commit

```
Phase 4: Documentation and cleanup for <target>

Enhanced run() method with comprehensive N-line docstring including:
- Template Method pattern explanation
- M-step execution flow
- P middleware lifecycle hooks
- Complete Args/Returns/Raises documentation
- Complexity metrics (before/after)
- Usage examples
- Cross-references to helpers and docs

Created REFACTORING_COMPLETE_<target>.md:
- Comprehensive refactoring summary
- Phase-by-phase breakdown with metrics
- Helper methods catalog (Q methods)
- Design patterns applied
- Testing pyramid (R tests)
- Verification results
- Review checklist

Created ADR-XXX:
- Architectural record of complexity reduction decision
- Context, alternatives, consequences documented
- Linked to methodology and implementation

Final verification:
✅ All R tests passing (100%)
✅ MyPy clean
✅ Ruff clean
✅ Complexity: E → F (G% reduction, exceeded 85% target)
✅ Coverage: S% maintained
✅ Non-functional parity verified

Refactoring complete! Ready for code review.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Version:** 1.1
**Last Updated:** 2025-10-25
**Team:** Elspeth Engineering
