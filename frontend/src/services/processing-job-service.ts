import type { ProcessingJob, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

// Recovery surface for the async extraction pipeline: list failures and requeue them.
export class ProcessingJobService {
  constructor(private readonly apiClient: ApiClient) {}

  // Only failed jobs are fetched; healthy jobs are not surfaced in the operator UI.
  async listFailed(session: Session): Promise<ProcessingJob[]> {
    const data = await this.apiClient.request<{ jobs: ProcessingJob[] }>("/api/v1/processing-jobs/failed?limit=50", {}, session);
    return data.jobs;
  }

  // Empty body: the server re-derives the work from the job record; we only signal intent to retry.
  reprocess(session: Session, job: ProcessingJob): Promise<ProcessingJob> {
    return this.apiClient.request<ProcessingJob>(
      `/api/v1/processing-jobs/${job.processing_job_id}/reprocess`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
      session,
    );
  }
}
