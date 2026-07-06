"""XDG-standard path management for Foray.

All heavy index data lives under a central, OS-standard global directory.
It never clutters the user's working directories with hidden folders.

Layout:
    ~/.local/share/foray/
        config.json          global settings (LLM keys, workspaces, theme)
        indexes/<repo_id>/  per-repo index roots
            live/            the active SQLite index (atomically swapped)
            vectors/         ChromaDB store (mutated in place: the Rust
                             bindings cache by path, so this dir is never
                             renamed; consistency self-heals on re-index)
            .staging-<uid>/  SQLite index being built by the worker
        repos/               shallow clones for git-url imports
"""

from __future__ import annotations

import os
from pathlib import Path


def _xdg_data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve()
    return Path.home() / ".local" / "share"


def foray_home() -> Path:
    """Root data directory. FORAY_HOME overrides for tests and containers."""
    override = os.environ.get("FORAY_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return _xdg_data_home() / "foray"


def config_path() -> Path:
    return foray_home() / "config.json"


def indexes_root() -> Path:
    return foray_home() / "indexes"


def index_root(repo_id: str) -> Path:
    return indexes_root() / repo_id


_STAGING_PREFIX = ".staging"


def new_staging_dir(repo_id: str) -> Path:
    """A unique staging directory per indexing run.

    ChromaDB caches its Rust bindings by path, so every indexing run must
    use a fresh path; reusing one after its files were replaced would
    leave the bindings pointing at deleted inodes.
    """
    import uuid

    return index_root(repo_id) / f"{_STAGING_PREFIX}-{uuid.uuid4().hex[:10]}"


def staging_glob(repo_id: str) -> list[Path]:
    root = index_root(repo_id)
    if not root.is_dir():
        return []
    return sorted(root.glob(f"{_STAGING_PREFIX}-*"))


def staging_dir(repo_id: str) -> Path:
    """Legacy single staging path (tests / diagnostics only)."""
    return index_root(repo_id) / _STAGING_PREFIX


def live_dir(repo_id: str) -> Path:
    return index_root(repo_id) / "live"


def retire_dir(repo_id: str) -> Path:
    return index_root(repo_id) / ".retired"


def repos_root() -> Path:
    return foray_home() / "repos"


def ensure_layout() -> None:
    for path in (foray_home(), indexes_root(), repos_root()):
        path.mkdir(parents=True, exist_ok=True)


def sqlite_path(repo_id: str) -> Path:
    return live_dir(repo_id) / "index.sqlite"


def vectors_dir(repo_id: str) -> Path:
    """ChromaDB store. Stable path, mutated in place by the worker."""
    return index_root(repo_id) / "vectors"


# Backwards-compatible alias used by search/UI readers.
def chroma_dir(repo_id: str) -> Path:
    return vectors_dir(repo_id)


def status_path(repo_id: str) -> Path:
    """Durably-persisted worker status so SSE clients can reconnect."""
    return index_root(repo_id) / "status.json"
