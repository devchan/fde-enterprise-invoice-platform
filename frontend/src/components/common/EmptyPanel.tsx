import { Inbox } from "lucide-react";
import { Card, CardContent } from "../ui/card";

// Inline placeholder for a panel with no selection/content yet (e.g. no invoice
// chosen). `hint` tells the user what action produces content here.
export function EmptyPanel({ hint, title }: { hint?: string; title: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center gap-2 py-14 text-center">
        <Inbox aria-hidden="true" className="h-6 w-6 text-muted-foreground/50" />
        <p className="text-sm font-medium">{title}</p>
        {hint ? <p className="max-w-xs text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
