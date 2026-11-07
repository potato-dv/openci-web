import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import {
  getUsers,
  updateUserActivation,
  updateUserRole,
} from "@/features/users/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { UserCreateForm } from "@/features/users/components/UserCreateForm";
import { RowActions } from "@/components/ui/RowActions";
import { Modal } from "@/components/ui/Modal";
import { Button, EmptyState, InlineAlert, Skeleton } from "@/components/ui/Primitives";
import type { User, UserRole } from "@/types/api";
export function UsersPage() {
  const { token, user } = useSession();
  const [params, setParams] = useSearchParams();
  const resource = useResource(useCallback(() => getUsers(token), [token]));
  const [create, setCreate] = useState(params.has("new"));
  const [editing, setEditing] = useState<User | null>(null);
  const [role, setRole] = useState<UserRole>("agent");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function mutate(action: () => Promise<User>) {
    setBusy(true);
    setError("");
    try {
      await action();
      setEditing(null);
      resource.refresh();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not update this account.",
      );
    } finally {
      setBusy(false);
    }
  }
  function accountActions(item: User) {
    return (
      <RowActions label={item.name}>
        <button
          type="button"
          role="menuitem"
          disabled={busy}
          onClick={() => {
            setEditing(item);
            setRole(item.role);
            setError("");
          }}
        >
          Edit role
        </button>
        <button
          type="button"
          role="menuitem"
          disabled={busy || item.id === user.id}
          onClick={() =>
            void mutate(() =>
              updateUserActivation(token, item.id, !item.is_active),
            )
          }
        >
          {item.is_active ? "Deactivate" : "Activate"}
        </button>
      </RowActions>
    );
  }
  return (
    <>
      <PageHeader
        title="User Management"
        description="Manage account access and roles."
        actions={
          <Button variant="primary" onClick={() => setCreate(true)}>
            New account
          </Button>
        }
      />
      {error && !editing && <InlineAlert>{error}</InlineAlert>}
      <section className="content-card">
        <div className="section-title">
          <h2>Accounts</h2>
          {resource.data && <span className="text-xs text-openci-text-muted">{resource.data.length} total</span>}
        </div>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {resource.loading ? (
          <Skeleton />
        ) : resource.data?.length ? (
          <>
          <div className="table-wrap desktop-data">
            <Table className="min-w-[680px] table-fixed">
              <colgroup>
                <col className="w-[24%]" />
                <col className="w-[35%]" />
                <col className="w-[16%]" />
                <col className="w-[17%]" />
                <col className="w-[8%]" />
              </colgroup>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Name</TableHead>
                  <TableHead scope="col">Email</TableHead>
                  <TableHead scope="col">Role</TableHead>
                  <TableHead scope="col">Account status</TableHead>
                  <TableHead scope="col" className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data?.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.name}</TableCell>
                    <TableCell className="truncate text-openci-text-muted" title={item.email}>{item.email}</TableCell>
                    <TableCell className="capitalize">{item.role}</TableCell>
                    <TableCell>
                      <span
                        className={`status-badge account-${item.is_active ? "active" : "inactive"}`}
                      >
                        {item.is_active ? "Active" : "Inactive"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">{accountActions(item)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <ul className="workspace-mobile-list" aria-label="User accounts">
            {resource.data.map((item) => (
              <li key={item.id}>
                <div className="mobile-row-heading">
                  <strong>{item.name}</strong>
                  {accountActions(item)}
                </div>
                <span className="mobile-row-meta">{item.email}</span>
                <dl className="mobile-row-facts">
                  <div><dt>Role</dt><dd className="capitalize">{item.role}</dd></div>
                  <div><dt>Account</dt><dd><span className={`status-badge account-${item.is_active ? "active" : "inactive"}`}>{item.is_active ? "Active" : "Inactive"}</span></dd></div>
                </dl>
              </li>
            ))}
          </ul>
          </>
        ) : !resource.error ? (
          <EmptyState title="No accounts yet">Create an account to give your team access to Collector.</EmptyState>
        ) : null}
      </section>
      <UserCreateForm
        token={token}
        open={create}
        onClose={() => {
          setCreate(false);
          setParams({});
        }}
        onCreated={() => resource.refresh()}
      />
      <Modal
        open={Boolean(editing)}
        title="Edit account role"
        onClose={() => !busy && setEditing(null)}
      >
        <form
          className="modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (editing)
              void mutate(() => updateUserRole(token, editing.id, role));
          }}
        >
          <label>
            Role
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
            >
              <option value="admin">Admin</option>
              <option value="supervisor">Supervisor</option>
              <option value="agent">Agent</option>
            </select>
          </label>
          {error && <InlineAlert>{error}</InlineAlert>}
          <div className="modal-form-actions">
            <Button onClick={() => setEditing(null)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save role"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
