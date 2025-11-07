# Makefile for ELSPETH Sidecar Daemon
# Convenient shortcuts for common development tasks

.PHONY: help check fmt lint test security build clean install-tools all ci

# Default target - show help
help:
	@echo "ELSPETH Sidecar Daemon - Development Commands"
	@echo ""
	@echo "Quick Start:"
	@echo "  make all          - Run full CI pipeline (fmt, lint, test, security, build)"
	@echo "  make ci           - Same as 'all' (matches CI workflow)"
	@echo ""
	@echo "Individual Tasks:"
	@echo "  make check        - Type check (cargo check)"
	@echo "  make fmt          - Format code (cargo fmt)"
	@echo "  make lint         - Lint with clippy (-D warnings)"
	@echo "  make test         - Run all tests"
	@echo "  make security     - Security scan (deny + audit)"
	@echo "  make build        - Build release binary"
	@echo ""
	@echo "Tools:"
	@echo "  make install-tools  - Install cargo-deny, cargo-audit, etc."
	@echo "  make clean         - Clean build artifacts"
	@echo ""
	@echo "Development:"
	@echo "  make watch         - Auto-rebuild on file changes"
	@echo "  make bench         - Run benchmarks"
	@echo "  make doc           - Generate documentation"
	@echo ""

# Run full CI pipeline locally (matches GitHub Actions)
all: check fmt lint test security build
	@echo ""
	@echo "✅ All checks passed! Ready to commit."

ci: all

# Type checking (fastest feedback)
check:
	@echo "🔍 Type checking..."
	cargo check --all-targets --all-features

# Code formatting
fmt:
	@echo "🎨 Checking code formatting..."
	cargo fmt -- --check

# Auto-format code
fmt-fix:
	@echo "🎨 Auto-formatting code..."
	cargo fmt

# Linting with clippy (-D warnings = fail on any warning)
lint:
	@echo "🔍 Linting with clippy..."
	cargo clippy --all-targets --all-features -- -D warnings

# Auto-fix clippy warnings
lint-fix:
	@echo "🔧 Auto-fixing clippy warnings..."
	cargo clippy --fix --all-targets --allow-dirty --allow-staged

# Run all tests
test:
	@echo "🧪 Running tests..."
	cargo test --all-features --verbose

# Run tests with output visible
test-verbose:
	@echo "🧪 Running tests (verbose output)..."
	cargo test --all-features -- --nocapture

# Security checks (deny.toml + RustSec advisories)
security: security-deny security-audit

security-deny:
	@echo "🛡️  Checking licenses & security policies (deny.toml)..."
	@command -v cargo-deny >/dev/null 2>&1 || { echo "cargo-deny not installed. Run: make install-tools"; exit 1; }
	cargo deny check

security-audit:
	@echo "🛡️  Checking for CVEs (RustSec advisories)..."
	@command -v cargo-audit >/dev/null 2>&1 || { echo "cargo-audit not installed. Run: make install-tools"; exit 1; }
	cargo audit

# Build release binary
build:
	@echo "🔨 Building release binary..."
	cargo build --release
	@echo ""
	@echo "Binary location: target/release/elspeth-sidecar-daemon"
	@ls -lh target/release/elspeth-sidecar-daemon

# Build debug binary (faster compilation)
build-debug:
	@echo "🔨 Building debug binary..."
	cargo build

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	cargo clean

# Install development tools
install-tools:
	@echo "📦 Installing Rust development tools..."
	@echo "  - cargo-deny (license & security policy)"
	@echo "  - cargo-audit (CVE scanning)"
	@echo "  - cargo-watch (auto-rebuild)"
	@echo "  - cargo-geiger (unsafe code detection)"
	@echo ""
	cargo install --locked cargo-deny
	cargo install --locked cargo-audit
	cargo install --locked cargo-watch
	cargo install --locked cargo-geiger
	@echo ""
	@echo "✅ Tools installed successfully!"

# Auto-rebuild on file changes
watch:
	@echo "👀 Watching for changes (auto-rebuild)..."
	@command -v cargo-watch >/dev/null 2>&1 || { echo "cargo-watch not installed. Run: make install-tools"; exit 1; }
	cargo watch -x check -x test

# Run benchmarks
bench:
	@echo "⚡ Running benchmarks..."
	cargo bench

# Generate documentation
doc:
	@echo "📚 Generating documentation..."
	cargo doc --no-deps --open

# Dependency tree
tree:
	@echo "🌳 Dependency tree..."
	cargo tree --depth 3

# Check for duplicate dependencies
tree-duplicates:
	@echo "🔍 Checking for duplicate dependencies..."
	cargo tree -d

# Count unsafe code blocks
unsafe-audit:
	@echo "🔍 Auditing unsafe code..."
	@command -v cargo-geiger >/dev/null 2>&1 || { echo "cargo-geiger not installed. Run: make install-tools"; exit 1; }
	cargo geiger

# Update dependencies (respects deny.toml policies)
update:
	@echo "📦 Updating dependencies..."
	cargo update
	@echo ""
	@echo "⚠️  Remember to run 'make security' to check updated dependencies!"

# Pre-commit checks (recommended to run before git commit)
pre-commit: fmt-fix lint-fix test security
	@echo ""
	@echo "✅ Pre-commit checks passed!"
	@echo "   You can now commit your changes."

# Integration test with Python client (requires Python environment)
integration-test:
	@echo "🔗 Running Python ↔ Rust integration tests..."
	@echo "   Building Rust daemon..."
	@cargo build --release
	@echo "   Running Python tests..."
	@cd .. && ELSPETH_RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_sidecar_integration.py -v

# Production deployment build (with optimizations)
build-production: clean
	@echo "🚀 Building production binary (optimized)..."
	RUSTFLAGS="-C target-cpu=native" cargo build --release
	@echo ""
	@echo "Production binary: target/release/elspeth-sidecar-daemon"
	@ls -lh target/release/elspeth-sidecar-daemon
	@echo ""
	@echo "⚠️  Test thoroughly before deployment!"

# Print binary size
size:
	@echo "📊 Binary size analysis..."
	@cargo build --release >/dev/null 2>&1
	@ls -lh target/release/elspeth-sidecar-daemon
	@size target/release/elspeth-sidecar-daemon 2>/dev/null || echo "(size command not available on this platform)"
