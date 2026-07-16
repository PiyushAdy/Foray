"""Path exclusion: .gitignore + .forayignore via pathspec.

Build artifacts, dependency folders and logs are excluded before chunking.
User-configured extra folders and size limits apply on top.
"""

from __future__ import annotations

import os
from pathlib import Path

import pathspec

DEFAULT_IGNORE_FILES = (".gitignore", ".forayignore")

# Files that are always skipped regardless of configuration.
ALWAYS_SKIP_NAMES = {".git", ".hg", ".svn", ".staging", ".retired"}

BINARY_SNIFF_BYTES = 8000


class IgnoreRules:
    """Compiles .gitignore / .forayignore rules found in the repository root."""

    def __init__(self, repo_root: Path, extra_folders: list[str] | None = None):
        self.root = repo_root.resolve()
        self._specs: list[pathspec.GitIgnoreSpec] = []

        for name in DEFAULT_IGNORE_FILES:
            ignore_file = self.root / name
            if ignore_file.is_file():
                try:
                    text = ignore_file.read_text(encoding="utf-8", errors="replace")
                    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
                    if lines:
                        self._specs.append(pathspec.GitIgnoreSpec.from_lines("gitwildmatch", lines))
                except OSError:
                    continue

        self.extra_folders = {f.strip("/") for f in (extra_folders or []) if f}

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        rel_path = rel_path.replace(os.sep, "/")

        # a path is excluded if any of its ancestor folders is user-ignored
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            if "/".join(parts[:i]) in self.extra_folders:
                return True
        if parts[0] in self.extra_folders:
            return True

        for spec in self._specs:
            try:
                if spec.match_file(rel_path):
                    return True
                if is_dir and spec.match_file(rel_path + "/"):
                    return True
            except Exception:
                continue
        return False


def looks_binary(file_path: Path) -> bool:
    """Cheap binary sniff: NUL byte or undecodable chunk in the first 8KB."""
    try:
        with open(file_path, "rb") as fh:
            head = fh.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True
    if b"\x00" in head:
        return True
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False
