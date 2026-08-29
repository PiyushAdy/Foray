import * as React from "react"
import * as SelectPrimitive from "@radix-ui/react-select"
import { CaretDownIcon, CheckIcon } from "@phosphor-icons/react"

import { cn } from "@/lib/utils"

const Select = SelectPrimitive.Root
const SelectValue = SelectPrimitive.Value

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-8 items-center justify-between gap-2 rounded-[8px] border border-[var(--border-strong)] bg-[var(--surface)] px-2.5 text-[12.5px] text-[var(--text-primary)] transition-colors duration-150 hover:border-[var(--border-strong)] focus:outline-none focus:ring-2 focus:ring-ember-500/30 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:truncate",
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <CaretDownIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
))
SelectTrigger.displayName = "SelectTrigger"

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      position={position}
      sideOffset={4}
      className={cn(
        "z-[60] max-h-72 min-w-[9rem] overflow-hidden rounded-[8px] border border-[var(--border-strong)] bg-[var(--surface-raised)] shadow-[0_12px_40px_-10px_rgba(0,0,0,0.35)]",
        className
      )}
      {...props}
    >
      <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
))
SelectContent.displayName = "SelectContent"

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex cursor-default select-none items-center rounded-[6px] py-1.5 pl-7 pr-3 text-[12.5px] text-[var(--text-primary)] outline-none transition-colors data-[highlighted]:bg-[var(--surface-inset)] data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <CheckIcon className="h-3 w-3 text-ember-500" weight="bold" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
))
SelectItem.displayName = "SelectItem"

const SelectLabel = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Label>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Label>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.Label
    ref={ref}
    className={cn("px-2 py-1.5 text-[10.5px] font-medium uppercase tracking-[0.14em] text-[var(--text-tertiary)]", className)}
    {...props}
  />
))
SelectLabel.displayName = "SelectLabel"

export { Select, SelectValue, SelectTrigger, SelectContent, SelectItem, SelectLabel }
