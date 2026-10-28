import type { ReactNode } from "react";
import { Link } from "react-router";
import type { UserRole } from "@/types/api";
import { useSession } from "@/app/session";
import { EmptyState } from "@/components/ui/Primitives";
import { PLANNING_ENABLED } from "@/config";

export function ProtectedRoute({
  roles,
  children,
  planning = false,
}: {
  roles: UserRole[];
  children: ReactNode;
  planning?: boolean;
}) {
  const { user } = useSession();

  if (!roles.includes(user.role)) {
    return (
      <EmptyState
        title="403 · Access restricted"
        action={
          <Link className="secondary-button" to="/dashboard">
            Go to Dashboard
          </Link>
        }
      >
        Your role does not have access to this page.
      </EmptyState>
    );
  }

  if (planning && !PLANNING_ENABLED) {
    return (
      <EmptyState title="Planning is unavailable">
        Planning is disabled in this environment. Manual investigation
        assignment is available.
      </EmptyState>
    );
  }

  return children;
}
