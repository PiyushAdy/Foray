export interface Workspace {
  id: string
  name: string
  path: string
  source: string
  git_url?: string
  description?: string
  languages?: string[]
  created: number
  last_sync: number | null
  last_index_state: string
  stats: Record<string, unknown>
  indexed: boolean
  demo?: boolean
}

export interface IndexStatus {
  state: "idle" | "running" | "done" | "error" | "queued"
  phase: string
  percent: number
  files_total: number
  files_done: number
  chunks_done: number
  embed_done: number
  error?: string
  detail?: string
  elapsed?: number
}

export interface Bootstrap {
  demo_mode: boolean
  version?: string
  repos: DemoRepo[]
  embedding_choice_made?: boolean
  embeddings?: { engine: string; model: string }
  llm?: { provider: string; model: string; api_base?: string; has_key?: boolean }
  indexing?: {
    ignore_folders: string[]
    max_file_size_kb: number
    exclude_extensions: string[]
  }
  theme?: string
  workspaces?: Workspace[]
  last_workspace_id?: string | null
  rate_limit?: { limit: number; window_s: number } | null
}

export interface DemoRepo {
  id: string
  name: string
  description: string
  languages: string[]
  loc: number
}

export interface SearchHit {
  chunk_id: string
  path: string
  start_line: number
  end_line: number
  language: string | null
  symbols: { name: string; kind: string; line: number }[]
  content: string
  score: number
  sources: string[]
}

export interface Citation {
  path: string
  line: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  citations?: Citation[]
  streaming?: boolean
  error?: string
  contextCount?: number
  tokens?: number
}

export interface FileContent {
  path: string
  start_line: number
  end_line: number
  total_lines: number
  language: string | null
  content: string
}

export interface RepoMap {
  nodes: { id: string; label: string; score: number; files: number; loc: number; norm: number }[]
  links: { source: string; target: string; weight: number }[]
  top_files: { path: string; loc: number; language: string | null; chunks: number; score: number }[]
  stats: { files: number; loc: number; modules: number }
}

export interface ByokConfig {
  api_key?: string
  api_base?: string
}

const BYOK_KEY = "foray.byok"

export function loadByok(): ByokConfig | null {
  try {
    const raw = localStorage.getItem(BYOK_KEY)
    return raw ? (JSON.parse(raw) as ByokConfig) : null
  } catch {
    return null
  }
}

export function saveByok(cfg: ByokConfig) {
  localStorage.setItem(BYOK_KEY, JSON.stringify(cfg))
}

export function clearByok() {
  localStorage.removeItem(BYOK_KEY)
}

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `${resp.status}`
    try {
      const body = await resp.json()
      detail = body.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await resp.json()) as T
}

export const api = {
  async bootstrap(): Promise<Bootstrap> {
    return json<Bootstrap>(await fetch("/api/bootstrap"))
  },

  async setEmbedding(engine: "local" | "openai", model = "", apiKey = ""): Promise<void> {
    await json(
      await fetch("/api/config/embeddings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ engine, model, api_key: apiKey }),
      })
    )
  },

  async updateConfig(patch: Record<string, unknown>): Promise<void> {
    await json(
      await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      })
    )
  },

  async models(): Promise<{ providers: Record<string, string[]> }> {
    return json(await fetch("/api/models"))
  },

  async addWorkspace(input: { path?: string; git_url?: string; name?: string }): Promise<{ workspace: Workspace; status: IndexStatus }> {
    return json(
      await fetch("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      })
    )
  },

  async listWorkspaces(): Promise<{ workspaces: Workspace[] }> {
    return json(await fetch("/api/workspaces"))
  },

  async workspace(id: string): Promise<Workspace & { status: IndexStatus }> {
    return json(await fetch(`/api/workspaces/${id}`))
  },

  async deleteWorkspace(id: string): Promise<void> {
    await json(await fetch(`/api/workspaces/${id}`, { method: "DELETE" }))
  },

  async syncWorkspace(id: string): Promise<IndexStatus> {
    return json(await fetch(`/api/workspaces/${id}/sync`, { method: "POST" }))
  },

  async repoMap(id: string): Promise<RepoMap> {
    return json(await fetch(`/api/workspaces/${id}/map`))
  },

  async costs(id: string): Promise<{ indexing: CostBucket; docs: CostBucket }> {
    return json(await fetch(`/api/workspaces/${id}/costs`))
  },

  async getDocs(id: string): Promise<{ docs: { content: string; model: string; created: number } | null; estimate: DocEstimate }> {
    return json(await fetch(`/api/workspaces/${id}/docs`))
  },

  async generateDocs(id: string, byok?: ByokConfig): Promise<{ content: string; model: string; created: number; tokens: number; cost_usd: number }> {
    return json(
      await fetch(`/api/workspaces/${id}/docs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ byok }),
      })
    )
  },

  async search(workspaceId: string, query: string, n = 10): Promise<{ results: SearchHit[] }> {
    return json(
      await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, query, n }),
      })
    )
  },

  async readFile(workspaceId: string, path: string, startLine = 1, endLine = 0): Promise<FileContent> {
    return json(
      await fetch("/api/file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, path, start_line: startLine, end_line: endLine }),
      })
    )
  },
}

export interface CostBucket {
  n: number
  tokens: number
  cost: number
}

export interface DocEstimate {
  provider: string
  tokens: number
  cost_usd: number
  note: string
}

/* ---------------------------------------------------------------------------
 * SSE consumption: indexing progress + chat token streams.
 * fetch-based (not EventSource) so we can POST bodies.
 * ------------------------------------------------------------------------ */

export function streamIndexStatus(
  workspaceId: string,
  onEvent: (status: IndexStatus) => void,
  onDone: () => void,
  onError: (message: string) => void
): () => void {
  const controller = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(`/api/workspaces/${workspaceId}/status`, { signal: controller.signal })
      if (!resp.ok || !resp.body) throw new Error(`status stream failed (${resp.status})`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split("\n\n")
        buffer = frames.pop() ?? ""
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "))
          if (!line) continue
          try {
            const payload = JSON.parse(line.slice(6)) as IndexStatus
            onEvent(payload)
            if (payload.state === "done" || payload.state === "error") {
              if (payload.state === "error") onError(payload.error ?? "indexing failed")
              onDone()
              controller.abort()
              return
            }
          } catch {
            /* skip malformed frame */
          }
        }
      }
      onDone()
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError((err as Error).message)
    }
  })()
  return () => controller.abort()
}

export interface ChatStreamHandlers {
  onToken: (text: string) => void
  onContext?: (chunks: { path: string; start_line: number; end_line: number }[]) => void
  onDone: (payload: { text: string; citations: Citation[]; tokens: number; contextCount: number }) => void
  onError: (message: string) => void
}

export function streamChat(
  workspaceId: string,
  question: string,
  history: { role: "user" | "assistant"; content: string }[],
  handlers: ChatStreamHandlers,
  byok?: ByokConfig | null
): () => void {
  const controller = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ workspace_id: workspaceId, question, history, byok: byok ?? undefined }),
      })
      if (!resp.ok || !resp.body) {
        let detail = `chat failed (${resp.status})`
        try {
          const body = await resp.json()
          detail = body.detail ?? detail
        } catch {
          /* ignore */
        }
        handlers.onError(detail)
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split("\n\n")
        buffer = frames.pop() ?? ""
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "))
          if (!line) continue
          try {
            const payload = JSON.parse(line.slice(6))
            if (payload.type === "token") handlers.onToken(payload.text)
            else if (payload.type === "context") handlers.onContext?.(payload.chunks ?? [])
            else if (payload.type === "done") {
              handlers.onDone({
                text: payload.text ?? "",
                citations: payload.citations ?? [],
                tokens: payload.tokens ?? 0,
                contextCount: payload.context_count ?? 0,
              })
              controller.abort()
              return
            } else if (payload.type === "error") {
              handlers.onError(payload.message)
              controller.abort()
              return
            }
          } catch {
            /* skip malformed frame */
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") handlers.onError((err as Error).message)
    }
  })()
  return () => controller.abort()
}
