import type { AuditLog, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class AuditLogService {
  constructor(private readonly apiClient: ApiClient) {}

  async list(session: Session, params = new URLSearchParams({ limit: "50" })): Promise<AuditLog[]> {
    const data = await this.apiClient.request<{ audit_logs: AuditLog[] }>(`/api/v1/audit-logs?${params.toString()}`, {}, session);
    return data.audit_logs;
  }
}
