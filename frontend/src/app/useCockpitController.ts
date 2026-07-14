import { useNavigate } from "@tanstack/react-router";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { API_BASE_URL } from "../config";
import { canReview, canUpload, isAdmin } from "../domain/authorization";
import type { AuditLog, ExtractionProvider, InvoiceDetail, InvoiceFile, ProcessingJob, Session, UserRecord } from "../domain/types";
import { SessionExpiredError } from "../services/api-client";
import { auditLogService, authService, invoiceService, processingJobService, userService } from "../services";
import { SessionStore } from "../services/session-store";
import { emptyToUndefined, errorMessage } from "../utils/form";

export type LoginCredentials = {
  email: string;
  password: string;
};

export function useCockpitController() {
  // Start unauthenticated; the httpOnly cookie is the source of truth and is
  // validated on mount via /auth/me (the JS-readable token no longer exists).
  const navigate = useNavigate();
  const [session, setSession] = useState<Session | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "ok" | "error" | "info" } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [health, setHealth] = useState<"unknown" | "ok" | "error">("unknown");
  const [invoices, setInvoices] = useState<InvoiceDetail[]>([]);
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceDetail | null>(null);
  const [failedJobs, setFailedJobs] = useState<ProcessingJob[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [users, setUsers] = useState<UserRecord[]>([]);
  // Extraction provider options for the upload form (with availability flags).
  const [extractionProviders, setExtractionProviders] = useState<ExtractionProvider[]>([]);
  const [defaultProvider, setDefaultProvider] = useState<string | null>(null);

  const userIsAdmin = isAdmin(session);
  const userCanReview = canReview(session);
  const userCanUpload = canUpload(session);

  useEffect(() => {
    checkHealth();
    void rehydrateSession();
  }, []);

  async function rehydrateSession() {
    try {
      const context = await authService.me();
      setSession(context);
    } catch {
      // No valid cookie session; drop any stale cached identity.
      SessionStore.clear();
    }
  }

  // React to identity changes: cache identity + load data on sign-in, purge on sign-out.
  useEffect(() => {
    if (session) {
      SessionStore.write(session);
      void refreshAll(session);
    } else {
      SessionStore.clear();
    }
  }, [session]);

  // Depends on the full `invoices` array (not just length) because status counts change without length changing.
  const dashboardStats = useMemo(
    () => [
      { label: "Loaded invoices", value: invoices.length.toString() },
      { label: "Review required", value: invoices.filter((invoice) => invoice.status === "review_required").length.toString() },
      { label: "Failed jobs", value: failedJobs.length.toString() },
      { label: "Audit events", value: auditLogs.length.toString() },
    ],
    [auditLogs.length, failedJobs.length, invoices],
  );

  // Wraps every authenticated call so a SessionExpiredError uniformly tears down the session.
  async function withSessionHandling<T>(request: () => Promise<T>): Promise<T> {
    try {
      return await request();
    } catch (error) {
      if (error instanceof SessionExpiredError) {
        clearSession("Your session expired. Sign in again to continue.", "error");
      }
      throw error;
    }
  }

  async function checkHealth() {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      setHealth(response.ok ? "ok" : "error");
    } catch {
      setHealth("error");
    }
  }

  async function refreshAll(activeSession = session) {
    if (!activeSession) return;
    setInitializing(true);
    try {
      // Invoices are the primary view, so load them first; the rest fan out in
      // parallel with allSettled so one endpoint failing does not block the others.
      await loadInvoices(activeSession);
      await Promise.allSettled([
        loadFailedJobs(activeSession),
        loadAuditLogs(activeSession),
        loadExtractionProviders(activeSession),
        activeSession.role === "admin" ? loadUsers(activeSession) : Promise.resolve(),
      ]);
    } catch (error) {
      if (!(error instanceof SessionExpiredError)) {
        setToast({ message: errorMessage(error), tone: "error" });
      }
    } finally {
      setInitializing(false);
    }
  }

  async function loadExtractionProviders(activeSession = session) {
    if (!activeSession) return;
    // Non-fatal: if this fails the upload form simply falls back to no selector.
    const response = await withSessionHandling(() => invoiceService.getProviders(activeSession));
    setExtractionProviders(response.providers);
    setDefaultProvider(response.default);
  }

  async function login(credentials: LoginCredentials) {
    setBusy("login");
    try {
      const nextSession = await withSessionHandling(() =>
        authService.login(
          credentials.email.trim(),
          credentials.password,
        ),
      );
      void navigate({ to: "/" });
      setSession(nextSession);
      setToast({ message: `Signed in as ${nextSession.email}`, tone: "ok" });
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  function logout() {
    // Revoke server-side (best-effort) so the tokens cannot be replayed.
    void authService.logout().catch(() => undefined);
    clearSession("Signed out.", "info");
  }

  function clearSession(message: string, tone: "ok" | "error" | "info") {
    setSession(null);
    setInvoices([]);
    setFailedJobs([]);
    setAuditLogs([]);
    setUsers([]);
    setSelectedInvoice(null);
    setBusy(null);
    setInitializing(false);
    void navigate({ to: "/" });
    setToast({ message, tone });
  }

  async function loadInvoices(activeSession = session) {
    if (!activeSession) return;
    const data = await withSessionHandling(() => invoiceService.list(activeSession));
    setInvoices(data);
    if (selectedInvoice) {
      const refreshed = data.find((invoice) => invoice.invoice_id === selectedInvoice.invoice_id);
      if (refreshed) setSelectedInvoice(refreshed);
    }
  }

  async function loadInvoice(invoiceId: string) {
    setBusy(`invoice:${invoiceId}`);
    try {
      if (!session) return;
      const detail = await withSessionHandling(() => invoiceService.get(session, invoiceId));
      setSelectedInvoice(detail);
      void navigate({ to: "/review" });
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function uploadInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!userCanUpload) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    // Drop blank optional fields so the backend sees them as absent rather than empty strings.
    for (const key of ["supplier_id", "total_amount"]) {
      if (!String(form.get(key) || "").trim()) form.delete(key);
    }
    setBusy("upload");
    try {
      if (!session) return;
      const result = await withSessionHandling(() => invoiceService.upload(session, form));
      setToast({ message: `Uploaded ${result.invoice_number}.`, tone: "ok" });
      formElement.reset();
      await loadInvoices();
      await loadInvoice(result.invoice_id);
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function reviewInvoice(decision: "approve" | "reject", event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedInvoice || !userCanReview) return;
    const form = new FormData(event.currentTarget);
    setBusy(`review:${decision}`);
    try {
      // Only send fields the reviewer actually changed; blanks collapse to undefined and are omitted.
      const correctedFields = {
        invoice_number: emptyToUndefined(form.get("invoice_number")),
        invoice_date: emptyToUndefined(form.get("invoice_date")),
        total_amount: emptyToUndefined(form.get("total_amount")),
        currency: emptyToUndefined(form.get("currency")),
      };
      if (!session) return;
      const detail = await withSessionHandling(() =>
        invoiceService.review(session, selectedInvoice.invoice_id, {
          decision,
          notes: String(form.get("notes") || ""),
          corrected_fields: correctedFields,
          expected_updated_at: selectedInvoice.updated_at,
        }),
      );
      setSelectedInvoice(detail);
      setToast({ message: `Invoice ${decision === "approve" ? "approved" : "rejected"}.`, tone: "ok" });
      await loadInvoices();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function openFile(file: InvoiceFile) {
    if (!selectedInvoice) return;
    setBusy(`file:${file.file_id}`);
    try {
      if (!session) return;
      const downloadUrl = await withSessionHandling(() => invoiceService.createDownloadUrl(session, selectedInvoice.invoice_id, file));
      window.open(downloadUrl, "_blank", "noopener,noreferrer");
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function loadFailedJobs(activeSession = session) {
    if (!activeSession) return;
    const jobs = await withSessionHandling(() => processingJobService.listFailed(activeSession));
    setFailedJobs(jobs);
  }

  async function reprocessJob(job: ProcessingJob) {
    setBusy(`job:${job.processing_job_id}`);
    try {
      if (!session) return;
      await withSessionHandling(() => processingJobService.reprocess(session, job));
      setToast({ message: "Job requeued.", tone: "ok" });
      await loadFailedJobs();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function loadAuditLogs(activeSession = session) {
    if (!activeSession) return;
    const logs = await withSessionHandling(() => auditLogService.list(activeSession));
    setAuditLogs(logs);
  }

  async function filterAuditLogs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    // Build the query from only the filled filter inputs; omitted keys mean "no filter".
    const params = new URLSearchParams({ limit: "50" });
    for (const key of ["entity_type", "entity_id", "action"]) {
      const value = String(form.get(key) || "").trim();
      if (value) params.set(key, value);
    }
    setBusy("audit");
    try {
      if (!session) return;
      const logs = await withSessionHandling(() => auditLogService.list(session, params));
      setAuditLogs(logs);
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function loadUsers(activeSession = session) {
    if (!activeSession || activeSession.role !== "admin") return;
    const data = await withSessionHandling(() => userService.list(activeSession));
    setUsers(data);
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy("create-user");
    try {
      if (!session) return;
      await withSessionHandling(() =>
        userService.create(session, {
          email: String(form.get("email") || "").trim(),
          role: String(form.get("role") || "reviewer"),
          password: String(form.get("password") || ""),
        }),
      );
      setToast({ message: "User created.", tone: "ok" });
      formElement.reset();
      await loadUsers();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function updateUser(user: UserRecord, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(`user:update:${user.user_id}`);
    try {
      if (!session) return;
      const updated = await withSessionHandling(() =>
        userService.update(session, user, {
          email: String(form.get("email") || "").trim(),
          role: String(form.get("role") || user.role),
        }),
      );
      // If admins edit their own record, mirror the change into the live session immediately.
      if (session?.user_id === updated.user_id) {
        setSession({ ...session, email: updated.email, role: updated.role });
      }
      setToast({ message: "User updated.", tone: "ok" });
      await loadUsers();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function resetUserPassword(user: UserRecord, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(`user:password:${user.user_id}`);
    try {
      if (!session) return;
      await withSessionHandling(() => userService.resetPassword(session, user, String(form.get("password") || "")));
      setToast({ message: "Password reset.", tone: "ok" });
      formElement.reset();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  async function changeOwnPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy("own-password");
    try {
      if (!session) return;
      await withSessionHandling(() =>
        authService.changeOwnPassword(
          session,
          String(form.get("current_password") || ""),
          String(form.get("new_password") || ""),
        ),
      );
      setToast({ message: "Password changed.", tone: "ok" });
      formElement.reset();
      await loadAuditLogs();
    } catch (error) {
      setToast({ message: errorMessage(error), tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  return {
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
    actions: {
      changeOwnPassword,
      checkHealth,
      createUser,
      filterAuditLogs,
      loadAuditLogs,
      loadFailedJobs,
      loadInvoice,
      loadInvoices,
      loadUsers,
      login,
      logout,
      openFile,
      refreshAll,
      reprocessJob,
      resetUserPassword,
      reviewInvoice,
      setToast,
      updateUser,
      uploadInvoice,
    },
  };
}
