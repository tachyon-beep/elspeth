# Dependency Vulnerability Tracking

This document tracks known vulnerabilities in Elspeth's dependencies and their remediation status.

## Active Vulnerabilities

### CVE-2025-8869: pip tarfile extraction vulnerability

**Status:** 🟡 MONITORING (Fix pending upstream release)
**Severity:** LOW
**Scope:** Development dependency only (not in production runtime)
**Discovery Date:** 2025-10-20
**Target Resolution:** Upon pip 25.3 release

#### Details

- **Package:** pip 25.2
- **CVE:** CVE-2025-8869
- **GHSA:** GHSA-4xh5-x5gv-qwph
- **Issue:** Arbitrary file overwrite during malicious sdist installation via tarfile symlink/hardlink escape
- **Impact:** An attacker-controlled source distribution can overwrite arbitrary files on the host during `pip install`
- **Fix Status:** Patch available in https://github.com/pypa/pip/pull/13550, planned for pip 25.3 release

#### Risk Assessment

**Production Impact:** NONE
- pip is a development/build-time dependency only
- Not included in production runtime environments
- Not used during production operation

**Development Impact:** LOW
- Requires installing a malicious package from an attacker-controlled source
- Mitigated by installing only from trusted PyPI repository
- No known exploits in the wild targeting development environments

**Supply Chain Impact:** LOW
- Developer workstations install packages from trusted sources (requirements-*.lock with hashes)
- CI/CD pipelines use locked dependencies with hash verification
- No dynamic package installation from untrusted sources

#### Mitigation Strategy

**Current Controls:**
1. All dependencies pinned in requirements-*.lock files
2. Hash verification enabled for production lockfiles (requirements-azure.lock)
3. Developers instructed to install from lockfiles only
4. No installation from untrusted package indexes

**Planned Actions:**
1. ✅ Document vulnerability in this file (completed 2025-10-20)
2. 🔄 Monitor pip release schedule for 25.3
3. 🔄 Update requirements-dev.lock when pip 25.3 released
4. 🔄 Add `pip>=25.3` constraint to pyproject.toml dev dependencies

#### Tracking Links

- Upstream fix: https://github.com/pypa/pip/pull/13550
- CVE details: CVE-2025-8869
- GHSA advisory: https://github.com/advisories/GHSA-4xh5-x5gv-qwph

#### Update Log

- **2025-10-20:** Vulnerability identified during AIS forensic audit
- **2025-10-20:** Risk assessment completed, mitigation strategy documented
- **TBD:** pip 25.3 released
- **TBD:** Dependencies updated, vulnerability resolved

---

## Historical Vulnerabilities

None recorded.

---

## Monitoring Process

Elspeth uses the following tools for continuous dependency vulnerability monitoring:

1. **pip-audit** — Automated scanning of installed packages against PyPI vulnerability database
   ```bash
   .venv/bin/pip-audit --skip-editable
   ```

2. **GitHub Dependabot** — Automated pull requests for vulnerable dependencies (if enabled)

3. **Manual Reviews** — Quarterly security audits of dependency tree

### Running Vulnerability Scans

**Local Development:**
```bash
# Install pip-audit (included in dev dependencies)
pip install pip-audit

# Scan current environment
pip-audit

# Scan lockfile without installing
pip-audit -r requirements-dev.lock
```

**CI/CD Integration:**
```bash
# Fail build on HIGH/CRITICAL vulnerabilities
pip-audit --require-hashes -r requirements-azure.lock --vulnerability-service osv
```

### Remediation SLA

| Severity | Production Dependencies | Development Dependencies |
|----------|------------------------|-------------------------|
| CRITICAL | 7 days | 30 days |
| HIGH | 30 days | 90 days |
| MEDIUM | 90 days | Next major release |
| LOW | Next major release | Best effort |

---

## References

- NIST National Vulnerability Database: https://nvd.nist.gov/
- PyPI Advisory Database: https://github.com/pypa/advisory-database
- pip-audit documentation: https://pypi.org/project/pip-audit/
- GHSA database: https://github.com/advisories
