# Installation

Get Elspeth up and running on your system.

## Prerequisites

- **Python 3.12** or higher
- **pip** package manager
- **Git** (for cloning the repository)
- **Virtual environment support** (venv)

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.12 | 3.12+ |
| RAM | 4 GB | 8 GB |
| Disk Space | 500 MB | 1 GB |
| OS | Linux, macOS, Windows | Linux (tested on Ubuntu 22.04+) |

---

## Quick Install

The fastest way to get started:

```bash
# Clone the repository
git clone https://github.com/johnm-dta/elspeth.git
cd elspeth

# Run bootstrap (creates venv, installs dependencies, runs tests)
make bootstrap
```

**That's it!** The `bootstrap` command handles everything:
- Creates `.venv` virtual environment
- Installs dependencies from lockfiles (with hash verification)
- Installs Elspeth in editable mode
- Runs test suite to verify installation

---

## Step-by-Step Install

If you prefer manual control:

### 1. Clone Repository

```bash
git clone https://github.com/johnm-dta/elspeth.git
cd elspeth
```

### 2. Create Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

**CRITICAL**: Always install from lockfiles with hash verification (AIS compliance):

```bash
# Install development dependencies
python -m pip install -r requirements-dev.lock --require-hashes

# Install Elspeth in editable mode
python -m pip install -e . --no-deps --no-index
```

!!! warning "Never Install Unpinned Packages"
    Do NOT run `pip install -e .[dev]` directly. Always use lockfiles (`requirements*.lock`) with `--require-hashes` for security.

### 4. Verify Installation

```bash
# Run test suite
python -m pytest -m "not slow"

# Check Elspeth CLI
python -m elspeth.cli --help
```

**Expected output**:
```
usage: python -m elspeth.cli [-h] [--settings SETTINGS] [--suite-root SUITE_ROOT] ...
```

---

## Bootstrap Without Tests

If you want to skip tests during installation (faster, but not recommended):

```bash
make bootstrap-no-test
```

---

## Azure ML Integration (Optional)

For Azure ML workflows, use Azure-specific lockfiles:

```bash
# Runtime only
pip install --require-hashes -r requirements-azure.lock
pip install -e . --no-deps

# Development + Azure
python -m pip install -r requirements-dev-azure.lock --require-hashes
python -m pip install -e . --no-deps --no-index
```

**Azure dependencies**:
- `azure-identity`
- `azure-storage-blob`
- `azure-search-documents`

---

## Troubleshooting

### Python Version Issues

**Error**: `python: command not found` or wrong version

**Solution**:
```bash
# Check Python version
python3.12 --version

# Use explicit version
python3.12 -m venv .venv
```

### Lockfile Hash Verification Fails

**Error**: `THESE PACKAGES DO NOT MATCH THE HASHES`

**Solution**:
```bash
# Verify lockfile integrity
make verify-locked

# If corrupted, regenerate lockfiles (contact maintainers)
```

### Permission Denied

**Error**: `Permission denied` when installing

**Solution**:
```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Never use sudo with pip in virtual environments
```

### Tests Fail After Installation

**Error**: Some tests failing during `make bootstrap`

**Solution**:
```bash
# Run specific test to identify issue
python -m pytest tests/test_<failing>.py -v

# Check for missing dependencies
make verify-locked
```

---

## Environment Variables

Elspeth respects these environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ELSPETH_LOG_LEVEL` | Logging verbosity | `INFO` |
| `ELSPETH_CONFIG_DIR` | Configuration directory | `./config` |
| `ELSPETH_ARTIFACTS_DIR` | Artifact output directory | `./artifacts` |

**Example**:
```bash
export ELSPETH_LOG_LEVEL=DEBUG
python -m elspeth.cli --settings config/sample_suite/settings.yaml
```

---

## Next Steps

- **[Quickstart](quickstart.md)** - Run your first experiment in 5 minutes
- **[First Experiment](first-experiment.md)** - Create an experiment from scratch
- **[Configuration](../user-guide/configuration.md)** - Understand configuration files

---

## Uninstalling

To remove Elspeth:

```bash
# Deactivate virtual environment
deactivate

# Remove virtual environment
rm -rf .venv

# Remove repository (if desired)
cd .. && rm -rf elspeth
```

---

!!! tip "Production Deployments"
    For production use, see the repository's `docs/operations/` directory for containerized deployment options with signed artifacts.
