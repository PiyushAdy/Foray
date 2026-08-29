"""MCP server tool tests (stdio server, tools called in-process)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foray import config


@pytest.fixture()
def worker_reset():
    import foray.indexer as indexer_mod

    indexer_mod.WORKER = indexer_mod.IndexWorker()
    yield
    indexer_mod.WORKER = indexer_mod.IndexWorker()


@pytest.fixture()
def indexed_repo(clean_foray_home, worker_reset, sample_repo):
    from foray.main import app

    with TestClient(app) as client:
        resp = client.post("/api/workspaces", json={"path": str(sample_repo)})
        assert resp.status_code == 200
        repo_id = resp.json()["workspace"]["id"]
        deadline = time.time() + 120
        while time.time() < deadline:
            state = client.get(f"/api/workspaces/{repo_id}").json()["status"]["state"]
            if state in ("done", "error"):
                break
            time.sleep(0.2)
        assert state == "done"
        yield repo_id


def _json(tool_result: str) -> dict:
    return json.loads(tool_result)


class TestMcpTools:
    def test_list_workspaces(self, indexed_repo):
        from foray.mcp_server import list_workspaces

        data = _json(list_workspaces.fn())
        assert any(ws["id"] == indexed_repo for ws in data)

    def test_search_code(self, indexed_repo):
        from foray.mcp_server import search_code

        data = _json(search_code.fn("split_blocks"))
        assert data["results"]
        assert data["results"][0]["path"] == "quill/blocks.py"

    def test_read_file(self, indexed_repo):
        from foray.mcp_server import read_file

        data = _json(read_file.fn("quill/blocks.py", start_line=1, end_line=4))
        assert data["path"] == "quill/blocks.py"
        assert "Block model" in data["content"]
        assert data["total_lines"] > 4

    def test_read_file_blocks_traversal(self, indexed_repo):
        from foray.mcp_server import read_file

        data = _json(read_file.fn("../../etc/passwd"))
        assert "error" in data

    def test_get_repo_map(self, indexed_repo):
        from foray.mcp_server import get_repo_map

        data = _json(get_repo_map.fn())
        assert data["stats"]["files"] >= 9
        assert any(m["id"] == "quill" for m in data["modules"])

    def test_get_symbols(self, indexed_repo):
        from foray.mcp_server import get_symbols

        data = _json(get_symbols.fn("quill/parser.py"))
        names = {s["name"] for s in data["symbols"]}
        assert "Parser" in names
        assert "parse" in names

    def test_unknown_workspace_id(self, indexed_repo):
        from foray.mcp_server import search_code

        with pytest.raises(ValueError):
            search_code.fn("query", repo_id="missing")

    def test_no_workspaces_registered(self, clean_foray_home, worker_reset, monkeypatch):
        monkeypatch.setenv("FORAY_WORKSPACE", "")
        from foray import mcp_server

        with pytest.raises(ValueError, match="no workspaces indexed"):
            mcp_server._first_workspace_id()
