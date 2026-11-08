import { NavLink } from "react-router";
import {
  Activity, FileCheck2, LayoutDashboard, MapPinned,
  PanelLeftClose, PanelLeftOpen, Route, Search, Settings2,
  ShieldCheck, UsersRound,
} from "lucide-react";
import type { User } from "@/types/api";
import { PLANNING_ENABLED } from "@/config";
import { CollectorBrand } from "./CollectorBrand";

type Item = { to: string; label: string; icon: typeof LayoutDashboard };

function sectionsFor(user: User): { label: string; items: Item[] }[] {
  const manage = user.role !== "agent";
  return [
    {
      label: "Operations",
      items: [
        { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
        { to: "/investigations", label: "Investigations", icon: Search },
        ...(manage && PLANNING_ENABLED ? [
          { to: "/field-agents", label: "Field Agents", icon: UsersRound },
          { to: "/route-planning", label: "Route Planning", icon: Route },
        ] : []),
        ...(!manage && PLANNING_ENABLED ? [
          { to: "/my-route", label: "My Route", icon: MapPinned },
        ] : []),
        ...(manage ? [{ to: "/reports", label: "Reports", icon: FileCheck2 }] : []),
      ],
    },
    ...(user.role === "admin" ? [{
      label: "Administration",
      items: [
        { to: "/activity-logs", label: "Activity Logs", icon: Activity },
        { to: "/users", label: "User Management", icon: Settings2 },
        { to: "/access-control", label: "Access Control", icon: ShieldCheck },
      ],
    }] : []),
  ];
}

export function WorkspaceSidebar({
  user, collapsed = false, mobile = false, planningShell = false, onToggleCollapse, onNavigate,
}: {
  user: User;
  collapsed?: boolean;
  mobile?: boolean;
  planningShell?: boolean;
  onToggleCollapse?: () => void;
  onNavigate?: () => void;
}) {
  const desktopWidth = planningShell
    ? collapsed ? "w-[68px]" : "w-[232px]"
    : collapsed ? "w-[72px]" : "w-[248px]";
  const horizontalPadding = planningShell && collapsed ? "px-[9px]" : "px-3";

  return (
    <aside
      className={`${mobile ? "relative h-full w-full" : `fixed inset-y-0 left-0 z-30 hidden ${desktopWidth} md:flex`} flex-col bg-[#f5f7fb] ${horizontalPadding} py-5 text-[#243854]`}
      aria-label="Workspace navigation"
    >
      <div className={`flex items-center ${collapsed ? "justify-between gap-0 px-0" : "justify-between gap-2 px-3"}`}>
        {!collapsed ? (
          <NavLink to="/dashboard" onClick={onNavigate} className="flex min-w-0 items-center rounded-lg text-[#1f3554] no-underline focus-visible:outline-[#315eb8]" aria-label="Collector field operations home">
            <CollectorBrand variant="workspace-sidebar" />
          </NavLink>
        ) : (
          <NavLink to="/dashboard" onClick={onNavigate} aria-label="Collector field operations home" className="grid h-10 w-full place-items-center rounded-md hover:bg-[#f3f6fb]">
            <img src="/collector-mark.svg" alt="" aria-hidden="true" className="size-6" />
          </NavLink>
        )}
        {onToggleCollapse && (
          <button type="button" onClick={onToggleCollapse} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!collapsed} className={`grid shrink-0 place-items-center border border-[#e2e7ef] bg-white text-[#61728b] hover:bg-[#f5f7fa] focus-visible:outline-[#315eb8] ${collapsed ? "size-6 rounded-md" : "size-9 rounded-lg"}`}>
            {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={18} />}
          </button>
        )}
      </div>
      <nav className="mt-9 flex-1 space-y-7 overflow-y-auto" aria-label="Main navigation">
        {sectionsFor(user).map((section) => (
          <div key={section.label} className="space-y-1">
            {!collapsed && <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.12em] text-black">{section.label}</p>}
            {section.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                onClick={onNavigate}
                title={collapsed ? label : undefined}
                className={({ isActive }) => `group flex min-h-10 items-center ${collapsed ? "justify-center px-0" : "gap-3 px-3"} rounded-lg text-[13px] font-medium no-underline transition-colors focus-visible:outline-[#315eb8] ${isActive ? "bg-[#e2ebfa] text-[#244c96] ring-1 ring-inset ring-[#cddcf5]" : "text-[#4a5b72] hover:bg-[#f0f2f5] hover:text-[#344861]"}`}
              >
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                {!collapsed && <span className="truncate">{label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {!collapsed && <div className="mt-5 rounded-xl border border-[#e6eaf0] bg-[#f7f8fa] px-3 py-3 text-[11px] leading-5 text-[#7a8799]">Operational workspace <span className="block font-medium text-[#344861]">{user.role === "agent" ? "Field agent" : user.role === "supervisor" ? "Supervisor" : "Administrator"}</span></div>}
    </aside>
  );
}
