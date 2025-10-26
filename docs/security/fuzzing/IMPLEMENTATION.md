# Phase 1 Fuzzing: Implementation Guide

**Purpose**: Tactical step-by-step guide to implement property-based fuzzing with Hypothesis

**Audience**: Developer implementing Phase 1 for the first time

**Time Required**: 30-45 hours over 3-4 weeks (realistic estimate)

**Prerequisites**: Python 3.12, pytest experience, basic security awareness

---

## Quick Links

- **Strategy & Why**: [fuzzing.md](./fuzzing.md) - Read sections 1.3 (Oracles) and 2.2 (Bug Injection) first
- **Week-by-week plan**: [fuzzing_plan.md](./fuzzing_plan.md) - High-level roadmap
- **Risk assessment**: [fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md) - For IRAP assessors

---

## Week 0: Setup (30-60 minutes)

**Goal**: Get infrastructure ready before writing tests

### 1. Install Dependencies (5 min)

```bash
# Hypothesis already in requirements-dev.lock
pip install hypothesis pytest-hypothesis

# Verify installation
python -c "import hypothesis; print(f'Hypothesis {hypothesis.__version__} installed')"
```

### 2. Create Directory Structure (5 min)

```bash
cd /home/john/elspeth

# Property tests (main fuzzing tests)
mkdir -p tests/fuzz_props
touch tests/fuzz_props/__init__.py
touch tests/fuzz_props/conftest.py
touch tests/fuzz_props/seeds.py

# Smoke tests (bug injection validation)
mkdir -p tests/fuzz_smoke
touch tests/fuzz_smoke/__init__.py

# Verify structure
tree tests/fuzz_props tests/fuzz_smoke
```

### 3. Configure pyproject.toml (10 min)

Add to `/home/john/elspeth/pyproject.toml`:

```toml
# Pytest markers for fuzzing
[tool.pytest.ini_options]
markers = [
    "integration: marks tests that require external services such as pgvector",
    "slow: marks tests that are slow to run and may be excluded from CI",
    "fuzz: Property-based fuzzing tests (pytest -m fuzz)",  # NEW
]

# Hypothesis settings (add new section)
[tool.hypothesis]
max_examples = 100
deadline = 500  # milliseconds per example

[tool.hypothesis.profiles.ci]
max_examples = 200
deadline = 500
derandomize = true

[tool.hypothesis.profiles.explore]
max_examples = 5000
deadline = 5000
verbosity = "verbose"
```

### 4. Test Configuration (10 min)

```bash
# Test default profile
HYPOTHESIS_PROFILE=default pytest tests/ -m fuzz --collect-only
# Should show: "collected 0 items" (correct - no tests yet)

# Test CI profile
HYPOTHESIS_PROFILE=ci pytest tests/ -m fuzz --collect-only

# If errors, check pyproject.toml syntax
```

---

## Week 1: First Property Test (4-6 hours)

**Goal**: Write ONE working property test with bug injection validation

**Target Module**: `path_guard.py` (highest risk - filesystem access to classified data)

### 1. Review Oracle Specifications (30 min)

Read `fuzzing.md` Section 1.3 "Input Domain Specification" oracle table:

**Path Guard Invariants** (MUST always hold):

- Result always under `base_dir`
- No symlink escape
- Normalized (no `..` in result)
- Absolute paths rejected

**Allowed Exceptions**: `ValueError`, `SecurityError`

### 2. Write First Property Test (2 hours)

Create `tests/fuzz_props/test_path_guard_properties.py`:

```python
"""
Property-based fuzzing tests for path_guard.py

Oracle: Path resolution must never escape base directory.
Target: Discover path traversal vulnerabilities, symlink attacks, Unicode bypasses.
"""
import pytest
from hypothesis import given, strategies as st, settings
from pathlib import Path

from elspeth.core.utils.path_guard import resolve_under_base
from elspeth.core.exceptions import SecurityError


@pytest.mark.fuzz
@given(
    candidate=st.text(
        alphabet=st.characters(blacklist_categories=['Cs']),  # Valid Unicode, no surrogates
        min_size=1,
        max_size=200
    )
)
@settings(max_examples=100, deadline=500)
def test_resolve_under_base_never_escapes(tmp_path, candidate):
    """
    Oracle: Resolved path must always be under base directory.

    Invariant: Result always under base_dir (from oracle table)
    Reference: fuzzing.md Section 1.3
    """
    try:
        result = resolve_under_base(tmp_path, candidate)

        # Oracle assertion - result must be under base_dir
        assert result.is_relative_to(tmp_path), \
            f"ORACLE VIOLATION: Path escaped base directory\n" \
            f"  Base: {tmp_path}\n" \
            f"  Candidate: {repr(candidate)}\n" \
            f"  Result: {result}\n" \
            f"  Invariant: Result always under base_dir (oracle table)"

        # Additional invariant: No '..' in resolved path
        assert '..' not in result.parts, \
            f"ORACLE VIOLATION: Path not normalized (contains '..')\n" \
            f"  Result: {result}"

    except (ValueError, SecurityError) as e:
        # Expected exceptions for invalid inputs - this is correct behavior
        pass
    except Exception as e:
        # Unexpected exception - potential bug
        pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


@pytest.mark.fuzz
@given(
    candidate=st.text(min_size=1, max_size=100)
)
@settings(max_examples=100, deadline=500)
def test_absolute_paths_rejected(tmp_path, candidate):
    """
    Oracle: Absolute paths must be rejected.

    Invariant: Absolute paths rejected (from oracle table)
    """
    if candidate.startswith('/') or candidate.startswith('\\'):
        with pytest.raises((ValueError, SecurityError)):
            resolve_under_base(tmp_path, candidate)
```

### 3. Run First Test (15 min)

```bash
# Run with verbose output
pytest tests/fuzz_props/test_path_guard_properties.py::test_resolve_under_base_never_escapes -v

# Expected: PASSED (or FAILED if bug found!)
# If FAILED: Congratulations, you found your first bug! Document it.

# Run all path guard properties
pytest tests/fuzz_props/test_path_guard_properties.py -v -m fuzz

# Check coverage
pytest tests/fuzz_props/test_path_guard_properties.py --cov=elspeth.core.utils.path_guard --cov-report=term-missing
```

### 4. Bug Injection Validation (1 hour) ⭐ **CRITICAL**

Create `tests/fuzz_smoke/test_bug_injection_path_guard.py`:

```python
"""
Smoke test: Verify property tests catch intentionally injected bugs.

MUST FAIL when BUG_INJECTION_ENABLED=1

Purpose: Prove that our property tests actually detect vulnerabilities
"""
import os
import pytest
from hypothesis import given, strategies as st, settings
from pathlib import Path


BUG_INJECTION = os.getenv("BUG_INJECTION_ENABLED") == "1"


def vulnerable_resolve_under_base(base: Path, candidate: str) -> Path:
    """
    Intentionally vulnerable implementation for smoke testing.

    BUG: When BUG_INJECTION_ENABLED=1, skips normalization - allows path traversal.
    """
    if BUG_INJECTION:
        # VULNERABILITY: Skip path normalization, directly join paths
        # This allows '../../../etc/passwd' to escape base directory
        return base / candidate
    else:
        # Use correct implementation
        from elspeth.core.utils.path_guard import resolve_under_base
        return resolve_under_base(base, candidate)


@pytest.mark.fuzz
@given(candidate=st.text(min_size=1, max_size=100))
@settings(max_examples=100, deadline=500)
def test_path_traversal_injection_caught(tmp_path, candidate):
    """
    Property: Path never escapes base (should catch injected bug).

    This test MUST FAIL when BUG_INJECTION_ENABLED=1
    """
    try:
        result = vulnerable_resolve_under_base(tmp_path, candidate)

        # Oracle: Result must be under base_dir
        assert result.is_relative_to(tmp_path), \
            f"BUG DETECTED (expected when BUG_INJECTION_ENABLED=1):\n" \
            f"  Path escaped base: {result}\n" \
            f"  Candidate: {repr(candidate)}"

    except (ValueError, SecurityError):
        # Allowed exceptions for invalid inputs
        pass
```

**Test the smoke test**:

```bash
# Test 1: Normal mode (should PASS)
pytest tests/fuzz_smoke/test_bug_injection_path_guard.py -v
# Expected: PASSED

# Test 2: Bug injection mode (MUST FAIL)
BUG_INJECTION_ENABLED=1 pytest tests/fuzz_smoke/test_bug_injection_path_guard.py -v
# Expected: FAILED (this proves property test catches bugs!)

# If Test 2 PASSED, your oracle is broken - fix it!
```

### 5. Document First Bug (if found) (30 min)

If property test found a bug:

1. **Reproduce with seed**:

   ```bash
   HYPOTHESIS_SEED=<seed-from-output> pytest tests/fuzz_props/test_path_guard_properties.py::test_resolve_under_base_never_escapes -v
   ```

2. **Create GitHub issue** (use `[FUZZ]` prefix):

   ```markdown
   # [FUZZ] Path traversal vulnerability in resolve_under_base

   **Severity**: S0 (Critical) - Path escape to classified files

   **Hypothesis Seed**: 123456789

   **Oracle Violation**: Result escaped base_dir

   **Minimized Example**:
   ```python
   resolve_under_base(Path("/safe"), "../../etc/passwd")
   # Returns: /etc/passwd (outside /safe)
   ```

   **Impact**: Can access classified files outside authorized directory

   **Fix Required**: Within 24 hours (S0 SLA)

   ```

3. **Add regression test** in `tests/fuzz_props/seeds.py`:

   ```python
   KNOWN_PATH_TRAVERSAL = [
       ("../../etc/passwd", "Issue #123 - Path traversal found by Hypothesis"),
   ]

   @pytest.mark.parametrize("candidate,reason", KNOWN_PATH_TRAVERSAL)
   def test_known_path_traversal_regression(tmp_path, candidate, reason):
       with pytest.raises((ValueError, SecurityError)):
           resolve_under_base(tmp_path, candidate)
   ```

---

## Week 2: Expand Test Suite (8-10 hours)

**Goal**: Add 5-8 more property tests across 2-3 modules

### Modules to Fuzz (Priority Order)

1. ✅ `path_guard.py` (Week 1 - done)
2. **`approved_endpoints.py`** (Week 2) - URL validation, SSRF risk
3. **`sanitizers.py`** (Week 2) - CSV/Excel formula injection
4. `prompt_renderer.py` (Week 3) - Template injection
5. `config_parser.py` (Week 3) - YAML injection

### Example: URL Validation Properties

Create `tests/fuzz_props/test_url_validation_properties.py`:

```python
"""Property-based fuzzing for URL validation."""
import pytest
from hypothesis import given, strategies as st, settings

from elspeth.core.validators.approved_endpoints import validate_approved_endpoint
from elspeth.core.exceptions import SecurityError, URLError


@pytest.mark.fuzz
@given(
    url=st.from_regex(r'https?://[a-zA-Z0-9.-]+(/[^\\s]*)?', fullmatch=True)
)
@settings(max_examples=100, deadline=500)
def test_url_validation_never_allows_credentials(url):
    """
    Oracle: Validated URLs must never contain credentials.

    Invariant: No credentials in URL (from oracle table)
    """
    try:
        result = validate_approved_endpoint(url)

        # Oracle: No credentials in validated URL
        assert '@' not in result.netloc, \
            f"ORACLE VIOLATION: Credentials in validated URL\n" \
            f"  URL: {url}\n" \
            f"  Result netloc: {result.netloc}"

        # Oracle: Scheme must be http or https
        assert result.scheme in ['http', 'https'], \
            f"ORACLE VIOLATION: Invalid scheme\n" \
            f"  Scheme: {result.scheme}"

    except (ValueError, SecurityError, URLError):
        # Expected exceptions for invalid URLs
        pass
```

---

## Week 3: CI Integration (2-3 hours)

**Goal**: Automate fuzzing in GitHub Actions

### 1. Create Fast PR Workflow

Create `.github/workflows/fuzz.yml`:

```yaml
name: Property Tests (Fast)

on:
  pull_request:
  push:
    branches: [main, develop]

jobs:
  hypothesis-fast:
    runs-on: ubuntu-latest
    timeout-minutes: 5  # Hard limit

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.lock --require-hashes
          pip install -e . --no-deps --no-index

      - name: Run fast property tests
        env:
          HYPOTHESIS_PROFILE: ci
        run: |
          pytest tests/fuzz_props/ -v -m fuzz \
            --tb=short --maxfail=3

      - name: Upload crash artifacts (if crashes found)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: fuzz-crashes-pr-${{ github.run_id }}
          path: |
            .hypothesis/examples/
            .hypothesis/unicodedata/
          if-no-files-found: warn
          retention-days: 7
```

### 2. Create Nightly Deep Exploration

Create `.github/workflows/fuzz-nightly.yml`:

```yaml
name: Property Tests (Deep)

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:  # Manual trigger

jobs:
  hypothesis-explore:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Run deep property exploration
        env:
          HYPOTHESIS_PROFILE: explore
        run: |
          pytest tests/fuzz_props/ -v -m fuzz \
            --hypothesis-seed=random \
            --tb=short

      - name: Upload crash artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: fuzz-crashes-nightly-${{ github.run_id }}
          path: |
            .hypothesis/examples/
            .hypothesis/unicodedata/
          retention-days: 7

      - name: Create issue for crashes
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '[FUZZ] Nightly fuzzing found issues',
              body: `Fuzzing run failed. Check artifacts: https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
              labels: ['security', 'fuzzing', 'needs-triage']
            })
```

---

## Week 4: Polish & Documentation (3-5 hours)

### 1. Coverage Analysis

```bash
# Generate coverage report
pytest tests/fuzz_props/ -m fuzz \
  --cov=elspeth.core.utils.path_guard \
  --cov=elspeth.core.validators.approved_endpoints \
  --cov=elspeth.plugins.nodes.sinks.sanitizers \
  --cov-report=html \
  --cov-report=term-missing

# Review HTML report
open htmlcov/index.html

# Goal: ≥85% branch coverage on security modules
```

### 2. Create Metrics Dashboard

Create `docs/security/fuzzing/METRICS.md`:

```markdown
# Fuzzing Metrics Dashboard

**Last Updated**: YYYY-MM-DD

## Progress

| Module | Property Tests | Coverage | Bugs Found | Status |
|--------|----------------|----------|------------|--------|
| path_guard.py | 5 / 5 | 87% | 2 (S0, S2) | ✅ Complete |
| approved_endpoints.py | 5 / 5 | 82% | 1 (S1) | ✅ Complete |
| sanitizers.py | 3 / 3 | 79% | 0 | ✅ Complete |

**Total**: 13 / 15 property tests implemented

## Bugs Discovered

1. **[Issue #XXX]** Path traversal in resolve_under_base (S0 - FIXED)
2. **[Issue #YYY]** Unbounded memory in CSV sanitizer (S2 - FIXED)
3. **[Issue #ZZZ]** URL validation bypass for IDN (S1 - FIXED)

## CI Health

- PR test runtime: 3.2 min (target: <5 min) ✅
- Nightly runtime: 12.5 min (target: <15 min) ✅
- False positive rate: 4% (target: <10%) ✅
```

### 3. Update IRAP Evidence

Add to `fuzzing_irap_risk_acceptance.md`:

```markdown
## Phase 1 Implementation Status

**Status**: ✅ **OPERATIONAL** (as of YYYY-MM-DD)

**Evidence**:
- 15 property tests implemented across 5 security modules
- 3 security bugs found and fixed (S0, S1, S2)
- Bug injection tests validate 100% detection rate
- CI integration: PR tests (<5 min) + nightly exploration (15 min)
- Coverage: 85% branch coverage on security modules

**Conclusion**: Phase 1 demonstrates fuzzing ROI. Ready for shakedown cruise with PROTECTED data.
```

---

## Troubleshooting

### Issue: "No module named 'hypothesis'"

```bash
pip install hypothesis pytest-hypothesis
# Or if using lockfile:
pip install -r requirements-dev.lock --require-hashes
```

### Issue: "pytest: no tests ran matching -m fuzz"

Check `pyproject.toml` has marker definition:

```toml
[tool.pytest.ini_options]
markers = [
    "fuzz: Property-based fuzzing tests (pytest -m fuzz)",
]
```

### Issue: Property test takes >500ms (deadline exceeded)

Increase deadline or optimize test:

```python
@settings(max_examples=100, deadline=1000)  # 1 second
def test_slow_function(...):
    ...
```

### Issue: "Flaky" tests (pass/fail inconsistently)

Use `derandomize=true` in CI profile to make tests deterministic.

---

## Success Criteria

**Phase 1 is complete when**:

- ✅ 15+ property tests implemented
- ✅ ≥2 security bugs found (S0-S2)
- ✅ Bug injection tests pass validation (100% detection)
- ✅ CI integrated: <5 min PR, <15 min nightly
- ✅ ≥85% branch coverage on security modules
- ✅ False positive rate <10%

**Then**: Update IRAP risk acceptance, proceed to production shakedown cruise

---

## Next Steps After Phase 1

1. **Shakedown cruise**: Run Elspeth with PROTECTED data, monitor for security events
2. **External review**: Code review + penetration testing
3. **Monitor Phase 2 blocker**: Check Atheris Python 3.12 support monthly
4. **Expand coverage**: Add more security modules based on threat model updates

---

## Resources

- **Hypothesis Documentation**: <https://hypothesis.readthedocs.io/>
- **Property-Based Testing**: <https://fsharpforfunandprofit.com/posts/property-based-testing/>
- **Security Invariants**: See `fuzzing.md` Section 1.3

---

**Questions?** Contact Security Engineering Lead

**Last Updated**: 2025-10-25
