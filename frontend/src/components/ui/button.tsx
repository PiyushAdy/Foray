import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-all duration-150 [transition-timing-function:var(--ease-snap)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember-500/60 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--surface)] disabled:pointer-events-none disabled:opacity-50 active:translate-y-[1px] [&_svg]:pointer-events-none [&_svg]:shrink-0 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-paper-900 text-paper-50 hover:bg-paper-800 dark:bg-ink-100 dark:text-ink-950 dark:hover:bg-white",
        accent:
          "bg-ember-600 text-white hover:bg-ember-500 shadow-[0_1px_2px_rgba(234,88,12,0.35)]",
        outline:
          "border border-[var(--border-strong)] bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-inset)]",
        ghost:
          "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-inset)] hover:text-[var(--text-primary)]",
        subtle:
          "bg-[var(--surface-inset)] text-[var(--text-primary)] hover:brightness-[1.04] dark:hover:brightness-125",
        danger:
          "bg-transparent text-red-600 dark:text-red-400 hover:bg-red-500/10 border border-red-500/30",
      },
      size: {
        default: "h-9 px-4 rounded-[8px] text-[13px]",
        sm: "h-7 px-3 rounded-[7px] text-[12px]",
        lg: "h-11 px-6 rounded-[8px] text-[14px]",
        icon: "h-8 w-8 rounded-[7px]",
        iconSm: "h-7 w-7 rounded-[6px]",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
