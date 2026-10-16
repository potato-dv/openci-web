import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";

import { useAuth } from "./hooks/useAuth";
import { useWorkspaceData } from "./hooks/useWorkspaceData";
import {
  createInvestigation,
  getTrashedInvestigations,
  updateUserActivation,
  updateUserRole,
} from "./services/api";
import type {
  Investigation,
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
import { UserCreateForm } from "./components/users/UserCreateForm";
import { PhilippineAddressFields } from "./components/investigations/PhilippineAddressFields";
import { ActivityLogPage } from "./pages/ActivityLogPage";
import { TrashPage } from "./pages/TrashPage";
import { Modal } from "./components/ui/Modal";
import { RowActions } from "./components/ui/RowActions";
import { formatUserName } from "./utils/userName";

type Page = "overview" | "users" | "investigations" | "activity";

function getInvestigationIdFromLocation() {
  const value = new URLSearchParams(window.location.search).get("investigationId");
  const id = value ? Number(value) : null;
  return id !== null && Number.isSafeInteger(id) && id > 0 ? id : null;
}

const emptyInvestigation: NewInvestigation = {
  first_name: "", middle_name: null, last_name: "",
  house_number: "", unit_floor_building_name: "",
  street: "", subdivision_village_purok: "", region_code: "", province_code: "",
  city_municipality_code: "", barangay_code: "", postal_code: "", priority: "normal",
};

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showUserCreateForm, setShowUserCreateForm] = useState(false);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState<(typeof users)[number]["role"]>("agent");
  const [roleEditError, setRoleEditError] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [userStatusError, setUserStatusError] = useState("");
  const [updatingUserId, setUpdatingUserId] = useState<number | null>(null);

  const [newInvestigation, setNewInvestigation] = useState<NewInvestigation>(emptyInvestigation);
  const [activePage, setActivePage] = useState<Page>(() =>
    getInvestigationIdFromLocation() === null ? "overview" : "investigations",
  );
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedInvestigationId, setSelectedInvestigationId] = useState<number | null>(
    getInvestigationIdFromLocation,
  );
  const [investigationQuery, setInvestigationQuery] = useState("");
  const [investigationStatus, setInvestigationStatus] = useState<
    InvestigationStatus | "all"
  >("all");
  const [investigationPriority, setInvestigationPriority] = useState<
    InvestigationPriority | "all"
  >("all");
  const [showTrash, setShowTrash] = useState(false);
  const [trashedInvestigations, setTrashedInvestigations] = useState<Investigation[]>([]);
  const [trashLoaded, setTrashLoaded] = useState(false);
  const [trashLoading, setTrashLoading] = useState(false);
  const [trashError, setTrashError] = useState("");
  const [investigationNotice, setInvestigationNotice] = useState("");

  const { accessToken, user, isInitializing, login, logout } = useAuth();
  const {
    users,
    investigations,
    isLoading: dataLoading,
    error: dataError,
    setUsers,
    setInvestigations,
  } = useWorkspaceData(user, accessToken, refreshKey);

  useEffect(() => {
    function syncNavigationFromHistory() {
      const id = getInvestigationIdFromLocation();
      if (id !== null) {
        setActivePage("investigations");
        setSelectedInvestigationId(id);
        setShowTrash(false);
        return;
      }

      setSelectedInvestigationId(null);
      const page = window.history.state?.openciPage as Page | undefined;
      if (page && ["overview", "users", "investigations", "activity"].includes(page)) {
        setActivePage(page);
      }
    }

    window.addEventListener("popstate", syncNavigationFromHistory);
    return () => window.removeEventListener("popstate", syncNavigationFromHistory);
  }, []);

  const filteredInvestigations = investigations.filter((item) => {
    const query = investigationQuery.trim().toLowerCase();
    const matchesQuery =
      query.length === 0 ||
      [item.reference_number, item.subject_name, item.address_display, item.legacy_address ?? ""].some((value) =>
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
      setActivePage(selectedInvestigationId === null ? "overview" : "investigations");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect to the server.",
      );
    } finally {
      setLoading(false);
    }
  }

  function openInvestigationDetails(investigationId: number) {
    const listUrl = new URL(window.location.href);
    listUrl.searchParams.delete("investigationId");
    window.history.replaceState({ openciPage: "investigations" }, "", listUrl);

    const detailUrl = new URL(listUrl);
    detailUrl.searchParams.set("investigationId", String(investigationId));
    window.history.pushState(
      { openciPage: "investigations", openciDetail: true, openciHasParent: true },
      "",
      detailUrl,
    );
    setActivePage("investigations");
    setSelectedInvestigationId(investigationId);
    setShowTrash(false);
  }

  function returnToInvestigationList() {
    if (window.history.state?.openciHasParent === true) {
      window.history.back();
      return;
    }

    const listUrl = new URL(window.location.href);
    listUrl.searchParams.delete("investigationId");
    window.history.replaceState({ openciPage: "investigations" }, "", listUrl);
    setActivePage("investigations");
    setSelectedInvestigationId(null);
    setShowTrash(false);
  }

  function handlePageChange(page: Page) {
    if (page === "investigations" && selectedInvestigationId !== null) {
      returnToInvestigationList();
      return;
    }

    if (page === "investigations") {
      setShowTrash(false);
    }

    if (page !== "investigations" && selectedInvestigationId !== null) {
      const pageUrl = new URL(window.location.href);
      pageUrl.searchParams.delete("investigationId");
      window.history.replaceState({ openciPage: page }, "", pageUrl);
      setSelectedInvestigationId(null);
    }
    setActivePage(page);
  }

  async function handleShowTrash(forceReload = false) {
    setSelectedInvestigationId(null);
    setShowTrash(true);
    setTrashError("");
    if (trashLoaded && !forceReload) return;

    setTrashLoading(true);
    try {
      setTrashedInvestigations(await getTrashedInvestigations(accessToken));
      setTrashLoaded(true);
    } catch (err) {
      setTrashError(err instanceof Error ? err.message : "Could not load Trash.");
    } finally {
      setTrashLoading(false);
    }
  }

  async function handleCreateInvestigation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError("");
    setCreating(true);

    try {
      const data = await createInvestigation(accessToken, newInvestigation);

      setInvestigations((current) => [data, ...current]);

      setNewInvestigation(emptyInvestigation);

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

  async function handleUserRole(userId: number, role: (typeof users)[number]["role"]) {
    setUserStatusError("");
    setRoleEditError("");
    setUpdatingUserId(userId);
    try {
      const updated = await updateUserRole(accessToken, userId, role);
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setEditingUserId(null);
    } catch (err) {
      setRoleEditError(err instanceof Error ? err.message : "Unable to update role.");
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
    setShowTrash(false);
    setTrashedInvestigations([]);
    setTrashLoaded(false);
    const loginUrl = new URL(window.location.href);
    loginUrl.searchParams.delete("investigationId");
    window.history.replaceState({}, "", loginUrl);
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
          <img className="login-logo" src="/favicon.svg" alt="Collector" />
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

  const pageTitle = activePage === "overview" ? "Dashboard" : "";

  return (
    <div className="app-layout">
      <Sidebar
        user={user}
        activePage={activePage}
        onPageChange={handlePageChange}
      />

      <Topbar
        title={pageTitle}
        user={user}
        onLogout={handleLogout}
        breadcrumbs={selectedInvestigationId !== null ? {
          parentLabel: "Investigations",
          currentLabel: "Investigation detail",
          onParentClick: returnToInvestigationList,
        } : undefined}
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
                    onClick={() => handlePageChange("investigations")}
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
                <InvestigationTable
                  items={investigations.slice(0, 5)}
                  onSubjectOpen={(item) => openInvestigationDetails(item.id)}
                />
              )}
            </section>
          </>
        )}

        {!dataLoading && activePage === "users" && (
          <section className="content-card">
            <SectionToolbar
              title="Registered Users"
              description="Accounts currently stored in PostgreSQL."
              actions={
                <div className="heading-actions">
                  <span className="count-badge">{users.length} users</span>
                  <button type="button" className="primary-button toolbar-button" onClick={() => setShowUserCreateForm(true)}>New account</button>
                </div>
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
                      <th className="user-actions-cell">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((item) => (
                      <tr key={item.id}>
                        <td>{formatUserName(item.name)}</td>
                        <td>{item.email}</td>
                        <td className="role-cell">{item.role}</td>
                        <td>
                          <span
                            className={`status-badge account-${item.is_active ? "active" : "inactive"}`}
                          >
                            {item.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="user-actions-cell">
                          <RowActions label={formatUserName(item.name)}>
                              <button type="button" role="menuitem" onClick={() => { setEditingUserId(item.id); setEditRole(item.role); setRoleEditError(""); }}>Edit role</button>
                              <button type="button" role="menuitem" disabled={updatingUserId === item.id || item.id === user.id} title={item.id === user.id ? "You cannot change your own account status" : undefined} onClick={() => { void handleUserActivation(item.id, !item.is_active); }}>
                                {updatingUserId === item.id ? "Updating…" : item.is_active ? "Deactivate" : "Activate"}
                              </button>
                          </RowActions>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <UserCreateForm
              token={accessToken}
              open={showUserCreateForm}
              onClose={() => setShowUserCreateForm(false)}
              onCreated={(createdUser) => setUsers((current) => [createdUser, ...current])}
            />
            <Modal open={editingUserId !== null} title="Edit account role" onClose={() => setEditingUserId(null)}>
              <form className="modal-form" onSubmit={(event) => { event.preventDefault(); if (editingUserId !== null) void handleUserRole(editingUserId, editRole); }}>
                <label className="modal-field">Role
                  <select value={editRole} onChange={(event) => setEditRole(event.target.value as typeof editRole)}>
                    <option value="admin">Admin</option><option value="supervisor">Supervisor</option><option value="agent">Agent</option>
                  </select>
                </label>
                {roleEditError && <p className="error" role="alert">{roleEditError}</p>}
                <div className="modal-form-actions">
                  <button type="button" className="secondary-button toolbar-button" onClick={() => setEditingUserId(null)} disabled={updatingUserId !== null}>Cancel</button>
                  <button type="submit" className="primary-button toolbar-button" disabled={updatingUserId !== null}>{updatingUserId !== null ? "Saving…" : "Save role"}</button>
                </div>
              </form>
            </Modal>
          </section>
        )}

        {!dataLoading && activePage === "investigations" && !showTrash && (
          selectedInvestigationId !== null && investigations.some((item) => item.id === selectedInvestigationId) ? (
            <InvestigationDetailsPage
              key={selectedInvestigationId}
              token={accessToken}
              user={user}
              investigation={investigations.find((item) => item.id === selectedInvestigationId)!}
              onChanged={() => setRefreshKey((current) => current + 1)}
              onDeleted={(item) => {
                const listUrl = new URL(window.location.href);
                listUrl.searchParams.delete("investigationId");
                window.history.replaceState({ openciPage: "investigations" }, "", listUrl);
                setSelectedInvestigationId(null);
                setInvestigations((current) => current.filter((currentItem) => currentItem.id !== item.id));
                setTrashLoaded(false);
                setInvestigationNotice(`${item.reference_number} was moved to Trash.`);
                setRefreshKey((current) => current + 1);
              }}
            />
          ) : <section className="content-card">
            <SectionToolbar
              title="All Investigations"
              description="Investigation records stored in the system."
              actions={
                <div className="heading-actions">
                  <span className="count-badge">
                    {filteredInvestigations.length} of {investigations.length}{" "}
                    records
                  </span>

                  {(user.role === "supervisor" || user.role === "admin") && (
                    <button
                      type="button"
                      className="primary-button toolbar-button"
                      onClick={() => {
                        setShowCreateForm(true);
                        setCreateError("");
                      }}
                    >
                      + New Investigation
                    </button>
                  )}
                  {(user.role === "admin" || user.role === "supervisor") && (
                    <button
                      type="button"
                      className="secondary-button toolbar-button"
                      onClick={() => void handleShowTrash()}
                    >
                      Trash
                    </button>
                  )}
                </div>
              }
            />

            {investigationNotice && <p className="success-message" role="status" aria-live="polite">{investigationNotice}</p>}

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

            {/* Investigation creation is rendered in a modal outside table flow. */}
            <Modal open={showCreateForm} title="New investigation" size="wide" onClose={() => setShowCreateForm(false)}>
              <form className="create-form modal-form" onSubmit={handleCreateInvestigation}>
                <h3>New Investigation</h3>

                <p className="form-hint">A reference number will be generated automatically.</p>

                <div className="subject-name-grid">
                  <label htmlFor="subject_first_name">
                    First name
                    <input
                      id="subject_first_name"
                      autoComplete="given-name"
                      value={newInvestigation.first_name}
                      maxLength={255}
                      onChange={(event) => setNewInvestigation({ ...newInvestigation, first_name: event.target.value })}
                      required
                    />
                  </label>
                  <label htmlFor="subject_middle_name">
                    Middle name <span className="optional-label">Optional</span>
                    <input
                      id="subject_middle_name"
                      autoComplete="additional-name"
                      value={newInvestigation.middle_name ?? ""}
                      maxLength={255}
                      onChange={(event) => setNewInvestigation({ ...newInvestigation, middle_name: event.target.value || null })}
                    />
                  </label>
                  <label htmlFor="subject_last_name">
                    Last name
                    <input
                      id="subject_last_name"
                      autoComplete="family-name"
                      value={newInvestigation.last_name}
                      maxLength={255}
                      onChange={(event) => setNewInvestigation({ ...newInvestigation, last_name: event.target.value })}
                      required
                    />
                  </label>
                </div>

                <PhilippineAddressFields token={accessToken} value={newInvestigation} onChange={setNewInvestigation} />

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

                {createError && <p className="error" role="alert">{createError}</p>}

                <div className="modal-form-actions">
                  <button type="button" className="secondary-button toolbar-button" onClick={() => setShowCreateForm(false)} disabled={creating}>Cancel</button>
                  <button className="primary-button toolbar-button" type="submit" disabled={creating}>{creating ? "Creating…" : "Create investigation"}</button>
                </div>
              </form>
            </Modal>

            {/* Investigation list */}
            {filteredInvestigations.length === 0 ? (
              <p className="empty-state">
                {investigations.length === 0
                  ? user.role === "agent"
                    ? "No investigations are assigned to you yet."
                    : "No investigations found. Use New Investigation to create one."
                  : "No investigations match the selected filters."}
              </p>
            ) : (
              <InvestigationTable
                items={filteredInvestigations}
                onSelect={(item) => openInvestigationDetails(item.id)}
              />
            )}

          </section>
        )}

        {!dataLoading && activePage === "investigations" && showTrash && (
          <TrashPage
            token={accessToken}
            isAdmin={user.role === "admin"}
            items={trashedInvestigations}
            loading={trashLoading}
            error={trashError}
            onRetry={() => void handleShowTrash(true)}
            onRestored={(item) => {
              setTrashedInvestigations((current) => current.filter((currentItem) => currentItem.id !== item.id));
              setInvestigations((current) => [item, ...current.filter((currentItem) => currentItem.id !== item.id)]);
              setRefreshKey((current) => current + 1);
            }}
            onPermanentlyDeleted={(item) => {
              setTrashedInvestigations((current) => current.filter((currentItem) => currentItem.id !== item.id));
            }}
          />
        )}

        {!dataLoading && activePage === "activity" && user.role === "admin" && (
          <ActivityLogPage token={accessToken} />
        )}
      </main>
    </div>
  );
}

export default App;
