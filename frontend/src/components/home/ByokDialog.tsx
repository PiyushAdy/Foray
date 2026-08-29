import React from "react"
import { toast } from "sonner"

import { clearByok, loadByok, saveByok, streamChat } from "@/lib/api"
import { useApp } from "@/stores/app"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

/** BYOK: bring your own key. Stored only in this browser (localStorage). */
export function ByokDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [apiKey, setApiKey] = React.useState("")
  const [apiBase, setApiBase] = React.useState("")
  const [existing, setExisting] = React.useState(false)
  const [testing, setTesting] = React.useState(false)
  const bootstrap = useApp((s) => s.bootstrap)

  React.useEffect(() => {
    if (open) {
      const saved = loadByok()
      setExisting(Boolean(saved?.api_key))
      setApiKey(saved?.api_key ?? "")
      setApiBase(saved?.api_base ?? "")
    }
  }, [open])

  const verify = async () => {
    if (!apiKey.trim()) {
      toast.error("Enter an API key first")
      return
    }
    setTesting(true)
    let tokens = 0
    const stop = streamChat(
      bootstrap?.repos?.[0]?.id ?? "",
      "Reply with the single word: ok",
      [],
      {
        onToken: () => {
          tokens += 1
        },
        onDone: () => {
          setTesting(false)
          stop()
          toast.success("Key verified. Unlimited queries unlocked for this browser.")
          onOpenChange(false)
        },
        onError: (message) => {
          setTesting(false)
          toast.error(`Key check failed: ${message}`)
        },
      },
      { api_key: apiKey.trim(), api_base: apiBase.trim() || undefined }
    )
  }

  const save = () => {
    saveByok({ api_key: apiKey.trim(), api_base: apiBase.trim() || undefined })
    toast.success("Key saved locally. It is never written to the server config.")
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bring your own key</DialogTitle>
          <DialogDescription>
            Visitors on this demo share a host key with a strict rate limit. Add your own key to
            bypass it. The key is stored in this browser only and passed per-session to LiteLLM.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[var(--text-primary)]">API key</span>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium text-[var(--text-primary)]">
              Custom base URL <span className="text-[var(--text-tertiary)]">(optional)</span>
            </span>
            <Input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="https://api.openai.com/v1"
              autoComplete="off"
            />
          </label>
        </div>
        <DialogFooter>
          {existing && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                clearByok()
                setApiKey("")
                setApiBase("")
                setExisting(false)
                toast.success("Saved key removed from this browser")
              }}
            >
              Remove saved key
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={save}>
            Save without testing
          </Button>
          <Button variant="accent" size="sm" onClick={verify} disabled={testing}>
            {testing ? "Verifying..." : "Save and verify"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
