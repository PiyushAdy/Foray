import React from "react"
import { FileTextIcon, LightningIcon, ArrowClockwiseIcon } from "@phosphor-icons/react"
import { toast } from "sonner"

import { api, loadByok, type DocEstimate } from "@/lib/api"
import { formatCost, formatTime } from "@/lib/utils"

/* Minimal markdown renderer for the onboarding doc: h1-h3, code, lists, bold, inline code */
function DocMarkdown({ text }: { text: string }) {
  const blocks = text.split(/```/)
  return (
    <div className="flex flex-col gap-3">
      {blocks.map((block, i) => {
        if (i % 2 === 1) {
          return (
            <pre key={i} className="code-pane overflow-x-auto rounded-[8px] border border-ink-800 bg-ink-950 p-3.5 text-ink-200">
              <code>{block.replace(/^\w+\n/, "").replace(/\n$/, "")}</code>
            </pre>
          )
        }
        const lines = block.split("\n")
        return (
          <React.Fragment key={i}>
            {lines.map((line, j) => {
              const trimmed = line.trim()
              if (trimmed.startsWith("# ") || trimmed.startsWith("## ")) {
                return (
                  <h2 key={j} className="mt-4 text-[16px] font-semibold tracking-[-0.015em] text-ink-50">
                    {trimmed.replace(/^#+\s+/, "")}
                  </h2>
                )
              }
              if (trimmed.startsWith("### ")) {
                return (
                  <h3 key={j} className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-ink-500">
                    {trimmed.slice(4)}
                  </h3>
                )
              }
              if (/^[-*]\s/.test(trimmed)) {
                return (
                  <div key={j} className="flex gap-2.5 text-[13px] leading-relaxed text-ink-300">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-600" aria-hidden />
                    <span>{inline(trimmed.replace(/^[-*]\s+/, ""))}</span>
                  </div>
                )
              }
              if (trimmed.startsWith("|")) {
                return (
                  <div key={j} className="font-mono text-[11.5px] leading-relaxed text-ink-300">
                    {line}
                  </div>
                )
              }
              if (!trimmed) return <div key={j} className="h-1.5" />
              return <p key={j} className="text-[13px] leading-relaxed text-ink-300">{inline(trimmed)}</p>
            })}
          </React.Fragment>
        )
      })}
    </div>
  )
}

function inline(text: string): React.ReactNode {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="rounded-[4px] border border-ink-700/60 bg-ink-850 px-1 py-[1px] font-mono text-[11.5px] text-ink-200">
          {part.slice(1, -1)}
        </code>
      )
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-ink-100">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return part
  })
}

export function DocsView({ workspaceId }: { workspaceId: string }) {
  const [docs, setDocs] = React.useState<{ content: string; model: string; created: number } | null>(null)
  const [estimate, setEstimate] = React.useState<DocEstimate | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [generating, setGenerating] = React.useState(false)

  const load = React.useCallback(() => {
    setLoading(true)
    api
      .getDocs(workspaceId)
      .then((r) => {
        setDocs(r.docs)
        setEstimate(r.estimate)
      })
      .catch((err) => toast.error((err as Error).message))
      .finally(() => setLoading(false))
  }, [workspaceId])

  React.useEffect(load, [load])

  const generate = async () => {
    setGenerating(true)
    try {
      const result = await api.generateDocs(workspaceId, loadByok() ?? undefined)
      setDocs({ content: result.content, model: result.model, created: result.created })
      toast.success(`Onboarding guide generated (~${formatCost(result.cost_usd)})`)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-800 px-5">
        <FileTextIcon className="h-4 w-4 text-ember-400" />
        <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink-100">Onboarding docs</h2>
        {docs && (
          <span className="font-mono text-[10.5px] text-ink-500">
            {docs.model} · generated {formatTime(docs.created)}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {docs && (
            <button
              type="button"
              onClick={generate}
              disabled={generating}
              className="flex h-7 items-center gap-1.5 rounded-[6px] border border-ink-700 px-2.5 text-[11.5px] text-ink-300 transition-colors hover:border-ink-600 hover:text-ink-100 disabled:opacity-50"
            >
              <ArrowClockwiseIcon className="h-3 w-3" />
              Regenerate
            </button>
          )}
          <button
            type="button"
            onClick={generate}
            disabled={generating || !estimate}
            className="flex h-7 items-center gap-1.5 rounded-[6px] bg-ember-600 px-3 text-[11.5px] font-medium text-white transition-colors hover:bg-ember-500 disabled:opacity-50"
          >
            <LightningIcon className="h-3 w-3" weight="fill" />
            {generating ? "Generating..." : docs ? "Refresh guide" : "Generate docs"}
            {!docs && estimate && (
              <span className="font-mono text-[10px] opacity-80">≈{formatCost(estimate.cost_usd)}</span>
            )}
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && (
          <div className="mx-auto flex w-full max-w-[640px] flex-col gap-3 p-6">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="skeleton h-3.5 rounded" style={{ width: `${50 + ((i * 17) % 45)}%` }} />
            ))}
          </div>
        )}
        {!loading && !docs && (
          <div className="mx-auto flex w-full max-w-[560px] flex-col items-start gap-4 px-6 py-16">
            <h3 className="text-[19px] font-semibold tracking-[-0.015em] text-ink-50">
              No onboarding guide yet
            </h3>
            <p className="max-w-[60ch] text-[13px] leading-relaxed text-ink-400">
              Generate a guide that explains this repository's core structure, entry points and key
              modules, written from the live index. Generation runs only when you ask for it, and
              the result is cached until the next sync.
            </p>
            {estimate && (
              <div className="flex items-center gap-2.5 rounded-[8px] border border-ink-800 bg-ink-900 px-3.5 py-2.5">
                <span className="font-mono text-[11px] text-ink-500">
                  est. {estimate.tokens.toLocaleString()} tokens
                </span>
                <span className="h-3 w-px bg-ink-700" aria-hidden />
                <span className="font-mono text-[11px] text-ember-400">
                  ≈{formatCost(estimate.cost_usd)} ({estimate.provider})
                </span>
              </div>
            )}
          </div>
        )}
        {!loading && docs && (
          <div className="mx-auto w-full max-w-[640px] px-6 py-8">
            <DocMarkdown text={docs.content} />
          </div>
        )}
      </div>
    </div>
  )
}
