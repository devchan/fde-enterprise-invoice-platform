import { createRoute } from "@tanstack/react-router";
import { useSession } from "../app/useSession";
import { SignInRequiredPanel } from "../components/common/AccessPanels";
import { useBulkReprocessJobsMutation, useFailedJobsQuery, useReprocessJobMutation } from "../queries/jobs";
import { FailedJobsPanel } from "../features/jobs/FailedJobsPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/failed",
  component: FailedRoute,
});

function FailedRoute() {
  const { session, userCanReview } = useSession();
  const failedJobsQuery = useFailedJobsQuery(session);
  const reprocessMutation = useReprocessJobMutation(session);
  const bulkReprocessMutation = useBulkReprocessJobsMutation(session);

  if (!session) return <SignInRequiredPanel title="Sign in to manage failed jobs." />;

  return (
    <FailedJobsPanel
      canReprocess={userCanReview}
      jobs={failedJobsQuery.data ?? []}
      onBulkReprocess={(jobs) => bulkReprocessMutation.mutate(jobs)}
      onRefresh={() => void failedJobsQuery.refetch()}
      onReprocess={(job) => reprocessMutation.mutate(job)}
      reprocessingJobId={reprocessMutation.isPending ? reprocessMutation.variables?.processing_job_id ?? null : null}
    />
  );
}
