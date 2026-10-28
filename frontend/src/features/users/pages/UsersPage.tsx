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
import { Button, InlineAlert, Skeleton } from "@/components/ui/Primitives";
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
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {resource.loading ? (
          <Skeleton />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Account status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {resource.data?.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.email}</td>
                    <td className="capitalize">{item.role}</td>
                    <td>
                      <span
                        className={`status-badge account-${item.is_active ? "active" : "inactive"}`}
                      >
                        {item.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
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
                              updateUserActivation(
                                token,
                                item.id,
                                !item.is_active,
                              ),
                            )
                          }
                        >
                          {item.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </RowActions>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
