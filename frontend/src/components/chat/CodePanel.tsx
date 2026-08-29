import React from "react"
import { AnimatePresence, motion } from "motion/react"
import { FileCodeIcon, XIcon, ArrowSquareOutIcon } from "@phosphor-icons/react"

import { api } from "@/lib/api"
import { useChat } from "@/stores/app"

/* light-touch syntax tinting for the code pane */
function highlight(code: string): React.ReactNode[] {
  const lines = code.split("\n")
  return lines.map((line, i) => {
    let html = line
    html = html.replace(/(&)/g, "&amp;").replace(/(<)/g, "&lt;").replace(/(>)/g, "&gt;")
    html = html.replace(/(#[^\n]*|\/\/[^\n]*)/g, '<span class="tok-com">$1</span>')
    html = html.replace(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="tok-str">$1</span>')
    html = html.replace(
      /\b(def|class|import|from|return|async|await|function|const|let|var|export|if|else|for|while|try|except|type|interface|struct|impl|fn|pub|use|match|new|extends)\b/g,
      '<span class="tok-kw">$1</span>'
    )
    html = html.replace(/\b([A-Za-z_][\w]*)\s*\(/g, '<span class="tok-fn">$1</span>(')
    return <div key={i} className="table-row" dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }} />
  })
}

export function CodePanel({ workspaceId }: { workspaceId: string }) {
  const openCitation = useChat((s) => s.openCitation)
  const setOpenCitation = useChat((s) => s.setOpenCitation)
  const [file, setFile] = React.useState<{ path: string; start_line: number; end_line: number; total_lines: number; language: string | null; content: string; anchor: number } | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState("")

  React.useEffect(() => {
    if (!openCitation) return
    let cancelled = false
    setLoading(true)
    setError("")
    api
      .readFile(workspaceId, openCitation.path, Math.max(1, openCitation.line - 12), openCitation.line + 48)
      .then((data) => {
        if (cancelled) return
        setFile({ ...data, anchor: openCitation.line })
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError((err as Error).message)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [openCitation, workspaceId])

  const lineNumbers = React.useMemo(() => {
    if (!file) return []
    const width = String(file.end_line).length
    return Array.from({ length: file.end_line - file.start_line + 1 }, (_, i) => String(file.start_line + i).padStart(width, " "))
  }, [file])

  const anchorOffset = file ? file.anchor - file.start_line : 0

  return (
    <AnimatePresence>
      {openCitation && (
        <>
          <motion.button
            type="button"
            className="fixed inset-0 z-30 cursor-default bg-black/25"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            onClick={() => setOpenCitation(null)}
            aria-label="Close code panel"
            tabIndex={-1}
          />
          <motion.aside
            className="fixed right-0 top-0 z-40 flex h-full w-full max-w-[520px] flex-col border-l border-ink-800 bg-ink-900 shadow-[-24px_0_60px_-24px_rgba(0,0,0,0.5)]"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="flex h-12 shrink-0 items-center gap-2 border-b border-ink-800 px-4">
              <FileCodeIcon className="h-4 w-4 shrink-0 text-ember-400" />
              <span className="flex-1 truncate font-mono text-[12px] text-ink-200">
                {openCitation.path}
              </span>
              {file && (
                <span className="shrink-0 font-mono text-[10px] text-ink-600">
                  L{file.start_line}-{file.end_line} of {file.total_lines}
                </span>
              )}
              <button
                type="button"
                onClick={() => setOpenCitation(null)}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-ink-500 transition-colors hover:bg-ink-850 hover:text-ink-200"
                aria-label="Close"
              >
                <XIcon className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-auto">
              {loading && (
                <div className="flex flex-col gap-2 p-4">
                  {Array.from({ length: 14 }).map((_, i) => (
                    <div key={i} className="skeleton h-3.5 rounded" style={{ width: `${55 + ((i * 13) % 40)}%` }} />
                  ))}
                </div>
              )}
              {error && (
                <div className="p-4 text-[12.5px] leading-relaxed text-red-400">{error}</div>
              )}
              {!loading && !error && file && (
                <div className="flex p-3">
                  <div className="code-pane table shrink-0 select-none pr-3 text-right text-ink-600">
                    {lineNumbers.map((n, i) => (
                      <div
                        key={n}
                        className={`table-row ${i === anchorOffset ? "text-ember-400" : ""}`}
                      >
                        {n}
                      </div>
                    ))}
                  </div>
                  <div className="code-pane min-w-0 flex-1 table text-ink-200">
                    {highlight(file.content)}
                    {file.end_line < file.total_lines && (
                      <div className="table-row text-ink-600">
                        <span className="font-mono">... {file.total_lines - file.end_line} more lines</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {file && (
              <div className="flex h-10 shrink-0 items-center justify-between border-t border-ink-800 px-4 font-mono text-[10.5px] text-ink-500">
                <span>{file.language ?? "text"}</span>
                <span className="flex items-center gap-1">
                  <ArrowSquareOutIcon className="h-3 w-3" />
                  anchored at L{file.anchor}
                </span>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
