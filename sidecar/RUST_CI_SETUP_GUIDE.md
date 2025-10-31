# Rust CI/CD Setup Guide for ELSPETH Sidecar Daemon

## 📋 Overview

This guide provides step-by-step instructions to implement comprehensive CI/CD for the Rust sidecar daemon, matching the sophistication of the Python CI/CD infrastructure.

**Created Files:**
- ✅ `sidecar/deny.toml` - Security policy (licenses, advisories, sources)
- ✅ `.github/workflows/reusable-rust-ci.yml` - Reusable CI workflow
- ✅ `.github/workflows/rust-build.yml` - Main Rust build workflow
- ✅ `.github/workflows/integration-tests.yml` - Python ↔ Rust integration tests
- ✅ `.github/dependabot.yml` - Updated with Rust dependency management

---

## 🚀 Quick Start (5 Minutes)

### 1. Verify Files Are in Place

```bash
# Check that all files were created
ls -la sidecar/deny.toml
ls -la .github/workflows/reusable-rust-ci.yml
ls -la .github/workflows/rust-build.yml
ls -la .github/workflows/integration-tests.yml
```

### 2. Test Locally (Before Pushing)

```bash
# Navigate to sidecar directory
cd sidecar

# Install required Rust tools
cargo install --locked cargo-deny cargo-audit

# Run the full CI pipeline locally
cargo fmt -- --check              # Formatting check
cargo clippy -- -D warnings       # Linting with strict warnings
cargo test --all-features         # All tests
cargo deny check                  # License & security policy
cargo audit                       # CVE scanning
cargo build --release             # Release build

# Return to project root
cd ..
```

### 3. Commit and Push

```bash
# Add all new files
git add sidecar/deny.toml
git add .github/workflows/reusable-rust-ci.yml
git add .github/workflows/rust-build.yml
git add .github/workflows/integration-tests.yml
git add .github/dependabot.yml
git add sidecar/RUST_CI_SETUP_GUIDE.md

# Commit with descriptive message
git commit -m "ci(rust): Add comprehensive CI/CD for sidecar daemon

- Add deny.toml for security policy enforcement
- Add reusable Rust CI workflow (fmt, clippy, test, security)
- Add integration test workflow (Python ↔ Rust)
- Configure Dependabot for Rust dependencies
- Enforce license compliance (permissive only)
- CVE scanning via cargo-audit + RustSec
- MSRV check (Rust 1.77)
- Binary size analysis
- Unsafe code audit

Matches Python CI/CD sophistication with:
✅ SHA-pinned GitHub Actions
✅ Locked dependency versions
✅ Security scanning (deny.toml, cargo-audit)
✅ Coverage enforcement (optional cargo-tarpaulin)
✅ Integration tests with daemon + Python client

See: sidecar/RUST_CI_SETUP_GUIDE.md"

# Push to your feature branch
git push origin feature/sidecar-security-daemon
```

---

## 🔍 Detailed Setup Steps

### Step 1: Fix Existing Clippy Errors (REQUIRED)

Before CI passes, fix the clippy errors identified in the code review:

```bash
cd sidecar

# Auto-fix clippy errors
cargo clippy --fix --all-targets --allow-dirty --allow-staged

# Expected fixes:
# - sidecar/tests/grants_test.rs:52 - Remove redundant pattern matching
# - sidecar/tests/handlers_test.rs - Remove useless try_into() conversions

# Verify all tests still pass
cargo test

# Commit the fixes
git add -u
git commit -m "fix(rust): Auto-fix clippy linting errors

- Remove redundant pattern matching in grants_test.rs
- Remove useless try_into() conversions in handlers_test.rs

All clippy warnings now resolved (--deny warnings ready)"

cd ..
```

### Step 2: Fix Python Type Safety Issues (REQUIRED)

Fix the MyPy errors in `sidecar_client.py`:

```bash
# Fix type annotations in sidecar_client.py
# See code review report for specific line numbers

# After fixing, verify
python -m mypy src/elspeth/core/security/sidecar_client.py
python -m mypy src/elspeth/core/security/digest.py

# Fix unused imports
python -m ruff check --fix src/elspeth/core/security/
```

### Step 3: Install Required Rust Tools (Local Development)

```bash
# Install cargo-deny for license & security checks
cargo install cargo-deny

# Install cargo-audit for CVE scanning
cargo install cargo-audit

# Optional: Install cargo-geiger for unsafe code auditing
cargo install cargo-geiger

# Optional: Install cargo-tarpaulin for coverage
cargo install cargo-tarpaulin

# Optional: Install cargo-outdated for dependency updates
cargo install cargo-outdated
```

### Step 4: Configure Cargo.lock (Already Done)

The `Cargo.lock` should already exist. If not:

```bash
cd sidecar
cargo update  # Generate/update Cargo.lock
cd ..
```

### Step 5: Test CI Workflows Locally

Use [act](https://github.com/nektos/act) to test GitHub Actions locally (optional):

```bash
# Install act (if not already installed)
# macOS: brew install act
# Linux: curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Test Rust build workflow
act -W .github/workflows/rust-build.yml

# Test integration workflow
act -W .github/workflows/integration-tests.yml
```

### Step 6: Enable GitHub Actions (If Disabled)

```bash
# Check if Actions are enabled in your repo
gh repo view --json hasIssuesEnabled,hasWikiEnabled,hasProjectsEnabled

# If you need to enable Actions, go to:
# https://github.com/YOUR_ORG/elspeth/settings/actions
```

### Step 7: Configure Branch Protection (Recommended)

Add these CI checks to required status checks:

```bash
# Via GitHub UI: Settings > Branches > Branch protection rules > main

# Required status checks:
- Rust CI (Format, Lint, Test)
- MSRV Check (Rust 1.77)
- Unsafe Code Audit (cargo-geiger)
- Python ↔ Rust Integration Tests

# Or via GitHub CLI:
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=rust-ci \
  --field required_status_checks[contexts][]=msrv-check \
  --field required_status_checks[contexts][]=python-rust-integration
```

---

## 📦 What Each Workflow Does

### 1. **reusable-rust-ci.yml** (Core CI - Reusable)

Runs on every Rust code change. Executes:

1. ✅ **Type Check** (`cargo check`) - Fastest feedback
2. ✅ **Formatting** (`cargo fmt --check`) - Enforced style
3. ✅ **Linting** (`cargo clippy -D warnings`) - Zero warnings policy
4. ✅ **Tests** (`cargo test`) - All unit + integration tests
5. ✅ **Security Scan** (`cargo deny check`) - License + CVE + sources
6. ✅ **Dependency Audit** (`cargo audit`) - RustSec advisories
7. ✅ **Release Build** (`cargo build --release`) - Production-ready binary

**Caching Strategy:**
- Cargo registry cached by `Cargo.lock` hash
- Build artifacts cached by source file hashes
- ~80% faster builds on cache hit

### 2. **rust-build.yml** (Main Workflow)

Calls `reusable-rust-ci.yml` plus additional checks:

- **MSRV Check:** Ensures code compiles with Rust 1.77 (minimum)
- **Unsafe Audit:** Reports `unsafe` block usage via `cargo-geiger`
- **Binary Size:** Prevents bloat (fails if binary > 20 MB)
- **Dependency Tree:** Detects duplicate dependencies

**Triggers:**
- Push to `main` or `feature/**` branches
- Pull requests modifying `sidecar/**`
- Manual workflow dispatch

### 3. **integration-tests.yml** (End-to-End)

Tests the full Python ↔ Rust communication stack:

1. **Build Rust daemon** (`cargo build --release`)
2. **Install Python deps** (locked with `--require-hashes`)
3. **Run integration tests** (`pytest test_sidecar_integration.py`)
4. **Test health check** (standalone + sidecar modes)
5. **CBOR round-trip** (verify protocol compatibility)

**Triggers:**
- Any change to `sidecar/**` or `src/elspeth/core/security/**`
- Ensures Python client and Rust daemon stay in sync

### 4. **Dependabot** (Automated Dependency Updates)

Checks Rust dependencies every **Thursday 9 AM AEST**:

- **Grouped updates:** tokio-stack, serde-stack, crypto-libs
- **Conservative crypto:** Only patch updates for `ring`, `blake*`
- **Lockfile-only:** Respects `Cargo.lock` (like pip-compile)
- **Auto-labeled:** `dependencies`, `rust`, `sidecar`

---

## 🛡️ Security Policy Enforcement

### deny.toml - What It Does

The `deny.toml` file enforces **strict security policies**:

| Policy | Setting | Rationale |
|--------|---------|-----------|
| **License** | Permissive only (MIT, Apache-2.0, BSD) | Matches CLAUDE.md requirements |
| **Copyleft** | Deny GPL/AGPL/LGPL/MPL | Legal/compliance risk |
| **CVEs** | Deny vulnerabilities | Zero-tolerance for known CVEs |
| **Sources** | crates.io only (no git deps) | Supply chain security |
| **Duplicates** | Deny multiple versions | Reduce attack surface |
| **Yanked** | Deny yanked crates | Critical bugs detected |
| **Unmaintained** | Warn (review required) | No security patches |

### How to Handle Policy Violations

#### License Violation Example

```bash
$ cargo deny check licenses
error: license `GPL-2.0` is explicitly denied

Crate: some-gpl-crate v1.0.0
License: GPL-2.0

# Resolution:
# Option 1: Replace dependency with permissive alternative
# Option 2: Request exception (rare, requires security team approval)
```

#### CVE Detected Example

```bash
$ cargo audit
Crate:     tokio
Version:   1.28.0
Warning:   RUSTSEC-2023-0001 (High severity)
           Vulnerability in tokio::io::AsyncReadExt::read_buf
Fix:       Upgrade to tokio >= 1.28.1

# Resolution:
cargo update tokio
cargo test  # Verify still works
git commit -am "security: Update tokio to fix RUSTSEC-2023-0001"
```

#### Multiple Versions Detected

```bash
$ cargo tree -d
syn v1.0.109
└── serde_derive v1.0.163

syn v2.0.15
└── tokio-macros v2.1.0

# Resolution:
# Update Cargo.toml to unify versions
# Run: cargo tree -i syn  # Find which crates depend on old version
# Update those crates or use [patch] section
```

---

## 🔧 Troubleshooting

### CI Failing: "clippy warnings treated as errors"

```bash
# Run locally to see warnings
cargo clippy --all-targets --all-features

# Auto-fix what's possible
cargo clippy --fix --all-targets --allow-dirty

# Commit fixes
git commit -am "fix(rust): Resolve clippy warnings"
```

### CI Failing: "cargo-deny check failed"

```bash
# Run locally to see violations
cargo deny check

# Common fixes:
cargo deny check licenses  # License violations
cargo deny check advisories  # Security CVEs
cargo deny check sources  # Git dependencies detected
```

### Integration Tests Skipped in CI

```bash
# Check if ELSPETH_RUN_INTEGRATION_TESTS is set
# In .github/workflows/integration-tests.yml:
env:
  ELSPETH_RUN_INTEGRATION_TESTS: "1"  # ✅ Must be set
```

### Binary Size Exceeds 20 MB

```bash
# Analyze what's bloating the binary
cargo install cargo-bloat
cargo bloat --release

# Common solutions:
# 1. Remove unused dependencies
# 2. Use feature flags to make dependencies optional
# 3. Check for duplicate dependencies (cargo tree -d)
```

---

## 📊 CI/CD Checklist (For Coding Agent)

Use this checklist when implementing:

- [x] `sidecar/deny.toml` created with security policies
- [x] `.github/workflows/reusable-rust-ci.yml` created
- [x] `.github/workflows/rust-build.yml` created
- [x] `.github/workflows/integration-tests.yml` created
- [x] `.github/dependabot.yml` updated with Rust section
- [ ] Fix clippy errors in `sidecar/tests/` (auto-fix available)
- [ ] Fix MyPy errors in `src/elspeth/core/security/sidecar_client.py`
- [ ] Fix ruff import errors (auto-fix: `ruff check --fix`)
- [ ] Install `cargo-deny` and `cargo-audit` locally
- [ ] Run full CI pipeline locally (see Quick Start step 2)
- [ ] Commit all changes with descriptive message
- [ ] Push and verify GitHub Actions pass
- [ ] Add required status checks to branch protection
- [ ] Update `CLAUDE.md` to document Rust CI (optional)

---

## 🎯 Success Criteria

Your CI/CD is ready when:

✅ **All workflows pass** on push to main/feature branches
✅ **Clippy errors** resolved (`cargo clippy -D warnings` passes)
✅ **MyPy errors** resolved (`mypy src/` passes)
✅ **Integration tests** pass (Python ↔ Rust daemon communication)
✅ **Security scans** pass (`cargo deny check` + `cargo audit`)
✅ **Dependabot** creates Rust dependency PRs on Thursdays
✅ **Branch protection** configured (require CI before merge)

---

## 📚 Additional Resources

### Rust CI/CD Best Practices
- [cargo-deny docs](https://embarkstudios.github.io/cargo-deny/)
- [RustSec Advisory Database](https://rustsec.org/)
- [GitHub Actions for Rust](https://github.com/actions-rs)

### ELSPETH Project Docs
- `../docs/architecture/decisions/002-security-architecture.md` - MLS enforcement
- `../docs/compliance/CONTROL_INVENTORY.md` - Security controls
- `../CLAUDE.md` - Project development guidelines

### Security
- `../docs/security/DEPENDENCY_VULNERABILITIES.md` - Vulnerability tracking
- `.github/workflows/dependency-review.yml` - Existing Python security

---

## 🤝 Support

If you encounter issues:

1. **Check workflow logs:** GitHub Actions > Failed workflow > View logs
2. **Run locally first:** Reproduce error with commands from Quick Start
3. **Review deny.toml:** Ensure policies match your security requirements
4. **Verify dependencies:** Run `cargo tree -d` to find duplicates

For security policy exceptions, consult with your security team before modifying `deny.toml`.

---

**Last Updated:** 2025-10-30
**Maintainer:** ELSPETH Security Team
**Related ADR:** ADR-002 (Multi-Level Security Enforcement)
