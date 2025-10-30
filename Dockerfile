# syntax=docker/dockerfile:1.7

# NOTE: Default to a specific patch tag. In CI, pass a digest-pinned image via:
#   --build-arg PYTHON_IMAGE=python:3.12.12-slim@sha256:<digest>
ARG PYTHON_IMAGE=python:3.12.12-slim

FROM python:3.12.12-slim@sha256:b03eed4944bc758029e0506ec41acb6a4be6d1b2b875d6e04ac4759db343a370 AS base
ARG PYTHON_IMAGE
# Enforce digest-pinned base image for reproducibility (CI passes a pinned digest)
COPY scripts/validate-digest.sh /usr/local/bin/validate-digest.sh
RUN chmod +x /usr/local/bin/validate-digest.sh \
    && /usr/local/bin/validate-digest.sh "${PYTHON_IMAGE}"
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

# Create three users for privilege separation (3-UID security model):
# - sidecar (1001): Rust daemon, owns /run/sidecar/, holds secrets
# - appuser (1000): Python orchestrator, can read session key, spawns workers
# - appplugin (1002): Plugin workers, NO access to /run/sidecar/
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    useradd -m -u 1001 -s /bin/bash sidecar && \
    useradd -m -u 1002 -s /bin/bash appplugin

# Install sudo and supervisor for multi-process management
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated virtualenv for isolation
RUN python -m venv /opt/venv

# ========================= RUST SIDECAR BUILD =========================
FROM rust:1.83-slim@sha256:540c902e99c384163b688bbd8b5b8520e94e7731b27f7bd0eaa56ae1960627ab AS rust-builder
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy Rust workspace
COPY sidecar/ sidecar/

# Build sidecar daemon in release mode and strip debug symbols
WORKDIR /build/sidecar
RUN cargo build --release --locked && \
    strip /build/sidecar/target/release/elspeth-sidecar-daemon

# Verify binary was created and report size
RUN test -f /build/sidecar/target/release/elspeth-sidecar-daemon || \
    (echo "ERROR: Sidecar binary not found at expected path" && exit 1) && \
    echo "Sidecar binary size: $(du -h /build/sidecar/target/release/elspeth-sidecar-daemon | cut -f1)"

# ========================= DEV/TEST BUILD =========================
FROM base AS builder-dev
WORKDIR /workspace

COPY requirements-dev.lock requirements-dev.lock
COPY pyproject.toml pyproject.toml
# Install dev/test dependencies strictly from the hash-locked file
RUN python -m pip install --require-hashes -r requirements-dev.lock

# Copy source and install package in editable mode
COPY src/ src/
COPY tests/ tests/
COPY scripts/ scripts/
COPY docs/ docs/
COPY README.md README.md
COPY LICENSE LICENSE
RUN python -m pip install -e . --no-deps --no-index --no-build-isolation

FROM base AS dev
COPY --from=builder-dev /opt/venv /opt/venv
COPY --from=builder-dev /workspace/src /workspace/src
COPY --from=builder-dev /workspace/tests /workspace/tests
COPY --from=builder-dev /workspace/scripts /workspace/scripts
COPY --from=builder-dev /workspace/docs /workspace/docs
COPY --from=builder-dev /workspace/README.md /workspace/README.md
COPY --from=builder-dev /workspace/LICENSE /workspace/LICENSE

# Copy Rust sidecar daemon binary and config
COPY --from=rust-builder /build/sidecar/target/release/elspeth-sidecar-daemon /usr/local/bin/elspeth-sidecar-daemon
COPY --from=rust-builder /build/sidecar/config/sidecar.toml /etc/elspeth/sidecar.toml

# Copy Docker configuration files (for testing multi-process deployment)
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/elspeth-sudoers /etc/sudoers.d/elspeth
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Set permissions
RUN chmod 0440 /etc/sudoers.d/elspeth && \
    chmod +x /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/elspeth-sidecar-daemon && \
    chown -R appuser:appuser /workspace && \
    chmod -R go+rX /workspace/src /workspace/tests /workspace/scripts

# NOTE: Do NOT set USER here - entrypoint needs root to create /run/sidecar
# Supervisord will spawn processes with correct UIDs
WORKDIR /workspace

# Default command useful for CI execs
# Note: For multi-process testing, override entrypoint
CMD ["pytest", "-m", "not slow", "--maxfail=1", "--disable-warnings"]

# ========================= RUNTIME BUILD =========================
FROM base AS builder-runtime
WORKDIR /workspace

COPY requirements.lock requirements.lock
COPY pyproject.toml pyproject.toml
# Install only runtime dependencies from the hash-locked file
RUN python -m pip install --require-hashes -r requirements.lock

COPY src/ src/
COPY README.md README.md
COPY LICENSE LICENSE
# Install the package non-editably so code is baked into site-packages
RUN python -m pip install . --no-deps --no-index --no-build-isolation

FROM base AS runtime
COPY --from=builder-runtime /opt/venv /opt/venv

# Copy Rust sidecar daemon binary and config
COPY --from=rust-builder /build/sidecar/target/release/elspeth-sidecar-daemon /usr/local/bin/elspeth-sidecar-daemon
COPY --from=rust-builder /build/sidecar/config/sidecar.toml /etc/elspeth/sidecar.toml

# Copy Docker configuration files for multi-process deployment
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/elspeth-sudoers /etc/sudoers.d/elspeth
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Set correct permissions for sudoers, entrypoint, and sidecar daemon
RUN chmod 0440 /etc/sudoers.d/elspeth && \
    chmod +x /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/elspeth-sidecar-daemon

# Create workspace directory
WORKDIR /workspace

# Default entrypoint uses supervisord for multi-process management
# For development/testing, can override with: docker run --entrypoint python
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command (can be overridden)
# Note: In supervisord mode, this is ignored. Set via ORCHESTRATOR_ARGS env var.
CMD []
