// Inline placeholder for a panel with no selection/content yet (e.g. no invoice chosen).
export function EmptyPanel({ title }: { title: string }) {
  return <section className="panel text-sm text-muted-foreground">{title}</section>;
}
