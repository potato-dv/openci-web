import { useEffect, useRef, useState } from "react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";
import { LogOut, MoreVertical } from "lucide-react";
import type { User } from "../../types/api";
import { formatUserName } from "../../utils/userName";

type AccountDropdownProps = {
  user: User;
  onLogout: () => void;
  presentation?: "topbar" | "sidebar";
  collapsed?: boolean;
  mobile?: boolean;
};

export function AccountDropdown({
  user,
  onLogout,
  presentation = "topbar",
  collapsed = false,
  mobile = false,
}: AccountDropdownProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);
  const displayName = formatUserName(user.name);
  const isSidebar = presentation === "sidebar";

  useEffect(() => {
    setPortalContainer(
      mobile ? triggerRef.current?.closest("dialog") ?? null : null,
    );
  }, [mobile]);

  return (
    <DropdownMenuPrimitive.Root>
      <div className={isSidebar ? "workspace-account" : "topbar-account"}>
        <DropdownMenuPrimitive.Trigger asChild>
          <button
            ref={triggerRef}
            type="button"
            className={`${isSidebar ? "workspace-account-trigger" : "topbar-account-trigger"}${isSidebar && collapsed ? " is-collapsed" : ""}`}
            aria-label={`Account menu for ${displayName}, ${user.role}`}
            title={`${displayName}, ${user.role}`}
          >
            <span className="avatar">{displayName.charAt(0)}</span>
            {isSidebar && !collapsed && (
              <span className="workspace-account-copy" aria-hidden="true">
                <strong title={displayName}>{displayName}</strong>
                <small title={user.email}>{user.email}</small>
              </span>
            )}
            {isSidebar && (
              <MoreVertical
                className="workspace-account-menu-icon"
                aria-hidden="true"
              />
            )}
          </button>
        </DropdownMenuPrimitive.Trigger>
      </div>
      <DropdownMenuPrimitive.Portal
        container={mobile ? portalContainer ?? undefined : undefined}
      >
        <DropdownMenuPrimitive.Content
          className="account-menu"
          side={isSidebar ? (mobile ? "bottom" : "right") : "bottom"}
          align="end"
          sideOffset={isSidebar ? 4 : 8}
          collisionPadding={12}
          aria-label="Account actions"
        >
          <DropdownMenuPrimitive.Label className="account-menu-identity">
            <strong title={displayName}>{displayName}</strong>
            <small title={user.email}>{user.email}</small>
            <small className="account-menu-role">{user.role}</small>
          </DropdownMenuPrimitive.Label>
          <DropdownMenuPrimitive.Separator className="account-menu-divider" />
          <DropdownMenuPrimitive.Item
            className="account-menu-item"
            onSelect={onLogout}
          >
            <LogOut aria-hidden="true" />
            Log out
          </DropdownMenuPrimitive.Item>
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
