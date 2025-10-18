# syntax=docker/dockerfile:1.7

# NOTE: Pin to a specific patch tag. Digest pinning can be enabled later.
ARG PYTHON_IMAGE=python:3.12.12-slim

FROM ${PYTHON_IMAGE} AS base
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
COPY README.md README.md
COPY LICENSE LICENSE
RUN python -m pip install -e . --no-deps

FROM base AS dev
COPY --from=builder-dev /opt/venv /opt/venv
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

