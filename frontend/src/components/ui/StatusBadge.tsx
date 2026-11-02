import type { InvestigationStatus } from "../../types/api";
import { date } from "../../utils/format";

type StatusBadgeProps = {
  status: InvestigationStatus;
  reopenOn?: string | null;
};

export function StatusBadge({ status, reopenOn }: StatusBadgeProps) {
  const label =
    status === "cancelled" && reopenOn
      ? `cancelled · reopens ${date(reopenOn)}`
      : status.replaceAll("_", " ");
  return (
    <span className={`status-badge status-${status.replaceAll("_", "-")}`}>
      {label}
    </span>
  );
}
