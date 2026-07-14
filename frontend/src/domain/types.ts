export type Session = {
  // Auth is carried by httpOnly cookies; the token is never stored client-side.
  // These remain optional only because the login response body still includes
  // them for non-browser API clients.
  access_token?: string;
  expires_in?: number;
  user_id: string;
  organization_id: string;
  email: string;
  role: string;
};

export type ApiError = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
};

export type InvoiceFile = {
  file_id: string;
  storage_key: string;
  mime_type: string;
  file_size: number;
};

export type InvoiceLineItem = {
  line_item_id: string;
  description: string;
  // Monetary/quantity values arrive as strings to preserve exact decimal precision
  // (avoiding JS float rounding); null when the extractor could not determine them.
  quantity: string | null;
  unit_price: string | null;
  line_total: string | null;
};

export type InvoiceDetail = {
  invoice_id: string;
  organization_id: string;
  supplier_id: string | null;
  uploaded_by: string;
  invoice_number: string;
  invoice_date: string | null;
  total_amount: string | null;
  currency: string;
  status: string;
  file_checksum: string | null;
  created_at: string;
  updated_at: string;
  files: InvoiceFile[];
  line_items: InvoiceLineItem[];
  latest_extraction: null | {
    extraction_id: string;
    model_name: string;
    prompt_version: string;
    confidence_score: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost: string | null;
    extracted_payload: Record<string, unknown>;
  };
  validation_results: Array<{
    validation_result_id: string;
    rule_code: string;
    severity: string;
    message: string;
    passed: boolean;
  }>;
  reviews: Array<{
    review_id: string;
    reviewer_id: string;
    decision: string;
    notes: string | null;
    corrected_fields: Record<string, unknown> | null;
    created_at: string;
  }>;
};

export type ProcessingJob = {
  processing_job_id: string;
  invoice_id: string;
  job_type: string;
  status: string;
  attempts: number;
  last_error: string | null;
};

export type AuditLog = {
  audit_log_id: string;
  actor_user_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  metadata: Record<string, unknown>;
  request_id: string | null;
  created_at: string;
};

export type UserRecord = {
  user_id: string;
  organization_id: string;
  email: string;
  role: string;
};

// Stable identifiers for the cockpit tabs; drives both navigation and RBAC gating.
export type TabKey = "overview" | "upload" | "review" | "failed" | "audit" | "users";

// An extraction provider option for the upload form; `available` is false when
// the server has no API key for it, so the UI renders that option disabled.
export type ExtractionProvider = {
  id: string;
  label: string;
  available: boolean;
};

export type ExtractionProvidersResponse = {
  default: string | null;
  providers: ExtractionProvider[];
};

export type LoginCredentials = {
  email: string;
  password: string;
};
