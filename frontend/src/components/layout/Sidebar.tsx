import { NavLink } from "react-router";
import {
  LayoutDashboard,
  Search,
  UsersRound,
  Route,
  FileCheck2,
  Activity,
  Settings2,
  MapPinned,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import type { User } from "../../types/api";
import { PLANNING_ENABLED } from "../../config";
import { IconButton } from "../ui/Primitives";
import { CollectorBrand } from "./CollectorBrand";
export function Sidebar({
  user,
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: {
  user: User;
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const manage = user.role !== "agent";
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <NavLink
          to="/dashboard"
          className="sidebar-brand"
          onClick={onNavigate}
          aria-label="Collector field operations home"
          title={collapsed ? "Collector · Field operations" : undefined}
        >
          <CollectorBrand variant="sidebar" />
        </NavLink>
        {onToggleCollapse && (
          <IconButton
            className="sidebar-collapse-button"
            label={collapsed ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={!collapsed}
            onClick={onToggleCollapse}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </IconButton>
        )}
      </div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        <div className="nav-group">
          <p className="nav-label">Workspace</p>
          {[
            { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
            { to: "/investigations", label: "Investigations", icon: Search },
            ...(manage && PLANNING_ENABLED
              ? [
                  {
                    to: "/field-agents",
                    label: "Field Agents",
                    icon: UsersRound,
                  },
                  {
                    to: "/route-planning",
                    label: "Route Planning",
                    icon: Route,
                  },
                ]
              : []),
            ...(!manage && PLANNING_ENABLED
              ? [{ to: "/my-route", label: "My Route", icon: MapPinned }]
              : []),
            ...(manage
              ? [{ to: "/reports", label: "Reports", icon: FileCheck2 }]
              : []),
          ].map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
              onClick={onNavigate}
            >
              <Icon
                className="nav-icon"
                aria-hidden="true"
                strokeWidth={1.75}
              />
              <span className="nav-item-label">{label}</span>
            </NavLink>
          ))}
        </div>
        {user.role === "admin" && (
          <div className="nav-group">
            <p className="nav-label">Administration</p>
            <NavLink
              to="/activity-logs"
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
              onClick={onNavigate}
            >
              <Activity className="nav-icon" aria-hidden="true" />
              <span className="nav-item-label">Activity Logs</span>
            </NavLink>
            <NavLink
              to="/users"
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
              onClick={onNavigate}
            >
              <Settings2 className="nav-icon" aria-hidden="true" />
              <span className="nav-item-label">User Management</span>
            </NavLink>
          </div>
        )}
      </nav>
    </aside>
  );
}
