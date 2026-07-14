import { createRoute, useNavigate } from "@tanstack/react-router";
import { useSession } from "../app/useSession";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { useExtractionProvidersQuery, useUploadInvoiceMutation } from "../queries/invoices";
import { UploadPanel } from "../features/invoices/UploadPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/upload",
  component: UploadRoute,
});

function UploadRoute() {
  const { session, userCanUpload } = useSession();
  const navigate = useNavigate();
  const providersQuery = useExtractionProvidersQuery(session);
  const uploadMutation = useUploadInvoiceMutation(session);

  if (!session) return <SignInRequiredPanel title="Sign in to upload invoices." />;
  if (!userCanUpload) return <AccessRequiredPanel title="Upload requires admin or uploader access." />;

  return (
    <UploadPanel
      busy={uploadMutation.isPending}
      onSubmit={(event) => {
        event.preventDefault();
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        // Drop blank optional fields so the backend sees them as absent rather than empty strings.
        for (const key of ["supplier_id", "total_amount"]) {
          if (!String(form.get(key) || "").trim()) form.delete(key);
        }
        uploadMutation.mutate(form, {
          onSuccess: (result) => {
            formElement.reset();
            void navigate({ to: "/review", search: { invoiceId: result.invoice_id } });
          },
        });
      }}
      providers={providersQuery.data?.providers ?? []}
      defaultProvider={providersQuery.data?.default ?? null}
    />
  );
}
