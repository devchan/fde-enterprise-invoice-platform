import {
  KeyRound,
  Lock,
  Loader2,
  LogOut,
} from "lucide-react";
import { tabs } from "./app/navigation";
import { useCockpitController } from "./app/useCockpitController";
import { AccessRequiredPanel, SignInRequiredPanel } from "./components/common/AccessPanels";
import { Field } from "./components/common/Field";
import { StatusPill } from "./components/common/StatusPill";
import { Toast } from "./components/common/Toast";
import { canAccessTab } from "./domain/authorization";
import { AuditPanel } from "./features/audit/AuditPanel";
import { SignInForm } from "./features/auth/SignInForm";
import { OverviewPanel } from "./features/dashboard/OverviewPanel";
import { ReviewPanel } from "./features/invoices/ReviewPanel";
import { UploadPanel } from "./features/invoices/UploadPanel";
import { FailedJobsPanel } from "./features/jobs/FailedJobsPanel";
import { UsersPanel } from "./features/users/UsersPanel";

export function App() {
  const {
    activeTab,
    auditLogs,
    busy,
    dashboardStats,
    defaultProvider,
    extractionProviders,
    failedJobs,
    health,
    initializing,
    invoices,
    selectedInvoice,
    session,
    toast,
    userCanReview,
    userCanUpload,
    userIsAdmin,
    users,
    actions,
  } = useCockpitController();

  // All app state and side effects live in the controller hook; this component is
  // purely presentational. Each tab below applies the same gate cascade:
  // signed in? -> has the required role? -> render panel, else a sign-in/access notice.
  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">FDE Invoice Platform</p>
            <h1 className="text-2xl font-semibold tracking-normal">Reviewer Cockpit</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label="API" tone={health === "ok" ? "ok" : health === "error" ? "error" : "info"} />
            {session ? (
              <>
                <span className="session-chip rounded border border-border px-3 py-2 text-sm text-muted-foreground">
                  {session.email} · {session.role}
                </span>
                <button className="btn-secondary" onClick={actions.logout} type="button">
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[280px_1fr]">
        <aside className="h-max min-w-0 rounded border border-border bg-white p-4">
          <nav className="space-y-1 text-sm" aria-label="Primary">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const locked = !canAccessTab(session, tab.key);
              return (
                <button
                  className={`nav-button ${activeTab === tab.key ? "nav-button-active" : ""}`}
                  key={tab.key}
                  onClick={() => actions.setActiveTab(tab.key)}
                  type="button"
                  aria-current={activeTab === tab.key ? "page" : undefined}
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
                </button>
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
              <button className="btn-secondary w-full" disabled={busy === "own-password"} type="submit">
                {busy === "own-password" ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                Change password
              </button>
            </form>
          )}
        </aside>

        <div className="min-w-0 space-y-6">
          {toast ? <Toast message={toast.message} tone={toast.tone} onClose={() => actions.setToast(null)} /> : null}
          {activeTab === "overview" ? (
            <OverviewPanel
              loading={initializing}
              signedIn={Boolean(session)}
              stats={dashboardStats}
              refresh={() => actions.refreshAll()}
              checkHealth={actions.checkHealth}
            />
          ) : null}
          {activeTab === "upload" ? (
            session ? (
              userCanUpload ? (
                <UploadPanel
                  busy={busy === "upload"}
                  onSubmit={actions.uploadInvoice}
                  providers={extractionProviders}
                  defaultProvider={defaultProvider}
                />
              ) : (
                <AccessRequiredPanel title="Upload requires admin or uploader access." />
              )
            ) : (
              <SignInRequiredPanel title="Sign in to upload invoices." />
            )
          ) : null}
          {activeTab === "review" ? (
            session ? (
              userCanReview ? (
                <ReviewPanel
                  busy={busy}
                  invoices={invoices}
                  onOpenFile={actions.openFile}
                  onRefresh={() => actions.loadInvoices()}
                  onReview={actions.reviewInvoice}
                  onSelect={actions.loadInvoice}
                  selectedInvoice={selectedInvoice}
                />
              ) : (
                <AccessRequiredPanel title="Review requires admin or reviewer access." />
              )
            ) : (
              <SignInRequiredPanel title="Sign in to review invoices." />
            )
          ) : null}
          {activeTab === "failed" ? (
            session ? (
              <FailedJobsPanel
                busy={busy}
                canReprocess={userCanReview}
                jobs={failedJobs}
                onRefresh={() => actions.loadFailedJobs()}
                onReprocess={actions.reprocessJob}
              />
            ) : (
              <SignInRequiredPanel title="Sign in to manage failed jobs." />
            )
          ) : null}
          {activeTab === "audit" ? (
            session ? (
              <AuditPanel
                logs={auditLogs}
                busy={busy === "audit"}
                onFilter={actions.filterAuditLogs}
                onRefresh={() => actions.loadAuditLogs()}
              />
            ) : (
              <SignInRequiredPanel title="Sign in to view audit logs." />
            )
          ) : null}
          {activeTab === "users" ? (
            session ? (
              userIsAdmin ? (
                <UsersPanel
                  busy={busy}
                  onCreate={actions.createUser}
                  onRefresh={() => actions.loadUsers()}
                  onResetPassword={actions.resetUserPassword}
                  onUpdate={actions.updateUser}
                  users={users}
                />
              ) : (
                <AccessRequiredPanel title="User administration requires admin access." />
              )
            ) : (
              <SignInRequiredPanel title="Sign in to administer users." />
            )
          ) : null}
        </div>
      </section>
    </main>
  );
}
