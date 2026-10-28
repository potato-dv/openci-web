import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { LogOut } from "lucide-react";
import type { User } from "../../types/api";
import { formatUserName } from "../../utils/userName";

type AccountDropdownProps = {
  user: User;
  onLogout: () => void;
};

export function AccountDropdown({ user, onLogout }: AccountDropdownProps) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const logoutRef = useRef<HTMLButtonElement>(null);
  const displayName = formatUserName(user.name);

  const positionMenu = useCallback(() => {
    const menu = menuRef.current;
    const trigger = triggerRef.current;
    if (!menu || !trigger || !menu.matches(":popover-open")) return;

    const viewportWidth =
      document.documentElement.clientWidth || window.innerWidth;
    const viewportHeight =
      document.documentElement.clientHeight || window.innerHeight;
    const triggerBounds = trigger.getBoundingClientRect();
    const viewportGutter = 12;
    const triggerGap = 8;
    const maxWidth = Math.max(0, Math.min(224, viewportWidth - viewportGutter * 2));
    const width = maxWidth;

    menu.style.position = "fixed";
    menu.style.inset = "auto";
    menu.style.setProperty("position-area", "none");
    menu.style.setProperty("justify-self", "start");
    menu.style.right = "auto";
    menu.style.bottom = "auto";
    menu.style.width = `${width}px`;
    menu.style.maxWidth = `${maxWidth}px`;

    const menuHeight = menu.getBoundingClientRect().height;
    const left = triggerBounds.right - width;
    const maxLeft = Math.max(
      viewportGutter,
      viewportWidth - width - viewportGutter,
    );
    const boundedLeft = Math.min(Math.max(viewportGutter, left), maxLeft);

    let top = triggerBounds.bottom + triggerGap;
    if (top + menuHeight > viewportHeight - viewportGutter) {
      top = triggerBounds.top - menuHeight - triggerGap;
    }
    top = Math.min(
      Math.max(viewportGutter, top),
      Math.max(viewportGutter, viewportHeight - menuHeight - viewportGutter),
    );

    menu.style.left = `${boundedLeft}px`;
    menu.style.top = `${top}px`;
    menu.dataset.positioned = "true";
  }, []);

  useEffect(() => {
    if (!open) return;

    let frame = 0;
    const schedulePosition = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(positionMenu);
    };

    frame = window.requestAnimationFrame(() => {
      positionMenu();
      logoutRef.current?.focus();
    });
    window.addEventListener("resize", schedulePosition);
    window.addEventListener("scroll", schedulePosition, true);
    window.visualViewport?.addEventListener("resize", schedulePosition);
    window.visualViewport?.addEventListener("scroll", schedulePosition);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedulePosition);
      window.removeEventListener("scroll", schedulePosition, true);
      window.visualViewport?.removeEventListener("resize", schedulePosition);
      window.visualViewport?.removeEventListener("scroll", schedulePosition);
    };
  }, [open, positionMenu]);

  function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      menuRef.current?.hidePopover();
      triggerRef.current?.focus();
      return;
    }

    if (event.key === "Tab") {
      menuRef.current?.hidePopover();
      return;
    }

    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      logoutRef.current?.focus();
    }
  }

  return (
    <div className="topbar-account">
      <button
        ref={triggerRef}
        type="button"
        className="topbar-account-trigger"
        aria-label={`Account menu for ${displayName}, ${user.role}`}
        title={`${displayName} · ${user.role}`}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        popoverTarget={menuId}
        popoverTargetAction="toggle"
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            const menu = menuRef.current;
            if (menu && triggerRef.current) {
              menu.showPopover({ source: triggerRef.current });
              positionMenu();
              logoutRef.current?.focus();
            }
          }
        }}
      >
        <span className="avatar">{displayName.charAt(0)}</span>
      </button>
      <div
        id={menuId}
        ref={menuRef}
        className="account-menu"
        popover="auto"
        role="menu"
        aria-label="Account actions"
        onToggle={(event) => {
          const nextOpen = (event.nativeEvent as ToggleEvent).newState === "open";
          setOpen(nextOpen);
          if (!nextOpen) menuRef.current?.removeAttribute("data-positioned");
        }}
        onKeyDown={handleMenuKeyDown}
      >
        <div
          className="account-menu-identity"
          role="group"
          aria-label="Signed-in account"
        >
          <strong title={displayName}>{displayName}</strong>
          <small title={user.email}>{user.email}</small>
          <small className="account-menu-role">{user.role}</small>
        </div>
        <div className="account-menu-divider" role="separator" />
        <button
          ref={logoutRef}
          type="button"
          className="account-menu-item"
          role="menuitem"
          onClick={() => {
            menuRef.current?.hidePopover();
            onLogout();
          }}
        >
          <LogOut aria-hidden="true" />
          Log out
        </button>
      </div>
    </div>
  );
}
