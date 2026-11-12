import { useCallback, useEffect, useState } from "react";
import {
  useLocation,
  useNavigate,
  useOutletContext,
  useParams,
} from "react-router";
import { useSession } from "@/app/session";
import {
  getInvestigation,
  confirmInvestigationLocation,
} from "@/features/investigations/api";
import { useResource } from "@/hooks/useResource";
import { Skeleton, InlineAlert, Button } from "@/components/ui/Primitives";
import { InvestigationDetailsPage } from "./InvestigationDetailsPage";
export function InvestigationDetailRoute() {
  const { id } = useParams();
  const { token, user, agentPermissions } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const setHeaderReference = useOutletContext<(reference: string) => void>();
  const resource = useResource(
    useCallback(
      (signal) => getInvestigation(token, Number(id), signal),
      [token, id],
    ),
    {
      resourceKeys: [`investigation:${id}`],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 30_000,
    },
  );
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");
  useEffect(() => {
    if (resource.data && location.hash)
      document.getElementById(location.hash.slice(1))?.scrollIntoView();
  }, [resource.data, location.hash]);
  useEffect(() => {
    const reference =
      resource.data?.id === Number(id)
        ? resource.data.reference_number
        : "";
    setHeaderReference(reference);
    return () => setHeaderReference("");
  }, [id, resource.data?.id, resource.data?.reference_number, setHeaderReference]);
  return (
    <>
      {location.state?.locationError && (
        <InlineAlert variant="warning">
          The investigation was saved, but its location could not be confirmed.
          Confirm the point in the Location section below.
          {location.state.locationDraft && (
            <Button
              disabled={retrying}
              onClick={() => {
                setRetrying(true);
                setRetryError("");
                void confirmInvestigationLocation(
                  token,
                  Number(id),
                  location.state.locationDraft,
                )
                  .then(() => {
                    navigate(location.pathname, { replace: true, state: null });
                    resource.refresh();
                  })
                  .catch((error: unknown) =>
                    setRetryError(
                      error instanceof Error
                        ? error.message
                        : "The point could not be confirmed. Try again.",
                    ),
                  )
                  .finally(() => setRetrying(false));
              }}
            >
              {retrying ? "Retrying…" : "Retry location confirmation"}
            </Button>
          )}
        </InlineAlert>
      )}
      {retryError && <InlineAlert>{retryError}</InlineAlert>}
      {resource.loading && !resource.data ? (
        <Skeleton rows={6} />
      ) : resource.error && !resource.data ? (
        <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
      ) : (
        resource.data && (
          <>
            {resource.error && (
              <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
            )}
            <InvestigationDetailsPage
              token={token}
              user={user}
              agentPermissions={agentPermissions}
              investigation={resource.data}
              onChanged={resource.refresh}
              onDeleted={() => navigate("/investigations")}
            />
          </>
        )
      )}
    </>
  );
}
