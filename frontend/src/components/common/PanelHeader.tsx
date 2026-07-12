import { RefreshCw } from "lucide-react";

// Shared panel title row with a manual refresh control (data is not auto-refetched).
export function PanelHeader({ title, onRefresh }: { title: string; onRefresh: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-lg font-semibold">{title}</h2>
      <button className="icon-button" onClick={onRefresh} title={`Refresh ${title}`} type="button">
        <RefreshCw className="h-4 w-4" />
      </button>
    </div>
  );
}
