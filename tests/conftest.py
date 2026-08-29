"""Shared fixtures: a small realistic sample repository."""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest


SAMPLE_FILES: dict[str, str] = {
    ".gitignore": textwrap.dedent(
        """
        __pycache__/
        *.pyc
        .venv/
        build/
        secrets.env
        """
    ).lstrip(),
    "README.md": textwrap.dedent(
        """
        # Quill Notes

        A tiny note-taking service. Markdown in, HTML out.

        Run `python -m quill.server` and open http://localhost:7700.
        """
    ).lstrip(),
    "quill/__init__.py": '"""Quill: markdown notes service."""\n\n__version__ = "0.3.1"\n',
    "quill/parser.py": textwrap.dedent(
        '''
        """Markdown parsing primitives."""

        import re
        from quill.blocks import Block, split_blocks


        HEADING_RE = re.compile(r"^(#{1,6})\\s+(.+)$")


        class Parser:
            """Turns raw markdown text into a list of blocks."""

            def __init__(self, text: str):
                self.text = text
                self.blocks = split_blocks(text)

            def headings(self) -> list[str]:
                """Return every heading text, deepest first."""
                found = []
                for block in self.blocks:
                    match = HEADING_RE.match(block.text.splitlines()[0] if block.text else "")
                    if match:
                        found.append(match.group(2).strip())
                return found

            def to_html(self) -> str:
                parts = []
                for block in self.blocks:
                    parts.append(block.render())
                return "\\n".join(parts)


        def parse(text: str) -> Parser:
            return Parser(text)
        '''
    ).lstrip(),
    "quill/blocks.py": textwrap.dedent(
        """
        \"\"\"Block model: a note is a stream of typed blocks.\"\"\"

        from dataclasses import dataclass, field


        @dataclass
        class Block:
            kind: str
            text: str
            meta: dict = field(default_factory=dict)

            def render(self) -> str:
                if self.kind == "heading":
                    level = len(self.meta.get("marks", "#"))
                    return f"<h{level}>{self.text}</h{level}>"
                if self.kind == "code":
                    return f"<pre><code>{self.text}</code></pre>"
                return f"<p>{self.text}</p>"


        def split_blocks(text: str) -> list[Block]:
            blocks = []
            buffer: list[str] = []
            for line in text.splitlines():
                if not line.strip() and buffer:
                    blocks.append(_finish(buffer))
                    buffer = []
                else:
                    buffer.append(line)
            if buffer:
                blocks.append(_finish(buffer))
            return blocks


        def _finish(buffer: list[str]) -> Block:
            first = buffer[0].lstrip()
            if first.startswith("#"):
                return Block(kind="heading", text=first.lstrip("# ").strip(), meta={"marks": first.split()[0]})
            if first.startswith("```"):
                return Block(kind="code", text="\\n".join(buffer))
            return Block(kind="para", text="\\n".join(buffer))
        """
    ).lstrip(),
    "quill/store.py": textwrap.dedent(
        '''
        """SQLite-backed note storage."""

        import json
        import sqlite3
        from pathlib import Path

        from quill.blocks import Block


        SCHEMA = """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY,
            title TEXT,
            body TEXT
        );
        """


        class Store:
            def __init__(self, db_path: Path):
                self.conn = sqlite3.connect(db_path)
                self.conn.executescript(SCHEMA)

            def save(self, title: str, blocks: list[Block]) -> int:
                body = json.dumps([b.__dict__ for b in blocks])
                cur = self.conn.execute("INSERT INTO notes(title, body) VALUES(?,?)", (title, body))
                self.conn.commit()
                return cur.lastrowid

            def load(self, note_id: int) -> list[Block] | None:
                row = self.conn.execute("SELECT body FROM notes WHERE id = ?", (note_id,)).fetchone()
                if row is None:
                    return None
                return [Block(**b) for b in json.loads(row[0])]
        '''
    ).lstrip(),
    "quill/server.py": textwrap.dedent(
        '''
        """Tiny HTTP front-end for the note store."""

        from http.server import BaseHTTPRequestHandler, HTTPServer
        from pathlib import Path

        from quill.parser import parse
        from quill.store import Store


        class Handler(BaseHTTPRequestHandler):
            store: Store

            def do_GET(self) -> None:
                parser = parse("# Welcome\\n\\nHello **notes**.")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(parser.to_html().encode())

            def log_message(self, fmt, *args) -> None:
                pass


        def serve(port: int = 7700, db_path: str = "quill.db") -> None:
            Handler.store = Store(Path(db_path))
            server = HTTPServer(("127.0.0.1", port), Handler)
            print(f"quill listening on {port}")
            server.serve_forever()


        if __name__ == "__main__":
            serve()
        '''
    ).lstrip(),
    "web/main.js": textwrap.dedent(
        """
        import { renderNote } from './render.js';
        import { Store } from './store.js';

        const store = new Store(window.localStorage);
        const noteEl = document.getElementById('note');

        function refresh() {
          const note = store.load('scratch');
          noteEl.innerHTML = renderNote(note);
        }

        document.addEventListener('DOMContentLoaded', refresh);
        export { refresh };
        """
    ).lstrip(),
    "web/render.js": textwrap.dedent(
        """
        export function renderNote(note) {
          if (!note) return '<p class="empty">No note yet</p>';
          return note.blocks.map(b => `<section>${b.text}</section>`).join('');
        }

        export function escapeHtml(s) {
          return s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
        }
        """
    ).lstrip(),
    "web/store.js": textwrap.dedent(
        """
        export class Store {
          constructor(backend) { this.backend = backend; }
          load(key) {
            const raw = this.backend.getItem(key);
            return raw ? JSON.parse(raw) : null;
          }
          save(key, value) {
            this.backend.setItem(key, JSON.stringify(value));
          }
        }
        """
    ).lstrip(),
    "scripts/release.sh": "#!/usr/bin/env bash\nset -euo pipefail\nrm -rf dist/\nmkdir -p dist\necho 'built'\n",
    "scripts/build.py": textwrap.dedent(
        '''
        """Build script: renders the landing page with the parser."""

        from pathlib import Path

        from quill.parser import parse


        def build_index_page(notes_dir: str) -> str:
            source = Path(notes_dir) / "index.md"
            html = parse(source.read_text()).to_html()
            out = Path(notes_dir) / "index.html"
            out.write_text(html)
            return out.as_posix()
        '''
    ).lstrip(),
    "build/generated.js": "// generated artifact, must be ignored via .gitignore\nmodule.exports = {};\n",
    "secrets.env": "TOKEN=nope\n",
}


@pytest.fixture()
def sample_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "quill"
    repo.mkdir()
    for rel, content in SAMPLE_FILES.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return repo


@pytest.fixture()
def clean_foray_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "foray-home"
    home.mkdir()
    monkeypatch.setenv("FORAY_HOME", str(home))
    # reset module singletons that cache state
    from foray import config as config_mod

    config_mod._LOCK = __import__("threading").RLock()
    yield home
    shutil.rmtree(home, ignore_errors=True)
