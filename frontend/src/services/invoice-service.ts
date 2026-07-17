import type { ExtractionProvidersResponse, InvoiceDetail, InvoiceFile, Session, SimilarInvoicesResponse } from "../domain/types";
import type { ApiClient } from "./api-client";

export class InvoiceService {
  constructor(private readonly apiClient: ApiClient) {}

  // Endpoints are tenant-scoped server-side via the session; the client only forwards it.
  async list(session: Session): Promise<InvoiceDetail[]> {
    // Unwrap the paginated envelope so callers get a plain array.
    const data = await this.apiClient.request<{ invoices: InvoiceDetail[] }>("/api/v1/invoices?limit=50", {}, session);
    return data.invoices;
  }

  get(session: Session, invoiceId: string): Promise<InvoiceDetail> {
    return this.apiClient.request<InvoiceDetail>(`/api/v1/invoices/${invoiceId}`, {}, session);
  }

  // Nearest invoices by embedding cosine similarity (pgvector, same org). Empty
  // until the worker has embedded the invoice post-extraction.
  async similar(session: Session, invoiceId: string): Promise<SimilarInvoicesResponse["similar_invoices"]> {
    const data = await this.apiClient.request<SimilarInvoicesResponse>(`/api/v1/invoices/${invoiceId}/similar`, {}, session);
    return data.similar_invoices;
  }

  // Lists extraction providers and whether each is usable, so the upload form
  // can disable options whose API key isn't configured server-side.
  getProviders(session: Session): Promise<ExtractionProvidersResponse> {
    return this.apiClient.request<ExtractionProvidersResponse>("/api/v1/extraction/providers", {}, session);
  }

  // Passes FormData through untouched so the client sets a multipart body (not JSON) for the file upload.
  upload(session: Session, form: FormData): Promise<{ invoice_id: string; invoice_number: string; processing_job_id: string | null }> {
    return this.apiClient.request<{ invoice_id: string; invoice_number: string; processing_job_id: string | null }>(
      "/api/v1/invoices/upload",
      { method: "POST", body: form },
      session,
    );
  }

  // expected_updated_at is sent for optimistic-concurrency: the server rejects the review
  // if the invoice changed since it was loaded, preventing clobbering a concurrent edit.
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

  // Files are not served directly: the API mints a short-lived, pre-signed URL per request.
  async createDownloadUrl(session: Session, invoiceId: string, file: InvoiceFile): Promise<string> {
    const data = await this.apiClient.request<{ download_url: string }>(
      `/api/v1/invoices/${invoiceId}/files/${file.file_id}/download-url`,
      {},
      session,
    );
    return data.download_url;
  }
}
