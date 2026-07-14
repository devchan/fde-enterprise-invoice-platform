import { createRoute } from "@tanstack/react-router";
import { useSession } from "../app/useSession";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { useCreateUserMutation, useResetPasswordMutation, useUpdateUserMutation, useUsersQuery } from "../queries/users";
import { UsersPanel } from "../features/users/UsersPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/users",
  component: UsersRoute,
});

function UsersRoute() {
  const { session, userIsAdmin } = useSession();
  const usersQuery = useUsersQuery(session);
  const createMutation = useCreateUserMutation(session);
  const updateMutation = useUpdateUserMutation(session);
  const resetPasswordMutation = useResetPasswordMutation(session);

  if (!session) return <SignInRequiredPanel title="Sign in to administer users." />;
  if (!userIsAdmin) return <AccessRequiredPanel title="User administration requires admin access." />;

  return (
    <UsersPanel
      creatingUser={createMutation.isPending}
      onCreate={(event) => {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        createMutation.mutate(
          {
            email: String(form.get("email") || "").trim(),
            role: String(form.get("role") || "reviewer"),
            password: String(form.get("password") || ""),
          },
          { onSuccess: () => formElement.reset() },
        );
      }}
      onRefresh={() => void usersQuery.refetch()}
      onResetPassword={(user, password) => resetPasswordMutation.mutate({ user, password })}
      onUpdate={(user, event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        updateMutation.mutate({
          user,
          email: String(form.get("email") || "").trim(),
          role: String(form.get("role") || user.role),
        });
      }}
      resettingPasswordUserId={resetPasswordMutation.isPending ? resetPasswordMutation.variables?.user.user_id ?? null : null}
      updatingUserId={updateMutation.isPending ? updateMutation.variables?.user.user_id ?? null : null}
      users={usersQuery.data ?? []}
    />
  );
}
