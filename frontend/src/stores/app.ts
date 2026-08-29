import { create } from "zustand"

import type { Bootstrap, ChatMessage, Workspace } from "@/lib/api"

export type View = "chat" | "map" | "docs"

interface AppState {
  bootstrap: Bootstrap | null
  workspaces: Workspace[]
  activeWorkspaceId: string | null
  view: View
  theme: "light" | "dark"
  sidebarCollapsed: boolean
  chatSessionCost: number
  chatSessionTokens: number
  loading: boolean

  setBootstrap: (b: Bootstrap) => void
  setWorkspaces: (ws: Workspace[]) => void
  setActiveWorkspace: (id: string | null) => void
  setView: (v: View) => void
  setTheme: (t: "light" | "dark") => void
  toggleSidebar: () => void
  addSessionCost: (tokens: number) => void
  resetSessionCost: () => void
  setLoading: (v: boolean) => void
}

const THEME_KEY = "foray.theme"

function initialTheme(): "light" | "dark" {
  const saved = localStorage.getItem(THEME_KEY)
  if (saved === "light" || saved === "dark") return saved
  /* The core workspace is a strict dark environment by design;
     public pages render a fixed warm-paper palette either way. */
  return "dark"
}

export function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark")
  document.documentElement.style.colorScheme = theme
}

export const useApp = create<AppState>((set) => ({
  bootstrap: null,
  workspaces: [],
  activeWorkspaceId: null,
  view: "chat",
  theme: initialTheme(),
  sidebarCollapsed: false,
  chatSessionCost: 0,
  chatSessionTokens: 0,
  loading: true,

  setBootstrap: (b) =>
    set({
      bootstrap: b,
      workspaces: b.workspaces ?? [],
      activeWorkspaceId: b.last_workspace_id ?? null,
    }),
  setWorkspaces: (ws) => set({ workspaces: ws }),
  setActiveWorkspace: (id) => set({ activeWorkspaceId: id, chatSessionCost: 0, chatSessionTokens: 0 }),
  setView: (v) => set({ view: v }),
  setTheme: (t) => {
    localStorage.setItem(THEME_KEY, t)
    applyTheme(t)
    set({ theme: t })
  },
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  addSessionCost: (tokens) =>
    set((s) => ({
      chatSessionTokens: s.chatSessionTokens + tokens,
      chatSessionCost: s.chatSessionCost + tokens / 1_000_000 * 0.4,
    })),
  resetSessionCost: () => set({ chatSessionCost: 0, chatSessionTokens: 0 }),
  setLoading: (v) => set({ loading: v }),
}))

/* ---------------------------------------------------------------------------
 * Ephemeral chat store. Chat history is intentionally NOT persisted:
 * it resets on reload to keep the app fast and stateless.
 * ------------------------------------------------------------------------ */

interface ChatState {
  messages: ChatMessage[]
  streaming: boolean
  openCitation: { path: string; line: number } | null

  addMessage: (m: ChatMessage) => void
  appendToken: (id: string, text: string) => void
  finishMessage: (id: string, patch: Partial<ChatMessage>) => void
  setStreaming: (v: boolean) => void
  setOpenCitation: (c: { path: string; line: number } | null) => void
  reset: () => void
}

export const useChat = create<ChatState>((set) => ({
  messages: [],
  streaming: false,
  openCitation: null,

  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  appendToken: (id, text) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content: m.content + text } : m)),
    })),
  finishMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch, streaming: false } : m)),
    })),
  setStreaming: (v) => set({ streaming: v }),
  setOpenCitation: (c) => set({ openCitation: c }),
  reset: () => set({ messages: [], streaming: false, openCitation: null }),
}))
