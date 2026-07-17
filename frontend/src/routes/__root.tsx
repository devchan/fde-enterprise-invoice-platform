import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { KeyRound, Lock, Loader2, LogOut, Search } from "lucide-react";
import { useState } from "react";
import { AssistantProvider } from "../app/AssistantContext";
import { tabs } from "../app/navigation";
import { useHealth } from "../app/useHealth";
import { useSession } from "../app/useSession";
import { useSessionExpiredHandler } from "../app/useSessionExpiredHandler";
import { useChangeOwnPasswordMutation, useLoginMutation, useLogoutMutation } from "../queries/auth";
import { useRealtimeEvents } from "../queries/realtime";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { CommandPalette } from "../components/common/CommandPalette";
import { Field } from "../components/common/Field";
import { ModeToggle } from "../components/common/ModeToggle";
import { StatusPill } from "../components/common/StatusPill";
import { Toast } from "../components/common/Toast";
import { useToast } from "../app/ToastContext";
import { canAccessTab } from "../domain/authorization";
import { SignInForm } from "../features/auth/SignInForm";
import { AssistantWidget } from "../features/invoices/AssistantWidget";

export const Route = createRootRoute({
  component: RootComponent,
});

// Topbar brand block: amber dot with the soft glow ring + mono wordmark,
// mirroring the architecture view's identity.
function Brand() {
  return (
    <span className="flex items-center gap-2.5 font-mono text-[13px] tracking-wide text-foreground">
      <span className="brand-dot" aria-hidden="true" />
      FDE&nbsp;·&nbsp;INVOICE&nbsp;OPS
    </span>
  );
}

function RootComponent() {
  useSessionExpiredHandler();
  const { health } = useHealth();
  const { session, sessionLoading } = useSession();
  const { connected: liveUpdatesConnected } = useRealtimeEvents(session);
  const { toast, setToast } = useToast();
  const loginMutation = useLoginMutation();
  const logoutMutation = useLogoutMutation();
  const changePasswordMutation = useChangeOwnPasswordMutation();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  // Signed out: the login screen is the product's one editorial moment —
  // the grid-paper canvas, the brand mark, and a single centered card.
  if (!session && !sessionLoading) {
    return (
      <main className="flex min-h-screen flex-col">
        <header className="border-b border-border bg-card/85 backdrop-blur-sm">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
            <Brand />
            <ModeToggle />
          </div>
        </header>
        <div className="flex flex-1 items-center justify-center px-4 py-16">
          <div className="w-full max-w-sm">
            <p className="eyebrow">Enterprise AI Invoice Processing</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight">Reviewer Cockpit</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Upload invoices, review AI-extracted data, and keep every decision audited.
            </p>
            {toast ? (
              <div className="mt-4">
                <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />
              </div>
            ) : null}
            <Card className="mt-6 shadow-sm">
              <CardContent className="p-6">
                <SignInForm
                  busy={loginMutation.isPending}
                  onSubmit={(credentials) => loginMutation.mutate(credentials)}
                />
              </CardContent>
            </Card>
            <div className="mt-4">
              <StatusPill label="API" tone={health === "ok" ? "good" : health === "error" ? "crit" : "blueprint"} />
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <AssistantProvider>
    <main className="min-h-screen">
      <CommandPalette onOpenChange={setCommandPaletteOpen} open={commandPaletteOpen} />
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        href="#main-content"
      >
        Skip to main content
      </a>
      <header className="sticky top-0 z-20 border-b border-border bg-card/85 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <Brand />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              className="text-muted-foreground"
              onClick={() => setCommandPaletteOpen(true)}
              size="sm"
              type="button"
              variant="outline"
            >
              <Search className="h-4 w-4" />
              <span className="hidden sm:inline">Search</span>
              <kbd className="ml-1 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px]">⌘K</kbd>
            </Button>
            <StatusPill label="API" tone={health === "ok" ? "good" : health === "error" ? "crit" : "blueprint"} />
            {session ? (
              <span
                className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground"
                title={liveUpdatesConnected ? "Live updates connected" : "Live updates unavailable — reconnecting"}
              >
                <span
                  className={`h-2 w-2 rounded-full ${liveUpdatesConnected ? "bg-good" : "bg-muted-foreground/40"}`}
                  aria-hidden="true"
                />
                live
              </span>
            ) : null}
            <ModeToggle />
            {session ? (
              <>
                <span className="session-chip hidden rounded-full border border-border px-3 py-1.5 font-mono text-[11px] text-muted-foreground md:inline">
                  {session.email} · {session.role}
                </span>
                <Button onClick={() => logoutMutation.mutate()} size="sm" type="button" variant="outline">
                  <LogOut className="h-4 w-4" />
                  <span className="hidden sm:inline">Sign out</span>
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[260px_1fr]">
        <Card className="h-max min-w-0 shadow-sm">
          <CardContent className="p-3">
            <p className="eyebrow px-3 pb-2 pt-1.5">Workspace</p>
            <nav className="space-y-0.5 text-sm" aria-label="Primary">
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
                    <span className="flex items-center gap-2.5">
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {tab.label}
                    </span>
                    {locked ? (
                      <Lock className="nav-lock h-3.5 w-3.5" aria-label="Access restricted" />
                    ) : (
                      <span className="text-muted-foreground/60" aria-hidden="true">
                        ›
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            {session ? (
              <form
                className="mt-4 space-y-3 border-t border-border px-3 pb-1.5 pt-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  const formElement = event.currentTarget;
                  const form = new FormData(formElement);
                  changePasswordMutation.mutate(
                    {
                      session,
                      currentPassword: String(form.get("current_password") || ""),
                      newPassword: String(form.get("new_password") || ""),
                    },
                    { onSuccess: () => formElement.reset() },
                  );
                }}
              >
                <p className="eyebrow">Account</p>
                <Field label="Current password" name="current_password" type="password" required />
                <Field label="New password" name="new_password" type="password" minLength={12} required />
                <Button className="w-full" disabled={changePasswordMutation.isPending} type="submit" variant="outline">
                  {changePasswordMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <KeyRound className="h-4 w-4" />
                  )}
                  Change password
                </Button>
              </form>
            ) : null}
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-6" id="main-content">
          {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} /> : null}
          <Outlet />
        </div>
      </section>

      {/* Global assistant: reachable from every screen via the corner launcher,
          not buried in one panel. */}
      {session ? <AssistantWidget session={session} /> : null}
    </main>
    </AssistantProvider>
  );
}
