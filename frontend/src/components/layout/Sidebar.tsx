import { useEffect, useRef, useState } from "react";
import type { User } from "../../types/api";

type Page = "overview" | "users" | "investigations";

type SidebarProps = {
  user: User;
  activePage: Page;
  onPageChange: (page: Page) => void;
  onLogout: () => void;
};

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
        <img className="sidebar-brand-icon" src="/favicon.svg" alt="OpenCI" />
        <div>
          <strong>OpenCI</strong>
          <span>Operations</span>
        </div>
      </div>

      <p className="nav-label">WORKSPACE</p>
      <button
        className={`nav-item ${activePage === "overview" ? "active" : ""}`}
        onClick={() => onPageChange("overview")}
      >
        Overview
      </button>
      <button
        className={`nav-item ${activePage === "investigations" ? "active" : ""}`}
        onClick={() => onPageChange("investigations")}
      >
        Investigations
      </button>

      {user.role === "admin" && (
        <>
          <p className="nav-label">ADMINISTRATION</p>
          <button
            className={`nav-item ${activePage === "users" ? "active" : ""}`}
            onClick={() => onPageChange("users")}
          >
            User Management
          </button>
        </>
      )}

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
