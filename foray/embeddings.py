"""Embedding engines: local fastembed (private, free) or cloud OpenAI.

fastembed runs ONNX models inside the Python process for a true
zero-config experience. Cloud engines send code off-machine and
incur API costs, which are tracked transparently.
"""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

LOCAL_MODELS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
}

OPENAI_MODEL = "text-embedding-3-small"
OPENAI_DIM = 1536
OPENAI_PRICE_PER_MTOK = 0.02


class EmbeddingError(RuntimeError):
    pass


class LocalEmbedder:
    """fastembed-backed ONNX embedder. Model loads lazily once per process."""

    _models: dict[str, Any] = {}

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        if model not in LOCAL_MODELS:
            model = "BAAI/bge-small-en-v1.5"
        self.model_name = model

    def _model(self):
        if self.model_name not in LocalEmbedder._models:
            from fastembed import TextEmbedding

            LocalEmbedder._models[self.model_name] = TextEmbedding(self.model_name)
        return LocalEmbedder._models[self.model_name]

    @property
    def dim(self) -> int:
        return LOCAL_MODELS[self.model_name]

    def embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._model()
        vectors = [list(map(float, v)) for v in model.embed(list(texts))]
        if len(vectors) != len(texts):
            raise EmbeddingError("embedding count mismatch")
        return vectors

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_sync, texts)


class OpenAIEmbedder:
    """Cloud embeddings through LiteLLM's OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, model: str = OPENAI_MODEL, api_base: str = ""):
        if not api_key:
            raise EmbeddingError("OpenAI embeddings require an API key")
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model
        self.tokens_used = 0

    @property
    def dim(self) -> int:
        return OPENAI_DIM

    def embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        import litellm

        try:
            response = litellm.embedding(
                model=f"openai/{self.model_name}",
                input=list(texts),
                api_key=self.api_key,
                api_base=self.api_base or None,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a toast
            raise EmbeddingError(f"cloud embedding failed: {exc}") from exc

        usage = getattr(response, "usage", None)
        if usage is not None and getattr(usage, "total_tokens", None):
            self.tokens_used += usage.total_tokens
        data = getattr(response, "data", None) or []
        vectors = [list(map(float, item["embedding"])) for item in data]
        if len(vectors) != len(texts):
            raise EmbeddingError("embedding count mismatch")
        return vectors

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed_sync, texts)

    def estimated_cost(self) -> float:
        return self.tokens_used / 1_000_000 * OPENAI_PRICE_PER_MTOK


def build_embedder(settings: dict[str, Any], byok: dict[str, str] | None = None):
    """Factory honoring the first-run embedding choice + BYOK overrides."""
    engine = (settings.get("engine") or "local").lower()
    if engine == "openai":
        api_key = (byok or {}).get("embedding_api_key") or settings.get("api_key") or ""
        api_base = (byok or {}).get("api_base") or settings.get("api_base") or ""
        model = settings.get("model") or OPENAI_MODEL
        return OpenAIEmbedder(api_key=api_key, model=model, api_base=api_base)
    model = settings.get("model") or "BAAI/bge-small-en-v1.5"
    return LocalEmbedder(model=model)
