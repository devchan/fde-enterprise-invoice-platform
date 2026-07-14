import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { API_BASE_URL } from "../config";
import type { Session } from "../domain/types";
import { auditKeys, invoiceKeys, jobKeys } from "./keys";

type RealtimeEvent = {
  type: "job.completed" | "job.failed" | "job.requeued" | "invoice.status_changed";
  invoice_id?: string;
  processing_job_id?: string;
  status?: string;
  occurred_at: string;
};

// Signal-not-payload: the event only tells us what changed, so we invalidate the
// relevant react-query cache entries and let the next render refetch the real data.
export function useRealtimeEvents(session: Session | null) {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!session) {
      setConnected(false);
      return;
    }
    const orgId = session.organization_id;
    const source = new EventSource(`${API_BASE_URL}/api/v1/events/stream`, { withCredentials: true });

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      let event: RealtimeEvent;
      try {
        event = JSON.parse(message.data) as RealtimeEvent;
      } catch {
        return;
      }
      switch (event.type) {
        case "job.completed":
        case "job.failed":
        case "job.requeued":
          void queryClient.invalidateQueries({ queryKey: invoiceKeys.list(orgId) });
          void queryClient.invalidateQueries({ queryKey: jobKeys.failed(orgId) });
          void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
          break;
        case "invoice.status_changed":
          void queryClient.invalidateQueries({ queryKey: invoiceKeys.list(orgId) });
          if (event.invoice_id) {
            void queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(orgId, event.invoice_id) });
          }
          void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
          break;
      }
    };

    return () => {
      source.close();
      setConnected(false);
    };
  }, [session, queryClient]);

  return { connected };
}
