import * as React from "react"
import * as SwitchPrimitive from "@radix-ui/react-switch"

import { cn } from "@/lib/utils"

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    className={cn(
      "peer inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full border border-[var(--border-strong)] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ember-500/40 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-ember-600 data-[state=unchecked]:bg-[var(--surface-inset)]",
      className
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitive.Thumb
      className={cn(
        "pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-150 [transition-timing-function:var(--ease-snap)] data-[state=checked]:translate-x-[15px] data-[state=unchecked]:translate-x-[1.5px]"
      )}
    />
  </SwitchPrimitive.Root>
))
Switch.displayName = "Switch"

export { Switch }
