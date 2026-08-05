"""Serialized background indexing worker with atomic swaps.

Concurrency pattern:
- A single asyncio worker owns indexing jobs; closing the browser never
  aborts an index. The React UI reconnects to the SSE /status stream.
- Incremental sync via SHA-256 hashing skips unmodified files.
- Ghost files (DB records whose files vanished from disk) are purged
  before writing.
- The new index is built in a hidden .staging/ directory, then atomically
  renamed to live/ to prevent SQLite locks and corruption.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import chunker, config, db as dbmod, paths
from .embeddings import EmbeddingError, build_embedder
from .vectorstore import VectorStore, new_chunk_id

_EMBED_BATCH = 32


@dataclass
class IndexStatus:
    state: str = "idle"  # idle | running | done | error
    phase: str = ""
    percent: float = 0.0
    files_total: int = 0
    files_done: int = 0
    chunks_done: int = 0
    embed_done: int = 0
    error: str = ""
    started: float = 0.0
    finished: float = 0.0
    workspace_id: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "phase": self.phase,
            "percent": round(self.percent, 1),
            "files_total": self.files_total,
            "files_done": self.files_done,
            "chunks_done": self.chunks_done,
            "embed_done": self.embed_done,
            "error": self.error,
            "workspace_id": self.workspace_id,
            "detail": self.detail,
            "elapsed": round((self.finished or time.time()) - self.started, 1) if self.started else 0,
        }


class IndexWorker:
    """One job at a time; jobs survive browser disconnects."""

    def __init__(self) -> None:
        self._jobs: dict[str, asyncio.Task] = {}
        self.status: dict[str, IndexStatus] = {}  # repo_id -> status
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    # -- lifecycle ---------------------------------------------------------

    def is_running(self, repo_id: str) -> bool:
        task = self._jobs.get(repo_id)
        return task is not None and not task.done()

    def current_status(self, repo_id: str) -> dict[str, Any]:
        status = self.status.get(repo_id)
        if status is None:
            status = self._load_persisted(repo_id)
        return status.to_dict() if status else {"state": "idle"}

    def subscribe(self, repo_id: str, cb: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._subscribers.setdefault(repo_id, []).append(cb)

        def unsub() -> None:
            try:
                self._subscribers[repo_id].remove(cb)
            except (KeyError, ValueError):
                pass

        return unsub

    def _emit(self, repo_id: str, status: IndexStatus) -> None:
        self.status[repo_id] = status
        payload = status.to_dict()
        for cb in list(self._subscribers.get(repo_id, [])):
            try:
                cb(payload)
            except Exception:
                pass

    def _persist(self, repo_id: str, status: IndexStatus) -> None:
        try:
            p = paths.status_path(repo_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(status.to_dict()))
        except OSError:
            pass

    def _load_persisted(self, repo_id: str) -> IndexStatus | None:
        try:
            p = paths.status_path(repo_id)
            if p.is_file():
                data = json.loads(p.read_text())
                status = IndexStatus()
                for key, value in data.items():
                    if key == "elapsed":
                        continue
                    setattr(status, key, value)
                if status.state == "running":
                    # process restarted mid-job: mark interrupted
                    status.state = "error"
                    status.error = "indexing interrupted by server restart"
                    status.finished = time.time()
                return status
        except (OSError, json.JSONDecodeError):
            return None
        return None

    # -- job entry ----------------------------------------------------------

    async def submit(self, repo_id: str) -> dict[str, Any]:
        async with self._lock:
            if self.is_running(repo_id):
                return self.current_status(repo_id)
            status = IndexStatus(state="running", phase="queued", workspace_id=repo_id, started=time.time())
            self._persist(repo_id, status)
            self._emit(repo_id, status)
            task = asyncio.create_task(self._run(repo_id))
            self._jobs[repo_id] = task
            return status.to_dict()

    async def _run(self, repo_id: str) -> None:
        status = IndexStatus(state="running", workspace_id=repo_id, started=time.time())
        try:
            await asyncio.to_thread(self._index_sync, repo_id, status)
            status.state = "done"
            status.phase = "done"
            status.percent = 100.0
            status.finished = time.time()
            config.update_workspace(repo_id, last_sync=time.time(), last_index_state="done")
        except asyncio.CancelledError:
            status.state = "error"
            status.error = "indexing cancelled"
            status.finished = time.time()
            config.update_workspace(repo_id, last_index_state="error")
        except Exception as exc:  # noqa: BLE001
            status.state = "error"
            status.error = str(exc)
            status.finished = time.time()
            config.update_workspace(repo_id, last_index_state="error")
        finally:
            self._persist(repo_id, status)
            self._emit(repo_id, status)
            self._jobs.pop(repo_id, None)
            self._cleanup_staging(repo_id)

    def _cleanup_staging(self, repo_id: str) -> None:
        for d in paths.staging_glob(repo_id):
            shutil.rmtree(d, ignore_errors=True)

    # -- core sync work ------------------------------------------------------

    def _index_sync(self, repo_id: str, status: IndexStatus) -> None:
        ws = config.get_workspace(repo_id)
        if ws is None:
            raise RuntimeError("workspace not found")
        root = Path(ws["path"]).expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(f"repository path no longer exists: {root}")

        cfg = config.load()
        idx_cfg = cfg.get("indexing", {})
        emb_cfg = cfg.get("embeddings", {})
        embedder = build_embedder(emb_cfg)
        cloud_cost = getattr(embedder, "estimated_cost", lambda: 0.0)

        # Unique staging dir per run for the SQLite index; the atomic swap
        # renames it to live/ at the end. Vector data lives at a stable
        # vectors/ path (chromadb caches Rust bindings by path and must
        # never see its files replaced), mutated in place and reconciled.
        staging = paths.new_staging_dir(repo_id)
        live = paths.live_dir(repo_id)
        vectors = paths.vectors_dir(repo_id)
        for stale in paths.staging_glob(repo_id):
            shutil.rmtree(stale, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

        # Seed staging sqlite from live for incremental sync (fresh = empty).
        live_db = live / "index.sqlite"
        if live_db.is_file():
            status.phase = "clone"
            status.detail = "preparing incremental staging"
            shutil.copy2(live_db, staging / "index.sqlite")
            for side in ("index.sqlite-wal", "index.sqlite-shm"):
                side_file = live / side
                if side_file.is_file():
                    shutil.copy2(side_file, staging / side)
        else:
            status.phase = "scan"
            status.detail = "fresh index"

        conn = dbmod.connect(staging / "index.sqlite")
        dbmod.init_schema(conn)
        vstore = VectorStore(vectors)

        from .ignore import IgnoreRules, looks_binary

        rules = IgnoreRules(root, extra_folders=idx_cfg.get("ignore_folders", []))
        max_bytes = int(idx_cfg.get("max_file_size_kb", 512)) * 1024
        exclude_ext = set(idx_cfg.get("exclude_extensions", []))

        # -- phase 1: scan + ghost purge ------------------------------------
        status.phase = "scan"
        self._emit(repo_id, status)
        disk_files: list[Path] = []
        for dirpath, dirnames, filenames in os_walk(root):
            rel_dir = Path(dirpath).relative_to(root)
            kept_dirs: list[str] = []
            for d in dirnames:
                rel = (rel_dir / d).as_posix() if str(rel_dir) != "." else d
                if d in {"__pycache__", ".git"} or rules.is_ignored(rel, is_dir=True):
                    continue
                kept_dirs.append(d)
            dirnames[:] = kept_dirs
            for fname in filenames:
                rel = (rel_dir / fname).as_posix() if str(rel_dir) != "." else fname
                if rules.is_ignored(rel):
                    continue
                if Path(fname).suffix.lower() in exclude_ext and Path(fname).name.lower() not in _FILENAME_EXEMPT:
                    continue
                disk_files.append(root / rel)

        status.files_total = len(disk_files)
        status.percent = 4.0
        self._emit(repo_id, status)

        # purge ghost files: DB rows with no on-disk counterpart
        disk_rel = {p.relative_to(root).as_posix() for p in disk_files}
        db_paths = {row["path"] for row in conn.execute("SELECT path FROM files")}
        ghosts = [p for p in db_paths if p not in disk_rel]
        if ghosts:
            status.detail = f"purging {len(ghosts)} ghost files"
            self._emit(repo_id, status)
            for gpath in ghosts:
                conn.execute("DELETE FROM files WHERE path = ?", (gpath,))
                conn.execute("DELETE FROM chunks_fts WHERE path = ?", (gpath,))
                conn.execute("DELETE FROM chunks WHERE path = ?", (gpath,))
            conn.commit()
            vstore.delete_by_paths(ghosts)

        # -- phase 2: parse & hash ------------------------------------------
        conn.execute("BEGIN IMMEDIATE")
        try:
            pending_files: list[Path] = []
            for i, fpath in enumerate(disk_files):
                rel = fpath.relative_to(root).as_posix()
                try:
                    raw = fpath.read_bytes()
                except OSError:
                    continue
                if len(raw) > max_bytes or (raw and looks_binary(fpath)):
                    continue
                file_hash = hashlib.sha256(raw).hexdigest()
                prev = conn.execute("SELECT hash, chunk_count, loc FROM files WHERE path = ?", (rel,)).fetchone()
                if prev is not None and prev["hash"] == file_hash:
                    status.files_done += 1
                    continue  # unmodified, skip

                if prev is not None:
                    conn.execute("DELETE FROM chunks_fts WHERE path = ?", (rel,))
                    conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
                    vstore.delete_by_paths([rel])

                lang = chunker.detect_language(fpath)
                chunks = chunker.chunk_file(raw, rel, lang or "text") if lang else []
                loc = raw.count(b"\n") + 1
                conn.execute(
                    "INSERT OR REPLACE INTO files(path, hash, size, loc, language, chunk_count, indexed_at) VALUES(?,?,?,?,?,?,?)",
                    (rel, file_hash, len(raw), loc, lang, len(chunks), time.time()),
                )
                for chunk in chunks:
                    cid = new_chunk_id()
                    symbols_json = json.dumps([s.__dict__ for s in chunk.symbols])
                    conn.execute(
                        "INSERT INTO chunks(chunk_id, path, start_line, end_line, language, symbols, content, token_est) VALUES(?,?,?,?,?,?,?,?)",
                        (cid, chunk.path, chunk.start_line, chunk.end_line, chunk.language, symbols_json, chunk.content, chunk.token_est),
                    )
                    conn.execute(
                        "INSERT INTO chunks_fts(content, path, symbols_text) VALUES(?,?,?)",
                        (chunk.content, chunk.path, chunker.symbols_text(chunk.symbols)),
                    )
                pending_files.append(fpath)
                status.files_done += 1
                status.chunks_done += len(chunks)
                if i % 25 == 0:
                    status.percent = 4.0 + 41.0 * (i + 1) / max(1, len(disk_files))
                    self._emit(repo_id, status)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        conn.commit()

        # -- phase 3: embed ---------------------------------------------------
        status.phase = "embed"
        status.detail = "generating embeddings"
        status.percent = 46.0
        self._emit(repo_id, status)

        rows = conn.execute(
            "SELECT chunk_id, path, start_line, end_line, language, symbols, content, token_est FROM chunks"
        ).fetchall()
        existing_ids = self._existing_vector_ids(vstore)
        to_embed = [r for r in rows if r["chunk_id"] not in existing_ids]

        for start in range(0, len(to_embed), _EMBED_BATCH):
            batch = to_embed[start : start + _EMBED_BATCH]
            texts = [self._embed_text(row) for row in batch]
            vectors = embedder.embed_sync(texts)
            ids = [row["chunk_id"] for row in batch]
            documents = [row["content"][:4000] for row in batch]
            metadatas = []
            for row in batch:
                meta: dict[str, Any] = {
                    "path": row["path"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "language": row["language"] or "text",
                }
                try:
                    names = [s["name"] for s in json.loads(row["symbols"] or "[]")][:24]
                except (json.JSONDecodeError, KeyError, TypeError):
                    names = []
                if names:  # chroma rejects empty metadata values
                    meta["symbols"] = " ".join(names)
                metadatas.append(meta)
            vstore.upsert(ids, vectors, documents, metadatas)
            status.embed_done += len(batch)
            status.percent = 46.0 + 44.0 * (status.embed_done / max(1, len(to_embed)))
            self._emit(repo_id, status)

        # reconcile: drop vectors whose chunks are gone from the new index
        # (self-heals any interrupted earlier run)
        valid_ids = {row["chunk_id"] for row in rows}
        orphan_ids = [cid for cid in existing_ids if cid not in valid_ids]
        if orphan_ids:
            try:
                vstore._collection.delete(ids=orphan_ids)
            except Exception:
                pass
        # record indexing cost (permanently, in the repo's SQLite)
        tokens_est = sum(row["token_est"] for row in rows)
        cost_usd = cloud_cost() if hasattr(embedder, "estimated_cost") else 0.0
        detail = f"local:{embedder.model_name}" if isinstance(embedder, object) and hasattr(embedder, "model_name") else "local"
        dbmod.record_cost(conn, "indexing", tokens_est, cost_usd, detail)

        # -- phase 4: import graph -------------------------------------------
        status.phase = "graph"
        status.percent = 91.0
        status.detail = "building dependency graph"
        self._emit(repo_id, status)
        graph_edges = self._build_edges(root, disk_rel)
        with conn:
            conn.execute("DELETE FROM edges")
            conn.executemany("INSERT INTO edges(source, target, kind) VALUES(?,?,?)", graph_edges)

        stats = {
            "files": status.files_total,
            "indexed_files": status.files_done,
            "chunks": status.chunks_done,
            "loc": conn.execute("SELECT COALESCE(SUM(loc),0) FROM files").fetchone()[0],
            "languages": conn.execute(
                "SELECT language, COUNT(*) AS n FROM files WHERE language IS NOT NULL GROUP BY language ORDER BY n DESC LIMIT 12"
            ).fetchall() and {r["language"]: r["n"] for r in conn.execute(
                "SELECT language, COUNT(*) AS n FROM files WHERE language IS NOT NULL GROUP BY language ORDER BY n DESC LIMIT 12"
            ).fetchall()},
            "tokens_est": tokens_est,
        }
        dbmod.meta_set(conn, "stats", stats)
        dbmod.meta_set(conn, "embed_model", getattr(embedder, "model_name", "local"))
        conn.commit()

        # -- phase 5: atomic swap ---------------------------------------------
        status.phase = "finalize"
        status.percent = 97.0
        status.detail = "activating index"
        self._emit(repo_id, status)
        conn.close()
        retired = paths.retire_dir(repo_id)
        shutil.rmtree(retired, ignore_errors=True)
        if live.exists():
            live.rename(retired)
        staging.mkdir(parents=True, exist_ok=True)
        staging.rename(live)
        shutil.rmtree(retired, ignore_errors=True)
        # vectors/ stays in place at index root

    def _existing_vector_ids(self, vstore: VectorStore) -> set[str]:
        try:
            got = vstore._collection.get(include=[])  # ids only
            return set(got["ids"] or [])
        except Exception:
            return set()

    def _embed_text(self, row: Any) -> str:
        header = f"File: {row['path']}"
        if row["symbols"]:
            try:
                names = " ".join(s["name"] for s in json.loads(row["symbols"])[:24])
                header = f"File: {row['path']}\nSymbols: {names}"
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return f"{header}\n```\n{row['content'][:3500]}\n```"

    # -- import graph ---------------------------------------------------------

    def _build_edges(self, root: Path, disk_rel: set[str]) -> list[tuple[str, str, str]]:
        from .graph import build_import_edges

        return build_import_edges(root, disk_rel)


def os_walk(root: Path):
    import os

    return os.walk(root)


_FILENAME_EXEMPT = {".gitignore", ".forayignore", "dockerfile", "makefile", "cmakelists.txt"}


# module-level singleton
WORKER = IndexWorker()


def get_worker() -> IndexWorker:
    return WORKER
