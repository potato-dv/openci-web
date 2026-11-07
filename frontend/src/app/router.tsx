import { lazy } from "react";
import { Link, Navigate, Route, Routes, useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { ProtectedRoute } from "@/app/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState } from "@/components/ui/Primitives";
import type { UserRole } from "@/types/api";

export { ProtectedRoute } from "@/app/ProtectedRoute";

const DashboardPage = lazy(() =>
  import("@/features/dashboard/pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const InvestigationsPage = lazy(() =>
  import("@/features/investigations/pages/InvestigationsPage").then(
    (module) => ({ default: module.InvestigationsPage }),
  ),
);
const InvestigationDetailRoute = lazy(() =>
  import("@/features/investigations/pages/InvestigationDetailRoute").then(
    (module) => ({ default: module.InvestigationDetailRoute }),
  ),
);
const InvestigationFormPage = lazy(() =>
  import("@/features/investigations/pages/InvestigationFormPage").then(
    (module) => ({ default: module.InvestigationFormPage }),
  ),
);
const TrashRoute = lazy(() =>
  import("@/features/investigations/pages/TrashRoute").then((module) => ({
    default: module.TrashRoute,
  })),
);
const FieldAgentsPage = lazy(() =>
  import("@/features/agents/pages/FieldAgentsPage").then((module) => ({
    default: module.FieldAgentsPage,
  })),
);
const RoutePlanningPage = lazy(() =>
  import("@/features/route-planning/pages/RoutePlanningPage").then(
    (module) => ({ default: module.RoutePlanningPage }),
  ),
);
const MyRoutePage = lazy(() =>
  import("@/features/route-planning/pages/MyRoutePage").then((module) => ({
    default: module.MyRoutePage,
  })),
);
const ReportsPage = lazy(() =>
  import("@/features/reports/pages/ReportsPage").then((module) => ({
    default: module.ReportsPage,
  })),
);
const UsersPage = lazy(() =>
  import("@/features/users/pages/UsersPage").then((module) => ({
    default: module.UsersPage,
  })),
);
const AccessControlPage = lazy(() =>
  import("@/features/agent-permissions/pages/AccessControlPage").then((module) => ({
    default: module.AccessControlPage,
  })),
);
const ActivityLogPage = lazy(() =>
  import("@/features/activity-logs/pages/ActivityLogPage").then((module) => ({
    default: module.ActivityLogPage,
  })),
);

function LegacyRedirect() {
  const [params] = useSearchParams();
  const id = params.get("investigationId");
  return (
    <Navigate
      to={id && /^\d+$/.test(id) ? `/investigations/${id}` : "/dashboard"}
      replace
    />
  );
}

export function AppRoutes() {
  const { token } = useSession();
  const managers: UserRole[] = ["admin", "supervisor"];

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LegacyRedirect />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="investigations" element={<InvestigationsPage />} />
        <Route
          path="investigations/new"
          element={
            <ProtectedRoute roles={managers}>
              <InvestigationFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="investigations/trash"
          element={
            <ProtectedRoute roles={managers}>
              <TrashRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path="investigations/:id"
          element={<InvestigationDetailRoute />}
        />
        <Route
          path="investigations/:id/edit"
          element={
            <ProtectedRoute roles={managers}>
              <InvestigationFormPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="field-agents"
          element={
            <ProtectedRoute roles={managers} planning>
              <FieldAgentsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="route-planning"
          element={
            <ProtectedRoute roles={managers} planning>
              <RoutePlanningPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="my-route"
          element={
            <ProtectedRoute roles={["agent"]} planning>
              <MyRoutePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="reports"
          element={
            <ProtectedRoute roles={managers}>
              <ReportsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="users"
          element={
            <ProtectedRoute roles={["admin"]}>
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="access-control"
          element={
            <ProtectedRoute roles={["admin"]}>
              <AccessControlPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="activity-logs"
          element={
            <ProtectedRoute roles={["admin"]}>
              <ActivityLogPage token={token} />
            </ProtectedRoute>
          }
        />
        <Route
          path="*"
          element={
            <EmptyState
              title="404 · Page not found"
              action={
                <Link className="secondary-button" to="/dashboard">
                  Go to Dashboard
                </Link>
              }
            >
              This page could not be found. Use the navigation to return to your
              workspace.
            </EmptyState>
          }
        />
      </Route>
    </Routes>
  );
}
