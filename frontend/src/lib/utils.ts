import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTime(ts: number | null | undefined): string {
  if (!ts) return "never"
  const seconds = Math.floor(Date.now() / 1000 - ts)
  if (seconds < 45) return "just now"
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function formatCost(usd: number): string {
  if (usd <= 0) return "$0.00"
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return `${n}`
}

export const langColors: Record<string, string> = {
  python: "#3776ab",
  typescript: "#3178c6",
  tsx: "#3178c6",
  javascript: "#f1e05a",
  jsx: "#f1e05a",
  go: "#00add8",
  rust: "#dea584",
  java: "#b07219",
  ruby: "#701516",
  c: "#555555",
  cpp: "#f34b7d",
  csharp: "#178600",
  swift: "#f05138",
  kotlin: "#a97bff",
  php: "#4f5d95",
  html: "#e34c26",
  css: "#563d7c",
  markdown: "#519aba",
  yaml: "#cb171e",
  json: "#292929",
  shell: "#89e051",
}

export function languageDot(lang: string): string {
  return langColors[lang] ?? "#8d8d93"
}
