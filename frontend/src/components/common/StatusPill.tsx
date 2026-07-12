export function StatusPill({ label, tone }: { label: string; tone: "ok" | "error" | "info" }) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}
