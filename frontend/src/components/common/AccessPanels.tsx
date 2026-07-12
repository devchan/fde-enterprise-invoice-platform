import { Loader2, Lock, ShieldCheck } from "lucide-react";

// The three mutually-exclusive placeholder states a gated tab can show instead of
// its content: data is loading, the user is signed out, or the user lacks the role.
export function LoadingPanel({ title }: { title: string }) {
  return (
    <section className="callout-panel">
      <div className="callout-icon">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">Fetching tenant-scoped invoices, jobs, audit logs, and account data.</p>
      </div>
    </section>
  );
}

export function SignInRequiredPanel({ title }: { title: string }) {
  return (
    <section className="callout-panel">
      <div className="callout-icon">
        <ShieldCheck className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Use the sign-in form in the sidebar to access tenant-scoped invoices, jobs, audit logs, and user administration.
        </p>
      </div>
    </section>
  );
}

export function AccessRequiredPanel({ title }: { title: string }) {
  return (
    <section className="callout-panel">
      <div className="callout-icon callout-icon-warning">
        <Lock className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Switch to an account with the required role or ask an administrator to update your access.
        </p>
      </div>
    </section>
  );
}
