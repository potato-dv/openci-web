import { CheckCircle2, CircleX, History } from "lucide-react";

type HistoryAccessSectionProps = {
  agentId: number;
  agentName: string;
  effectiveAllowed: boolean;
  selection: "allow" | "deny";
  hasPendingChange: boolean;
  onSelectionChange: (selection: "allow" | "deny") => void;
};

const description =
  "View completed investigations, earlier report versions, and investigation activity for cases currently assigned to you.";

export function HistoryAccessSection({
  agentId,
  agentName,
  effectiveAllowed,
  selection,
  hasPendingChange,
  onSelectionChange,
}: HistoryAccessSectionProps) {
  return (
    <section
      className="history-access-section"
      aria-labelledby="history-access-heading"
    >
      <div className="history-access-heading">
        <div className="history-access-title">
          <History size={18} strokeWidth={2} aria-hidden="true" />
          <h3 id="history-access-heading">History Access</h3>
        </div>
        <p className="history-access-agent">Agent: {agentName}</p>
      </div>
      <article className="history-access-row">
        <div className="history-access-info">
          <h4>View own history</h4>
          <p>{description}</p>
        </div>
        <fieldset className="history-access-choices">
          <legend className="sr-only">View own history permission</legend>
          {(["allow", "deny"] as const).map((effect) => (
            <label className="history-access-choice" key={effect}>
              <input
                type="radio"
                name={`history-access-${agentId}`}
                value={effect}
                checked={selection === effect}
                onChange={() => onSelectionChange(effect)}
              />
              <span>{effect === "allow" ? "Allow" : "Deny"}</span>
            </label>
          ))}
        </fieldset>
      </article>
      <div className="history-access-effective" aria-live="polite">
        <h4>Effective access</h4>
        <p className={effectiveAllowed ? "is-allowed" : "is-denied"}>
          {effectiveAllowed ? (
            <CheckCircle2 size={18} strokeWidth={2} aria-hidden="true" />
          ) : (
            <CircleX size={18} strokeWidth={2} aria-hidden="true" />
          )}
          <span>
            {agentName} {effectiveAllowed ? "can" : "cannot"} view their
            investigation history.
          </span>
        </p>
        {hasPendingChange && (
          <p className="history-access-pending">
            Unsaved selection: {selection === "allow" ? "Allow" : "Deny"}
          </p>
        )}
      </div>
    </section>
  );
}
