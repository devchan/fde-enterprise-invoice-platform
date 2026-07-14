import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { OverviewPanel } from "../features/dashboard/OverviewPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/",
  component: OverviewRoute,
});

function OverviewRoute() {
  const { dashboardStats, initializing, session, actions } = useCockpit();
  return (
    <OverviewPanel
      loading={initializing}
      signedIn={Boolean(session)}
      stats={dashboardStats}
      refresh={() => actions.refreshAll()}
      checkHealth={actions.checkHealth}
    />
  );
}
