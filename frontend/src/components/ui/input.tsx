import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.ComponentPropsWithoutRef<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-[8px] border border-[var(--border-strong)] bg-[var(--surface)] px-3 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] transition-colors duration-150 focus-visible:outline-none focus-visible:border-ember-500/70 focus-visible:ring-2 focus-visible:ring-ember-500/25 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentPropsWithoutRef<"textarea">>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex w-full rounded-[8px] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-[13px] leading-relaxed text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] transition-colors duration-150 focus-visible:outline-none focus-visible:border-ember-500/70 focus-visible:ring-2 focus-visible:ring-ember-500/25 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Textarea.displayName = "Textarea"

export { Input, Textarea }
