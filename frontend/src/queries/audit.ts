import { useQuery } from "@tanstack/react-query";
import type { Session } from "../domain/types";
import { auditLogService } from "../services";
import { auditKeys } from "./keys";

export function useAuditLogsQuery(session: Session | null, params?: URLSearchParams) {
  const searchParams = params ?? new URLSearchParams({ limit: "50" });
  return useQuery({
    queryKey: auditKeys.list(session?.organization_id ?? "", searchParams.toString()),
    queryFn: () => auditLogService.list(session as Session, searchParams),
    enabled: Boolean(session),
  });
}
