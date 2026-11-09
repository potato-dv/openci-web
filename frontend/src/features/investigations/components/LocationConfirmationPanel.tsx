import { useCallback, useState } from "react";
import { MapPinCheck } from "lucide-react";
import {
  confirmInvestigationLocation,
  getInvestigationLocation,
} from "@/features/investigations/api";
import type { Investigation } from "@/types/api";
import { useResource } from "@/hooks/useResource";
import { LocationPicker } from "@/components/map/LocationPicker";
import { InlineAlert, Skeleton } from "@/components/ui/Primitives";
export function LocationConfirmationPanel({
  token,
  investigation,
  onChanged,
}: {
  token: string;
  investigation: Investigation;
  onChanged: () => void;
}) {
  const resource = useResource(
    useCallback(
      () => getInvestigationLocation(token, investigation.id),
      [token, investigation.id],
    ),
    { resourceKeys: [`investigation-location:${investigation.id}`] },
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  return (
    <section id="location" className="workflow-panel investigation-location-panel">
      <div className="section-heading">
        <div>
          <div className="workflow-title">
            <span className="workflow-title-icon" aria-hidden="true">
              <MapPinCheck size={17} strokeWidth={2} />
            </span>
            <div>
              <h3>Investigation location</h3>
              <p>A confirmed location is required for route optimization.</p>
            </div>
          </div>
        </div>
        <span className="count-badge">
          {investigation.location_confirmed ? "Confirmed" : "Unconfirmed"}
        </span>
      </div>
      {resource.error && (
        <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
      )}
      {error && <InlineAlert>{error}</InlineAlert>}
      {message && <InlineAlert variant="success">{message}</InlineAlert>}
      {saving && <p role="status">Saving confirmed location…</p>}
      {resource.loading ? (
        <Skeleton rows={3} />
      ) : (
        !resource.error && (
          <LocationPicker
            key={resource.data?.confirmed_at ?? "unconfirmed"}
            token={token}
            initial={
              resource.data
                ? { ...resource.data, label: investigation.address_display }
                : null
            }
            initialQuery={investigation.address_display}
            onConfirm={(point) => {
              setSaving(true);
              setError("");
              setMessage("");
              return confirmInvestigationLocation(
                token,
                investigation.id,
                point,
              )
                .then(() => {
                  setMessage(
                    "Location confirmed. Address edits will require confirmation again.",
                  );
                  onChanged();
                  resource.refresh();
                })
                .catch((error: unknown) => {
                  setError(
                    error instanceof Error
                      ? error.message
                      : "Could not confirm this point.",
                  );
                  throw error;
                })
                .finally(() => setSaving(false));
            }}
          />
        )
      )}
      {resource.data && (
        <details className="workflow-history location-index-details">
          <summary>Technical details · H3 cell IDs</summary>
          <p>
            H3 resolution 7: {resource.data.h3_r7}
            <br />
            Resolution 8: {resource.data.h3_r8}
            <br />
            Resolution 9: {resource.data.h3_r9}
          </p>
        </details>
      )}
    </section>
  );
}
