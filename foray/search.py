"""Hybrid search: SQLite FTS5 (BM25) + Chroma vectors, fused with RRF.

Pure vector search struggles with exact variable names and error codes;
FTS5 alone misses conceptual matches. Reciprocal Rank Fusion delivers
the best of both.
"""

from __future__ import annotations

import re
from typing import Any

from . import db as dbmod
from .embeddings import build_embedder
from .vectorstore import VectorStore

RRF_K = 60
FTS_LIMIT = 40
VECTOR_LIMIT = 24


def _fts_search(conn, query: str, limit: int = FTS_LIMIT) -> list[dict[str, Any]]:
    """BM25 lexical search over chunk contents + symbol names."""
    terms = _fts_terms(query)
    if not terms:
        return []
    fts_query = " OR ".join(terms)
    try:
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.path, c.start_line, c.end_line, c.language, c.symbols, c.content,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts f
            JOIN chunks c ON c.path = f.path AND c.content = f.content
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except Exception:
        return []
    hits: list[dict[str, Any]] = []
    for row in rows:
        hits.append(
            {
                "chunk_id": row["chunk_id"],
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "language": row["language"],
                "symbols": _parse_symbols(row["symbols"]),
                "content": row["content"],
                "rank": 0,
            }
        )
    return hits


def _fts_terms(query: str) -> list[str]:
    cleaned = re.sub(r"[^\w\s.]", " ", query)
    terms = [t for t in cleaned.split() if len(t) >= 2]
    # add the raw query as a phrase when it has multiple words
    if len(terms) > 1:
        terms.insert(0, '"' + " ".join(terms) + '"')
    return terms[:12]


def _parse_symbols(raw: str) -> list[dict[str, Any]]:
    import json

    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []


def _normalize_symbols(symbols: Any) -> list[dict[str, Any]]:
    """FTS legs carry dicts; vector legs carry plain name strings."""
    if not isinstance(symbols, list):
        return []
    out: list[dict[str, Any]] = []
    for sym in symbols:
        if isinstance(sym, dict) and sym.get("name"):
            out.append({"name": sym["name"], "kind": sym.get("kind", ""), "line": sym.get("line", 0)})
        elif isinstance(sym, str) and sym.strip():
            out.append({"name": sym.strip(), "kind": "", "line": 0})
    return out


def hybrid_search(repo_id: str, query: str, n: int = 12) -> list[dict[str, Any]]:
    """RRF-fused FTS5 + vector results for a query scoped to one workspace."""
    from . import paths

    live = paths.live_dir(repo_id)
    if not (live / "index.sqlite").is_file():
        return []

    conn = dbmod.open_index(repo_id, create=False)
    try:
        fts_hits = _fts_search(conn, query)
    finally:
        conn.close()

    vector_hits: list[dict[str, Any]] = []
    try:
        vstore = VectorStore(paths.chroma_dir(repo_id))
        cfg = _embedding_settings()
        embedder = build_embedder(cfg)
        vector = embedder.embed_sync([query])[0]
        vector_hits = vstore.query(vector, n=VECTOR_LIMIT)
    except Exception:
        vector_hits = []

    vector_score = {hit["chunk_id"]: hit.get("score", 0.0) for hit in vector_hits}

    # Reciprocal Rank Fusion
    fused: dict[str, dict[str, Any]] = {}
    for hits in (fts_hits, vector_hits):
        for rank, hit in enumerate(hits):
            cid = hit["chunk_id"]
            entry = fused.setdefault(
                cid,
                {
                    "chunk_id": cid,
                    "path": hit["path"],
                    "start_line": hit["start_line"],
                    "end_line": hit["end_line"],
                    "language": hit.get("language", ""),
                    "symbols": _normalize_symbols(hit.get("symbols", [])),
                    "content": hit["content"],
                    "rrf": 0.0,
                    "sources": [],
                },
            )
            # keep the richer (dict) symbol payload when both legs agree
            if not entry["symbols"] or all(isinstance(s, str) for s in entry["symbols"]):
                entry["symbols"] = _normalize_symbols(hit.get("symbols", []))
            entry["rrf"] += 1.0 / (RRF_K + rank + 1)
            source = "fts" if hits is fts_hits else "vector"
            if source not in entry["sources"]:
                entry["sources"].append(source)

    # Definition boost: an exact identifier query should surface the site
    # that defines it, not merely the import statement that names it.
    terms = {t.lower() for t in query.replace("(", " ").replace(")", " ").split() if len(t) >= 3}
    for entry in fused.values():
        defined = any(
            str(sym.get("name", "")).lower() in terms
            for sym in entry.get("symbols", [])
            if isinstance(sym, dict)
        )
        if defined:
            entry["rrf"] += 0.02

    results = sorted(
        fused.values(),
        key=lambda h: (h["rrf"], vector_score.get(h["chunk_id"], 0.0)),
        reverse=True,
    )[:n]
    for hit in results:
        hit["score"] = round(hit.pop("rrf"), 4)
    return results


def _embedding_settings() -> dict[str, Any]:
    from . import config

    return config.load().get("embeddings", {})
