import { Lock, ShieldCheck } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";

// The two mutually-exclusive placeholder states a gated tab can show instead of
// its content: the user is signed out, or the user lacks the role.
export function SignInRequiredPanel({ title }: { title: string }) {
  return (
    <Alert>
      <ShieldCheck className="h-4 w-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        Use the sign-in form in the sidebar to access tenant-scoped invoices, jobs, audit logs, and user administration.
      </AlertDescription>
    </Alert>
  );
}

export function AccessRequiredPanel({ title }: { title: string }) {
  return (
    <Alert variant="warning">
      <Lock className="h-4 w-4" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>Switch to an account with the required role or ask an administrator to update your access.</AlertDescription>
    </Alert>
  );
}
