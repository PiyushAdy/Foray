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
