import React from "react"
import { useNavigate } from "react-router-dom"
import { Command } from "cmdk"
import {
  ArrowClockwiseIcon,
  ChatsIcon,
  CompassIcon,
  FileTextIcon,
  GearIcon,
  PlusIcon,
  MagnifyingGlassIcon,
} from "@phosphor-icons/react"

import { api } from "@/lib/api"
import { useApp, useChat } from "@/stores/app"
import { Dialog, DialogContent } from "@/components/ui/dialog"

export function CommandPalette({
  open,
  onOpenChange,
  onOpenSettings,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onOpenSettings: () => void
}) {
  const navigate = useNavigate()
  const workspaces = useApp((s) => s.workspaces)
  const activeWorkspaceId = useApp((s) => s.activeWorkspaceId)
  const setView = useApp((s) => s.setView)
  const [results, setResults] = React.useState<{ path: string; start_line: number; snippet: string }[]>([])
  const [searching, setSearching] = React.useState(false)

  const runSearch = React.useCallback((query: string) => {
    if (!query.trim() || query.startsWith(">") || !activeWorkspaceId) {
      setResults([])
      return
    }
    setSearching(true)
    const timer = setTimeout(() => {
      api
        .search(activeWorkspaceId, query, 6)
        .then((r) => {
          setResults(
            r.results.map((hit) => ({
              path: hit.path,
              start_line: hit.start_line,
              snippet: hit.content.split("\n").slice(0, 2).join(" ").slice(0, 110),
            }))
          )
        })
        .catch(() => setResults([]))
        .finally(() => setSearching(false))
    }, 220)
    return () => clearTimeout(timer)
  }, [activeWorkspaceId])

  const openResult = (path: string, line: number) => {
    onOpenChange(false)
    useChat.getState().setOpenCitation({ path, line })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[18%] max-w-[560px] translate-y-0 p-0">
        <Command
          className="flex h-full flex-col overflow-hidden rounded-[12px]"
          onKeyDown={(e) => e.key === "Escape" && onOpenChange(false)}
        >
          <div className="flex items-center gap-2.5 border-b border-[var(--border-hair)] px-4">
            <MagnifyingGlassIcon className="h-4 w-4 text-[var(--text-tertiary)]" />
            <Command.Input
              autoFocus
              placeholder="Search code or jump to..."
              onValueChange={runSearch}
              className="h-11 flex-1 bg-transparent text-[13.5px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none"
            />
            {searching && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ember-500 border-t-transparent" />}
          </div>
          <Command.List className="max-h-[380px] overflow-y-auto p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-[12.5px] text-[var(--text-tertiary)]">
              No results found
            </Command.Empty>

            {results.length > 0 && (
              <Command.Group heading="Code results" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.14em] [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]">
                {results.map((r) => (
                  <Command.Item
                    key={`${r.path}:${r.start_line}`}
                    value={`${r.path} ${r.snippet}`}
                    onSelect={() => openResult(r.path, r.start_line)}
                    className="flex cursor-pointer items-start gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
                  >
                    <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ember-500/70" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-[11.5px] text-[var(--text-primary)]">
                        {r.path}
                        <span className="text-[var(--text-tertiary)]">:L{r.start_line}</span>
                      </span>
                      <span className="mt-0.5 block truncate font-mono text-[10.5px] text-[var(--text-tertiary)]">
                        {r.snippet}
                      </span>
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            <Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.14em] [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]">
              <Command.Item
                value="goto chat"
                onSelect={() => {
                  setView("chat")
                  onOpenChange(false)
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <ChatsIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Chat
              </Command.Item>
              <Command.Item
                value="goto repo map"
                onSelect={() => {
                  setView("map")
                  onOpenChange(false)
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <CompassIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Repo map
              </Command.Item>
              <Command.Item
                value="goto docs"
                onSelect={() => {
                  setView("docs")
                  onOpenChange(false)
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <FileTextIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Onboarding docs
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.14em] [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]">
              <Command.Item
                value="sync index"
                onSelect={() => {
                  onOpenChange(false)
                  if (activeWorkspaceId) {
                    api.syncWorkspace(activeWorkspaceId).catch(() => undefined)
                  }
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <ArrowClockwiseIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Sync index
              </Command.Item>
              <Command.Item
                value="open settings"
                onSelect={() => {
                  onOpenChange(false)
                  onOpenSettings()
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <GearIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Settings
              </Command.Item>
              <Command.Item
                value="add repository"
                onSelect={() => {
                  onOpenChange(false)
                  navigate("/setup")
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
              >
                <PlusIcon className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
                Add repository
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Workspaces" className="[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.14em] [&_[cmdk-group-heading]]:text-[var(--text-tertiary)]">
              {workspaces.map((ws) => (
                <Command.Item
                  key={ws.id}
                  value={`workspace ${ws.name}`}
                  onSelect={() => {
                    onOpenChange(false)
                    navigate(`/workspace/${ws.id}`)
                  }}
                  className="flex cursor-pointer items-center gap-2.5 rounded-[7px] px-2.5 py-2 text-[12.5px] data-[selected=true]:bg-[var(--surface-inset)]"
                >
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: ws.id === activeWorkspaceId ? "#f97316" : "var(--text-tertiary)" }}
                    aria-hidden
                  />
                  <span className="flex-1 truncate">{ws.name}</span>
                  {ws.id === activeWorkspaceId && (
                    <span className="font-mono text-[10px] text-ember-500">active</span>
                  )}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
