"""AST-aware chunking and symbol extraction via tree-sitter.

Uses the tree-sitter-language-pack: 371 bundled grammars with
community-authored tags.scm queries, so 100+ languages work out of
the box with no two-tier fallback for symbol extraction.

Chunking strategy (hybrid):
1. Chunk by top-level AST nodes (definitions, declarations, statements).
2. If a node exceeds the embedding token budget, recursively split it
   with a character text splitter so no code is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter
from tree_sitter_language_pack import get_language, get_parser, get_tags_query

# node types that represent a definition/declaration across grammars
_DEFINITION_NODE_HINTS = {
    "function_definition", "function_declaration", "method_definition", "method_declaration",
    "class_definition", "class_declaration", "class_specifier",
    "interface_declaration", "trait_declaration", "struct_declaration", "struct_item",
    "enum_declaration", "enum_item", "impl_item", "module_declaration", "module_definition",
    "namespace_declaration", "type_declaration", "type_definition", "type_spec",
    "export_statement", "lexical_declaration", "variable_declaration", "const_declaration",
    "function_item", "macro_definition", "rule_clause", "expression_case",
}

_TOKEN_BUDGET = 3800          # hard character budget proxy for embedding token limit
_MIN_CHUNK_CHARS = 40         # tiny fragments merge with their neighbors


@dataclass
class Symbol:
    kind: str      # function | class | method | interface | struct | enum | ...
    name: str
    line: int


@dataclass
class Chunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    language: str
    content: str
    symbols: list[Symbol] = field(default_factory=list)

    @property
    def token_est(self) -> int:
        return max(1, len(self.content) // 4)

    def to_row(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "content": self.content,
            "symbols": [s.__dict__ for s in self.symbols],
            "token_est": self.token_est,
        }


# ---------------------------------------------------------------------------
# language detection
# ---------------------------------------------------------------------------

EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".swift": "swift", ".m": "objc", ".mm": "objc",
    ".scala": "scala", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".lua": "lua", ".pl": "perl", ".r": "r", ".jl": "julia", ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang", ".hs": "haskell", ".ml": "ocaml", ".clj": "clojure", ".dart": "dart",
    ".zig": "zig", ".nim": "nim", ".v": "verilog", ".sv": "verilog", ".sql": "sql",
    ".proto": "proto", ".graphql": "graphql", ".vue": "vue", ".svelte": "svelte",
    ".html": "html", ".css": "css", ".scss": "scss", ".less": "less",
    ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".tf": "hcl", ".dockerfile": "dockerfile", "Dockerfile": "dockerfile",
    ".cmake": "cmake", ".makefile": "make", "Makefile": "make",
}

_FILENAME_LANGUAGE = {
    "dockerfile": "dockerfile", "makefile": "make", "gnumakefile": "make",
    "cmakelists.txt": "cmake", "justfile": "make",
}

LANGUAGE_SUPPORTED_CACHE: dict[str, bool] = {}


def detect_language(path: Path) -> str | None:
    name = path.name.lower()
    if name in _FILENAME_LANGUAGE:
        return _FILENAME_LANGUAGE[name]
    ext = path.suffix.lower()
    return EXTENSION_LANGUAGE.get(ext)


def language_supported(lang: str) -> bool:
    if lang not in LANGUAGE_SUPPORTED_CACHE:
        try:
            get_language(lang)
            LANGUAGE_SUPPORTED_CACHE[lang] = True
        except Exception:
            LANGUAGE_SUPPORTED_CACHE[lang] = False
    return LANGUAGE_SUPPORTED_CACHE[lang]


# ---------------------------------------------------------------------------
# symbol extraction
# ---------------------------------------------------------------------------

def _symbol_from_node(node: tree_sitter.Node, kind: str) -> Symbol | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        for child in node.children:
            if child.is_named and child.child_count == 0 and child.type in (
                "identifier", "property_identifier", "type_identifier", "field_identifier",
                "variable_name", "constant", "name", "word", "atom", "symbol",
            ):
                name_node = child
                break
    if name_node is None:
        for child in node.children:
            if child.is_named and child.child_count == 0:
                name_node = child
                break
    if name_node is None:
        return None
    name = name_node.text.decode("utf-8", errors="replace").strip()
    if not name or len(name) > 200 or "\n" in name:
        return None
    kind_clean = kind.split(".")[-1]
    return Symbol(kind=kind_clean, name=name, line=node.start_point.row + 1)


def extract_symbols(code: bytes, lang: str) -> list[Symbol]:
    """Extract symbols: bundled tags.scm query first, structural walk fallback.

    Both paths run per-file on fresh trees, so the extractor is stateless
    and safe across the worker and MCP server processes.
    """
    symbols: list[Symbol] = []
    seen: set[tuple[str, int]] = set()
    try:
        language = get_language(lang)
        query_src = get_tags_query(lang)
        if query_src:
            query = tree_sitter.Query(language, query_src)
            tree = get_parser(lang).parse(code)
            captures = tree_sitter.QueryCursor(query).captures(tree.root_node)
            for capture_name, nodes in captures.items():
                if not capture_name.startswith("definition."):
                    continue
                for node in nodes:
                    sym = _symbol_from_node(node, capture_name)
                    if sym and (sym.name, sym.line) not in seen:
                        seen.add((sym.name, sym.line))
                        symbols.append(sym)
    except Exception:
        pass

    if symbols:
        symbols.sort(key=lambda s: s.line)
        return symbols

    # Structural fallback: walk the AST for definition-like nodes.
    # Covers grammars whose tags.scm is sparse (e.g. some TypeScript shapes).
    try:
        tree = get_parser(lang).parse(code)
    except Exception:
        return []

    def walk(node: tree_sitter.Node) -> None:
        if node.type in _DEFINITION_NODE_HINTS and (node.start_point.row + 1, node.type) not in seen:
            kind = "declaration"
            for part in node.type.split("_"):
                if part in ("function", "method", "class", "interface", "struct", "enum", "module", "type", "impl"):
                    kind = part
                    break
            sym = _symbol_from_node(node, f"definition.{kind}")
            if sym and (sym.name, sym.line) not in seen:
                seen.add((sym.name, sym.line))
                symbols.append(sym)
        for child in node.children:
            if child.is_named:
                walk(child)

    walk(tree.root_node)
    symbols.sort(key=lambda s: s.line)
    return symbols


# ---------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------

def _line_of(code: bytes, byte_offset: int) -> int:
    return code[:byte_offset].count(b"\n") + 1


def _top_level_segments(tree: tree_sitter.Tree, code: bytes) -> list[tuple[int, int, int, int]]:
    """Segments as (start_byte, end_byte, start_line, end_line)."""
    segments: list[tuple[int, int, int, int]] = []
    for child in tree.root_node.children:
        if child.end_byte - child.start_byte == 0:
            continue
        segments.append(
            (child.start_byte, child.end_byte, child.start_point.row + 1, child.end_point.row + 1)
        )
    return _merge_tiny(segments, code)


def _merge_tiny(segments: list[tuple[int, int, int, int]], code: bytes) -> list[tuple[int, int, int, int]]:
    """Merge consecutive small segments so chunks stay meaningful."""
    if not segments:
        return segments
    merged: list[tuple[int, int, int, int]] = []
    buf = list(segments[0])
    for seg in segments[1:]:
        buf_len = buf[1] - buf[0]
        seg_len = seg[1] - seg[0]
        if buf_len < _MIN_CHUNK_CHARS or seg_len < _MIN_CHUNK_CHARS:
            buf[1] = seg[1]
            buf[3] = seg[3]
        else:
            merged.append(tuple(buf))
            buf = list(seg)
    merged.append(tuple(buf))
    return merged


def _char_split(start_byte: int, end_byte: int, code: bytes, path: str, lang: str) -> list[Chunk]:
    """Recursive character splitter: split oversized nodes on line boundaries."""
    text = code[start_byte:end_byte].decode("utf-8", errors="replace")
    base_line = _line_of(code, start_byte)
    lines = text.split("\n")
    pieces: list[Chunk] = []
    buf: list[str] = []
    buf_len = 0
    buf_start = base_line

    def flush() -> None:
        nonlocal buf, buf_len, buf_start
        if not buf:
            return
        content = "\n".join(buf).strip()
        if content:
            pieces.append(
                Chunk(
                    chunk_id="",
                    path=path,
                    start_line=buf_start,
                    end_line=buf_start + len(buf) - 1,
                    language=lang,
                    content=content,
                )
            )
        buf, buf_len = [], 0
        buf_start = 0  # set by caller below

    current_line = base_line
    for i, line in enumerate(lines):
        if buf_len > _TOKEN_BUDGET:
            flush()
            buf_start = current_line
        buf.append(line)
        buf_len += len(line) + 1
        current_line += 1
    flush()
    # fix chunk ids and enforce recursion guard
    out: list[Chunk] = []
    for i, piece in enumerate(pieces):
        piece.chunk_id = f"{path}:{piece.start_line}:{piece.end_line}:{i}"
        if len(piece.content) > _TOKEN_BUDGET * 2:
            # extremely rare: hard-split by fixed windows
            step = _TOKEN_BUDGET
            for j in range(0, len(piece.content), step):
                window = piece.content[j : j + step]
                out.append(
                    Chunk(
                        chunk_id=f"{path}:{piece.start_line}:{piece.end_line}:{i}:{j}",
                        path=path,
                        start_line=piece.start_line + piece.content[:j].count("\n"),
                        end_line=piece.start_line + piece.content[: j + step].count("\n"),
                        language=lang,
                        content=window,
                    )
                )
        else:
            out.append(piece)
    return out


def chunk_file(code: bytes, rel_path: str, lang: str) -> list[Chunk]:
    """Produce chunks for one file: AST-first, hybrid fallback."""
    try:
        parser = get_parser(lang)
        tree = parser.parse(code)
    except Exception:
        tree = None

    symbols = extract_symbols(code, lang)

    chunks: list[Chunk] = []
    if tree is not None and tree.root_node.child_count > 0:
        segments = _top_level_segments(tree, code)
        for start_byte, end_byte, start_line, end_line in segments:
            size = end_byte - start_byte
            if size > _TOKEN_BUDGET:
                pieces = _char_split(start_byte, end_byte, code, rel_path, lang)
                for piece in pieces:
                    piece.symbols = [s for s in symbols if start_line <= s.line <= end_line]
                chunks.extend(pieces)
            else:
                content = code[start_byte:end_byte].decode("utf-8", errors="replace").strip()
                if content:
                    chunks.append(
                        Chunk(
                            chunk_id=f"{rel_path}:{start_line}:{end_line}",
                            path=rel_path,
                            start_line=start_line,
                            end_line=end_line,
                            language=lang,
                            content=content,
                            symbols=[s for s in symbols if start_line <= s.line <= end_line],
                        )
                    )
    else:
        # Plain-text path (markdown, config, or unsupported grammar shape)
        pieces = _char_split(0, len(code), code, rel_path, lang)
        for piece in pieces:
            piece.symbols = symbols
        chunks.extend(pieces)

    if not chunks:
        content = code.decode("utf-8", errors="replace").strip()
        if content:
            chunks.append(
                Chunk(
                    chunk_id=f"{rel_path}:1:{content.count(chr(10)) + 1}",
                    path=rel_path,
                    start_line=1,
                    end_line=content.count("\n") + 1,
                    language=lang,
                    content=content,
                    symbols=symbols,
                )
            )
    return chunks


def symbols_text(symbols: list[Symbol]) -> str:
    return " ".join(s.name for s in symbols)
