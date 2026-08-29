import React from "react"
import { motion } from "motion/react"
import { CompassIcon, ArrowClockwiseIcon } from "@phosphor-icons/react"

import { api, type RepoMap, type Workspace } from "@/lib/api"
import { formatNumber, languageDot } from "@/lib/utils"

/* ---------------------------------------------------------------------------
 * Lightweight force-directed layout (velocity Verlet, damped).
 * No external graph library: runs once per mount, 60fps, tiny footprint.
 * ------------------------------------------------------------------------ */

interface SimNode {
  id: string
  label: string
  x: number
  y: number
  vx: number
  vy: number
  r: number
  score: number
  files: number
  loc: number
}

interface SimLink {
  source: SimNode
  target: SimNode
  weight: number
}

function runLayout(nodes: SimNode[], links: SimLink[], width: number, height: number, iterations = 220) {
  const k = Math.sqrt((width * height) / Math.max(1, nodes.length)) * 0.9
  for (let iter = 0; iter < iterations; iter++) {
    const cooling = 1 - iter / iterations
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i]
        const b = nodes[j]
        let dx = a.x - b.x
        let dy = a.y - b.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 0.01
        if (dist > 400) continue
        const force = (k * k) / dist
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        a.vx += fx * 0.02
        a.vy += fy * 0.02
        b.vx -= fx * 0.02
        b.vy -= fy * 0.02
      }
    }
    // attraction along links
    for (const link of links) {
      const dx = link.target.x - link.source.x
      const dy = link.target.y - link.source.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
      const force = (dist - k * 1.4) * 0.015
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      link.source.vx += fx
      link.source.vy += fy
      link.target.vx -= fx
      link.target.vy -= fy
    }
    // integrate + containment
    for (const node of nodes) {
      node.vx *= 0.86 * cooling + 0.1
      node.vy *= 0.86 * cooling + 0.1
      node.x += Math.max(-14, Math.min(14, node.vx))
      node.y += Math.max(-14, Math.min(14, node.vy))
      node.x = Math.max(node.r + 8, Math.min(width - node.r - 8, node.x))
      node.y = Math.max(node.r + 8, Math.min(height - node.r - 8, node.y))
    }
  }
}

function MapGraph({ data, onPickModule }: { data: RepoMap; onPickModule: (id: string) => void }) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [size, setSize] = React.useState({ w: 900, h: 560 })
  const [hover, setHover] = React.useState<string | null>(null)

  React.useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect
      if (rect) setSize({ w: Math.max(320, rect.width), h: Math.max(360, rect.height) })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const { nodes, links } = React.useMemo(() => {
    if (data.nodes.length === 0) return { nodes: [] as SimNode[], links: [] as SimLink[] }
    const simNodes: SimNode[] = data.nodes.map((n, i) => {
      const angle = (i / data.nodes.length) * Math.PI * 2
      const radius = Math.min(size.w, size.h) * 0.36
      const r = 10 + n.norm * 18
      return {
        id: n.id,
        label: n.label,
        x: size.w / 2 + Math.cos(angle) * radius,
        y: size.h / 2 + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        r,
        score: n.score,
        files: n.files,
        loc: n.loc,
      }
    })
    const byId = new Map(simNodes.map((n) => [n.id, n]))
    const simLinks: SimLink[] = data.links
      .map((l) => {
        const source = byId.get(l.source)
        const target = byId.get(l.target)
        if (!source || !target) return null
        return { source, target, weight: l.weight }
      })
      .filter(Boolean) as SimLink[]
    runLayout(simNodes, simLinks, size.w, size.h)
    return { nodes: simNodes, links: simLinks }
  }, [data, size.w, size.h])

  if (nodes.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-[13px] text-ink-500">
        No graph data in this index yet
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative min-h-0 flex-1 overflow-hidden">
      <svg width={size.w} height={size.h} className="block">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(161,161,170,0.4)" />
          </marker>
        </defs>
        {links.map((link, i) => {
          const active = hover === link.source.id || hover === link.target.id
          const dx = link.target.x - link.source.x
          const dy = link.target.y - link.source.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const sx = link.source.x + (dx / dist) * (link.source.r + 3)
          const sy = link.source.y + (dy / dist) * (link.source.r + 3)
          const tx = link.target.x - (dx / dist) * (link.target.r + 7)
          const ty = link.target.y - (dy / dist) * (link.target.r + 7)
          return (
            <line
              key={i}
              x1={sx}
              y1={sy}
              x2={tx}
              y2={ty}
              stroke={active ? "rgba(249,115,22,0.55)" : "rgba(161,161,170,0.22)"}
              strokeWidth={Math.min(3, 0.8 + link.weight * 0.15)}
              markerEnd="url(#arrow)"
              className="transition-[stroke] duration-150"
            />
          )
        })}
        {nodes.map((node) => {
          const active = hover === node.id
          return (
            <g
              key={node.id}
              transform={`translate(${node.x},${node.y})`}
              className="cursor-pointer"
              onMouseEnter={() => setHover(node.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onPickModule(node.id)}
            >
              <circle
                r={node.r}
                fill={active ? "rgba(249,115,22,0.16)" : "rgba(39,39,42,0.85)"}
                stroke={active ? "#f97316" : "rgba(82,82,91,0.9)"}
                strokeWidth={active ? 2 : 1.2}
                className="transition-all duration-150"
              />
              <text
                y={node.r + 13}
                textAnchor="middle"
                fill={active ? "#f4f4f5" : "#a1a1aa"}
                fontSize="10.5"
                fontFamily="var(--font-mono)"
                className="pointer-events-none select-none"
              >
                {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
              </text>
              {node.files > 1 && (
                <text
                  y={4}
                  textAnchor="middle"
                  fill={active ? "#fdba74" : "#71717a"}
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                  className="pointer-events-none select-none"
                >
                  {node.files}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export function MapView({ workspaceId, workspace }: { workspaceId: string; workspace: Workspace }) {
  const [data, setData] = React.useState<RepoMap | null>(null)
  const [error, setError] = React.useState("")
  const [loading, setLoading] = React.useState(true)
  const [reloadKey, setReloadKey] = React.useState(0)

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError("")
    api
      .repoMap(workspaceId)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId, reloadKey])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-800 px-5">
        <CompassIcon className="h-4 w-4 text-ember-400" />
        <h2 className="text-[13px] font-semibold tracking-[-0.01em] text-ink-100">Repository map</h2>
        {data && (
          <span className="font-mono text-[10.5px] text-ink-500">
            {data.stats.modules} modules · {formatNumber(data.stats.loc)} loc · {data.stats.files} files
          </span>
        )}
        <button
          type="button"
          onClick={() => setReloadKey((k) => k + 1)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-[6px] text-ink-500 transition-colors hover:bg-ink-850 hover:text-ink-200"
          aria-label="Reload map"
        >
          <ArrowClockwiseIcon className="h-3.5 w-3.5" />
        </button>
      </div>

      {loading && (
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-ember-500 border-t-transparent" />
          <span className="font-mono text-[11px] text-ink-500">computing layout...</span>
        </div>
      )}
      {error && <div className="p-6 text-[13px] text-red-400">{error}</div>}
      {!loading && !error && data && (
        <MapGraph data={data} onPickModule={() => undefined} />
      )}

      {!loading && !error && data && (
        <div className="h-40 shrink-0 overflow-y-auto border-t border-ink-800 bg-ink-900/40">
          <div className="sticky top-0 flex h-8 items-center bg-ink-900/90 px-4 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-600 backdrop-blur-sm">
            highest-ranked files
          </div>
          <div className="divide-y divide-ink-800/60">
            {data.top_files.map((f) => (
              <div key={f.path} className="flex items-center gap-3 px-4 py-2 hover:bg-ink-850/50">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: languageDot(f.language ?? "") }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink-300">{f.path}</span>
                <span className="shrink-0 font-mono text-[10.5px] text-ink-600">{formatNumber(f.loc)} loc</span>
                <span className="w-14 shrink-0 text-right font-mono text-[10.5px] text-ink-600">
                  {f.score.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <motion.div className="hidden">{workspace.name}</motion.div>
    </div>
  )
}
