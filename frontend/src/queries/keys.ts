// Centralized query-key factory, scoped by organization_id so a sign-out/sign-in-as-
// different-org can never surface another tenant's cached data.
export const sessionKeys = {
  me: () => ["session"] as const,
};

export const invoiceKeys = {
  list: (orgId: string) => ["invoices", orgId, "list"] as const,
  detail: (orgId: string, invoiceId: string) => ["invoices", orgId, "detail", invoiceId] as const,
  similar: (orgId: string, invoiceId: string) => ["invoices", orgId, "similar", invoiceId] as const,
  providers: (orgId: string) => ["invoices", orgId, "providers"] as const,
};

export const jobKeys = {
  failed: (orgId: string) => ["jobs", orgId, "failed"] as const,
};

export const auditKeys = {
  list: (orgId: string, params: string) => ["audit-logs", orgId, params] as const,
  all: (orgId: string) => ["audit-logs", orgId] as const,
};

export const userKeys = {
  list: (orgId: string) => ["users", orgId] as const,
};
