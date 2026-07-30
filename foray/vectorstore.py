"""ChromaDB vector store wrapper.

Chroma runs in-process alongside FastAPI and persists vector data in the
per-repo index directory. It handles repository-scale data (10k-50k chunks
effortlessly) without external services or heavy containers.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

_BATCH = 256


class VectorStore:
    def __init__(self, persist_dir: Path, collection: str = "chunks"):
        persist_dir = Path(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._collection.count()

    def upsert(self, ids: list[str], vectors: list[list[float]], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        for start in range(0, len(ids), _BATCH):
            end = start + _BATCH
            self._collection.upsert(
                ids=ids[start:end],
                embeddings=vectors[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

    def query(self, vector: list[float], n: int = 24, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=min(n, self._collection.count()),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[dict[str, Any]] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for cid, doc, meta, dist in zip(ids, docs, metas, dists):
            raw_symbols = (meta or {}).get("symbols", "")
            symbols = raw_symbols.split() if isinstance(raw_symbols, str) else (raw_symbols or [])
            hits.append(
                {
                    "chunk_id": cid,
                    "content": doc,
                    "path": (meta or {}).get("path", ""),
                    "start_line": (meta or {}).get("start_line", 0),
                    "end_line": (meta or {}).get("end_line", 0),
                    "language": (meta or {}).get("language", ""),
                    "symbols": symbols,
                    "score": 1.0 - float(dist),
                }
            )
        return hits

    def delete_by_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        for start in range(0, len(paths), _BATCH):
            end = start + _BATCH
            self._collection.delete(where={"path": {"$in": paths[start:end]}})

    def reset(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name="chunks", metadata={"hnsw:space": "cosine"}
        )


def new_chunk_id() -> str:
    return uuid.uuid4().hex
