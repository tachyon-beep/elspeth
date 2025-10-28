# ADR-012 – Testing Strategy and Quality Gates (LITE)

## Status

**DRAFT** (2025-10-26)

## Context

High-security orchestration platform requires comprehensive testing. Current gaps: inconsistent test coverage, no mutation testing, unclear quality gates for PRs.

## Decision

Implement **Multi-Layer Testing Strategy** with enforced quality gates.

### Testing Pyramid

```
         /\
        /  \  E2E Tests (5%)
       /____\
      /      \
     / Integ  \ Integration Tests (20%)
    /__________\
   /            \
  /    Unit      \ Unit Tests (75%)
 /________________\
```

### Test Types

**Unit Tests** (75% of suite):
```python
def test_security_level_enforcement():
    """Verify MLS enforcement (ADR-002)."""
    plugin = create_plugin(security_level=SecurityLevel.SECRET)
    assert plugin.security_level == SecurityLevel.SECRET

    with pytest.raises(SecurityValidationError):
        plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
```

**Integration Tests** (20%):
```python
def test_pipeline_execution():
    """Verify end-to-end pipeline with real datasource/sinks."""
    runner = ExperimentSuiteRunner(...)
    results = runner.run()

    assert results["status"] == "completed"
    assert Path("outputs/results.csv").exists()
```

**E2E Tests** (5%):
```python
def test_full_suite_with_azure_ml():
    """Verify complete suite with Azure ML integration."""
    # Requires Azure credentials, runs in CI only
    ...
```

### Quality Gates (CI Enforcement)

**Gate 1: Test Coverage**
```bash
pytest --cov=elspeth --cov-report=term --cov-fail-under=80
# ✅ Must achieve ≥80% coverage
```

**Gate 2: Security Tests**
```bash
pytest -m security  # Run all security tests
# ✅ All security tests must pass
```

**Gate 3: Mutation Testing** (high-security modules):
```bash
mutmut run --paths-to-mutate src/elspeth/core/security
# ✅ Mutation score ≥70% for security modules
```

**Gate 4: Type Checking**
```bash
mypy src/elspeth
# ✅ No type errors allowed
```

**Gate 5: Linting**
```bash
ruff check src tests
# ✅ Zero linting errors (warnings OK)
```

### Mutation Testing (Security-Critical)

**Target Modules** (≥70% mutation score required):
- `src/elspeth/core/security/` - All security enforcement
- `src/elspeth/core/security/secure_data.py` - Container model (ADR-002-A)
- `src/elspeth/core/base/plugin.py` - BasePlugin security bones

**Example**:
```bash
# Mutate security module
mutmut run --paths-to-mutate src/elspeth/core/security/secure_data.py

# View survivors
mutmut results
# Mutant #42: Changed `if level < self.classification` to `if level <= self.classification`
# Status: SURVIVED (test didn't catch this!)
# Action: Add test for exact boundary condition
```

### Test Organization

```
tests/
├── unit/
│   ├── test_security.py
│   ├── test_plugins.py
│   └── test_registries.py
├── integration/
│   ├── test_pipeline.py
│   └── test_suite_runner.py
├── e2e/
│   └── test_azure_ml_suite.py
├── security/  # Marked with @pytest.mark.security
│   ├── test_adr002_invariants.py
│   └── test_adr006_exceptions.py
└── fixtures/
    ├── config/
    └── data/
```

### CI Pipeline

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Unit + Integration Tests
        run: pytest --cov=elspeth --cov-fail-under=80

      - name: Security Tests
        run: pytest -m security

      - name: Mutation Testing (Security Modules)
        run: mutmut run --paths-to-mutate src/elspeth/core/security

      - name: Type Checking
        run: mypy src/elspeth

      - name: Linting
        run: ruff check src tests
```

## Consequences

### Benefits
- **Enforced quality** - PRs blocked if gates fail
- **Security confidence** - Mutation testing catches weak tests
- **Consistent standards** - All code meets same bar
- **Fast feedback** - CI runs in <5 minutes

### Limitations
- **Mutation testing cost** - ~10-15 minutes for security modules
- **Coverage pressure** - Developers may write "coverage tests" (no assertions)
- **E2E brittleness** - Azure ML tests flaky (network, credentials)

### Mitigations
- **Parallel mutation** - Run mutmut across modules concurrently
- **Coverage + mutation** - Both required (coverage alone insufficient)
- **E2E in nightly** - Daily E2E runs, not per-PR

## Related

ADR-001 (Philosophy - quality first), ADR-006 (Security-critical testing), Refactoring methodology (Phase 0)

---
**Last Updated**: 2025-10-26
