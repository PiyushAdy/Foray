import React from "react"
import { useNavigate } from "react-router-dom"
import { TrashIcon, ArrowSquareOutIcon } from "@phosphor-icons/react"
import { toast } from "sonner"

import { api, type CostBucket } from "@/lib/api"
import { formatCost, formatTime } from "@/lib/utils"
import { useApp } from "@/stores/app"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-[var(--border-hair)] pt-4 first:border-t-0 first:pt-0">
      <h3 className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-[var(--text-primary)]">{label}</span>
      {children}
      {hint && <span className="text-[11px] leading-relaxed text-[var(--text-tertiary)]">{hint}</span>}
    </label>
  )
}

export function SettingsModal({
  open,
  onOpenChange,
  onWorkspaceDeleted,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onWorkspaceDeleted: () => void
}) {
  const navigate = useNavigate()
  const theme = useApp((s) => s.theme)
  const setTheme = useApp((s) => s.setTheme)
  const bootstrap = useApp((s) => s.bootstrap)
  const workspaces = useApp((s) => s.workspaces)
  const sessionCost = useApp((s) => s.chatSessionCost)
  const sessionTokens = useApp((s) => s.chatSessionTokens)

  const llm = bootstrap?.llm
  const [provider, setProvider] = React.useState(llm?.provider ?? "openai")
  const [model, setModel] = React.useState(llm?.model ?? "gpt-4o-mini")
  const [apiKey, setApiKey] = React.useState("")
  const [apiBase, setApiBase] = React.useState(llm?.api_base ?? "")
  const [models, setModels] = React.useState<Record<string, string[]>>({})
  const [costs, setCosts] = React.useState<{ indexing: CostBucket; docs: CostBucket } | null>(null)
  const [saving, setSaving] = React.useState(false)
  const [ignoreFolders, setIgnoreFolders] = React.useState("")
  const [maxFileSize, setMaxFileSize] = React.useState(512)

  React.useEffect(() => {
    if (!open) return
    api.models().then((r) => setModels(r.providers)).catch(() => undefined)
    const ws = useApp.getState().activeWorkspaceId
    if (ws) api.costs(ws).then(setCosts).catch(() => undefined)
    const idx = bootstrap?.indexing
    if (idx) {
      setIgnoreFolders(idx.ignore_folders.join(", "))
      setMaxFileSize(idx.max_file_size_kb)
    }
  }, [open, bootstrap?.indexing])

  const save = async () => {
    setSaving(true)
    try {
      await api.updateConfig({
        llm: {
          provider,
          model,
          api_key: apiKey || undefined,
          api_base: apiBase || "",
        },
        theme,
        indexing: {
          ignore_folders: ignoreFolders.split(",").map((s) => s.trim()).filter(Boolean),
          max_file_size_kb: maxFileSize,
          exclude_extensions: bootstrap?.indexing?.exclude_extensions ?? [],
        },
      })
      toast.success("Settings saved")
      onOpenChange(false)
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const deleteWorkspace = async (id: string, name: string) => {
    if (!window.confirm(`Delete the index for ${name}? This reclaims disk space and cannot be undone.`)) return
    try {
      await api.deleteWorkspace(id)
      toast.success(`${name} index deleted`)
      onOpenChange(false)
      onWorkspaceDeleted()
    } catch (err) {
      toast.error((err as Error).message)
    }
  }

  const providerModels = models[provider] ?? []
  const totalIndexing = (costs?.indexing.cost ?? 0) + (costs?.docs.cost ?? 0)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent wide className="max-h-[85dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Global configuration lives in ~/.local/share/foray/config.json, fully separate from the
            per-repository indexes.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          <Section title="LLM provider">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Provider">
                <Select
                  value={provider}
                  onValueChange={(v) => {
                    setProvider(v)
                    const first = models[v]?.[0]
                    if (first) setModel(first)
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="openai">OpenAI</SelectItem>
                    <SelectItem value="anthropic">Anthropic</SelectItem>
                    <SelectItem value="ollama">Ollama (local)</SelectItem>
                    <SelectItem value="custom">Custom endpoint</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Chat model">
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(providerModels.length > 0 ? providerModels : [model]).map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                    <SelectItem value={model}>{model} (current)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <Field
              label="API key"
              hint={llm?.has_key ? "A key is configured. Leave blank to keep it." : provider === "ollama" ? "Ollama needs no key." : "No key configured yet."}
            >
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." autoComplete="off" />
            </Field>
            {provider !== "openai" && (
              <Field label="API base URL" hint={provider === "ollama" ? "Defaults to http://localhost:11434" : undefined}>
                <Input value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder={provider === "ollama" ? "http://localhost:11434" : "https://..."} className="font-mono" />
              </Field>
            )}
          </Section>

          <Section title="Indexing">
            <Field label="Ignored folders" hint="Comma-separated, applied on top of .gitignore rules">
              <Input value={ignoreFolders} onChange={(e) => setIgnoreFolders(e.target.value)} placeholder="node_modules, dist" className="font-mono" />
            </Field>
            <Field label={`Max file size: ${maxFileSize} KB`} hint="Files above this size are skipped during indexing">
              <input
                type="range"
                min={16}
                max={2048}
                step={16}
                value={maxFileSize}
                onChange={(e) => setMaxFileSize(Number(e.target.value))}
                className="mt-1 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-[var(--surface-inset)] accent-ember-600"
              />
            </Field>
          </Section>

          <Section title="Cost tracker">
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Indexing", bucket: costs?.indexing, note: "permanent, per repo" },
                { label: "Docs", bucket: costs?.docs, note: "cached guides" },
                { label: "Chat (session)", bucket: null, note: "ephemeral" },
              ].map((row) => (
                <div key={row.label} className="rounded-[8px] border border-[var(--border-hair)] p-3">
                  <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    {row.label}
                  </div>
                  <div className="mt-1.5 font-mono text-[17px] font-medium tracking-[-0.01em] text-[var(--text-primary)]">
                    {row.bucket
                      ? formatCost(row.bucket.cost)
                      : formatCost(sessionCost)}
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-[var(--text-tertiary)]">
                    {row.bucket
                      ? `${row.bucket.tokens.toLocaleString()} tok`
                      : `${sessionTokens.toLocaleString()} tok`}
                  </div>
                  <div className="mt-1 text-[10px] text-[var(--text-tertiary)]">{row.note}</div>
                </div>
              ))}
            </div>
            {totalIndexing > 0 && (
              <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">
                {formatCost(totalIndexing)} spent on indexing and docs for this workspace.
              </p>
            )}
          </Section>

          <Section title="Workspaces">
            <div className="flex flex-col divide-y divide-[var(--border-hair)] rounded-[8px] border border-[var(--border-hair)]">
              {workspaces.map((ws) => (
                <div key={ws.id} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium text-[var(--text-primary)]">{ws.name}</span>
                    <span className="block truncate font-mono text-[10.5px] text-[var(--text-tertiary)]">{ws.path}</span>
                  </span>
                  <span className="shrink-0 font-mono text-[10.5px] text-[var(--text-tertiary)]">
                    {formatTime(ws.last_sync)}
                  </span>
                  <button
                    type="button"
                    onClick={() => navigate(`/workspace/${ws.id}`)}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--surface-inset)] hover:text-[var(--text-primary)]"
                    aria-label={`Open ${ws.name}`}
                  >
                    <ArrowSquareOutIcon className="h-3.5 w-3.5" />
                  </button>
                  {!ws.demo && (
                    <button
                      type="button"
                      onClick={() => deleteWorkspace(ws.id, ws.name)}
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-[var(--text-tertiary)] transition-colors hover:bg-red-500/10 hover:text-red-500"
                      aria-label={`Delete ${ws.name} index`}
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
              {workspaces.length === 0 && (
                <div className="px-3 py-3 text-[12px] text-[var(--text-tertiary)]">No workspaces yet</div>
              )}
            </div>
          </Section>

          <Section title="Appearance">
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] text-[var(--text-primary)]">Dark workspace theme</span>
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[10.5px] text-[var(--text-tertiary)]">
                  {theme === "dark" ? "dark" : "light"}
                </span>
                <Switch
                  checked={theme === "dark"}
                  onCheckedChange={(v) => setTheme(v ? "dark" : "light")}
                  aria-label="Toggle dark mode"
                />
              </div>
            </div>
          </Section>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-[var(--border-hair)] pt-4">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="accent" size="sm" onClick={save} disabled={saving}>
            {saving ? "Saving..." : "Save settings"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
