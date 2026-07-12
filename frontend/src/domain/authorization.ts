import type { Session, TabKey } from "./types";

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
  if (tab === "overview") return true;
  if (!session) return false;
  if (tab === "upload") return canUpload(session);
  if (tab === "review") return canReview(session);
  if (tab === "users") return isAdmin(session);
  return true;
}
