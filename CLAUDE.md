# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Elspeth** (Extensible Layered Secure Pipeline Engine for Transformation and Handling) is a security-first orchestration platform for LLM experimentation and general-purpose sense-decide-act workflows. The platform implements **Bell-LaPadula Multi-Level Security (MLS)** enforcement with fail-fast security validation (see ADR-002).

Core pipeline: **Sources → Transforms → Sinks** with middleware, plugins, and artifact signing throughout.

## Essential Commands

### Environment Setup
```bash
# Bootstrap (creates .venv, installs deps, runs tests)
make bootstrap

# Bootstrap without running tests
make bootstrap-no-test

# Activate environment (ALWAYS use lockfiles with --require-hashes)
source .venv/bin/activate
python -m pip install -r requirements-dev.lock --require-hashes
python -m pip install -e . --no-deps --no-index
```

**CRITICAL**: Never install from `pyproject.toml` unpinned ranges. Always use lockfiles (`requirements*.lock`) with `--require-hashes` for AIS compliance.

### Running Tests
```bash
# Fast feedback (excludes slow tests)
python -m pytest -m "not slow"

# Full test suite
make test

# Performance baseline
make perf

# During triage (fail fast)
python -m pytest --maxfail=1 --disable-warnings

# Run a single test file
python -m pytest tests/test_specific.py -v
```

### Linting and Type Checking
```bash
# Format, lint, and type check
make lint

# Individual tools
python -m ruff check src tests
python -m ruff format src tests
python -m mypy src/elspeth
```

### Running Experiments
```bash
# Run sample suite (mock LLM, no external deps)
make sample-suite

# Full CLI usage
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0

# With signed artifacts
make sample-suite-artifacts

# Validate schemas before running
python -m elspeth.cli validate-schemas \
  --settings config/sample_suite/settings.yaml \
  --profile default
```

### Security & Audit
```bash
# Audit dependencies for vulnerabilities
make audit

# Generate SBOM
make sbom

# Verify locked install matches lockfile
make verify-locked
```

## Architecture Overview

### Core Structure
- **`src/elspeth/core/`** – Orchestration engine, pipeline, registries, validation
  - `experiments/` – `ExperimentSuiteRunner` (suite_runner.py), `ExperimentOrchestrator`, plugin registry
  - `registries/` – Unified `BasePluginRegistry` framework (Phase 2 migration complete)
  - `pipeline/` – Artifact pipeline, chaining, security enforcement
  - `security/` – Security levels (MLS), signing, PII validation
  - `cli/` – CLI entry points (suite, single, job, validate)
  - `validation/` – Schema validation, suite validation, settings validation

- **`src/elspeth/plugins/`** – All plugins following Phase 2 layout
  - `nodes/sources/` – Datasources (CSV local/blob, future: PostgreSQL, Azure Search)
  - `nodes/transforms/llm/` – LLM clients (Azure OpenAI, OpenAI HTTP, mock)
    - `middleware/` – Prompt shielding, Azure Content Safety, health monitoring
  - `nodes/sinks/` – Output sinks (CSV, Excel, JSON, Markdown, visual analytics, signed bundles, repositories)
  - `experiments/` – Row/aggregation/baseline/early-stop plugins
    - `baseline/` – Statistical analysis (significance, effect size, power, Bayesian, distribution)
    - `aggregators/` – Summary stats, recommendations, cost/latency, rationale analysis

- **`tests/`** – Comprehensive test coverage (see `docs/development/testing-overview.md`)
  - Configuration, datasources, middleware, LLM adapters, sanitization, signing, artifact pipeline, suite runner

### Key Architectural Patterns

**Plugin Registration (Phase 2)**
- All registries use `BasePluginRegistry[T]` from `src/elspeth/core/registries/base.py`
- Plugins declare `consumes()` and `produces()` for safe composition
- Security levels declared via `security_level` field (enforced at pipeline construction)
- Context propagation via `PluginContext` (security_level, run_id, audit_logger)

**Multi-Level Security (ADR-002)**
- Pipeline computes minimum security level across all components (datasource, transforms, sinks)
- Components with higher declared levels refuse to run if pipeline level is downgraded
- **Fail-fast**: Misconfigured pipelines abort before data retrieval
- Example: SECRET datasource + UNOFFICIAL sink → pipeline aborts before querying datasource

**Configuration Merge Order** (see `docs/architecture/configuration-security.md`)
1. Suite defaults (`config/suite_defaults.yaml`)
2. Prompt packs (if specified)
3. Experiment-specific overrides
4. Deep merge with validation at each layer

**Artifact Pipeline** (`src/elspeth/core/pipeline/artifact_pipeline.py:192`)
- Dependency-ordered execution
- Security level enforcement per sink
- Chaining metadata between sinks
- Signed bundle support (HMAC-SHA256/SHA512, RSA-PSS-SHA256, ECDSA-P256-SHA256)

## Critical Security Considerations

1. **Never bypass lockfile installs** – Always use `requirements*.lock` with `--require-hashes`
2. **Security level validation** – All new plugins MUST declare `security_level`
3. **Spreadsheet sanitization** – Excel/CSV sinks automatically sanitize formulas (see `_sanitize.py`)
4. **Prompt rendering** – Use strict Jinja2 sandboxing (`src/elspeth/core/prompts/template.py`)
5. **Audit logging** – All runs emit JSONL logs to `logs/run_*.jsonl`
6. **Container signing** – Published images are Cosign-signed with SBOM attestations

## Common Development Patterns

### Adding a New Plugin

1. **Create plugin class** in appropriate directory:
   - Datasource: `src/elspeth/plugins/nodes/sources/`
   - Transform: `src/elspeth/plugins/nodes/transforms/llm/`
   - Sink: `src/elspeth/plugins/nodes/sinks/`
   - Experiment helper: `src/elspeth/plugins/experiments/`

2. **Implement required methods**:
   - Sources: `load_data()`, `security_level` property
   - Transforms: `transform()`, `consumes()`, `produces()`
   - Sinks: `write()`, `consumes()`, `produces()`, `security_level`

3. **Register plugin** in corresponding registry (see `src/elspeth/core/registries/`)

4. **Add schema validation** using `jsonschema` patterns

5. **Write tests** covering:
   - Happy path
   - Security level enforcement
   - Error handling (`on_error` policies)
   - Schema validation

6. **Update documentation** in `docs/architecture/plugin-catalogue.md`

### Running Single Test with Coverage
```bash
python -m pytest tests/test_specific.py -v --cov=elspeth.module --cov-report=term-missing
```

### Regenerating Artifacts After Changes
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

### Debugging Configuration Issues

1. Use `validate-schemas` first to catch mismatches
2. Check logs in `logs/run_*.jsonl` for audit trail
3. Use `--head 0` to skip preview tables and focus on execution
4. Enable dry-run mode with `--live-outputs` omitted

## Major Refactoring: Complexity Reduction Methodology

For high-security orchestration platforms like Elspeth, **major code changes require a systematic, zero-regression approach**. The team has developed a battle-tested five-phase methodology documented in `docs/refactoring/`.

### When to Use This Methodology

**Use for functions with:**
- Cognitive complexity ≥ 25 (SonarQube "Critical" or "Major")
- Test coverage ≥ 70% (if lower, build tests first)
- No active feature work (avoid merge conflicts)
- 10-15 hours available over 3-5 days

**Success Rate:** 100% (2/2 PRs) with 86.7% average complexity reduction, zero behavioral changes, zero regressions.

### Five-Phase Process Overview

```
Phase 0: Safety Net Construction (35% of time, 4-6 hours)
    ↓
Phase 1: Supporting Classes (10%, 1-2 hours)
    ↓
Phase 2: Simple Helper Extractions (20%, 2-3 hours)
    ↓
Phase 3: Complex Method Extractions (30%, 3-4 hours)
    ↓
Phase 4: Documentation & Cleanup (10%, 1-2 hours)
```

### Phase 0: Safety Net Construction (CRITICAL)

**Build comprehensive test coverage BEFORE touching code:**

1. **Risk Assessment** – Identify top 3-5 risks using `Impact × Probability × Subtlety`
2. **Risk Reduction Activities** – Document subtle behaviors, write 3-7 tests per risk area
3. **Characterization Tests** – Write 6+ integration tests capturing complete workflows
4. **Coverage Target** – Achieve ≥80% coverage on target function
5. **Mutation Testing** – Run `mutmut` to verify test quality (≤10% survivors)

**Exit Criteria:** All tests passing (100%), MyPy clean, Ruff clean

**⚠️ DO NOT skip Phase 0. Spend 30-40% of time here. This is the secret to zero-regression refactoring.**

### Phase 1: Supporting Classes

Create 1-3 dataclasses to consolidate scattered state (5+ variables → single typed object). Reduces parameter passing complexity and enables focused helper methods.

### Phase 2: Simple Helper Extractions

Extract 4-6 low-risk helpers (5-20 lines each), ONE AT A TIME:
- Initialization blocks → `_prepare_suite_context()`
- Priority chain lookups → `_resolve_experiment_sinks()`
- Simple getters → `_get_experiment_context()`
- Cleanup blocks → `_finalize_suite()`

**Run tests after EVERY extraction.** Target: ~30-40% complexity reduction.

### Phase 3: Complex Method Extractions

Extract 5-7 high-complexity helpers (15-40 lines each), **ONE AT A TIME**:
- Notification patterns → `_notify_middleware_suite_loaded()`
- Orchestration logic → `_run_baseline_comparison()`
- Config merging → `_merge_baseline_plugin_defs()`

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

**⚠️ Extract ONE method, test, commit. NEVER batch complex extractions.**

Target: ≥85% complexity reduction, run() becomes readable orchestration template (30-60 lines).

### Phase 4: Documentation & Cleanup

1. **Enhance run() docstring** – 50+ lines with execution flow, design patterns, complexity metrics
2. **Review helper docstrings** – Ensure Args/Returns/Complexity Reduction notes
3. **Create summary document** – `REFACTORING_COMPLETE_<target>.md` with metrics, phase breakdown, helper catalog
4. **Create ADR** – Document decision in `docs/architecture/decisions/`
5. **Final verification** – All tests passing, MyPy clean, Ruff clean, complexity ≤15

### Key Success Principles

1. **Test-First is Non-Negotiable** – 80%+ coverage before any changes
2. **One Thing at a Time** – ONE method extraction → tests → commit
3. **Zero Behavioral Changes** – Refactoring changes structure ONLY, not behavior
4. **Commit Frequently** – After each phase minimum, optionally after each complex extraction
5. **Template Method Pattern** – run() becomes orchestration template delegating to focused helpers

### Quick Reference

**Essential Reading:**
- `docs/refactoring/QUICK_START.md` – TL;DR for experienced developers
- `docs/refactoring/METHODOLOGY.md` – Full 2,300-line guide
- `docs/refactoring/v1.1/CHECKLIST.md` – Phase-by-phase checklist

**Common Commands:**
```bash
# Check complexity before starting
radon cc src/<path>/target.py -s

# Run mutation testing (Phase 0)
mutmut run --paths-to-mutate src/<path>/target.py

# Run tests after each extraction
pytest tests/test_<target>*.py -v

# Verify final complexity
radon cc src/<path>/target.py -s  # Target: ≤15
```

**Emergency Rollback:**
```bash
# If tests fail after extraction
git reset --hard HEAD~1  # Revert last commit
# Investigate, try smaller extraction
```

### When NOT to Use

❌ Don't use this methodology for:
- Functions with complexity < 15 (not worth 10-15 hour investment)
- Untested code (build tests first in separate PR)
- Code under active feature development (high merge conflict risk)
- Code scheduled for deletion <6 months

### Real-World Results

**PR #10 (runner.py):** 73 → 11 complexity (85% reduction), 150 → 51 lines, 15 helpers, 12 hours
**PR #11 (suite_runner.py):** 69 → 8 complexity (88.4% reduction), 138 → 55 lines, 11 helpers, 14 hours

Both PRs: 100% test pass rate, zero behavioral changes, zero regressions, coverage maintained/improved.

**This methodology is proven for high-security orchestration code. Follow it rigorously for major refactoring work.**

## Project-Specific Constraints

### Licensing (CRITICAL)
- **Permissive licenses ONLY**: MIT, Apache-2.0, BSD, ISC, PSF, Unlicense
- **No copyleft**: GPL/AGPL/LGPL/MPL strictly forbidden
- CI enforces license checks in Dependency Review workflow

### Code Style
- Python 3.12 required
- Line length: 140 chars (Ruff)
- Type annotations enforced in core modules (see `pyproject.toml:177-199`)
- Docstrings: Google style (relaxed enforcement, see Ruff config)
- Security rules: flake8-bandit enabled (S-series)

### Testing Requirements
- All security-critical paths must have test coverage
- Use `pytest` markers: `@pytest.mark.integration`, `@pytest.mark.slow`
- Configuration tests in `tests/test_config*.py`
- Middleware tests in `tests/test_llm_middleware.py`
- Artifact pipeline tests in `tests/test_artifact_pipeline.py`

### Commit Conventions
- Imperative mood: "Add", "Fix", "Refine", "Security:", "Docs:", "Test:"
- Reference issues/ADRs when relevant
- Sign commits for security changes

## Documentation Structure

- **`docs/architecture/`** – System design, ADRs, component diagrams
- **`docs/development/`** – Plugin authoring, testing, logging standards, lifecycle
- **`docs/compliance/`** – Security controls, incident response, traceability matrix
- **`docs/operations/`** – Artifacts, logging, healthcheck, retrieval endpoints
- **`docs/examples/`** – End-to-end scenarios, security demos, Azure workflows

## Key Files to Reference

- **Architecture**: `docs/architecture/architecture-overview.md`, `docs/architecture/component-diagram.md`
- **Security**: `docs/architecture/decisions/002-security-architecture.md`, `docs/architecture/security-controls.md`
- **Plugin Development**: `docs/development/plugin-authoring.md`, `docs/architecture/plugin-catalogue.md`
- **Configuration**: `docs/architecture/configuration-security.md` (merge order, validation pipeline)
- **Testing**: `docs/development/testing-overview.md`
- **Migration**: `docs/migration-guide.md`, `docs/development/upgrade-strategy.md`
- **Refactoring**: `docs/refactoring/METHODOLOGY.md`, `docs/refactoring/QUICK_START.md`, `docs/refactoring/v1.1/CHECKLIST.md`

## Azure ML Integration (Optional)

For Azure ML workflows, use Azure-specific lockfiles:
```bash
# Runtime only
pip install --require-hashes -r requirements-azure.lock
pip install -e . --no-deps

# Dev tooling + Azure
python -m pip install -r requirements-dev-azure.lock --require-hashes
python -m pip install -e . --no-deps --no-index
```

Azure datasources and sinks require `azure-identity`, `azure-storage-blob`, `azure-search-documents`.

## Common Pitfalls

1. **Installing without lockfiles** → Use `requirements*.lock` with `--require-hashes`, never `pip install -e .[dev]` directly
2. **Forgetting security_level** → All plugins MUST declare security level or pipeline will reject
3. **Skipping schema validation** → Always run `validate-schemas` before executing experiments
4. **Not handling on_error** → Datasources and sinks should respect `on_error: abort|skip|log`
5. **Modifying suite defaults without validation** → Changes to `suite_defaults.yaml` affect all experiments
6. **Ignoring artifact dependencies** → Sinks must declare `consumes()` for proper chaining

## Useful Debugging Tips

- **Enable verbose pytest**: `python -m pytest -vv --tb=long`
- **Check audit logs**: `tail -f logs/run_*.jsonl`
- **Validate lockfile sync**: `make verify-locked`
- **Inspect artifact metadata**: Check `outputs/*/manifest.json` for run details
- **Test single experiment**: Use CLI with `--suite-root` pointing to single experiment config
- **Schema validation errors**: Often mean datasource columns don't match plugin `input_schema()`

## Related ADRs

- **ADR-001**: Design Philosophy – Security-first priority hierarchy
- **ADR-002**: Multi-Level Security Enforcement – Bell-LaPadula MLS model with pipeline-wide minimum evaluation

## Contact & Support

- File issues via GitHub Issues
- Security escalation: `docs/compliance/incident-response.md`
- Compliance evidence: `docs/compliance/CONTROL_INVENTORY.md`, `docs/compliance/TRACEABILITY_MATRIX.md`
