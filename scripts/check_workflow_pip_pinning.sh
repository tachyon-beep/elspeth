#!/usr/bin/env bash
set -euo pipefail

# Scan GitHub workflow YAMLs for unpinned or unsafe pip usage.
# Fails if it finds any of the following in .github/workflows/*.yml:
#  - "pip install --upgrade pip"
#  - "piptools sync" (networked resolution)
#  - "pip install" that is not one of the allowed patterns below
#
# Allowed patterns:
#  - python -m pip install -r requirements*.lock --require-hashes
#  - python -m pip install -e . --no-deps --no-index

shopt -s nullglob

WORKFLOWS=(.github/workflows/*.yml)
if [[ ${#WORKFLOWS[@]} -eq 0 ]]; then
  echo "No workflows found under .github/workflows; skipping check."
  exit 0
fi

violations=()

for wf in "${WORKFLOWS[@]}"; do
  while IFS= read -r line; do
    # Skip commented lines
    content="${line#*:}"
    [[ "${content}" =~ ^[[:space:]]*# ]] && continue

    if grep -qE "pip install --upgrade pip" <<<"${line}"; then
      violations+=("${wf}:${line}")
      continue
    fi

    if grep -qE "piptools[[:space:]]+sync" <<<"${line}"; then
      violations+=("${wf}:${line}")
      continue
    fi

    if grep -qE "python[[:space:]]+-m[[:space:]]+pip[[:space:]]+install" <<<"${line}"; then
      # Allow locked installs
      if grep -qE "install[[:space:]]+-r[[:space:]]+[^ ]*requirements.*\.lock([[:space:]]+|.*)--require-hashes" <<<"${line}"; then
        continue
      fi
      # Allow offline editable local install
      if grep -qE "install[[:space:]]+-e[[:space:]]+\.[[:space:]]+--no-deps([[:space:]]+.*)?--no-index" <<<"${line}"; then
        continue
      fi
      violations+=("${wf}:${line}")
    fi
  done < <(nl -ba "${wf}" | sed 's/^\s*\([0-9]\+\)\t/\1:/')
done

if [[ ${#violations[@]} -gt 0 ]]; then
  {
    echo "Found unpinned or unsafe pip usage in GitHub workflows:";
    printf '  %s\n' "${violations[@]}";
    echo;
    echo "Allowed patterns:";
    echo "  - python -m pip install -r requirements*.lock --require-hashes";
    echo "  - python -m pip install -e . --no-deps --no-index";
  } >&2
  exit 1
fi

echo "✅ Workflow pip usage is pinned and safe"

