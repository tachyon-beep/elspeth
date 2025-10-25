# Code Quality Reports

This directory contains code quality analysis reports and triage documentation.

---

## Contents

| Document | Purpose | Status |
|----------|---------|--------|
| **sonar_issues_triaged.md** | SonarQube issue triage and resolution tracking | Active |

---

## Quality Tools

**SonarQube**: Static analysis for code quality, security vulnerabilities, and code smells
- Instance: SonarCloud (cloud-based)
- Integration: GitHub Actions CI/CD
- Metrics tracked: Complexity, coverage, duplications, security hotspots

**Ruff**: Fast Python linter (replaces flake8, isort, pyupgrade)
- Config: `pyproject.toml`
- Run: `make lint` or `python -m ruff check src tests`

**MyPy**: Static type checker
- Config: `pyproject.toml`
- Run: `make lint` or `python -m mypy src/elspeth`

---

## Quality Standards

**Complexity Thresholds**:
- **Critical** (≥50): Immediate refactoring required
- **Major** (25-49): Refactoring recommended within sprint
- **Moderate** (15-24): Monitor, refactor if modifying
- **Low** (<15): Acceptable

**Test Coverage**:
- **Minimum**: 70% overall
- **Critical paths**: 100% (security, authentication, data pipeline)
- **New code**: 80% minimum

**Security**:
- **Zero P0 vulnerabilities** in production code
- **Zero Critical** security hotspots unaddressed
- All dependencies scanned with `make audit`

---

## Related Documentation

- **Testing Overview**: `docs/development/testing-overview.md`
- **Refactoring Methodology**: `docs/refactoring/METHODOLOGY.md`
- **Security Controls**: `docs/architecture/security-controls.md`
- **Compliance**: `docs/compliance/CONTROL_INVENTORY.md`

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Created**: 2025-10-25
