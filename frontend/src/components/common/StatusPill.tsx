import { Badge } from "../ui/badge";

const toneVariant = {
  ok: "success",
  error: "destructive",
  info: "secondary",
} as const;

export function StatusPill({ label, tone }: { label: string; tone: "ok" | "error" | "info" }) {
  return (
    <Badge className="uppercase" variant={toneVariant[tone]}>
      {label}
    </Badge>
  );
}
