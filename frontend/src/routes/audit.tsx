import { createRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useSession } from "../app/useSession";
import { SignInRequiredPanel } from "../components/common/AccessPanels";
import { useAuditLogsQuery } from "../queries/audit";
import { AuditPanel } from "../features/audit/AuditPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/audit",
  component: AuditRoute,
});

function AuditRoute() {
  const { session } = useSession();
  const [filterParams, setFilterParams] = useState<URLSearchParams>();
  const auditLogsQuery = useAuditLogsQuery(session, filterParams);

  if (!session) return <SignInRequiredPanel title="Sign in to view audit logs." />;

  return (
    <AuditPanel
      logs={auditLogsQuery.data ?? []}
      busy={auditLogsQuery.isFetching}
      onFilter={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        // Build the query from only the filled filter inputs; omitted keys mean "no filter".
        const params = new URLSearchParams({ limit: "50" });
        for (const key of ["entity_type", "entity_id", "action"]) {
          const value = String(form.get(key) || "").trim();
          if (value) params.set(key, value);
        }
        setFilterParams(params);
      }}
      onRefresh={() => void auditLogsQuery.refetch()}
    />
  );
}
