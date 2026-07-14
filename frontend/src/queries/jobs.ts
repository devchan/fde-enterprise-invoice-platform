import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "../app/ToastContext";
import type { ProcessingJob, Session } from "../domain/types";
import { processingJobService } from "../services";
import { errorMessage } from "../utils/form";
import { auditKeys, jobKeys } from "./keys";

export function useFailedJobsQuery(session: Session | null) {
  return useQuery({
    queryKey: jobKeys.failed(session?.organization_id ?? ""),
    queryFn: () => processingJobService.listFailed(session as Session),
    enabled: Boolean(session),
  });
}

export function useReprocessJobMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: (job: ProcessingJob) => processingJobService.reprocess(session as Session, job),
    onSuccess: () => {
      setToast({ message: "Job requeued.", tone: "ok" });
      void queryClient.invalidateQueries({ queryKey: jobKeys.failed(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

// Client-side bulk action: the backend has no bulk-reprocess endpoint, so this fires
// one request per job and reports a single summary toast instead of N individual ones.
export function useBulkReprocessJobsMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: (jobs: ProcessingJob[]) => Promise.allSettled(jobs.map((job) => processingJobService.reprocess(session as Session, job))),
    onSuccess: (results) => {
      const succeeded = results.filter((result) => result.status === "fulfilled").length;
      const failed = results.length - succeeded;
      void queryClient.invalidateQueries({ queryKey: jobKeys.failed(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
      setToast({
        message:
          failed === 0
            ? `${succeeded} job${succeeded === 1 ? "" : "s"} requeued.`
            : `${succeeded} requeued, ${failed} failed — see audit log.`,
        tone: failed === 0 ? "ok" : "error",
      });
    },
  });
}
