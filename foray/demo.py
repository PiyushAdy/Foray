"""Read-only demo mode + BYOK for hosted showcases.

Demo mode (FORAY_DEMO=1 or --demo):
- disables all repository additions and indexing endpoints
- reads demo_repos.yaml to decide exactly which pre-indexed
  repositories appear on the landing page
- visitors share a host API key under a strict rate limit
- power users bypass limits via BYOK (their own key + base URL,
  stored in the browser, passed per-session to LiteLLM)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import config

DEMO_ENV_VAR = "FORAY_DEMO"

DEMO_REPOS_FILENAME = "demo_repos.yaml"

RATE_LIMIT_WINDOW = 3600.0  # one hour
RATE_LIMIT_MAX = 25         # grounded-chat queries per hour for visitors


def is_demo_mode() -> bool:
    import os

    return os.environ.get(DEMO_ENV_VAR, "").lower() in ("1", "true", "yes")


def demo_repos_file() -> Path:
    import os

    override = os.environ.get("FORAY_DEMO_REPOS")
    if override:
        return Path(override).expanduser().resolve()
    # next to the package, or in the CWD
    candidates = [
        Path(__file__).resolve().parent.parent / DEMO_REPOS_FILENAME,
        Path.cwd() / DEMO_REPOS_FILENAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


def load_demo_repos() -> list[dict[str, Any]]:
    """Parse demo_repos.yaml: exact repos shown on the landing page."""
    path = demo_repos_file()
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        import yaml

        data = yaml.safe_load(text)
    except ImportError:
        return _parse_simple_yaml(text)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []
    repos = data.get("repos")
    if not isinstance(repos, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "id": str(entry.get("id", "")),
                "name": str(entry.get("name", entry.get("id", "repo"))),
                "description": str(entry.get("description", "")),
                "languages": [str(x) for x in entry.get("languages", [])][:6],
                "loc": entry.get("loc", 0),
            }
        )
    return [r for r in out if r["id"]]


def _parse_simple_yaml(text: str) -> list[dict[str, Any]]:
    """Minimal fallback parser for the fixed demo_repos.yaml shape."""
    repos: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("repos:"):
            continue
        if line.startswith("  - ") or line.startswith("- "):
            current = {}
            repos.append(current)
            body = line.split("- ", 1)[1]
            if ":" in body:
                key, value = body.split(":", 1)
                current[key.strip()] = value.strip().strip("'\"")
            continue
        if current is not None and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            current[key.strip()] = value.strip().strip("'\"")
    normalized = []
    for r in repos:
        languages = str(r.get("languages", "")).strip("[]").split(",")
        normalized.append(
            {
                "id": str(r.get("id", "")),
                "name": str(r.get("name", r.get("id", "repo"))),
                "description": str(r.get("description", "")),
                "languages": [l.strip() for l in languages if l.strip()][:6],
                "loc": int(r.get("loc", 0) or 0),
            }
        )
    return [r for r in normalized if r["id"]]


# ---------------------------------------------------------------------------
# rate limiting (in-memory, per client key)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Sliding-window limiter for the hosted demo key."""

    def __init__(self, max_calls: int = RATE_LIMIT_MAX, window: float = RATE_LIMIT_WINDOW):
        self.max_calls = max_calls
        self.window = window
        self._calls: dict[str, list[float]] = {}

    def check(self, key: str) -> dict[str, Any]:
        now = time.time()
        history = [t for t in self._calls.get(key, []) if now - t < self.window]
        allowed = len(history) < self.max_calls
        if allowed:
            history.append(now)
        self._calls[key] = history
        remaining = max(0, self.max_calls - len(history))
        reset_in = max(0, int(self.window - (now - history[0]))) if history else 0
        return {
            "allowed": allowed,
            "remaining": remaining,
            "limit": self.max_calls,
            "reset_in": reset_in,
        }


RATE_LIMITER = RateLimiter()


def rate_limit_status(client_key: str) -> dict[str, Any]:
    return RATE_LIMITER.check(client_key)


def chat_rate_limit_headers(status: dict[str, Any]) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(status["limit"]),
        "X-RateLimit-Remaining": str(status["remaining"]),
    }


# ---------------------------------------------------------------------------
# BYOK
# ---------------------------------------------------------------------------

def sanitize_byok(byok: dict[str, str] | None) -> dict[str, str]:
    """Only whitelisted fields pass through to LiteLLM; never persisted."""
    if not isinstance(byok, dict):
        return {}
    out: dict[str, str] = {}
    for key in ("api_key", "api_base"):
        value = byok.get(key)
        if isinstance(value, str) and 0 < len(value.strip()) <= 4096:
            out[key] = value.strip()
    return out


def demo_bootstrap() -> dict[str, Any]:
    """Public bootstrap payload when running as a hosted showcase."""
    cfg = config.load()
    return {
        "demo_mode": True,
        "repos": load_demo_repos(),
        "llm": {"provider": cfg.get("llm", {}).get("provider", ""), "model": cfg.get("llm", {}).get("model", "")},
        "rate_limit": {"limit": RATE_LIMIT_MAX, "window_s": int(RATE_LIMIT_WINDOW)},
    }
