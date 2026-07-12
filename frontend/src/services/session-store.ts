import { SESSION_STORAGE_KEY } from "../config";
import type { Session } from "../domain/types";

// Caches non-sensitive identity in localStorage for fast UI hydration on reload.
// It is a UX convenience only, never the auth source of truth (that is the httpOnly cookie).
export class SessionStore {
  static read(): Session | null {
    try {
      const value = localStorage.getItem(SESSION_STORAGE_KEY);
      return value ? (JSON.parse(value) as Session) : null;
    } catch {
      // Corrupt/absent storage or JSON parse failure: treat as no cached identity.
      return null;
    }
  }

  static write(session: Session): void {
    // Persist only non-sensitive identity for UI/RBAC. The auth token lives in
    // an httpOnly cookie and is deliberately never written to localStorage.
    const context = {
      user_id: session.user_id,
      organization_id: session.organization_id,
      email: session.email,
      role: session.role,
    };
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(context));
  }

  static clear(): void {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}
