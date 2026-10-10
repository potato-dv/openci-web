
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";

const API_URL = "http://localhost:8000";

type User = {
  id: number;
  name: string;
  email: string;
  role: string;
};

type Investigation = {
  id: number;
  reference_number: string;
  subject_name: string;
  status: string;
  priority: string;
  assigned_agent_id?: number | null;
};

type Page = "overview" | "users" | "investigations";

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [user, setUser] = useState<User | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const [newInvestigation, setNewInvestigation] = useState({
  reference_number: "",
  subject_name: "",
  address: "",
  priority: "normal",
});
  const [accessToken, setAccessToken] = useState("");
  const [activePage, setActivePage] = useState<Page>("overview");

  const [users, setUsers] = useState<User[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState("");

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Login failed");
      }

      const token: string = data.access_token;

      const profileResponse = await fetch(`${API_URL}/users/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      const profile = await profileResponse.json();

      if (!profileResponse.ok) {
        throw new Error(profile.detail || "Could not load profile");
      }

      sessionStorage.setItem("access_token", token);
      setAccessToken(token);
      setUser(profile);
      setActivePage("overview");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to connect to the server.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!user || !accessToken) return;

    let cancelled = false;

    async function loadDashboardData() {
      setDataLoading(true);
      setDataError("");

      const headers = {
        Authorization: `Bearer ${accessToken}`,
      };

      try {
        const response = await fetch(
          `${API_URL}/investigations/`,
          { headers },
        );

        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            data.detail || "Could not load investigations",
          );
        }

        if (!Array.isArray(data)) {
          throw new Error("Unexpected investigations response");
        }

        if (!cancelled) {
          setInvestigations(data);
        }

        if (user.role === "admin") {
          const usersResponse = await fetch(`${API_URL}/users/`, {
            headers,
          });

          const usersData = await usersResponse.json();

          if (!usersResponse.ok) {
            throw new Error(usersData.detail || "Could not load users");
          }

          if (!cancelled) {
            setUsers(usersData);
          }
        } else if (!cancelled) {
          setUsers([]);
        }
      } catch (err) {
        if (!cancelled) {
          setDataError(
            err instanceof Error
              ? err.message
              : "Could not load dashboard data.",
          );
        }
      } finally {
        if (!cancelled) {
          setDataLoading(false);
        }
      }
    }

    void loadDashboardData();

    return () => {
      cancelled = true;
    };
  }, [user, accessToken]);

  async function handleCreateInvestigation(
  event: FormEvent<HTMLFormElement>,
) {
  event.preventDefault();
  setCreating(true);
  setCreateError("");

  try {
    const response = await fetch(`${API_URL}/investigations/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        ...newInvestigation,
        status: "pending",
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Failed to create investigation");
    }

    setInvestigations((current) => [data, ...current]);

    setNewInvestigation({
      reference_number: "",
      subject_name: "",
      address: "",
      priority: "normal",
    });

    setShowCreateForm(false);
  } catch (err) {
    setCreateError(
      err instanceof Error
        ? err.message
        : "Unable to create investigation",
    );
  } finally {
    setCreating(false);
  }
}

  function handleLogout() {
    sessionStorage.removeItem("access_token");
    setAccessToken("");
    setUser(null);
    setPassword("");
    setUsers([]);
    setInvestigations([]);
    setActivePage("overview");
  }

  if (!user) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="brand-mark">OC</div>
          <p className="eyebrow">OPENCI OPERATIONS</p>
          <h1>Welcome back</h1>
          <p className="muted">
            Sign in to manage operations and investigations.
          </p>

          <form onSubmit={handleLogin}>
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />

            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />

            {error && <p className="error">{error}</p>}

            <button className="primary-button" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="footer-note">Operations Management System</p>
        </section>
      </main>
    );
  }

  const pendingCount = investigations.filter(
    (item) => item.status.toLowerCase() === "pending",
  ).length;

  const assignedCount = investigations.filter(
    (item) => item.assigned_agent_id != null,
  ).length;

  const pageTitle = {
    overview: "Dashboard",
    users: "User Management",
    investigations: "Investigations",
  }[activePage];

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">OC</div>
          <div>
            <strong>OpenCI</strong>
            <span>Operations</span>
          </div>
        </div>

        <p className="nav-label">WORKSPACE</p>

        <button
          className={`nav-item ${activePage === "overview" ? "active" : ""}`}
          onClick={() => setActivePage("overview")}
        >
          Overview
        </button>

        <button
          className={`nav-item ${activePage === "investigations" ? "active" : ""}`}
          onClick={() => setActivePage("investigations")}
        >
          Investigations
        </button>

        {user.role === "admin" && (
          <>
            <p className="nav-label">ADMINISTRATION</p>
            <button
              className={`nav-item ${activePage === "users" ? "active" : ""}`}
              onClick={() => setActivePage("users")}
            >
              User Management
            </button>
          </>
        )}

        <div className="sidebar-user">
          <div className="avatar">
            {user.name.charAt(0).toUpperCase()}
          </div>
          <div className="sidebar-user-info">
            <strong>{user.name}</strong>
            <span>{user.role}</span>
          </div>
          <button className="logout-button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">OPENCI OPERATIONS</p>
            <h1>{pageTitle}</h1>
          </div>
          <span className="role-badge">{user.role}</span>
        </header>

        {dataError && (
          <div className="notice error-notice">
            {dataError}
            <button
              className="text-button"
              onClick={() => setAccessToken(accessToken)}
            >
              Retry
            </button>
          </div>
        )}

        {dataLoading && (
          <p className="muted">Loading your workspace data...</p>
        )}

        {!dataLoading && activePage === "overview" && (
          <>
            <section className="welcome-banner">
              <div>
                <p className="eyebrow">WORKSPACE OVERVIEW</p>
                <h2>Welcome, {user.name}</h2>
                <p>
                  Monitor investigation records and manage your operations.
                </p>
              </div>
            </section>

            <section className="stats-grid">
              <article className="stat-card">
                <span>Total Investigations</span>
                <strong>{investigations.length}</strong>
                <small>Records in the system</small>
              </article>

              <article className="stat-card">
                <span>Pending Investigations</span>
                <strong>{pendingCount}</strong>
                <small>Awaiting progress</small>
              </article>

              <article className="stat-card">
                <span>Assigned Investigations</span>
                <strong>{assignedCount}</strong>
                <small>Linked to an agent</small>
              </article>

              {user.role === "admin" && (
                <article className="stat-card">
                  <span>Total Users</span>
                  <strong>{users.length}</strong>
                  <small>Registered accounts</small>
                </article>
              )}
            </section>

            <section className="content-card">
              <div className="section-heading">
                <div>
                  <h2>Recent Investigations</h2>
                  <p>Latest records currently stored in the system.</p>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => setActivePage("investigations")}
                >
                  View all
                </button>
              </div>

              {investigations.length === 0 ? (
                <p className="empty-state">
                  No investigations found. Create one through your API for now.
                </p>
              ) : (
                <InvestigationTable
                  items={investigations.slice(0, 5)}
                />
              )}
            </section>
          </>
        )}

        {!dataLoading && activePage === "users" && (
          <section className="content-card">
            <div className="section-heading">
              <div>
                <h2>Registered Users</h2>
                <p>Accounts currently stored in PostgreSQL.</p>
              </div>
              <span className="count-badge">{users.length} users</span>
            </div>

            {users.length === 0 ? (
              <p className="empty-state">No users found.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Role</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((item) => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>{item.email}</td>
                        <td>
                          <span className="role-badge">{item.role}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        
{!dataLoading && activePage === "investigations" && (
  <section className="content-card">
    {/* Section heading */}
    <div className="section-heading">
      <div>
        <h2>All Investigations</h2>
        <p>Investigation records stored in the system.</p>
      </div>

      <div className="heading-actions">
        <span className="count-badge">
          {investigations.length} records
        </span>

        {(user.role === "admin" || user.role === "supervisor") && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setShowCreateForm((current) => !current);
              setCreateError("");
            }}
          >
            {showCreateForm ? "Cancel" : "+ New Investigation"}
          </button>
        )}
      </div>
    </div>

    {/* New Investigation form */}
    {showCreateForm && (
      <form
        className="create-form"
        onSubmit={handleCreateInvestigation}
      >
        <h3>New Investigation</h3>

        <label htmlFor="reference_number">Reference Number</label>
        <input
          id="reference_number"
          value={newInvestigation.reference_number}
          onChange={(event) =>
            setNewInvestigation({
              ...newInvestigation,
              reference_number: event.target.value,
            })
          }
          placeholder="INV-001"
          required
        />

        <label htmlFor="subject_name">Subject Name</label>
        <input
          id="subject_name"
          value={newInvestigation.subject_name}
          onChange={(event) =>
            setNewInvestigation({
              ...newInvestigation,
              subject_name: event.target.value,
            })
          }
          placeholder="Full name"
          required
        />

        <label htmlFor="address">Address</label>
        <input
          id="address"
          value={newInvestigation.address}
          onChange={(event) =>
            setNewInvestigation({
              ...newInvestigation,
              address: event.target.value,
            })
          }
          placeholder="Investigation address"
          required
        />

        <label htmlFor="priority">Priority</label>
        <select
          id="priority"
          value={newInvestigation.priority}
          onChange={(event) =>
            setNewInvestigation({
              ...newInvestigation,
              priority: event.target.value,
            })
          }
        >
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>

        {createError && <p className="error">{createError}</p>}

        <button
          className="primary-button"
          type="submit"
          disabled={creating}
        >
          {creating ? "Creating..." : "Create Investigation"}
        </button>
      </form>
    )}

    {/* Investigation list */}
    {investigations.length === 0 ? (
      <p className="empty-state">
        No investigations found. Click "+ New Investigation" to create one.
      </p>
    ) : (
      <InvestigationTable items={investigations} />
    )}
  </section>
)}

      </main>
    </div>
  );
}

function InvestigationTable({ items }: { items: Investigation[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Reference</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Priority</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="reference">{item.reference_number}</td>
              <td>{item.subject_name}</td>
              <td>
                <span className="status-badge">{item.status}</span>
              </td>
              <td>{item.priority}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
