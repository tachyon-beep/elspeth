from __future__ import annotations

from typing import Any

import pandas as pd

from .common import create_signed_bundle, ensure_artifacts_dir, write_simple_artifacts


def maybe_write_artifacts_single(args: Any, settings: Any, payload: dict[str, Any], df: pd.DataFrame) -> None:
    art_base = getattr(args, "artifacts_dir", None)
    if art_base is None and not getattr(args, "signed_bundle", False):
        return
    art_dir = ensure_artifacts_dir(art_base)
    write_simple_artifacts(art_dir, "single", payload, settings)
    if getattr(args, "signed_bundle", False):
        create_signed_bundle(
            art_dir,
            "single",
            payload,
            settings,
            df,
            signing_key_env=getattr(args, "signing_key_env", "ELSPETH_SIGNING_KEY"),
        )


__all__ = ["maybe_write_artifacts_single"]

