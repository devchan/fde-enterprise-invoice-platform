import { createRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { useSession } from "../app/useSession";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { emptyToUndefined } from "../utils/form";
import { useAskAssistantMutation } from "../queries/assistant";
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
  const askAssistantMutation = useAskAssistantMutation(session);

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
      assistantAnswer={askAssistantMutation.data ?? null}
      isAiSearching={nlSearchMutation.isPending}
      isAsking={askAssistantMutation.isPending}
      onAiSearch={(query) => nlSearchMutation.mutate(query)}
      onAsk={(question) => askAssistantMutation.mutate(question)}
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
