# Contributing to ELSPETH

Thanks for your interest in contributing to ELSPETH! This document covers the basics for getting started.

## Development Setup

```bash
git clone https://github.com/johnm-dta/elspeth.git && cd elspeth
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,azure]"

# Azure Blob integration tests require the Azurite emulator
npm install
```

**Important:** Use `uv` for all package management. Do not use `pip` directly.

## Running Quality Checks

All of these must pass before submitting changes:

```bash
# Tests
.venv/bin/python -m pytest tests/ -v

# Type checking
.venv/bin/python -m mypy src/

# Linting
.venv/bin/python -m ruff check src/

# Config contracts verification
.venv/bin/python -m scripts.check_contracts
```

## Code Standards

- **No defensive programming** against our own code. Access typed fields directly (`obj.field`), not defensively (`getattr(obj, "field", None)`). See [CLAUDE.md](CLAUDE.md) for the full rationale.
- **Three-tier trust model.** Handle errors differently based on data origin: crash on audit data corruption, quarantine bad user data, validate external API responses at the boundary.
- **No legacy shims or backwards compatibility.** When changing something, delete the old code completely. No deprecation wrappers, no commented-out code, no compatibility layers.
- **Test through production code paths.** Integration tests must use `ExecutionGraph.from_plugin_instances()` and `instantiate_plugins_from_config()`, not manually constructed objects.

## Commit Guidelines

- Keep commits focused on a single logical change.
- Write commit messages that explain *why*, not just *what*.
- Ensure all quality checks pass before committing.

## Reporting Issues

Open an issue on GitHub with:

- A clear description of the problem or suggestion.
- Steps to reproduce (for bugs).
- Expected vs. actual behavior.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
