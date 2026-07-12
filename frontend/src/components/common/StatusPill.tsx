// Small colored status badge; `tone` maps to a CSS modifier class (status-ok/error/info).
export function StatusPill({ label, tone }: { label: string; tone: "ok" | "error" | "info" }) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}
