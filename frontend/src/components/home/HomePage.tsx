import React from "react"
import { useNavigate } from "react-router-dom"
import { motion, useReducedMotion } from "motion/react"
import { ArrowRightIcon, GithubLogoIcon, LightningIcon } from "@phosphor-icons/react"
import { toast } from "sonner"

import { useApp } from "@/stores/app"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { ByokDialog } from "@/components/home/ByokDialog"

function TerminalBlock({ command }: { command: string }) {
  const [copied, setCopied] = React.useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      toast.error("Clipboard unavailable in this browser")
    }
  }
  return (
    <div className="group inline-flex w-full max-w-[420px] items-center justify-between gap-4 rounded-[12px] border border-paper-800/40 bg-ink-950 py-3.5 pl-4 pr-2.5 shadow-[0_18px_50px_-16px_rgba(27,26,24,0.45)]">
      <div className="flex min-w-0 items-center gap-2.5 font-mono text-[13px]">
        <span className="select-none text-ink-500">$</span>
        <span className="truncate text-ink-100">{command}</span>
      </div>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 rounded-[6px] border border-ink-700 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-400 transition-colors hover:border-ink-600 hover:text-ink-200"
      >
        {copied ? "copied" : "copy"}
      </button>
    </div>
  )
}

function HeroShots() {
  /* Real screenshots of the Foray workspace, captured from the app itself. */
  const shots = [
    { src: "/shots/chat.png", alt: "Foray grounded chat with inline citations", rotate: -2.2, z: 1 },
    { src: "/shots/map.png", alt: "Foray repository map, module dependency graph", rotate: 1.8, z: 2 },
  ]
  return (
    <div className="relative mx-auto hidden h-[420px] w-full max-w-[560px] select-none lg:block" aria-hidden={false}>
      {shots.map((shot, i) => (
        <motion.img
          key={shot.src}
          src={shot.src}
          alt={shot.alt}
          draggable={false}
          initial={false}
          onError={(e) => {
            ;(e.currentTarget as HTMLImageElement).style.display = "none"
          }}
          className={`absolute w-[78%] overflow-hidden rounded-[14px] border border-paper-900/10 shadow-[0_40px_90px_-30px_rgba(27,26,24,0.4)] ${i === 0 ? "left-0 top-2" : "right-0 top-[120px]"}`}
          style={{ rotate: shot.rotate, zIndex: shot.z }}
        />
      ))}
    </div>
  )
}

function DemoGrid() {
  const bootstrap = useApp((s) => s.bootstrap)
  const repos = bootstrap?.repos ?? []
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  if (repos.length === 0) return null

  return (
    <section className="mx-auto w-full max-w-[1200px] px-6 pb-24">
      <div className="mb-5 flex items-baseline justify-between">
        <h2 className="text-[19px] font-semibold tracking-[-0.015em] text-paper-900">Pre-indexed repositories</h2>
        <span className="font-mono text-[11.5px] text-paper-500">{repos.length} available</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {repos.map((repo, i) => (
          <motion.button
            key={repo.id}
            type="button"
            onClick={() => navigate(`/workspace/${repo.id}`)}
            initial={reduce ? false : { opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.5, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="group flex min-h-[120px] flex-col justify-between rounded-[12px] border border-[var(--border-strong)] bg-paper-50 p-4 text-left transition-all duration-150 hover:border-paper-400 hover:bg-white hover:shadow-[0_10px_30px_-14px_rgba(27,26,24,0.25)]"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[13px] font-medium text-paper-900">{repo.name}</span>
                <ArrowRightIcon
                  className="h-3.5 w-3.5 -translate-x-1 text-paper-400 opacity-0 transition-all duration-150 group-hover:translate-x-0 group-hover:text-ember-600 group-hover:opacity-100"
                  weight="bold"
                />
              </div>
              <p className="mt-1.5 line-clamp-2 text-[12.5px] leading-relaxed text-paper-600">{repo.description}</p>
            </div>
            <div className="mt-4 flex items-center gap-1.5">
              {repo.languages.slice(0, 4).map((lang) => (
                <span
                  key={lang}
                  className="rounded-full border border-paper-300 bg-paper-100 px-2 py-[1px] font-mono text-[10px] text-paper-700"
                >
                  {lang}
                </span>
              ))}
              {repo.loc > 0 && (
                <span className="ml-auto font-mono text-[10.5px] text-paper-400">
                  {(repo.loc / 1000).toFixed(1)}k loc
                </span>
              )}
            </div>
          </motion.button>
        ))}
      </div>
    </section>
  )
}

function LocalHighlights() {
  const items = [
    {
      title: "Grounded chat",
      body: "Answers cite the exact file and line. Click a citation to read the code next to the conversation.",
    },
    {
      title: "Hybrid search",
      body: "BM25 keyword precision fused with semantic vectors through reciprocal rank fusion.",
    },
    {
      title: "Repo map",
      body: "A PageRank-weighted module graph for fast orientation in unfamiliar codebases.",
    },
  ]
  const reduce = useReducedMotion()
  return (
    <section className="mx-auto w-full max-w-[1200px] px-6 pb-28">
      <h2 className="mb-5 text-[19px] font-semibold tracking-[-0.015em] text-paper-900">What you get</h2>
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-[12px] border border-[var(--border-strong)] bg-[var(--border-hair)] md:grid-cols-3">
        {items.map((item, i) => (
          <motion.div
            key={item.title}
            initial={reduce ? false : { opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.5, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
            className="bg-paper-50 p-5"
          >
            <h3 className="text-[14px] font-semibold text-paper-900">{item.title}</h3>
            <p className="mt-2 max-w-[42ch] text-[12.5px] leading-relaxed text-paper-600">{item.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const bootstrap = useApp((s) => s.bootstrap)
  const [byokOpen, setByokOpen] = React.useState(false)
  const demo = bootstrap?.demo_mode ?? false
  const version = bootstrap?.version ?? "0.1.0"

  const enterWorkspace = () => {
    if (demo) {
      const first = bootstrap?.repos?.[0]?.id
      navigate(first ? `/workspace/${first}` : "/setup")
      return
    }
    const workspaces = bootstrap?.workspaces ?? []
    if (workspaces.length === 0) {
      navigate("/setup")
      return
    }
    const target = bootstrap?.last_workspace_id ?? workspaces[0]?.id
    navigate(`/workspace/${target}`)
  }

  return (
    <div className="paper-grain min-h-[100dvh] bg-paper-100">
      {/* floating pill nav */}
      <header className="fixed inset-x-0 top-4 z-30 flex justify-center px-6">
        <nav className="flex h-11 w-full max-w-[560px] items-center justify-between rounded-full border border-paper-300/70 bg-white/90 px-3 pl-4 shadow-[0_4px_20px_rgba(27,26,24,0.06)] backdrop-blur-md">
          <a href="/" className="flex items-center gap-2.5">
            <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden>
              <rect width="32" height="32" rx="7" fill="#1b1a18" />
              <path d="M9 11.5 L16 23 L23 11.5" stroke="#f97316" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
            </svg>
            <span className="text-[14px] font-semibold tracking-[-0.01em] text-paper-900">foray</span>
          </a>
          <div className="flex items-center gap-1.5">
            <a
              href="https://github.com/foray/foray"
              target="_blank"
              rel="noreferrer"
              className="flex h-8 items-center gap-2 rounded-full px-3 text-[12.5px] font-medium text-paper-700 transition-colors hover:bg-paper-100"
            >
              <GithubLogoIcon className="h-4 w-4" weight="fill" />
              <span className="hidden sm:inline">Source</span>
            </a>
            <Button size="sm" variant="accent" className="rounded-full" onClick={enterWorkspace}>
              Enter Workspace
              <ArrowRightIcon className="h-3.5 w-3.5" weight="bold" />
            </Button>
          </div>
        </nav>
      </header>

      {/* hero: left copy + right overlapping screenshots */}
      <main className="mx-auto flex min-h-[100dvh] w-full max-w-[1200px] flex-col justify-center px-6 pb-16 pt-28">
        <div className="grid items-center gap-14 lg:grid-cols-[1.02fr_1fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-ember-600/25 bg-ember-50 px-3 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-ember-500" aria-hidden />
              <span className="font-mono text-[11px] text-ember-700">v{version} · local-first</span>
            </div>
            <h1 className="text-[64px] font-bold leading-[1.02] tracking-[-0.035em] text-paper-900 md:text-[76px]">
              Foray
            </h1>
            <p className="mt-4 max-w-[30ch] text-[19px] font-medium leading-snug tracking-[-0.01em] text-paper-800 md:text-[22px]">
              The local intelligence layer for your codebase.
            </p>
            <p className="mt-3 max-w-[52ch] text-[14px] leading-relaxed text-paper-600">
              Index a repository once. Chat with grounded citations, map its architecture, and serve
              context to your coding agents over MCP. Everything stays on your machine.
            </p>
            <div className="mt-8">
              <TerminalBlock command="uv tool install foray" />
            </div>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button size="lg" onClick={enterWorkspace}>
                Enter Workspace
                <ArrowRightIcon className="h-4 w-4" weight="bold" />
              </Button>
              <span className="hidden items-center gap-2 text-[12px] text-paper-500 sm:flex">
                press <Kbd>⌘</Kbd> <Kbd>K</Kbd> anywhere inside
              </span>
            </div>
          </div>
          <HeroShots />
        </div>
      </main>

      {demo && (
        <section className="mx-auto w-full max-w-[1200px] px-6 pb-6">
          <button
            type="button"
            onClick={() => setByokOpen(true)}
            className="group flex w-full items-center justify-between gap-4 rounded-[12px] border border-ember-600/25 bg-gradient-to-r from-ember-50 to-paper-50 px-5 py-3.5 text-left transition-all duration-150 hover:border-ember-600/45"
          >
            <span className="flex items-center gap-3">
              <LightningIcon className="h-4.5 w-4.5 shrink-0 text-ember-600" weight="fill" />
              <span className="text-[13.5px] text-paper-800">
                <strong className="font-semibold">Power user?</strong> Unlock unlimited queries with your own API key.
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-ember-700 transition-transform duration-150 group-hover:translate-x-0.5">
              BYOK
              <ArrowRightIcon className="h-3 w-3" weight="bold" />
            </span>
          </button>
        </section>
      )}

      <DemoGrid />
      {!demo && <LocalHighlights />}

      <footer className="mx-auto flex w-full max-w-[1200px] items-center justify-between px-6 pb-8">
        <span className="font-mono text-[11px] text-paper-400">
          {demo ? "hosted demo · read-only" : "runs entirely on your machine"}
        </span>
        <span className="flex items-center gap-4 font-mono text-[11px] text-paper-400">
          <span>~/.local/share/foray</span>
          <span className="text-paper-300">/</span>
          <span>MIT</span>
        </span>
      </footer>

      <ByokDialog open={byokOpen} onOpenChange={setByokOpen} />
    </div>
  )
}
