import { createRootRoute, Link, Outlet } from "@tanstack/react-router";
import { KeyRound, Lock, Loader2, LogOut, Search } from "lucide-react";
import { useState } from "react";
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

export const Route = createRootRoute({
  component: RootComponent,
});

function RootComponent() {
  useSessionExpiredHandler();
  const { health } = useHealth();
  const { session } = useSession();
  const { connected: liveUpdatesConnected } = useRealtimeEvents(session);
  const { toast, setToast } = useToast();
  const loginMutation = useLoginMutation();
  const logoutMutation = useLogoutMutation();
  const changePasswordMutation = useChangeOwnPasswordMutation();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  return (
    <main className="min-h-screen bg-background">
      <CommandPalette onOpenChange={setCommandPaletteOpen} open={commandPaletteOpen} />
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        href="#main-content"
      >
        Skip to main content
      </a>
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">FDE Invoice Platform</p>
            <h1 className="text-2xl font-semibold tracking-normal">Reviewer Cockpit</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              className="text-muted-foreground"
              onClick={() => setCommandPaletteOpen(true)}
              size="sm"
              type="button"
              variant="outline"
            >
              <Search className="h-4 w-4" />
              Search
              <kbd className="ml-2 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium">⌘K</kbd>
            </Button>
            <StatusPill label="API" tone={health === "ok" ? "ok" : health === "error" ? "error" : "info"} />
            {session ? (
              <span
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
                title={liveUpdatesConnected ? "Live updates connected" : "Live updates unavailable — reconnecting"}
              >
                <span
                  className={`h-2 w-2 rounded-full ${liveUpdatesConnected ? "bg-emerald-500" : "bg-muted-foreground/40"}`}
                  aria-hidden="true"
                />
                Live
              </span>
            ) : null}
            <ModeToggle />
            {session ? (
              <>
                <span className="session-chip rounded border border-border px-3 py-2 text-sm text-muted-foreground">
                  {session.email} · {session.role}
                </span>
                <Button onClick={() => logoutMutation.mutate()} type="button" variant="outline">
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
              <SignInForm busy={loginMutation.isPending} onSubmit={(credentials) => loginMutation.mutate(credentials)} />
            ) : (
              <form
                className="mt-5 space-y-3 border-t border-border pt-5"
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
                <h2 className="text-sm font-semibold">Account</h2>
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
            )}
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-6" id="main-content">
          {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} /> : null}
          <Outlet />
        </div>
      </section>
    </main>
  );
}
