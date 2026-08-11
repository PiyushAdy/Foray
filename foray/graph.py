"""Graph processing: SQLite edges + in-memory networkx.

Relationships ("File A imports File B") are stored as simple edges in
SQLite. For the repo map, edges load into networkx in memory where
PageRank runs in milliseconds - no dedicated graph database required.

Edge generation uses robust path-resolution for top-tier languages
(Python, JS/TS, Go) and fuzzy string matching against indexed file
paths as the fallback for everything else.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import networkx as nx

# --------------------------------------------------------------------------
# import statement extraction
# --------------------------------------------------------------------------

_PY_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+([\w\.]+)[ \t]+import[ \t]|import[ \t]+([\w\.]+(?:[ \t]*,[ \t]*[\w\.]+)*))", re.M)
_JS_IMPORT = re.compile(r"""(?:from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\))""")
_GO_IMPORT = re.compile(r'"([^"]+)"')


def _normalize_module(module: str) -> list[str]:
    return [part for part in module.split(".") if part]


def _extract_python_imports(text: str) -> set[str]:
    found: set[str] = set()
    for match in _PY_IMPORT.finditer(text):
        for group in match.groups():
            if not group:
                continue
            for mod in group.split(","):
                mod = mod.strip().split(" as ")[0].strip()
                if mod:
                    found.add(mod)
    return found


def _extract_js_imports(text: str) -> set[str]:
    found: set[str] = set()
    for match in _JS_IMPORT.finditer(text):
        for group in match.groups():
            if group:
                found.add(group)
    return found


def _extract_go_imports(text: str) -> set[str]:
    blocks = re.findall(r"import\s+(?:\(([^)]*)\)|\"([^\"]+)\")", text, re.S)
    found: set[str] = set()
    for block, single in blocks:
        if single:
            found.add(single)
        else:
            for line in block.splitlines():
                line = line.strip()
                if line and not line.startswith("//"):
                    m = _GO_IMPORT.search(line)
                    if m:
                        found.add(m.group(1))
    return found


# --------------------------------------------------------------------------
# path resolution
# --------------------------------------------------------------------------

def _resolve_python(module: str, source_dir: Path, rel: str, file_set: set[str], repo_name: str) -> str | None:
    if module.startswith("."):
        # relative import: walk up from the file's package
        level = len(module) - len(module.lstrip("."))
        target = module.lstrip(".")
        base = Path(rel).parent
        for _ in range(level - 1):
            base = base.parent
        candidate = (base / target.replace(".", "/")).as_posix()
        for suffix in (".py", "/__init__.py"):
            probe = candidate + suffix if suffix == ".py" else candidate + suffix
            if probe in file_set:
                return probe
        return None

    # repo-local absolute import: try top-level packages inside the repo
    parts = _normalize_module(module)
    if not parts:
        return None
    # strip a leading package that matches the repo name (common: src layout)
    for start in (0, 1):
        if start == 1 and parts and parts[0] == repo_name:
            parts_c = parts[1:]
        elif start == 1:
            continue
        else:
            parts_c = parts
        if not parts_c:
            continue
        candidate = "/".join(parts_c)
        for probe in (f"{candidate}.py", f"{candidate}/__init__.py"):
            if probe in file_set:
                return probe
    return None


def _resolve_js(specifier: str, rel: str, file_set: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None  # bare package specifier -> external dependency
    base = (Path(rel).parent / specifier).as_posix()
    for probe in (base, f"{base}.js", f"{base}.ts", f"{base}.tsx", f"{base}.jsx", f"{base}/index.ts", f"{base}/index.tsx", f"{base}/index.js", f"{base}/index.jsx"):
        if probe in file_set:
            return probe
    return None


def _resolve_go(path: str, rel: str, file_set: set[str], go_module: str | None, go_prefix: str) -> str | None:
    if not go_module:
        return None
    if not path.startswith(go_module):
        return None  # external package
    suffix = path[len(go_module):].lstrip("/")
    if not suffix:
        return None
    for probe in (f"{go_prefix}{suffix}.go", f"{go_prefix}{suffix}/",):
        p = probe.rstrip("/")
        if p in file_set:
            return p
        # match any file in that package dir
        for f in file_set:
            if f.startswith(p + "/") and f.endswith(".go"):
                return f
    return None


def _fuzzy_match(name: str, file_set: set[str]) -> str | None:
    """Fallback for other languages: match module name against indexed paths."""
    name = name.strip().strip('"\'')
    if not name or len(name) < 3 or "/" in name or "." in name:
        return None
    for f in file_set:
        stem = Path(f).stem
        if stem == name:
            return f
    return None


# --------------------------------------------------------------------------
# edge builder
# --------------------------------------------------------------------------

_IMPORT_EXTRACTORS = {
    "python": _extract_python_imports,
    "javascript": _extract_js_imports,
    "js": _extract_js_imports,
    "typescript": _extract_js_imports,
    "ts": _extract_js_imports,
    "tsx": _extract_js_imports,
    "jsx": _extract_js_imports,
}


def build_import_edges(root: Path, file_set: set[str], max_file_bytes: int = 512_000) -> list[tuple[str, str, str]]:
    repo_name = root.name
    go_module: str | None = None
    go_mod_file = root / "go.mod"
    if go_mod_file.is_file():
        try:
            first = go_mod_file.read_text(errors="replace").splitlines()
            for line in first:
                if line.startswith("module "):
                    go_module = line.split(None, 1)[1].strip().strip('"')
                    break
        except OSError:
            pass
    go_prefix = ""
    if go_module:
        # find the dir that maps the module root (usually repo root)
        go_prefix = ""

    edges: set[tuple[str, str, str]] = set()
    for rel in file_set:
        path = root / rel
        suffix = path.suffix.lower()
        lang_key = "python" if suffix == ".py" else (
            "js" if suffix in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts") else (
                "go" if suffix == ".go" else None
            )
        )
        if lang_key is None:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if lang_key == "python":
            for module in _extract_python_imports(text):
                target = _resolve_python(module, path.parent, rel, file_set, repo_name)
                if target and target != rel:
                    edges.add((rel, target, "import"))
        elif lang_key == "go":
            for import_path in _extract_go_imports(text):
                target = _resolve_go(import_path, rel, file_set, go_module, go_prefix)
                if target and target != rel:
                    edges.add((rel, target, "import"))
        else:
            for spec in _extract_js_imports(text):
                target = _resolve_js(spec, rel, file_set)
                if target and target != rel:
                    edges.add((rel, target, "import"))
                elif target is None and spec and not spec.startswith("."):
                    resolved = _fuzzy_match(spec.rsplit("/", 1)[-1], file_set)
                    if resolved and resolved != rel:
                        edges.add((rel, resolved, "import"))

    return sorted(edges)


# --------------------------------------------------------------------------
# repo map (module & file level, PageRank-weighted)
# --------------------------------------------------------------------------

def repo_map(conn, max_nodes: int = 60, max_edges: int = 140) -> dict:
    """Build the architecture visualization payload.

    Focus: how directories and major files depend on each other.
    Intentionally avoids symbol-level clutter for onboarding.
    """
    edge_rows = conn.execute("SELECT source, target FROM edges LIMIT 50000").fetchall()
    file_rows = conn.execute("SELECT path, loc, language, chunk_count FROM files").fetchall()

    if not file_rows:
        return {"nodes": [], "links": [], "top_files": [], "stats": {"files": 0, "loc": 0}}

    graph = nx.DiGraph()
    loc_by_path = {row["path"]: row["loc"] for row in file_rows}
    for row in file_rows:
        graph.add_node(row["path"], loc=row["loc"], language=row["language"])
    for row in edge_rows:
        if row["source"] in graph and row["target"] in graph:
            graph.add_edge(row["source"], row["target"])

    pagerank = nx.pagerank(graph, weight=None, max_iter=60) if graph.number_of_edges() else {n: 1 for n in graph.nodes}

    # module = directory. Aggregate file PageRank into directories.
    module_score: dict[str, float] = {}
    module_files: dict[str, list[str]] = {}
    for path, score in pagerank.items():
        module = str(path.rsplit("/", 1)[0]) if "/" in path else "."
        module_score[module] = module_score.get(module, 0.0) + float(score)
        module_files.setdefault(module, []).append(path)

    top_modules = sorted(module_score.items(), key=lambda kv: kv[1], reverse=True)[:max_nodes]
    module_names = {m for m, _ in top_modules}

    # directory-to-directory links, aggregated
    link_weights: dict[tuple[str, str], int] = {}
    for row in edge_rows:
        s, t = row["source"], row["target"]
        s_mod = str(s.rsplit("/", 1)[0]) if "/" in s else "."
        t_mod = str(t.rsplit("/", 1)[0]) if "/" in t else "."
        if s_mod == t_mod:
            continue
        if s_mod in module_names and t_mod in module_names:
            link_weights[(s_mod, t_mod)] = link_weights.get((s_mod, t_mod), 0) + 1

    top_links = sorted(link_weights.items(), key=lambda kv: kv[1], reverse=True)[:max_edges]
    score_range = [s for _, s in top_modules]
    smin, smax = (min(score_range), max(score_range)) if score_range else (0, 1)

    nodes = [
        {
            "id": module,
            "label": module if module == "." else module.rsplit("/", 1)[-1] if "/" in module else module,
            "score": round(score, 5),
            "files": len(module_files.get(module, [])),
            "loc": sum(loc_by_path.get(p, 0) for p in module_files.get(module, [])),
            "norm": _normalize(score, smin, smax),
        }
        for module, score in top_modules
    ]
    links = [
        {"source": s, "target": t, "weight": w}
        for (s, t), w in top_links
    ]

    top_files = sorted(
        (
            {"path": p, "loc": loc, "language": lang, "chunks": chunks, "score": round(float(pagerank.get(p, 0)), 5)}
            for p, loc, lang, chunks in ((row["path"], row["loc"], row["language"], row["chunk_count"]) for row in file_rows)
        ),
        key=lambda f: f["score"],
        reverse=True,
    )[:20]

    total_loc = sum(loc_by_path.values())
    return {
        "nodes": nodes,
        "links": links,
        "top_files": top_files,
        "stats": {"files": len(file_rows), "loc": total_loc, "modules": len(module_score)},
    }


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi - lo < 1e-9:
        return 0.5
    return (value - lo) / (hi - lo)
