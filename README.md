# Foray

The local intelligence layer for your codebase.

Foray indexes a repository locally and provides grounded context for two
audiences: **you** (a local web UI for chatting, visualizing and reading
docs) and **your agents** (an MCP server that feeds repository context
into external AI coding assistants like Claude Code or Cursor).

## Quick start

Requires Python 3.12+.

```bash
uv tool install foray     # or: pipx install foray
foray start               # spins up the UI and opens your browser
```

Point it at a local folder or paste a Git URL. Foray shallow-clones it,
indexes it, and you are ready to ask questions with citations that
navigate straight to the file and line.

## What it does

- **Grounded chat.** A ChatGPT-like interface scoped to your active
  workspace. Answers cite `[server.py:L12]` badges; clicking one slides
  open the referenced code next to the conversation. Chat history is
  ephemeral by design: reload resets it, keeping the app fast.
- **Hybrid search.** BM25 lexical search (SQLite FTS5) fused with
  semantic vector search (embedded ChromaDB) via Reciprocal Rank Fusion.
  Exact identifiers and conceptual questions both work.
- **Repo map.** A module-level dependency graph, PageRank-weighted, for
  fast orientation in unfamiliar codebases.
- **Onboarding docs.** A Markdown guide generated on demand (with an
  upfront cost estimate) and cached in the index.
- **MCP context server.** `foray-mcp` runs over stdio, spawned silently
  by your agent. Search, read files, get the repo map - no ports, no
  UI required.
- **100+ languages.** tree-sitter grammars with community-authored
  tags queries drive AST-aware chunking and symbol extraction out of
  the box.
- **Static snapshots.** Indexing happens when you click Sync, never in
  the background. Incremental syncs hash files (SHA-256) to skip
  unchanged ones and purge ghost files.

## Storage

All data lives in the OS-standard global directory
(`~/.local/share/foray`), never in your repositories:

```
~/.local/share/foray/
├── config.json        global settings (keys, theme, workspaces)
├── indexes/<repo>/    per-repo SQLite + ChromaDB indexes
└── repos/             shallow clones for Git URL imports
```

## Configuration

The first run asks for an embedding engine: local models (private, free)
or cloud embeddings. Settings cover LLM provider and keys (OpenAI,
Anthropic, or a local Ollama endpoint), indexing toggles (ignored
folders, max file size), a cost tracker, and light/dark theme.

`.gitignore` and `.forayignore` rules in the repository root are
respected automatically during indexing.

## MCP

Register the context server with your agent:

```json
{
  "mcpServers": {
    "foray": {
      "command": "foray-mcp"
    }
  }
}
```

Tools: `list_workspaces`, `search_code`, `read_file`, `get_repo_map`,
`get_symbols`.

## Hosted demo mode

Run with `FORAY_DEMO=1` (or `foray start --demo`) for a read-only
showcase. Visitors get a strict rate limit on the host key; power users
can unlock unlimited queries with their own API key and base URL
(BYOK, stored in their browser only). The demo landing page reads
`demo_repos.yaml` to decide which pre-indexed repositories to display.

## Docker

```bash
docker build -t foray .
docker run -p 7420:7420 -v foray-data:/data foray
```

## Development

```bash
git clone <this repo> && cd foray
uv sync                                  # backend deps
uv run pytest                            # backend tests
cd frontend && npm install && npm run dev   # UI against the API
npm run build                            # bundle into frontend/dist,
                                         # served by FastAPI
```

MIT license.
