# Copilot Instructions for Elspeth

## Repository Overview

**Elspeth** (Extensible Layered Secure Pipeline Engine for Transformation and Handling) is a security-focused orchestration platform for LLM experimentation implementing sense-decide-act workflows. It follows a plugin-based architecture with strict security controls, compliance tracking, and audit logging.

## Architecture

### Core Components

- **Sources** (`src/elspeth/plugins/nodes/sources/`): Data ingestion and normalization with security level tagging
- **Transforms** (`src/elspeth/plugins/nodes/transforms/`): LLM clients, middleware, and processing logic
- **Sinks** (`src/elspeth/plugins/nodes/sinks/`): Output handlers including CSV, Excel, JSON, analytics, and visualizations
- **Orchestrator** (`src/elspeth/core/experiments/`): Experiment execution, suite management, and plugin wiring
- **Controls** (`src/elspeth/core/controls/`): Rate limiting, retry logic, concurrency management
- **Security** (`src/elspeth/core/security/`): Artifact signing, security level enforcement, audit logging

### Plugin System

All plugins follow the Phase 2 layout and must:
- Inherit from `BasePlugin` (`src/elspeth/core/base/plugin.py`)
- Implement `consumes()` and `produces()` for schema validation
- Register via `src/elspeth/core/registries/__init__.py`
- Follow security controls per `docs/architecture/security-controls.md`

## Environment Setup

### Prerequisites
- Python 3.12
- GNU Make
- Virtual environment recommended

### Bootstrap Commands
```bash
make bootstrap           # Full setup with tests
make bootstrap-no-test   # Skip initial test pass
source .venv/bin/activate
```

### Install Dependencies
**CRITICAL**: Always install from lockfiles with `--require-hashes`:
```bash
# Development environment
python -m pip install -r requirements-dev.lock --require-hashes
python -m pip install -e . --no-deps --no-index

# Azure ML workflows
python -m pip install -r requirements-dev-azure.lock --require-hashes
python -m pip install -e . --no-deps --no-index
```

**Never** install directly from `pyproject.toml` - always use lockfiles for reproducibility and AIS compliance.

## Development Workflow

### Linting
```bash
make lint  # Runs ruff format + ruff check + mypy
```

Ruff configuration:
- Line length: 140 characters
- Target: Python 3.12
- Security checks enabled (flake8-bandit)
- Docstring linting (pydocstyle) with relaxed rules

### Testing
```bash
make test                                        # All tests
python -m pytest -m "not slow"                   # Fast tests only
python -m pytest --maxfail=1 --disable-warnings  # Fail fast
```

Test markers:
- `integration`: Tests requiring external services (e.g., pgvector)
- `slow`: Long-running tests (may be excluded from CI)

Coverage target: ~83% (tracked via `baseline_coverage.txt`)

### Building
```bash
make sample-suite  # Run sample orchestration workflow
```

### Validation Commands
```bash
make verify-locked      # Verify lockfile integrity
make validate-templates # Check template syntax
make audit             # Security audit with pip-audit
make sbom              # Generate CycloneDX SBOM
```

## Code Standards

### Style Guidelines
- Python 3.12 with type annotations
- 4-space indentation
- Imperative commit messages (`Add`, `Fix`, `Refine`)
- Functions should be focused; refactor when complexity warnings appear
- Match existing comment styles in each file

### Type Checking
MyPy strict mode enabled for:
- `elspeth.core.*`
- `elspeth.plugins.*`
- `elspeth.adapters.*`

Other modules use relaxed mode but should check untyped definitions.

### Documentation
- Update `docs/architecture/` for new features
- Keep README.md CLI examples current
- Document security implications for changes touching datasources, middleware, or sinks
- Include artifact checksums when outputs change

## Security Requirements

### Mandatory Practices
1. **No secrets in code**: Use environment variables or Azure Key Vault
2. **Maintain security posture**: Features must not degrade existing controls
3. **Sanitization**: Spreadsheet data, prompt rendering, and user inputs must be sanitized
4. **Audit logging**: Changes affecting audit trails must preserve structured JSONL output
5. **Signed artifacts**: Support for HMAC-SHA256/SHA512, RSA-PSS-SHA256, ECDSA-P256-SHA256

### Security Scanning
All PRs must pass:
- Semgrep static analysis
- Bandit security linting
- CodeQL analysis
- pip-audit for dependencies
- Gitleaks for secrets detection
- Grype container scans (HIGH severity blocks)

### Dependency Policy
**Permissive licenses only**: MIT, Apache-2.0, BSD-2/3-Clause, ISC, PSF, Unlicense

**Not allowed**: GPL/AGPL/SSPL, LGPL, MPL, non-SPDX, EULAs, Unknown licenses

The Dependency Review workflow gates this in CI.

## File Organization

### Source Structure
```
src/elspeth/
├── core/
│   ├── base/           # Base classes (BasePlugin)
│   ├── controls/       # Rate limiting, retry, concurrency
│   ├── experiments/    # Orchestration and runners
│   ├── prompts/        # Prompt management
│   ├── registries/     # Plugin registration
│   ├── security/       # Security controls
│   └── utils/          # Utilities
├── plugins/
│   ├── nodes/
│   │   ├── sources/    # Data sources
│   │   ├── transforms/ # LLM clients, middleware
│   │   └── sinks/      # Output handlers
│   ├── experiments/    # Experiment helpers
│   └── utilities/      # Plugin utilities
└── adapters/           # External system adapters
```

### Test Structure
```
tests/
├── core/              # Core component tests
├── plugins/           # Plugin-specific tests
├── security/          # Security control tests
├── conftest.py        # Pytest fixtures
└── test_*.py          # Feature-specific tests
```

### Configuration
```
config/
└── sample_suite/      # Sample orchestration configs
```

### Build Artifacts (git-ignored)
- `outputs/` - Experiment results
- `logs/` - JSONL audit logs
- `artifacts/` - Signed bundles
- `.venv/` - Virtual environment
- `*.pyc`, `__pycache__/` - Python bytecode

## Common Tasks

### Adding a New Plugin

1. Create plugin class inheriting from `BasePlugin`
2. Implement required methods:
   ```python
   def consumes(self) -> list[str]: ...
   def produces(self) -> list[str]: ...
   def execute(self, input_data: dict) -> dict: ...
   ```
3. Register in `src/elspeth/core/registries/__init__.py`
4. Add tests in `tests/plugins/`
5. Update `docs/architecture/plugin-catalogue.md`
6. Check security controls in `docs/architecture/security-controls.md`

See `docs/development/plugin-authoring.md` for full guide.

### Running Experiments

```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

Flags:
- `--live-outputs`: Enable actual writes to repositories/blobs
- `--head N`: Preview first N rows
- `--artifacts-dir`: Enable artifact persistence
- `--signed-bundle`: Sign artifacts with configured key

### Validating Schemas

Pre-flight validation without running experiments:
```bash
python -m elspeth.cli validate-schemas \
  --settings config/sample_suite/settings.yaml \
  --profile default
```

### Regenerating Analytics

After changing reports or sinks:
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

## CI/CD Workflows

### GitHub Actions
- **ci.yml**: Linting, typing, tests, security scans, SBOM
- **codeql.yml**: CodeQL analysis (scheduled + PR)
- **publish.yml**: Container build, sign, attest with Cosign
- **dependency-review.yml**: PR dependency change analysis
- **dependabot-auto-merge.yml**: Safe auto-merge for security updates

### Action Pinning
All third-party actions are SHA-pinned for security. Current CodeQL pin: `16140ae1a102900babc80a33c44059580f687047` (v4.30.9)

### Security Gates (must pass)
- Tests with ~83% coverage
- Ruff + mypy type checking
- Semgrep + Bandit static analysis
- CodeQL (separate workflow)
- pip-audit dependency scanning
- CycloneDX SBOM generation
- Grype container scan (blocks on HIGH+)
- Gitleaks secrets detection
- Dependency review

## Troubleshooting

### Common Issues

**"No schema validation performed"**
- Attach schema to datasource via config or enable inference

**"Schema compatibility check failed"**
- Plugin's `input_schema()` requires columns/types datasource doesn't provide
- Fix datasource schema or adjust plugin requirements

**"Missing prompt_fields in datasource schema"**
- Add missing columns to datasource schema

**Build failures**
- Ensure using lockfiles: `pip install -r requirements-dev.lock --require-hashes`
- Check Python version: 3.12 required
- Run `make bootstrap` to reset environment

**Test failures**
- Run fast tests: `pytest -m "not slow"`
- Check baseline: `baseline_tests.txt`, `baseline_coverage.txt`
- Regenerate artifacts if outputs changed

### Log Locations
- Audit logs: `logs/run_*.jsonl`
- Experiment outputs: `outputs/`
- Suite reports: `outputs/*_reports/`
- Artifacts: `artifacts/` (when enabled)

### Log Retention
Configure via environment variables:
- `ELSPETH_LOG_MAX_FILES`: Keep newest N files
- `ELSPETH_LOG_MAX_AGE_DAYS`: Delete files older than N days

## Contributing Guidelines

### Pull Request Requirements
- Describe change, security considerations, and verification commands
- Link related issues
- Include screenshots/artifact diffs for output changes
- Pass all CI gates
- Update documentation for new features

### AI-Assisted Development
AI coding assistants (Copilot, Claude, ChatGPT, Cursor) are **fully acceptable** for:
- Writing code, tests, documentation
- Refactoring and optimization
- Research and problem-solving

**Personal AI configurations must remain local** (gitignored):
- `.claude/`, `.cursor/`, `.copilot/` directories
- `CLAUDE.md`, `AGENTS.md`, custom prompts

### Commit Message Style
Use imperative mood:
- ✅ `Add plugin validation`
- ✅ `Fix retry backoff calculation`
- ✅ `Refine security controls documentation`
- ❌ `Added plugin validation`
- ❌ `Fixed retry backoff calculation`

### Code Review Focus
- Security implications (especially for datasources, middleware, sinks)
- Plugin registration correctness
- Schema compatibility (`consumes()`/`produces()`)
- Type annotation completeness
- Test coverage for new code paths
- Documentation updates

## References

### Documentation
- Architecture: `docs/architecture/README.md`
- Plugin Catalogue: `docs/architecture/plugin-catalogue.md`
- Security Controls: `docs/architecture/security-controls.md`
- Plugin Authoring: `docs/development/plugin-authoring.md`
- Configuration Security: `docs/architecture/configuration-security.md`
- Operations: `docs/reporting-and-suite-management.md`
- Compliance: `docs/compliance/CONTROL_INVENTORY.md`

### Key Files
- Licensing policy: `CONTRIBUTING.md`
- Release checklist: `docs/release-checklist.md`
- Migration guide: `docs/migration-guide.md`
- Incident response: `docs/compliance/incident-response.md`

### Useful Commands Summary
```bash
make bootstrap          # Setup environment
make lint              # Format and check code
make test              # Run tests
make sample-suite      # Run sample workflow
make audit             # Security audit
make sbom              # Generate SBOM
make verify-locked     # Verify lockfile integrity
```

## Contact

- File bugs/features via GitHub Issues
- Security issues: See `docs/compliance/incident-response.md`
- Compliance questions: See `docs/compliance/CONTROL_INVENTORY.md`

---

**License**: MIT - see `LICENSE`

**Remember**: Security first, permissive licenses only, always use lockfiles with hashes.
