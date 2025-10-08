#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$ROOT_DIR/.venv"
PYTHON_BIN=${PYTHON_BIN:-python3}
RUN_TESTS=${RUN_TESTS:-1}

if [ ! -d "$VENV_PATH" ]; then
  echo "[bootstrap] creating virtual environment at $VENV_PATH"
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e "$ROOT_DIR"[dev]

if [ "$RUN_TESTS" != "0" ]; then
  python -m pytest
fi
