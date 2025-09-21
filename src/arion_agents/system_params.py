from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_system_param_defaults() -> Dict[str, str]:
    """Load optional system parameter defaults from config file.

    Returns an empty mapping when the file is absent or malformed.
    """
    path = _project_root() / "config" / "system_params_defaults.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): data[k] for k in data}
    except Exception:
        # Swallow parsing errors; callers fall back to empty defaults.
        pass
    return {}


def merge_with_defaults(system_params: Dict[str, str] | None) -> Dict[str, str]:
    defaults = load_system_param_defaults()
    result = dict(defaults)
    if system_params:
        result.update({str(k): system_params[k] for k in system_params})
    return result


def available_system_param_keys() -> Dict[str, str]:
    """Expose defaults without merging for API responses."""
    return load_system_param_defaults().copy()
