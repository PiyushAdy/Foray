import React from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowUpIcon, ChatsIcon, PaperPlaneRightIcon, SparkleIcon } from "@phosphor-icons/react"
import { toast } from "sonner"

import { loadByok, streamChat, type ChatMessage, type Workspace } from "@/lib/api"
import { formatCost } from "@/lib/utils"
import { useApp, useChat } from "@/stores/app"
import { CitationBadge } from "@/components/ui/badge"
import { Kbd } from "@/components/ui/kbd"

const CITE_RE = /\[([^\]\n:]+?):L(\d+)\]/g

/** Render assistant text with live citation badges. */
function RichAnswer({
  text,
  onCitation,
  streaming,
}: {
  text: string
  onCitation: (path: string, line: number) => void
  streaming: boolean
}) {
  const parts: React.ReactNode[] = []
  let cursor = 0
  let key = 0
  for (const match of text.matchAll(CITE_RE)) {
    const start = match.index ?? 0
    if (start > cursor) parts.push(<span key={key++}>{text.slice(cursor, start)}</span>)
    parts.push(
      <CitationBadge
        key={key++}
        path={match[1]}
        line={Number(match[2])}
        onClick={() => onCitation(match[1], Number(match[2]))}
        className="mx-0.5 align-baseline"
      />
    )
    cursor = start + match[0].length
  }
  if (cursor < text.length) parts.push(<span key={key++}>{text.slice(cursor)}</span>)
  return (
    <div
      className={`prose-answer text-[13.5px] leading-[1.75] text-ink-200 ${streaming ? "stream-caret" : ""}`}
    >
      {parts}
    </div>
  )
}

function CodeFence({ children }: { children: string }) {
  return (
    <pre className="code-pane my-2 overflow-x-auto rounded-[8px] border border-ink-800 bg-ink-950 p-3 text-ink-200">
      <code>{children}</code>
    </pre>
  )
}

/** Minimal markdown: paragraphs, code fences, inline code, bold. */
function Markdownish({
  text,
  onCitation,
  streaming,
}: {
  text: string
  onCitation: (path: string, line: number) => void
  streaming: boolean
}) {
  const blocks = text.split(/```/)
  return (
    <div className="flex flex-col gap-1.5">
      {blocks.map((block, i) => {
        if (i % 2 === 1) {
          const firstBreak = block.indexOf("\n")
          const body = firstBreak >= 0 ? block.slice(firstBreak + 1) : block
          return <CodeFence key={i}>{body.replace(/\n$/, "")}</CodeFence>
        }
        const html = block
          .split("\n\n")
          .map((para) => para.trim())
          .filter(Boolean)
        return (
          <React.Fragment key={i}>
            {html.map((para, j) => (
              <RichAnswer key={j} text={para} onCitation={onCitation} streaming={streaming && i === blocks.length - 1 && j === html.length - 1} />
            ))}
          </React.Fragment>
        )
      })}
    </div>
  )
}

const SUGGESTIONS = [
  "What does this codebase do?",
  "Where is the main entry point?",
  "How does error handling work?",
  "Explain the core data model",
]

function EmptyState({ onPick, workspace }: { onPick: (q: string) => void; workspace: Workspace }) {
  const loc = Number(workspace.stats?.loc ?? 0)
  const files = Number(workspace.stats?.files ?? 0)
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-10">
      <div className="w-full max-w-[560px]">
        <div className="mb-1.5 flex items-center gap-2 font-mono text-[11px] text-ink-500">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
          index ready · {files} files · {(loc / 1000).toFixed(1)}k loc
        </div>
        <h2 className="text-[22px] font-semibold tracking-[-0.02em] text-ink-50">
          Ask anything about {workspace.name}
        </h2>
        <p className="mt-2 max-w-[60ch] text-[13px] leading-relaxed text-ink-400">
          Answers are grounded in the indexed source. Citations open the exact file and line in the
          side panel.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onPick(s)}
              className="rounded-full border border-ink-700 bg-ink-900 px-3.5 py-1.5 text-[12px] text-ink-300 transition-all duration-150 hover:border-ink-600 hover:bg-ink-850 hover:text-ink-100"
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function MessageBubble({
  message,
  onCitation,
}: {
  message: ChatMessage
  onCitation: (path: string, line: number) => void
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] rounded-[12px] rounded-br-[4px] border border-ink-700/50 bg-ink-850 px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink-100">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="group max-w-full">
      <div className="mb-1 flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-ember-600/15">
          <SparkleIcon className="h-3 w-3 text-ember-400" weight="fill" />
        </span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-500">foray</span>
        {message.tokens != null && message.tokens > 0 && (
          <span className="ml-auto font-mono text-[10px] text-ink-600">
            ~{message.tokens} tok · {formatCost(message.tokens / 1_000_000 * 0.4)}
          </span>
        )}
      </div>
      {message.error ? (
        <div className="rounded-[8px] border border-red-500/25 bg-red-500/5 px-3 py-2.5 text-[12.5px] leading-relaxed text-red-300">
          {message.error}
        </div>
      ) : (
        <Markdownish text={message.content} onCitation={onCitation} streaming={Boolean(message.streaming)} />
      )}
    </div>
  )
}

export function ChatView({
  workspaceId,
  workspace,
  onOpenPalette,
}: {
  workspaceId: string
  workspace: Workspace
  onOpenPalette: () => void
}) {
  const messages = useChat((s) => s.messages)
  const streaming = useChat((s) => s.streaming)
  const addMessage = useChat((s) => s.addMessage)
  const appendToken = useChat((s) => s.appendToken)
  const finishMessage = useChat((s) => s.finishMessage)
  const setStreaming = useChat((s) => s.setStreaming)
  const setOpenCitation = useChat((s) => s.setOpenCitation)
  const addSessionCost = useApp((s) => s.addSessionCost)
  const sessionTokens = useApp((s) => s.chatSessionTokens)

  const [draft, setDraft] = React.useState("")
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  const abortRef = React.useRef<(() => void) | null>(null)

  React.useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  const send = (question: string) => {
    const text = question.trim()
    if (!text || streaming) return
    setDraft("")

    const history = messages
      .filter((m) => !m.error)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content }))

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: text }
    const assistantId = `a-${Date.now()}`
    addMessage(userMsg)
    addMessage({ id: assistantId, role: "assistant", content: "", streaming: true })
    setStreaming(true)

    const stop = streamChat(
      workspaceId,
      text,
      history,
      {
        onToken: (tok) => appendToken(assistantId, tok),
        onDone: (payload) => {
          finishMessage(assistantId, {
            content: payload.text,
            citations: payload.citations,
            tokens: payload.tokens,
            contextCount: payload.contextCount,
          })
          addSessionCost(payload.tokens)
          setStreaming(false)
          abortRef.current = null
        },
        onError: (message) => {
          finishMessage(assistantId, { error: message })
          setStreaming(false)
          abortRef.current = null
          toast.error(message)
        },
      },
      loadByok() ?? undefined
    )
    abortRef.current = stop
  }

  const stopStreaming = () => {
    abortRef.current?.()
    abortRef.current = null
    const last = messages[messages.length - 1]
    if (last?.streaming) finishMessage(last.id, { content: last.content, error: undefined })
    setStreaming(false)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send(draft)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* transcript */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onPick={send} workspace={workspace} />
        ) : (
          <div className="mx-auto flex w-full max-w-[720px] flex-col gap-7 px-6 py-8">
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                onCitation={(path, line) => setOpenCitation({ path, line })}
              />
            ))}
          </div>
        )}
      </div>

      {/* composer: sticks to bottom */}
      <div className="shrink-0 border-t border-ink-800 bg-ink-900/40 backdrop-blur-sm">
        <div className="mx-auto w-full max-w-[720px] px-6 py-3.5">
          <div className="flex items-end gap-2.5 rounded-[12px] border border-ink-700 bg-ink-950 p-2.5 transition-colors focus-within:border-ink-600">
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={`Ask about ${workspace.name}...`}
              rows={1}
              className="max-h-[180px] min-h-[22px] flex-1 resize-none bg-transparent text-[13.5px] leading-relaxed text-ink-100 placeholder:text-ink-600 focus:outline-none"
              style={{ height: "auto" }}
              onInput={(e) => {
                const el = e.currentTarget
                el.style.height = "auto"
                el.style.height = `${Math.min(el.scrollHeight, 180)}px`
              }}
            />
            {streaming ? (
              <button
                type="button"
                onClick={stopStreaming}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] border border-ink-700 text-ink-300 transition-colors hover:border-ink-600 hover:text-ink-100"
                aria-label="Stop generating"
              >
                <span className="h-2.5 w-2.5 rounded-[2px] bg-current" />
              </button>
            ) : (
              <motion.button
                type="button"
                onClick={() => send(draft)}
                disabled={!draft.trim()}
                whileTap={{ scale: 0.94 }}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] bg-ember-600 text-white transition-colors hover:bg-ember-500 disabled:opacity-30"
                aria-label="Send message"
              >
                <ArrowUpIcon className="h-4 w-4" weight="bold" />
              </motion.button>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between px-1">
            <span className="flex items-center gap-1.5 font-mono text-[10.5px] text-ink-600">
              <ChatsIcon className="h-3 w-3" />
              ephemeral session · resets on reload
              {sessionTokens > 0 && (
                <span className="text-ink-500">· ~{sessionTokens} tok this session</span>
              )}
            </span>
            <button
              type="button"
              onClick={onOpenPalette}
              className="flex items-center gap-1 font-mono text-[10.5px] text-ink-600 transition-colors hover:text-ink-400"
            >
              <Kbd>⌘</Kbd>
              <Kbd>K</Kbd>
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence>{/* keep motion import used for composer button */}</AnimatePresence>
      <span className="hidden">
        <PaperPlaneRightIcon />
      </span>
    </div>
  )
}
