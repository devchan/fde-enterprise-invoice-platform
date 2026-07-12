import type { InvoiceDetail, InvoiceFile, Session } from "../domain/types";
import type { ApiClient } from "./api-client";

export class InvoiceService {
  constructor(private readonly apiClient: ApiClient) {}

  async list(session: Session): Promise<InvoiceDetail[]> {
    const data = await this.apiClient.request<{ invoices: InvoiceDetail[] }>("/api/v1/invoices?limit=50", {}, session);
    return data.invoices;
  }

  get(session: Session, invoiceId: string): Promise<InvoiceDetail> {
    return this.apiClient.request<InvoiceDetail>(`/api/v1/invoices/${invoiceId}`, {}, session);
  }

  upload(session: Session, form: FormData): Promise<{ invoice_id: string; invoice_number: string; processing_job_id: string | null }> {
    return this.apiClient.request<{ invoice_id: string; invoice_number: string; processing_job_id: string | null }>(
      "/api/v1/invoices/upload",
      { method: "POST", body: form },
      session,
    );
  }

  review(
    session: Session,
    invoiceId: string,
    payload: {
      decision: "approve" | "reject";
      notes: string;
      corrected_fields: Record<string, string | undefined>;
      expected_updated_at: string;
    },
  ): Promise<InvoiceDetail> {
    return this.apiClient.request<InvoiceDetail>(
      `/api/v1/invoices/${invoiceId}/review`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      session,
    );
  }

  async createDownloadUrl(session: Session, invoiceId: string, file: InvoiceFile): Promise<string> {
    const data = await this.apiClient.request<{ download_url: string }>(
      `/api/v1/invoices/${invoiceId}/files/${file.file_id}/download-url`,
      {},
      session,
    );
    return data.download_url;
  }
}
