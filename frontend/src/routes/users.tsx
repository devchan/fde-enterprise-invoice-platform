import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { UsersPanel } from "../features/users/UsersPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/users",
  component: UsersRoute,
});

function UsersRoute() {
  const { busy, session, userIsAdmin, users, actions } = useCockpit();

  if (!session) return <SignInRequiredPanel title="Sign in to administer users." />;
  if (!userIsAdmin) return <AccessRequiredPanel title="User administration requires admin access." />;

  return (
    <UsersPanel
      busy={busy}
      onCreate={actions.createUser}
      onRefresh={() => actions.loadUsers()}
      onResetPassword={actions.resetUserPassword}
      onUpdate={actions.updateUser}
      users={users}
    />
  );
}
