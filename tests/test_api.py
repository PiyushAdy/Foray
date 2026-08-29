"""API + chat + docs + demo-mode tests with a mock LLM stream."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from foray import config, demo


class _FakeDelta:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeStream:
    """Async-iterable stream mimicking litellm's acompletion output."""

    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._tokens):
            raise StopAsyncIteration
        token = self._tokens[self._i]
        self._i += 1
        return _FakeChunk(token)


@pytest.fixture()
def api_client(clean_foray_home, worker_reset):
    from foray.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture()
def worker_reset():
    import foray.indexer as indexer_mod

    indexer_mod.WORKER = indexer_mod.IndexWorker()
    yield
    indexer_mod.WORKER = indexer_mod.IndexWorker()


def _index_sample(client: TestClient, sample_repo: Path) -> dict:
    resp = client.post("/api/workspaces", json={"path": str(sample_repo)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    repo_id = data["workspace"]["id"]

    # wait for the background worker to finish
    deadline = time.time() + 120
    while time.time() < deadline:
        detail = client.get(f"/api/workspaces/{repo_id}").json()
        state = detail["status"]["state"]
        if state in ("done", "error"):
            assert state == "done", detail["status"]
            break
        time.sleep(0.2)
    else:
        pytest.fail("indexing timed out")
    return detail


class TestBootstrapAndConfig:
    def test_bootstrap_first_boot(self, api_client):
        data = api_client.get("/api/bootstrap").json()
        assert data["demo_mode"] is False
        assert data["embedding_choice_made"] is False
        assert data["workspaces"] == []

    def test_embedding_choice_persists(self, api_client):
        resp = api_client.post("/api/config/embeddings", json={"engine": "local"})
        assert resp.status_code == 200
        assert api_client.get("/api/bootstrap").json()["embedding_choice_made"] is True

    def test_theme_update_roundtrip(self, api_client):
        resp = api_client.put("/api/config", json={"theme": "light"})
        assert resp.status_code == 200
        assert config.load()["theme"] == "light"
        assert api_client.put("/api/config", json={"theme": "neon"}).status_code == 400

    def test_indexing_settings_validation(self, api_client):
        bad = {"indexing": {"ignore_folders": ["x"], "max_file_size_kb": 999999, "exclude_extensions": []}}
        assert api_client.put("/api/config", json=bad).status_code == 400


class TestWorkspacesApi:
    def test_add_local_workspace(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        assert detail["indexed"] is True
        assert detail["stats"]["files"] >= 9
        assert detail["name"] == "quill"

    def test_add_invalid_path(self, api_client):
        resp = api_client.post("/api/workspaces", json={"path": "/does/not/exist"})
        assert resp.status_code == 400

    def test_add_duplicate_rejected(self, api_client, sample_repo):
        assert api_client.post("/api/workspaces", json={"path": str(sample_repo)}).status_code == 200
        resp = api_client.post("/api/workspaces", json={"path": str(sample_repo)})
        assert resp.status_code == 409

    def test_add_invalid_git_url(self, api_client):
        resp = api_client.post("/api/workspaces", json={"git_url": "not a url"})
        assert resp.status_code == 400

    def test_delete_workspace(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        from foray import paths

        assert paths.index_root(repo_id).exists()
        resp = api_client.delete(f"/api/workspaces/{repo_id}")
        assert resp.status_code == 200
        assert paths.index_root(repo_id).exists() is False
        assert config.get_workspace(repo_id) is None

    def test_sync_endpoint(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        resp = api_client.post(f"/api/workspaces/{repo_id}/sync")
        assert resp.status_code == 200
        # wait for completion
        deadline = time.time() + 120
        while time.time() < deadline:
            state = api_client.get(f"/api/workspaces/{repo_id}").json()["status"]["state"]
            if state in ("done", "error"):
                break
            time.sleep(0.2)
        assert state == "done"

    def test_status_sse_stream(self, api_client, sample_repo):
        resp = api_client.post("/api/workspaces", json={"path": str(sample_repo)})
        repo_id = resp.json()["workspace"]["id"]
        with api_client.stream("GET", f"/api/workspaces/{repo_id}/status") as stream:
            events = []
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                if len(events) >= 1 and events[-1].get("state") in ("done", "error"):
                    break
                if len(events) > 500:
                    break
            assert events, "SSE stream produced no events"
            assert events[0]["state"] in ("running", "done", "queued")


class TestChatApi:
    def test_chat_requires_index(self, api_client, sample_repo):
        resp = api_client.post("/api/workspaces", json={"path": str(sample_repo)})
        repo_id = resp.json()["workspace"]["id"]
        time.sleep(0.5)
        # interrupt: delete index dir to simulate "no index yet"
        from foray import paths

        import shutil

        shutil.rmtree(paths.index_root(repo_id), ignore_errors=True)
        resp = api_client.post("/api/chat", json={"workspace_id": repo_id, "question": "hi"})
        assert resp.status_code == 409

    def test_chat_streams_tokens_and_citations(self, api_client, sample_repo, monkeypatch):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        config.update_section("llm", {"provider": "openai", "api_key": "sk-test"})

        tokens = [
            "The note store saves blocks as JSON. ",
            "See [quill/store.py:L20] for the save method ",
            "and [quill/blocks.py:L8] for the Block dataclass. ",
            "An invalid citation [ghost/file.py:L1] should be dropped. ",
        ]

        async def fake_acompletion(**kwargs: Any):
            return _FakeStream(tokens)

        import foray.llm as llmmod

        monkeypatch.setattr(llmmod.litellm, "acompletion", fake_acompletion)

        events: list[dict] = []
        with api_client.stream(
            "POST",
            "/api/chat",
            json={"workspace_id": repo_id, "question": "how are notes saved?", "history": []},
        ) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                if events and events[-1].get("type") == "done":
                    break

        types = [e["type"] for e in events]
        assert "token" in types
        done = next(e for e in events if e["type"] == "done")
        assert done["context_count"] > 0
        citation_paths = {c["path"] for c in done["citations"]}
        assert "quill/store.py" in citation_paths
        assert "quill/blocks.py" in citation_paths
        assert "ghost/file.py" not in citation_paths
        assert "[ghost/file.py:L1]" not in done["text"]  # demoted to unlinked

    def test_chat_error_without_key(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        config.update_section("llm", {"provider": "openai", "api_key": ""})

        events: list[dict] = []
        with api_client.stream(
            "POST", "/api/chat", json={"workspace_id": repo_id, "question": "hello"}
        ) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                if events and events[-1].get("type") in ("error", "done"):
                    break
        assert events[-1]["type"] == "error"
        assert "API key" in events[-1]["message"]

    def test_history_passed_to_llm(self, api_client, sample_repo, monkeypatch):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        config.update_section("llm", {"provider": "openai", "api_key": "sk-test"})
        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any):
            captured["messages"] = kwargs.get("messages")
            return _FakeStream(["ok"])

        import foray.llm as llmmod

        monkeypatch.setattr(llmmod.litellm, "acompletion", fake_acompletion)
        with api_client.stream(
            "POST",
            "/api/chat",
            json={
                "workspace_id": repo_id,
                "question": "what about blocks?",
                "history": [
                    {"role": "user", "content": "how are notes saved?"},
                    {"role": "assistant", "content": "as JSON rows."},
                ],
            },
        ) as stream:
            for line in stream.iter_lines():
                if line.startswith("data: ") and json.loads(line[6:]).get("type") == "done":
                    break
        roles = [m["role"] for m in captured["messages"]]
        assert roles == ["system", "user", "assistant", "user"]


class TestFileApi:
    def test_read_file_window(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        resp = api_client.post(
            "/api/file",
            json={"workspace_id": repo_id, "path": "quill/blocks.py", "start_line": 1, "end_line": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "python"
        assert data["start_line"] == 1
        assert data["end_line"] == 5
        # trailing newline means the 5th line is empty; split("\n") keeps it
        assert len(data["content"].split("\n")) == 5

    def test_path_traversal_blocked(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        resp = api_client.post(
            "/api/file",
            json={"workspace_id": repo_id, "path": "../../etc/passwd", "start_line": 1},
        )
        assert resp.status_code == 400


class TestDocsApi:
    def test_docs_estimate_then_generate(self, api_client, sample_repo, monkeypatch):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        config.update_section("llm", {"provider": "openai", "api_key": "sk-test"})

        resp = api_client.get(f"/api/workspaces/{repo_id}/docs")
        assert resp.status_code == 200
        assert resp.json()["docs"] is None
        assert "cost_usd" in resp.json()["estimate"]

        class _FakeResp:
            class choices:
                pass

            class message:
                content = "# Quill Notes: Onboarding\n\nEntry point at [quill/server.py:L20]."

            usage = type("U", (), {"total_tokens": 1800})()

        fake = _FakeResp()
        fake.choices = [type("C", (), {"message": type("M", (), {"content": fake.message.content})()})()]

        import foray.docs_gen as docs_mod

        monkeypatch.setattr(docs_mod.litellm, "completion", lambda **kw: fake)

        resp = api_client.post(f"/api/workspaces/{repo_id}/docs", json={})
        assert resp.status_code == 200, resp.text
        assert "Onboarding" in resp.json()["content"]

        # now cached
        cached = api_client.get(f"/api/workspaces/{repo_id}/docs").json()["docs"]
        assert cached is not None
        assert cached["content"] == fake.message.content

    def test_docs_no_llm_key_errors_cleanly(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        config.update_section("llm", {"provider": "openai", "api_key": ""})
        resp = api_client.post(f"/api/workspaces/{repo_id}/docs", json={})
        assert resp.status_code == 400
        assert "API key" in resp.json()["detail"]


class TestSearchApi:
    def test_search_endpoint(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        resp = api_client.post("/api/search", json={"workspace_id": repo_id, "query": "HTTPServer", "n": 5})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results
        assert results[0]["path"].endswith(".py")


class TestCosts:
    def test_indexing_cost_persisted(self, api_client, sample_repo):
        detail = _index_sample(api_client, sample_repo)
        repo_id = detail["id"]
        resp = api_client.get(f"/api/workspaces/{repo_id}/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["indexing"]["n"] >= 1
        assert data["indexing"]["tokens"] > 0


class TestDemoMode:
    def test_demo_readonly(self, api_client, sample_repo, monkeypatch):
        monkeypatch.setenv("FORAY_DEMO", "1")
        try:
            assert api_client.get("/api/bootstrap").json()["demo_mode"] is True
            resp = api_client.post("/api/workspaces", json={"path": str(sample_repo)})
            assert resp.status_code == 403
        finally:
            monkeypatch.delenv("FORAY_DEMO", raising=False)

    def test_demo_repos_yaml_parsed(self, clean_foray_home, tmp_path):
        yaml_file = tmp_path / "demo_repos.yaml"
        yaml_file.write_text(
            "repos:\n"
            "  - id: quill-demo\n"
            "    name: Quill Notes\n"
            "    description: Markdown notes service\n"
            "    languages: [python, javascript]\n"
            "    loc: 480\n"
        )
        import os

        os.environ["FORAY_DEMO_REPOS"] = str(yaml_file)
        try:
            repos = demo.load_demo_repos()
            assert len(repos) == 1
            assert repos[0]["id"] == "quill-demo"
            assert repos[0]["loc"] == 480
            assert "python" in repos[0]["languages"]
        finally:
            os.environ.pop("FORAY_DEMO_REPOS", None)

    def test_rate_limiter(self, clean_foray_home):
        limiter = demo.RateLimiter(max_calls=3, window=60)
        key = "visitor-1"
        assert limiter.check(key)["allowed"] is True
        assert limiter.check(key)["allowed"] is True
        assert limiter.check(key)["allowed"] is True
        blocked = limiter.check(key)
        assert blocked["allowed"] is False
        assert blocked["remaining"] == 0
        # different key unaffected
        assert limiter.check("visitor-2")["allowed"] is True

    def test_byok_sanitization(self, clean_foray_home):
        byok = {"api_key": "  sk-custom  ", "api_base": "https://relay.example/v1", "evil": "x" * 10}
        clean = demo.sanitize_byok(byok)
        assert clean == {"api_key": "sk-custom", "api_base": "https://relay.example/v1"}
        assert demo.sanitize_byok(None) == {}
        assert demo.sanitize_byok({"api_key": ""}) == {}
