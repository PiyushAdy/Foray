import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { Toaster } from "sonner"

import "@/index.css"

import { api } from "@/lib/api"
import { applyTheme, useApp } from "@/stores/app"
import HomePage from "@/components/home/HomePage"
import SetupPage from "@/components/setup/SetupPage"
import WorkspacePage from "@/components/layout/WorkspacePage"

function BootstrapGate({ children }: { children: React.ReactNode }) {
  const theme = useApp((s) => s.theme)
  React.useEffect(() => {
    applyTheme(theme)
  }, [theme])
  React.useEffect(() => {
    let cancelled = false
    api
      .bootstrap()
      .then((b) => {
        if (cancelled) return
        useApp.getState().setBootstrap(b)
        useApp.getState().setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        useApp.getState().setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])
  return (
    <>
      {children}
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "var(--surface-raised)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-strong)",
            borderRadius: "10px",
            fontSize: "13px",
            fontFamily: "var(--font-sans)",
          },
        }}
      />
    </>
  )
}

function RootRedirect() {
  const loading = useApp((s) => s.loading)
  if (loading) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-paper-100 dark:bg-ink-950">
        <div className="flex items-center gap-3 text-[13px] text-[var(--text-secondary)]">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-ember-500 border-t-transparent" />
          Loading Foray
        </div>
      </div>
    )
  }
  /* The homepage always renders first: hero, terminal block, demo grid.
     "Enter Workspace" routes on to setup (0 repos) or the last workspace. */
  return <HomePage />
}

function App() {
  return (
    <BrowserRouter>
      <BootstrapGate>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/home" element={<HomePage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/workspace/:id" element={<WorkspacePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BootstrapGate>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
