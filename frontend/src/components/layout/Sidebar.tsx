import React from "react"
import { useNavigate } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import {
  ChatsIcon,
  CompassIcon,
  FileTextIcon,
  GearIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  SidebarSimpleIcon,
  ArrowClockwiseIcon,
} from "@phosphor-icons/react"
import { toast } from "sonner"

import { api, type IndexStatus, type Workspace } from "@/lib/api"
import { formatNumber, formatTime, languageDot } from "@/lib/utils"
import { useApp, type View } from "@/stores/app"
import { Kbd } from "@/components/ui/kbd"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const NAV: { view: View; icon: typeof ChatsIcon; label: string }[] = [
  { view: "chat", icon: ChatsIcon, label: "Chat" },
  { view: "map", icon: CompassIcon, label: "Repo Map" },
  { view: "docs", icon: FileTextIcon, label: "Docs" },
]

function WorkspaceSwitcher({ workspace }: { workspace: Workspace }) {
  const navigate = useNavigate()
  const workspaces = useApp((s) => s.workspaces)
  const setActiveWorkspace = useApp((s) => s.setActiveWorkspace)

  const switchTo = (id: string) => {
    if (id === workspace.id) return
    setActiveWorkspace(id)
    navigate(`/workspace/${id}`)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="group flex w-full items-center justify-between gap-2 rounded-[8px] border border-ink-800 bg-ink-900 px-2.5 py-1.5 text-left transition-colors hover:border-ink-700"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span
              className="h-2 w-2 shrink-0 rounded-full border border-white/10"
              style={{ background: languageDot(workspace.languages?.[0] ?? (workspace.stats?.languages as string[] | undefined)?.[0] ?? "") }}
              aria-hidden
            />
            <span className="truncate text-[12.5px] font-medium text-ink-100">{workspace.name}</span>
          </span>
          <span className="shrink-0 font-mono text-[10px] text-ink-500 transition-colors group-hover:text-ink-300">
            {formatNumber(Number(workspace.stats?.loc ?? 0))} loc
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[240px]">
        <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
        {workspaces
          .filter((ws) => ws.id !== workspace.id)
          .map((ws) => (
            <DropdownMenuItem key={ws.id} onClick={() => switchTo(ws.id)}>
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: languageDot(ws.languages?.[0] ?? "") }}
                aria-hidden
              />
              <span className="flex-1 truncate">{ws.name}</span>
              <span className="font-mono text-[10px] text-ink-500">{formatTime(ws.last_sync)}</span>
            </DropdownMenuItem>
          ))}
        {workspaces.filter((ws) => ws.id !== workspace.id).length === 0 && (
          <div className="px-2 py-2 text-[11.5px] text-ink-500">No other workspaces</div>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate("/setup")} className="text-ember-400">
          <PlusIcon className="h-3.5 w-3.5" />
          Add repository
        </DropdownMenuItem>
        <div className="px-2 pb-1 pt-1.5 font-mono text-[10px] text-ink-600">
          {formatNumber(Number(workspace.stats?.chunks ?? 0))} chunks indexed
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function Sidebar({
  workspace,
  status,
  onOpenSettings,
  onOpenPalette,
  onRefresh,
}: {
  workspace: Workspace
  status: IndexStatus | null
  onOpenSettings: () => void
  onOpenPalette: () => void
  onRefresh: () => void
}) {
  const view = useApp((s) => s.view)
  const setView = useApp((s) => s.setView)
  const collapsed = useApp((s) => s.sidebarCollapsed)
  const toggleSidebar = useApp((s) => s.toggleSidebar)
  const [syncing, setSyncing] = React.useState(false)

  const sync = async () => {
    if (syncing) return
    setSyncing(true)
    try {
      await api.syncWorkspace(workspace.id)
      toast.success("Re-indexing started")
      onRefresh()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSyncing(false)
    }
  }

  const running = status?.state === "running"
  const busy = syncing || running
  const progress = running ? status?.percent ?? 0 : 0

  return (
    <TooltipProvider delayDuration={350}>
      <motion.aside
        className="relative z-20 flex h-full shrink-0 flex-col border-r border-ink-800 bg-ink-900"
        animate={{ width: collapsed ? 56 : 232 }}
        transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* top: brand + collapse */}
        <div className="flex h-12 items-center gap-2 border-b border-ink-800 px-3">
          <button
            type="button"
            onClick={toggleSidebar}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-ink-500 transition-colors hover:bg-ink-850 hover:text-ink-200"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <SidebarSimpleIcon className="h-4 w-4" />
          </button>
          {!collapsed && (
            <span className="flex items-center gap-2 overflow-hidden">
              <svg width="15" height="15" viewBox="0 0 32 32" aria-hidden>
                <rect width="32" height="32" rx="7" fill="#f4f4f5" />
                <path d="M9 11.5 L16 23 L23 11.5" stroke="#f97316" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              </svg>
              <span className="text-[13px] font-semibold tracking-[-0.01em] text-ink-100">foray</span>
            </span>
          )}
        </div>

        {/* search + workspace */}
        <div className="flex flex-col gap-2 px-2.5 py-2.5">
          <button
            type="button"
            onClick={onOpenPalette}
            className={`flex h-8 items-center gap-2 rounded-[8px] border border-ink-800 bg-ink-950/60 px-2.5 text-left transition-colors hover:border-ink-700 ${
              collapsed ? "justify-center px-0" : ""
            }`}
          >
            <MagnifyingGlassIcon className="h-3.5 w-3.5 shrink-0 text-ink-500" />
            {!collapsed && (
              <>
                <span className="flex-1 truncate text-[12px] text-ink-500">Search or jump to...</span>
                <span className="flex items-center gap-0.5">
                  <Kbd>⌘</Kbd>
                  <Kbd>K</Kbd>
                </span>
              </>
            )}
          </button>
          {!collapsed && <WorkspaceSwitcher workspace={workspace} />}
          {collapsed && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => useApp.getState().setActiveWorkspace(workspace.id)}
                  className="flex h-8 items-center justify-center rounded-[8px] text-[12px] font-semibold text-ink-200"
                >
                  {workspace.name.slice(0, 2).toUpperCase()}
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">{workspace.name}</TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* middle: nav */}
        <nav className="flex flex-col gap-0.5 px-2.5">
          {NAV.map((item) => {
            const active = view === item.view
            const button = (
              <button
                type="button"
                onClick={() => setView(item.view)}
                className={`flex h-8 items-center gap-2.5 rounded-[8px] px-2.5 text-[12.5px] font-medium transition-colors duration-100 ${
                  active ? "bg-ink-850 text-ink-50" : "text-ink-400 hover:bg-ink-850/60 hover:text-ink-200"
                } ${collapsed ? "justify-center px-0" : ""}`}
              >
                <item.icon className={`h-4 w-4 shrink-0 ${active ? "text-ember-400" : ""}`} weight={active ? "fill" : "regular"} />
                {!collapsed && item.label}
              </button>
            )
            return collapsed ? (
              <Tooltip key={item.view}>
                <TooltipTrigger asChild>{button}</TooltipTrigger>
                <TooltipContent side="right">{item.label}</TooltipContent>
              </Tooltip>
            ) : (
              <React.Fragment key={item.view}>{button}</React.Fragment>
            )
          })}
        </nav>

        <div className="flex-1" />

        {/* bottom: sync + settings */}
        <div className="flex flex-col gap-1 border-t border-ink-800 p-2.5">
          {running && (
            <div className="absolute bottom-0 left-0 h-[2px] w-full bg-ink-800" aria-hidden>
              <motion.div
                className="h-full bg-ember-500"
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
          )}
          {collapsed ? (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={sync}
                    disabled={busy}
                    className="flex h-8 items-center justify-center rounded-[8px] text-ink-400 transition-colors hover:bg-ink-850 hover:text-ink-200 disabled:opacity-60"
                    aria-label="Sync index"
                  >
                    <motion.span
                      animate={busy ? { rotate: 360 } : { rotate: 0 }}
                      transition={busy ? { duration: 1.2, repeat: Infinity, ease: "linear" } : { duration: 0 }}
                    >
                      <ArrowClockwiseIcon className="h-4 w-4" />
                    </motion.span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Sync index</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onOpenSettings}
                    className="flex h-8 items-center justify-center rounded-[8px] text-ink-400 transition-colors hover:bg-ink-850 hover:text-ink-200"
                    aria-label="Settings"
                  >
                    <GearIcon className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Settings</TooltipContent>
              </Tooltip>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={sync}
                disabled={busy}
                className="flex h-8 items-center gap-2.5 rounded-[8px] px-2.5 text-[12.5px] font-medium text-ink-400 transition-colors hover:bg-ink-850 hover:text-ink-200 disabled:opacity-60"
              >
                <motion.span
                  className="flex h-4 w-4 items-center justify-center"
                  animate={busy ? { rotate: 360 } : { rotate: 0 }}
                  transition={busy ? { duration: 1.2, repeat: Infinity, ease: "linear" } : { duration: 0 }}
                >
                  <ArrowClockwiseIcon className="h-4 w-4" />
                </motion.span>
                <span className="flex-1 text-left">{busy ? "Indexing..." : "Sync index"}</span>
                <span className="font-mono text-[10px] text-ink-600">{formatTime(workspace.last_sync)}</span>
              </button>
              <button
                type="button"
                onClick={onOpenSettings}
                className="flex h-8 items-center gap-2.5 rounded-[8px] px-2.5 text-[12.5px] font-medium text-ink-400 transition-colors hover:bg-ink-850 hover:text-ink-200"
              >
                <GearIcon className="h-4 w-4" />
                Settings
              </button>
            </>
          )}
        </div>
      </motion.aside>
      <AnimatePresence>{/* reserved */}</AnimatePresence>
    </TooltipProvider>
  )
}
