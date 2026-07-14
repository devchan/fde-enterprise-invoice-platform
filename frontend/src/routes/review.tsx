import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { ReviewPanel } from "../features/invoices/ReviewPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/review",
  component: ReviewRoute,
});

function ReviewRoute() {
  const { busy, invoices, selectedInvoice, session, userCanReview, actions } = useCockpit();

  if (!session) return <SignInRequiredPanel title="Sign in to review invoices." />;
  if (!userCanReview) return <AccessRequiredPanel title="Review requires admin or reviewer access." />;

  return (
    <ReviewPanel
      busy={busy}
      invoices={invoices}
      onOpenFile={actions.openFile}
      onRefresh={() => actions.loadInvoices()}
      onReview={actions.reviewInvoice}
      onSelect={actions.loadInvoice}
      selectedInvoice={selectedInvoice}
    />
  );
}
