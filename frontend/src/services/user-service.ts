import type { Session, UserRecord } from "../domain/types";
import type { ApiClient } from "./api-client";

// Admin-only user administration. Access is enforced server-side; the UI only
// exposes these calls once the session role is "admin".
export class UserService {
  constructor(private readonly apiClient: ApiClient) {}

  // Unwrap the paginated envelope so callers get a plain array.
  async list(session: Session): Promise<UserRecord[]> {
    const data = await this.apiClient.request<{ users: UserRecord[] }>("/api/v1/users", {}, session);
    return data.users;
  }

  create(session: Session, payload: { email: string; role: string; password: string }): Promise<UserRecord> {
    return this.apiClient.request<UserRecord>(
      "/api/v1/users",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      session,
    );
  }

  // PATCH: only the fields present are changed; password is handled separately below.
  update(session: Session, user: UserRecord, payload: { email: string; role: string }): Promise<UserRecord> {
    return this.apiClient.request<UserRecord>(
      `/api/v1/users/${user.user_id}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
      session,
    );
  }

  // Admin-initiated reset (no current password needed, unlike self-service change).
  resetPassword(session: Session, user: UserRecord, password: string): Promise<UserRecord> {
    return this.apiClient.request<UserRecord>(
      `/api/v1/users/${user.user_id}/password`,
      {
        method: "POST",
        body: JSON.stringify({ password }),
      },
      session,
    );
  }
}
