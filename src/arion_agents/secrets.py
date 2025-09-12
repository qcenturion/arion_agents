from __future__ import annotations

import os
from typing import Optional


def resolve_secret(secret_ref: Optional[str]) -> Optional[str]:
    if not secret_ref:
        return None
    # 1) Env var exact match
    env = os.getenv(secret_ref)
    if env:
        return env
    # 2) .secrets/<secret_ref>
    here = os.path.dirname(__file__)
    path = os.path.normpath(os.path.join(here, "..", "..", ".secrets", secret_ref))
    try:
        with open(path, "r", encoding="utf-8") as f:
            val = f.read().strip()
            return val or None
    except Exception:
        return None

