import { AlertCircle, ClipboardCheck, FileUp, History, ListChecks, Users } from "lucide-react";
import type { TabKey } from "../domain/types";

export const tabs: Array<{ key: TabKey; label: string; icon: typeof ClipboardCheck }> = [
  { key: "overview", label: "Overview", icon: ClipboardCheck },
  { key: "upload", label: "Upload", icon: FileUp },
  { key: "review", label: "Review Queue", icon: ListChecks },
  { key: "failed", label: "Failed Jobs", icon: AlertCircle },
  { key: "audit", label: "Audit Logs", icon: History },
  { key: "users", label: "Users", icon: Users },
];
