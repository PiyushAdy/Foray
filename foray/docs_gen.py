"""Auto-generated onboarding docs, built on-demand and cached.

The guide explains the repository's core structure and entry points.
Generation happens only when the user clicks "Generate Docs" (with an
upfront cost estimate) so background syncs never trigger LLM costs.
The result is cached in the repo's SQLite database.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import litellm

from . import config, db as dbmod, paths
from .llm import litellm_model
from .search import hybrid_search

DOCS_KEY = "onboarding"

ESTIMATE_NOTE = "estimated"

DOCS_SYSTEM_PROMPT = """You are Foray's onboarding-doc generator. Write a Markdown onboarding guide for a repository using ONLY the provided repository facts and code context.

Structure the guide exactly as:
# <Repo name>: Onboarding

## What this codebase is
Two or three sentences grounded in the README/root file evidence.

## Architecture at a glance
Describe the major directories from the repo map and how they depend on each other. Cite files inline like [path/file.py:L10] using only context-provided files.

## Where to start
List the primary entry points with file:line citations and one-line explanations of what happens there.

## Key modules
A short table or list of the highest-ranked files with their responsibility, derived from the repo map.

Rules:
- Ground every statement in the provided context. No invented file names.
- Use citation badges [path:L12] referencing real context files.
- Keep it under 450 words. Plain Markdown."""


def estimate_cost(llm_settings: dict[str, Any]) -> dict[str, Any]:
    """Rough token estimate + USD estimate before generation."""
    provider = (llm_settings.get("provider") or "openai").lower()
    prompt_tokens = 7000
    output_tokens = 900
    total = prompt_tokens + output_tokens
    price: float
    if provider == "anthropic":
        price = (3.0 * prompt_tokens + 15.0 * output_tokens) / 1_000_000
    elif provider == "ollama":
        price = 0.0
    else:
        model = llm_settings.get("model") or "gpt-4o-mini"
        if "4o" in model and "mini" not in model:
            price = (2.5 * prompt_tokens + 10.0 * output_tokens) / 1_000_000
        else:
            price = (0.15 * prompt_tokens + 0.6 * output_tokens) / 1_000_000
    return {"provider": provider, "tokens": total, "cost_usd": round(price, 4), "note": ESTIMATE_NOTE}


def get_cached_docs(repo_id: str) -> dict[str, Any] | None:
    live = paths.live_dir(repo_id)
    db_file = live / "index.sqlite"
    if not db_file.is_file():
        return None
    conn = dbmod.open_index(repo_id, create=False)
    try:
        row = conn.execute("SELECT content, model, created FROM docs WHERE key = ?", (DOCS_KEY,)).fetchone()
        if row is None:
            return None
        return {"content": row["content"], "model": row["model"], "created": row["created"]}
    finally:
        conn.close()


def generate_docs(repo_id: str, byok: dict[str, str] | None = None) -> dict[str, Any]:
    """Generate + cache the onboarding guide. Synchronous (called in a thread)."""

    ws = config.get_workspace(repo_id)
    if ws is None:
        raise RuntimeError("workspace not found")
    root = Path(ws["path"]).expanduser().resolve()
    repo_name = root.name

    conn = dbmod.open_index(repo_id, create=False)
    try:
        from .graph import repo_map

        rmap = repo_map(conn)
        stats = dbmod.meta_get(conn, "stats", {})
        file_rows = conn.execute(
            "SELECT path, loc, language FROM files ORDER BY loc DESC LIMIT 40"
        ).fetchall()
    finally:
        conn.close()

    # Context: entry-point-ish files + top files
    probes = ["main", "app", "index", "cli", "server", "setup", "readme"]
    selected: list[str] = []
    for row in file_rows:
        stem = Path(row["path"]).stem.lower()
        base = Path(row["path"]).name.lower()
        if any(p in stem or p in base for p in probes):
            selected.append(row["path"])
    for f in rmap.get("top_files", []):
        if f["path"] not in selected and len(selected) < 14:
            selected.append(f["path"])

    context_parts: list[str] = []
    for path in selected[:14]:
        try:
            absolute = root / path
            if absolute.stat().st_size > 60_000:
                continue
            text = absolute.read_text(encoding="utf-8", errors="replace")
            truncated = text[:6000]
            context_parts.append(f"--- {path} ---\n{truncated}")
        except OSError:
            continue

    map_text = "\n".join(
        f"- {n['id']}: {n['files']} files, {n['loc']} lines"
        for n in rmap.get("nodes", [])[:24]
    )
    facts = (
        f"Repository: {repo_name}\n"
        f"Total files: {stats.get('files', rmap['stats']['files'])}\n"
        f"Total lines: {stats.get('loc', rmap['stats']['loc'])}\n"
        f"Top languages: {', '.join(f'{k} ({v})' for k, v in list(stats.get('languages', {}).items())[:6])}\n\n"
        f"Module map (dir, files, lines):\n{map_text}\n\n"
        f"Highest PageRank files: {', '.join(f['path'] for f in rmap.get('top_files', [])[:10])}"
    )
    user_content = f"Repository facts:\n{facts}\n\nCode context:\n\n" + "\n\n".join(context_parts)

    cfg = config.load()
    llm_settings = cfg.get("llm", {})
    provider = (llm_settings.get("provider") or "openai").lower()
    model = llm_settings.get("model") or "gpt-4o-mini"
    api_key = (byok or {}).get("api_key") or llm_settings.get("api_key") or ""
    api_base = (byok or {}).get("api_base") or llm_settings.get("api_base") or ""

    if provider in ("openai", "anthropic", "custom") and not api_key:
        raise RuntimeError(f"No API key configured for {provider}. Add one in Settings first.")

    response = litellm.completion(
        model=litellm_model(provider, model),
        messages=[
            {"role": "system", "content": DOCS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        api_key=api_key or None,
        api_base=api_base or None,
        temperature=0.3,
        max_tokens=1400,
    )
    content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", 0) or 1800
    cost = _cost_for(provider, model, tokens)

    conn = dbmod.open_index(repo_id, create=False)
    try:
        with conn:
            conn.execute(
                "INSERT INTO docs(key, content, model, created) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET content = excluded.content, model = excluded.model, created = excluded.created",
                (DOCS_KEY, content, model, time.time()),
            )
        dbmod.record_cost(conn, "docs", tokens, cost, model)
    finally:
        conn.close()

    return {"content": content, "model": model, "created": time.time(), "tokens": tokens, "cost_usd": cost}


def _cost_for(provider: str, model: str, tokens: int) -> float:
    if provider == "ollama":
        return 0.0
    if provider == "anthropic":
        return round(tokens / 1_000_000 * 9.0, 6)
    if "mini" in model or "4.1-mini" in model:
        return round(tokens / 1_000_000 * 0.4, 6)
    return round(tokens / 1_000_000 * 2.0, 6)


def invalidate_docs(repo_id: str) -> None:
    """Called after re-indexing: cached docs may reference gone files."""
    live = paths.live_dir(repo_id)
    if not (live / "index.sqlite").is_file():
        return
    conn = dbmod.open_index(repo_id, create=False)
    try:
        with conn:
            conn.execute("DELETE FROM docs WHERE key = ?", (DOCS_KEY,))
    finally:
        conn.close()
