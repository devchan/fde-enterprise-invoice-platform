import { Card, CardContent } from "../ui/card";

// Inline placeholder for a panel with no selection/content yet (e.g. no invoice chosen).
export function EmptyPanel({ title }: { title: string }) {
  return (
    <Card>
      <CardContent className="pt-6 text-sm text-muted-foreground">{title}</CardContent>
    </Card>
  );
}
