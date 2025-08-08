# utils/resolve.py
from __future__ import annotations
from typing import Any

def resolve(path: str, data: dict, default: Any | None = None, strict: bool = True):
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None if strict else default
    return cur

def ensure_path_set(data: dict, path: str, value: Any):
    cur = data
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
