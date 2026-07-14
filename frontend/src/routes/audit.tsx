import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { SignInRequiredPanel } from "../components/common/AccessPanels";
import { AuditPanel } from "../features/audit/AuditPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/audit",
  component: AuditRoute,
});

function AuditRoute() {
  const { auditLogs, busy, session, actions } = useCockpit();

  if (!session) return <SignInRequiredPanel title="Sign in to view audit logs." />;

  return (
    <AuditPanel
      logs={auditLogs}
      busy={busy === "audit"}
      onFilter={actions.filterAuditLogs}
      onRefresh={() => actions.loadAuditLogs()}
    />
  );
}
