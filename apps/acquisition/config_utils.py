from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data
