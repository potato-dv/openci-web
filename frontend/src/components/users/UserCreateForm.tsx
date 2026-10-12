import { useState } from "react";
import type { FormEvent } from "react";

import { createUser } from "../../services/api";
import type { User, UserRole } from "../../types/api";
import { Modal } from "../ui/Modal";

type UserCreateFormProps = {
  token: string;
  open: boolean;
  onClose: () => void;
  onCreated: (user: User) => void;
};

const initialForm = {
  name: "",
  email: "",
  password: "",
  role: "agent" as UserRole,
};

export function UserCreateForm({ token, open, onClose, onCreated }: UserCreateFormProps) {
  const [form, setForm] = useState(initialForm);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError("");

    try {
      const user = await createUser(token, form);
      onCreated(user);
      setForm(initialForm);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Modal open={open} title="Create account" onClose={onClose}>
      <p className="modal-description">Add a Supervisor, Agent, or Admin account to Collector.</p>
      <form className="create-form modal-form user-create-form" onSubmit={handleSubmit}>
          <div className="user-form-grid">
            <label>
              Name
              <input
                value={form.name}
                onChange={(event) =>
                  setForm({ ...form, name: event.target.value })
                }
                placeholder="Full name"
                required
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={form.email}
                onChange={(event) =>
                  setForm({ ...form, email: event.target.value })
                }
                placeholder="name@example.com"
                required
              />
            </label>
            <label>
              Temporary password
              <input
                type="password"
                value={form.password}
                onChange={(event) =>
                  setForm({ ...form, password: event.target.value })
                }
                placeholder="Temporary password"
                minLength={12}
                required
              />
            </label>
            <label>
              Role
              <select
                value={form.role}
                onChange={(event) =>
                  setForm({ ...form, role: event.target.value as UserRole })
                }
              >
                <option value="agent">Agent</option>
                <option value="supervisor">Supervisor</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          </div>

          {error && <p className="error">{error}</p>}

        <div className="modal-form-actions">
          <button type="button" className="secondary-button toolbar-button" onClick={onClose} disabled={isSaving}>Cancel</button>
          <button className="primary-button toolbar-button" disabled={isSaving}>{isSaving ? "Creating account…" : "Create account"}</button>
        </div>
      </form>
    </Modal>
  );
}
