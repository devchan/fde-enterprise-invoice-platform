import type { ColumnDef } from "@tanstack/react-table";
import { Loader2, RefreshCw } from "lucide-react";
import { DataTable } from "../../components/common/DataTable";
import { PanelHeader } from "../../components/common/PanelHeader";
import { StatusPill } from "../../components/common/StatusPill";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import type { ProcessingJob } from "../../domain/types";

export function FailedJobsPanel({
  canReprocess,
  jobs,
  onBulkReprocess,
  onRefresh,
  onReprocess,
  reprocessingJobId,
}: {
  canReprocess: boolean;
  jobs: ProcessingJob[];
  onBulkReprocess: (jobs: ProcessingJob[]) => void;
  onRefresh: () => void;
  onReprocess: (job: ProcessingJob) => void;
  reprocessingJobId: string | null;
}) {
  const columns: ColumnDef<ProcessingJob>[] = [
    {
      accessorKey: "job_type",
      header: "Job",
      cell: ({ row }) => <span className="font-mono text-xs font-medium">{row.original.job_type}</span>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => <StatusPill label={row.original.status} />,
    },
    {
      accessorKey: "attempts",
      header: "Attempts",
      cell: ({ row }) => <span className="num">{row.original.attempts}</span>,
    },
    {
      accessorKey: "last_error",
      header: "Last error",
      // Fall back to the invoice id when the job recorded no error message.
      cell: ({ row }) => <span className="text-xs text-muted-foreground">{row.original.last_error || row.original.invoice_id}</span>,
    },
    {
      id: "actions",
      header: "Action",
      enableSorting: false,
      cell: ({ row }) => (
        // Disabled without reprocess rights, or while this specific job's request is in flight.
        <Button
          disabled={!canReprocess || reprocessingJobId === row.original.processing_job_id}
          onClick={() => onReprocess(row.original)}
          size="sm"
          type="button"
          variant="outline"
        >
          {reprocessingJobId === row.original.processing_job_id ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Reprocess
        </Button>
      ),
    },
  ];

  return (
    <Card>
      <CardContent className="pt-6">
        <PanelHeader title="Failed Jobs" onRefresh={onRefresh} />
        {!canReprocess ? (
          <p className="mt-3 text-sm leading-6 text-muted-foreground">Reprocess actions require admin or reviewer access.</p>
        ) : null}
        <div className="mt-4">
          <DataTable
            bulkActions={
              canReprocess ? [{ label: "Reprocess", icon: RefreshCw, onClick: onBulkReprocess }] : undefined
            }
            columns={columns}
            data={jobs}
            emptyMessage="No failed jobs — the processing pipeline is healthy."
            enableColumnVisibility
            enableExport={{ filename: "failed-jobs.csv" }}
            enableRowSelection={canReprocess}
            getRowId={(job) => job.processing_job_id}
          />
        </div>
      </CardContent>
    </Card>
  );
}
