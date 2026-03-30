"""Secret resolution helpers — tree-walk and error types.

Layer: L1 (core). Imports from L0 (contracts) only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from elspeth.contracts.secrets import ResolvedSecret, WebSecretResolver


class SecretResolutionError(Exception):
    """Raised when one or more secret refs cannot be resolved."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        names = ", ".join(missing)
        super().__init__(f"Cannot resolve secret references: {names}")


def resolve_secret_refs(
    config: dict[str, Any],
    resolver: WebSecretResolver,
    user_id: str,
) -> tuple[dict[str, Any], list[ResolvedSecret]]:
    """Walk a config dict tree and replace {"secret_ref": "NAME"} with resolved values.

    Returns (resolved_config, list_of_resolutions).
    Raises SecretResolutionError listing ALL missing refs (not one at a time).
    The returned config is a deep copy — the original is not mutated.
    """
    result = deepcopy(config)
    resolutions: list[ResolvedSecret] = []
    missing: list[str] = []
    _walk(result, resolver, user_id, resolutions, missing)
    if missing:
        raise SecretResolutionError(missing)
    return result, resolutions


def _is_secret_ref(value: Any) -> str | None:
    """If value is {"secret_ref": "NAME"}, return NAME. Else None."""
    if isinstance(value, dict) and len(value) == 1 and "secret_ref" in value:
        ref = value["secret_ref"]
        if isinstance(ref, str):
            return ref
    return None


def _walk(
    obj: Any,
    resolver: WebSecretResolver,
    user_id: str,
    resolutions: list[ResolvedSecret],
    missing: list[str],
) -> None:
    """Recursively walk and replace secret refs in-place."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            ref_name = _is_secret_ref(obj[key])
            if ref_name is not None:
                resolved = resolver.resolve(user_id, ref_name)
                if resolved is None:
                    missing.append(ref_name)
                else:
                    obj[key] = resolved.value
                    resolutions.append(resolved)
            else:
                _walk(obj[key], resolver, user_id, resolutions, missing)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            ref_name = _is_secret_ref(item)
            if ref_name is not None:
                resolved = resolver.resolve(user_id, ref_name)
                if resolved is None:
                    missing.append(ref_name)
                else:
                    obj[i] = resolved.value
                    resolutions.append(resolved)
            else:
                _walk(item, resolver, user_id, resolutions, missing)
