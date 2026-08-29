"""Integration tests: full indexing pipeline, search, atomic swaps."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

from foray import config, db as dbmod, paths
from foray.indexer import get_worker


def _add_workspace(repo_path: Path, name: str = "quill") -> dict:
    return config.add_workspace(name=name, path=repo_path.as_posix(), source="local")


def _run_index(repo_id: str, timeout: float = 240.0) -> dict:
    async def runner() -> dict:
        worker = get_worker()
        await worker.submit(repo_id)
        # wait for the background task to finish
        while worker.is_running(repo_id):
            await asyncio.sleep(0.1)
        return worker.current_status(repo_id)

    return asyncio.run(asyncio.wait_for(runner(), timeout=timeout))


def _fresh_worker() -> None:
    """Reset the module-level worker between tests."""
    import foray.indexer as indexer_mod

    indexer_mod.WORKER = indexer_mod.IndexWorker()


@pytest.fixture()
def worker_reset():
    _fresh_worker()
    yield
    _fresh_worker()


class TestIndexing:
    def test_full_index_flow(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        status = _run_index(ws["id"])

        assert status["state"] == "done", status
        assert status["percent"] == 100.0
        assert status["files_total"] >= 9

        # live index exists, staging cleaned up
        live = paths.live_dir(ws["id"])
        assert (live / "index.sqlite").is_file()
        assert paths.vectors_dir(ws["id"]).is_dir()
        assert paths.staging_glob(ws["id"]) == []

        # workspace config updated
        assert config.get_workspace(ws["id"])["last_index_state"] == "done"
        assert config.get_workspace(ws["id"])["last_sync"] is not None

    def test_ignored_files_not_indexed(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        conn = dbmod.open_index(ws["id"], create=False)
        try:
            paths_indexed = {row["path"] for row in conn.execute("SELECT path FROM files")}
        finally:
            conn.close()
        assert "build/generated.js" not in paths_indexed
        assert "secrets.env" not in paths_indexed
        assert "quill/parser.py" in paths_indexed

    def test_chunks_and_fts_populated(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        conn = dbmod.open_index(ws["id"], create=False)
        try:
            chunks = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
            fts = conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
            assert chunks >= 8
            assert fts == chunks

            # symbols captured across the file's chunks
            all_symbols: list[dict] = []
            for row in conn.execute("SELECT symbols FROM chunks WHERE path = 'quill/blocks.py'").fetchall():
                all_symbols.extend(json.loads(row["symbols"]))
            names = {s["name"] for s in all_symbols}
            assert {"split_blocks", "Block"} <= names
        finally:
            conn.close()

    def test_vectors_persisted(self, sample_repo, clean_foray_home, worker_reset):
        from foray.vectorstore import VectorStore

        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        vstore = VectorStore(paths.vectors_dir(ws["id"]))
        assert vstore.count() >= 8

    def test_atomic_swap_no_stale_staging(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        _run_index(ws["id"])  # second run: rebuild via staging + swap again
        assert paths.live_dir(ws["id"]).is_dir()
        assert paths.staging_glob(ws["id"]) == []

    def test_incremental_sync_skips_unchanged(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        status1 = _run_index(ws["id"])
        chunks_before = status1["chunks_done"]

        # touch nothing: second sync should not parse any new chunks
        status2 = _run_index(ws["id"])
        assert status2["state"] == "done"
        assert status2["chunks_done"] == 0  # all files unchanged -> skipped

    def test_sync_picks_up_edits(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])

        (sample_repo / "quill" / "parser.py").write_text(
            "def brand_new_function():\n    return 'fresh'\n", encoding="utf-8"
        )
        status = _run_index(ws["id"])
        assert status["state"] == "done"
        conn = dbmod.open_index(ws["id"], create=False)
        try:
            hit = conn.execute(
                "SELECT path FROM chunks WHERE content LIKE '%brand_new_function%'"
            ).fetchone()
            assert hit is not None
        finally:
            conn.close()

    def test_ghost_files_purged(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        (sample_repo / "web" / "store.js").unlink()

        status = _run_index(ws["id"])
        assert status["state"] == "done"
        conn = dbmod.open_index(ws["id"], create=False)
        try:
            paths_indexed = {row["path"] for row in conn.execute("SELECT path FROM files")}
            assert "web/store.js" not in paths_indexed
        finally:
            conn.close()

    def test_missing_repo_errors_cleanly(self, sample_repo, clean_foray_home, worker_reset):
        ws = config.add_workspace(name="ghost", path="/nonexistent/repo", source="local")
        status = _run_index(ws["id"])
        assert status["state"] == "error"
        assert "no longer exists" in status["error"]
        assert config.get_workspace(ws["id"])["last_index_state"] == "error"

    def test_status_survives_reconnect(self, sample_repo, clean_foray_home, worker_reset):
        """Status is persisted so SSE clients can reconnect via /status."""
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])
        worker = get_worker()
        # simulate a new process: clear in-memory status
        worker.status.pop(ws["id"], None)
        restored = worker.current_status(ws["id"])
        assert restored["state"] == "done"
        assert restored["percent"] == 100.0


class TestSearch:
    def test_hybrid_search_finds_exact_symbol(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])

        from foray.search import hybrid_search

        results = hybrid_search(ws["id"], "split_blocks", n=5)
        assert results, "expected results for exact symbol name"
        assert results[0]["path"] == "quill/blocks.py"
        assert any("split_blocks" in r["content"] for r in results)

    def test_hybrid_search_semantic(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])

        from foray.search import hybrid_search

        results = hybrid_search(ws["id"], "how does the server render notes as html", n=5)
        assert results
        top_paths = {r["path"] for r in results[:5]}
        assert "quill/server.py" in top_paths or "quill/parser.py" in top_paths

    def test_fts_ranking_exact_keywords(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])

        conn = dbmod.open_index(ws["id"], create=False)
        try:
            from foray.search import _fts_search

            hits = _fts_search(conn, "HTTPServer")
            assert hits
            assert any("server.py" in h["path"] for h in hits)
        finally:
            conn.close()

    def test_search_empty_index(self, clean_foray_home):
        from foray.search import hybrid_search

        assert hybrid_search("nope", "anything") == []


class TestRepoMap:
    def test_map_structure(self, sample_repo, clean_foray_home, worker_reset):
        ws = _add_workspace(sample_repo)
        _run_index(ws["id"])

        from foray.graph import repo_map as build_map

        conn = dbmod.open_index(ws["id"], create=False)
        try:
            data = build_map(conn)
        finally:
            conn.close()

        assert data["nodes"], "expected module nodes"
        module_ids = {n["id"] for n in data["nodes"]}
        assert "quill" in module_ids
        assert data["links"], "expected dependency links"
        link_pairs = {(l["source"], l["target"]) for l in data["links"]}
        assert ("quill", "quill") not in link_pairs  # no self-module loops
        assert data["stats"]["loc"] > 100
        assert data["stats"]["files"] >= 9
