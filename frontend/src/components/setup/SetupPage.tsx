import React from "react"
import { useNavigate } from "react-router-dom"
import { motion, useReducedMotion } from "motion/react"
import {
  ArrowRightIcon,
  CloudIcon,
  DatabaseIcon,
  FolderOpenIcon,
  GlobeIcon,
  HardDriveIcon,
  SealCheckIcon,
} from "@phosphor-icons/react"
import { toast } from "sonner"

import { api, streamIndexStatus, type IndexStatus } from "@/lib/api"
import { useApp } from "@/stores/app"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="#111112" />
      <path d="M9 11.5 L16 23 L23 11.5" stroke="#f97316" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

/* ---------------------------------------------------------------------------
 * Step 1: embedding engine choice (forced on first boot)
 * ------------------------------------------------------------------------ */

function EmbeddingChoice({ onDone }: { onDone: () => void }) {
  const [engine, setEngine] = React.useState<"local" | "openai">("local")
  const [apiKey, setApiKey] = React.useState("")
  const [saving, setSaving] = React.useState(false)

  const choose = async () => {
    setSaving(true)
    try {
      await api.setEmbedding(engine, engine === "openai" ? "text-embedding-3-small" : "", apiKey)
      const b = await api.bootstrap()
      useApp.getState().setBootstrap(b)
      onDone()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const options = [
    {
      id: "local" as const,
      icon: HardDriveIcon,
      title: "Local models",
      tagline: "Private and free",
      body: "fastembed runs ONNX models inside the app. Code never leaves this machine.",
      meta: "BAAI/bge-small-en-v1.5 · 384 dims",
    },
    {
      id: "openai" as const,
      icon: CloudIcon,
      title: "Cloud models",
      tagline: "Higher quality",
      body: "OpenAI embeddings with better semantic precision. Sends code off-machine and costs API credits.",
      meta: "text-embedding-3-small · 1536 dims",
    },
  ]

  return (
    <div className="paper-grain flex min-h-[100dvh] items-center justify-center bg-paper-100 px-6">
      <div className="w-full max-w-[560px]">
        <div className="mb-7 flex items-center gap-2.5">
          <Logo />
          <span className="text-[14px] font-semibold tracking-[-0.01em] text-paper-900">foray</span>
        </div>
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-paper-900">
          Choose your embedding engine
        </h1>
        <p className="mt-2 max-w-[56ch] text-[13.5px] leading-relaxed text-paper-600">
          This powers the vector index behind search and chat. You can switch later in Settings.
        </p>
        <div className="mt-6 flex flex-col gap-3">
          {options.map((opt) => {
            const selected = engine === opt.id
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setEngine(opt.id)}
                className={`flex items-start gap-4 rounded-[12px] border p-4 text-left transition-all duration-150 ${
                  selected
                    ? "border-ember-600/60 bg-ember-50/60 shadow-[0_0_0_1px_rgba(234,88,12,0.25)]"
                    : "border-[var(--border-strong)] bg-paper-50 hover:border-paper-400"
                }`}
              >
                <opt.icon className={`mt-0.5 h-5 w-5 shrink-0 ${selected ? "text-ember-600" : "text-paper-500"}`} weight="duotone" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2.5">
                    <span className="text-[14.5px] font-semibold text-paper-900">{opt.title}</span>
                    <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-paper-500">
                      {opt.tagline}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[12.5px] leading-relaxed text-paper-600">{opt.body}</p>
                  <span className="mt-2 block font-mono text-[10.5px] text-paper-400">{opt.meta}</span>
                </div>
                {selected && <SealCheckIcon className="mt-0.5 h-5 w-5 shrink-0 text-ember-600" weight="fill" />}
              </button>
            )
          })}
        </div>
        {engine === "openai" && (
          <label className="mt-4 flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-paper-800">OpenAI API key</span>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </label>
        )}
        <div className="mt-6 flex items-center justify-between">
          <span className="flex items-center gap-2 text-[11.5px] text-paper-500">
            <DatabaseIcon className="h-3.5 w-3.5" />
            index data lives in ~/.local/share/foray
          </span>
          <Button variant="accent" onClick={choose} disabled={saving}>
            {saving ? "Saving..." : "Continue"}
            <ArrowRightIcon className="h-3.5 w-3.5" weight="bold" />
          </Button>
        </div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Step 2: add repository (local path or git URL)
 * ------------------------------------------------------------------------ */

function AddRepository() {
  const navigate = useNavigate()
  const [mode, setMode] = React.useState<"local" | "git">("local")
  const [path, setPath] = React.useState("")
  const [gitUrl, setGitUrl] = React.useState("")
  const [name, setName] = React.useState("")
  const [submitting, setSubmitting] = React.useState(false)

  const submit = async () => {
    setSubmitting(true)
    try {
      const payload =
        mode === "local" ? { path: path.trim() } : { git_url: gitUrl.trim(), name: name.trim() || undefined }
      const { workspace } = await api.addWorkspace(payload)
      navigate(`/workspace/${workspace.id}`, { state: { justAdded: true } })
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="paper-grain flex min-h-[100dvh] items-center justify-center bg-paper-100 px-6">
      <div className="w-full max-w-[520px]">
        <div className="mb-7 flex items-center gap-2.5">
          <Logo />
          <span className="text-[14px] font-semibold tracking-[-0.01em] text-paper-900">foray</span>
        </div>
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-paper-900">Add a repository</h1>
        <p className="mt-2 max-w-[56ch] text-[13.5px] leading-relaxed text-paper-600">
          Point Foray at a local folder, or paste a Git URL for a shallow clone. Indexing respects
          your .gitignore.
        </p>

        <div className="mt-6 flex gap-1 rounded-[9px] border border-[var(--border-strong)] bg-paper-200/60 p-1">
          {(
            [
              { id: "local" as const, icon: FolderOpenIcon, label: "Local path" },
              { id: "git" as const, icon: GlobeIcon, label: "Git URL" },
            ]
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setMode(tab.id)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-[7px] px-3 py-2 text-[12.5px] font-medium transition-all duration-150 ${
                mode === tab.id ? "bg-white text-paper-900 shadow-[0_1px_3px_rgba(27,26,24,0.1)]" : "text-paper-600 hover:text-paper-800"
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-col gap-3">
          {mode === "local" ? (
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] font-medium text-paper-800">Repository directory</span>
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/Users/you/dev/your-project"
                spellCheck={false}
                className="font-mono"
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
              <span className="text-[11px] text-paper-500">The folder containing your source code</span>
            </label>
          ) : (
            <>
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-paper-800">Git URL</span>
                <Input
                  value={gitUrl}
                  onChange={(e) => setGitUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  spellCheck={false}
                  className="font-mono"
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                />
                <span className="text-[11px] text-paper-500">
                  Shallow-cloned into the managed foray directory
                </span>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] font-medium text-paper-800">
                  Display name <span className="text-paper-400">(optional)</span>
                </span>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="repo" />
              </label>
            </>
          )}
        </div>

        <div className="mt-6 flex items-center justify-between">
          <button type="button" onClick={() => navigate("/")} className="text-[12.5px] text-paper-500 hover:text-paper-800">
            Back
          </button>
          <Button
            variant="accent"
            onClick={submit}
            disabled={submitting || (mode === "local" ? !path.trim() : !gitUrl.trim())}
          >
            {submitting ? "Starting..." : "Index repository"}
            <ArrowRightIcon className="h-3.5 w-3.5" weight="bold" />
          </Button>
        </div>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Step 3: loading state (percentage bar driven by SSE)
 * ------------------------------------------------------------------------ */

const PHASE_LABELS: Record<string, string> = {
  queued: "Queued",
  scan: "Scanning files",
  clone: "Preparing staging",
  parse: "Parsing",
  embed: "Generating embeddings",
  graph: "Building dependency graph",
  finalize: "Activating index",
  done: "Ready",
  "": "Starting",
}

export function IndexProgressBar({
  workspaceId,
  onComplete,
}: {
  workspaceId: string
  onComplete: () => void
}) {
  const [status, setStatus] = React.useState<IndexStatus>({ state: "running", phase: "queued", percent: 0, files_total: 0, files_done: 0, chunks_done: 0, embed_done: 0 })
  const reduce = useReducedMotion()

  React.useEffect(() => {
    const stop = streamIndexStatus(
      workspaceId,
      setStatus,
      () => {
        /* stream closed */
      },
      (message) => toast.error(message)
    )
    return stop
  }, [workspaceId])

  React.useEffect(() => {
    if (status.state === "done") {
      const timer = setTimeout(onComplete, 700)
      return () => clearTimeout(timer)
    }
  }, [status.state, onComplete])

  const percent = Math.max(2, Math.min(100, status.percent ?? 0))
  const phaseLabel = PHASE_LABELS[status.phase] ?? status.phase
  const detail =
    status.state === "error"
      ? status.error
      : status.phase === "embed" && status.files_total > 0
        ? `${status.embed_done} chunks embedded`
        : status.files_total > 0
          ? `${status.files_done}/${status.files_total} files`
          : status.detail || ""

  return (
    <div className="paper-grain flex min-h-[100dvh] items-center justify-center bg-paper-100 px-6">
      <div className="w-full max-w-[480px]">
        <div className="mb-6 flex items-center gap-2.5">
          <Logo />
          <span className="text-[14px] font-semibold tracking-[-0.01em] text-paper-900">foray</span>
        </div>
        <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-paper-900">Indexing repository</h1>
        <p className="mt-2 text-[13px] leading-relaxed text-paper-600">
          A static snapshot is being built with tree-sitter and your embedding engine. You can
          close this tab, indexing continues in the server.
        </p>

        <div className="mt-8">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="font-mono text-[12px] text-paper-700">{phaseLabel}</span>
            <span className="font-mono text-[22px] font-medium tabular-nums tracking-[-0.02em] text-paper-900">
              {Math.floor(percent)}%
            </span>
          </div>
          <div className="h-[7px] w-full overflow-hidden rounded-full bg-paper-300/70">
            <motion.div
              className="h-full rounded-full bg-ember-500"
              initial={false}
              animate={{ width: `${percent}%` }}
              transition={reduce ? { duration: 0 } : { duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
          <div className="mt-2.5 flex items-center justify-between font-mono text-[11px] text-paper-500">
            <span className={status.state === "error" ? "text-red-600" : ""}>{detail}</span>
            {status.elapsed != null && status.elapsed > 0 && <span>{status.elapsed}s</span>}
          </div>
        </div>

        {status.state === "error" && (
          <div className="mt-5 rounded-[10px] border border-red-500/25 bg-red-50 p-3.5 text-[12.5px] leading-relaxed text-red-700">
            {status.error}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Setup page shell: routes through the first-run steps
 * ------------------------------------------------------------------------ */

export default function SetupPage() {
  const bootstrap = useApp((s) => s.bootstrap)
  const loading = useApp((s) => s.loading)
  const navigate = useNavigate()

  React.useEffect(() => {
    if (!loading && bootstrap && !bootstrap.demo_mode) {
      const workspaces = bootstrap.workspaces ?? []
      if (workspaces.length > 0 && bootstrap.embedding_choice_made) {
        const target = bootstrap.last_workspace_id ?? workspaces[0].id
        navigate(`/workspace/${target}`, { replace: true })
      }
    }
  }, [loading, bootstrap, navigate])

  if (loading || !bootstrap) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-paper-100">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-ember-500 border-t-transparent" />
      </div>
    )
  }

  if (!bootstrap.embedding_choice_made && !bootstrap.demo_mode) {
    return <EmbeddingChoice onDone={() => useApp.getState().setLoading(false)} />
  }

  return <AddRepository />
}
