import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { SignInRequiredPanel } from "../components/common/AccessPanels";
import { FailedJobsPanel } from "../features/jobs/FailedJobsPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/failed",
  component: FailedRoute,
});

function FailedRoute() {
  const { busy, failedJobs, session, userCanReview, actions } = useCockpit();

  if (!session) return <SignInRequiredPanel title="Sign in to manage failed jobs." />;

  return (
    <FailedJobsPanel
      busy={busy}
      canReprocess={userCanReview}
      jobs={failedJobs}
      onRefresh={() => actions.loadFailedJobs()}
      onReprocess={actions.reprocessJob}
    />
  );
}
