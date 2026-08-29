"""Unit tests: config, paths, ignore rules, chunker, graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from foray import chunker, config, paths
from foray.graph import build_import_edges, repo_map
from foray.ignore import IgnoreRules, looks_binary


# ---------------------------------------------------------------------------
# paths & config
# ---------------------------------------------------------------------------

class TestPaths:
    def test_layout_created(self, clean_foray_home):
        paths.ensure_layout()
        assert paths.foray_home().is_dir()
        assert paths.indexes_root().is_dir()
        assert paths.repos_root().is_dir()

    def test_env_override(self, clean_foray_home, tmp_path):
        assert paths.foray_home() == tmp_path / "foray-home"


class TestConfig:
    def test_defaults_on_first_boot(self, clean_foray_home):
        cfg = config.load()
        assert cfg["theme"] in ("light", "dark")
        assert cfg["embeddings"]["engine"] == "local"
        assert cfg["embedding_choice_made"] is False
        assert cfg["workspaces"] == []

    def test_workspace_crud(self, clean_foray_home):
        ws = config.add_workspace("quill", "/tmp/quill")
        assert config.get_workspace(ws["id"])["name"] == "quill"
        config.update_workspace(ws["id"], last_sync=123.0)
        assert config.get_workspace(ws["id"])["last_sync"] == 123.0
        assert config.workspace_exists_by_path("/tmp/quill")
        assert config.remove_workspace(ws["id"]) is True
        assert config.get_workspace(ws["id"]) is None

    def test_last_workspace_prefers_recent_sync(self, clean_foray_home):
        a = config.add_workspace("a", "/tmp/a")
        b = config.add_workspace("b", "/tmp/b")
        config.update_workspace(a["id"], last_sync=100.0)
        config.update_workspace(b["id"], last_sync=200.0)
        assert config.last_workspace_id() == b["id"]

    def test_config_survives_atomic_swap(self, clean_foray_home):
        # global config must be decoupled from per-repo SQLite
        config.update_section("llm", {"api_key": "sk-test"})
        assert config.load()["llm"]["api_key"] == "sk-test"


# ---------------------------------------------------------------------------
# ignore rules
# ---------------------------------------------------------------------------

class TestIgnoreRules:
    def test_gitignore_respected(self, sample_repo):
        rules = IgnoreRules(sample_repo)
        assert rules.is_ignored("build/generated.js")
        assert rules.is_ignored("secrets.env")
        assert not rules.is_ignored("quill/parser.py")

    def test_extra_folders(self, sample_repo):
        rules = IgnoreRules(sample_repo, extra_folders=["web"])
        assert rules.is_ignored("web/main.js")
        assert rules.is_ignored("web/sub/deep.js")

    def test_binary_sniff(self, sample_repo, tmp_path):
        binary = tmp_path / "blob.bin"
        binary.write_bytes(b"\x00\x01\x02")
        assert looks_binary(binary) is True
        assert looks_binary(sample_repo / "quill" / "parser.py") is False


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_python_symbols(self):
        code = (
            "def alpha(x):\n"
            "    return x\n"
            "\n"
            "class Beta:\n"
            "    def gamma(self):\n"
            "        return 1\n"
        ).encode()
        symbols = chunker.extract_symbols(code, "python")
        names = {s.name for s in symbols}
        assert {"alpha", "Beta", "gamma"} <= names

    def test_python_chunks_cover_file(self):
        code = (Path(__file__).parent / "conftest.py").read_bytes()
        chunks = chunker.chunk_file(code, "conftest.py", "python")
        assert chunks, "expected at least one chunk"
        joined = "\n".join(c.content for c in chunks)
        assert "SAMPLE_FILES" in joined  # no code lost
        for chunk in chunks:
            assert chunk.start_line <= chunk.end_line

    def test_oversize_node_recursively_split(self):
        # one massive function: must be split without losing code
        body = "def big():\n" + "\n".join(f"    x{i} = {i}" for i in range(900))
        chunks = chunker.chunk_file(body.encode(), "big.py", "python")
        assert len(chunks) > 1
        total = sum(c.content.count("x") for c in chunks)
        assert total >= 900

    def test_typescript_structural_fallback(self):
        code = (
            "export function greet(n: string): string {\n"
            "  return n;\n"
            "}\n"
            "export class Greeter {\n"
            "  greet() { return 1; }\n"
            "}\n"
        ).encode()
        symbols = chunker.extract_symbols(code, "typescript")
        names = {s.name for s in symbols}
        assert "greet" in names and "Greeter" in names

    def test_markdown_fallback_chunking(self):
        text = "# Notes\n\n" + "\n".join(f"Line {i}" for i in range(500))
        chunks = chunker.chunk_file(text.encode(), "notes.md", "markdown")
        assert chunks
        assert all(c.content for c in chunks)

    def test_language_detection(self, sample_repo):
        assert chunker.detect_language(sample_repo / "quill" / "parser.py") == "python"
        assert chunker.detect_language(sample_repo / "web" / "main.js") == "javascript"
        assert chunker.detect_language(sample_repo / "README.md") == "markdown"
        assert chunker.language_supported("python")
        assert chunker.language_supported("rust")


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------

class TestGraph:
    def test_python_edges(self, sample_repo):
        file_set = {p.relative_to(sample_repo).as_posix() for p in sample_repo.rglob("*") if p.is_file()}
        file_set = {f for f in file_set if not f.startswith(("build/", "secrets"))}
        edges = build_import_edges(sample_repo, file_set)
        pairs = {(s, t) for s, t, _ in edges}
        assert ("quill/parser.py", "quill/blocks.py") in pairs
        assert ("quill/server.py", "quill/store.py") in pairs
        assert ("quill/server.py", "quill/parser.py") in pairs
        # no self edges
        assert all(s != t for s, t, _ in edges)

    def test_js_relative_edges(self, sample_repo):
        file_set = {p.relative_to(sample_repo).as_posix() for p in sample_repo.rglob("*") if p.is_file()}
        file_set = {f for f in file_set if not f.startswith(("build/", "secrets"))}
        edges = build_import_edges(sample_repo, file_set)
        pairs = {(s, t) for s, t, _ in edges}
        assert ("web/main.js", "web/render.js") in pairs
        assert ("web/main.js", "web/store.js") in pairs

    def test_external_packages_not_linked(self, sample_repo):
        file_set = {p.relative_to(sample_repo).as_posix() for p in sample_repo.rglob("*") if p.is_file()}
        file_set = {f for f in file_set if not f.startswith(("build/", "secrets"))}
        edges = build_import_edges(sample_repo, file_set)
        targets = {t for _, t, _ in edges}
        assert all(not t.startswith("node_modules") for t in targets)
