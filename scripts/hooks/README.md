# Git Hooks

This directory contains git hooks that enforce quality gates before pushing code.

## Installation

To install the pre-push hook:

```bash
cp scripts/hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## Pre-Push Hook

The pre-push hook runs the following quality checks before allowing a push:

1. **Python Linting** (ruff) - Fast code style and error checking
2. **Rust Formatting** (cargo fmt --check) - Ensures Rust code follows standard formatting
3. **Rust Linting** (clippy) - Rust linter for common mistakes and improvements
4. **Python Tests** (pytest, fast subset) - Runs unit tests excluding slow/integration tests
5. **Rust Tests** (cargo test) - Runs Rust unit and integration tests

If any check fails, the push is blocked and you must fix the issues before pushing.

## Bypassing the Hook

⚠️ **NOT RECOMMENDED** - To bypass the hook in an emergency:

```bash
git push --no-verify
```

Only use this if absolutely necessary (e.g., reverting a broken commit).
