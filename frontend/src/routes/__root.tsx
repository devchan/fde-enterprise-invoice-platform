import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { KeyRound, Lock, Loader2, LogOut } from "lucide-react";
import { tabs } from "../app/navigation";
import { CockpitProvider, useCockpit } from "../app/CockpitContext";
import { useCockpitController } from "../app/useCockpitController";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { Field } from "../components/common/Field";
import { ModeToggle } from "../components/common/ModeToggle";
import { StatusPill } from "../components/common/StatusPill";
import { Toast } from "../components/common/Toast";
import { canAccessTab } from "../domain/authorization";
import { SignInForm } from "../features/auth/SignInForm";

export const Route = createRootRoute({
  component: RootComponent,
});

function RootComponent() {
  const controller = useCockpitController();
  return (
    <CockpitProvider value={controller}>
      <RootLayout />
    </CockpitProvider>
  );
}

function RootLayout() {
  const { busy, health, session, toast, actions } = useCockpit();

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">FDE Invoice Platform</p>
            <h1 className="text-2xl font-semibold tracking-normal">Reviewer Cockpit</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label="API" tone={health === "ok" ? "ok" : health === "error" ? "error" : "info"} />
            <ModeToggle />
            {session ? (
              <>
                <span className="session-chip rounded border border-border px-3 py-2 text-sm text-muted-foreground">
                  {session.email} · {session.role}
                </span>
                <Button onClick={actions.logout} type="button" variant="outline">
                  <LogOut className="h-4 w-4" />
                  Sign out
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-max min-w-0">
          <CardContent className="p-4">
            <nav className="space-y-1 text-sm" aria-label="Primary">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const locked = !canAccessTab(session, tab.key);
                return (
                  <Link
                    activeProps={{ className: "nav-button-active" }}
                    className="nav-button"
                    key={tab.key}
                    to={tab.path}
                  >
                    <span className="flex items-center gap-2">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {tab.label}
                    </span>
                    {locked ? (
                      <Lock className="nav-lock h-3.5 w-3.5" aria-label="Access restricted" />
                    ) : (
                      <span className="text-muted-foreground" aria-hidden="true">
                        ›
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            {!session ? (
              <SignInForm busy={busy === "login"} onSubmit={actions.login} />
            ) : (
              <form className="mt-5 space-y-3 border-t border-border pt-5" onSubmit={actions.changeOwnPassword}>
                <h2 className="text-sm font-semibold">Account</h2>
                <Field label="Current password" name="current_password" type="password" required />
                <Field label="New password" name="new_password" type="password" minLength={12} required />
                <Button className="w-full" disabled={busy === "own-password"} type="submit" variant="outline">
                  {busy === "own-password" ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                  Change password
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-6">
          {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => actions.setToast(null)} /> : null}
          <Outlet />
        </div>
      </section>
    </main>
  );
}
