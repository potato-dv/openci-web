import { Suspense, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { Menu, PanelLeft } from "lucide-react";
import { useSession } from "../../app/session";
import { Drawer, Skeleton } from "../ui/Primitives";
import { WorkspaceSidebar } from "./WorkspaceSidebar";
import { WorkspaceVisualContext } from "../ui/WorkspaceVisualContext";

function sectionName(pathname: string) {
  if (pathname === "/investigations/new") return "New investigation";
  if (/^\/investigations\/\d+\/edit$/.test(pathname)) return "Edit investigation";
  if (pathname === "/investigations/trash") return "Trash";
  if (pathname.startsWith("/investigations")) return "Investigations";
  if (pathname === "/field-agents") return "Field Agents";
  if (pathname === "/my-route") return "My Route";
  if (pathname === "/route-planning") return "Route Planning";
  if (pathname === "/reports") return "Reports";
  if (pathname === "/users") return "User Management";
  if (pathname === "/access-control") return "Access Control";
  if (pathname === "/activity-logs") return "Activity Logs";
  return "Dashboard";
}

export function AppShell() {
  const { user, logout, refreshAgentPermissions } = useSession();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const location = useLocation();
  const keepPlanningSurface = location.pathname === "/route-planning";
  useEffect(() => {
    document.title = `${location.pathname.split("/")[1]?.replaceAll("-", " ") || "Dashboard"} · Collector`;
    window.scrollTo(0, 0);
    document.getElementById("main-content")?.focus({ preventScroll: true });
  }, [location.pathname]);
  const section = sectionName(location.pathname);
  useEffect(() => {
    if (user.role !== "agent" || !refreshAgentPermissions) return;
    const refreshOnFocus = () => void refreshAgentPermissions();
    window.addEventListener("focus", refreshOnFocus);
    return () => {
      window.removeEventListener("focus", refreshOnFocus);
    };
  }, [refreshAgentPermissions, user.role]);
  if (!keepPlanningSurface) {
    return (
      <WorkspaceVisualContext.Provider value={true}>
      <div className="collector-workspace min-h-dvh bg-[#f5f7fb] md:pt-2 md:pr-2 md:pb-2">
        <a className="skip-link" href="#main-content">Skip to content</a>
        <WorkspaceSidebar
          user={user}
          onLogout={logout}
          collapsed={sidebarCollapsed}
        />
        <div className={`min-h-dvh overflow-x-hidden bg-white md:min-h-[calc(100dvh-1rem)] md:overflow-hidden md:rounded-2xl md:border-y md:border-r md:border-[#e5e7eb] ${sidebarCollapsed ? "md:ml-[72px]" : "md:ml-[248px]"}`}>
          <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-[#e5e7eb] bg-white px-4 md:rounded-t-2xl md:px-7">
            <div className="flex min-w-0 items-center gap-3">
              <button type="button" className="grid size-10 shrink-0 place-items-center rounded-lg border border-[#dce4ef] bg-white text-[#1d3557] md:hidden" aria-label="Open navigation" aria-expanded={navigationOpen} onClick={() => setNavigationOpen(true)}><Menu size={19} /></button>
              <button type="button" className="hidden size-9 shrink-0 place-items-center rounded-md border-0 bg-transparent text-[#596579] hover:bg-[#f2f4f7] focus-visible:outline-[#315eb8] md:grid" aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!sidebarCollapsed} onClick={() => setSidebarCollapsed((value) => !value)}><PanelLeft size={17} aria-hidden="true" /></button>
              <span className="hidden h-5 w-px bg-[#e2e5e9] md:block" aria-hidden="true" />
              <span className="hidden text-[13px] text-[#7888a0] sm:inline">Collector</span>
              <span className="hidden text-[#b4bfd0] sm:inline" aria-hidden="true">/</span>
              <span className="truncate text-[13px] font-semibold text-[#203656]">{section}</span>
            </div>
          </header>
          <main id="main-content" tabIndex={-1} className="mx-auto min-h-[calc(100dvh-64px)] max-w-[1680px] min-w-0 px-4 py-6 outline-none sm:px-6 md:min-h-[calc(100dvh-80px)] md:px-7 md:py-7 lg:px-8">
            <Suspense fallback={<Skeleton rows={6} />}><Outlet /></Suspense>
          </main>
        </div>
        <Drawer title="Navigation" open={navigationOpen} onClose={() => setNavigationOpen(false)}>
          <WorkspaceSidebar user={user} onLogout={logout} mobile onNavigate={() => setNavigationOpen(false)} />
        </Drawer>
      </div>
      </WorkspaceVisualContext.Provider>
    );
  }
  return (
    <div className="planning-ui-preserved min-h-dvh bg-[#f5f7fb] md:pt-2 md:pr-2 md:pb-2">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <WorkspaceSidebar
        user={user}
        onLogout={logout}
        collapsed={sidebarCollapsed}
      />
      <div className={`[--height-header:80px] min-h-dvh overflow-x-hidden bg-white md:min-h-[calc(100dvh-1rem)] md:overflow-hidden md:rounded-2xl md:border-y md:border-r md:border-[#e5e7eb] ${sidebarCollapsed ? "md:ml-[72px]" : "md:ml-[248px]"}`}>
        <header className="relative z-20 flex h-16 items-center justify-between gap-4 border-b border-[#e5e7eb] bg-white px-4 md:rounded-t-2xl md:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="grid size-10 shrink-0 place-items-center rounded-lg border border-[#dce4ef] bg-white text-[#1d3557] md:hidden" aria-label="Open navigation" aria-expanded={navigationOpen} onClick={() => setNavigationOpen(true)}><Menu size={19} /></button>
            <button type="button" className="hidden size-9 shrink-0 place-items-center rounded-md border-0 bg-transparent text-[#596579] hover:bg-[#f2f4f7] focus-visible:outline-[#315eb8] md:grid" aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!sidebarCollapsed} onClick={() => setSidebarCollapsed((value) => !value)}><PanelLeft size={17} aria-hidden="true" /></button>
            <span className="hidden h-5 w-px bg-[#e2e5e9] md:block" aria-hidden="true" />
            <span className="hidden text-[13px] text-[#7888a0] sm:inline">Collector</span>
            <span className="hidden text-[#b4bfd0] sm:inline" aria-hidden="true">/</span>
            <span className="truncate text-[13px] font-semibold text-[#203656]">{section}</span>
          </div>
        </header>
        <main
          id="main-content"
          className="main-content planning-main"
          tabIndex={-1}
        >
          <Suspense fallback={<Skeleton rows={6} />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <Drawer title="Navigation" open={navigationOpen} onClose={() => setNavigationOpen(false)}>
        <WorkspaceSidebar user={user} onLogout={logout} mobile onNavigate={() => setNavigationOpen(false)} />
      </Drawer>
    </div>
  );
}
