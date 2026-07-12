import type { FormEvent } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { FileSearch } from "lucide-react";
import { DataTable } from "../../components/common/DataTable";
import { Field } from "../../components/common/Field";
import { PanelHeader } from "../../components/common/PanelHeader";
import type { AuditLog } from "../../domain/types";
import { formatDate, shortId } from "../../utils/format";

const auditColumns: ColumnDef<AuditLog>[] = [
  {
    accessorKey: "action",
    header: "Action",
    cell: ({ row }) => <span className="font-medium">{row.original.action}</span>,
  },
  {
    accessorKey: "entity_type",
    header: "Entity",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {row.original.entity_type} · {shortId(row.original.entity_id)}
      </span>
    ),
  },
  {
    accessorKey: "actor_user_id",
    header: "Actor",
    cell: ({ row }) => <span className="text-muted-foreground">{shortId(row.original.actor_user_id)}</span>,
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <span className="text-muted-foreground">{formatDate(row.original.created_at)}</span>,
  },
];

export function AuditPanel({
  busy,
  logs,
  onFilter,
  onRefresh,
}: {
  busy: boolean;
  logs: AuditLog[];
  onFilter: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="panel">
      <PanelHeader title="Audit Logs" onRefresh={onRefresh} />
      <form className="mt-4 grid gap-3 md:grid-cols-4" onSubmit={onFilter}>
        <Field label="Entity type" name="entity_type" placeholder="invoice" />
        <Field label="Entity ID" name="entity_id" placeholder="UUID" />
        <Field label="Action" name="action" placeholder="invoice.uploaded" />
        <button className="btn-primary self-end" disabled={busy} type="submit">
          <FileSearch className="h-4 w-4" />
          Filter
        </button>
      </form>
      <div className="mt-4">
        <DataTable columns={auditColumns} data={logs} emptyMessage="No audit logs found." />
      </div>
    </section>
  );
}
