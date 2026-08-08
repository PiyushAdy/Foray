"""LLM synthesis & citations via LiteLLM.

LiteLLM standardizes API calls (OpenAI, Anthropic, Ollama) while the
prompt construction and citation parsing stay in clean, transparent
custom Python.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import litellm

from .search import hybrid_search

SYSTEM_PROMPT = """You are Foray, a codebase intelligence assistant answering questions about one repository.

Rules:
- Ground every claim in the provided code context. If the context is insufficient, say so plainly.
- Answer concisely with correct, specific technical detail.
- Cite evidence inline using this exact badge syntax whenever you reference code:
  [path/to/file.py:L12] where L12 is the first line of the relevant code.
  Citations must reference files and lines that exist in the context blocks.
- Prefer file paths exactly as given in the context headers.
- Use short paragraphs. Use fenced code blocks with language tags for code."""

CONTEXT_HEADER = "--- {path} (lines {start}-{end}) ---"

CITATION_RE = re.compile(r"\[([^\]\n:]+\.?[^\]\n]*?):L(\d+)\]")


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class GroundedContext:
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def render(self, max_chars: int = 24000) -> str:
        parts: list[str] = []
        total = 0
        for chunk in self.chunks:
            body = chunk["content"]
            if total + len(body) > max_chars:
                body = body[: max(0, max_chars - total)]
            if not body.strip():
                continue
            header = CONTEXT_HEADER.format(path=chunk["path"], start=chunk["start_line"], end=chunk["end_line"])
            block = f"{header}\n{body}"
            parts.append(block)
            total += len(body)
            if total >= max_chars:
                break
        return "\n\n".join(parts)


def build_messages(question: str, history: list[ChatTurn], context: GroundedContext) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-6:]:
        messages.append({"role": turn.role, "content": turn.content})
    context_text = context.render()
    user_content = f"Code context:\n\n{context_text}\n\nQuestion: {question}" if context_text else question
    messages.append({"role": "user", "content": user_content})
    return messages


def parse_citations(text: str) -> list[dict[str, Any]]:
    """Extract citation badges the LLM emitted, validated against context."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for match in CITATION_RE.finditer(text):
        path, line = match.group(1).strip(), int(match.group(2))
        if not path or (path, line) in seen:
            continue
        seen.add((path, line))
        found.append({"path": path, "line": line})
    return found


def validate_citations(text: str, context: GroundedContext) -> tuple[str, list[dict[str, Any]]]:
    """Drop citations that do not resolve to context files (anti-hallucination)."""
    valid_paths = {chunk["path"] for chunk in context.chunks}
    valid: list[dict[str, Any]] = []
    for citation in parse_citations(text):
        if citation["path"] in valid_paths:
            valid.append(citation)

    def _filter(match: re.Match) -> str:
        path, line = match.group(1).strip(), int(match.group(2))
        if path in valid_paths:
            return match.group(0)
        return f"[{path}]"  # keep the reference readable but unlinked

    cleaned = CITATION_RE.sub(_filter, text)
    return cleaned, valid


# ---------------------------------------------------------------------------
# model config
# ---------------------------------------------------------------------------

PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"],
    "anthropic": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-3-5-sonnet-latest"],
    "ollama": ["qwen2.5-coder:7b", "llama3.1:8b", "deepseek-coder-v2:16b"],
}


def litellm_model(provider: str, model: str) -> str:
    provider = (provider or "openai").lower()
    if provider == "ollama":
        return f"ollama/{model}"
    if provider == "anthropic":
        return model if model.startswith("claude") else f"anthropic/{model}"
    if provider == "custom":
        return f"openai/{model}"
    return model if model.startswith("gpt") or model.startswith("o") else f"openai/{model}"


# ---------------------------------------------------------------------------
# streaming completion
# ---------------------------------------------------------------------------

async def stream_chat(
    repo_id: str,
    question: str,
    history: list[ChatTurn],
    llm_settings: dict[str, Any],
    byok: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE-ready events: context, token deltas, citations, done, error.

    Chat costs are ephemeral (session only); indexing costs persist.
    """
    chunks = hybrid_search(repo_id, question, n=12)
    context = GroundedContext(chunks=chunks)
    yield {
        "type": "context",
        "chunks": [
            {
                "path": c["path"],
                "start_line": c["start_line"],
                "end_line": c["end_line"],
                "score": c.get("score", 0),
                "sources": c.get("sources", []),
            }
            for c in chunks
        ],
    }

    messages = build_messages(question, history, context)

    provider = (llm_settings.get("provider") or "openai").lower()
    model = llm_settings.get("model") or "gpt-4o-mini"
    api_key = (byok or {}).get("api_key") or llm_settings.get("api_key") or ""
    api_base = (byok or {}).get("api_base") or llm_settings.get("api_base") or ""

    call_model = litellm_model(provider, model)
    api_base_value = api_base or None

    if provider == "ollama" and not api_base:
        api_base_value = "http://localhost:11434"

    if provider in ("openai", "anthropic", "custom") and not api_key:
        yield {"type": "error", "message": f"No API key configured for {provider}. Add one in Settings, or use a local Ollama endpoint."}
        return

    full_text: list[str] = []
    try:
        stream = await litellm.acompletion(
            model=call_model,
            messages=messages,
            stream=True,
            api_key=api_key or None,
            api_base=api_base_value,
            temperature=0.2,
            max_tokens=1600,
        )
        async for event in stream:
            delta = event.choices[0].delta.content if event.choices else None
            if delta:
                full_text.append(delta)
                yield {"type": "token", "text": delta}
    except Exception as exc:  # noqa: BLE001 - surfaced as an elegant toast
        yield {"type": "error", "message": f"LLM call failed: {exc}"}
        return

    text = "".join(full_text)
    text, citations = validate_citations(text, context)
    usage_tokens = _estimate_tokens(question, text)
    yield {
        "type": "done",
        "text": text,
        "citations": citations,
        "context_count": len(chunks),
        "tokens": usage_tokens,
    }


def _estimate_tokens(question: str, answer: str) -> int:
    return (len(question) + len(answer)) // 4
