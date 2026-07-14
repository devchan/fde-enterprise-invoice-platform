import { canReview, canUpload, isAdmin } from "../domain/authorization";
import { useSessionQuery } from "../queries/auth";

// Plain hook, not a Context: react-query already dedupes/shares the underlying
// /auth/me fetch across every caller, so no provider/prop-drilling is needed here.
export function useSession() {
  const sessionQuery = useSessionQuery();
  const session = sessionQuery.data ?? null;

  return {
    session,
    sessionLoading: sessionQuery.isLoading,
    userIsAdmin: isAdmin(session),
    userCanReview: canReview(session),
    userCanUpload: canUpload(session),
  };
}
