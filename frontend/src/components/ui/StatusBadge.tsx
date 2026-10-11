import type { InvestigationStatus } from "../../types/api";

type StatusBadgeProps = {
  status: InvestigationStatus;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-${status.replaceAll("_", "-")}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
