"""FastAPI application: API + static frontend from a single process.

Endpoints speak plain HTTP with Server-Sent Events streaming for LLM
chat tokens and indexing progress, uni-directionally from FastAPI to
the React app.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, config, db as dbmod, demo, docs_gen, llm as llmmod, paths, search
from .api_models import (
    AddWorkspaceRequest,
    ChatMessage,
    ChatRequest,
    ConfigPatch,
    EmbeddingChoice,
    FileRequest,
    SearchRequest,
)
from .indexer import get_worker

app = FastAPI(title="Foray", version=__version__, docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or request.client.host


def _require_workspace(repo_id: str) -> dict[str, Any]:
    ws = config.get_workspace(repo_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return ws


def _has_live_index(repo_id: str) -> bool:
    return (paths.live_dir(repo_id) / "index.sqlite").is_file()


def _workspace_payload(ws: dict[str, Any]) -> dict[str, Any]:
    repo_id = ws["id"]
    stats = ws.get("stats") or {}
    if _has_live_index(repo_id):
        try:
            conn = dbmod.open_index(repo_id, create=False)
            try:
                stats = dbmod.meta_get(conn, "stats", stats)
            finally:
                conn.close()
        except Exception:
            pass
    return {**ws, "stats": stats, "indexed": _has_live_index(repo_id)}


_GIT_URL_RE = re.compile(r"^(?:https?://|git@)[\w\.\-:/~]+$")


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# bootstrap & config
# ---------------------------------------------------------------------------

@app.get("/api/bootstrap")
async def bootstrap() -> dict[str, Any]:
    cfg = config.load()
    if demo.is_demo_mode():
        return demo.demo_bootstrap()

    workspaces = [_workspace_payload(ws) for ws in config.list_workspaces()]
    last_id = config.last_workspace_id()
    return {
        "demo_mode": False,
        "version": __version__,
        "repos": [],
        "embedding_choice_made": bool(cfg.get("embedding_choice_made")),
        "embeddings": {
            "engine": cfg.get("embeddings", {}).get("engine", "local"),
            "model": cfg.get("embeddings", {}).get("model", ""),
        },
        "llm": {
            "provider": cfg.get("llm", {}).get("provider", "openai"),
            "model": cfg.get("llm", {}).get("model", "gpt-4o-mini"),
            "api_base": cfg.get("llm", {}).get("api_base", ""),
            "has_key": bool(cfg.get("llm", {}).get("api_key")),
        },
        "indexing": cfg.get("indexing", {}),
        "theme": cfg.get("theme", "dark"),
        "workspaces": workspaces,
        "last_workspace_id": last_id,
        "rate_limit": None,
    }


@app.post("/api/config/embeddings")
async def set_embedding_choice(choice: EmbeddingChoice) -> dict[str, Any]:
    """First-run choice: local models (private, free) or cloud (quality, cost)."""
    if demo.is_demo_mode():
        raise HTTPException(status_code=403, detail="read-only demo mode")
    patch: dict[str, Any] = {"engine": choice.engine, "model": choice.model or "", "api_key": choice.api_key or ""}
    if choice.engine == "local" and not patch["model"]:
        patch["model"] = "BAAI/bge-small-en-v1.5"
    if choice.engine == "openai" and not patch["model"]:
        patch["model"] = "text-embedding-3-small"
    config.update_section("embeddings", patch)
    config.update(embedding_choice_made=True)
    return {"ok": True, "embeddings": config.load()["embeddings"]}


@app.put("/api/config")
async def update_config(patch: ConfigPatch) -> dict[str, Any]:
    if demo.is_demo_mode() and patch.indexing is not None:
        raise HTTPException(status_code=403, detail="read-only demo mode")
    cfg = config.load()
    if patch.theme is not None:
        if patch.theme not in ("light", "dark"):
            raise HTTPException(status_code=400, detail="theme must be light or dark")
        cfg["theme"] = patch.theme
    if patch.llm is not None:
        llm_cfg = cfg.setdefault("llm", {})
        llm_cfg.update(patch.llm.model_dump())
    if patch.indexing is not None:
        idx_cfg = cfg.setdefault("indexing", {})
        idx_cfg.update(patch.indexing.model_dump())
        if not (1 <= idx_cfg.get("max_file_size_kb", 512) <= 10240):
            raise HTTPException(status_code=400, detail="max_file_size_kb must be 1-10240")
    config.save(cfg)
    return {"ok": True}


@app.get("/api/models")
async def list_models() -> dict[str, Any]:
    return {"providers": llmmod.PROVIDER_MODELS}


# ---------------------------------------------------------------------------
# workspaces
# ---------------------------------------------------------------------------

@app.get("/api/workspaces")
async def list_workspaces() -> dict[str, Any]:
    if demo.is_demo_mode():
        return {"workspaces": [
            _demo_workspace_payload(r) for r in demo.load_demo_repos()
        ]}
    return {"workspaces": [_workspace_payload(ws) for ws in config.list_workspaces()]}


def _demo_workspace_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "name": entry["name"],
        "path": "",
        "source": "demo",
        "description": entry.get("description", ""),
        "languages": entry.get("languages", []),
        "created": 0.0,
        "last_sync": None,
        "last_index_state": "done" if _has_live_index(entry["id"]) else "missing",
        "stats": {"loc": entry.get("loc", 0), "files": 0, "chunks": 0},
        "indexed": _has_live_index(entry["id"]),
        "demo": True,
    }


@app.post("/api/workspaces")
async def add_workspace(req: AddWorkspaceRequest) -> dict[str, Any]:
    if demo.is_demo_mode():
        raise HTTPException(status_code=403, detail="read-only demo mode")

    if bool(req.path) == bool(req.git_url):
        raise HTTPException(status_code=400, detail="provide exactly one of path or git_url")

    if req.path:
        root = Path(req.path).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(status_code=400, detail=f"directory does not exist: {req.path}")
        if config.workspace_exists_by_path(root.as_posix()):
            raise HTTPException(status_code=409, detail="this repository is already indexed")
        name = req.name.strip() or root.name
        ws = config.add_workspace(name=name, path=root.as_posix(), source="local")
    else:
        url = req.git_url.strip()
        if not _GIT_URL_RE.match(url):
            raise HTTPException(status_code=400, detail="invalid git URL")
        ws = await _clone_git_repo(url, req.name.strip())

    status = await get_worker().submit(ws["id"])
    return {"workspace": _workspace_payload(ws), "status": status}


async def _clone_git_repo(url: str, name_hint: str) -> dict[str, Any]:
    """Shallow-clone into the managed XDG repos directory."""
    slug = re.sub(r"[\W_]+", "-", name_hint or url.rsplit("/", 1)[-1].removesuffix(".git")).strip("-").lower() or "repo"
    target = paths.repos_root() / f"{slug}-{int(time.time())}"
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth", "1", "--single-branch", url, str(target),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
        message = stderr.decode(errors="replace").strip().splitlines()
        detail = message[-1] if message else "clone failed"
        raise HTTPException(status_code=400, detail=f"git clone failed: {detail}")
    name = name_hint or target.name.rsplit("-", 1)[0] or slug
    return config.add_workspace(name=name, path=target.as_posix(), source="git", git_url=url)


@app.get("/api/workspaces/{repo_id}")
async def workspace_detail(repo_id: str) -> dict[str, Any]:
    if demo.is_demo_mode():
        for entry in demo.load_demo_repos():
            if entry["id"] == repo_id:
                return _demo_workspace_payload(entry)
        raise HTTPException(status_code=404, detail="workspace not found")
    ws = _require_workspace(repo_id)
    payload = _workspace_payload(ws)
    payload["status"] = get_worker().current_status(repo_id)
    return payload


@app.delete("/api/workspaces/{repo_id}")
async def delete_workspace(repo_id: str) -> dict[str, Any]:
    if demo.is_demo_mode():
        raise HTTPException(status_code=403, detail="read-only demo mode")
    ws = _require_workspace(repo_id)
    if get_worker().is_running(repo_id):
        raise HTTPException(status_code=409, detail="indexing in progress, wait or retry")
    config.remove_workspace(repo_id)
    if ws.get("source") == "git" and ws.get("path"):
        shutil.rmtree(ws["path"], ignore_errors=True)
    shutil.rmtree(paths.index_root(repo_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/workspaces/{repo_id}/sync")
async def sync_workspace(repo_id: str) -> dict[str, Any]:
    if demo.is_demo_mode():
        raise HTTPException(status_code=403, detail="read-only demo mode")
    _require_workspace(repo_id)
    if get_worker().is_running(repo_id):
        return get_worker().current_status(repo_id)
    status = await get_worker().submit(repo_id)
    return status


@app.get("/api/workspaces/{repo_id}/status")
async def workspace_status_stream(repo_id: str) -> StreamingResponse:
    """SSE stream of indexing progress. Survives UI reconnects."""
    _require_workspace(repo_id)

    async def event_stream() -> AsyncIterator[str]:
        worker = get_worker()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_update(payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, payload)

        unsubscribe = worker.subscribe(repo_id, on_update)
        yield _sse(worker.current_status(repo_id))
        try:
            timeout = 0.5
            idle = 0.0
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=timeout)
                    idle = 0.0
                except asyncio.TimeoutError:
                    idle += timeout
                    if not worker.is_running(repo_id):
                        if idle >= 1.5:
                            break
                    continue
                yield _sse(payload)
                if payload.get("state") in ("done", "error"):
                    break
        finally:
            unsubscribe()
            yield _sse(worker.current_status(repo_id))

    return StreamingResponse(event_stream(), media_type="text/event-stream")
