import { useCallback } from "react";
import { useSession } from "@/app/session";
import { getTrashedInvestigations } from "@/features/investigations/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { TrashPage } from "./TrashPage";
export function TrashRoute() {
  const { token, user } = useSession();
  const resource = useResource(
    useCallback(() => getTrashedInvestigations(token), [token]),
  );
  return (
    <>
      <PageHeader
        title="Trash"
        parent={{ to: "/investigations", label: "Investigations" }}
      />
      <TrashPage
        token={token}
        isAdmin={user.role === "admin"}
        items={resource.data ?? []}
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.refresh}
        onRestored={resource.refresh}
        onPermanentlyDeleted={resource.refresh}
      />
    </>
  );
}
