import { useEffect, useRef, useState } from "react";
import type { User } from "../../types/api";

type Page = "overview" | "users" | "investigations" | "activity";

type SidebarProps = {
  user: User;
  activePage: Page;
  onPageChange: (page: Page) => void;
  onLogout: () => void;
};

function NavigationIcon({ name }: { name: "overview" | "investigations" | "users" | "activity" }) {
  const paths = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1.2" /><rect x="14" y="3" width="7" height="7" rx="1.2" /><rect x="3" y="14" width="7" height="7" rx="1.2" /><rect x="14" y="14" width="7" height="7" rx="1.2" /></>,
    investigations: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.2 4.2" /></>,
    users: <><circle cx="9" cy="8" r="3.2" /><path d="M3 20c.4-3.3 2.6-5 6-5s5.6 1.7 6 5M16 5.2a3.2 3.2 0 0 1 0 6.2M17 15c2.2.7 3.4 2.3 3.7 5" /></>,
    activity: <><path d="M3 12h4l2.2-6 4.2 12 2.2-6H21" /></>,
  };

  return <svg className="nav-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

export function Sidebar({
  user,
  activePage,
  onPageChange,
  onLogout,
}: SidebarProps) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);
  const accountMenuItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (
        accountMenuRef.current &&
        !accountMenuRef.current.contains(event.target as Node)
      ) {
        setAccountMenuOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeAccountMenu();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  useEffect(() => {
    if (accountMenuOpen) {
      accountMenuItemRef.current?.focus();
    }
  }, [accountMenuOpen]);

  function closeAccountMenu() {
    setAccountMenuOpen(false);
    accountTriggerRef.current?.focus();
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img className="sidebar-brand-icon" src="/favicon.svg" alt="Collector" />
        <div>
          <strong>Collector</strong>
          <span>Operations</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        <div className="nav-group">
          <p className="nav-label">Workspace</p>
          <button className={`nav-item ${activePage === "overview" ? "active" : ""}`} onClick={() => onPageChange("overview")}>
            <NavigationIcon name="overview" />Overview
          </button>
          <button className={`nav-item ${activePage === "investigations" ? "active" : ""}`} onClick={() => onPageChange("investigations")}>
            <NavigationIcon name="investigations" />Investigations
          </button>
        </div>

        {user.role === "admin" && <div className="nav-group">
          <p className="nav-label">Administration</p>
          <button className={`nav-item ${activePage === "users" ? "active" : ""}`} onClick={() => onPageChange("users")}>
            <NavigationIcon name="users" />User Management
          </button>
          <button className={`nav-item ${activePage === "activity" ? "active" : ""}`} onClick={() => onPageChange("activity")}>
            <NavigationIcon name="activity" />Activity log
          </button>
        </div>}
      </nav>

      <div className="sidebar-user" ref={accountMenuRef}>
        <button
          type="button"
          className="account-trigger"
          ref={accountTriggerRef}
          aria-expanded={accountMenuOpen}
          aria-haspopup="menu"
          aria-controls="account-menu"
          onClick={() => setAccountMenuOpen((current) => !current)}
        >
          <span className="avatar">{user.name.charAt(0).toUpperCase()}</span>
          <span className="sidebar-user-info">
            <strong>{user.name}</strong>
            <span>{user.role}</span>
          </span>
          <span
            className={`account-chevron ${accountMenuOpen ? "open" : ""}`}
            aria-hidden="true"
          />
        </button>

        {accountMenuOpen && (
          <div id="account-menu" className="account-menu" role="menu">
            <div className="account-menu-identity">
              <span className="account-menu-avatar">
                {user.name.charAt(0).toUpperCase()}
              </span>
              <span>
                <strong>{user.name}</strong>
                <small>{user.role}</small>
              </span>
            </div>
            <div className="account-menu-divider" />
            <button
              type="button"
              className="account-menu-item"
              ref={accountMenuItemRef}
              role="menuitem"
              onClick={() => {
                closeAccountMenu();
                onLogout();
              }}
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
