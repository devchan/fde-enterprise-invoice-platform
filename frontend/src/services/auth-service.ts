import type { Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class AuthService {
  constructor(private readonly apiClient: ApiClient) {}

  /** Exchange credentials for a session; the server also sets the httpOnly auth cookies. */
  login(email: string, password: string): Promise<Session> {
    return this.apiClient.request<Session>(
      "/api/v1/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
      // No session yet, so pass null: the client must not attempt a token refresh on a 401 here.
      null,
    );
  }

  /** Rehydrate the session from the httpOnly cookie (used on app load/reload). */
  me(): Promise<Session> {
    return this.apiClient.request<Session>("/api/v1/auth/me", { method: "GET" }, null);
  }

  /** Revoke the current tokens server-side and clear the auth cookies. */
  logout(): Promise<void> {
    return this.apiClient.request<void>("/api/v1/auth/logout", { method: "POST" }, null);
  }

  /** Self-service password change; requires the current password to re-authenticate the actor. */
  changeOwnPassword(session: Session, currentPassword: string, newPassword: string): Promise<void> {
    return this.apiClient.request<void>(
      "/api/v1/users/me/password",
      {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      },
      session,
    );
  }
}
