import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "../app/ToastContext";
import type { InvoiceDetail, Session } from "../domain/types";
import { invoiceService } from "../services";
import { errorMessage } from "../utils/form";
import { auditKeys, invoiceKeys } from "./keys";

export function useInvoicesQuery(session: Session | null) {
  return useQuery({
    queryKey: invoiceKeys.list(session?.organization_id ?? ""),
    queryFn: () => invoiceService.list(session as Session),
    enabled: Boolean(session),
  });
}

export function useInvoiceQuery(session: Session | null, invoiceId: string | undefined) {
  return useQuery({
    queryKey: invoiceKeys.detail(session?.organization_id ?? "", invoiceId ?? ""),
    queryFn: () => invoiceService.get(session as Session, invoiceId as string),
    enabled: Boolean(session && invoiceId),
  });
}

export function useExtractionProvidersQuery(session: Session | null) {
  return useQuery({
    queryKey: invoiceKeys.providers(session?.organization_id ?? ""),
    queryFn: () => invoiceService.getProviders(session as Session),
    enabled: Boolean(session),
    staleTime: 5 * 60_000, // provider availability rarely changes
  });
}

export function useUploadInvoiceMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (form: FormData) => invoiceService.upload(session as Session, form),
    onSuccess: (result) => {
      setToast({ message: `Uploaded ${result.invoice_number}.`, tone: "ok" });
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.list(session?.organization_id ?? "") });
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

export function useReviewInvoiceMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: (payload: {
      invoiceId: string;
      decision: "approve" | "reject";
      notes: string;
      corrected_fields: Record<string, string | undefined>;
      expected_updated_at: string;
    }) =>
      invoiceService.review(session as Session, payload.invoiceId, {
        decision: payload.decision,
        notes: payload.notes,
        corrected_fields: payload.corrected_fields,
        expected_updated_at: payload.expected_updated_at,
      }),
    onSuccess: (detail: InvoiceDetail, variables) => {
      queryClient.setQueryData(invoiceKeys.detail(orgId, detail.invoice_id), detail);
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.list(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
      setToast({ message: `Invoice ${variables.decision === "approve" ? "approved" : "rejected"}.`, tone: "ok" });
    },
    onError: (error, variables) => {
      if (errorMessage(error).startsWith("invoice_review_conflict")) {
        setToast({ message: "This invoice was updated by someone else — refresh to see the latest version.", tone: "error" });
        void queryClient.invalidateQueries({ queryKey: invoiceKeys.detail(orgId, variables.invoiceId) });
        return;
      }
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}

// Client-side bulk action: the backend has no bulk-review endpoint, so this fires
// one request per invoice and reports a single summary toast instead of the N
// individual toasts useReviewInvoiceMutation would otherwise show.
export function useBulkReviewInvoicesMutation(session: Session | null) {
  const queryClient = useQueryClient();
  const { setToast } = useToast();
  const orgId = session?.organization_id ?? "";

  return useMutation({
    mutationFn: async ({ invoices, decision }: { invoices: InvoiceDetail[]; decision: "approve" | "reject" }) =>
      Promise.allSettled(
        invoices.map((invoice) =>
          invoiceService.review(session as Session, invoice.invoice_id, {
            decision,
            notes: "",
            corrected_fields: {},
            expected_updated_at: invoice.updated_at,
          }),
        ),
      ),
    onSuccess: (results, variables) => {
      const succeeded = results.filter((result) => result.status === "fulfilled").length;
      const failed = results.length - succeeded;
      const verb = variables.decision === "approve" ? "approved" : "rejected";
      void queryClient.invalidateQueries({ queryKey: invoiceKeys.list(orgId) });
      void queryClient.invalidateQueries({ queryKey: auditKeys.all(orgId) });
      setToast({
        message:
          failed === 0
            ? `${succeeded} invoice${succeeded === 1 ? "" : "s"} ${verb}.`
            : `${succeeded} ${verb}, ${failed} failed — see audit log.`,
        tone: failed === 0 ? "ok" : "error",
      });
    },
  });
}

export function useOpenInvoiceFileMutation(session: Session | null) {
  const { setToast } = useToast();

  return useMutation({
    mutationFn: (payload: { invoiceId: string; file: InvoiceDetail["files"][number] }) =>
      invoiceService.createDownloadUrl(session as Session, payload.invoiceId, payload.file),
    onSuccess: (downloadUrl) => {
      window.open(downloadUrl, "_blank", "noopener,noreferrer");
    },
    onError: (error) => {
      setToast({ message: errorMessage(error), tone: "error" });
    },
  });
}
