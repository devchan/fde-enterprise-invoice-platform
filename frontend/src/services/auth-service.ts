import type { Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class AuthService {
  constructor(private readonly apiClient: ApiClient) {}

  login(email: string, password: string): Promise<Session> {
    return this.apiClient.request<Session>(
      "/api/v1/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
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
