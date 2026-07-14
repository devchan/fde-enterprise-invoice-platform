import { createRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { useSession } from "../app/useSession";
import { useHealth } from "../app/useHealth";
import { useAuditLogsQuery } from "../queries/audit";
import { useInvoicesQuery } from "../queries/invoices";
import { useFailedJobsQuery } from "../queries/jobs";
import { OverviewPanel } from "../features/dashboard/OverviewPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/",
  component: OverviewRoute,
});

function OverviewRoute() {
  const { session } = useSession();
  const { checkHealth } = useHealth();
  const invoicesQuery = useInvoicesQuery(session);
  const failedJobsQuery = useFailedJobsQuery(session);
  const auditLogsQuery = useAuditLogsQuery(session);

  // Depends on the arrays themselves (not just lengths) because status counts
  // change without the array length changing.
  const stats = useMemo(
    () => [
      { label: "Loaded invoices", value: (invoicesQuery.data ?? []).length.toString() },
      {
        label: "Review required",
        value: (invoicesQuery.data ?? []).filter((invoice) => invoice.status === "review_required").length.toString(),
      },
      { label: "Failed jobs", value: (failedJobsQuery.data ?? []).length.toString() },
      { label: "Audit events", value: (auditLogsQuery.data ?? []).length.toString() },
    ],
    [auditLogsQuery.data, failedJobsQuery.data, invoicesQuery.data],
  );

  return (
    <OverviewPanel
      // isLoading (first fetch only), not isFetching, so manual "Refresh data" clicks
      // don't re-trigger the full skeleton grid.
      loading={invoicesQuery.isLoading || failedJobsQuery.isLoading || auditLogsQuery.isLoading}
      signedIn={Boolean(session)}
      stats={stats}
      refresh={() => {
        void invoicesQuery.refetch();
        void failedJobsQuery.refetch();
        void auditLogsQuery.refetch();
      }}
      checkHealth={checkHealth}
    />
  );
}
