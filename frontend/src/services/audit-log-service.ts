import type { AuditLog, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

// Read-only access to the tenant's audit trail.
export class AuditLogService {
  constructor(private readonly apiClient: ApiClient) {}

  // params defaults to a bare limit; callers pass filters (entity/action) via the same URLSearchParams.
  async list(session: Session, params = new URLSearchParams({ limit: "50" })): Promise<AuditLog[]> {
    // Unwrap the envelope so callers get a plain array.
    const data = await this.apiClient.request<{ audit_logs: AuditLog[] }>(`/api/v1/audit-logs?${params.toString()}`, {}, session);
    return data.audit_logs;
  }
}
