import { useState } from "react";
import type { FormEvent } from "react";

import { createUser } from "../../services/api";
import type { User, UserRole } from "../../types/api";

type UserCreateFormProps = {
  token: string;
  onCreated: (user: User) => void;
};

const initialForm = {
  name: "",
  email: "",
  password: "",
  role: "agent" as UserRole,
};

export function UserCreateForm({ token, onCreated }: UserCreateFormProps) {
  const [form, setForm] = useState(initialForm);
  const [isOpen, setIsOpen] = useState(false);
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
      setIsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="user-create-section">
      <div className="section-heading">
        <div>
          <h2>Create account</h2>
          <p>Add a Supervisor, Agent, or Admin account to OpenCI.</p>
        </div>
        <button
          type="button"
          className="secondary-button toolbar-button"
          onClick={() => {
            setIsOpen((current) => !current);
            setError("");
          }}
        >
          {isOpen ? "Cancel" : "New account"}
        </button>
      </div>

      {isOpen && (
        <form className="create-form user-create-form" onSubmit={handleSubmit}>
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
                minLength={8}
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

          <button className="primary-button compact-button" disabled={isSaving}>
            {isSaving ? "Creating account..." : "Create account"}
          </button>
        </form>
      )}
    </div>
  );
}
