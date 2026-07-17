import { cn } from "@/lib/utils";

// One pill for every status in the product: mono lowercase label, tinted
// ground + border, a single leading dot (styles in styles.css). Tones map to
// the semantic palette — good/warn/crit for outcomes, blueprint for in-flight,
// accent (amber) strictly for AI signals, neutral for everything else.
export type PillTone = "good" | "warn" | "crit" | "blueprint" | "accent" | "neutral" | "ok" | "error" | "info";

// Legacy tone names kept as aliases so existing call sites stay valid.
const toneClass: Record<PillTone, string> = {
  good: "status-pill-good",
  warn: "status-pill-warn",
  crit: "status-pill-crit",
  blueprint: "status-pill-blueprint",
  accent: "status-pill-accent",
  neutral: "",
  ok: "status-pill-good",
  error: "status-pill-crit",
  info: "status-pill-blueprint",
};

// Canonical invoice/job status → tone mapping, used by every table and detail
// view so a status always reads the same color everywhere.
const statusToneMap: Record<string, PillTone> = {
  approved: "good",
  validation_passed: "good",
  completed: "good",
  rejected: "crit",
  failed: "crit",
  review_required: "warn",
  processing: "blueprint",
  queued: "blueprint",
  extracted: "blueprint",
  uploaded: "neutral",
};

export function statusTone(status: string): PillTone {
  return statusToneMap[status] ?? "neutral";
}

export function StatusPill({ className, label, tone }: { className?: string; label: string; tone?: PillTone }) {
  const resolved = tone ?? statusTone(label);
  return <span className={cn("status-pill", toneClass[resolved], className)}>{label.replace(/_/g, " ")}</span>;
}
