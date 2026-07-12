import type { Session, TabKey } from "./types";

// Client-side RBAC mirrors of the server's role rules: they gate UI affordances
// for a smooth UX, but the API remains the real authority on every request.
// "admin" is a superset that satisfies every capability check.
export function isAdmin(session: Session | null): boolean {
  return session?.role === "admin";
}

export function canReview(session: Session | null): boolean {
  return session?.role === "admin" || session?.role === "reviewer";
}

export function canUpload(session: Session | null): boolean {
  return session?.role === "admin" || session?.role === "uploader";
}

export function canAccessTab(session: Session | null, tab: TabKey): boolean {
  if (tab === "overview") return true; // landing tab is always reachable, even signed out
  if (!session) return false; // every other tab requires authentication
  if (tab === "upload") return canUpload(session);
  if (tab === "review") return canReview(session);
  if (tab === "users") return isAdmin(session);
  // failed/audit: any authenticated user may view (reprocess actions are gated separately).
  return true;
}
