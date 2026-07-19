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
