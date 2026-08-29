import * as React from "react"

import { cn } from "@/lib/utils"

/** Keystroke micro-UI: physical key caps for shortcuts. */
export function Kbd({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-[4px] border border-[var(--border-strong)] bg-[var(--surface-inset)] px-1 font-mono text-[10.5px] font-medium text-[var(--text-secondary)]",
        className
      )}
    >
      {children}
    </kbd>
  )
}

/** Monospaced file-path / meta label with truncated middle. */
export function FilePath({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={cn("font-mono text-[11.5px] tracking-[-0.01em] text-[var(--text-secondary)]", className)}>
      {children}
    </span>
  )
}
