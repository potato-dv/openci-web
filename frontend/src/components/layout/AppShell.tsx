import { Suspense, useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { Menu } from "lucide-react";
import { useSession } from "../../app/session";
import { Sidebar } from "./Sidebar";
import { AccountDropdown } from "./AccountDropdown";
import { Drawer, IconButton, Skeleton } from "../ui/Primitives";
export function AppShell() {
  const { user, logout } = useSession();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const location = useLocation();
  useEffect(() => {
    document.title = `${location.pathname.split("/")[1]?.replaceAll("-", " ") || "Dashboard"} · Collector Operations`;
    document.getElementById("main-content")?.focus();
  }, [location.pathname]);
  return (
    <div className={`app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="desktop-navigation">
        <Sidebar
          user={user}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        />
      </div>
      <div className="workspace-shell">
        <header className="app-topbar">
          <div className="topbar-context">
            <span className="mobile-menu">
              <IconButton
                label="Open navigation"
                aria-expanded={navigationOpen}
                onClick={() => setNavigationOpen(true)}
              >
                <Menu size={20} />
              </IconButton>
            </span>
            <span className="topbar-workspace">Field operations workspace</span>
          </div>
          <AccountDropdown user={user} onLogout={logout} />
        </header>
        <main
          id="main-content"
          className={`main-content ${location.pathname === "/route-planning" ? "planning-main" : ""}`}
          tabIndex={-1}
        >
          <Suspense fallback={<Skeleton rows={6} />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <Drawer
        title="Navigation"
        open={navigationOpen}
        onClose={() => setNavigationOpen(false)}
      >
        <Sidebar
          user={user}
          onNavigate={() => setNavigationOpen(false)}
        />
      </Drawer>
    </div>
  );
}
