import { createRoute } from "@tanstack/react-router";
import { useCockpit } from "../app/CockpitContext";
import { AccessRequiredPanel, SignInRequiredPanel } from "../components/common/AccessPanels";
import { UploadPanel } from "../features/invoices/UploadPanel";
import { Route as RootRoute } from "./__root";

export const Route = createRoute({
  getParentRoute: () => RootRoute,
  path: "/upload",
  component: UploadRoute,
});

function UploadRoute() {
  const { busy, defaultProvider, extractionProviders, session, userCanUpload, actions } = useCockpit();

  if (!session) return <SignInRequiredPanel title="Sign in to upload invoices." />;
  if (!userCanUpload) return <AccessRequiredPanel title="Upload requires admin or uploader access." />;

  return (
    <UploadPanel
      busy={busy === "upload"}
      onSubmit={actions.uploadInvoice}
      providers={extractionProviders}
      defaultProvider={defaultProvider}
    />
  );
}
