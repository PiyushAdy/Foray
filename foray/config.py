"""Global configuration, decoupled from per-repo SQLite indexes.

Settings live in ~/.local/share/foray/config.json so an atomic index swap
never touches user preferences (LLM keys, theme, known workspaces).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import paths

_LOCK = threading.RLock()

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "theme": "dark",
    "llm": {
        # provider: openai | anthropic | ollama | custom
        "provider": "openai",
        "api_key": "",
        "api_base": "",
        "model": "gpt-4o-mini",
        # model choices offered in settings for each provider
    },
    "embeddings": {
        # engine: local (fastembed) | openai (cloud)
        "engine": "local",
        "model": "BAAI/bge-small-en-v1.5",
        "api_key": "",
    },
    "embedding_choice_made": False,
    "indexing": {
        "ignore_folders": ["node_modules", ".venv", "venv", "dist", "build", "target", "__pycache__", ".git"],
        "max_file_size_kb": 512,
        "exclude_extensions": [".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".so", ".dll", ".exe", ".bin", ".woff", ".woff2", ".ttf", ".mp4", ".mp3", ".lock"],
    },
    "workspaces": [],
}


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def load() -> dict[str, Any]:
    """Load config merged over defaults (defaults fill missing keys)."""
    with _LOCK:
        raw = _read_raw(paths.config_path())
    merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    for key, value in raw.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save(cfg: dict[str, Any]) -> None:
    with _LOCK:
        paths.ensure_layout()
        tmp = paths.config_path().with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, sort_keys=True)
        tmp.replace(paths.config_path())


def update(**patch: Any) -> dict[str, Any]:
    """Shallow-merge patch into the top-level config and persist."""
    cfg = load()
    cfg.update(patch)
    save(cfg)
    return cfg


def update_section(section: str, patch: dict[str, Any]) -> dict[str, Any]:
    cfg = load()
    base = cfg.get(section) or {}
    if isinstance(base, dict):
        base.update(patch)
        cfg[section] = base
    else:
        cfg[section] = patch
    save(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Workspace registry helpers
# ---------------------------------------------------------------------------

def list_workspaces() -> list[dict[str, Any]]:
    return load().get("workspaces", [])


def get_workspace(repo_id: str) -> dict[str, Any] | None:
    for ws in list_workspaces():
        if ws.get("id") == repo_id:
            return ws
    return None


def workspace_exists_by_path(path: str) -> bool:
    return any(ws.get("path") == path for ws in list_workspaces())


def add_workspace(name: str, path: str, source: str = "local", git_url: str = "") -> dict[str, Any]:
    cfg = load()
    ws = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "path": path,
        "source": source,
        "git_url": git_url,
        "created": time.time(),
        "last_sync": None,
        "last_index_state": "pending",
        "stats": {},
    }
    cfg.setdefault("workspaces", []).append(ws)
    save(cfg)
    return ws


def update_workspace(repo_id: str, **patch: Any) -> dict[str, Any] | None:
    cfg = load()
    for ws in cfg.get("workspaces", []):
        if ws.get("id") == repo_id:
            ws.update(patch)
            save(cfg)
            return ws
    return None


def remove_workspace(repo_id: str) -> bool:
    cfg = load()
    before = len(cfg.get("workspaces", []))
    cfg["workspaces"] = [ws for ws in cfg.get("workspaces", []) if ws.get("id") != repo_id]
    save(cfg)
    return len(cfg["workspaces"]) < before


def last_workspace_id() -> str | None:
    workspaces = list_workspaces()
    if not workspaces:
        return None
    # most recently synced, otherwise most recently created
    synced = [ws for ws in workspaces if ws.get("last_sync")]
    pool = synced or workspaces
    return max(pool, key=lambda ws: ws.get("last_sync") or ws.get("created") or 0).get("id")
