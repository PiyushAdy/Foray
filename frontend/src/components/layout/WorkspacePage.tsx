import React from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { toast } from "sonner"

import { api, streamIndexStatus, type IndexStatus, type Workspace } from "@/lib/api"
import { useApp, useChat } from "@/stores/app"
import { Sidebar } from "@/components/layout/Sidebar"
import { ChatView } from "@/components/chat/ChatView"
import { CodePanel } from "@/components/chat/CodePanel"
import { MapView } from "@/components/map/MapView"
import { DocsView } from "@/components/docs/DocsView"
import { SettingsModal } from "@/components/settings/SettingsModal"
import { CommandPalette } from "@/components/palette/CommandPalette"

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const view = useApp((s) => s.view)
  const setActiveWorkspace = useApp((s) => s.setActiveWorkspace)
  const setWorkspaces = useApp((s) => s.setWorkspaces)
  const resetChat = useChat((s) => s.reset)

  const [workspace, setWorkspace] = React.useState<Workspace | null>(null)
  const [status, setStatus] = React.useState<IndexStatus | null>(null)
  const [settingsOpen, setSettingsOpen] = React.useState(false)
  const [paletteOpen, setPaletteOpen] = React.useState(false)
  const [loadError, setLoadError] = React.useState("")

  const workspaceId = id ?? ""

  const refresh = React.useCallback(async () => {
    try {
      const detail = await api.workspace(workspaceId)
      setWorkspace(detail)
      setStatus(detail.status)
      setActiveWorkspace(workspaceId)
    } catch (err) {
      setLoadError((err as Error).message)
    }
  }, [workspaceId, setActiveWorkspace])

  React.useEffect(() => {
    if (!workspaceId) return
    resetChat()
    setWorkspace(null)
    setLoadError("")
    refresh()
    const list = api.listWorkspaces().then((r) => setWorkspaces(r.workspaces)).catch(() => undefined)
    return () => {
      void list
    }
  }, [workspaceId, resetChat, refresh, setWorkspaces])

  /* live indexing progress while a sync runs */
  React.useEffect(() => {
    if (!workspaceId || status?.state !== "running") return
    const stop = streamIndexStatus(
      workspaceId,
      (payload) => {
        setStatus(payload)
        if (payload.state === "done") {
          toast.success("Index updated")
          refresh()
        } else if (payload.state === "error") {
          refresh()
        }
      },
      () => {
        /* stream ended; final refresh picks up terminal state */
        refresh()
      },
      (message) => toast.error(message)
    )
    return stop
  }, [workspaceId, status?.state, refresh])

  /* global ⌘K */
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  if (loadError) {
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 bg-ink-950 text-center">
        <p className="text-[14px] text-ink-300">{loadError}</p>
        <button
          type="button"
          onClick={() => navigate("/")}
          className="rounded-[8px] border border-ink-700 px-4 py-2 text-[12.5px] text-ink-200 hover:bg-ink-900"
        >
          Back to home
        </button>
      </div>
    )
  }

  if (!workspace) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-ink-950">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-ember-500 border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-ink-950 text-ink-100">
      <Sidebar
        workspace={workspace}
        status={status}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenPalette={() => setPaletteOpen(true)}
        onRefresh={refresh}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <AnimatePresence mode="wait">
          {view === "chat" && (
            <motion.div
              key="chat"
              className="flex min-h-0 flex-1 flex-col"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
            >
              <ChatView workspaceId={workspaceId} workspace={workspace} onOpenPalette={() => setPaletteOpen(true)} />
            </motion.div>
          )}
          {view === "map" && (
            <motion.div
              key="map"
              className="flex min-h-0 flex-1 flex-col"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
            >
              <MapView workspaceId={workspaceId} workspace={workspace} />
            </motion.div>
          )}
          {view === "docs" && (
            <motion.div
              key="docs"
              className="flex min-h-0 flex-1 flex-col overflow-hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
            >
              <DocsView workspaceId={workspaceId} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <CodePanel workspaceId={workspaceId} />

      <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} onWorkspaceDeleted={() => navigate("/setup")} />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onOpenSettings={() => setSettingsOpen(true)} />
    </div>
  )
}
