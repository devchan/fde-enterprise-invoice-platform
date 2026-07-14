import { AlertCircle, ClipboardCheck, FileUp, History, ListChecks, Users } from "lucide-react";
import type { TabKey } from "../domain/types";

// Single source of truth for the sidebar: array order sets the display order.
// Per-tab RBAC gating lives in domain/authorization.ts (canAccessTab), not here.
export const tabs: Array<{ key: TabKey; label: string; icon: typeof ClipboardCheck; path: string }> = [
  { key: "overview", label: "Overview", icon: ClipboardCheck, path: "/" },
  { key: "upload", label: "Upload", icon: FileUp, path: "/upload" },
  { key: "review", label: "Review Queue", icon: ListChecks, path: "/review" },
  { key: "failed", label: "Failed Jobs", icon: AlertCircle, path: "/failed" },
  { key: "audit", label: "Audit Logs", icon: History, path: "/audit" },
  { key: "users", label: "Users", icon: Users, path: "/users" },
];
