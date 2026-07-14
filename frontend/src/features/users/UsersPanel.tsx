import type { FormEvent } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { KeyRound, Loader2, Save, UserPlus } from "lucide-react";
import { DataTable } from "../../components/common/DataTable";
import { Field } from "../../components/common/Field";
import { PanelHeader } from "../../components/common/PanelHeader";
import { StatusPill } from "../../components/common/StatusPill";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { inputVariants } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
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
      <Card>
        <CardContent className="pt-6">
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
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Create user</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={onCreate}>
            <Field label="Email" name="email" type="email" required />
            <div className="grid gap-1.5">
              <Label htmlFor="new-user-role">Role</Label>
              <select className={inputVariants} defaultValue="reviewer" id="new-user-role" name="role">
                <option value="admin">admin</option>
                <option value="reviewer">reviewer</option>
                <option value="uploader">uploader</option>
              </select>
            </div>
            <Field label="Temporary password" name="password" type="password" minLength={12} required />
            <Button disabled={busy === "create-user"} type="submit">
              {busy === "create-user" ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
              Create user
            </Button>
          </form>
        </CardContent>
      </Card>
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
    <Card>
      <CardContent className="overflow-hidden pt-6">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-medium">{user.email}</p>
            <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{shortId(user.user_id)}</p>
          </div>
          <StatusPill label={user.role} tone="info" />
        </div>

        <div className="mt-4 grid gap-4">
          <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" onSubmit={(event) => onUpdate(user, event)}>
            <div className="grid gap-1.5 sm:col-span-2">
              <Label htmlFor={`email-${user.user_id}`}>Email</Label>
              <input
                className={inputVariants}
                defaultValue={user.email}
                id={`email-${user.user_id}`}
                name="email"
                required
                type="email"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`role-${user.user_id}`}>Role</Label>
              <select className={inputVariants} defaultValue={user.role} id={`role-${user.user_id}`} name="role">
                <option value="admin">admin</option>
                <option value="reviewer">reviewer</option>
                <option value="uploader">uploader</option>
              </select>
            </div>
            <Button className="self-end" disabled={updating} type="submit" variant="outline">
              {updating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save
            </Button>
          </form>

          <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={(event) => onResetPassword(user, event)}>
            <Field label="New password" name="password" type="password" minLength={12} required />
            <Button disabled={resetting} type="submit" variant="outline">
              {resetting ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              Reset password
            </Button>
          </form>
        </div>
      </CardContent>
    </Card>
  );
}
