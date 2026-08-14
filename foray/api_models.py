"""Pydantic request/response models for the Foray API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EmbeddingChoice(BaseModel):
    engine: Literal["local", "openai"]
    model: str = ""
    api_key: str = ""


class LLMSettings(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    api_base: str = ""


class IndexingSettings(BaseModel):
    ignore_folders: list[str] = Field(default_factory=list)
    max_file_size_kb: int = 512
    exclude_extensions: list[str] = Field(default_factory=list)


class ConfigPatch(BaseModel):
    theme: str | None = None
    llm: LLMSettings | None = None
    indexing: IndexingSettings | None = None


class AddWorkspaceRequest(BaseModel):
    # exactly one of these must be set
    path: str = ""
    git_url: str = ""
    name: str = ""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    workspace_id: str
    question: str
    history: list[ChatMessage] = Field(default_factory=list)
    byok: dict[str, str] | None = None


class SearchRequest(BaseModel):
    workspace_id: str
    query: str
    n: int = 10


class FileRequest(BaseModel):
    workspace_id: str
    path: str
    start_line: int = 1
    end_line: int = 0  # 0 = to EOF


class WorkspaceOut(BaseModel):
    id: str
    name: str
    path: str
    source: str
    git_url: str = ""
    created: float = 0.0
    last_sync: float | None = None
    last_index_state: str = "pending"
    stats: dict[str, Any] = Field(default_factory=dict)
