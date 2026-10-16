import { useEffect, useRef, useState } from "react";
import type { User } from "../../types/api";
import { formatUserName } from "../../utils/userName";

type AccountDropdownProps = {
  user: User;
  onLogout: () => void;
};

export function AccountDropdown({ user, onLogout }: AccountDropdownProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const logoutRef = useRef<HTMLButtonElement>(null);
  const displayName = formatUserName(user.name);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && open) {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (open) logoutRef.current?.focus();
  }, [open]);

  return (
    <div className="topbar-account" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        className="topbar-account-trigger"
        aria-label={`Open account menu for ${displayName}`}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls="account-menu"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="avatar">{displayName.charAt(0)}</span>
      </button>
      {open && (
        <div id="account-menu" className="account-menu" role="menu">
          <div className="account-menu-identity">
            <span className="account-menu-avatar">{displayName.charAt(0)}</span>
            <span className="account-menu-label">
              <strong>{displayName}</strong>
              <small>{user.email}</small>
              <small className="account-menu-role">{user.role}</small>
            </span>
          </div>
          <div className="account-menu-divider" />
          <button
            ref={logoutRef}
            type="button"
            className="account-menu-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 17l5-5-5-5M15 12H3" />
              <path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" />
            </svg>
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
