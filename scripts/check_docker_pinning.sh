#!/usr/bin/env bash
set -euo pipefail

# Scan Dockerfiles for:
#  1) Digest-pinned base images (all FROM instructions that reference external images must include @sha256:...)
#  2) Pinned/locked pip usage (no unpinned 'pip install', no 'piptools sync')
#     Allowed pip patterns:
#       - python -m pip install -r requirements*.lock --require-hashes
#       - python -m pip install -e . --no-deps --no-index
#       - python -m pip install . --no-deps --no-index

shopt -s nullglob

mapfile -t FILES < <(find . -path './.git' -prune -o -type f -name 'Dockerfile*' -print)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No Dockerfiles found; skipping check."
  exit 0
fi

violations=()

for f in "${FILES[@]}"; do
  # Track stage names created by previous FROM ... AS <stage>
  declare -A stages
  stages=()

  while IFS= read -r raw; do
    line="${raw%%#*}"  # strip trailing comments
    [[ -z "${line//[[:space:]]/}" ]] && continue  # skip empty

    # Normalize whitespace for easier regex checks
    norm="$(echo "$line" | tr -s '[:space:]' ' ')"

    if [[ "$norm" =~ ^FROM[[:space:]]+([^[:space:]]+)([[:space:]]+AS[[:space:]]+([^[:space:]]+))? ]]; then
      image="${BASH_REMATCH[1]}"
      stage_name="${BASH_REMATCH[3]:-}"

      # If this FROM references a prior stage by name, it's fine
      if [[ -n "${image}" && -n "${stages[$image]:-}" ]]; then
        : # referencing previous stage; skip digest check
      else
        # External image must be digest-pinned
        if [[ "${image}" != *"@sha256:"* ]]; then
          violations+=("${f}: Unpinned base image in FROM: '${image}' (must include @sha256:<digest>)")
        fi
      fi

      # Record stage alias
      if [[ -n "${stage_name}" ]]; then
        stages["${stage_name}"]=1
      fi
      continue
    fi

    # Disallow piptools sync entirely
    if grep -qE "piptools[[:space:]]+sync" <<<"$norm"; then
      violations+=("${f}: Disallowed 'piptools sync' detected: ${raw}")
      continue
    fi

    # Flag pip installs unless they match allowed patterns
    if grep -qE "(pip|python -m pip)[[:space:]]+install" <<<"$norm"; then
      # Allow locked installs, regardless of option order
      allow_locked_req=$(grep -qE "install[[:space:]]+-r[[:space:]]+[^ ]*requirements.*\.lock([[:space:]]+|.*)--require-hashes" <<<"$norm" && echo 1 || echo 0)
      allow_locked_req_rev=$(grep -qE "install[[:space:]]+--require-hashes([[:space:]]+.*)?-r[[:space:]]+[^ ]*requirements.*\.lock" <<<"$norm" && echo 1 || echo 0)
      allow_editable_offline=$(grep -qE "install[[:space:]]+-e[[:space:]]+\.[[:space:]]+--no-deps([[:space:]]+.*)?--no-index" <<<"$norm" && echo 1 || echo 0)
      allow_pkg_offline=$(grep -qE "install[[:space:]]+\.[[:space:]]+--no-deps([[:space:]]+.*)?--no-index" <<<"$norm" && echo 1 || echo 0)
      if [[ $allow_locked_req -eq 0 && $allow_locked_req_rev -eq 0 && $allow_editable_offline -eq 0 && $allow_pkg_offline -eq 0 ]]; then
        violations+=("${f}: Unpinned/unsafe pip usage: ${raw}")
      fi
    fi

  done < "$f"
done

if [[ ${#violations[@]} -gt 0 ]]; then
  {
    echo "Found Dockerfile pinning violations:";
    printf '  - %s\n' "${violations[@]}";
    echo;
    echo "Required policies:";
    echo "  - All FROM external images must be digest pinned (image@sha256:<digest>).";
    echo "  - pip usage must be from locked requirements with --require-hashes or offline local installs (--no-index).";
  } >&2
  exit 1
fi

echo "✅ Dockerfile base images and pip usage are pinned and safe"
