import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "../app/ToastContext";
import type { InvoiceDetail, Session } from "../domain/types";
import { invoiceService } from "../services";
import { useReviewInvoiceMutation } from "./invoices";

vi.mock("../services", () => ({
  invoiceService: { review: vi.fn() },
}));

const session: Session = {
  user_id: "u1",
  organization_id: "o1",
  email: "user@example.com",
  role: "admin",
};

const invoice: InvoiceDetail = {
  invoice_id: "inv-1",
  organization_id: "o1",
  supplier_id: null,
  uploaded_by: "u1",
  invoice_number: "INV-1",
  invoice_date: null,
  total_amount: "10.00",
  currency: "USD",
  status: "review_required",
  file_checksum: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  files: [],
  line_items: [],
  latest_extraction: null,
  validation_results: [],
  reviews: [],
};

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useReviewInvoiceMutation", () => {
  it("shows a distinct toast and does not surface the raw error on a 409 conflict", async () => {
    vi.mocked(invoiceService.review).mockRejectedValue(new Error("invoice_review_conflict: Invoice changed since it was loaded."));

    const { result } = renderHook(
      () => ({ mutation: useReviewInvoiceMutation(session), toast: useToast() }),
      { wrapper },
    );

    await act(async () => {
      result.current.mutation.mutate({
        invoiceId: invoice.invoice_id,
        decision: "approve",
        notes: "",
        corrected_fields: {},
        expected_updated_at: invoice.updated_at,
      });
    });

    await waitFor(() => expect(result.current.mutation.isError).toBe(true));
    expect(result.current.toast.toast?.message).toBe(
      "This invoice was updated by someone else — refresh to see the latest version.",
    );
    expect(result.current.toast.toast?.tone).toBe("error");
  });

  it("shows the raw error message for a non-conflict failure", async () => {
    vi.mocked(invoiceService.review).mockRejectedValue(new Error("api_error: Something went wrong."));

    const { result } = renderHook(
      () => ({ mutation: useReviewInvoiceMutation(session), toast: useToast() }),
      { wrapper },
    );

    await act(async () => {
      result.current.mutation.mutate({
        invoiceId: invoice.invoice_id,
        decision: "approve",
        notes: "",
        corrected_fields: {},
        expected_updated_at: invoice.updated_at,
      });
    });

    await waitFor(() => expect(result.current.mutation.isError).toBe(true));
    expect(result.current.toast.toast?.message).toBe("api_error: Something went wrong.");
  });
});
