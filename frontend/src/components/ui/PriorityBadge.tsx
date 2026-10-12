import type { InvestigationPriority } from "../../types/api";

type PriorityBadgeProps = {
  priority: InvestigationPriority;
};

export function PriorityBadge({ priority }: PriorityBadgeProps) {
  return (
    <span className={`priority-badge priority-${priority}`}>
      {priority}
    </span>
  );
}
