import type { ProcessingJob, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class ProcessingJobService {
  constructor(private readonly apiClient: ApiClient) {}

  async listFailed(session: Session): Promise<ProcessingJob[]> {
    const data = await this.apiClient.request<{ jobs: ProcessingJob[] }>("/api/v1/processing-jobs/failed?limit=50", {}, session);
    return data.jobs;
  }

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
