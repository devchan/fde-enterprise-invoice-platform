import type { ColumnDef } from "@tanstack/react-table";
import { Loader2, RefreshCw } from "lucide-react";
import { DataTable } from "../../components/common/DataTable";
import { PanelHeader } from "../../components/common/PanelHeader";
import type { ProcessingJob } from "../../domain/types";

export function FailedJobsPanel({
  busy,
  canReprocess,
  jobs,
  onRefresh,
  onReprocess,
}: {
  busy: string | null;
  canReprocess: boolean;
  jobs: ProcessingJob[];
  onRefresh: () => void;
  onReprocess: (job: ProcessingJob) => void;
}) {
  const columns: ColumnDef<ProcessingJob>[] = [
    {
      accessorKey: "job_type",
      header: "Job",
      cell: ({ row }) => <span className="font-medium">{row.original.job_type}</span>,
    },
    {
      accessorKey: "status",
      header: "Status",
    },
    {
      accessorKey: "attempts",
      header: "Attempts",
    },
    {
      accessorKey: "last_error",
      header: "Last error",
      // Fall back to the invoice id when the job recorded no error message.
      cell: ({ row }) => <span className="text-muted-foreground">{row.original.last_error || row.original.invoice_id}</span>,
    },
    {
      id: "actions",
      header: "Action",
      enableSorting: false,
      cell: ({ row }) => (
        // Disabled without reprocess rights, or while this specific job's request is in flight.
        <button
          className="btn-secondary"
          disabled={!canReprocess || busy === `job:${row.original.processing_job_id}`}
          onClick={() => onReprocess(row.original)}
          type="button"
        >
          {busy === `job:${row.original.processing_job_id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Reprocess
        </button>
      ),
    },
  ];

  return (
    <section className="panel">
      <PanelHeader title="Failed Jobs" onRefresh={onRefresh} />
      {!canReprocess ? (
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Reprocess actions require admin or reviewer access.</p>
      ) : null}
      <div className="mt-4">
        <DataTable columns={columns} data={jobs} emptyMessage="No failed jobs." />
      </div>
    </section>
  );
}
