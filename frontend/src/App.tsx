import { useState } from "react";
import type { FormEvent } from "react";
import "./App.css";

import { useAuth } from "./hooks/useAuth";
import { useWorkspaceData } from "./hooks/useWorkspaceData";
import { createInvestigation, updateUserActivation } from "./services/api";
import type {
  InvestigationPriority,
  InvestigationStatus,
  NewInvestigation,
} from "./types/api";
import { InvestigationTable } from "./components/data/InvestigationTable";
import { InvestigationFilters } from "./components/data/InvestigationFilters";
import { InvestigationDetailsPage } from "./pages/InvestigationDetailsPage";
import { Sidebar } from "./components/layout/Sidebar";
import { SectionToolbar } from "./components/layout/SectionToolbar";
import { Topbar } from "./components/layout/Topbar";
import { Notice } from "./components/ui/Notice";
import { RoleBadge } from "./components/ui/RoleBadge";
import { UserCreateForm } from "./components/users/UserCreateForm";

type Page = "overview" | "users" | "investigations";

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [userStatusError, setUserStatusError] = useState("");
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);

  const [newInvestigation, setNewInvestigation] = useState<NewInvestigation>({
    reference_number: "",
    subject_name: "",
    address: "",
    priority: "normal",
  });
  const [activePage, setActivePage] = useState<Page>("overview");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedInvestigationId, setSelectedInvestigationId] = useState<
    number | null
  >(null);
  const [investigationQuery, setInvestigationQuery] = useState("");
  const [investigationStatus, setInvestigationStatus] = useState<
    InvestigationStatus | "all"
  >("all");
  const [investigationPriority, setInvestigationPriority] = useState<
    InvestigationPriority | "all"
  >("all");

  const { accessToken, user, isInitializing, login, logout } = useAuth();
  const {
    users,
    investigations,
    isLoading: dataLoading,
    error: dataError,
    setUsers,
    setInvestigations,
  } = useWorkspaceData(user, accessToken, refreshKey);

  const filteredInvestigations = investigations.filter((item) => {
    const query = investigationQuery.trim().toLowerCase();
    const matchesQuery =
      query.length === 0 ||
      [item.reference_number, item.subject_name, item.address].some((value) =>
        value.toLowerCase().includes(query),
      );
    const matchesStatus =
      investigationStatus === "all" || item.status === investigationStatus;
    const matchesPriority =
      investigationPriority === "all" ||
      item.priority === investigationPriority;

    return matchesQuery && matchesStatus && matchesPriority;
  });

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
      setEmail("");
      setPassword("");
      setActivePage("overview");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect to the server.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateInvestigation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError("");

    try {
      const data = await createInvestigation(accessToken, newInvestigation);

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
        err instanceof Error ? err.message : "Unable to create investigation",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleUserActivation(userId: number, isActive: boolean) {
    setUserStatusError("");
    setUpdatingUserId(userId);

    try {
      const updatedUser = await updateUserActivation(
        accessToken,
        userId,
        isActive,
      );
      setUsers((current) =>
        current.map((item) => (item.id === updatedUser.id ? updatedUser : item)),
      );
    } catch (err) {
      setUserStatusError(
        err instanceof Error ? err.message : "Unable to update account status.",
      );
    } finally {
      setUpdatingUserId(null);
    }
  }

  function handleLogout() {
    logout();
    setEmail("");
    setPassword("");
    setActivePage("overview");
    setSelectedInvestigationId(null);
  }

  if (isInitializing) {
    return (
      <main className="login-page">
        <p className="muted">Restoring your session...</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="login-page">
        <section className="login-card">
          <img className="login-logo" src="/favicon.svg" alt="OpenCI" />
          <h1>Welcome back</h1>

          <form className="login-form" onSubmit={handleLogin}>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="Email address"
              aria-label="Email address"
              autoComplete="username"
              required
            />

            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              aria-label="Password"
              autoComplete="current-password"
              required
            />

            {error && <p className="error">{error}</p>}

            <button className="primary-button login-submit" disabled={loading}>
              {loading ? "Signing in..." : "Continue"}
            </button>
          </form>
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
      <Sidebar
        user={user}
        activePage={activePage}
        onPageChange={setActivePage}
        onLogout={handleLogout}
      />

      <Topbar
        title={pageTitle}
        isLoading={dataLoading}
        onRefresh={() => setRefreshKey((current) => current + 1)}
      />

      <main className="main-content">
        {dataError && (
          <Notice
            message={dataError}
            actionLabel="Retry"
            onAction={() => setRefreshKey((current) => current + 1)}
          />
        )}

        {dataLoading && <p className="muted">Loading your workspace data...</p>}

        {!dataLoading && activePage === "overview" && (
          <>
            <section className="welcome-banner">
              <div>
                <p className="eyebrow">WORKSPACE OVERVIEW</p>
                <h2>Welcome, {user.name}</h2>
                <p>Monitor investigation records and manage your operations.</p>
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
              <SectionToolbar
                title="Recent Investigations"
                description="Latest records currently stored in the system."
                actions={
                  <button
                    type="button"
                    className="secondary-button toolbar-button"
                    onClick={() => setActivePage("investigations")}
                  >
                    View all
                  </button>
                }
              />

              {investigations.length === 0 ? (
                <p className="empty-state">
                  No investigations found. Create one through your API for now.
                </p>
              ) : (
                <InvestigationTable items={investigations.slice(0, 5)} />
              )}
            </section>
          </>
        )}

        {!dataLoading && activePage === "users" && (
          <section className="content-card">
            <UserCreateForm
              token={accessToken}
              onCreated={(createdUser) =>
                setUsers((current) => [createdUser, ...current])
              }
            />

            <SectionToolbar
              title="Registered Users"
              description="Accounts currently stored in PostgreSQL."
              actions={
                <span className="count-badge">{users.length} users</span>
              }
            />

            {userStatusError && (
              <Notice message={userStatusError} />
            )}

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
                      <th>Account status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((item) => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>{item.email}</td>
                        <td>
                          <RoleBadge role={item.role} />
                        </td>
                        <td>
                          <span
                            className={`status-badge account-${item.is_active ? "active" : "inactive"}`}
                          >
                            {item.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="text-button user-status-button"
                            disabled={updatingUserId === item.id || item.id === user.id}
                            title={item.id === user.id ? "You cannot change your own account status" : undefined}
                            onClick={() =>
                              void handleUserActivation(item.id, !item.is_active)
                            }
                          >
                            {updatingUserId === item.id
                              ? "Updating..."
                              : item.is_active
                                ? "Deactivate"
                                : "Activate"}
                          </button>
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
            <SectionToolbar
              title="All Investigations"
              description="Investigation records stored in the system."
              actions={
                <div className="heading-actions">
                  <span className="count-badge">
                    {filteredInvestigations.length} of {investigations.length}{" "}
                    records
                  </span>

                  {user.role === "supervisor" && (
                    <button
                      type="button"
                      className="secondary-button toolbar-button"
                      onClick={() => {
                        setShowCreateForm((current) => !current);
                        setCreateError("");
                      }}
                    >
                      {showCreateForm ? "Cancel" : "+ New Investigation"}
                    </button>
                  )}
                </div>
              }
            />

            <InvestigationFilters
              query={investigationQuery}
              status={investigationStatus}
              priority={investigationPriority}
              onQueryChange={setInvestigationQuery}
              onStatusChange={setInvestigationStatus}
              onPriorityChange={setInvestigationPriority}
              onReset={() => {
                setInvestigationQuery("");
                setInvestigationStatus("all");
                setInvestigationPriority("all");
              }}
            />

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
                      priority: event.target
                        .value as NewInvestigation["priority"],
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
            {filteredInvestigations.length === 0 ? (
              <p className="empty-state">
                {investigations.length === 0
                  ? 'No investigations found. Click "+ New Investigation" to create one.'
                  : "No investigations match the selected filters."}
              </p>
            ) : (
              <InvestigationTable
                items={filteredInvestigations}
                onSelect={(item) => setSelectedInvestigationId(item.id)}
              />
            )}

            {selectedInvestigationId !== null &&
              investigations.some(
                (item) => item.id === selectedInvestigationId,
              ) && (
                <InvestigationDetailsPage
                  token={accessToken}
                  user={user}
                  investigation={
                    investigations.find(
                      (item) => item.id === selectedInvestigationId,
                    )!
                  }
                  onChanged={() => setRefreshKey((current) => current + 1)}
                />
              )}
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
