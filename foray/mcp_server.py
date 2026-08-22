"""MCP Context Server: agent-spawned, stdio, silent operation.

External agents (Claude Code, Cursor) spawn this process in the
background to access search tools, read files and get the repo map,
even while the Foray Web UI is completely closed. No network ports,
no CORS issues.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastmcp import FastMCP, Context

mcp = FastMCP("Foray Context Server")


def _workspace_root(repo_id: str) -> Path:
    from . import config

    ws = config.get_workspace(repo_id)
    if ws is None:
        raise ValueError(f"unknown workspace id: {repo_id}")
    root = Path(ws["path"]).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"workspace path missing: {root}")
    return root


def _first_workspace_id() -> str:
    from . import config

    workspaces = config.list_workspaces()
    if not workspaces:
        raise ValueError(
            "no workspaces indexed yet. Run `foray start` and add a repository in the web UI first."
        )
    repo_id = os.environ.get("FORAY_WORKSPACE") or config.last_workspace_id()
    if repo_id is None or not any(ws["id"] == repo_id for ws in workspaces):
        repo_id = workspaces[0]["id"]
    return repo_id


def _require_workspace(repo_id: str) -> str:
    """Validate an explicit workspace id (agents deserve clear errors)."""
    from . import config

    if config.get_workspace(repo_id) is None:
        raise ValueError(f"unknown workspace id: {repo_id}")
    return repo_id


@mcp.tool
def list_workspaces() -> str:
    """List every indexed repository with its id, name, path and stats."""
    from . import config

    workspaces = config.list_workspaces()
    payload = [
        {
            "id": ws["id"],
            "name": ws["name"],
            "path": ws["path"],
            "last_sync": ws.get("last_sync"),
        }
        for ws in workspaces
    ]
    return json.dumps(payload, indent=2)


@mcp.tool
def search_code(query: str, repo_id: str = "", n: int = 8) -> str:
    """Hybrid semantic + keyword search over the indexed codebase.

    Returns the top matching code chunks with file path, line range and
    a relevance score.
    """
    from .search import hybrid_search

    repo = _require_workspace(repo_id) if repo_id else _first_workspace_id()
    results = hybrid_search(repo, query, n=max(1, min(n, 20)))
    if not results:
        return json.dumps({"results": [], "note": "no matches; try different terms or re-index"})
    return json.dumps(
        {
            "repo": repo,
            "results": [
                {
                    "path": r["path"],
                    "lines": f"{r['start_line']}-{r['end_line']}",
                    "score": r.get("score", 0),
                    "symbols": [s.get("name") for s in r.get("symbols", [])][:8],
                    "content": r["content"][:1500],
                }
                for r in results
            ],
        },
        indent=2,
    )


@mcp.tool
def read_file(path: str, start_line: int = 1, end_line: int = 0, repo_id: str = "") -> str:
    """Read a file from the active repository with an optional line range.

    Paths are relative to the repository root.
    """
    repo = repo_id or _first_workspace_id()
    root = _workspace_root(repo)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        return json.dumps({"error": "path escapes repository"})
    if not target.is_file():
        return json.dumps({"error": "file not found"})
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    total = len(lines)
    start = max(1, start_line)
    end = min(end_line or total, total)
    return json.dumps(
        {
            "path": path,
            "start_line": start,
            "end_line": end,
            "total_lines": total,
            "content": "\n".join(lines[start - 1 : end]),
        },
        indent=2,
    )


@mcp.tool
def get_repo_map(repo_id: str = "", max_nodes: int = 40) -> str:
    """Get the architecture map: modules, their dependency edges and the
    highest-PageRank files. Ideal for repo orientation and onboarding."""
    from . import db as dbmod, paths
    from .graph import repo_map as build_map

    repo = repo_id or _first_workspace_id()
    if not (paths.live_dir(repo) / "index.sqlite").is_file():
        return json.dumps({"error": "this repository has no live index"})
    conn = dbmod.open_index(repo, create=False)
    try:
        data = build_map(conn, max_nodes=max_nodes)
    finally:
        conn.close()
    return json.dumps(
        {
            "repo": repo,
            "stats": data["stats"],
            "modules": [
                {"id": n["id"], "files": n["files"], "loc": n["loc"]} for n in data["nodes"]
            ],
            "dependencies": [{"from": l["source"], "to": l["target"]} for l in data["links"][:80]],
            "top_files": [
                {"path": f["path"], "loc": f["loc"], "language": f["language"]}
                for f in data["top_files"][:12]
            ],
        },
        indent=2,
    )


@mcp.tool
def get_symbols(path: str, repo_id: str = "") -> str:
    """List the symbols (functions, classes, methods) defined in a file,
    with their definition line numbers."""
    import tree_sitter

    from . import chunker

    repo = repo_id or _first_workspace_id()
    root = _workspace_root(repo)
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return json.dumps({"error": "file not found"})
    lang = chunker.detect_language(target)
    if not lang or not chunker.language_supported(lang):
        return json.dumps({"error": f"unsupported language: {lang}"})
    code = target.read_bytes()
    symbols = chunker.extract_symbols(code, lang)
    return json.dumps(
        {"path": path, "language": lang, "symbols": [s.__dict__ for s in symbols]},
        indent=2,
    )


def main() -> None:
    """Entry point: `foray-mcp`. Spoken to over stdio by external agents."""
    import logging

    logging.disable(logging.CRITICAL)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
