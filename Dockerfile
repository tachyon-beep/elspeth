# syntax=docker/dockerfile:1.7

# NOTE: Default to a specific patch tag. In CI, pass a digest-pinned image via:
#   --build-arg PYTHON_IMAGE=python:3.12.12-slim@sha256:<digest>
ARG PYTHON_IMAGE=python:3.12.12-slim

FROM ${PYTHON_IMAGE} AS base
ARG PYTHON_IMAGE
# Enforce digest-pinned base image for reproducibility (CI passes a pinned digest)
RUN sh -lc 'case "${PYTHON_IMAGE}" in *@sha256:*) echo "[base] Using digest-pinned image: ${PYTHON_IMAGE}" ;; * ) echo "ERROR: PYTHON_IMAGE not digest-pinned (${PYTHON_IMAGE}). Pass --build-arg PYTHON_IMAGE=image@sha256:<digest>" >&2; exit 1 ;; esac'
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"
RUN useradd -ms /bin/bash appuser

# Create a dedicated virtualenv for isolation
RUN python -m venv /opt/venv

# ========================= DEV/TEST BUILD =========================
FROM base AS builder-dev
WORKDIR /workspace

COPY requirements-dev.lock requirements-dev.lock
COPY pyproject.toml pyproject.toml
RUN python -m pip install --upgrade pip pip-tools \
 && python -m piptools sync requirements-dev.lock

# Copy source and install package in editable mode
COPY src/ src/
COPY tests/ tests/
COPY README.md README.md
COPY LICENSE LICENSE
RUN python -m pip install -e . --no-deps

FROM base AS dev
COPY --from=builder-dev /opt/venv /opt/venv
COPY --from=builder-dev /workspace/src /workspace/src
COPY --from=builder-dev /workspace/tests /workspace/tests
COPY --from=builder-dev /workspace/README.md /workspace/README.md
COPY --from=builder-dev /workspace/LICENSE /workspace/LICENSE
USER appuser
WORKDIR /workspace

# Default command useful for CI execs
CMD ["pytest", "-m", "not slow", "--maxfail=1", "--disable-warnings"]

# ========================= RUNTIME BUILD =========================
FROM base AS builder-runtime
WORKDIR /workspace

COPY requirements.lock requirements.lock
COPY pyproject.toml pyproject.toml
RUN python -m pip install --upgrade pip pip-tools 
# Install only runtime dependencies
RUN python -m piptools sync requirements.lock

COPY src/ src/
COPY README.md README.md
COPY LICENSE LICENSE
RUN python -m pip install -e . --no-deps

FROM base AS runtime
COPY --from=builder-runtime /opt/venv /opt/venv
USER appuser
WORKDIR /workspace

# Default entrypoint for CLI usage (override as needed)
CMD ["python", "-m", "elspeth.cli", "--help"]
