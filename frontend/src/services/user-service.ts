import type { Session, UserRecord } from "../domain/types";
import type { ApiClient } from "./api-client";

export class UserService {
  constructor(private readonly apiClient: ApiClient) {}

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
