import type { FormEvent } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { KeyRound, Loader2, Save, UserPlus } from "lucide-react";
import { DataTable } from "../../components/common/DataTable";
import { Field } from "../../components/common/Field";
import { PanelHeader } from "../../components/common/PanelHeader";
import { StatusPill } from "../../components/common/StatusPill";
import type { UserRecord } from "../../domain/types";
import { shortId } from "../../utils/format";

export function UsersPanel({
  busy,
  users,
  onCreate,
  onRefresh,
  onResetPassword,
  onUpdate,
}: {
  busy: string | null;
  users: UserRecord[];
  onCreate: (event: FormEvent<HTMLFormElement>) => void;
  onRefresh: () => void;
  onResetPassword: (user: UserRecord, event: FormEvent<HTMLFormElement>) => void;
  onUpdate: (user: UserRecord, event: FormEvent<HTMLFormElement>) => void;
}) {
  const columns: ColumnDef<UserRecord>[] = [
    {
      accessorKey: "email",
      header: "Email",
      cell: ({ row }) => <span className="font-medium">{row.original.email}</span>,
    },
    {
      accessorKey: "role",
      header: "Role",
      cell: ({ row }) => <StatusPill label={row.original.role} tone="info" />,
    },
    {
      accessorKey: "user_id",
      header: "User ID",
      cell: ({ row }) => <span className="text-muted-foreground">{shortId(row.original.user_id)}</span>,
    },
  ];

  return (
    <section className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <div className="panel">
        <PanelHeader title="Users" onRefresh={onRefresh} />
        <div className="mt-4">
          <DataTable columns={columns} data={users} emptyMessage="No users found." />
        </div>
        <div className="mt-4 space-y-3">
          {users.map((user) => (
            <UserManagementRow
              busy={busy}
              key={user.user_id}
              onResetPassword={onResetPassword}
              onUpdate={onUpdate}
              user={user}
            />
          ))}
        </div>
      </div>
      <form className="panel space-y-3" onSubmit={onCreate}>
        <h2 className="text-lg font-semibold">Create user</h2>
        <Field label="Email" name="email" type="email" required />
        <label className="field">
          <span>Role</span>
          <select name="role" defaultValue="reviewer">
            <option value="admin">admin</option>
            <option value="reviewer">reviewer</option>
            <option value="uploader">uploader</option>
          </select>
        </label>
        <Field label="Temporary password" name="password" type="password" minLength={12} required />
        <button className="btn-primary" disabled={busy === "create-user"} type="submit">
          {busy === "create-user" ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
          Create user
        </button>
      </form>
    </section>
  );
}

// Per-user row with two independent forms (edit details, reset password); busy keys are
// scoped by user_id so a spinner only shows on the row/action actually in flight.
function UserManagementRow({
  busy,
  onResetPassword,
  onUpdate,
  user,
}: {
  busy: string | null;
  onResetPassword: (user: UserRecord, event: FormEvent<HTMLFormElement>) => void;
  onUpdate: (user: UserRecord, event: FormEvent<HTMLFormElement>) => void;
  user: UserRecord;
}) {
  const updating = busy === `user:update:${user.user_id}`;
  const resetting = busy === `user:password:${user.user_id}`;

  return (
    <article className="user-card">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-medium">{user.email}</p>
          <p className="text-xs text-muted-foreground">{shortId(user.user_id)}</p>
        </div>
        <StatusPill label={user.role} tone="info" />
      </div>

      <div className="mt-4 grid gap-4">
        <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" onSubmit={(event) => onUpdate(user, event)}>
          <label className="field sm:col-span-2">
            <span>Email</span>
            <input name="email" type="email" defaultValue={user.email} required />
          </label>
          <label className="field">
            <span>Role</span>
            <select name="role" defaultValue={user.role}>
              <option value="admin">admin</option>
              <option value="reviewer">reviewer</option>
              <option value="uploader">uploader</option>
            </select>
          </label>
          <button className="btn-secondary self-end" disabled={updating} type="submit">
            {updating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </button>
        </form>

        <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={(event) => onResetPassword(user, event)}>
          <Field label="New password" name="password" type="password" minLength={12} required />
          <button className="btn-secondary" disabled={resetting} type="submit">
            {resetting ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
            Reset password
          </button>
        </form>
      </div>
    </article>
  );
}
