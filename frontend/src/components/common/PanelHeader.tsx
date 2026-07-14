import { RefreshCw } from "lucide-react";
import { Button } from "../ui/button";

// Shared panel title row with a manual refresh control (data is not auto-refetched).
export function PanelHeader({ title, onRefresh }: { title: string; onRefresh: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-lg font-semibold">{title}</h2>
      <Button aria-label={`Refresh ${title}`} onClick={onRefresh} size="icon" title={`Refresh ${title}`} type="button" variant="outline">
        <RefreshCw className="h-4 w-4" />
      </Button>
    </div>
  );
}
