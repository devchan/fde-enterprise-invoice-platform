import { useEffect } from "react";
import { createRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { useAssistant } from "../app/AssistantContext";
import { useSession } from "../app/useSession";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { emptyToUndefined } from "../utils/form";
import {
  useBulkReviewInvoicesMutation,
  useInvoiceQuery,
  useInvoicesQuery,
  useNLSearchInvoicesMutation,
  useOpenInvoiceFileMutation,
  useReviewInvoiceMutation,
  useSimilarInvoicesQuery,
} from "../queries/invoices";
import { ReviewPanel } from "../features/invoices/ReviewPanel";
import { Route as RootRoute } from "./__root";

const reviewSearchSchema = z.object({
  invoiceId: z.string().optional(),
});

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/review",
  validateSearch: reviewSearchSchema,
  component: ReviewRoute,
});

function ReviewRoute() {
  const { session, userCanReview } = useSession();
  const { invoiceId } = Route.useSearch();
  const navigate = useNavigate();

  const invoicesQuery = useInvoicesQuery(session);
  const selectedInvoiceQuery = useInvoiceQuery(session, invoiceId);
  const similarInvoicesQuery = useSimilarInvoicesQuery(session, invoiceId);
  const reviewMutation = useReviewInvoiceMutation(session);
  const bulkReviewMutation = useBulkReviewInvoicesMutation(session);
  const openFileMutation = useOpenInvoiceFileMutation(session);
  const nlSearchMutation = useNLSearchInvoicesMutation(session);

  // Hand the currently-open invoice to the global assistant so its "why is this
  // stuck?" quick action targets it, then clear on leave.
  const { setContextInvoice } = useAssistant();
  const contextInvoiceData = selectedInvoiceQuery.data;
  useEffect(() => {
    setContextInvoice(
      contextInvoiceData
        ? { invoice_id: contextInvoiceData.invoice_id, invoice_number: contextInvoiceData.invoice_number }
        : null,
    );
    return () => setContextInvoice(null);
  }, [contextInvoiceData, setContextInvoice]);

  if (!session) return <SignInRequiredPanel title="Sign in to review invoices." />;
  if (!userCanReview) return <AccessRequiredPanel title="Review requires admin or reviewer access." />;

  const selectedInvoice = selectedInvoiceQuery.data ?? null;
  // While an AI search result is present it replaces the normal list; reset()
  // (via onClearAiSearch) restores the standard query-backed listing.
  const aiSearchResult = nlSearchMutation.data ?? null;

  return (
    <ReviewPanel
      aiFilters={aiSearchResult?.filters ?? null}
      aiSearchActive={aiSearchResult !== null}
      isAiSearching={nlSearchMutation.isPending}
      onAiSearch={(query) => nlSearchMutation.mutate(query)}
      onClearAiSearch={() => nlSearchMutation.reset()}
      invoices={aiSearchResult?.invoices ?? invoicesQuery.data ?? []}
      isApproving={reviewMutation.isPending && reviewMutation.variables?.decision === "approve"}
      isRejecting={reviewMutation.isPending && reviewMutation.variables?.decision === "reject"}
      onBulkReview={(decision, invoices) => bulkReviewMutation.mutate({ invoices, decision })}
      onClearSelection={() => void navigate({ to: "/review", search: {} })}
      onOpenFile={(file) => selectedInvoice && openFileMutation.mutate({ invoiceId: selectedInvoice.invoice_id, file })}
      onRefresh={() => void invoicesQuery.refetch()}
      onReview={(decision, form) => {
        if (!selectedInvoice) return;
        reviewMutation.mutate({
          invoiceId: selectedInvoice.invoice_id,
          decision,
          notes: String(form.get("notes") || ""),
          corrected_fields: {
            invoice_number: emptyToUndefined(form.get("invoice_number")),
            invoice_date: emptyToUndefined(form.get("invoice_date")),
            total_amount: emptyToUndefined(form.get("total_amount")),
            currency: emptyToUndefined(form.get("currency")),
          },
          expected_updated_at: selectedInvoice.updated_at,
        });
      }}
      onSelect={(id) => void navigate({ to: "/review", search: { invoiceId: id } })}
      openingFileId={openFileMutation.isPending ? openFileMutation.variables?.file.file_id ?? null : null}
      selectedInvoice={selectedInvoice}
      similarInvoices={similarInvoicesQuery.data ?? []}
      similarInvoicesLoading={similarInvoicesQuery.isLoading}
    />
  );
}
