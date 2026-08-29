import * as React from "react"

import { cn } from "@/lib/utils"

/** Monospaced citation badge, e.g. [server.py:L12]. Clickable. */
export function CitationBadge({
  path,
  line,
  onClick,
  className,
}: {
  path: string
  line: number
  onClick?: () => void
  className?: string
}) {
  const short = path.split("/").pop() ?? path
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${path}:L${line}`}
      className={cn(
        "inline-flex max-w-[220px] items-center gap-1 rounded-full border border-ember-600/30 bg-ember-600/10 px-2 py-[1px] font-mono text-[10.5px] text-ember-700 dark:border-ember-500/25 dark:bg-ember-500/10 dark:text-ember-300 transition-colors duration-150 hover:bg-ember-600/20 dark:hover:bg-ember-500/20",
        onClick ? "cursor-pointer" : "cursor-default",
        className
      )}
    >
      <span className="truncate">{short}</span>
      <span className="shrink-0 opacity-70">:L{line}</span>
    </button>
  )
}

/** Small pill label for languages / meta. */
export function Pill({
  className,
  children,
  tone = "neutral",
}: {
  className?: string
  children: React.ReactNode
  tone?: "neutral" | "ember" | "green"
}) {
  const tones = {
    neutral: "border-[var(--border-strong)] text-[var(--text-secondary)]",
    ember: "border-ember-600/30 bg-ember-600/10 text-ember-700 dark:text-ember-300",
    green: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-300",
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-[2px] text-[10.5px] font-medium",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  )
}
